"""Stage a separate TSX factor research pool before open; never select trades."""
from __future__ import annotations

import argparse
import datetime as dt
import fcntl
import hashlib
import json
import re
import time
from pathlib import Path
from urllib.parse import quote
from zoneinfo import ZoneInfo

from bar_cache import key
from build_biotech import write_atomic
from diagnostic_context import SNAPSHOT_KIND
from factor_inputs import _from_cache, _previous_close
import factor_pool_policy as P

ET = ZoneInfo('America/New_York')
ROOT = Path(__file__).resolve().parent


def fetch_history(ticker, now):
    """Exact Canadian identity plus raw chart receipt; historical data only."""
    from adapters import YahooDirectAdapter
    adapter = YahooDirectAdapter(timeout=14)
    adapter.chart_budget_seconds = P.REQUEST_SECONDS - 1
    raw = adapter._chart(ticker, '5m', '60d')
    meta = raw.get('meta', {})
    if (meta.get('symbol') != ticker or meta.get('currency') != 'CAD'
            or meta.get('exchangeName') != 'TOR'
            or meta.get('instrumentType') != 'EQUITY'):
        raise ValueError('RESEARCH_IDENTITY_NOT_VERIFIED')
    bars = adapter._bars_df(raw)
    bars = bars[[i.date() < now.date() for i in bars.index]]
    if bars.empty or bars.index[-1].date() != _previous_close(now).date():
        raise ValueError('RESEARCH_PRIOR_SESSION_MISSING')
    frame = {'columns': list(bars.columns), 'index': [i.isoformat() for i in bars.index],
             'data': bars.to_numpy().tolist()}
    return {'ticker': ticker, 'session': now.date().isoformat(),
            'frame': json.dumps(frame, allow_nan=False), 'receipt': raw,
            'retrieved_at': dt.datetime.now(ET).isoformat()}


def _cache_manifest(ticker, directory, now, *, diagnostic=False):
    manifest = json.loads((directory/'manifest.json').read_text())
    if not isinstance(manifest, dict):
        raise ValueError('RESEARCH_CACHE_INVALID_MANIFEST')
    prepared = dt.datetime.fromisoformat(manifest['prepared_at'])
    is_diagnostic = manifest.get('kind') == SNAPSHOT_KIND
    if is_diagnostic and (not diagnostic or manifest.get('morning_snapshot') is not False):
        raise ValueError('RESEARCH_DIAGNOSTIC_CACHE_NOT_PREOPEN')
    if (prepared.tzinfo is None or prepared.astimezone(ET).date() != now.date()
            or (prepared.astimezone(ET).time() >= dt.time(9, 30) and not is_diagnostic)
            or prepared > now
            or manifest.get('session') != now.date().isoformat()
            or manifest.get('source') != 'yahoo_direct'
            or ticker not in manifest.get('tickers', [])):
        raise ValueError('RESEARCH_CACHE_IDENTITY_MISMATCH')
    return manifest


def _cached(ticker, directory, cfg, now, *, diagnostic=False):
    manifest = _cache_manifest(ticker, directory, now, diagnostic=diagnostic)
    return _from_cache(ticker, directory, manifest, cfg, now)


def _validate_research_receipt(ticker, directory, now, *, diagnostic=False):
    """Validate actual saved bytes and receipt identity without rerunning metrics."""
    path = directory/key(ticker)
    raw = path.read_bytes()
    receipt = json.loads((directory/(key(ticker)+'.receipt')).read_text())
    if (not isinstance(receipt, dict) or not isinstance(receipt.get('response'), dict)
            or not isinstance(receipt['response'].get('meta'), dict)):
        raise ValueError('RESEARCH_CACHE_INVALID_RECEIPT')
    retrieved = dt.datetime.fromisoformat(receipt['retrieved_at'])
    meta = receipt['response']['meta']
    if (retrieved.tzinfo is None or retrieved > now
            or retrieved.astimezone(ET).date() != now.date()
            or (not diagnostic and retrieved.astimezone(ET).time() >= dt.time(9, 30))
            or receipt.get('input_sha256') != hashlib.sha256(raw).hexdigest()
            or meta.get('symbol') != ticker or meta.get('currency') != 'CAD'
            or meta.get('exchangeName') != 'TOR'
            or meta.get('instrumentType') != 'EQUITY'):
        raise ValueError('RESEARCH_CACHE_RECEIPT_MISMATCH')
    return receipt


