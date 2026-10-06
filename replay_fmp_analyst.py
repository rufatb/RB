#!/usr/bin/env python3
"""The day-125 registered test: does an analyst rating change move a TSX stock
from 09:45 to the close, against the market?  (PREREGISTER_day125_fmp.md)

    python replay_fmp_analyst.py            # writes data/replay_day125_analyst.json

Population: the morning pool's TSX names; every FMP upgrade/downgrade dated
2024-01-02 … 2026-10-02. Outcome: sign × (name − XIU.TO), 09:40-bar close →
15:55-bar close, on the rating's session (D) — the scoreboard's yardstick.
Bar: mean > 0, session-clustered t ≥ 3 AND placebo p < 0.05. Identical
(name, session, sign) rows from several firms count once; a name with both
signs on one session is dropped. Both are disclosed in the output.
"""
from __future__ import annotations

import concurrent.futures as cf
import datetime as dt
import json
import math
import random
import sys
from pathlib import Path

import fmp_client as F

START, END = '2024-01-02', '2026-10-02'
OUT = Path(__file__).with_name('data')/'replay_day125_analyst.json'
PLANTED = 0.5
DRAWS = 2000
ENTRY, EXIT, OPEN = '09:40:00', '15:55:00', '09:30:00'


def pool_tickers(state_dir='.rb-state'):
    d = json.loads((Path(state_dir)/'deepseek_candidates.json').read_text())
    return sorted(c['ticker'] for c in d['candidates'] if c['ticker'].endswith('.TO'))


def sessions(bars):
    """{date: {'open', 'c0945', 'close'}} from FMP 5-min rows (any order)."""
    by = {}
    for b in bars or []:
        d, t = b['date'].split(' ')
        by.setdefault(d, {})[t] = b
    out = {}
    for d, bs in by.items():
        if ENTRY in bs and EXIT in bs and OPEN in bs:
            out[d] = {'open': bs[OPEN]['open'], 'c0945': bs[ENTRY]['close'], 'close': bs[EXIT]['close']}
    return out


def window(day):
    d = dt.date.fromisoformat(day)
    return (d - dt.timedelta(days=10)).isoformat(), (d + dt.timedelta(days=2)).isoformat()


def returns(s, prev):
    r = {'r945': 100 * (s['close'] / s['c0945'] - 1), 'open_945': 100 * (s['c0945'] / s['open'] - 1)}
    if prev:
        r['gap'] = 100 * (s['open'] / prev['close'] - 1)
    return r


def clustered(xs):
    """(mean, se, t) with session clusters: xs = [(session, value)]."""
    n = len(xs)
    if n < 2:
        return None, None, None
    mean = sum(v for _, v in xs) / n
    groups = {}
    for g, v in xs:
        groups[g] = groups.get(g, 0.0) + (v - mean)
    G = len(groups)
    var = sum(s * s for s in groups.values()) / n ** 2 * (G / (G - 1) if G > 1 else 1)
    se = math.sqrt(var)
    return mean, se, (mean / se if se else None)


