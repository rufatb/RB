#!/usr/bin/env python3
"""The day-132 registered test (PREREGISTER_day132_chasing.md).

Does a move of at least one ATR carry past 09:45 the next session, and how
much do the live picks chase such moves?

    python replay_chasing.py [--cache DIR]      writes data/replay_day132_chasing.json

FMP daily and 15-minute bars, 2024-01-02 → 2026-10-13, for the 2026-10-14
pool's TSX names and XIU.TO. Each name's responses are reduced and cached under
--cache, so an interrupted run resumes. Research only: nothing here is read by
the morning.
"""
from __future__ import annotations

import argparse
import calendar
import concurrent.futures as cf
import csv
import datetime as dt
import json
import math
import sys
from pathlib import Path

import numpy as np

import fmp_client as F
from daily_technicals import ATR_WINDOW
from replay_drift import Fetch
from replay_fmp_analyst import clustered, pool_tickers

ROOT = Path(__file__).resolve().parent
START, END, EOD_FROM = '2024-01-02', '2026-10-13', '2023-10-01'
LIVE_FROM, LIVE_TO = '2026-09-17', '2026-10-14'
OUT = ROOT / 'data' / 'replay_day132_chasing.json'
PICKS = ROOT / 'data' / 'model_picks.csv'
MARKET = 'XIU.TO'
THRESHOLD, PLANTED, COST, DRAWS, SEED, AWAY = 1.0, 0.10, 0.10, 2000, 132, 5
# 15-minute bars are stamped at their start: the 09:30 bar opens the session and
# closes at 09:45; the 11:45 bar closes at noon; the 15:45 bar closes at 16:00.
B_OPEN, B_NOON, B_CLOSE = '09:30:00', '11:45:00', '15:45:00'
CAP_BARS = 800                    # a month is ~600 bars; at the cap FMP truncated
CHOSEN_KINDS = {'selected', 'nominated', 'forced', 'pick', 'final'}


def months(a=START, b=END):
    """[(first day, last day)] per calendar month, clipped to [a, b]."""
    d, end, out = dt.date.fromisoformat(a).replace(day=1), dt.date.fromisoformat(b), []
    while d <= end:
        last = d.replace(day=calendar.monthrange(d.year, d.month)[1])
        out.append((max(d, dt.date.fromisoformat(a)).isoformat(), min(last, end).isoformat()))
        d = last + dt.timedelta(days=1)
    return out


def reduce_bars(rows):
    """{date: [open, p0945, noon, close]} from FMP 15-minute rows; a day missing
    any of the three bars is left out."""
    by = {}
    for b in rows or []:
        d, t = b['date'].split(' ')
        by.setdefault(d, {})[t] = b
    out = {}
    for d, bs in by.items():
        if all(k in bs for k in (B_OPEN, B_NOON, B_CLOSE)):
            vals = [bs[B_OPEN]['open'], bs[B_OPEN]['close'], bs[B_NOON]['close'], bs[B_CLOSE]['close']]
            if all(isinstance(v, (int, float)) and v > 0 for v in vals):
                out[d] = [float(v) for v in vals]
    return out


def reduce_eod(rows):
    """[[date, open, high, low, close]] ascending; rows without all four prices
    are dropped."""
    out = []
    for r in rows or []:
        v = [r.get(k) for k in ('open', 'high', 'low', 'close')]
        if all(isinstance(x, (int, float)) and x > 0 for x in v):
            out.append([r['date']] + [float(x) for x in v])
    return sorted(out)


def collect(ticker, fetch, cache=None):
    """One name's reduced data: daily bars, 15-minute session prices, report
    dates and how many calls failed or hit the bar cap."""
    f = Path(cache) / (ticker + '.json') if cache else None
    if f and f.exists():
        return json.loads(f.read_text())
    eod = reduce_eod(fetch('historical-price-eod/full', symbol=ticker, **{'from': EOD_FROM, 'to': END}))
    bars, failed, capped = {}, 0, 0
    for a, b in months():
        rows = fetch('historical-chart/15min', symbol=ticker, **{'from': a, 'to': b})
        if rows is None:
            failed += 1
            continue
        if len(rows) >= CAP_BARS:
            capped += 1
        bars.update(reduce_bars(rows))
    reports = []
    if ticker != MARKET:
        reports = sorted({r['date'] for r in fetch('earnings', symbol=ticker) or []
                          if r.get('epsActual') is not None and r.get('date')})
    out = {'ticker': ticker, 'eod': eod, 'bars': bars, 'reports': reports,
           'failed_calls': failed, 'capped_calls': capped}
    if f:
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(json.dumps(out))
    return out


