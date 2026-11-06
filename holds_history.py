"""Day-147 (council lab item 8, PREREGISTER_day147_holds.md): held for days,
do the models' reads come true over one, three or five sessions?

The population is the scoreboard's "All model picks together"
(`model_picks.pooled_card`'s rule), sessions 2026-09-17 -> 2026-10-29: each
scored model pick once per session, ticker and side. Each is entered at its
recorded 09:45 price (`entry`) and closed at FMP's daily close H sessions
later, by XIU.TO's session calendar, against XIU.TO over the same window
(its 09:45 price is the close of FMP's 09:40 five-minute bar):

    y_H = side x (the pick's return - XIU's return), in %, per pick.

H = 3 is the registered verdict, judged on day-145's machinery
(`best_first.t_stat` and `best_first.placebo`) at seed 147. H = 1 and H = 5,
the same picks closed the same day (y0), raw returns, sides, models and
Claude's own nominations are described beside it, never judged. FMP calls
only (cached under .rb-state/holds_day147_cache): no OpenRouter, no model.

    python holds_history.py --out data/holds_day147.json
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import math
import statistics as st
import sys
from pathlib import Path

import best_first as B

ROOT = Path(__file__).resolve().parent
CACHE = ROOT / '.rb-state' / 'holds_day147_cache'
OUT = ROOT / 'data' / 'holds_day147.json'
FIRST, LAST = '2026-09-17', '2026-10-29'      # the registered window; it does not move
CLAUDE_FIRST = '2026-10-14'                   # Claude's recorded nominations start here
HORIZONS = (1, 3, 5)
VERDICT_H = 3
BENCH = 'XIU.TO'
ENTRY_BAR = '09:40:00'                        # FMP labels a bar by its start: 09:40-09:45
SEED = 147
DRAWS = B.DRAWS
PLANT = 1.0                                   # % added to every pick in the control
BAR_T, BAR_P = B.BAR_T, B.BAR_P
BASIS_TOLERANCE = 0.05                        # FMP's same-day close vs the record's exit
REGISTRATION = 'PREREGISTER_day147_holds.md'


def _num(v):
    return B._num(v)


def _cost():
    return B._cost()


def population(rows, *, first=FIRST, last=LAST):
    """The pooled rule (`model_picks.pooled_card`) inside the window: the first
    scored row per (session, ticker, side), file order kept."""
    import model_picks as M
    seen = {}
    for r in rows:
        if (not r.get('scored_at') or r.get('kind') not in M.POOLED_KINDS
                or r.get('model') in M.POOLED_EXCLUDED):
            continue
        if not (first <= (r.get('session') or '') <= last):
            continue
        seen.setdefault((r['session'], r['ticker'], r['side']), r)
    return list(seen.values())


def claude_nominations(rows, *, first=CLAUDE_FIRST, last=LAST):
    """Claude's own scored nominations in the window, one per session, ticker
    and side (descriptive arm)."""
    seen = {}
    for r in rows:
        if r.get('model') != 'claude' or r.get('kind') != 'nominated' or not r.get('scored_at'):
            continue
        if not (first <= (r.get('session') or '') <= last):
            continue
        seen.setdefault((r['session'], r['ticker'], r['side']), r)
    return list(seen.values())


def first_named(noms, *, db=B.DB, reviews=B.REVIEWS):
    """Claude's first-named long and short per session (the live Top 2's rule),
    ordered by the frozen report, else the evening review, as day-145."""
    frozen = B.frozen_orders(db)
    have = {}
    for r in noms:
        have.setdefault((r['session'], r['side']), set()).add(r['ticker'])
    out = []
    for (session, side), tickers in sorted(have.items()):
        order = frozen.get((session, 'claude', side)) or []
        if not (order and set(order) >= tickers):
            order = B.review_order(session, 'claude', side, reviews)
        if order and order[0] in tickers:
            out.append((session, side, order[0]))
    keep = set(out)
    return [r for r in noms if (r['session'], r['side'], r['ticker']) in keep]


def daily(fetch, ticker, start, end):
    """{date: close} from FMP's daily bars."""
    rows = fetch('historical-price-eod/full', symbol=ticker, **{'from': start, 'to': end}) or []
    out = {}
    for b in rows:
        c = _num(b.get('close'))
        if b.get('date') and c and c > 0:
            out[b['date'][:10]] = c
    return out


