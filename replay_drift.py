#!/usr/bin/env python3
"""The day-130 step-4 registered test: report-day drift (PREREGISTER_day130_drift.md).

On an earnings reaction day, does the first half hour against XIU.TO
(09:30 → 10:00) predict the rest of the day (10:00 → close) in the same
direction?

    python replay_drift.py [--cache DIR]     writes data/replay_day130_drift.json

The reaction session is chosen causally: D0 (the first session on or after
FMP's report date) or D1, whichever first opens with a gap at least twice the
name's median absolute gap over the 20 sessions before D0. Every FMP response
is cached under --cache, so an interrupted run resumes.
"""
from __future__ import annotations

import argparse
import concurrent.futures as cf
import datetime as dt
import hashlib
import json
import random
import statistics as st
import sys
import threading
import time
from pathlib import Path

import fmp_client as F
from replay_fmp_analyst import clustered, pool_tickers

START, END = '2024-01-02', '2026-10-09'
OUT = Path(__file__).with_name('data') / 'replay_day130_drift.json'
GAP_MULT, LOOKBACK = 2.0, 20
PLANTED, DRAWS, COST, BIG = 0.5, 2000, 0.10, 1.0
OPEN, T1000, NOON, EXIT = '09:30:00', '09:55:00', '11:55:00', '15:55:00'
RATE = 9.0                        # calls per second, as fmp_context


class Fetch:
    """FMP GETs, throttled and cached on disk. Failures are counted by code."""

    def __init__(self, cache=None, get=F.get):
        self.cache, self.get = (Path(cache) if cache else None), get
        self.lock, self.next_at, self.failures = threading.Lock(), 0.0, {}
        if self.cache:
            self.cache.mkdir(parents=True, exist_ok=True)

    def __call__(self, path, **params):
        name = hashlib.sha256(json.dumps([path, params], sort_keys=True).encode()).hexdigest()[:24]
        f = self.cache / (name + '.json') if self.cache else None
        if f and f.exists():
            return json.loads(f.read_text())
        with self.lock:
            wait = self.next_at - time.monotonic()
            self.next_at = max(self.next_at, time.monotonic()) + 1.0 / RATE
        if wait > 0:
            time.sleep(wait)
        try:
            data = self.get(path, retries=2, **params)
        except F.FMPError as exc:
            with self.lock:
                self.failures[str(exc)] = self.failures.get(str(exc), 0) + 1
            return None
        if f:
            f.write_text(json.dumps(data))
        return data


def five(rows):
    """{date: {'open', 'p1000', 'noon', 'close'}} from FMP 5-minute rows."""
    by = {}
    for b in rows or []:
        d, t = b['date'].split(' ')
        by.setdefault(d, {})[t] = b
    out = {}
    for d, bs in by.items():
        if all(k in bs for k in (OPEN, T1000, NOON, EXIT)):
            out[d] = {'open': bs[OPEN]['open'], 'p1000': bs[T1000]['close'],
                      'noon': bs[NOON]['close'], 'close': bs[EXIT]['close']}
    return out


def daily(rows):
    """[(date, open, close)] ascending, from FMP end-of-day rows."""
    out = [(r['date'], r.get('open'), r.get('close')) for r in rows or []
           if isinstance(r.get('open'), (int, float)) and isinstance(r.get('close'), (int, float))]
    return sorted(out)


def reaction(days, report_date):
    """(D0, D1, event session or None, why). Each candidate is judged on its own
    opening gap against the 20 sessions before D0 — nothing from later."""
    dates = [d for d, _, _ in days]
    after = [i for i, d in enumerate(dates) if d >= report_date]
    if not after or after[0] < LOOKBACK + 1:
        return None, None, None, 'no daily history'
    i0 = after[0]
    gaps = [abs(days[j][1] / days[j - 1][2] - 1) for j in range(i0 - LOOKBACK, i0)]
    med = st.median(gaps)
    d1 = dates[i0 + 1] if i0 + 1 < len(dates) else None
    for i in (i0, i0 + 1):
        if i >= len(days):
            break
        if med > 0 and abs(days[i][1] / days[i - 1][2] - 1) >= GAP_MULT * med:
            return dates[i0], d1, dates[i], None
    return dates[i0], d1, None, 'no gap twice the median on D0 or D1'


