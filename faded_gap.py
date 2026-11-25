#!/usr/bin/env python3
"""Day-155 (PREREGISTER_day155_faded_gap.md, council lab item 17): the faded
gap, Claude's short thesis.

On the prior session d-1, with ATR the mean of the 14 true ranges ending at d-1
(each against its own prior close, dividend-adjusted daily bars, the brief's
arithmetic in daily_technicals.context) and

    gap_atr = (open(d-1) - close(d-2)) / ATR,

a faded up-gap (gap_atr >= 1, close(d-1) < open(d-1)) is a SHORT on d and a
faded down-gap (gap_atr <= -1, close(d-1) > open(d-1)) a LONG. The name's bars
d-15 .. d-1 must be the market's consecutive sessions. On d

    y = side x (the name's 09:45 -> close - XIU's 09:45 -> close), in %.

  primary    the 150 names, FMP 15-minute session prices 2024-01-02 -> 2026-10-29
  secondary  (a) the same names, daily open -> close against XIU's, 2016-01-04 ->
             (b) the point-in-time S&P 500, daily open -> close against SPY's

The setup is the registration's own counting code (prior-session prices only),
moved here unchanged. Bars are read from day-143's cache
(.rb-state/report_day_cache), downloaded again by `python report_day.py --fetch`
(amendment 1). The live record's prior sessions come from FMP daily bars
fetched at the run. No model.

    python faded_gap.py        # writes data/faded_gap_day155.json
"""
from __future__ import annotations

import argparse
import concurrent.futures as cf
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
OUT = ROOT/'data'/'faded_gap_day155.json'
START, END = '2024-01-02', '2026-10-29'
DAILY_START = '2016-01-04'
LIVE_FIRST = '2026-10-14'
MARKET, US_MARKET = 'XIU.TO', 'SPY'
ATR_N, GAP_ATR, BIG_GAP = 14, 1.0, 2.0
AWAY = 5                                  # the placebo session is at least 5 sessions away
COST_PER_PICK = 0.13                      # the measured round trip, day-132b
PLANTED, DRAWS, SEED = 0.30, 2000, 155
BAR_T, BAR_P = 3.0, 0.01
REGISTERED = {'primary_events': 1209, 'primary_short': 512, 'primary_long': 697,
              'primary_sessions': 357, 'primary_names': 150, 'primary_gap_2atr_or_more': 159,
              'tsx_daily_events': 4218, 'tsx_daily_sessions': 1599, 'tsx_daily_short': 1972,
              'sp500_events': 14303, 'sp500_sessions': 2360, 'sp500_short': 6805, 'sp500_names': 661}


# ── the setup: prior-session prices only ─────────────────────────────────────

def next_session(daily):
    """{session: the next session} on a market's daily calendar."""
    ds = sorted(r[0] for r in daily)
    return {ds[i]: ds[i + 1] for i in range(len(ds) - 1)}


def prior_sessions(daily, nx, lo, hi):
    """[(d, gap_atr, open1, close1, close2)], one per session d in [lo, hi] the
    name's bars can describe: d-1 is a row of `daily` ([[date, o, h, l, c, vol]]
    ascending), d the market's next session after it (`nx`), and the 15 rows
    ending at d-1 the market's consecutive sessions. The registration's count,
    unchanged."""
    rows = [r for r in daily if all(x and x > 0 for x in r[1:5])]
    out = []
    for i in range(ATR_N + 1, len(rows)):
        d1, d2 = rows[i], rows[i - 1]
        if nx.get(d2[0]) != d1[0]:
            continue
        win = rows[i - ATR_N:i + 1]
        if any(nx.get(win[k][0]) != win[k + 1][0] for k in range(ATR_N)):
            continue
        tr = [max(r[2] - r[3], abs(r[2] - p[4]), abs(r[3] - p[4])) for p, r in zip(win[:-1], win[1:])]
        atr = float(np.mean(tr))
        if atr <= 0:
            continue
        d = nx.get(d1[0])
        if d is None or not (lo <= d <= hi):
            continue
        out.append((d, (d1[1] - d2[4]) / atr, d1[1], d1[4], d2[4]))
    return out


def faded(rows):
    """[(d, side, gap_atr, full_reversal)]: SHORT after a faded up-gap, LONG
    after a faded down-gap. A full reversal closed d-1 back beyond d-2's close."""
    out = []
    for d, g, o1, c1, c2 in rows:
        if g >= GAP_ATR and c1 < o1:
            out.append((d, 'SHORT', g, c1 < c2))
        elif g <= -GAP_ATR and c1 > o1:
            out.append((d, 'LONG', g, c1 > c2))
    return out