def bench_entry(fetch, session):
    """XIU.TO's 09:45 price that session: the close of FMP's 09:40 bar."""
    rows = fetch('historical-chart/5min', symbol=BENCH, **{'from': session, 'to': session}) or []
    for b in rows:
        if b.get('date') == '%s %s' % (session, ENTRY_BAR):
            c = _num(b.get('close'))
            return c if c and c > 0 else None
    return None


def outcomes(picks, fetch, *, horizons=HORIZONS, end=None):
    """(rows, left_out). Each row carries y0 and y_H for every horizon; a pick
    with any missing price is left out and counted by reason, never filled."""
    # Never past yesterday: a session still trading has no close yet.
    end = end or min(dt.date.fromisoformat(LAST) + dt.timedelta(days=14),
                     dt.date.today() - dt.timedelta(days=1)).isoformat()
    start = (dt.date.fromisoformat(FIRST) - dt.timedelta(days=7)).isoformat()
    xiu = daily(fetch, BENCH, start, end)
    calendar = sorted(xiu)
    entries = {s: bench_entry(fetch, s) for s in sorted({p['session'] for p in picks})}
    closes = {t: daily(fetch, t, start, end) for t in sorted({p['ticker'] for p in picks})}
    left = {}
    rows = []

    def drop(reason):
        left[reason] = left.get(reason, 0) + 1

    for p in picks:
        s, t = p['session'], p['ticker']
        sign = 1 if p['side'] == 'LONG' else -1
        entry = _num(p.get('entry'))
        if not entry or entry <= 0:
            drop('no recorded entry')
            continue
        if s not in xiu or not entries.get(s):
            drop('no XIU price that session')
            continue
        i = calendar.index(s)
        if i + max(horizons) >= len(calendar):
            drop('the horizon is not closed yet')
            continue
        own = closes.get(t) or {}
        days = [calendar[i + h] for h in (0,) + tuple(horizons)]
        if any(d not in own for d in days):
            drop('a missing close')
            continue
        recorded_exit = _num(p.get('exit'))
        if recorded_exit and abs(own[s] / recorded_exit - 1) > BASIS_TOLERANCE:
            drop('basis mismatch (split or bad bar)')
            continue
        x0 = entries[s]
        out = {'session': s, 'ticker': t, 'side': p['side'], 'model': p.get('model'),
               'kind': p.get('kind'), 'entry': entry, 'r_pct': _num(p.get('r_pct'))}
        for h, d in zip((0,) + tuple(horizons), days):
            pick_r = own[d] / entry - 1
            bench_r = xiu[d] / x0 - 1
            out['y%d' % h] = round(100 * sign * (pick_r - bench_r), 4)
            out['raw%d' % h] = round(100 * sign * pick_r, 4)
        rows.append(out)
    return rows, left


def session_means(rows, key):
    by = {}
    for r in rows:
        by.setdefault(r['session'], []).append(r[key])
    return [(s, st.mean(v)) for s, v in sorted(by.items())]


def control(rows, key):
    """House rule 10: every y centred on zero, then PLANT added to every pick,
    and the same t taken over session means."""
    m = st.mean(r[key] for r in rows)
    planted = [dict(r, **{key: r[key] - m + PLANT}) for r in rows]
    t = B.t_stat([v for _, v in session_means(planted, key)])
    return {'planted_pct': PLANT, 't': None if t is None else round(t, 2),
            'detected': t is not None and t >= BAR_T}


def verdict(rows, key='y%d' % VERDICT_H, *, draws=DRAWS, seed=SEED):
    """The registered decision over the session means of y_H."""
    days = session_means(rows, key)
    ds = [v for _, v in days]
    n = len(ds)
    t = B.t_stat(ds)
    half = n // 2
    halves = [st.mean(ds[:half]), st.mean(ds[half:])] if half else []
    p_up = B.placebo(ds, tail='upper', draws=draws, seed=seed)
    p_down = B.placebo(ds, tail='lower', draws=draws, seed=seed)
    ctl = control(rows, key) if rows else {'detected': False, 't': None, 'planted_pct': PLANT}
    mean = st.mean(ds) if ds else None
    sd = st.stdev(ds) if n > 1 else None
    drift = (t is not None and mean > 0 and t >= BAR_T and p_up is not None and p_up < BAR_P
             and halves and all(h > 0 for h in halves) and mean - _cost() > 0)
    reversal = (t is not None and t <= -BAR_T and p_down is not None and p_down < BAR_P
                and halves and all(h < 0 for h in halves))
    status = ('DRIFT' if drift else 'REVERSAL' if reversal else
              'UNDERPOWERED' if not ctl['detected'] else 'NULL')
    return {'status': status, 'horizon': key, 'sessions': n, 'picks': len(rows),
            'mean': None if mean is None else round(mean, 3),
            'net': None if mean is None else round(mean - _cost(), 3),
            't': None if t is None else round(t, 2),
            'placebo_p_upper': None if p_up is None else round(p_up, 4),
            'placebo_p_lower': None if p_down is None else round(p_down, 4),
            'halves': [round(h, 3) for h in halves],
            'right': sum(r[key] > 0 for r in rows),
            'control': ctl,
            'mde': round((BAR_T + 0.84) * sd / math.sqrt(n), 3) if sd else None,
            'by_session': [{'session': s, 'mean': round(v, 3)} for s, v in days]}


