#!/usr/bin/env python3
"""Day-146 (PREREGISTER_day146_runs.md, owner 2026-11-04): does a pick that
follows a three-day run lose on day four?

A run is three completed sessions closing the same way in a row (a flat close
breaks it). Following it is LONG after an up run and SHORT after a down run.
Per name-day with a run: y = sign(run) x (the name's 09:45 -> close - XIU's).

  primary    the 150 names, FMP 15-minute session prices 2024-01-02 -> 2026-10-29
  secondary  (a) the 150 names, ten years of dividend-adjusted daily bars,
                 open -> close against XIU's
             (b) the point-in-time S&P 500, daily open -> close against SPY's

Every bar is read from day-143's cache (.rb-state/report_day_cache); the only
network call is the live record's descriptive split (FMP daily closes for the
names picked since 2026-09-17).

    python runs_history.py        # writes data/runs_day146.json
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import sys
from pathlib import Path

import numpy as np

from replay_fmp_analyst import clustered

ROOT = Path(__file__).resolve().parent
CACHE = ROOT/'.rb-state'/'report_day_cache'
NAMES = ROOT/'data'/'report_day143_names.json'
PICKS = ROOT/'data'/'model_picks.csv'
OUT = ROOT/'data'/'runs_day146.json'
START, END = '2024-01-02', '2026-10-29'
DAILY_START = '2016-01-04'
LIVE_FIRST, LIVE_LAST = '2026-09-17', '2026-11-04'
MARKET, US_MARKET = 'XIU.TO', 'SPY'
RUN = 3                                   # the owner's three days
LOOKBACK = 12                             # a run is counted back at most this far
PLANTED, DRAWS, SEED, AWAY, ATR_N = 0.10, 2000, 146, 5, 14
BAR_T, BAR_P = 3.0, 0.01
POOLED_KINDS = ('selected', 'forced', 'nominated', 'pick', 'final')
SHADOWS = ('engine', 'top2count', 'top2memory', 'top2runner', 'top2mover', 'top2wild',
           'top2council', 'top2run')


def sign(x):
    return 1 if x > 0 else -1 if x < 0 else 0


def run_length(closes):
    """The signed number of sessions the closes moved one way, counted back from
    the last: +3 is three rises in a row, -3 three falls. A flat close stops
    the count."""
    n, s = 0, 0
    for i in range(len(closes) - 1, 0, -1):
        x = sign(closes[i] - closes[i - 1])
        if x == 0 or (s and x != s):
            break
        s, n = x, n + 1
    return s * n


def atr_pct(series, i):
    """ATR14 as % of the last close, seen before session i (day-137's cut)."""
    if i < ATR_N + 2:
        return None
    trs = []
    for j in range(i - ATR_N, i):
        h, l, pc = series[j][2], series[j][3], series[j - 1][4]
        trs.append(max(h - l, abs(h - pc), abs(l - pc)))
    return 100 * (sum(trs) / len(trs)) / series[i - 1][4]


# ── the panels ────────────────────────────────────────────────────────────────

def name_rows(series, cal, market, lo, hi, *, bars=None, member=None):
    """One row per session with a run of RUN or more, for one name:
    {session, run, y, raw, atr, move3, pre, oc} with y the run-signed result
    against the market. `series` is [[date, o, h, l, c, ...]] ascending; with
    `bars` (the 15-minute session prices) the result is 09:45 -> close, else the
    day's open -> close. The name's prior session must be the market's."""
    pos = {r[0]: i for i, r in enumerate(series)}
    mpos = {d: i for i, d in enumerate(cal)}
    out, skipped = [], {'short_history': 0, 'not_the_market_session': 0, 'not_a_member': 0,
                        'no_market': 0}
    days = sorted(bars) if bars is not None else [r[0] for r in series]
    for d in days:
        if not (lo <= d <= hi):
            continue
        if d not in market:
            skipped['no_market'] += 1
            continue
        i = pos.get(d)
        if i is None:
            continue
        if i < max(ATR_N + 2, LOOKBACK + 1):
            skipped['short_history'] += 1
            continue
        if mpos.get(d, 0) < 1 or series[i - 1][0] != cal[mpos[d] - 1]:
            skipped['not_the_market_session'] += 1
            continue
        if member is not None and not member(d):
            skipped['not_a_member'] += 1
            continue
        run = run_length([r[4] for r in series[i - LOOKBACK - 1:i]])
        if abs(run) < 2:                       # 2-day runs are kept for the descriptive split
            continue
        m = market[d]
        if bars is not None:
            o, p945, _, c = bars[d]
            res, pre, oc = 100 * (c / p945 - 1), 100 * (p945 / o - 1), 100 * (c / o - 1)
            y = res - m['main']
            pre_adj, oc_adj = pre - m['pre'], oc - m['oc']
        else:
            o, c = series[i][1], series[i][4]
            res = 100 * (c / o - 1)
            y, pre_adj, oc_adj = res - m['main'], None, None
        atr = atr_pct(series, i)
        move3 = 100 * (series[i - 1][4] / series[i - 4][4] - 1)
        s = sign(run)
        out.append({'session': d, 'run': run, 'y': s * y, 'u': y, 'raw': s * res,
                    'atr': atr, 'move3_atr': (abs(move3) / atr) if atr else None,
                    'pre': None if pre_adj is None else s * pre_adj,
                    'oc': None if oc_adj is None else s * oc_adj})
    return out, skipped


def market_of(x, intraday):
    if intraday:
        return {d: {'main': 100 * (b[3] / b[1] - 1), 'pre': 100 * (b[1] / b[0] - 1),
                    'oc': 100 * (b[3] / b[0] - 1)} for d, b in x['bars'].items()}
    return {r[0]: {'main': 100 * (r[4] / r[1] - 1)} for r in x['daily']}


def panel(data, market_sym, lo, hi, *, intraday, members=None):
    """[(ticker, row)] over every name, and the skip counts."""
    mk = data[market_sym]
    series_key = 'eod' if intraday else 'daily'
    cal = [r[0] for r in mk[series_key]]
    market = market_of(mk, intraday)
    rows, counts = [], {}
    for t, x in sorted(data.items()):
        if t == market_sym or not x.get(series_key):
            continue
        member = None
        if members is not None:
            member = lambda d, t=t: any(a <= d < b for a, b in members.get(t, ()))
        got, c = name_rows(x[series_key], cal, market, lo, hi,
                           bars=x['bars'] if intraday else None, member=member)
        rows += [(t, r) for r in got]
        for k, v in c.items():
            counts[k] = counts.get(k, 0) + v
    return rows, counts


# ── the statistics (day-137's, seed 146) ─────────────────────────────────────

def stat(pairs):
    pairs = [(s, v) for s, v in pairs if v is not None]
    if len(pairs) < 2:
        return {'n': len(pairs), 'mean_pct': None, 'se': None, 't': None, 'hit': None}
    mean, se, t = clustered(pairs)
    return {'n': len(pairs), 'mean_pct': round(mean, 4), 'se': round(se, 4) if se else None,
            't': round(t, 2) if t is not None else None,
            'hit': round(sum(v > 0 for _, v in pairs) / len(pairs), 3),
            'sessions': len({s for s, _ in pairs})}


def blocks(events):
    ordered = sorted(events, key=lambda e: (e['session'], e['key']))
    q = len(ordered) // 4
    parts = [ordered[i * q:(i + 1) * q] if i < 3 else ordered[3 * q:] for i in range(4)]
    return [round(float(np.mean([e['y'] for e in p])), 4) if p else None for p in parts]


def placebo(events, draws=DRAWS, seed=SEED):
    """Each event's run sign replaced by the same name's run sign on a random
    other run session at least AWAY run sessions away; the draws' means."""
    rng = np.random.default_rng(seed)
    by = {}
    for e in sorted(events, key=lambda e: (e['key'], e['session'])):
        by.setdefault(e['key'], []).append(e)
    means = np.zeros(draws)
    used = 0
    for k, evs in by.items():
        n = len(evs)
        if n <= 2 * AWAY:
            continue
        signs = np.array([sign(e['run']) for e in evs])
        u = np.array([e['u'] for e in evs])
        own = np.arange(n)
        pick = rng.integers(0, n, size=(draws, n))
        bad = np.abs(pick - own) < AWAY
        while bad.any():
            pick[bad] = rng.integers(0, n, size=int(bad.sum()))
            bad = np.abs(pick - own) < AWAY
        means += (signs[pick] * u).sum(axis=1)
        used += n
    return means / used if used else np.array([]), used


def verdict(events, secondary_means):
    main = stat([(e['session'], e['y']) for e in events])
    qs = blocks(events)
    draws, used = placebo(events) if events else (np.array([]), 0)
    obs, se, t = main['mean_pct'], main['se'], main['t'] or 0
    p = float(np.mean(np.abs(draws) >= abs(obs))) if draws.size and obs is not None else None
    planted_t = round(PLANTED / se, 2) if se else None
    secondary_negative = all(m is not None and m < 0 for m in secondary_means)
    rev = (obs is not None and obs < 0 and t <= -BAR_T and all(x is not None and x < 0 for x in qs)
           and p is not None and p < BAR_P and secondary_negative)
    cont = (obs is not None and obs > 0 and t >= BAR_T and all(x is not None and x > 0 for x in qs)
            and p is not None and p < BAR_P)
    name = ('REVERSAL' if rev else 'CONTINUATION' if cont else
            'NULL' if planted_t and planted_t >= BAR_T else 'UNDERPOWERED')
    return {'primary': main, 'block_means_pct': qs,
            'placebo': {'draws': int(draws.size), 'events_used': used, 'p_two_sided': p,
                        'sd_of_draws_pct': round(float(draws.std()), 4) if draws.size else None},
            'control': {'planted_pct': PLANTED, 't_planted': planted_t,
                        'mde80_pct': round(2.8 * se, 3) if se else None},
            'secondary_means_negative': secondary_negative,
            'verdict': name}


# ── the live record (descriptive) ────────────────────────────────────────────

def live_picks(path=PICKS, first=LIVE_FIRST, last=LIVE_LAST):
    """The first scored row per (session, ticker, side), shadows left out."""
    seen = {}
    with open(path, newline='') as f:
        for r in csv.DictReader(f):
            if (not r.get('scored_at') or r.get('kind') not in POOLED_KINDS
                    or r.get('model') in SHADOWS or not (first <= r['session'] <= last)):
                continue
            try:
                y = float(r['r_pct'])
            except (TypeError, ValueError):
                continue
            seen.setdefault((r['session'], r['ticker'], r['side']), y)
    return seen


def live(get=None):
    import concurrent.futures as cf
    import fmp_client as F
    key = F.load_key(str(ROOT/'.rb-state'))
    get = get or (lambda t: F.get('historical-price-eod/full', key, symbol=t,
                                  **{'from': '2026-07-01', 'to': LIVE_LAST}))
    picks = live_picks()
    tickers = sorted({t for _, t, _ in picks} | {MARKET})

    def series(t):
        try:
            rows = get(t)
        except Exception as exc:                       # counted, never silent
            return t, None, type(exc).__name__
        got = sorted([str(r['date'])[:10], float(r['close'])] for r in rows or []
                     if r.get('close') is not None)
        return t, got, None
    with cf.ThreadPoolExecutor(8) as pool:
        got = list(pool.map(series, tickers))
    by = {t: s for t, s, _ in got if s}
    failed = sorted(t for t, s, e in got if not s)
    cal = [d for d, _ in by.get(MARKET, [])]
    groups, unknown = {'follows a run': [], 'does not': []}, 0
    detail = []
    for (session, t, side), y in sorted(picks.items()):
        s = by.get(t)
        if not s or session not in cal:
            unknown += 1
            continue
        dates = [d for d, _ in s]
        if session not in dates:
            unknown += 1
            continue
        i = dates.index(session)
        j = cal.index(session)
        if i < 4 or j < 1 or dates[i - 1] != cal[j - 1]:
            unknown += 1
            continue
        run = run_length([c for _, c in s[max(0, i - LOOKBACK - 1):i]])
        follows = (side == 'LONG' and run >= RUN) or (side == 'SHORT' and run <= -RUN)
        groups['follows a run' if follows else 'does not'].append((session, y))
        detail.append({'session': session, 'ticker': t, 'side': side, 'run': run, 'r_pct': round(y, 3),
                       'follows': follows})
    out = {}
    for k, v in groups.items():
        ys = [y for _, y in v]
        out[k] = {'picks': len(v), 'right': sum(y > 0 for y in ys),
                  'mean_pct': round(float(np.mean(ys)), 3) if ys else None,
                  'sessions': len({s for s, _ in v})}
    return {'window': [LIVE_FIRST, LIVE_LAST], 'unique_picks': len(picks), 'unknown': unknown,
            'fetch_failed': failed, 'groups': out,
            'note': "the record's yardstick: 09:45 -> close, raw, no costs",
            'picks': detail}


# ── the run ──────────────────────────────────────────────────────────────────

def load(kind):
    d = CACHE/kind
    if not d.exists():
        raise SystemExit('no cache: run `python report_day.py --fetch` first')
    return {f.stem: json.loads(f.read_text()) for f in d.glob('*.json')}


def events_of(rows, k=RUN):
    return [{'session': r['session'], 'key': t, 'run': r['run'], 'y': r['y'], 'u': r['u']}
            for t, r in rows if abs(r['run']) >= k]


def split(rows, test):
    return stat([(r['session'], r['y']) for t, r in rows if test(r)])


def run(*, with_live=True):
    names = json.loads(NAMES.read_text())['names']
    tsx = load('tsx')
    missing = [t for t in [MARKET] + names if t not in tsx]
    if missing:
        raise SystemExit('the cache is incomplete: %d names missing (%s)' % (len(missing), ', '.join(missing[:5])))
    tsx = {t: tsx[t] for t in [MARKET] + names}
    rows, counts = panel(tsx, MARKET, START, END, intraday=True)
    d_rows, d_counts = panel(tsx, MARKET, DAILY_START, END, intraday=False)
    us = load('us')
    intervals = {t: [tuple(x) for x in iv] for t, iv in
                 json.loads((CACHE/'sp500_membership.json').read_text())['intervals'].items()}
    us_rows, us_counts = panel(us, US_MARKET, DAILY_START, END, intraday=False, members=intervals)
    events = events_of(rows)
    sec_a = stat([(r['session'], r['y']) for t, r in d_rows if abs(r['run']) >= RUN])
    sec_b = stat([(r['session'], r['y']) for t, r in us_rows if abs(r['run']) >= RUN])
    v = verdict(events, [sec_a['mean_pct'], sec_b['mean_pct']])
    three = [(t, r) for t, r in rows if abs(r['run']) >= RUN]
    out = {
        'registered': 'PREREGISTER_day146_runs.md', 'run_on': dt.date.today().isoformat(),
        'window': [START, END], 'names': len(names), 'run_days': RUN, 'seed': SEED,
        'counts': counts, 'name_days_with_a_run_of_2_or_more': len(rows),
        **v,
        'secondary': {
            'tsx_daily_open_to_close': {'window': [DAILY_START, END], 'counts': d_counts, **sec_a},
            'point_in_time_sp500_daily': {'window': [DAILY_START, END], 'counts': us_counts,
                                          'names_with_bars': sum(1 for t, x in us.items()
                                                                 if x.get('daily') and t != US_MARKET),
                                          **sec_b}},
        'descriptive': {
            'by_length': {'2 or more': split(rows, lambda r: abs(r['run']) >= 2),
                          '3 or more': split(rows, lambda r: abs(r['run']) >= 3),
                          '4 or more': split(rows, lambda r: abs(r['run']) >= 4),
                          '5 or more': split(rows, lambda r: abs(r['run']) >= 5),
                          'exactly 3': split(rows, lambda r: abs(r['run']) == 3)},
            'by_side': {'LONG after an up run': split(three, lambda r: r['run'] > 0),
                        'SHORT after a down run': split(three, lambda r: r['run'] < 0)},
            'by_size_in_normal_days': {
                'under 1': split(three, lambda r: r['move3_atr'] is not None and r['move3_atr'] < 1),
                '1 to 2': split(three, lambda r: r['move3_atr'] is not None and 1 <= r['move3_atr'] < 2),
                '2 or more': split(three, lambda r: r['move3_atr'] is not None and r['move3_atr'] >= 2)},
            'raw_not_against_xiu': stat([(r['session'], r['raw']) for t, r in three]),
            'open_to_0945_against_xiu': stat([(r['session'], r['pre']) for t, r in three]),
            'open_to_close_against_xiu': stat([(r['session'], r['oc']) for t, r in three]),
            'daily_by_year_tsx': {y: split([(t, r) for t, r in d_rows if abs(r['run']) >= RUN
                                            and r['session'][:4] == y], lambda r: True)
                                  for y in sorted({r['session'][:4] for _, r in d_rows})},
            'sp500_by_side': {'LONG after an up run': split([(t, r) for t, r in us_rows if r['run'] >= RUN],
                                                            lambda r: True),
                              'SHORT after a down run': split([(t, r) for t, r in us_rows if r['run'] <= -RUN],
                                                              lambda r: True)}}}
    if with_live:
        try:
            out['live_record'] = live()
        except Exception as exc:                       # descriptive only; named, never silent
            out['live_record'] = {'error': '%s: %s' % (type(exc).__name__, str(exc)[:120])}
    OUT.write_text(json.dumps(out, indent=1) + '\n')
    return out


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    p.add_argument('--no-live', action='store_true', help='skip the live record split (no network)')
    a = p.parse_args(argv)
    got = run(with_live=not a.no_live)
    shown = {k: v for k, v in got.items() if k not in ('live_record',)}
    print(json.dumps(shown, indent=1))
    if 'live_record' in got:
        print(json.dumps({k: v for k, v in got['live_record'].items() if k != 'picks'}, indent=1))
    return 0


if __name__ == '__main__':
    sys.exit(main())
