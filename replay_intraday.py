#!/usr/bin/env python3
"""H5 and H6 of PREREGISTER_day130_learning.md (amendment 1).

H5  intraday momentum: the 09:30 -> 10:00 return's sign, traded 15:25 -> 15:55,
    for names whose signal is beyond +/-0.25%, net of 0.10% per side.
H6  intraday vs overnight drift: per-session mean open -> close and close ->
    next open across the pool, two years of daily bars.

    python replay_intraday.py --bars DIR [--out data/replay_day130_intraday.json]

DIR holds Yahoo chart JSON <TICKER>_5m_60d.json and <TICKER>_1d_2y.json.
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
COST_PER_SIDE = 0.10
THRESHOLD = 0.25


def _quote(d):
    return d['indicators']['quote'][0]


def five_minute(path):
    """{date: {time: (open, close)}} regular session only."""
    d = json.loads(Path(path).read_text())
    q = _quote(d)
    out = {}
    for i, ts in enumerate(d['timestamp']):
        o, c = q['open'][i], q['close'][i]
        if o is None or c is None or o <= 0 or c <= 0:
            continue
        t = dt.datetime.fromtimestamp(ts, ET)
        out.setdefault(t.date(), {})[t.time()] = (float(o), float(c))
    return out


def daily(path):
    d = json.loads(Path(path).read_text())
    q = _quote(d)
    out = {}
    for i, ts in enumerate(d['timestamp']):
        o, c = q['open'][i], q['close'][i]
        if o and c and o > 0 and c > 0:
            out[dt.datetime.fromtimestamp(ts, ET).date()] = (float(o), float(c))
    return out


def clustered(pairs):
    """Mean and session-clustered t of [(session, value)]."""
    by = {}
    for s, v in pairs:
        by.setdefault(s, []).append(v)
    n = sum(len(v) for v in by.values())
    if len(by) < 3 or n == 0:
        return float('nan'), float('nan'), len(by), n
    m = sum(sum(v) for v in by.values()) / n
    k = len(by)
    var = sum((sum(v) - m * len(v)) ** 2 for v in by.values()) * k / (k - 1) / n ** 2
    return m, (m / math.sqrt(var) if var > 0 else float('nan')), k, n


def h5(bars_dir, tickers, *, draws=500, seed=11):
    t0, t1 = dt.time(9, 30), dt.time(9, 55)            # 09:30 open -> 10:00 (09:55 bar close)
    l0, l1 = dt.time(15, 25), dt.time(15, 55)           # 15:25 open -> 15:55 bar close
    obs = []
    for t in tickers:
        path = Path(bars_dir) / ('%s_5m_60d.json' % t)
        if not path.is_file():
            continue
        for day, bars in five_minute(path).items():
            if all(x in bars for x in (t0, t1, l0, l1)):
                sig = (bars[t1][1] / bars[t0][0] - 1) * 100
                last = (bars[l1][1] / bars[l0][0] - 1) * 100
                obs.append((day, t, sig, last))
    trades = [(d, (1 if s > 0 else -1) * last - 2 * COST_PER_SIDE)
              for d, _, s, last in obs if abs(s) > THRESHOLD]
    gross = [(d, (1 if s > 0 else -1) * last) for d, _, s, last in obs if abs(s) > THRESHOLD]
    m, t_, k, n = clustered(trades)
    gm, gt, _, _ = clustered(gross)
    months = {}
    for d, v in trades:
        months.setdefault(d.strftime('%Y-%m'), []).append(v)
    rng = random.Random(seed)
    by_day = {}
    for d, tk, s, last in obs:
        by_day.setdefault(d, []).append((s, last))
    beat = 0
    for _ in range(draws):
        vals = []
        for d, rows in by_day.items():
            sigs = [s for s, _ in rows]
            rng.shuffle(sigs)
            vals += [(1 if s > 0 else -1) * last - 2 * COST_PER_SIDE
                     for s, (_, last) in zip(sigs, rows) if abs(s) > THRESHOLD]
        beat += (st.mean(vals) if vals else 0) >= m
    full = [(d, (1 if s > 0 else -1) * last) for d, _, s, last in obs if s != 0]
    corr_m, corr_t, _, _ = clustered(full)
    out = {'name_days': len(obs), 'trades': n, 'sessions': k,
           'gross_mean_pct': round(gm, 4), 'gross_t': round(gt, 2),
           'net_mean_pct': round(m, 4), 'net_t': round(t_, 2),
           'all_name_days_signed_last_half_hour_pct': round(corr_m, 4), 'all_name_days_t': round(corr_t, 2),
           'months': {mo: (round(st.mean(v), 4), len(v)) for mo, v in sorted(months.items())},
           'placebo_p': round((beat + 1) / (draws + 1), 4)}
    mo = [v for v, _ in out['months'].values()]
    out['passes'] = (out['net_t'] >= 3 and len(mo) >= 3 and all(x > 0 for x in mo)
                     and out['placebo_p'] < 0.01)
    return out


def h6(bars_dir, tickers):
    per = {}
    for t in tickers:
        path = Path(bars_dir) / ('%s_1d_2y.json' % t)
        if not path.is_file():
            continue
        rows = daily(path)
        days = sorted(rows)
        for i in range(1, len(days)):
            d, p = days[i], days[i - 1]
            o, c = rows[d]
            per.setdefault(d, {'intraday': [], 'overnight': []})
            per[d]['intraday'].append((c / o - 1) * 100)
            per[d]['overnight'].append((o / rows[p][1] - 1) * 100)
    sess = sorted(d for d in per if len(per[d]['intraday']) >= 25)
    intra = [st.mean(per[d]['intraday']) for d in sess]
    over = [st.mean(per[d]['overnight']) for d in sess]

    def t_of(v):
        return st.mean(v) / (st.stdev(v) / math.sqrt(len(v)))
    quarters = {}
    for d, v in zip(sess, intra):
        quarters.setdefault('%dQ%d' % (d.year, (d.month - 1) // 3 + 1), []).append(v)
    q = {k: (round(st.mean(v), 4), len(v)) for k, v in sorted(quarters.items())}
    last4 = [m for m, n in list(q.values())[-5:] if n >= 20][-4:]
    out = {'sessions': len(sess), 'first': str(sess[0]), 'last': str(sess[-1]),
           'intraday_mean_pct': round(st.mean(intra), 4), 'intraday_t': round(t_of(intra), 2),
           'overnight_mean_pct': round(st.mean(over), 4), 'overnight_t': round(t_of(over), 2),
           'quarters_intraday': q}
    out['passes'] = out['intraday_t'] <= -3 and len(last4) == 4 and all(m < 0 for m in last4)
    return out


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--bars', required=True)
    p.add_argument('--out')
    a = p.parse_args(argv)
    tickers = sorted(json.loads((ROOT/'data'/'tsx_sectors.json').read_text())['sectors'])
    res = {'test': 'day130-H5-H6', 'H5_intraday_momentum': h5(a.bars, tickers),
           'H6_intraday_vs_overnight': h6(a.bars, tickers)}
    print(json.dumps(res, indent=1))
    if a.out:
        Path(a.out).write_text(json.dumps(res, indent=1) + '\n')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