def held(rows):
    """Descriptive: the gap held (the close at or beyond the open in the gap's
    direction), followed: LONG after a held up-gap, SHORT after a held down-gap."""
    out = []
    for d, g, o1, c1, c2 in rows:
        if g >= GAP_ATR and c1 >= o1:
            out.append((d, 'LONG', g, False))
        elif g <= -GAP_ATR and c1 <= o1:
            out.append((d, 'SHORT', g, False))
    return out


def sign(side):
    return 1 if side == 'LONG' else -1


# ── the panels ───────────────────────────────────────────────────────────────

def load(kind):
    d = CACHE/kind
    if not d.exists():
        raise SystemExit('no cache: run `python report_day.py --fetch` first')
    return {f.stem: json.loads(f.read_text()) for f in d.glob('*.json')}


def intraday_events(tsx, names, kind=faded):
    """The primary: each setup scored 09:45 -> close against XIU on d, with the
    two other windows of d beside it (open -> 09:45, before the entry; 09:45 ->
    noon). A setup whose d has no bar for the name or for XIU is not an event,
    as at registration."""
    mk = tsx[MARKET]
    nx, xb = next_session(mk['daily']), mk['bars']
    ev = []
    for t in names:
        bars = tsx[t]['bars']
        for d, side, g, full in kind(prior_sessions(tsx[t]['daily'], nx, START, END)):
            b, m = bars.get(d), xb.get(d)
            if not (m and b and b[1] and b[3]):
                continue
            s = sign(side)
            ev.append({'ticker': t, 'session': d, 'side': side, 'gap_atr': g, 'full_reversal': full,
                       'y': s * (100 * (b[3] / b[1] - 1) - 100 * (m[3] / m[1] - 1)),
                       'pre': s * (100 * (b[1] / b[0] - 1) - 100 * (m[1] / m[0] - 1)),
                       'noon': s * (100 * (b[2] / b[1] - 1) - 100 * (m[2] / m[1] - 1))})
    return sorted(ev, key=lambda e: (e['session'], e['ticker']))


def daily_events(data, names, market_sym, lo=DAILY_START, hi=END, member=None):
    """A secondary panel: (scored events, counted setups). Counted is the
    registration's count (no price on d read); an event is scored open -> close
    on d against the market's open -> close when the name has d's bar."""
    mk = data[market_sym]['daily']
    nx, mrow = next_session(mk), {r[0]: r for r in mk}
    ev, counted = [], []
    for t in names:
        rows = data[t].get('daily') or []
        if not rows:
            continue
        own = {r[0]: r for r in rows}
        for d, side, g, full in faded(prior_sessions(rows, nx, lo, hi)):
            if member is not None and not member(d, t):
                continue
            counted.append((t, d, side))
            r, m = own.get(d), mrow.get(d)
            if not (r and m):
                continue
            ev.append({'ticker': t, 'session': d, 'side': side, 'gap_atr': g, 'full_reversal': full,
                       'y': sign(side) * (100 * (r[4] / r[1] - 1) - 100 * (m[4] / m[1] - 1))})
    return sorted(ev, key=lambda e: (e['session'], e['ticker'])), counted


def outcomes(tsx, names):
    """({ticker: (positions, values)}, {session: position}): each name's 09:45 ->
    close against XIU on every session of the window it has a bar, at its
    position on XIU's 15-minute calendar. The placebo draws from these."""
    xb = tsx[MARKET]['bars']
    cal = sorted(d for d in xb if START <= d <= END)
    pos = {d: i for i, d in enumerate(cal)}
    out = {}
    for t in names:
        bars = tsx[t]['bars']
        ps, vs = [], []
        for d in cal:
            b, m = bars.get(d), xb[d]
            if b and b[1] and b[3]:
                ps.append(pos[d])
                vs.append(100 * (b[3] / b[1] - 1) - 100 * (m[3] / m[1] - 1))
        out[t] = (np.asarray(ps, int), np.asarray(vs, float))
    return out, pos


# ── the statistics ───────────────────────────────────────────────────────────

