#!/usr/bin/env python3
"""Stage Yahoo cookie/crumb authentication near 09:40, before quote acquisition.

One bounded authentication attempt, no quote/option requests or market-price
cache. Reuse a valid private cache. No report, delivery or strategy mutation.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
from pathlib import Path
import time

from bounded import acquire
import yahoo_auth_cache as cache

AUTH_BUDGET_SECONDS = 30
AUTH_WORKER_SECONDS = 35


def _authenticate(now, clock=None):
    from quotes import YahooMarketData, _failure_details
    client = YahooMarketData(timeout=15, auth_state_dir=False)
    client._quote_deadline = time.monotonic() + AUTH_BUDGET_SECONDS
    try:
        client.auth()
    except Exception as exc:
        exc.acquisition_reason_code = _failure_details(exc)[0]
        status = getattr(exc, 'code', None)
        if type(status) is int and 100 <= status <= 599:
            exc.acquisition_http_status = status
        raise
    if time.monotonic() >= client._quote_deadline:
        raise TimeoutError('authentication preparation deadline exceeded')
    finished = (clock or (lambda: dt.datetime.now(cache.ET)))()
    return cache.document(client.cookie_jar, client.crumb, finished)


def prepare(state_dir, *, now=None, clock=None, worker=None):
    """Safe result only; credentials stay inside this function and private state."""
    clock = clock or (lambda: dt.datetime.now(cache.ET))
    now = cache._aware(now or clock())
    state = Path(state_dir)
    _, status = cache.load(state, now)
    if status['status'] == 'READY':
        return {**status, 'reused': True}
    started = time.monotonic()
    run = (worker or acquire)({'yahoo_auth': (lambda: _authenticate(now, clock), AUTH_WORKER_SECONDS)})['yahoo_auth']
    finished = cache._aware(clock())
    result = {'status': 'UNAVAILABLE', 'session': now.date().isoformat(),
              'started_at': now.isoformat(), 'checked_at': finished.isoformat(),
              'seconds': round(time.monotonic() - started, 3), 'reused': False,
              'note': 'Authentication only; live quote access and BBO timestamps are not certified.'}
    # The worker's final value is private. Its fixed progress stages are safe.
    result['stages'] = [r['stage'] for r in run.get('progress', [])
                        if r.get('stage') in {'yahoo_cookie_started', 'yahoo_cookie_completed',
                                              'yahoo_crumb_started', 'yahoo_crumb_completed'}]
    if run.get('error'):
        error = run['error']
        result['reason_code'] = ('AUTH_PREPARATION_TIMEOUT' if error in {'TimeoutError', 'TimeoutExpired'}
                                 else 'AUTH_PREPARATION_UNAVAILABLE')
        # Do not copy arbitrary exception text, worker fields or provider URLs.
        result['error_class'] = error if error in {'TimeoutError', 'TimeoutExpired', 'HTTPError',
                                                  'URLError', 'ValueError', 'AuthCacheError',
                                                  'WorkerExited'} else 'AcquisitionError'
        if run.get('reason_code') in {'AUTHENTICATION_ERROR', 'RATE_LIMITED', 'INVALID_PAYLOAD',
                                     'TRANSPORT_TIMEOUT', 'TRANSPORT_ERROR'}:
            result['reason_code'] = run['reason_code']
        http_status = run.get('http_status')
        if type(http_status) is int and 100 <= http_status <= 599:
            result['http_status'] = http_status
    else:
        try:
            cache.save(state, run['value'], finished)
            result.update(cache.load(state, finished)[1])
        except (cache.AuthCacheError, OSError, ValueError, TypeError) as exc:
            result['reason_code'] = str(exc) if isinstance(exc, cache.AuthCacheError) else 'AUTH_CACHE_SAVE_ERROR'
    cache.private_atomic(state / 'yahoo_auth_status.json', result)
    cache.private_atomic(state / 'diagnostics' / 'yahoo_auth' /
                         (finished.strftime('%Y%m%dT%H%M%S.%f') + '.json'), result)
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--state-dir', required=True)
    args = parser.parse_args(argv)
    try:
        result = prepare(args.state_dir)
    except (OSError, ValueError, TypeError) as exc:
        result = {'status': 'UNAVAILABLE', 'reason_code': 'AUTH_PREPARATION_LOCAL_FAILURE',
                  'error_class': type(exc).__name__}
    print(json.dumps(result, sort_keys=True))
    return 0 if result['status'] == 'READY' else 2


if __name__ == '__main__':
    raise SystemExit(main())
