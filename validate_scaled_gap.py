#!/usr/bin/env python3
"""The registered test in PREREGISTER_day113_scaled_gap.md. Nothing here is tuned.

Is a gap large RELATIVE TO THE NAME'S NORMAL MOVE informative about the same
session's open-to-close direction? Session-clustered, four quarters, placebo,
and a planted positive control run through the identical harness.
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent
THRESHOLD = 1.0          # |g| >= one normal day's move — registered
SD_WINDOW = 20
PLACEBO_DRAWS = 2000
CONTROL_EDGE_SD = 0.10   # planted continuation, in units of sd20_prev
COST_PCT = 0.10          # 10 bp round trip
T_BAR = 3.0


def load(path=ROOT / 'data' / 'tsx_daily.csv'):
    df = pd.read_csv(path, parse_dates=['date']).sort_values(['t', 'date'])
    df['sd20_prev'] = (df.groupby('t')['daily']
                         .transform(lambda s: s.rolling(SD_WINDOW, min_periods=SD_WINDOW).std().shift(1)))
    df = df.dropna(subset=['sd20_prev', 'overnight', 'intraday'])
    df = df[df['sd20_prev'] > 0]
    df['g'] = df['overnight'] / df['sd20_prev']
    return df


def clustered(frame, value):
    """t over SESSIONS: each session's mean of `value` is one observation."""
    daily = frame.groupby('date')[value].mean()
    n = len(daily)
    if n < 3:
        return {'mean': None, 't': None, 'sessions': n}
    sd = float(daily.std(ddof=1))
    mean = float(daily.mean())
    return {'mean': mean, 't': mean / (sd / math.sqrt(n)) if sd > 0 else None, 'sessions': n}


def run(df, *, seed=113):
    q = df[df['g'].abs() >= THRESHOLD].copy()
    q['s'] = np.sign(q['g']) * q['intraday']
    full = clustered(q, 's')

    sessions = np.sort(q['date'].unique())
    quarters = []
    for chunk in np.array_split(sessions, 4):
        part = q[q['date'].isin(chunk)]
        r = clustered(part, 's')
        quarters.append({'from': str(pd.Timestamp(chunk[0]).date()),
                         'to': str(pd.Timestamp(chunk[-1]).date()), **r})

    rng = np.random.default_rng(seed)
    placebo = []
    for _ in range(PLACEBO_DRAWS):
        signs = rng.choice([-1.0, 1.0], size=len(q))
        placebo.append(float((pd.Series(signs * q['intraday'].to_numpy(), index=q.index)
                              .groupby(q['date']).mean()).mean()))
    placebo = np.array(placebo)
    p_two = float((np.abs(placebo) >= abs(full['mean'])).mean())

    control = q.copy()
    control['s'] = np.sign(control['g']) * (control['intraday']
                                             + np.sign(control['g']) * CONTROL_EDGE_SD * control['sd20_prev'])
    detected = clustered(control, 's')

    same_sign = all(x['mean'] is not None and np.sign(x['mean']) == np.sign(full['mean'])
                    for x in quarters)
    checks = {
        't_at_least_3': full['t'] is not None and abs(full['t']) >= T_BAR,
        'same_sign_all_four_quarters': bool(same_sign),
        'placebo_p_below_0.01': p_two < 0.01,
        'beats_10bp_cost': full['mean'] is not None and abs(full['mean']) > COST_PCT,
        'positive_control_detected': detected['t'] is not None and detected['t'] >= T_BAR,
    }
    if not checks['positive_control_detected']:
        verdict = 'UNDERPOWERED — the harness could not detect a planted edge; no null may be reported'
    elif all(checks.values()):
        verdict = ('PASSED — ' + ('continuation' if full['mean'] > 0 else 'fade')
                   + '; licenses a shadow, unsized, forward-scored line only')
    else:
        verdict = 'REJECTED — a powered negative: failed ' + ', '.join(k for k, v in checks.items() if not v)
    return {'registration': 'PREREGISTER_day113_scaled_gap.md',
            'rows': int(len(df)), 'qualifying_rows': int(len(q)),
            'names': int(q['t'].nunique()),
            'span': [str(df['date'].min().date()), str(df['date'].max().date())],
            'full': full, 'quarters': quarters,
            'placebo': {'draws': PLACEBO_DRAWS, 'p_two_sided': p_two,
                        'p99_5_abs': float(np.quantile(np.abs(placebo), 0.995))},
            'positive_control': {'edge_sd': CONTROL_EDGE_SD, **detected},
            'checks': checks, 'verdict': verdict,
            'proxy': 'open-to-close daily bars; sd20 of close-to-close returns, not a true ATR'}


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    p.add_argument('--output', default=str(ROOT / 'data' / 'day113_scaled_gap.json'))
    a = p.parse_args(argv)
    result = run(load())
    Path(a.output).write_text(json.dumps(result, indent=1))
    print(json.dumps(result, indent=1))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