def window(d0, d1):
    a = dt.date.fromisoformat(d0) - dt.timedelta(days=14)
    b = dt.date.fromisoformat(d1 or d0) + dt.timedelta(days=3)
    return a.isoformat(), b.isoformat()


def xy(s, m, end='close'):
    """(x30, y) in %: x30 against XIU 09:30 → 10:00; y = sign(x30) × (name − XIU) 10:00 → end."""
    x30 = 100 * ((s['p1000'] / s['open'] - 1) - (m['p1000'] / m['open'] - 1))
    if x30 == 0:
        return x30, None
    sign = 1 if x30 > 0 else -1
    return x30, sign * 100 * ((s[end] / s['p1000'] - 1) - (m[end] / m['p1000'] - 1))


def run(tickers, fetch):
    with cf.ThreadPoolExecutor(8) as pool:
        earns = dict(zip(tickers, pool.map(lambda t: fetch('earnings', symbol=t), tickers)))
        eods = dict(zip(tickers, pool.map(lambda t: daily(fetch(
            'historical-price-eod/full', symbol=t, **{'from': '2023-11-01', 'to': END})), tickers)))
    counts = {'names': len(tickers), 'reports': 0, 'no_daily_history': 0, 'no_reaction_gap': 0,
              'events': 0, 'no_bars': 0, 'x30_zero': 0}
    events, report_days = [], {}
    for t in tickers:
        reps = sorted({r['date'] for r in earns.get(t) or []
                       if r.get('epsActual') is not None and START <= r.get('date', '') <= END})
        report_days[t] = reps
        for rd in reps:
            counts['reports'] += 1
            d0, d1, ev, why = reaction(eods.get(t) or [], rd)
            if ev is None:
                counts['no_daily_history' if why == 'no daily history' else 'no_reaction_gap'] += 1
                continue
            gap = next(o / p - 1 for (d, o, _), (_, _, p) in zip(eods[t][1:], eods[t]) if d == ev)
            events.append({'ticker': t, 'report_date': rd, 'd0': d0, 'd1': d1, 'session': ev,
                           'gap_pct': round(100 * gap, 3)})
    counts['events'] = len(events)
    ranges = sorted({window(e['d0'], e['d1']) for e in events})
    with cf.ThreadPoolExecutor(8) as pool:
        xiu = dict(zip(ranges, pool.map(lambda r: five(fetch(
            'historical-chart/5min', symbol='XIU.TO', **{'from': r[0], 'to': r[1]})), ranges)))
        bars = list(pool.map(lambda e: five(fetch(
            'historical-chart/5min', symbol=e['ticker'],
            **dict(zip(('from', 'to'), window(e['d0'], e['d1']))))), events))
    rows, placebo = [], []
    for e, s in zip(events, bars):
        m = xiu[window(e['d0'], e['d1'])]
        if e['session'] not in s or e['session'] not in m:
            counts['no_bars'] += 1
            continue
        x30, y = xy(s[e['session']], m[e['session']])
        if y is None:
            counts['x30_zero'] += 1
            continue
        _, y_noon = xy(s[e['session']], m[e['session']], 'noon')
        rows.append({**e, 'x30': round(x30, 4), 'y': round(y, 4), 'y_noon': round(y_noon, 4),
                     'gap_agrees': (x30 > 0) == (e['gap_pct'] > 0)})
        # Placebo sessions: the same name's window, never near any of its reports.
        near = set()
        for rd in report_days[e['ticker']]:
            base = dt.date.fromisoformat(rd)
            near |= {(base + dt.timedelta(days=k)).isoformat() for k in range(-3, 6)}
        lo, hi = e['d0'], e['d1'] or e['d0']
        pool_ = []
        for d in sorted(s):
            if d in m and d not in near and not (lo <= d <= hi):
                _, py = xy(s[d], m[d])
                if py is not None:
                    pool_.append(py)
        placebo.append(pool_)
    return rows, placebo, counts