def move_atr(eod, i):
    """daily_technicals.context's move_atr for the session at index i: the move
    of i over the mean true range of the ATR_WINDOW sessions ending at i."""
    if i < ATR_WINDOW or i >= len(eod):
        return None
    trs = []
    for j in range(i - ATR_WINDOW + 1, i + 1):
        h, l, pc = eod[j][2], eod[j][3], eod[j - 1][4]
        trs.append(max(h - l, abs(h - pc), abs(l - pc)))
    atr = sum(trs) / len(trs)
    return (eod[i][4] - eod[i - 1][4]) / atr if atr > 0 else None


def sign(x):
    return 1 if x > 0 else -1 if x < 0 else 0


def name_rows(name, market):
    """Every usable session D of one name: the prior session's move_atr (m), the
    same move against XIU in ATR units (m_x), and D's windows against XIU, in %."""
    eod, bars = name['eod'], name['bars']
    pos = {r[0]: i for i, r in enumerate(eod)}
    mpos = {r[0]: i for i, r in enumerate(market['eod'])}
    reports = name.get('reports') or []
    out, skipped = [], {'no_daily_bar': 0, 'short_history': 0, 'no_market': 0}
    for d in sorted(bars):
        if not (START <= d <= END):
            continue
        i = pos.get(d)
        if i is None:
            skipped['no_daily_bar'] += 1
            continue
        if i < ATR_WINDOW + 2:
            skipped['short_history'] += 1
            continue
        k = mpos.get(d)
        mb = market['bars'].get(d)
        if k is None or k < 2 or mb is None or market['eod'][k - 1][0] != eod[i - 1][0]:
            skipped['no_market'] += 1
            continue
        m = move_atr(eod, i - 1)
        if m is None:
            skipped['short_history'] += 1
            continue
        prev, prev2 = eod[i - 1][4], eod[i - 2][4]
        atr_frac = (prev - prev2) / m / prev2 if m else None
        mret = market['eod'][k - 1][4] / market['eod'][k - 2][4] - 1
        m_x = m - mret / atr_frac if atr_frac else None
        o, p945, noon, close = bars[d]
        xo, x945, xnoon, xclose = mb
        xprev = market['eod'][k - 1][4]
        hold = None
        if i + 4 < len(eod) and k + 4 < len(market['eod']) and market['eod'][k + 4][0] == eod[i + 4][0]:
            hold = 100 * ((eod[i + 4][4] / p945 - 1) - (market['eod'][k + 4][4] / x945 - 1))
        d1, d2 = eod[i - 1][0], eod[i - 2][0]
        out.append({
            'ticker': name['ticker'], 'session': d, 'm': m, 'm_x': m_x,
            'gap': 100 * ((o / prev - 1) - (xo / xprev - 1)),
            'early': 100 * ((p945 / o - 1) - (x945 / xo - 1)),
            'noon': 100 * ((noon / p945 - 1) - (xnoon / x945 - 1)),
            'main': 100 * ((close / p945 - 1) - (xclose / x945 - 1)),
            'hold5': hold,
            'earnings': any(d2 <= r <= d1 for r in reports)})
    return out, skipped


def stat(pairs):
    """{'n', 'mean_pct', 'se', 't', 'hit'} for [(session, value)], clustered by session."""
    pairs = [(s, v) for s, v in pairs if v is not None]
    if len(pairs) < 2:
        return {'n': len(pairs), 'mean_pct': None, 'se': None, 't': None, 'hit': None}
    mean, se, t = clustered(pairs)
    return {'n': len(pairs), 'mean_pct': round(mean, 4), 'se': round(se, 4) if se else None,
            't': round(t, 2) if t is not None else None,
            'hit': round(sum(v > 0 for _, v in pairs) / len(pairs), 3)}


def signed(rows, key, by='m'):
    return [(r['session'], None if r[key] is None else sign(r[by]) * r[key]) for r in rows]