def stat(evs, key='y'):
    pairs = [(e['session'], e[key]) for e in evs if e.get(key) is not None]
    base = {'n': len(pairs), 'sessions': len({s for s, _ in pairs})}
    if len(pairs) < 2:
        return {**base, 'mean_pct': None, 'se': None, 't': None, 'hit': None}
    mean, se, t = clustered(pairs)
    return {**base, 'mean_pct': round(mean, 4), 'se': round(se, 4) if se else None,
            't': round(t, 2) if t is not None else None,
            'hit': round(sum(v > 0 for _, v in pairs) / len(pairs), 3)}


def blocks(evs):
    """Four blocks of equal numbers of events in date order (the last takes the
    remainder): each block's mean."""
    ys = [e['y'] for e in sorted(evs, key=lambda e: (e['session'], e['ticker']))]
    q = len(ys) // 4
    parts = [ys[i * q:(i + 1) * q] if i < 3 else ys[3 * q:] for i in range(4)]
    return [float(np.mean(p)) if p else None for p in parts]


def draw_away(ps, p, rng, draws, away=AWAY):
    """`draws` indices into `ps` (a name's sorted session positions), uniform
    over the positions at least `away` sessions from p; None when there are none."""
    a = int(np.searchsorted(ps, p - away + 1, 'left'))
    b = int(np.searchsorted(ps, p + away - 1, 'right'))
    m = len(ps) - (b - a)
    if m <= 0:
        return None
    u = rng.integers(0, m, draws)
    return np.where(u >= a, u + (b - a), u)


def placebo(evs, outs, pos, draws=DRAWS, seed=SEED):
    """Each event moves to a random session of the same name at least AWAY
    sessions away, keeping its side; the draws' means, and how many events had
    no such session."""
    rng = np.random.default_rng(seed)
    total, used, skipped = np.zeros(draws), 0, 0
    for e in sorted(evs, key=lambda e: (e['session'], e['ticker'])):
        ps, vs = outs[e['ticker']]
        u = draw_away(ps, pos[e['session']], rng, draws)
        if u is None:
            skipped += 1
            continue
        total += sign(e['side']) * vs[u]
        used += 1
    return (total / used if used else np.array([])), skipped


def verdict(evs, draws, secondary_means):
    pairs = [(e['session'], e['y']) for e in evs]
    mean, se, t = clustered(pairs) if len(pairs) >= 2 else (None, None, None)
    qs = blocks(evs)
    have = draws.size and mean is not None
    p_up = float(np.mean(draws >= mean)) if have else None
    p_down = float(np.mean(draws <= mean)) if have else None
    planted_t = PLANTED / se if se else None          # 0.30 / se, never (mean + 0.30) / se
    follows = {'mean_positive_t_at_least_3': mean is not None and mean > 0 and t is not None and t >= BAR_T,
               'all_four_blocks_positive': all(x is not None and x > 0 for x in qs),
               'placebo_p_under_0.01': p_up is not None and p_up < BAR_P,
               'mean_above_the_0.13_cost': mean is not None and mean - COST_PER_PICK > 0,
               'both_secondary_means_positive': all(m is not None and m > 0 for m in secondary_means)}
    reverses = {'mean_negative_t_at_most_minus_3': mean is not None and mean < 0 and t is not None and t <= -BAR_T,
                'all_four_blocks_negative': all(x is not None and x < 0 for x in qs),
                'placebo_p_under_0.01': p_down is not None and p_down < BAR_P,
                'both_secondary_means_negative': all(m is not None and m < 0 for m in secondary_means)}
    detected = planted_t is not None and planted_t >= BAR_T
    if not detected:
        name = 'UNDERPOWERED'
    else:
        name = 'FOLLOWS' if all(follows.values()) else 'REVERSES' if all(reverses.values()) else 'NULL'
    r = lambda x, k=4: None if x is None else round(float(x), k)
    return {'primary': stat(evs), 'block_means_pct': [r(x) for x in qs],
            'cost_per_pick_pct': COST_PER_PICK,
            'placebo': {'draws': int(draws.size), 'seed': SEED, 'away_sessions': AWAY,
                        'p_one_sided_follows': p_up, 'p_one_sided_reverses': p_down,
                        'mean_of_draws_pct': r(draws.mean()) if draws.size else None,
                        'sd_of_draws_pct': r(draws.std()) if draws.size else None},
            'control': {'planted_pct': PLANTED, 't_planted': r(planted_t, 2), 'detected': detected,
                        'mde80_pct': r(2.8 * se) if se else None},
            'bar': {'follows': follows, 'reverses': reverses},
            'verdict': name, 'rejection_70': name not in ('FOLLOWS', 'REVERSES')}