def summarize(rows, placebo, counts, failures, *, seed=130):
    def stat(xs):
        mean, se, t = clustered([(r['session'], r[xs[1]]) for r in xs[0]])
        return {'n': len(xs[0]), 'mean_pct': None if mean is None else round(mean, 4),
                'se': None if se is None else round(se, 4), 't': None if t is None else round(t, 2),
                'hit': round(sum(r[xs[1]] > 0 for r in xs[0]) / len(xs[0]), 3) if xs[0] else None}
    main = stat((rows, 'y'))
    ordered = sorted(rows, key=lambda r: r['session'])
    q = len(ordered) // 4
    quarters = [ordered[i * q:(i + 1) * q] if i < 3 else ordered[3 * q:] for i in range(4)]
    qmeans = [round(st.mean(r['y'] for r in part), 4) if part else None for part in quarters]
    rng = random.Random(seed)
    usable = [p for p in placebo if p]
    draws = [st.mean(rng.choice(p) for p in usable) for _ in range(DRAWS)] if usable else []
    p_val = (sum(d >= main['mean_pct'] for d in draws) / len(draws)) if draws and main['mean_pct'] is not None else None
    se = main['se']
    planted_t = round(PLANTED / se, 2) if se else None
    checks = {
        'mean_positive_t_ge_3': bool(main['mean_pct'] and main['mean_pct'] > 0 and (main['t'] or 0) >= 3),
        'all_four_quarters_positive': all(m is not None and m > 0 for m in qmeans),
        'placebo_p_below_0_05': p_val is not None and p_val < 0.05,
        'control_detects_planted_0_5': bool(planted_t and planted_t >= 3),
        'net_of_0_10_positive': bool(main['mean_pct'] is not None and main['mean_pct'] - COST > 0)}
    verdict = ('PASS' if all(checks.values()) else
               'UNDERPOWERED' if not checks['control_detects_planted_0_5'] else 'FAIL')
    big = [r for r in rows if abs(r['x30']) >= BIG]
    small = [r for r in rows if abs(r['x30']) < BIG]
    return {
        'registered': 'PREREGISTER_day130_drift.md', 'run_on': dt.date.today().isoformat(),
        'window': [START, END], 'counts': counts, 'fetch_failures': failures,
        'primary': main, 'quarter_means_pct': qmeans,
        'placebo': {'draws': len(draws), 'events_with_a_placebo_pool': len(usable),
                    'mean_of_draws_pct': round(st.mean(draws), 4) if draws else None, 'p': p_val},
        'control': {'planted_pct': PLANTED, 't_planted': planted_t,
                    'mde80_pct': round(2.8 * se, 3) if se else None},
        'net_of_cost_pct': None if main['mean_pct'] is None else round(main['mean_pct'] - COST, 4),
        'checks': checks, 'verdict': verdict,
        'descriptive': {
            'abs_x30_ge_1pct': stat((big, 'y')), 'abs_x30_below_1pct': stat((small, 'y')),
            'x30_agrees_with_gap': stat(([r for r in rows if r['gap_agrees']], 'y')),
            'x30_against_gap': stat(([r for r in rows if not r['gap_agrees']], 'y')),
            'noon_exit_10_to_12': stat((rows, 'y_noon'))},
    }


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    p.add_argument('--state-dir', default='.rb-state')
    p.add_argument('--cache', help='directory for FMP responses, so a run can resume')
    p.add_argument('--out', default=str(OUT))
    a = p.parse_args(argv)
    F.load_key(a.state_dir)
    fetch = Fetch(a.cache)
    tickers = pool_tickers(a.state_dir)
    rows, placebo, counts = run(tickers, fetch)
    out = summarize(rows, placebo, counts, fetch.failures)
    out['rows'] = rows
    Path(a.out).write_text(json.dumps(out, indent=1, sort_keys=True) + '\n')
    print(json.dumps({k: v for k, v in out.items() if k != 'rows'}, indent=1, sort_keys=True))
    return 0


if __name__ == '__main__':
    sys.exit(main())