def placebo(events, by_name, draws=DRAWS, seed=SEED):
    """Each event's sign replaced by the sign of m on a random other session of
    the same name at least AWAY sessions away. Returns the draws' means."""
    rng = np.random.default_rng(seed)
    idx = {t: {r['session']: j for j, r in enumerate(rs)} for t, rs in by_name.items()}
    signs = {t: np.array([sign(r['m']) for r in rs]) for t, rs in by_name.items()}
    groups = {}
    for e in events:
        groups.setdefault(e['ticker'], []).append((idx[e['ticker']][e['session']], e['main']))
    means = np.zeros(draws)
    total = len(events)
    for t, items in groups.items():
        n = len(signs[t])
        if n <= 2 * AWAY:
            continue
        own = np.array([j for j, _ in items])
        val = np.array([v for _, v in items])
        pick = rng.integers(0, n, size=(draws, len(own)))
        bad = np.abs(pick - own) < AWAY
        while bad.any():
            pick[bad] = rng.integers(0, n, size=int(bad.sum()))
            bad = np.abs(pick - own) < AWAY
        means += (signs[t][pick] * val).sum(axis=1)
    return means / total


def blocks(events, key='y'):
    ordered = sorted(events, key=lambda e: (e['session'], e['ticker']))
    q = len(ordered) // 4
    parts = [ordered[i * q:(i + 1) * q] if i < 3 else ordered[3 * q:] for i in range(4)]
    return [round(float(np.mean([e[key] for e in p])), 4) if p else None for p in parts]


def verdict(main, qmeans, p_val, planted_t):
    m, t = main['mean_pct'], main['t'] or 0
    cont = {'mean_positive_t_ge_3': bool(m is not None and m > 0 and t >= 3),
            'all_four_blocks_positive': all(x is not None and x > 0 for x in qmeans),
            'placebo_p_below_0_05': p_val is not None and p_val < 0.05,
            'net_of_0_10_positive': bool(m is not None and m - COST > 0)}
    rev = {'mean_negative_t_le_minus_3': bool(m is not None and m < 0 and t <= -3),
           'all_four_blocks_negative': all(x is not None and x < 0 for x in qmeans),
           'placebo_p_below_0_05': p_val is not None and p_val < 0.05}
    powered = bool(planted_t and planted_t >= 3)
    name = ('CONTINUATION' if all(cont.values()) else 'REVERSAL' if all(rev.values())
            else 'NULL' if powered else 'UNDERPOWERED')
    return name, {'continuation': cont, 'reversal': rev, 'control_detects_planted_0_10': powered}


def summarize(rows):
    events = [dict(r, y=sign(r['m']) * r['main']) for r in rows if abs(r['m']) >= THRESHOLD]
    main = stat([(e['session'], e['y']) for e in events])
    qmeans = blocks(events)
    by_name = {}
    for r in sorted(rows, key=lambda r: (r['ticker'], r['session'])):
        by_name.setdefault(r['ticker'], []).append(r)
    draws = placebo(events, by_name) if events else np.array([])
    obs = main['mean_pct']
    p_val = (float(np.mean(np.abs(draws) >= abs(obs))) if draws.size and obs is not None else None)
    se = main['se']
    planted_t = round(PLANTED / se, 2) if se else None
    name, checks = verdict(main, qmeans, p_val, planted_t)
    up = [e for e in events if e['m'] > 0]
    down = [e for e in events if e['m'] < 0]
    idio = [r for r in rows if r['m_x'] is not None and abs(r['m_x']) >= THRESHOLD]
    return {
        'primary': main, 'block_means_pct': qmeans,
        'placebo': {'draws': int(draws.size), 'mean_of_draws_pct': round(float(draws.mean()), 4) if draws.size else None,
                    'sd_of_draws_pct': round(float(draws.std()), 4) if draws.size else None, 'p_two_sided': p_val},
        'control': {'planted_pct': PLANTED, 't_planted': planted_t,
                    'mde80_pct': round(2.8 * se, 3) if se else None},
        'net_of_cost_pct': None if obs is None else round(obs - COST, 4),
        'checks': checks, 'verdict': name,
        'descriptive': {
            'windows_signed_by_prior_move': {
                'gap_close_to_open': stat(signed(events, 'gap')),
                'open_to_0945': stat(signed(events, 'early')),
                '0945_to_noon': stat(signed(events, 'noon')),
                '0945_to_close': stat(signed(events, 'main')),
                'hold_0945_to_close_d4': stat(signed(events, 'hold5'))},
            'dose': {
                'abs_m_ge_2': stat(signed([e for e in events if abs(e['m']) >= 2], 'main')),
                'abs_m_1_to_2': stat(signed([e for e in events if abs(e['m']) < 2], 'main')),
                'abs_m_below_1': stat(signed([r for r in rows if abs(r['m']) < THRESHOLD], 'main'))},
            'side': {'up_move_long_chase': stat(signed(up, 'main')),
                     'down_move_short_chase': stat(signed(down, 'main'))},
            'idiosyncratic_abs_m_x_ge_1': stat(signed(idio, 'main', by='m_x')),
            'earnings': {'prior_session_was_a_report': stat(signed([e for e in events if e['earnings']], 'main')),
                         'no_report': stat(signed([e for e in events if not e['earnings']], 'main'))},
            'gap': {'opened_further_the_same_way': stat(signed([e for e in events if sign(e['gap']) == sign(e['m'])], 'main')),
                    'opened_against_it': stat(signed([e for e in events if sign(e['gap']) == -sign(e['m'])], 'main'))}},
        'counts': {'name_days': len(rows), 'events': len(events), 'sessions': len({r['session'] for r in rows}),
                   'event_sessions': len({e['session'] for e in events}), 'up_moves': len(up), 'down_moves': len(down)},
    }


