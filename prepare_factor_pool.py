"""Stage a separate TSX factor research pool before open; never select trades."""
from __future__ import annotations

import argparse
import datetime as dt
import fcntl
import hashlib
import json
import time
from pathlib import Path
from zoneinfo import ZoneInfo

from bar_cache import key
from build_biotech import write_atomic
from diagnostic_context import SNAPSHOT_KIND
from factor_inputs import _from_cache, _previous_close
import factor_pool_policy as P

ET = ZoneInfo('America/New_York')


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


def _cached(ticker, directory, cfg, now, *, diagnostic=False):
    manifest = json.loads((directory/'manifest.json').read_text())
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
    return _from_cache(ticker, directory, manifest, cfg, now)


def prepare(state_dir, cfg, *, now=None, fetcher=None, acquire_fn=None):
    """Once/session, incremental checkpoints, bounded acquisition and no retries.

    Baseline cache is only read. Every requested name remains in the output,
    including failed names, so partial coverage cannot masquerade as a full pool.
    """
    return _prepare(state_dir, cfg, now=now, fetcher=fetcher, acquire_fn=acquire_fn)


def prepare_diagnostic(state_dir, cfg, *, now=None, fetcher=None, acquire_fn=None):
    """Run the same pool preparation with real clocks in an isolated diagnostic.

    Diagnostic history is previous-session context acquired now, never a cache
    that was available before open. This entry point does not alter production's
    deadline or permit replacing/retrying a scheduled preparation attempt.
    """
    from diagnostic_context import require_context
    require_context(Path(state_dir))
    return _prepare(state_dir, cfg, now=now, fetcher=fetcher,
                    acquire_fn=acquire_fn, diagnostic=True)


def _prepare(state_dir, cfg, *, now=None, fetcher=None, acquire_fn=None,
             diagnostic=False):
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
    fetcher = fetcher or fetch_history
    acquire_fn = acquire_fn or acquire
    root = Path(state_dir)
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
        status = {'status': 'PREPARING', 'session': now.date().isoformat(),
                  'started_at': now.isoformat(), 'requested': len(P.TICKERS),
                  'verified': 0, 'reused_baseline': 0, 'errors': {},
                  'complete_technicals': 0,
                  'identity_scope': 'New names: exact CAD/Toronto/equity provider metadata; baseline: existing validated cache identity.',
                  'registration': P.REGISTRATION, 'adopted': False, **context}
        write_atomic(attempt, status)
        directory = root/'factor_pool_cache'
        directory.mkdir(parents=True, exist_ok=True)
        manifest = {'session': status['session'], 'source': 'yahoo_direct',
                    'tickers': list(P.TICKERS), 'complete': False,
                    'prepared_at': now.isoformat(), **context}
        write_atomic(directory/'manifest.json', manifest)
        rows, diagnostics, pending = {}, {}, []
        baseline = set(cfg['scan']['universe'])
        for ticker in P.TICKERS:
            if ticker not in baseline:
                pending.append(ticker)
                continue
            try:
                rows[ticker], diagnostics[ticker] = _cached(ticker, root/'intraday_cache', cfg, now)
                status['reused_baseline'] += 1
            except (OSError, ValueError, TypeError, KeyError, IndexError):
                # Do not repeat the baseline provider's failed staging work.
                status['errors'][ticker] = 'BASELINE_HISTORY_UNAVAILABLE'
        budget = P.BUDGET_SECONDS if diagnostic else min(P.BUDGET_SECONDS,
            (now.replace(hour=9, minute=30, second=0, microsecond=0)-now).total_seconds())
        deadline = started_monotonic + budget

        def checkpoint():
            status['verified'] = len(rows)
            required = ('vwap', 'rsi', 'macd', 'macd_signal', 'macd_hist', 'orb_high', 'orb_low', 'rvol')
            status['complete_technicals'] = sum(all(item.get('technicals', {}).get(k) is not None
                    for k in required) for item in rows.values())
            assembled = dt.datetime.now(ET) if live_clock else now
            payload = {'as_of': assembled.isoformat(), 'candidates': [rows.get(t, {'ticker': t})
                        for t in P.TICKERS], 'macro': {},
                       'candidate_diagnostics': {t: notes for t, notes in diagnostics.items()
                           if notes}, 'pool_registration': P.REGISTRATION, **context}
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
            outage = False
            for ticker in batch:
                result = results[ticker]
                if result['status'] != 'OK':
                    reason = result.get('error', 'ACQUISITION_UNAVAILABLE')
                    # Exception classes only, never raw provider response text.
                    status['errors'][ticker] = reason if str(reason).isidentifier() else 'ACQUISITION_UNAVAILABLE'
                    if reason in ('ChartRateLimitError', 'ChartAuthenticationError',
                                  'ChartTimeoutError', 'TimeoutExpired', 'URLError',
                                  'ConnectionError', 'Timeout', 'ChartAcquisitionError'):
                        outage = True
                    continue
                item = result['value']
                try:
                    receipt = item.pop('receipt')
                    retrieved = item.pop('retrieved_at')
                    write_atomic(directory/(key(ticker)+'.receipt'),
                                 {'retrieved_at': retrieved, 'response': receipt})
                    write_atomic(directory/key(ticker), item)
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
            if outage:
                status['errors']['provider'] = 'PROVIDER_OUTAGE_FURTHER_REQUESTS_SKIPPED'
                break
        for ticker in P.TICKERS:
            if ticker not in rows:
                status['errors'].setdefault(ticker, 'NOT_ACQUIRED')
        status['status'] = ('READY' if status['complete_technicals'] == len(P.TICKERS)
                            else 'PARTIAL' if rows else 'UNAVAILABLE')
        if not diagnostic and live_clock and dt.datetime.now(ET).time() >= dt.time(9, 30):
            status['status'] = 'NOT READY'
            status['errors']['clock'] = 'PREOPEN_DEADLINE_REACHED'
        status['completed_at'] = dt.datetime.now(ET).isoformat()
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
    result = prepare(args.state_dir, load_config(args.config))
    print(json.dumps(result, indent=2))
    raise SystemExit(0 if result['status'] == 'READY' else 2)
