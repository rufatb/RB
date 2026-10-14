#!/usr/bin/env python3
"""Day-132c phase 3 (PREREGISTER_day132c_after_open.md): ask after the open.

    python replay_after_open.py --cache DIR [--control-only]
        writes data/replay_day132c_after_open.json

Arm A asks DeepSeek v4-pro the production nomination question before the open;
Arm B asks the same question with each name's first thirty minutes added
(`open30`). Bars and answers are cached under DIR, so a run resumes. Research
only: nothing here is read by the morning.
"""
from __future__ import annotations

import argparse
import concurrent.futures as cf
import copy
import datetime as dt
import glob
import json
import statistics as st
import sys
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np

import fmp_client as F
from replay_chasing import months, reduce_eod
from replay_drift import Fetch
from replay_fmp_analyst import clustered

ET = ZoneInfo('America/New_York')
ROOT = Path(__file__).resolve().parent
OUT = ROOT / 'data' / 'replay_day132c_after_open.json'
POOLS = ROOT / '.rb-state' / 'replay' / 'pools'
MARKET = 'XIU.TO'
FIRST, LAST = '2026-07-06', '2026-09-28'
BAR_FROM = '2026-06-01'
LOOKBACK, SEED, DRAWS, PLANTED = 20, 132, 2000, 0.5
B_OPEN, B_945, B_CLOSE = '09:30:00', '09:45:00', '15:45:00'

OLD_HEAD = 'The entry is 09:46 ET and the exit is 15:59 ET on the SAME day.'
NEW_HEAD = 'The entry is 10:01 ET and the exit is 15:59 ET on the SAME day.'
OLD_WINDOW = 'from 09:46 ET to 15:59 ET today'
NEW_WINDOW = 'from 10:01 ET to 15:59 ET today'
OLD_TIMING = ('- Everything supplied describes the PREVIOUS completed session or pre-open\n'
              '  levels, and the entry is 09:46 — AFTER the open. Say in the reason why it is\n'
              '  NOT already priced in, or do not rely on it.')
NEW_TIMING = ('- The rows describe the PREVIOUS completed session, EXCEPT `open30`, which is\n'
              "  TODAY's first thirty minutes (09:30 → 10:00 ET), measured before you answer.\n"
              '  The entry is 10:01 ET. Say in the reason why the move is not already priced\n'
              '  in, or do not rely on it.')
OPEN30_DOC = ("open30 (TODAY, 09:30 → 10:00 ET): gap_pct is today's open against the prior "
              "close; r30_pct the 10:00 price against the open; x30_pct is r30_pct minus "
              "XIU.TO's; rvol30 the 09:30–10:00 volume against its median over the prior 20 "
              "sessions; vwap30_gap_pct the 10:00 price against the 09:30–10:00 volume-weighted "
              "price; range30_pos where 10:00 sits in the first thirty minutes' range, 0 the low "
              "and 1 the high. macro.xiu_open30 carries XIU.TO's own gap_pct and r30_pct.")


# ---------------------------------------------------------------- prompts
def after_open_prompt(base):
    """Arm A's prompt with exactly the registered edits; refuses if a passage moved."""
    for old in (OLD_HEAD, OLD_WINDOW, OLD_TIMING):
        if base.count(old) != 1:
            raise ValueError('AFTER_OPEN_PROMPT_PASSAGE_MISSING')
    return (base.replace(OLD_HEAD, NEW_HEAD).replace(OLD_WINDOW, NEW_WINDOW)
            .replace(OLD_TIMING, NEW_TIMING) + '\n\n' + OPEN30_DOC)


# ---------------------------------------------------------------- bars
def reduce15(rows):
    """{date: {...}} with the 09:30, 09:45 and 15:45 bars of each session."""
    by = {}
    for b in rows or []:
        d, t = b['date'].split(' ')
        by.setdefault(d, {})[t] = b
    out = {}
    for d, bs in by.items():
        if not all(k in bs for k in (B_OPEN, B_945, B_CLOSE)):
            continue
        a, b, z = bs[B_OPEN], bs[B_945], bs[B_CLOSE]
        vals = [a.get('open'), a.get('close'), b.get('close'), z.get('close')]
        if not all(isinstance(v, (int, float)) and v > 0 for v in vals):
            continue
        vol = (a.get('volume') or 0) + (b.get('volume') or 0)
        typ = lambda x: (x['high'] + x['low'] + x['close']) / 3
        vwap = ((typ(a) * (a.get('volume') or 0) + typ(b) * (b.get('volume') or 0)) / vol) if vol else None
        out[d] = {'open': a['open'], 'p945': a['close'], 'p1000': b['close'], 'close': z['close'],
                  'high30': max(a['high'], b['high']), 'low30': min(a['low'], b['low']),
                  'vol30': vol, 'vwap30': vwap}
    return out