def chases(side, m):
    return m is not None and abs(m) >= THRESHOLD and (m > 0) == (side == 'LONG')


def prior_move(name, session):
    """move_atr of the session before `session`, from the name's daily bars."""
    eod = name['eod']
    before = [i for i, r in enumerate(eod) if r[0] < session]
    return move_atr(eod, before[-1]) if before else None


def live(data, picks_path=PICKS, seed=SEED):
    """M1: the picks' chasing share against the pool's base rate; M2: chasing
    picks against the rest on the recorded r_pct."""
    with open(picks_path, newline='') as f:
        rows = [r for r in csv.DictReader(f) if LIVE_FROM <= r['session'] <= LIVE_TO]
    pool = [t for t in data if t != MARKET]
    picks, missing = [], 0
    for r in rows:
        if r['kind'] not in CHOSEN_KINDS and not (r['model'] == 'engine' and r['kind'] == 'board'):
            continue
        name = data.get(r['ticker'])
        m = prior_move(name, r['session']) if name else None
        if m is None:
            missing += 1
            continue
        picks.append({'session': r['session'], 'model': r['model'], 'kind': r['kind'], 'side': r['side'],
                      'ticker': r['ticker'], 'm': m, 'chase': chases(r['side'], m),
                      'r_pct': float(r['r_pct']) if r['r_pct'] not in ('', None) else None})
    sessions = sorted({p['session'] for p in picks})
    base = {}
    for s in sessions:
        ms = [prior_move(data[t], s) for t in pool]
        ms = [m for m in ms if m is not None]
        base[s] = (sum(abs(m) >= THRESHOLD for m in ms), 2 * len(ms))   # one side of each big mover chases

    def share(group, ss):
        n = sum(1 for p in group if p['session'] in ss)
        c = sum(1 for p in group if p['session'] in ss and p['chase'])
        bc = sum(base[s][0] * ss.count(s) for s in set(ss))
        bn = sum(base[s][1] * ss.count(s) for s in set(ss))
        return c, n, bc, bn

    def m1(group):
        ss = sorted({p['session'] for p in group})
        c, n, bc, bn = share(group, ss)
        if not n or not bn:
            return {'picks': n}
        rng = np.random.default_rng(seed)
        ratios = []
        for _ in range(DRAWS):
            draw = list(rng.choice(ss, size=len(ss), replace=True))
            c2 = sum(sum(1 for p in group if p['session'] == s and p['chase']) for s in draw)
            n2 = sum(sum(1 for p in group if p['session'] == s) for s in draw)
            b2 = sum(base[s][0] for s in draw) / max(1, sum(base[s][1] for s in draw))
            if n2 and b2:
                ratios.append((c2 / n2) / b2)
        lo, hi = (float(np.percentile(ratios, 2.5)), float(np.percentile(ratios, 97.5))) if ratios else (None, None)
        return {'picks': n, 'chasing': c, 'share': round(c / n, 3), 'base_share': round(bc / bn, 3),
                'ratio': round((c / n) / (bc / bn), 2),
                'ratio_ci95': [round(lo, 2), round(hi, 2)] if lo is not None else None,
                'sessions': len(ss)}

    llm = [p for p in picks if p['model'] != 'engine']
    groups = {
        'all_model_picks': llm,
        'top2_council': [p for p in llm if p['model'] == 'top2'],
        'desk_selections': [p for p in llm if p['kind'] == 'selected'],
        'nominations': [p for p in llm if p['kind'] == 'nominated'],
        'jev_forced': [p for p in llm if p['kind'] == 'forced'],
        'engine_board': [p for p in picks if p['model'] == 'engine']}
    scored = [p for p in llm if p['r_pct'] is not None]

    def m2(group):
        by = {}
        for p in group:
            by.setdefault(p['session'], {'c': [], 'r': []})['c' if p['chase'] else 'r'].append(p['r_pct'])
        diffs = [np.mean(v['c']) - np.mean(v['r']) for v in by.values() if v['c'] and v['r']]
        chase = [p['r_pct'] for p in group if p['chase']]
        rest = [p['r_pct'] for p in group if not p['chase']]
        out = {'chasing': {'n': len(chase), 'hit': round(sum(x > 0 for x in chase) / len(chase), 3) if chase else None,
                           'mean_pct': round(float(np.mean(chase)), 3) if chase else None},
               'rest': {'n': len(rest), 'hit': round(sum(x > 0 for x in rest) / len(rest), 3) if rest else None,
                        'mean_pct': round(float(np.mean(rest)), 3) if rest else None},
               'sessions_with_both': len(diffs)}
        if len(diffs) >= 2:
            mean, sd = float(np.mean(diffs)), float(np.std(diffs, ddof=1))
            se = sd / math.sqrt(len(diffs))
            out.update({'diff_pct': round(mean, 3), 'se': round(se, 3), 't': round(mean / se, 2) if se else None,
                        'mde80_pct': round(2.8 * se, 3)})
        return out

    return {'m1_selection': {k: m1(v) for k, v in groups.items()},
            'm2_outcomes': {'all_model_picks': m2(scored),
                            'top2_council': m2([p for p in scored if p['model'] == 'top2'])},
            'picks_without_a_prior_move': missing,
            'picks': picks}


