#!/usr/bin/env python3
"""Day-132b (PREREGISTER_day132b_feedback.md): an outside read of the
scoreboard, tested.

    python feedback_review.py --cache DIR      writes data/review_day132b_feedback.json

M1-M7 are descriptive; T1 is the registered test: does a model's own
confidence rank its picks? DIR is the day-132 per-name cache
(replay_chasing.py --cache). Research only: nothing here is read by the
morning.
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import glob
import json
import math
import sqlite3
import statistics as st
import sys
from pathlib import Path

import numpy as np

import fmp_client as F
from replay_chasing import MARKET, collect
from replay_drift import Fetch
from replay_fmp_analyst import clustered

ROOT = Path(__file__).resolve().parent
OUT = ROOT / 'data' / 'review_day132b_feedback.json'
PICKS = ROOT / 'data' / 'model_picks.csv'
REPLAY = ROOT / '.rb-state' / 'replay'
REPORTS = ROOT / '.rb-state' / 'reports.sqlite3'
SEED, DRAWS, PLANTED = 132, 2000, 0.5
COMMISSION_PER_SIDE = (0.01, 0.05)       # % per side: a range, not measured
COUNCIL_FROM = '2026-10-05'


def stat(values, sessions=None):
    """n, hit, mean, and (when sessions are given) the session-clustered se and t."""
    v = [x for x in values if x is not None]
    if not v:
        return {'n': 0}
    out = {'n': len(v), 'hit': round(sum(x > 0 for x in v) / len(v), 3), 'mean_pct': round(st.mean(v), 3)}
    if sessions is not None and len(v) >= 2:
        pairs = [(s, x) for s, x in zip(sessions, values) if x is not None]
        mean, se, t = clustered(pairs)
        out.update({'se': round(se, 3) if se else None, 't': round(t, 2) if t is not None else None})
    return out


def read_picks(path=PICKS):
    with open(path, newline='') as f:
        return [r for r in csv.DictReader(f)]


def xiu_945(market, session):
    b = market['bars'].get(session)
    return None if b is None else 100 * (b[3] / b[1] - 1)


def five_min(fetch, ticker, day):
    rows = fetch('historical-chart/5min', symbol=ticker, **{'from': day, 'to': day}) or []
    return {r['date'][11:16]: r for r in rows if r['date'][:10] == day}


# ---------------------------------------------------------------- M1, M4
def decompose(rows, market, late_market):
    """Each scored pick: raw r, the market's part (side × XIU over the same
    window), and the rest."""
    out = []
    for r in rows:
        if not r.get('scored_at') or r.get('r_pct') in ('', None):
            continue
        sign = 1 if r['side'] == 'LONG' else -1
        if r.get('entry_time'):
            x = late_market.get((r['session'], r['entry_time']))
        else:
            x = xiu_945(market, r['session'])
        raw = float(r['r_pct'])
        mkt = None if x is None else sign * x
        out.append({'session': r['session'], 'key': '%s_%s' % (r['model'], r['kind']), 'side': r['side'],
                    'ticker': r['ticker'], 'raw': raw, 'mkt': mkt,
                    'excess': None if mkt is None else raw - mkt,
                    'confidence': float(r['confidence']) if r.get('confidence') not in ('', None) else None,
                    'prompt_version': r.get('prompt_version') or ''})
    return out


def rows_table(picks, keys):
    table = {}
    for k in keys:
        g = [p for p in picks if p['key'] == k]
        if not g:
            continue
        s = [p['session'] for p in g]
        table[k] = {'raw': stat([p['raw'] for p in g], s), 'market_part': stat([p['mkt'] for p in g], s),
                    'excess': stat([p['excess'] for p in g], s),
                    'longs': sum(p['side'] == 'LONG' for p in g), 'shorts': sum(p['side'] == 'SHORT' for p in g),
                    'sessions': len(set(s))}
    return table


# ---------------------------------------------------------------- M2
def spreads(path=REPORTS):
    """Entry spreads (bps) recorded at 09:46 on the sized desk legs and the
    engine's legs of every stored publication."""
    out = []
    if not Path(path).exists():
        return out
    con = sqlite3.connect(path)
    for session, body in con.execute('select session, body from reports'):
        intra = json.loads(body).get('intraday') or {}
        for d in intra.get('desks') or []:
            for leg in d.get('legs') or []:
                v = leg.get('entry_spread_bps')
                if isinstance(v, (int, float)) and v > 0:
                    out.append({'session': session, 'ticker': leg.get('ticker'), 'bps': float(v), 'who': d.get('model')})
        for leg in intra.get('legs') or []:
            v = leg.get('entry_spread_bps') if isinstance(leg, dict) else None
            if isinstance(v, (int, float)) and v > 0:
                out.append({'session': session, 'ticker': leg.get('ticker'), 'bps': float(v), 'who': 'engine'})
    return out


