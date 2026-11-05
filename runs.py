"""Day-146 (owner, 2026-11-04; PREREGISTER_day146_runs.md): how many sessions a
name has closed one way, read before the open from FMP's daily closes.

A run is three or more completed sessions closing the same way in a row; a
flat close breaks it. A pick that FOLLOWS a run (LONG after three rises, SHORT
after three falls) is the one the owner asked to pass over, for the rebound or
the profit-taking that can follow. The registered history test found no edge
either way (NULL, rejection #61), so this changes which picks are made, not
how often they are right.

`council.stage` records `runs` for the names on the table; `council.top_two`
reads it (`council.SKIP_RUNS`). Nothing here is sent to the members.
"""
from __future__ import annotations

import concurrent.futures as cf
import datetime as dt

RUN = 3                    # the owner's three days
LOOKBACK = 12              # sessions a run is counted back over
DAYS = 30                  # calendar days of closes asked for
WORKERS = 8
CALL_TIMEOUT = 8.0         # seconds per FMP call
DEADLINE = 20.0            # seconds for every name together; the council never waits longer
NUMBER = {2: 'two', 3: 'three', 4: 'four', 5: 'five', 6: 'six', 7: 'seven', 8: 'eight',
          9: 'nine', 10: 'ten', 11: 'eleven', 12: 'twelve'}


def _sign(x):
    return 1 if x > 0 else -1 if x < 0 else 0


def run_length(closes):
    """The signed number of sessions the closes moved one way, counted back from
    the last: +3 is three rises in a row, -3 three falls. A flat close stops
    the count. (runs_history.run_length, the registered test's, is the same.)"""
    n, s = 0, 0
    for i in range(len(closes) - 1, 0, -1):
        x = _sign(closes[i] - closes[i - 1])
        if x == 0 or (s and x != s):
            break
        s, n = x, n + 1
    return s * n


def follows(side, run):
    """True when a pick on `side` bets that a run of RUN or more carries on."""
    if isinstance(run, bool) or not isinstance(run, int):
        return False
    return (side == 'LONG' and run >= RUN) or (side == 'SHORT' and run <= -RUN)


def series(rows):
    """[(date, close)] ascending from FMP daily rows; rows without a close are dropped."""
    out = {}
    for r in rows or []:
        c, d = r.get('close'), str(r.get('date') or '')[:10]
        if d and isinstance(c, (int, float)) and not isinstance(c, bool) and c > 0:
            out[d] = float(c)
    return sorted(out.items())


def of_series(closes, prior):
    """The run record from [(date, close)], which must end on `prior` (the last
    completed session, an ISO date): {'run', 'as_of', 'dates', 'changes_pct'}
    with the run's own daily changes, at least the last RUN of them."""
    if len(closes) < 2:
        raise ValueError('TOO_FEW_DAILY_CLOSES')
    if closes[-1][0] != prior:
        raise ValueError('NOT_THE_PRIOR_SESSION')
    tail = closes[-(LOOKBACK + 1):]
    run = run_length([c for _, c in tail])
    k = min(max(abs(run), RUN), len(tail) - 1)
    last = tail[-(k + 1):]
    return {'run': run, 'as_of': prior, 'dates': [d for d, _ in last[1:]],
            'changes_pct': [round(100 * (b / a - 1), 2) for (_, a), (_, b) in zip(last, last[1:])]}


def fetch(tickers, prior, *, get=None, state_dir=None, workers=WORKERS, deadline=DEADLINE):
    """({ticker: run record}, {ticker: error code}) for the names, from FMP's
    daily closes ending on `prior`. One call per name, in parallel; a failure
    or a late answer costs that name only, and nothing waits past `deadline`."""
    tickers = sorted({t for t in tickers if t})
    if not tickers:
        return {}, {}
    if get is None:
        import fmp_client as F
        key = F.load_key(state_dir)
        start = (dt.date.fromisoformat(prior) - dt.timedelta(days=DAYS)).isoformat()

        def get(t):
            return F.get('historical-price-eod/full', key, symbol=t, timeout=CALL_TIMEOUT,
                         retries=0, **{'from': start, 'to': prior})

    def one(t):
        try:
            return of_series(series(get(t)), prior)
        except Exception as exc:          # named per name, never silent, never fatal
            msg = str(exc)
            return ValueError(msg if (msg.isupper() and ' ' not in msg) else type(exc).__name__)

    out, errors = {}, {}
    pool = cf.ThreadPoolExecutor(max(1, min(workers, len(tickers))))
    try:
        futs = {pool.submit(one, t): t for t in tickers}
        done, late = cf.wait(futs, timeout=deadline)
        for f in done:
            got = f.result()
            if isinstance(got, Exception):
                errors[futs[f]] = str(got)[:40]
            else:
                out[futs[f]] = got
        for f in late:
            errors[futs[f]] = 'TIMEOUT'
    finally:
        pool.shutdown(wait=False, cancel_futures=True)
    return out, errors


def words(rec):
    """'rose three sessions running (+0.4%, +1.2%, +0.8%)', or None without a run."""
    run = (rec or {}).get('run')
    if isinstance(run, bool) or not isinstance(run, int) or abs(run) < 2:
        return None
    changes = (rec.get('changes_pct') or [])[-abs(run):]
    out = '%s %s sessions running' % ('rose' if run > 0 else 'fell', NUMBER.get(abs(run), str(abs(run))))
    return out + (' (%s)' % ', '.join('%+.1f%%' % x for x in changes) if changes else '')