def _research_cached(ticker, directory, cfg, now, *, diagnostic=False):
    """Validate the saved file, source receipt and indicators before reusing bars.

    A manifest alone does not establish coverage. Previous-session or diagnostic
    caches cannot be relabelled as a current production preparation.
    """
    _validate_research_receipt(ticker, directory, now, diagnostic=diagnostic)
    return _cached(ticker, directory, cfg, now, diagnostic=diagnostic)


def _research_universe(root, now, *, diagnostic=False):
    """Consume the prepared security master locally; never discover on this path."""
    try:
        from tsx_universe import load_prepared
        master = load_prepared(root, now, diagnostic=diagnostic)
    except (OSError, ValueError, TypeError, KeyError) as exc:
        master = {'status': 'UNAVAILABLE', 'session': now.date().isoformat(),
                  'candidates': [], 'gaps': ['SECURITY_MASTER_LOAD_'+type(exc).__name__]}
    except ModuleNotFoundError as exc:
        if exc.name != 'tsx_universe':
            raise
        master = {'status': 'UNAVAILABLE', 'session': now.date().isoformat(),
                  'candidates': [], 'gaps': ['SECURITY_MASTER_LOADER_UNAVAILABLE']}
    if not isinstance(master, dict):
        master = {'status': 'UNAVAILABLE', 'session': now.date().isoformat(),
                  'candidates': [], 'gaps': ['SECURITY_MASTER_INVALID_RESULT']}
    candidates = master.get('candidates')
    eligible = (master.get('status') in ('READY', 'PARTIAL')
                and master.get('session') == now.date().isoformat()
                and isinstance(candidates, list) and 0 < len(candidates) <= P.EXPANDED_TARGET
                and all(isinstance(row, dict) and isinstance(row.get('ticker'), str)
                        and row['ticker'].endswith('.TO') for row in candidates))
    if eligible and len({row['ticker'] for row in candidates}) != len(candidates):
        eligible = False
    broader = eligible and len(candidates) > len(P.TICKERS)
    if broader:
        tickers = tuple(row['ticker'] for row in candidates)
        return tickers, {**master, 'target': P.EXPANDED_TARGET,
            'mode': 'EXPANDED_TSX_RESEARCH', 'fallback_reason': None,
            'source_requested': len(tickers), 'selected_count': len(tickers),
            'expanded_status': master['status']}
    return P.TICKERS, {**master, 'target': P.EXPANDED_TARGET,
        'mode': 'LEGACY_RESEARCH_FALLBACK', 'expanded_status': 'UNAVAILABLE',
        'fallback_reason': ('EXPANDED_POOL_NOT_BROADER_THAN_LEGACY' if eligible
                            else 'NO_CURRENT_VALIDATED_EXPANDED_CANDIDATES'),
        'source_requested': len(P.TICKERS), 'selected_count': len(P.TICKERS),
        'fallback_registration': P.REGISTRATION}


def prepare(state_dir, cfg, *, now=None, fetcher=None, acquire_fn=None,
            daily_fetcher=None, biotech_snapshot=None):
    """Once/session, incremental checkpoints, bounded acquisition and no retries.

    Baseline cache is only read. Every requested name remains in the output,
    including failed names, so partial coverage cannot masquerade as a full pool.
    """
    return _prepare(state_dir, cfg, now=now, fetcher=fetcher, acquire_fn=acquire_fn,
                    daily_fetcher=daily_fetcher, biotech_snapshot=biotech_snapshot)


def prepare_diagnostic(state_dir, cfg, *, now=None, fetcher=None, acquire_fn=None,
                       daily_fetcher=None, biotech_snapshot=None):
    """Run the same pool preparation with real clocks in an isolated diagnostic.

    Diagnostic history is previous-session context acquired now, never a cache
    that was available before open. This entry point does not alter production's
    deadline or permit replacing/retrying a scheduled preparation attempt.
    """
    from diagnostic_context import require_context
    require_context(Path(state_dir))
    return _prepare(state_dir, cfg, now=now, fetcher=fetcher,
                    acquire_fn=acquire_fn, diagnostic=True,
                    daily_fetcher=daily_fetcher, biotech_snapshot=biotech_snapshot)


