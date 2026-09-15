"""Local expanded-research coverage. No acquisition, model calls or selection.

Report assembly checks candidate receipts against actual cached bytes. Preflight
additionally runs the production completed-history validator over every staged
name; a manifest or claimed count alone cannot certify technical readiness.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import math
from pathlib import Path
from zoneinfo import ZoneInfo

from diagnostics import safe_detail

ET = ZoneInfo('America/New_York')
REQUIRED = ('vwap', 'rsi', 'macd', 'macd_signal', 'macd_hist', 'orb_high', 'orb_low', 'rvol')


def _read(path):
    if path.stat().st_size > 16_000_000:
        raise ValueError('RESEARCH_COVERAGE_INPUT_TOO_LARGE')
    obj = json.loads(path.read_text(), parse_constant=lambda _: (_ for _ in ()).throw(ValueError('NONFINITE_JSON')))
    if not isinstance(obj, dict):
        raise ValueError('RESEARCH_COVERAGE_OBJECT_REQUIRED')
    return obj


def _stamp(value, now, *, diagnostic=False):
    stamp = dt.datetime.fromisoformat(value)
    if stamp.tzinfo is None or stamp > now or stamp.astimezone(ET).date() != now.date():
        raise ValueError('RESEARCH_COVERAGE_CLOCK_MISMATCH')
    if not diagnostic and stamp.astimezone(ET).time() >= dt.time(9, 30):
        raise ValueError('RESEARCH_COVERAGE_NOT_PREOPEN')
    return stamp.isoformat()


def _complete(row):
    tech = row.get('technicals') or {}
    return isinstance(tech, dict) and all(type(tech.get(k)) in (int, float)
            and math.isfinite(tech[k]) for k in REQUIRED)


def _reason(exc):
    reason = str(exc)
    return reason if reason and all(c.isupper() or c.isdigit() or c in '_:' for c in reason) else type(exc).__name__


def _verify_row(row, state, cfg, now, *, verify_history=False, diagnostic=False):
    from bar_cache import key
    ticker = row['ticker']
    provenance = row.get('technical_provenance')
    if not isinstance(provenance, dict) or row.get('technical_source') != 'python':
        raise ValueError('RESEARCH_CACHE_RECEIPT_MISMATCH')
    # An eligible baseline identity may be backed by the independent research
    # cache. Resolve its actual immutable input hash rather than guessing the
    # producer's directory from the current selection roster.
    sources = ['factor_pool_cache']
    if ticker in set(cfg.get('scan', {}).get('universe', [])):
        sources.insert(0, 'intraday_cache')
    last_error = FileNotFoundError()
    for source in sources:
        directory = state/source
        try:
            raw = (directory/key(ticker)).read_bytes()
            if hashlib.sha256(raw).hexdigest() != provenance.get('input_sha256'):
                raise ValueError('RESEARCH_CACHE_RECEIPT_MISMATCH')
            import prepare_factor_pool
            prepare_factor_pool._cache_manifest(ticker, directory, now, diagnostic=diagnostic)
            if source == 'factor_pool_cache':
                prepare_factor_pool._validate_research_receipt(ticker, directory, now, diagnostic=diagnostic)
            actual = row
            if verify_history:
                validator = prepare_factor_pool._cached if source == 'intraday_cache' else prepare_factor_pool._research_cached
                actual, _ = validator(ticker, directory, cfg, now, diagnostic=diagnostic)
                if actual.get('technicals') != row.get('technicals'):
                    raise ValueError('RESEARCH_STAGED_TECHNICALS_MISMATCH')
            return actual, source+'/'+key(ticker)
        except (OSError, ValueError, TypeError, KeyError, IndexError) as exc:
            # Keep a concrete validation failure ahead of a second missing file.
            if not isinstance(exc, FileNotFoundError) or isinstance(last_error, FileNotFoundError):
                last_error = exc
    raise last_error


def inspect_pool(state, cfg, now, *, verify_history=False, diagnostic=False):
    """Read saved identities and actual cache bytes; optional full validation."""
    if now.tzinfo is None:
        raise ValueError('AWARE_CLOCK_REQUIRED')
    now = now.astimezone(ET)
    state = Path(state)
    result = {'status': 'UNAVAILABLE', 'session': now.date().isoformat(),
              'requested': None, 'verified': 0, 'complete_technicals': 0,
              'reused_baseline': 0, 'errors': {}, 'technical_tickers': [], 'cache_sources': {},
              'validation': 'completed_history' if verify_history else 'receipt_and_cache_hash',
              'reason': 'Research pool not prepared for this session.'}
    try:
        staged = _read(state/'factor_pool_status.json')
        if staged.get('session') != now.date().isoformat():
            raise ValueError('RESEARCH_POOL_WRONG_SESSION')
        from diagnostic_context import SNAPSHOT_KIND
        is_diagnostic = staged.get('kind') == SNAPSHOT_KIND
        if is_diagnostic != diagnostic or (diagnostic and staged.get('morning_snapshot') is not False):
            raise ValueError('RESEARCH_POOL_CONTEXT_MISMATCH')
        if staged.get('status') not in ('READY', 'PARTIAL', 'UNAVAILABLE', 'NOT READY', 'PREPARING'):
            raise ValueError('INVALID_OPTIONAL_POOL_STATUS')
        for field in ('requested', 'verified', 'complete_technicals', 'reused_baseline'):
            if type(staged.get(field)) is not int or not 0 <= staged[field] <= 500:
                raise ValueError('INVALID_OPTIONAL_POOL_COUNT')
        result['requested'] = staged['requested']
        result['reused_baseline'] = staged['reused_baseline']
        result['started_at'] = _stamp(staged['started_at'], now, diagnostic=diagnostic)
        # Incomplete/preparing checkpoints are auditable; they are never READY.
        if staged.get('completed_at'):
            result['completed_at'] = _stamp(staged['completed_at'], now, diagnostic=diagnostic)
        path = state/'deepseek_candidates.json'
        payload = _read(path)
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        history_path = state/'factor_pool_history'/now.date().isoformat()/'candidates.json'
        if (digest != staged.get('candidates_sha256') or not history_path.is_file()
                or hashlib.sha256(history_path.read_bytes()).hexdigest() != digest):
            raise ValueError('PREPARED_POOL_MISSING_OR_CHANGED')
        _stamp(payload.get('as_of'), now, diagnostic=diagnostic)
        if (payload.get('kind') == SNAPSHOT_KIND) != diagnostic:
            raise ValueError('RESEARCH_POOL_CONTEXT_MISMATCH')
        rows = payload.get('candidates')
        if not isinstance(rows, list) or len(rows) != result['requested']:
            raise ValueError('RESEARCH_POOL_COUNT_MISMATCH')
        from factor_inputs import TICKER
        tickers = [r.get('ticker') if isinstance(r, dict) else None for r in rows]
        if any(not isinstance(t, str) or not TICKER.fullmatch(t) for t in tickers) or len(set(tickers)) != len(tickers):
            raise ValueError('RESEARCH_POOL_IDENTITIES_INVALID')
        universe = payload.get('research_universe')
        if universe is not None:
            if not isinstance(universe, dict):
                raise ValueError('RESEARCH_UNIVERSE_METADATA_INVALID')
            result['research_universe'] = universe
        errors = staged.get('errors') or {}
        if not isinstance(errors, dict):
            raise ValueError('INVALID_OPTIONAL_POOL_ERRORS')
        result['errors'] = {safe_detail(str(k), 24): safe_detail(str(v), 120)
                            for k, v in list(errors.items())[:502]}
        result['tickers'] = tickers
        result['candidates_sha256'] = digest
        for row in rows:
            ticker = row['ticker']
            if not row.get('technical_provenance'):
                result['errors'].setdefault(ticker, 'PYTHON_TECHNICALS_NOT_STAGED')
                continue
            try:
                actual, source = _verify_row(row, state, cfg, now,
                    verify_history=verify_history, diagnostic=diagnostic)
                result['cache_sources'][ticker] = source
                result['verified'] += 1
                if _complete(actual):
                    result['technical_tickers'].append(ticker)
                else:
                    result['errors'][ticker] = 'TECHNICAL_HISTORY_INCOMPLETE'
            except (OSError, ValueError, TypeError, KeyError, IndexError) as exc:
                result['errors'][ticker] = _reason(exc)
        result['complete_technicals'] = len(result['technical_tickers'])
        result['status'] = ('READY' if result['requested'] and result['complete_technicals'] == result['requested']
                            else 'PARTIAL' if result['verified'] else 'UNAVAILABLE')
        if staged['status'] in ('PREPARING', 'NOT READY'):
            result['status'] = 'NOT READY'
            result['errors']['preparation'] = 'PREPARATION_NOT_COMPLETED_READY'
        result.pop('reason', None)
    except (OSError, ValueError, TypeError, KeyError, IndexError) as exc:
        result['status'] = 'UNAVAILABLE'
        result['reason'] = _reason(exc)
    return result


def load_prepared(state, cfg, now, factors=None, *, verify_history=False, diagnostic=False, pool=None):
    """Independent local coverage survives an unavailable model assessment."""
    if now.tzinfo is None:
        raise ValueError('AWARE_CLOCK_REQUIRED')
    now = now.astimezone(ET)
    state = Path(state)
    pool = pool if pool is not None else inspect_pool(state, cfg, now, verify_history=verify_history, diagnostic=diagnostic)
    import tsx_universe
    master = tsx_universe.load_prepared(state, now, diagnostic=diagnostic)
    factors = factors or {}
    staged_universe = pool.get('research_universe') or factors.get('research_universe') or {}
    master_rows = master.get('candidates') or []
    fallback = staged_universe.get('mode') == 'LEGACY_RESEARCH_FALLBACK'
    expanded_status = 'UNAVAILABLE'
    if (master.get('status') in ('READY', 'PARTIAL') and
            staged_universe.get('mode') == 'EXPANDED_TSX_RESEARCH'):
        expanded_status = ('READY' if master['status'] == pool['status'] == 'READY' else
                           'PARTIAL' if pool.get('verified') else 'UNAVAILABLE')
    result = {'status': expanded_status, 'session': now.date().isoformat(),
              'master_status': master.get('status', 'UNAVAILABLE'), 'target': master.get('target', 150),
              'master_eligible': len(master_rows), 'mode': staged_universe.get('mode', 'UNAVAILABLE'),
              'pool_requested': pool.get('requested'), 'pool_status': pool['status'], 'technical_complete': pool.get('complete_technicals', 0),
              'shortlisted': None, 'assessed': factors.get('covered', 0),
              'usable': (factors.get('research_watchlist') or {}).get('evaluated', 0),
              'pool': pool, 'master': master, 'source_coverage': master.get('source_coverage') or {},
              'master_exclusions': master.get('exclusions') or [],
              'gaps': list(master.get('gaps') or []),
              'adopted': False, 'registration': 'PREREGISTER_day101_tsx_expansion.md'}
    if pool.get('reason'):
        result['gaps'].append(pool['reason'])
    if fallback:
        result['gaps'].append('LEGACY_RESEARCH_FALLBACK: '+safe_detail(staged_universe.get('fallback_reason') or 'Expanded universe unavailable.'))
    if master.get('reason'):
        result['gaps'].append(safe_detail(master['reason']))
    shortlist = factors.get('research_shortlist') or {}
    selected = set(shortlist.get('tickers') or [])
    if shortlist:
        result['shortlisted'] = shortlist.get('selected_count')
        result['shortlist_exclusions'] = shortlist.get('exclusions') or []
        result['gaps'].extend(shortlist.get('gaps') or [])
    pool_names = set(pool.get('tickers') or [])
    complete = set(pool.get('technical_tickers') or [])
    assessed = {r['ticker'] for r in factors.get('assessments') or []}
    # The source master supplies industry facts; fallback membership is never
    # upgraded to a certified master by having a cached technical observation.
    metadata = {r['ticker']: r for r in master_rows if isinstance(r, dict) and isinstance(r.get('ticker'), str)}
    result['sectors'] = []
    result['industries'] = []
    for key, output in (('sector', 'sectors'), ('industry', 'industries')):
        counts = {}
        for ticker in sorted(pool_names):
            name = safe_detail(metadata.get(ticker, {}).get(key) or 'Unverified classification', 100)
            item = counts.setdefault(name, {'name': name, 'pool': 0, 'technical_complete': 0, 'shortlisted': 0 if shortlist else None, 'assessed': 0})
            item['pool'] += 1
            item['technical_complete'] += ticker in complete
            if shortlist:
                item['shortlisted'] += ticker in selected
            item['assessed'] += ticker in assessed
        result[output] = [counts[k] for k in sorted(counts)]
    result['news_status'] = factors.get('news_status') or {}
    return result