def run(tickers, *, get=F.get):
    with cf.ThreadPoolExecutor(8) as pool:
        grades = dict(zip(tickers, pool.map(lambda t: get('grades', symbol=t), tickers)))
    raw = [(t, g['date'], 1 if g['action'] == 'upgrade' else -1)
           for t, gs in grades.items() for g in gs or []
           if g.get('action') in ('upgrade', 'downgrade') and START <= g.get('date', '') <= END]
    by_key = {}
    for t, d, s in raw:
        by_key.setdefault((t, d), set()).add(s)
    events = [(t, d, next(iter(s))) for (t, d), s in sorted(by_key.items()) if len(s) == 1]
    conflicted = sum(1 for s in by_key.values() if len(s) > 1)

    ranges = {window(d) for _, d, _ in events}
    with cf.ThreadPoolExecutor(8) as pool:
        xiu = dict(zip(ranges, pool.map(
            lambda r: sessions(get('historical-chart/5min', symbol='XIU.TO', **{'from': r[0], 'to': r[1]})),
            ranges)))
        bars = list(pool.map(lambda e: sessions(get('historical-chart/5min', symbol=e[0],
                                                    **dict(zip(('from', 'to'), window(e[1]))))), events))
    rows, placebo_pool, dropped = [], [], 0
    event_days = {(t, d) for t, d, _ in events}
    for (t, d, sign), s in zip(events, bars):
        m = xiu[window(d)]
        days = sorted(x for x in s if x in m)
        after = [x for x in days if x >= d]
        if not after:
            dropped += 1
            continue
        D = after[0]
        i = days.index(D)

        def signed(day):
            j = days.index(day)
            a = returns(s[day], s[days[j - 1]] if j else None)
            b = returns(m[day], m[days[j - 1]] if j else None)
            out = {k: sign * (a[k] - b[k]) for k in a if k in b}
            return out
        row = {'ticker': t, 'date': d, 'session': D, 'sign': sign, **{k: round(v, 4) for k, v in signed(D).items()}}
        if i + 1 < len(days):
            row['d1_r945'] = round(signed(days[i + 1])['r945'], 4)
        rows.append(row)
        placebo_pool.append([signed(x)['r945'] for x in days[:i]
                             if x != D and (t, x) not in event_days])
    return rows, placebo_pool, {'raw_changes': len(raw), 'events': len(events),
                                'same_day_conflicts_dropped': conflicted,
                                'no_bars_dropped': dropped}


def summarize(rows, placebo_pool, counts, *, seed=125):
    prim = [(r['session'], r['r945']) for r in rows]
    mean, se, t = clustered(prim)
    rng = random.Random(seed)
    usable = [p for p in placebo_pool if p]
    draws = []
    for _ in range(DRAWS):
        vals = [rng.choice(p) for p in usable]
        draws.append(sum(vals) / len(vals))
    p = (sum(1 for x in draws if x >= mean) + 1) / (DRAWS + 1) if mean is not None else None

    def stat(key, sub=rows):
        xs = [(r['session'], r[key]) for r in sub if key in r]
        m, s, tt = clustered(xs)
        return {'n': len(xs), 'mean_pct': None if m is None else round(m, 4),
                't': None if tt is None else round(tt, 2),
                'hit': None if not xs else round(sum(1 for _, v in xs if v > 0) / len(xs), 3)}
    passed = bool(mean is not None and mean > 0 and t is not None and t >= 3.0 and p < 0.05)
    planted_t = round(PLANTED / se, 2) if se else None
    return {
        'registration': 'PREREGISTER_day125_fmp.md', 'window': [START, END], **counts,
        'used': len(rows), 'sessions': len({r['session'] for r in rows}),
        'primary': {**stat('r945'), 'placebo_p': None if p is None else round(p, 4)},
        'planted_t_at_0.5pct': planted_t,
        'verdict': ('PASS' if passed else
                    'UNDERPOWERED' if planted_t is not None and planted_t < 3 else 'FAIL'),
        'gap': stat('gap'), 'open_to_0945': stat('open_945'), 'd_plus_1': stat('d1_r945'),
        'upgrades': stat('r945', [r for r in rows if r['sign'] > 0]),
        'downgrades': stat('r945', [r for r in rows if r['sign'] < 0]),
    }


def prompt_line(summary):
    """The one sentence the prompt carries about analyst_30d (registered use)."""
    p, g = summary['primary'], summary['gap']
    if summary['verdict'] == 'PASS':
        head = 'a registered test found same-day drift after a rating change'
    else:
        head = 'a registered test found NO reliable same-day drift after a rating change'
    return ('%s: %d TSX changes 2024–2026, 09:45 to close against the market %+.2f%% '
            '(t = %.1f, placebo p = %.2f); the open had already moved %+.2f%% its way (t = %.1f).'
            % (head, p['n'], p['mean_pct'], p['t'], p['placebo_p'], g['mean_pct'], g['t']))


def main(argv=None):
    tickers = pool_tickers()
    rows, placebo, counts = run(tickers)
    summary = summarize(rows, placebo, counts)
    summary['universe'] = tickers
    summary['prompt_line'] = prompt_line(summary)
    OUT.write_text(json.dumps({**summary, 'rows': rows}, indent=1) + '\n')
    print(json.dumps({k: v for k, v in summary.items() if k != 'universe'}, indent=1))
    return 0


if __name__ == '__main__':
    sys.exit(main())