SECTORS_PATH = ROOT/'data'/'tsx_sectors.json'
MIN_SECTOR_MEMBERS = 3


MAX_SECTOR_MAP_AGE_DAYS = 62   # PREREGISTER_day101: reference facts at most 62 days old


def load_sector_map(path=None, today=None):
    """The committed map, or {} when it is missing or older than 62 days."""
    try:
        import datetime as _real   # the real module: tests patch `dt`
        doc = json.loads(Path(path or SECTORS_PATH).read_text())
        captured = _real.date.fromisoformat(doc['captured'])
        if today is None:
            today = _real.date.today()
        if not 0 <= (today - captured).days <= MAX_SECTOR_MAP_AGE_DAYS:
            return {}
        return doc['sectors']
    except (OSError, ValueError, KeyError, TypeError):
        return {}


def sector_context(rows, sectors=None, today=None):
    """Label each CA row with its sector and its move relative to that sector.

    Returns how many rows received a relative move."""
    import statistics
    # The LABEL stays off the candidate: day-101's registration keeps sector
    # classification out of the model payload. Only the measured numbers ride.
    if sectors is None:
        sectors = load_sector_map(today=today)
        if not sectors:
            return 0
    moves = {}
    for ticker, row in rows.items():
        label = (sectors.get(ticker) or {}).get('sector')
        if not label or row.get('market', 'CA') != 'CA':
            continue
        t = row.get('technicals') or {}
        if isinstance(t.get('move_atr'), (int, float)) and isinstance(t.get('atr_pct'), (int, float)):
            moves.setdefault(label, []).append((ticker, t['move_atr']*t['atr_pct']))
    placed = 0
    for label, members in moves.items():
        if len(members) < MIN_SECTOR_MEMBERS:
            continue
        median = statistics.median(m for _, m in members)
        for ticker, move in members:
            rows[ticker]['technicals']['sector_move_pct'] = round(median, 4)
            rows[ticker]['technicals']['rel_sector_pct'] = round(move-median, 4)
            placed += 1
    return placed


def earnings_days(rows, now, client=None):
    """Write `days_to_earnings` into each row's technicals; return how many."""
    import quotes
    client = client or quotes.YahooMarketData(auth_state_dir=False)
    today = now.astimezone(ET).date()
    names = [t for t in rows if rows[t].get('technicals') is not None]
    dated = 0
    for start in range(0, len(names), 50):
        raw = client.get(names[start:start+50])
        for ticker, row in (raw or {}).items():
            if not isinstance(row, dict) or ticker not in rows:
                continue
            stamp = row.get('earningsTimestampStart') or row.get('earningsTimestamp')
            if type(stamp) not in (int, float) or isinstance(stamp, bool):
                continue
            days = (dt.datetime.fromtimestamp(stamp, ET).date() - today).days
            if -120 <= days <= 180:
                rows[ticker]['technicals']['days_to_earnings'] = float(days)
                dated += 1
    return dated


