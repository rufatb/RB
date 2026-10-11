#!/usr/bin/env python3
"""H1 of PREREGISTER_day130_learning.md: short-term (weekly) reversal in the pool.

Each session, every name's 5-session return to the prior close, minus its
sector's median, is ranked across the pool. Long the bottom fifth, short the
top fifth, entered at the next open and held `hold` sessions, rebalanced every
`hold` sessions so periods never overlap. 0.10% per side per name.

    python replay_reversal.py --bars DIR [--hold 5] [--out data/replay_day130_reversal.json]

DIR holds Yahoo chart JSON named <TICKER>_1d_2y.json (the day-130 cache).
Research only: nothing here is read by the morning.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import math
import random
import statistics as st
from pathlib import Path
from zoneinfo import ZoneInfo

ET = ZoneInfo('America/New_York')
ROOT = Path(__file__).resolve().parent
COST_PER_SIDE = 0.10          # % per name per side
LOOKBACK = 5
QUANTILE = 0.2


def load(bars_dir, tickers):
    """{ticker: {date: (open, close)}} from daily charts; missing files skipped."""
    out = {}
    for t in tickers:
        path = Path(bars_dir) / ('%s_1d_2y.json' % t)
        if not path.is_file():
            continue
        d = json.loads(path.read_text())
        q = d['indicators']['quote'][0]
        rows = {}
        for i, ts in enumerate(d['timestamp']):
            o, c = q['open'][i], q['close'][i]
            if o and c and o > 0 and c > 0:
                rows[dt.datetime.fromtimestamp(ts, ET).date()] = (float(o), float(c))
        out[t] = rows
    return out


def periods(data, sectors, *, hold=5, lookback=LOOKBACK, quantile=QUANTILE, start_offset=0):
    """[(entry_date, long_mean, short_mean, n_names)] over non-overlapping periods."""
    days = sorted({d for rows in data.values() for d in rows})
    out = []
    i = lookback + 1 + start_offset
    while i + hold - 1 < len(days):
        prev, base, entry_d, exit_d = days[i - 1], days[i - 1 - lookback], days[i], days[i + hold - 1]
        sig, fwd = {}, {}
        for t, rows in data.items():
            if all(d in rows for d in (prev, base, entry_d, exit_d)):
                sig[t] = rows[prev][1] / rows[base][1] - 1
                fwd[t] = (rows[exit_d][1] / rows[entry_d][0] - 1) * 100
        if len(sig) >= 25:
            by_sector = {}
            for t, v in sig.items():
                by_sector.setdefault(sectors.get(t) or '?', []).append(v)
            pool_med = st.median(sig.values())
            rel = {t: v - (st.median(by_sector[sectors.get(t) or '?'])
                           if len(by_sector[sectors.get(t) or '?']) >= 3 else pool_med)
                   for t, v in sig.items()}
            ranked = sorted(rel, key=rel.get)
            k = max(1, int(len(ranked) * quantile))
            losers, winners = ranked[:k], ranked[-k:]
            out.append((entry_d, st.mean(fwd[t] for t in losers), st.mean(fwd[t] for t in winners),
                        len(ranked), {t: rel[t] for t in ranked}, fwd))
        i += hold
    return out


def spreads(rows, cost=COST_PER_SIDE):
    """Net long-losers minus short-winners return per period, in %."""
    return [(d, lo - wi - 4 * cost) for d, lo, wi, *_ in rows]


def tstat(vals):
    if len(vals) < 3:
        return float('nan')
    sd = st.stdev(vals)
    return st.mean(vals) / (sd / math.sqrt(len(vals))) if sd > 0 else float('nan')


def quarters(sp):
    by = {}
    for d, v in sp:
        by.setdefault('%dQ%d' % (d.year, (d.month - 1) // 3 + 1), []).append(v)
    return {q: (round(st.mean(v), 3), len(v)) for q, v in sorted(by.items())}


def placebo(rows, *, draws=1000, seed=7, quantile=QUANTILE, cost=COST_PER_SIDE):
    """Shuffle the signal across names within each period; p of a mean as large."""
    rng = random.Random(seed)
    real = st.mean(v for _, v in spreads(rows, cost))
    beat = 0
    for _ in range(draws):
        vals = []
        for d, _, _, n, rel, fwd in rows:
            names = list(rel)
            rng.shuffle(names)
            k = max(1, int(len(names) * quantile))
            vals.append(st.mean(fwd[t] for t in names[:k]) - st.mean(fwd[t] for t in names[-k:]) - 4 * cost)
        beat += st.mean(vals) >= real
    return (beat + 1) / (draws + 1)


def control(sp, edge=0.5):
    """House rule 10: the planted edge's own t, edge / se of the real spreads."""
    vals = [v for _, v in sp]
    se = st.stdev(vals) / math.sqrt(len(vals))
    return {'planted_edge_pct': edge, 't_of_planted_edge': round(edge / se, 2),
            'detected': edge / se >= 3.0, 'mde_80pct_at_t3': round(3.84 * se, 3)}


def run(bars_dir, *, hold=5):
    sectors = {t: v.get('sector') for t, v in
               json.loads((ROOT/'data'/'tsx_sectors.json').read_text())['sectors'].items()}
    data = load(bars_dir, sectors)
    rows = periods(data, sectors, hold=hold)
    sp = spreads(rows)
    gross = [lo - wi for _, lo, wi, *_ in rows]
    vals = [v for _, v in sp]
    q = quarters(sp)
    last4 = list(q.values())[-4:]
    out = {'test': 'day130-H1-reversal', 'hold_sessions': hold, 'names_loaded': len(data),
           'periods': len(rows), 'first': str(rows[0][0]) if rows else None,
           'last': str(rows[-1][0]) if rows else None,
           'gross_mean_pct': round(st.mean(gross), 3), 'net_mean_pct': round(st.mean(vals), 3),
           'net_t': round(tstat(vals), 2), 'hit': round(sum(v > 0 for v in vals) / len(vals), 3),
           'long_losers_mean_pct': round(st.mean(lo for _, lo, *_ in rows), 3),
           'short_winners_mean_pct': round(st.mean(wi for _, _, wi, *_ in rows), 3),
           'quarters': q, 'last_four_same_sign': (len(last4) == 4 and
                                                   len({m > 0 for m, _ in last4}) == 1),
           'placebo_p': placebo(rows), 'control': control(sp),
           'survivorship': 'the pool is today\'s names; delisted names are absent'}
    out['passes'] = (out['net_t'] >= 3 and out['last_four_same_sign'] and out['placebo_p'] < 0.01
                     and out['control']['detected'] and out['net_mean_pct'] > 0)
    return out


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--bars', required=True)
    p.add_argument('--hold', type=int, default=5)
    p.add_argument('--out')
    a = p.parse_args(argv)
    res = run(a.bars, hold=a.hold)
    print(json.dumps(res, indent=1))
    if a.out:
        Path(a.out).write_text(json.dumps(res, indent=1) + '\n')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