def today(data, session=LIVE_TO, names=('SSRM.TO', 'CNQ.TO')):
    out = {}
    for t in names:
        m = prior_move(data[t], session) if t in data else None
        out[t] = {'move_atr_prior_session': None if m is None else round(m, 2)}
    return out


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    p.add_argument('--state-dir', default='.rb-state')
    p.add_argument('--cache', help='directory for reduced per-name FMP data, so a run can resume')
    p.add_argument('--out', default=str(OUT))
    a = p.parse_args(argv)
    F.load_key(a.state_dir)
    fetch = Fetch(None)
    tickers = pool_tickers(a.state_dir)
    with open(PICKS, newline='') as f:
        extra = sorted({r['ticker'] for r in csv.DictReader(f)
                        if LIVE_FROM <= r['session'] <= LIVE_TO and r['ticker'].endswith('.TO')} - set(tickers))
    names = [MARKET] + tickers + extra
    with cf.ThreadPoolExecutor(8) as pool:
        data = dict(zip(names, pool.map(lambda t: collect(t, fetch, a.cache), names)))
    market = data[MARKET]
    rows, skipped = [], {}
    for t in tickers:
        rs, sk = name_rows(data[t], market)
        rows.extend(rs)
        for k, v in sk.items():
            skipped[k] = skipped.get(k, 0) + v
    out = summarize(rows)
    out.update({'registered': 'PREREGISTER_day132_chasing.md', 'run_on': dt.date.today().isoformat(),
                'window': [START, END], 'names': len(tickers), 'skipped': skipped,
                'fetch_failures': fetch.failures,
                'failed_calls': sum(d['failed_calls'] for d in data.values()),
                'capped_calls': sum(d['capped_calls'] for d in data.values()),
                'live': live(data), 'today': today(data)})
    Path(a.out).write_text(json.dumps(out, indent=1, sort_keys=True, default=float) + '\n')
    brief = {k: v for k, v in out.items() if k != 'live'}
    brief['live'] = {k: v for k, v in out['live'].items() if k != 'picks'}
    print(json.dumps(brief, indent=1, sort_keys=True, default=float))
    return 0


if __name__ == '__main__':
    sys.exit(main())