def legs(evs):
    return {'SHORT after a faded up-gap': stat([e for e in evs if e['side'] == 'SHORT']),
            'LONG after a faded down-gap': stat([e for e in evs if e['side'] == 'LONG'])}


# ── the live record (descriptive; FMP daily bars fetched at the run) ─────────

def live(fetch=None, path=PICKS, first=LIVE_FIRST, today=None):
    """Claude's scored council nominations since `first`: those whose side
    follows a faded gap on the prior session, against the rest. A count only."""
    with open(path, newline='') as f:
        rows = [r for r in csv.DictReader(f) if r['model'] == 'claude' and r['kind'] == 'nominated'
                and r['session'] >= first and r.get('r_pct') not in (None, '')]
    today = today or dt.date.today().isoformat()
    if fetch is None:
        import fmp_client as F
        import replay_weeks as W
        from replay_drift import Fetch
        F.load_key(str(ROOT/'.rb-state'))
        fetch = W.robust(Fetch(None))
    import report_day as RD
    lo = (dt.date.fromisoformat(first) - dt.timedelta(days=50)).isoformat()

    def bars(t):
        got = fetch('historical-price-eod/dividend-adjusted', symbol=t, **{'from': lo, 'to': today})
        return None if got is None else RD._eod(got, prefix='adj')

    mk = bars(MARKET)
    if not mk:
        return {'error': 'no %s daily bars' % MARKET}
    nx = next_session(mk)
    tickers = sorted({r['ticker'] for r in rows})
    with cf.ThreadPoolExecutor(8) as pool:
        got = dict(zip(tickers, pool.map(bars, tickers)))
    read = {}
    for t, b in got.items():
        for d, g, o1, c1, c2 in prior_sessions(b or [], nx, first, today):
            read[(t, d)] = faded([(d, g, o1, c1, c2)])
    groups, unread = {'follows': [], 'against': [], 'no_faded_gap': []}, 0
    for r in rows:
        k = (r['ticker'], r['session'])
        if k not in read:
            unread += 1
            continue
        setup = read[k]
        if not setup:
            groups['no_faded_gap'].append(r)
        elif setup[0][1] == r['side']:
            groups['follows'].append(r)
        else:
            groups['against'].append(r)

    def summ(rs):
        ys = [float(r['r_pct']) for r in rs]
        return {'n': len(ys), 'right': sum(y > 0 for y in ys),
                'mean_r_pct': round(float(np.mean(ys)), 3) if ys else None}

    rest = groups['against'] + groups['no_faded_gap']
    return {'window': [first, today], 'nominations_scored': len(rows), 'names': len(tickers),
            'names_without_bars': sorted(t for t, b in got.items() if not b),
            'prior_session_unread': unread,
            'follows_a_faded_gap': summ(groups['follows']),
            'the_other_nominations': summ(rest),
            'against_a_faded_gap': summ(groups['against']),
            'follows_detail': ['%s %s %s %+.2f%%' % (r['session'], r['side'], r['ticker'], float(r['r_pct']))
                               for r in groups['follows']],
            'fetch_failures': getattr(fetch, 'failures', None),
            'note': 'far too few to judge; a count, never a verdict'}


# ── the run ──────────────────────────────────────────────────────────────────

def download(tsx, us):
    glitches = json.loads((CACHE/'sp500_membership.json').read_text()).get('glitches')
    return {'tsx_files': len(tsx), 'tsx_failed_calls': sum(x.get('failed_calls', 0) for x in tsx.values()),
            'tsx_capped_calls': sum(x.get('capped_calls', 0) for x in tsx.values()),
            'us_files': len(us), 'us_failed_calls': sum(x.get('failed_calls', 0) for x in us.values()),
            'us_without_bars': sum(1 for x in us.values() if not x.get('daily')),
            'membership_glitches': glitches}


def counts(ev, cal_sessions, counted_a, counted_b):
    now = {'primary_events': len(ev), 'primary_short': sum(e['side'] == 'SHORT' for e in ev),
           'primary_long': sum(e['side'] == 'LONG' for e in ev),
           'primary_sessions': len({e['session'] for e in ev}), 'primary_names': len({e['ticker'] for e in ev}),
           'primary_gap_2atr_or_more': sum(abs(e['gap_atr']) >= BIG_GAP for e in ev),
           'tsx_daily_events': len(counted_a), 'tsx_daily_sessions': len({d for _, d, _ in counted_a}),
           'tsx_daily_short': sum(s == 'SHORT' for _, _, s in counted_a),
           'sp500_events': len(counted_b), 'sp500_sessions': len({d for _, d, _ in counted_b}),
           'sp500_short': sum(s == 'SHORT' for _, _, s in counted_b),
           'sp500_names': len({t for t, _, _ in counted_b})}
    return {'market_sessions_in_window': cal_sessions,
            **{k: {'now': now[k], 'registered': REGISTERED[k]} for k in REGISTERED}}