def costs(sp):
    if not sp:
        return {'legs': 0}
    bps = sorted(s['bps'] for s in sp)
    med = st.median(bps)
    lo = med / 2 / 100 + 2 * COMMISSION_PER_SIDE[0]      # half spread in, auction out
    hi = med / 100 + 2 * COMMISSION_PER_SIDE[1]          # full spread, both ways
    return {'legs': len(bps), 'sessions': len({s['session'] for s in sp}),
            'spread_bps': {'median': round(med, 1), 'p25': round(bps[len(bps) // 4], 1),
                           'p75': round(bps[3 * len(bps) // 4], 1), 'max': round(bps[-1], 1)},
            'round_trip_pct': {'low': round(lo, 3), 'high': round(hi, 3)},
            'assumptions': 'low: half the median entry spread plus an exit in the closing auction; high: the '
                           'full median spread; commission %.2f-%.2f%% per side (not measured); no borrow fee on '
                           'a same-day short' % COMMISSION_PER_SIDE}


# ---------------------------------------------------------------- M3
def council_vs(picks):
    council = [p for p in picks if p['key'] == 'top2_pick' and 'day124-council' in p['prompt_version']]
    sessions = sorted({p['session'] for p in council})
    desks = ('claude_selected', 'deepseek_selected', 'gemini_selected', 'jev_selected')
    out = {'sessions': sessions}

    def on(ss, key):
        g = [p for p in picks if p['key'] == key and p['session'] in ss]
        return {'raw': stat([p['raw'] for p in g], [p['session'] for p in g]),
                'excess': stat([p['excess'] for p in g], [p['session'] for p in g])}
    out['council_top2'] = on(sessions, 'top2_pick')
    out['debate_final'] = on(sessions, 'debate_final')
    for k in desks + ('jev_forced', 'engine_board'):
        out[k] = on(sessions, k)
    best, diffs = [], []
    for s in sessions:
        cand = [p for p in picks if p['session'] == s and p['key'] in desks and p['confidence'] is not None]
        if not cand:
            continue
        top = max(cand, key=lambda p: p['confidence'])
        best.append(top)
        c = [p['raw'] for p in council if p['session'] == s]
        if c:
            diffs.append(top['raw'] - st.mean(c))
    out['highest_conviction_desk_pick'] = {
        'raw': stat([p['raw'] for p in best], [p['session'] for p in best]),
        'excess': stat([p['excess'] for p in best], [p['session'] for p in best]),
        'picks': [(p['session'], p['key'], p['side'], p['ticker'], p['confidence'], round(p['raw'], 3)) for p in best]}
    if len(diffs) >= 2:
        m, sd = st.mean(diffs), st.stdev(diffs)
        se = sd / math.sqrt(len(diffs))
        out['paired_best_minus_council'] = {'sessions': len(diffs), 'mean_pct': round(m, 3), 'se': round(se, 3),
                                            't': round(m / se, 2) if se else None, 'mde80_pct': round(2.8 * se, 3)}
    return out


# ---------------------------------------------------------------- M5
def power(picks, key='top2_pick'):
    v = [p['raw'] for p in picks if p['key'] == key]
    sd = st.stdev(v)
    need = {('%.1f' % e): math.ceil((3 * sd / e) ** 2) for e in (0.1, 0.2, 0.3)}
    return {'per_pick_sd_pct': round(sd, 3), 'picks_for_t3': need,
            'sessions_for_t3_at_2_per_day': {k: math.ceil(n / 2) for k, n in need.items()},
            'mde80_pct': {str(s): round(2.8 * sd / math.sqrt(2 * s), 3) for s in (9, 40, 60, 120)}}


# ---------------------------------------------------------------- M6
def biotech(path=ROOT / 'data' / 'biotech_calls.csv'):
    with open(path, newline='') as f:
        rows = list(csv.DictReader(f))
    first = {}
    for r in sorted(rows, key=lambda r: r['session']):
        first.setdefault(r['event_id'], r)
    by_month = {}
    for r in first.values():
        by_month[r['window_end'][:7]] = by_month.get(r['window_end'][:7], 0) + 1
    scored = [r for r in first.values() if r.get('r_pct') not in ('', None)]
    return {'calls': len(rows), 'events': len(first),
            'calls_by_side': {s: sum(r['side'] == s for r in rows) for s in ('LONG', 'SHORT')},
            'first_calls_by_side': {s: sum(r['side'] == s for r in first.values()) for s in ('LONG', 'SHORT')},
            'resolved_events': len(scored),
            'resolved': [(r['event_id'], r['side'], r['r_pct']) for r in scored],
            'events_by_window_end_month': dict(sorted(by_month.items()))}


# ---------------------------------------------------------------- T1
def replay_runs(root=REPLAY):
    """{run: {session: [(side, ticker, confidence), ...]}} in the order returned."""
    runs = {'flash': {}, 'v4pro': {}, 'research': {}, 'single': {}}

    def add(run, session, d):
        ps = [('LONG', p['ticker'], p.get('confidence')) for p in d.get('longs') or []]
        ps += [('SHORT', p['ticker'], p.get('confidence')) for p in d.get('shorts') or []]
        runs[run][session] = [p for p in ps if isinstance(p[2], (int, float))]
    for f in sorted(glob.glob(str(root / 'answers' / '*.json'))):
        add('flash', Path(f).stem, json.load(open(f)).get('deepseek') or {})
    for f in sorted(glob.glob(str(root / 'v4pro' / '*.json'))):
        add('v4pro', Path(f).stem, json.load(open(f)).get('deepseek') or {})
    for f in sorted(glob.glob(str(root / 'research' / '*.json'))):
        session, kind = Path(f).stem.split('_')
        add(kind, session, json.load(open(f)))
    return runs


def outcome(data, market, side, ticker, session, excess=False):
    b = (data.get(ticker) or {}).get('bars', {}).get(session)
    if b is None:
        return None
    r = 100 * (b[3] / b[1] - 1)
    if excess:
        x = xiu_945(market, session)
        if x is None:
            return None
        r -= x
    return r if side == 'LONG' else -r


def units(runs, data, market, excess=False):
    """[(session, [(confidence, outcome), ...])] per (run, session) with ≥ 2 scored picks."""
    out = []
    for run, by in runs.items():
        for session, ps in sorted(by.items()):
            scored = [(c, outcome(data, market, s, t, session, excess)) for s, t, c in ps]
            scored = [(c, y) for c, y in scored if y is not None]
            if len(scored) >= 2:
                out.append((session, run, scored))
    return out


def top_minus_rest(scored):
    i = max(range(len(scored)), key=lambda j: (scored[j][0], -j))
    rest = [y for j, (_, y) in enumerate(scored) if j != i]
    return scored[i][1] - st.mean(rest)


def spearman(xs, ys):
    def ranks(v):
        order = sorted(range(len(v)), key=lambda i: v[i])
        r = [0.0] * len(v)
        i = 0
        while i < len(order):
            j = i
            while j + 1 < len(order) and v[order[j + 1]] == v[order[i]]:
                j += 1
            for k in range(i, j + 1):
                r[order[k]] = (i + j) / 2
            i = j + 1
        return r
    rx, ry = ranks(xs), ranks(ys)
    return float(np.corrcoef(rx, ry)[0, 1]) if len(xs) > 2 else None


def t1(runs, data, market, seed=SEED, draws=DRAWS):
    us = units(runs, data, market)
    vals = [(s, top_minus_rest(sc)) for s, _, sc in us]
    mean, se, t = clustered(vals)
    rng = np.random.default_rng(seed)
    null = []
    for _ in range(draws):
        dv = []
        for s, _, sc in us:
            conf = [c for c, _ in sc]
            rng.shuffle(conf)
            dv.append(top_minus_rest([(c, y) for c, (_, y) in zip(conf, sc)]))
        null.append(st.mean(dv))
    p = sum(d >= mean for d in null) / len(null)
    planted_t = round(PLANTED / se, 2) if se else None
    checks = {'mean_positive_t_ge_3': bool(mean > 0 and t is not None and t >= 3),
              'placebo_p_below_0_05': p < 0.05,
              'control_detects_planted_0_5': bool(planted_t and planted_t >= 3)}
    verdict = ('PASS' if all(checks.values()) else
               'UNDERPOWERED' if not checks['control_detects_planted_0_5'] else 'FAIL')
    per_run = {}
    for run in runs:
        v = [(s, top_minus_rest(sc)) for s, r, sc in us if r == run]
        if len(v) >= 2:
            m, e, tt = clustered(v)
            per_run[run] = {'units': len(v), 'mean_pct': round(m, 3), 't': round(tt, 2) if tt is not None else None}
    flat = [(c, y) for _, _, sc in us for c, y in sc]
    ex = units(runs, data, market, excess=True)
    ex_vals = [(s, top_minus_rest(sc)) for s, _, sc in ex]
    em, ese, et = clustered(ex_vals)
    sessions = sorted({s for s, _, _ in us})
    rng2 = np.random.default_rng(seed)
    boots = []
    by_s = {}
    for s, _, sc in us:
        by_s.setdefault(s, []).extend(sc)
    for _ in range(1000):
        pick = rng2.choice(sessions, size=len(sessions), replace=True)
        xs = [c for s in pick for c, _ in by_s[s]]
        ys = [y for s in pick for _, y in by_s[s]]
        boots.append(spearman(xs, ys))
    top_all = [sc[max(range(len(sc)), key=lambda j: (sc[j][0], -j))][1] for _, _, sc in us]
    rest_all = [y for _, _, sc in us for j, (_, y) in enumerate(sc)
                if j != max(range(len(sc)), key=lambda k: (sc[k][0], -k))]
    return {'units': len(us), 'sessions': len(sessions), 'picks': len(flat),
            'top_minus_rest': {'mean_pct': round(mean, 3), 'se': round(se, 3), 't': round(t, 2)},
            'placebo': {'draws': draws, 'p_one_sided': p, 'mean_of_draws_pct': round(st.mean(null), 4)},
            'control': {'planted_pct': PLANTED, 't_planted': planted_t, 'mde80_pct': round(2.8 * se, 3)},
            'checks': checks, 'verdict': verdict, 'per_run': per_run,
            'descriptive': {
                'top_pick': stat(top_all), 'other_picks': stat(rest_all),
                'against_xiu_top_minus_rest': {'mean_pct': round(em, 3), 't': round(et, 2) if et is not None else None},
                'spearman_confidence_outcome': round(spearman([c for c, _ in flat], [y for _, y in flat]), 3),
                'spearman_ci95_session_bootstrap': [round(float(np.percentile(boots, 2.5)), 3),
                                                    round(float(np.percentile(boots, 97.5)), 3)]}}


# ---------------------------------------------------------------- M7
def today_picks(report_path, fetch, session):
    import exposure
    rep = json.loads(Path(report_path).read_text())
    intra = rep.get('intraday') or {}
    picks = []
    for p in (intra.get('top_two') or {}).get('picks') or []:
        picks.append(('Top 2', p.get('side'), p.get('ticker')))
    for d in intra.get('desks') or []:
        for leg in d.get('legs') or []:
            picks.append(('%s desk (%s)' % (d.get('model'), leg.get('status')), leg.get('side'), leg.get('ticker')))
    jev = intra.get('jev') or {}
    for k, side in (('forced_long', 'LONG'), ('forced_short', 'SHORT')):
        if (jev.get(k) or {}).get('ticker'):
            picks.append(('Jev forced', side, jev[k]['ticker']))
    for leg in intra.get('legs') or []:
        if isinstance(leg, dict) and leg.get('ticker'):
            picks.append(('Engine', leg.get('side'), leg.get('ticker')))
    for g in (intra.get('gap_signal') or {}).get('picks') or []:
        picks.append(('Gap signal', g.get('side'), g.get('ticker')))
    bars, out = {}, []

    def move(t):
        if t not in bars:
            bars[t] = five_min(fetch, t, session)
        b = bars[t]
        if '09:40' not in b or not b:
            return None, None
        last = max(b)
        return 100 * (b[last]['close'] / b['09:40']['close'] - 1), last
    xiu, last = move(MARKET)
    for who, side, t in picks:
        if not side or not t:
            continue
        r, at = move(t)
        etf = exposure.position_exposure(t)['etf']
        e, _ = move(etf) if etf else (None, None)
        sign = 1 if side == 'LONG' else -1
        out.append({'who': who, 'pick': '%s %s' % (side, t), 'since_0945_pct': None if r is None else round(sign * r, 2),
                    'vs_xiu_pct': None if r is None or xiu is None else round(sign * (r - xiu), 2),
                    'etf': etf, 'vs_etf_pct': None if r is None or e is None else round(sign * (r - e), 2),
                    'as_of': at})
    return {'as_of': last, 'xiu_since_0945_pct': None if xiu is None else round(xiu, 2), 'picks': out}


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    p.add_argument('--state-dir', default='.rb-state')
    p.add_argument('--cache', required=True, help='the day-132 per-name cache (replay_chasing.py --cache)')
    p.add_argument('--out', default=str(OUT))
    p.add_argument('--today', default=None)
    a = p.parse_args(argv)
    F.load_key(a.state_dir)
    fetch = Fetch(None)
    cache = Path(a.cache)
    data = {f.stem: json.loads(f.read_text()) for f in cache.glob('*.json')}
    market = data[MARKET]
    rows = read_picks()
    late_market = {}
    for r in rows:
        if r.get('entry_time') and r.get('scored_at') and (r['session'], r['entry_time']) not in late_market:
            b = five_min(fetch, MARKET, r['session'])
            if r['entry_time'] in b and '15:55' in b:
                late_market[(r['session'], r['entry_time'])] = 100 * (b['15:55']['close'] / b[r['entry_time']]['close'] - 1)
    picks = decompose(rows, market, late_market)
    keys = ('top2_pick', 'claude_selected', 'deepseek_selected', 'gemini_selected', 'engine_board',
            'jev_selected', 'jev_forced', 'debate_final', 'claude_late', 'deepseek_late', 'jev_late_forced',
            'top2count_pick', 'top2memory_pick')
    sessions = sorted({p['session'] for p in picks if not p['key'].endswith('late') and p['key'] != 'jev_late_forced'})
    xs = [xiu_945(market, s) for s in sessions]
    sp = spreads()
    out = {'registered': 'PREREGISTER_day132b_feedback.md', 'run_on': dt.date.today().isoformat(),
           'm1_rows': rows_table(picks, keys),
           'm1_xiu_0945_close': {'sessions': len(sessions), 'mean_pct': round(st.mean([x for x in xs if x is not None]), 3),
                                  'by_session': {s: round(x, 3) for s, x in zip(sessions, xs) if x is not None}},
           'm2_costs': costs(sp),
           'm3_council': council_vs(picks),
           'm4_late': [p for p in picks if p['key'] in ('claude_late', 'deepseek_late', 'jev_late_forced')],
           'm5_power': power(picks),
           'm6_biotech': biotech(),
           't1_confidence': t1(replay_runs(), data, market)}
    try:
        import model_picks
        out['m4_wire'] = model_picks.wire_card(rows).get('wire_release')
    except Exception as exc:            # the wire card is descriptive; say why it is missing
        out['m4_wire'] = {'error': '%s: %s' % (type(exc).__name__, str(exc)[:120])}
    today = a.today or dt.date.today().isoformat()
    report = Path(a.state_dir) / 'latest' / 'report.json'
    if report.exists():
        out['m7_today'] = today_picks(report, fetch, today)
    out['fetch_failures'] = fetch.failures
    Path(a.out).write_text(json.dumps(out, indent=1, sort_keys=True, default=float) + '\n')
    print(json.dumps(out, indent=1, sort_keys=True, default=float))
    return 0


if __name__ == '__main__':
    sys.exit(main())