def collect(ticker, fetch, cache):
    f = Path(cache) / (ticker + '.json')
    if f.exists():
        return json.loads(f.read_text())
    bars, failed = {}, 0
    for a, b in months(BAR_FROM, LAST):
        rows = fetch('historical-chart/15min', symbol=ticker, **{'from': a, 'to': b})
        if rows is None:
            failed += 1
            continue
        bars.update(reduce15(rows))
    eod = reduce_eod(fetch('historical-price-eod/full', symbol=ticker, **{'from': '2026-05-01', 'to': LAST}))
    out = {'ticker': ticker, 'bars': bars, 'eod': eod, 'failed_calls': failed}
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(json.dumps(out))
    return out


def prior_close(name, session):
    before = [r for r in name['eod'] if r[0] < session]
    return before[-1][4] if before else None


def open30(name, market, session):
    """The registered fields for one name on one session, or None."""
    b, m = name['bars'].get(session), market['bars'].get(session)
    prev, mprev = prior_close(name, session), prior_close(market, session)
    if not b or not m or not prev or not mprev:
        return None
    past = sorted(d for d in name['bars'] if d < session)[-LOOKBACK:]
    vols = [name['bars'][d]['vol30'] for d in past if name['bars'][d]['vol30']]
    med = st.median(vols) if len(vols) >= 10 else None
    r30 = 100 * (b['p1000'] / b['open'] - 1)
    xr30 = 100 * (m['p1000'] / m['open'] - 1)
    span = b['high30'] - b['low30']
    return {'gap_pct': round(100 * (b['open'] / prev - 1), 2), 'r30_pct': round(r30, 2),
            'x30_pct': round(r30 - xr30, 2),
            'rvol30': round(b['vol30'] / med, 2) if med else None,
            'vwap30_gap_pct': round(100 * (b['p1000'] / b['vwap30'] - 1), 2) if b['vwap30'] else None,
            'range30_pos': round((b['p1000'] - b['low30']) / span, 2) if span > 0 else 0.5}


def xiu_open30(market, session):
    m, prev = market['bars'].get(session), prior_close(market, session)
    if not m or not prev:
        return None
    return {'gap_pct': round(100 * (m['open'] / prev - 1), 2),
            'r30_pct': round(100 * (m['p1000'] / m['open'] - 1), 2)}


def outcome(name, market, session, side, entry):
    """side × (name − XIU) from `entry` ('p945' or 'p1000') to the close, in %."""
    b, m = name['bars'].get(session), market['bars'].get(session)
    if not b or not m:
        return None
    r = (b['close'] / b[entry] - 1) - (m['close'] / m[entry] - 1)
    return 100 * r * (1 if side == 'LONG' else -1)


# ---------------------------------------------------------------- asking
def requests_for(pool, data, market, session):
    """(A request, B payload) over the names with complete bars that session."""
    import deepseek_opportunities as O
    cands = [c for c in pool['candidates'] if c['ticker'] in data and data[c['ticker']]['bars'].get(session)
             and open30(data[c['ticker']], market, session)]
    now = dt.datetime.combine(dt.date.fromisoformat(session), dt.time(9, 0), tzinfo=ET)
    req = O.build_request(cands, pool.get('macro') or None, now)
    if not req:
        return None, None
    b = copy.deepcopy(req['payload'])
    b['entry'] = '10:01 ET'
    b.setdefault('data_dates', {})['open30'] = '%s 09:30–10:00 ET' % session
    for row in b['candidates']:
        row['open30'] = open30(data[row['ticker']], market, session)
    b.setdefault('macro', {})['xiu_open30'] = xiu_open30(market, session)
    return req, b