def _arm(rows, key):
    if not rows:
        return {'picks': 0}
    ys = [r[key] for r in rows]
    ds = [v for _, v in session_means(rows, key)]
    t = B.t_stat(ds)
    return {'picks': len(ys), 'sessions': len(ds), 'right': sum(y > 0 for y in ys),
            'mean': round(st.mean(ys), 3), 't': None if t is None else round(t, 2)}


def describe(rows, claude_rows, claude_first_rows):
    """Beside the verdict, never part of it."""
    keys = ['y0'] + ['y%d' % h for h in HORIZONS]
    out = {'by_horizon': {k: _arm(rows, k) for k in keys},
           'raw': {('raw%d' % h): _arm(rows, 'raw%d' % h) for h in (0,) + HORIZONS},
           'record_r_pct': _arm([r for r in rows if r['r_pct'] is not None], 'r_pct')}
    paired = [dict(r, d=r['y%d' % VERDICT_H] - r['y0']) for r in rows]
    out['held_minus_same_day'] = _arm(paired, 'd')
    out['by_side'] = {s: {k: _arm([r for r in rows if r['side'] == s], k) for k in keys}
                      for s in ('LONG', 'SHORT')}
    models = sorted({r['model'] for r in rows})
    out['by_first_model'] = {m: {k: _arm([r for r in rows if r['model'] == m], k) for k in keys}
                             for m in models}
    out['claude_nominations'] = {k: _arm(claude_rows, k) for k in keys}
    out['claude_first_named'] = {k: _arm(claude_first_rows, k) for k in keys}
    return out


def run(rows=None, fetch=None, *, db=B.DB, reviews=B.REVIEWS, draws=DRAWS, seed=SEED, end=None):
    import model_picks as M
    rows = M.read() if rows is None else rows
    if fetch is None:
        from replay_drift import Fetch
        fetch = Fetch(CACHE)
    picks = population(rows)
    got, left = outcomes(picks, fetch, end=end)
    noms = claude_nominations(rows)
    claude_got, claude_left = outcomes(noms, fetch, end=end)
    first = {(r['session'], r['side'], r['ticker']) for r in first_named(noms, db=db, reviews=reviews)}
    claude_first = [r for r in claude_got if (r['session'], r['side'], r['ticker']) in first]
    failures = dict(getattr(fetch, 'failures', {}) or {})
    return {'registration': REGISTRATION, 'window': [FIRST, LAST], 'seed': seed, 'draws': draws,
            'cost_pct': _cost(), 'population': len(picks), 'scored': len(got), 'left_out': left,
            'claude': {'nominations': len(noms), 'scored': len(claude_got), 'left_out': claude_left,
                       'first_named': len(claude_first)},
            'fmp_failures': failures,
            'verdict': verdict(got, draws=draws, seed=seed) if got else {'status': 'NO_DATA'},
            'reported': {('y%d' % h): verdict(got, 'y%d' % h, draws=draws, seed=seed)
                         for h in HORIZONS if h != VERDICT_H} if got else {},
            'describe': describe(got, claude_got, claude_first) if got else {},
            'rows': got}


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    p.add_argument('--out', default=str(OUT), help='write the summary here')
    a = p.parse_args(argv)
    got = run()
    text = json.dumps(got, indent=1)
    Path(a.out).write_text(text + '\n')
    shown = {k: v for k, v in got.items() if k != 'rows'}
    for v in [shown.get('verdict')] + list((shown.get('reported') or {}).values()):
        if isinstance(v, dict):
            v.pop('by_session', None)
    print(json.dumps(shown, indent=1))
    return 0


if __name__ == '__main__':
    sys.exit(main())
