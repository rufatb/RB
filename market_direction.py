#!/usr/bin/env python3
"""Day-147c (PREREGISTER_day147c_market_direction.md): can the market's
direction after 09:45 be read at 09:45?

    python market_direction.py --fetch   # SPY's bars into .rb-state/market_direction_cache; computes no return
    python market_direction.py           # the one registered look -> data/market_direction_day147c.json

Primary: y = sign(XIU.TO's prior close -> 09:45) x XIU.TO's 09:45 -> close, one
per session, 2024-01-02 -> 2026-10-29, from the day-143 cache (FMP 15-minute
bars reduced to the open, 09:45, noon and the close). Research only: nothing
here is read by the morning, and no model is asked.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import math
import random
import statistics as st
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
OUT = ROOT/'data'/'market_direction_day147c.json'
TSX_CACHE = ROOT/'.rb-state'/'report_day_cache'/'tsx'
CACHE = ROOT/'.rb-state'/'market_direction_cache'
SECTORS = ROOT/'data'/'tsx_sectors.json'
START, END, EOD_FROM = '2024-01-02', '2026-10-29', '2023-10-01'
MARKET, US = 'XIU.TO', 'SPY'
SEED, DRAWS = 1473, 10000
BAR_T, BAR_P, SPY_T = 3.0, 0.01, 2.0
COST = 0.02            # XIU's round trip, %
PLANT = 0.10           # the control, % a session
MIN_SECTOR = 3
BIG = 0.5              # a "big morning", % either way
MAX_GAP_DAYS = 5       # a prior close further back than this is a data hole


# ── data ─────────────────────────────────────────────────────────────────────

def fetch_spy(cache=CACHE):
    """SPY's 15-minute bars (reduced as the day-143 cache) and unadjusted daily
    closes. Cached whole; computes no return."""
    import fmp_client as F
    import replay_chasing as RC
    import report_day as RD
    import replay_weeks as W
    from replay_drift import Fetch
    f = Path(cache)/'SPY.json'
    if f.exists():
        return json.loads(f.read_text())
    F.load_key(str(ROOT/'.rb-state'))
    get = W.robust(Fetch(None))
    eod = RD._eod(get('historical-price-eod/full', symbol=US, **{'from': EOD_FROM, 'to': END}))
    bars, failed, capped = {}, 0, 0
    for a, b in RC.months(START, END):
        rows = get('historical-chart/15min', symbol=US, **{'from': a, 'to': b})
        if rows is None:
            failed += 1
            continue
        if len(rows) >= RC.CAP_BARS:
            capped += 1
        bars.update(RC.reduce_bars(rows))
    out = {'ticker': US, 'eod': eod, 'bars': bars, 'failed_calls': failed, 'capped_calls': capped}
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(json.dumps(out))
    return out


def load(path):
    return json.loads(Path(path).read_text())


def closes(eod):
    """[(date, close)] in date order from the cache's eod rows."""
    return sorted((r[0], r[4]) for r in eod)


def prior_close(eod):
    """{date: (prior session's close, the close before that)}, only where the
    prior session is at most MAX_GAP_DAYS back (else a hole, left out)."""
    cs = closes(eod)
    out = {}
    for i in range(1, len(cs)):
        d, prev = cs[i][0], cs[i - 1]
        gap = (dt.date.fromisoformat(d) - dt.date.fromisoformat(prev[0])).days
        if gap > MAX_GAP_DAYS:
            continue
        pp = cs[i - 2][1] if i >= 2 else None
        out[d] = (prev[1], pp)
    return out


def session_points(series):
    """{date: dict} for one instrument: prior close -> 09:45 ('so_far'), open
    -> 09:45 ('first15'), prior close -> open ('gap'), the prior session
    ('prior'), and 09:45 -> close ('after'), all in %."""
    pc = prior_close(series['eod'])
    out = {}
    for d, b in series['bars'].items():
        if not (START <= d <= END) or d not in pc:
            continue
        o, p945, _noon, c = b
        prev, prev2 = pc[d]
        if not all(isinstance(x, (int, float)) and x > 0 for x in (o, p945, c, prev)):
            continue
        out[d] = {'so_far': 100 * (p945 / prev - 1), 'first15': 100 * (p945 / o - 1),
                  'gap': 100 * (o / prev - 1),
                  'prior': None if not prev2 else 100 * (prev / prev2 - 1),
                  'after': 100 * (c / p945 - 1)}
    return out


def sign(x):
    return 0 if x is None or x == 0 else (1 if x > 0 else -1)


# ── the machinery (day-145's, two-sided) ─────────────────────────────────────

def t_stat(ys):
    """Day-145's t over session means (mean / sd x sqrt(n)), in plain floats so
    that 10,000 placebo draws stay quick."""
    n = len(ys)
    if n < 3:
        return None
    m = sum(ys) / n
    v = sum((y - m) ** 2 for y in ys) / (n - 1)
    if v <= 0:
        return None
    return m / math.sqrt(v / n)