def ask_arm(arm, session, system, payload, allowed, ask, cache):
    import nominations as N
    f = Path(cache) / 'answers' / ('%s_%s.json' % (arm, session))
    if f.exists():
        return json.loads(f.read_text())
    try:
        raw = ask(system, json.dumps(payload, sort_keys=True, allow_nan=False))
        longs, shorts, gaps = N.clean(raw, allowed, payload['candidates'])
        out = {'arm': arm, 'session': session, 'longs': longs, 'shorts': shorts, 'gaps': gaps}
    except Exception as exc:
        out = {'arm': arm, 'session': session, 'error': '%s: %s' % (type(exc).__name__, str(exc)[:120])}
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(json.dumps(out, default=str))
    return out


# ---------------------------------------------------------------- control
def control_payload():
    """Twelve names with the SAME pre-open rows; the plant is only in open30."""
    import deepseek_opportunities as O
    rows = O.control_universe()
    noise = next(r for r in rows if r['ticker'] == 'NOIS5.TO')['technicals']
    for r in rows:
        if r['ticker'] in (O.CONTROL_LONG, O.CONTROL_SHORT):
            r['technicals'] = dict(noise, last=noise['last'] + (7 if r['ticker'] == O.CONTROL_LONG else 9))
    now = dt.datetime(2026, 9, 17, 9, 5, tzinfo=ET)
    req = O.build_request(rows, None, now)
    p = req['payload']
    p['entry'] = '10:01 ET'
    p.setdefault('data_dates', {})['open30'] = '2026-09-17 09:30–10:00 ET'
    for i, row in enumerate(p['candidates']):
        if row['ticker'] == O.CONTROL_LONG:
            row['open30'] = {'gap_pct': 0.2, 'r30_pct': 2.5, 'x30_pct': 2.4, 'rvol30': 4.2,
                             'vwap30_gap_pct': 0.9, 'range30_pos': 0.97}
        elif row['ticker'] == O.CONTROL_SHORT:
            row['open30'] = {'gap_pct': -0.2, 'r30_pct': -2.8, 'x30_pct': -2.9, 'rvol30': 4.0,
                             'vwap30_gap_pct': -1.0, 'range30_pos': 0.03}
        else:
            s = 0.3 * (1 if i % 2 else -1) * ((i % 3) + 1) / 3
            row['open30'] = {'gap_pct': round(s / 2, 2), 'r30_pct': round(s + 0.1, 2), 'x30_pct': round(s, 2),
                             'rvol30': round(0.95 + 0.01 * i, 2), 'vwap30_gap_pct': round(s / 10, 2),
                             'range30_pos': round(0.45 + 0.01 * i, 2)}
    p.setdefault('macro', {})['xiu_open30'] = {'gap_pct': 0.1, 'r30_pct': 0.1}
    return p, req['allowed']


def run_control(ask, runs=5):
    import deepseek_opportunities as O
    import nominations as N
    system = after_open_prompt(N.prompt())
    payload, allowed = control_payload()
    out = []
    for _ in range(runs):
        try:
            longs, shorts, _ = N.clean(ask(system, json.dumps(payload, sort_keys=True)), allowed,
                                       payload['candidates'])
            L, S = [p['ticker'] for p in longs], [p['ticker'] for p in shorts]
            out.append({'clean': O.CONTROL_LONG in L and O.CONTROL_SHORT in S, 'longs': L, 'shorts': S})
        except Exception as exc:
            out.append({'clean': False, 'error': type(exc).__name__})
    return {'runs': out, 'clean': sum(r['clean'] for r in out), 'passes': sum(r['clean'] for r in out) >= 4}


# ---------------------------------------------------------------- statistics
def stat(pairs):
    pairs = [(s, v) for s, v in pairs if v is not None]
    if len(pairs) < 2:
        return {'n': len(pairs)}
    mean, se, t = clustered(pairs)
    return {'n': len(pairs), 'sessions': len({s for s, _ in pairs}), 'mean_pct': round(mean, 3),
            'se': round(se, 3), 't': round(t, 2) if t is not None else None,
            'hit': round(sum(v > 0 for _, v in pairs) / len(pairs), 3)}