def _prepare(state_dir, cfg, *, now=None, fetcher=None, acquire_fn=None,
             diagnostic=False, daily_fetcher=None, biotech_snapshot=None):
    from bounded import acquire
    live_clock = now is None
    now = now or dt.datetime.now(ET)
    if now.tzinfo is None:
        raise ValueError('AWARE_CLOCK_REQUIRED')
    now = now.astimezone(ET)
    if not diagnostic and now.time() >= dt.time(9, 30):
        raise ValueError('RESEARCH_POOL_PREOPEN_ONLY')
    context = ({'kind': SNAPSHOT_KIND, 'morning_snapshot': False}
               if diagnostic else {})
    started_monotonic = time.monotonic()
    # Capture whether the CALLER injected, before defaulting destroys the
    # evidence. The daily and biotech passes below key off this: gating them
    # on `fetcher is None` after this line made both dead code, and the run
    # reported daily_filled 0 / biotech_added 0 while looking healthy.
    # ANY injection means the caller is running deterministically. Keying only
    # on `fetcher` was not enough: several tests inject `acquire_fn` alone, and
    # the daily pass then opened real sockets behind their mock and filled the
    # very names they assert were NOT acquired.
    injected = fetcher is not None or acquire_fn is not None
    fetcher = fetcher or fetch_history
    acquire_fn = acquire_fn or acquire
    root = Path(state_dir)
    if not diagnostic and (root/'diagnostic_context.json').exists():
        raise ValueError('RESEARCH_POOL_DIAGNOSTIC_CONTEXT_REQUIRES_EXPLICIT_RUN')
    history = root/'factor_pool_history'/now.date().isoformat()
    history.mkdir(parents=True, exist_ok=True)
    with (history/'lock').open('a') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return {'status': 'UNAVAILABLE', 'session': now.date().isoformat(),
                    'reason': 'PREPARATION_IN_PROGRESS_NO_RETRY', 'adopted': False,
                    **context}
        attempt = history/'attempt.json'
        if attempt.exists():
            # An interrupted attempt is not authorization to acquire again.
            prior = json.loads(attempt.read_text())
            saved = history/'candidates.json'
            current = root/'deepseek_candidates.json'
            if ((prior.get('kind') == SNAPSHOT_KIND) != diagnostic
                    or (diagnostic and prior.get('morning_snapshot') is not False)):
                return {**prior, **context, 'status': 'UNAVAILABLE',
                        'replay_gap': 'RESEARCH_POOL_CONTEXT_MISMATCH_NO_RETRY'}
            if prior.get('status') == 'PREPARING':
                return {**prior, 'status': 'UNAVAILABLE', 'replay_gap': 'INTERRUPTED_PREPARATION_NO_RETRY'}
            if (not saved.exists() or not current.exists()
                    or hashlib.sha256(saved.read_bytes()).hexdigest() != prior.get('candidates_sha256')
                    or current.read_bytes() != saved.read_bytes()):
                return {**prior, 'status': 'UNAVAILABLE', 'replay_gap': 'PREPARED_POOL_MISSING_OR_CHANGED_NO_RETRY'}
            return prior
        tickers, universe = _research_universe(root, now, diagnostic=diagnostic)
        expanded = universe['mode'] == 'EXPANDED_TSX_RESEARCH'
        registration = P.EXPANSION_REGISTRATION if expanded else P.REGISTRATION
        budget_seconds = P.EXPANDED_BUDGET_SECONDS if expanded else P.BUDGET_SECONDS
        status = {'status': 'PREPARING', 'session': now.date().isoformat(),
                  'started_at': now.isoformat(), 'requested': len(tickers),
                  'verified': 0, 'reused_baseline': 0, 'reused_research': 0, 'errors': {},
                  'cache_reuse_gaps': {}, 'research_universe': universe,
                  'budget_seconds': budget_seconds,
                  'complete_technicals': 0,
                  'identity_scope': 'New names: exact CAD/Toronto/equity provider metadata; baseline: existing validated cache identity.',
                  'registration': registration, 'adopted': False, **context}
        write_atomic(attempt, status)
        directory = root/'factor_pool_cache'
        directory.mkdir(parents=True, exist_ok=True)
        manifest = {'session': status['session'], 'source': 'yahoo_direct',
                    'tickers': list(tickers), 'complete': False,
                    'prepared_at': now.isoformat(), **context}
        rows, diagnostics, pending = {}, {}, []
        baseline = set(cfg['scan']['universe'])
        for ticker in tickers:
            if ticker not in baseline:
                if (directory/'manifest.json').exists():
                    try:
                        rows[ticker], diagnostics[ticker] = _research_cached(
                            ticker, directory, cfg, now, diagnostic=diagnostic)
                        status['reused_research'] += 1
                        continue
                    except (OSError, ValueError, TypeError, KeyError, IndexError) as exc:
                        status['cache_reuse_gaps'][ticker] = 'RESEARCH_CACHE_REJECTED_'+type(exc).__name__
                pending.append(ticker)
                continue
            try:
                rows[ticker], diagnostics[ticker] = _cached(ticker, root/'intraday_cache', cfg, now)
                status['reused_baseline'] += 1
            except (OSError, ValueError, TypeError, KeyError, IndexError) as exc:
                # A stale baseline cache used to EXCLUDE the ticker outright,
                # and baseline names were the only ones with no live fallback —
                # research names already fall through to `pending`. The effect
                # was that the twenty-one names the report actually trades were
                # the twenty-one guaranteed to be dropped whenever the pre-open
                # staging job had not run, which is exactly what produced
                # "0/60 assessed" with "prepared technicals 21" in the
                # 2026-09-15 email. Caching changes acquisition only, not
                # features or rules, so acquire them live inside the same
                # budget instead — and say that it happened.
                status['cache_reuse_gaps'][ticker] = 'BASELINE_CACHE_REJECTED_'+type(exc).__name__
                pending.append(ticker)
        # Preserve the old manifest until all reuse checks have inspected it.
        write_atomic(directory/'manifest.json', manifest)
        budget = budget_seconds if diagnostic else min(budget_seconds,
            (now.replace(hour=9, minute=30, second=0, microsecond=0)-now).total_seconds())
        deadline = started_monotonic + budget

        def checkpoint():
            status['verified'] = len(rows)
            required = ('vwap', 'rsi', 'macd', 'macd_signal', 'macd_hist', 'orb_high', 'orb_low', 'rvol')
            status['complete_technicals'] = sum(all(item.get('technicals', {}).get(k) is not None
                    for k in required) for item in rows.values())
            assembled = dt.datetime.now(ET) if live_clock else now
            all_diagnostics = {t: list(diagnostics.get(t, [])) for t in tickers}
            for ticker in tickers:
                if ticker in status['errors']:
                    all_diagnostics[ticker].append(status['errors'][ticker])
            payload = {'as_of': assembled.isoformat(), 'candidates': [rows.get(t, {'ticker': t})
                        for t in tickers], 'macro': {},
                       'candidate_diagnostics': {t: notes for t, notes in all_diagnostics.items()
                           if notes}, 'pool_registration': registration,
                       'research_universe': universe, **context}
            write_atomic(root/'deepseek_candidates.json', payload)
            write_atomic(history/'candidates.json', payload)
            status['candidates_sha256'] = hashlib.sha256((history/'candidates.json').read_bytes()).hexdigest()
            write_atomic(root/'factor_pool_status.json', status)
            write_atomic(attempt, status)

        checkpoint()
        for offset in range(0, len(pending), P.WORKERS):
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                status['errors']['pool'] = 'RESEARCH_PREPARATION_BUDGET_EXHAUSTED'
                break
            batch = pending[offset:offset+P.WORKERS]
            results = acquire_fn({t: (lambda t=t: fetcher(t, now),
                                       min(P.REQUEST_SECONDS, remaining)) for t in batch})
            if not diagnostic and live_clock and dt.datetime.now(ET).time() >= dt.time(9, 30):
                status['errors']['clock'] = 'PREOPEN_DEADLINE_REACHED_RESULTS_NOT_STAGED'
                break
            refusal = False
            unavailable = 0
            for ticker in batch:
                result = results[ticker]
                if result['status'] != 'OK':
                    unavailable += 1
                    reason = result.get('error', 'ACQUISITION_UNAVAILABLE')
                    # Exception classes only, never raw provider response text.
                    status['errors'][ticker] = reason if str(reason).isidentifier() else 'ACQUISITION_UNAVAILABLE'
                    if reason in ('ChartRateLimitError', 'ChartAuthenticationError'):
                        refusal = True
                    continue
                item = result['value']
                try:
                    receipt = item.pop('receipt')
                    retrieved = item.pop('retrieved_at')
                    write_atomic(directory/key(ticker), item)
                    write_atomic(directory/(key(ticker)+'.receipt'),
                                 {'retrieved_at': retrieved, 'response': receipt,
                                  'input_sha256': hashlib.sha256(
                                      (directory/key(ticker)).read_bytes()).hexdigest()})
                    cache_clock = dt.datetime.now(ET) if live_clock else now
                    if diagnostic:
                        rows[ticker], diagnostics[ticker] = _cached(ticker, directory, cfg,
                            cache_clock, diagnostic=True)
                    else:
                        rows[ticker], diagnostics[ticker] = _cached(ticker, directory, cfg,
                            cache_clock)
                except (OSError, ValueError, TypeError, KeyError, IndexError):
                    status['errors'][ticker] = 'RESEARCH_HISTORY_VALIDATION_FAILED'
            checkpoint()
            if refusal or unavailable == len(batch):
                status['errors']['provider'] = 'PROVIDER_OUTAGE_FURTHER_REQUESTS_SKIPPED'
                break
        # ── DAILY-BAR PASS: the fix for "the same tickers every day" ────────
        # The five-minute path above covered 38 of 130 names on 2026-09-18 and
        # covered THE SAME 38 the day before — 38 of 38 overlap. MACD needs 35
        # contiguous complete sessions and Yahoo serves ~41 sessions of 5-minute
        # history, so the warm-up, not the roster, is the gate. A daily request
        # returns ~250 sessions and is a far smaller response, so it both warms
        # up and fails less. Probed: 25 of 25 TSX names complete this way.
        #
        # Daily bars fill the daily indicators ONLY. `r0`, `vwap` and the
        # opening range are intraday quantities and stay with the five-minute
        # panel; a name covered only daily simply carries fewer fields, which
        # `_row` already handles by omitting what is absent.
        status['daily_filled'] = 0
        status['daily_errors'] = {}
        # INJECTION, not a hard-coded adapter. The five-minute path above takes
        # `fetcher`; a daily pass that ignored it would reach the real network
        # from inside a test that had carefully mocked the provider, making the
        # suite non-hermetic and its results nondeterministic. When a caller
        # injects a fetcher it is running deterministically, so the daily pass
        # runs only with its own injected counterpart.
        if daily_fetcher is None and not injected:
            try:
                import daily_technicals
                from adapters import YahooDirectAdapter
                adapter = YahooDirectAdapter(timeout=14)
                daily_fetcher = lambda t, _a=adapter: daily_technicals.from_yahoo(t, _a, now)
            except Exception as exc:
                status['daily_errors']['pool'] = 'DAILY_PASS_UNAVAILABLE_'+type(exc).__name__
        for ticker in tickers if daily_fetcher else ():
            if time.monotonic() >= deadline:
                status['daily_errors']['pool'] = 'DAILY_PASS_BUDGET_EXHAUSTED'
                break
            if not diagnostic and live_clock and dt.datetime.now(ET).time() >= dt.time(9, 30):
                status['daily_errors']['clock'] = 'PREOPEN_DEADLINE_REACHED'
                break
            existing = (rows.get(ticker) or {}).get('technicals') or {}
            # Skip only when the daily CONTEXT is also present. Day-113 added
            # scale and location (ATR, prior-session levels, trend distance)
            # that only daily bars can supply; skipping every name the
            # five-minute panel had covered would have left the best-covered
            # names as the only ones WITHOUT it.
            if all(existing.get(k) is not None for k in ('rsi', 'macd_hist', 'rvol', 'atr_pct')):
                continue
            try:
                technicals, meta = daily_fetcher(ticker)
            except Exception as exc:
                status['daily_errors'][ticker] = (str(exc) if isinstance(exc, ValueError)
                    and re.fullmatch(r'[A-Z0-9_]{1,60}', str(exc)) else type(exc).__name__)
                continue
            merged = dict(rows.get(ticker) or {'ticker': ticker})
            # Five-minute values WIN where they exist: they are the intraday
            # facts. Daily only fills what the warm-up could not produce.
            import daily_technicals as _dt
            merged['technicals'] = {**_dt.model_fields(technicals),
                                    **{k: v for k, v in existing.items() if v is not None}}
            merged.setdefault('technical_source', 'python')
            merged.setdefault('source_url',
                'https://query1.finance.yahoo.com/v8/finance/chart/'+quote(ticker, safe=''))
            merged['technicals_as_of'] = merged.get('technicals_as_of') or now.isoformat()
            import daily_technicals as _dt
            merged['technicals_scope'] = _dt.scope(technicals['daily_sessions'],
                                                 meta.get('rebuilt_sessions') or ())
            merged['market'] = 'CA'
            merged['currency'] = meta.get('currency') or 'CAD'
            rows[ticker] = merged
            status['daily_filled'] += 1
        # ── BIOTECH: a different market, from bars already on disk ──────────
        # build_biotech.py stages US biotech securities with `daily_bars`
        # attached, which is exactly this module's input, so folding them in
        # costs no acquisition at all. They are US/USD and the baseline engine
        # neither scores nor prices them — every row is tagged so a biotech
        # name can never be read as a TSX board leg.
        status['biotech_added'] = 0
        if biotech_snapshot is None and not injected:
            try:
                biotech_snapshot = json.loads((ROOT/'data'/'biotech_snapshot.json').read_text())
            except (OSError, UnicodeError, ValueError):
                biotech_snapshot = None
        try:
            if biotech_snapshot is None:
                raise ValueError('BIOTECH_SNAPSHOT_NOT_SUPPLIED')
            import daily_technicals
            extra, biotech_gaps = daily_technicals.from_biotech_snapshot(biotech_snapshot, now)
            for item in extra:
                if item['ticker'] in rows:
                    continue
                rows[item['ticker']] = item
                tickers = tickers + (item['ticker'],)
                status['biotech_added'] += 1
            status['biotech_gaps'] = len(biotech_gaps)
        except Exception as exc:
            status['biotech_error'] = (str(exc) if isinstance(exc, ValueError)
                and re.fullmatch(r'[A-Z0-9_]{1,60}', str(exc)) else type(exc).__name__)
        # ── EARNINGS PROXIMITY: the DATE only (day-113 review, item 3) ──────
        # A name reporting tonight is a different instrument for six hours.
        # The quote endpoint already carries the scheduled report timestamp;
        # one batched request per fifty names. Signed calendar days, negative
        # when the report is behind us. No estimate, no expected move, nothing
        # about what the report will say.
        status['earnings_dated'] = 0
        if not injected and rows:
            try:
                status['earnings_dated'] = earnings_days(rows, now)
            except Exception as exc:
                status['earnings_error'] = type(exc).__name__
        # ── SECTOR CONTEXT from the pool's own constituents (item 2) ────────
        # The model was told a name is Energy and shown WTI; it was never told
        # what Energy DID. Measured from the pool itself — the median last-
        # session move of the names sharing a sector — so it costs no request
        # and cannot fail on a missing ETF quote. A sector needs three members.
        status['sector_context'] = sector_context(rows, today=now.astimezone(ET).date())
        for ticker in tickers:
            if ticker not in rows:
                status['errors'].setdefault(ticker, 'NOT_ACQUIRED')
            elif 'market' not in rows[ticker]:
                rows[ticker]['market'], rows[ticker]['currency'] = 'CA', 'CAD'
        status['requested'] = len(tickers)
        status['status'] = ('READY' if status['complete_technicals'] == len(tickers)
                            else 'PARTIAL' if rows else 'UNAVAILABLE')
        if not diagnostic and live_clock and dt.datetime.now(ET).time() >= dt.time(9, 30):
            status['status'] = 'NOT READY'
            status['errors']['clock'] = 'PREOPEN_DEADLINE_REACHED'
        status['completed_at'] = (dt.datetime.now(ET) if live_clock else now).isoformat()
        manifest['complete'] = status['status'] == 'READY'
        manifest['verified'] = list(rows)
        write_atomic(directory/'manifest.json', manifest)
        checkpoint()
        return status


if __name__ == '__main__':
    from dashboard import load_config
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--state-dir', required=True)
    parser.add_argument('--config', default=str(Path(__file__).with_name('config.yaml')))
    args = parser.parse_args()
    # A GUARD REFUSING IS NOT A CRASH. Run after 09:30 this raised
    # RESEARCH_POOL_PREOPEN_ONLY as a bare traceback, which in a morning log is
    # indistinguishable from the job breaking — and the distinction is the
    # whole diagnosis: one means "too late, correctly declined", the other
    # means "fix me". Name the reason and exit 3 for a refusal.
    try:
        result = prepare(args.state_dir, load_config(args.config))
    except ValueError as exc:
        reason = str(exc)
        if not re.fullmatch(r'[A-Z0-9_]{1,80}', reason):
            raise
        print(json.dumps({'status': 'REFUSED', 'reason': reason, 'adopted': False}, indent=2))
        raise SystemExit(3) from None
    print(json.dumps(result, indent=2))
    raise SystemExit(0 if result['status'] == 'READY' else 2)