def placebo_two(ys, *, draws=DRAWS, seed=SEED):
    """Two-sided sign-flip p: each session's y flipped as a unit; the share of
    draws with |t| at or above the real |t|."""
    t0 = t_stat(ys)
    if t0 is None:
        return None
    rng = random.Random(seed)
    hits = 0
    for _ in range(draws):
        t = t_stat([y if rng.random() < 0.5 else -y for y in ys])
        if t is not None and abs(t) >= abs(t0):
            hits += 1
    return (1 + hits) / (1 + draws)


def blocks(ys, k=4):
    n = len(ys)
    cuts = [round(i * n / k) for i in range(k + 1)]
    return [st.mean(ys[cuts[i]:cuts[i + 1]]) for i in range(k) if cuts[i + 1] > cuts[i]]


def control(ys):
    """House rule 10: centred on zero, PLANT added to every session."""
    m = st.mean(ys)
    t = t_stat([y - m + PLANT for y in ys])
    return {'planted_pct': PLANT, 't': None if t is None else round(t, 2),
            'detected': t is not None and t >= BAR_T}


def arm(days, *, draws=DRAWS, seed=SEED):
    """days: [(date, predictor, outcome)] in date order -> the arm's numbers."""
    days = sorted((d, p, a) for d, p, a in days if p is not None and a is not None)
    ys = [sign(p) * a for _, p, a in days]
    n = len(ys)
    if n < 3:
        return {'sessions': n, 'status': 'NO_DATA'}
    t = t_stat(ys)
    sd = st.stdev(ys)
    decided = [y for y in ys if y != 0]
    return {'sessions': n, 'mean_pct': round(st.mean(ys), 4),
            't': None if t is None else round(t, 2),
            'placebo_p_two': placebo_two(ys, draws=draws, seed=seed),
            'blocks': [round(b, 4) for b in blocks(ys)],
            'halves': [round(st.mean(ys[:n // 2]), 4), round(st.mean(ys[n // 2:]), 4)],
            'hit_rate': round(sum(y > 0 for y in decided) / len(decided), 4) if decided else None,
            'followed_up_share': round(sum(sign(p) > 0 for _, p, _ in days) / n, 4),
            'outcome_mean_pct': round(st.mean(a for _, _, a in days), 4),
            'outcome_sd_pct': round(st.stdev(a for _, _, a in days), 4),
            'control': control(ys),
            'mde_pct': round((BAR_T + 0.84) * sd / math.sqrt(n), 4) if sd else None,
            'first': days[0][0], 'last': days[-1][0]}


def clears(a, *, p=None):
    """The registered bar without the SPY check; `p` replaces the arm's own
    placebo p (Holm)."""
    if a.get('t') is None:
        return False
    p = a['placebo_p_two'] if p is None else p
    same = all(b > 0 for b in a['blocks']) or all(b < 0 for b in a['blocks'])
    return (abs(a['t']) >= BAR_T and p is not None and p < BAR_P and same
            and abs(a['mean_pct']) > COST)


def holm(ps):
    """Holm-adjusted p's, same order as given; None stays None."""
    idx = sorted((p, i) for i, p in enumerate(ps) if p is not None)
    m, out, run = len(idx), [None] * len(ps), 0.0
    for k, (p, i) in enumerate(idx):
        run = max(run, min(1.0, (m - k) * p))
        out[i] = round(run, 4)
    return out


def verdict(primary, spy_own):
    ok = clears(primary)
    spy_ok = (spy_own.get('t') is not None and abs(spy_own['t']) >= SPY_T
              and sign(spy_own['t']) == sign(primary.get('t')))
    if ok and spy_ok:
        return 'PREDICTABLE_FOLLOWS' if primary['t'] > 0 else 'PREDICTABLE_FADES'
    if not primary['control']['detected']:
        return 'UNDERPOWERED'
    return 'NULL'


# ── the panels ───────────────────────────────────────────────────────────────

def sector_days(names, sector_of):
    """[(date, mean over sectors of sign(sector so far) x sector after)]: a
    sector's move is the median over its names with all prices that session;
    a sector-session needs MIN_SECTOR names."""
    by = {}
    for t, pts in names.items():
        s = sector_of.get(t)
        if not s:
            continue
        for d, p in pts.items():
            by.setdefault(d, {}).setdefault(s, []).append((p['so_far'], p['after']))
    out = []
    for d, secs in sorted(by.items()):
        ys = []
        for s, xs in secs.items():
            if len(xs) < MIN_SECTOR:
                continue
            ys.append(sign(st.median(x for x, _ in xs)) * st.median(a for _, a in xs))
        if ys:
            out.append((d, st.mean(ys)))
    return out


def by_year(days):
    out = {}
    for d, p, a in days:
        out.setdefault(d[:4], []).append(sign(p) * a)
    return {y: {'sessions': len(v), 'mean_pct': round(st.mean(v), 4),
                't': (lambda t: None if t is None else round(t, 2))(t_stat(v))}
            for y, v in sorted(out.items())}


def ten_year(daily):
    """Descriptive: XIU's gap (prior close -> open) against its open -> close,
    FMP adjusted daily, 2015 -> END. Enters at the open, not 09:45."""
    rows = sorted(r for r in daily if r[0] <= END)
    days = []
    for a, b in zip(rows, rows[1:]):
        o, c, pc = b[1], b[4], a[4]
        if o > 0 and c > 0 and pc > 0:
            days.append((b[0], 100 * (o / pc - 1), 100 * (c / o - 1)))
    return arm(days)


def run(draws=DRAWS, seed=SEED):
    xiu = load(TSX_CACHE/f'{MARKET}.json')
    spy = load(CACHE/'SPY.json')
    sector_of = {t: v.get('sector') for t, v in load(SECTORS)['sectors'].items()}
    names = {}
    for f in sorted(TSX_CACHE.glob('*.json')):
        if f.stem == MARKET:
            continue
        d = load(f)
        names[d['ticker']] = session_points(d)
    X, S = session_points(xiu), session_points(spy)
    cal = sorted(X)
    left_out = {'xiu_bar_dates_in_window': sum(1 for d in xiu['bars'] if START <= d <= END),
                'sessions': len(cal)}
    left_out['xiu_without_prior_close_or_prices'] = left_out['xiu_bar_dates_in_window'] - len(cal)

    def xs(pred):
        return [(d, pred(d), X[d]['after']) for d in cal]

    primary = arm(xs(lambda d: X[d]['so_far']), draws=draws, seed=seed)
    spy_own = arm([(d, S[d]['so_far'], S[d]['after']) for d in sorted(S)], draws=draws, seed=seed)

    breadth = {}
    for d in cal:                       # the share of the 150 above their prior close
        up = [pts[d]['so_far'] > 0 for pts in names.values() if d in pts]
        breadth[d] = (sum(up) / len(up) - 0.5) if len(up) >= 50 else None
    sec = sector_days(names, sector_of)
    secondary = {
        'S1_first15': arm(xs(lambda d: X[d]['first15']), draws=draws, seed=seed),
        'S2_gap': arm(xs(lambda d: X[d]['gap']), draws=draws, seed=seed),
        'S3_spy_so_far': arm([(d, S[d]['so_far'] if d in S else None, X[d]['after']) for d in cal],
                             draws=draws, seed=seed),
        'S4_prior_session': arm(xs(lambda d: X[d]['prior']), draws=draws, seed=seed),
        'S5_breadth': arm(xs(lambda d: breadth[d]), draws=draws, seed=seed),
        'sector_arm': arm([(d, 1.0, y) for d, y in sec], draws=draws, seed=seed),
    }
    keys = list(secondary)
    adj = holm([secondary[k].get('placebo_p_two') for k in keys])
    for k, p in zip(keys, adj):
        secondary[k]['holm_p'] = p
        secondary[k]['a_lead'] = clears(secondary[k], p=p) if p is not None else False

    days = xs(lambda d: X[d]['so_far'])
    big = [(d, p, a) for d, p, a in days if abs(p) >= BIG]
    out = {
        'registration': 'PREREGISTER_day147c_market_direction.md',
        'window': [START, END], 'seed': seed, 'draws': draws,
        'bar': {'t': BAR_T, 'placebo_p': BAR_P, 'spy_t': SPY_T, 'cost_pct': COST, 'plant_pct': PLANT},
        'verdict': verdict(primary, spy_own),
        'primary': primary, 'spy_own': spy_own, 'secondary': secondary,
        'left_out': left_out,
        'spy_fetch': {'failed_calls': spy.get('failed_calls'), 'capped_calls': spy.get('capped_calls'),
                      'sessions': len(S)},
        'describe': {'by_year': by_year(days),
                     'big_mornings': arm(big, draws=draws, seed=seed),
                     'small_mornings': arm([x for x in days if abs(x[1]) < BIG], draws=draws, seed=seed),
                     'ten_year_daily_gap': ten_year(xiu['daily'])},
    }
    return out


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    p.add_argument('--fetch', action='store_true', help='download SPY; computes no return')
    a = p.parse_args(argv)
    if a.fetch:
        s = fetch_spy()
        print(json.dumps({'spy_bar_days': len(s['bars']), 'spy_eod_days': len(s['eod']),
                          'failed_calls': s['failed_calls'], 'capped_calls': s['capped_calls']}))
        return 0
    out = run()
    OUT.write_text(json.dumps(out, indent=1))
    pr, so = out['primary'], out['spy_own']
    print(f"VERDICT: {out['verdict']}")
    print(f"primary: {pr['sessions']} sessions, mean {pr['mean_pct']:+.3f}%, t {pr['t']}, "
          f"placebo p {pr['placebo_p_two']}, blocks {pr['blocks']}, hit {pr['hit_rate']}, "
          f"control t {pr['control']['t']}, MDE {pr['mde_pct']}%")
    print(f"SPY's own: {so['sessions']} sessions, mean {so['mean_pct']:+.3f}%, t {so['t']}")
    for k, v in out['secondary'].items():
        print(f"  {k}: n {v.get('sessions')}, mean {v.get('mean_pct')}, t {v.get('t')}, "
              f"p {v.get('placebo_p_two')}, Holm {v.get('holm_p')}, lead {v.get('a_lead')}")
    return 0


if __name__ == '__main__':
    sys.exit(main())