def scored(answers, data, market, entry):
    out = []
    for a in answers:
        for side, key in (('LONG', 'longs'), ('SHORT', 'shorts')):
            for p in a.get(key) or []:
                y = outcome(data[p['ticker']], market, a['session'], side, entry) if p['ticker'] in data else None
                out.append({'session': a['session'], 'side': side, 'ticker': p['ticker'], 'y': y,
                            'confidence': p.get('confidence')})
    return out


def placebo(picks, universe, data, market, entry, draws=DRAWS, seed=SEED):
    """Random names, as many longs and shorts per session as the arm picked."""
    rng = np.random.default_rng(seed)
    need = {}
    for p in picks:
        if p['y'] is not None:
            need.setdefault(p['session'], {'LONG': 0, 'SHORT': 0})[p['side']] += 1
    pre = {}
    for s, names in universe.items():
        pre[s] = {side: np.array([outcome(data[t], market, s, side, entry) for t in names])
                  for side in ('LONG', 'SHORT')}
    means = []
    for _ in range(draws):
        vals = []
        for s, n in need.items():
            for side in ('LONG', 'SHORT'):
                if n[side]:
                    v = pre[s][side]
                    vals.extend(v[rng.choice(len(v), size=min(n[side], len(v)), replace=False)])
        means.append(float(np.mean(vals)))
    return means


def summarize(a_picks, b_picks, rule_picks, universe, data, market, control):
    b = stat([(p['session'], p['y']) for p in b_picks])
    a = stat([(p['session'], p['y']) for p in a_picks])
    null_b = placebo(b_picks, universe, data, market, 'p1000')
    null_a = placebo(a_picks, universe, data, market, 'p945')
    p_b = sum(d >= b['mean_pct'] for d in null_b) / len(null_b) if b.get('mean_pct') is not None else None
    p_a = sum(d >= a['mean_pct'] for d in null_a) / len(null_a) if a.get('mean_pct') is not None else None
    planted_t = round(PLANTED / b['se'], 2) if b.get('se') else None
    checks = {'mean_positive_t_ge_3': bool(b.get('mean_pct') and b['mean_pct'] > 0 and (b.get('t') or 0) >= 3),
              'placebo_p_below_0_05': p_b is not None and p_b < 0.05,
              'control_detects_planted_0_5': bool(planted_t and planted_t >= 3)}
    verdict = ('NOT RUN: the model control failed' if not control.get('passes') else
               'PASS' if all(checks.values()) else
               'UNDERPOWERED' if not checks['control_detects_planted_0_5'] else 'FAIL')
    by_a, by_b = {}, {}
    for p in a_picks:
        if p['y'] is not None:
            by_a.setdefault(p['session'], []).append(p['y'])
    for p in b_picks:
        if p['y'] is not None:
            by_b.setdefault(p['session'], []).append(p['y'])
    diffs = [(s, st.mean(by_b[s]) - st.mean(by_a[s])) for s in by_b if s in by_a]
    follows = [p for p in b_picks if p.get('x30') is not None]
    return {'t2_after_open': {'arm_b': b, 'placebo': {'draws': len(null_b), 'mean_of_draws_pct': round(st.mean(null_b), 4),
                                                      'p_one_sided': p_b},
                              'control': {'planted_pct': PLANTED, 't_planted': planted_t,
                                          'mde80_pct': round(2.8 * b['se'], 3) if b.get('se') else None},
                              'checks': checks, 'verdict': verdict},
            'model_control': control,
            'descriptive': {
                'arm_a_before_open': {**a, 'placebo_p_one_sided': p_a},
                'b_minus_a_by_session': stat(diffs),
                'rule_follow_x30': stat([(p['session'], p['y']) for p in rule_picks]),
                'arm_b_follows_x30_share': round(sum((p['side'] == 'LONG') == (p['x30'] > 0) for p in follows)
                                                 / len(follows), 3) if follows else None,
                'arm_b_long': stat([(p['session'], p['y']) for p in b_picks if p['side'] == 'LONG']),
                'arm_b_short': stat([(p['session'], p['y']) for p in b_picks if p['side'] == 'SHORT'])}}