def run(live_fetch=None):
    names = json.loads(NAMES.read_text())['names']
    tsx = load('tsx')
    missing = [t for t in [MARKET] + names if t not in tsx]
    if missing:
        raise SystemExit('the cache is incomplete: %d names missing (%s)'
                         % (len(missing), ', '.join(missing[:5])))
    us = load('us')
    if US_MARKET not in us:
        raise SystemExit('the cache is incomplete: no %s' % US_MARKET)
    ev = intraday_events(tsx, names)
    outs, pos = outcomes(tsx, names)
    draws, skipped = placebo(ev, outs, pos)

    ev_a, counted_a = daily_events(tsx, names, MARKET)
    intervals = {t: [tuple(x) for x in iv] for t, iv in
                 json.loads((CACHE/'sp500_membership.json').read_text())['intervals'].items()}
    member = lambda d, t: any(a <= d < b for a, b in intervals.get(t, ()))
    us_names = sorted(t for t in us if t != US_MARKET and us[t].get('daily'))
    ev_b, counted_b = daily_events(us, us_names, US_MARKET, member=member)
    sec_a, sec_b = stat(ev_a), stat(ev_b)
    v = verdict(ev, draws, [sec_a['mean_pct'], sec_b['mean_pct']])

    held_ev = intraday_events(tsx, names, kind=held)
    out = {
        'registered': 'PREREGISTER_day155_faded_gap.md', 'run_on': dt.date.today().isoformat(),
        'window': [START, END], 'names': len(names), 'seed': SEED,
        'download': download(tsx, us),
        'counts': counts(ev, len(pos), counted_a, counted_b),
        'placebo_events_without_a_session': skipped,
        **v,
        'secondary': {
            'tsx_daily_open_to_close': {'window': [DAILY_START, END], 'counted': len(counted_a),
                                        'scored': len(ev_a), **sec_a, 'legs': legs(ev_a)},
            'point_in_time_sp500_daily': {'window': [DAILY_START, END], 'counted': len(counted_b),
                                          'scored': len(ev_b), **sec_b, 'legs': legs(ev_b)}},
        'descriptive': {
            'legs': legs(ev),
            'gap_2atr_or_more': stat([e for e in ev if abs(e['gap_atr']) >= BIG_GAP]),
            'full_reversal': stat([e for e in ev if e['full_reversal']]),
            'not_a_full_reversal': stat([e for e in ev if not e['full_reversal']]),
            'held_gap_followed': {**stat(held_ev), 'legs': {
                'LONG after a held up-gap': stat([e for e in held_ev if e['side'] == 'LONG']),
                'SHORT after a held down-gap': stat([e for e in held_ev if e['side'] == 'SHORT'])}},
            'open_to_0945_before_the_entry': stat(ev, key='pre'),
            '0945_to_noon': stat(ev, key='noon'),
            'by_year': {y: stat([e for e in ev if e['session'][:4] == y])
                        for y in sorted({e['session'][:4] for e in ev})},
            'secondary_tsx_by_year': {y: stat([e for e in ev_a if e['session'][:4] == y])
                                      for y in sorted({e['session'][:4] for e in ev_a})}},
    }
    try:
        out['live_record'] = live(live_fetch)
    except Exception as exc:                       # descriptive only; named, never silent
        out['live_record'] = {'error': '%s: %s' % (type(exc).__name__, str(exc)[:120])}
    OUT.write_text(json.dumps(out, indent=1) + '\n')
    return out


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    p.parse_args(argv)
    got = run()
    shown = {k: got[k] for k in ('verdict', 'counts', 'download', 'primary', 'block_means_pct',
                                 'placebo', 'control', 'bar')}
    print(json.dumps(shown, indent=1))
    print(json.dumps({'secondary_means': {k: v['mean_pct'] for k, v in got['secondary'].items()}}))
    print(json.dumps({k: v for k, v in got['live_record'].items() if k != 'follows_detail'}, indent=1))
    return 0


if __name__ == '__main__':
    sys.exit(main())