def rule(universe, data, market):
    """Two highest x30_pct long and two lowest short per session, 10:00 → close."""
    out = []
    for s, names in universe.items():
        xs = [(open30(data[t], market, s) or {}).get('x30_pct') for t in names]
        ranked = sorted((x, t) for x, t in zip(xs, names) if x is not None)
        for x, t in ranked[-2:]:
            out.append({'session': s, 'side': 'LONG', 'ticker': t, 'y': outcome(data[t], market, s, 'LONG', 'p1000')})
        for x, t in ranked[:2]:
            out.append({'session': s, 'side': 'SHORT', 'ticker': t, 'y': outcome(data[t], market, s, 'SHORT', 'p1000')})
    return out


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    p.add_argument('--state-dir', default='.rb-state')
    p.add_argument('--cache', required=True)
    p.add_argument('--out', default=str(OUT))
    p.add_argument('--control-only', action='store_true')
    a = p.parse_args(argv)
    from prepare_deepseek import load_private_key, load_private_model
    load_private_key(a.state_dir)
    load_private_model(a.state_dir)
    F.load_key(a.state_dir)
    import council
    import nominations as N
    ask = lambda system, user: council.ask_deepseek(system, user)
    control = run_control(ask)
    print(json.dumps({'model_control': control}, default=str))
    if a.control_only or not control['passes']:
        Path(a.out).write_text(json.dumps({'registered': 'PREREGISTER_day132c_after_open.md',
                                           'model_control': control,
                                           'verdict': 'NOT RUN: the model control failed'
                                           if not control['passes'] else 'control only'}, indent=1) + '\n')
        return 0 if control['passes'] else 2
    pools = {Path(f).stem: json.loads(Path(f).read_text()) for f in sorted(glob.glob(str(POOLS / '*.json')))}
    pools = {s: v for s, v in pools.items() if FIRST <= s <= LAST}
    tickers = sorted({c['ticker'] for v in pools.values() for c in v['candidates'] if c['ticker'].endswith('.TO')})
    fetch = Fetch(None)
    with cf.ThreadPoolExecutor(8) as pool:
        data = dict(zip([MARKET] + tickers, pool.map(lambda t: collect(t, fetch, a.cache), [MARKET] + tickers)))
    market = data.pop(MARKET)
    system_a, system_b = N.prompt(), after_open_prompt(N.prompt())
    jobs, universe = [], {}
    for s, pool_ in sorted(pools.items()):
        req, b = requests_for(pool_, data, market, s)
        if not req:
            continue
        universe[s] = [r['ticker'] for r in req['payload']['candidates']]
        jobs.append(('A', s, system_a, req['payload'], req['allowed']))
        jobs.append(('B', s, system_b, b, req['allowed']))
    with cf.ThreadPoolExecutor(4) as pool:
        answers = list(pool.map(lambda j: ask_arm(*j, ask=ask, cache=a.cache), jobs))
    errors = [x for x in answers if x.get('error')]
    a_ans = [x for x in answers if x['arm'] == 'A' and not x.get('error')]
    b_ans = [x for x in answers if x['arm'] == 'B' and not x.get('error')]
    a_picks = scored(a_ans, data, market, 'p945')
    b_picks = scored(b_ans, data, market, 'p1000')
    for p_ in b_picks:
        p_['x30'] = (open30(data[p_['ticker']], market, p_['session']) or {}).get('x30_pct') if p_['ticker'] in data else None
    out = summarize(a_picks, b_picks, rule(universe, data, market), universe, data, market, control)
    out.update({'registered': 'PREREGISTER_day132c_after_open.md', 'run_on': dt.date.today().isoformat(),
                'sessions': len(universe), 'names_per_session_median': st.median(len(v) for v in universe.values()),
                'answers': {'A': len(a_ans), 'B': len(b_ans), 'errors': [(x['arm'], x['session'], x['error']) for x in errors]},
                'fetch_failures': fetch.failures,
                'picks': {'A': a_picks, 'B': b_picks}})
    Path(a.out).write_text(json.dumps(out, indent=1, sort_keys=True, default=float) + '\n')
    brief = {k: v for k, v in out.items() if k != 'picks'}
    print(json.dumps(brief, indent=1, sort_keys=True, default=float))
    return 0


if __name__ == '__main__':
    sys.exit(main())
