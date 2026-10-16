#!/usr/bin/env python3
"""Day-135d — after a broad big-move day, do the movers turn back?

Registered first: PREREGISTER_day135d_breadth.md. A broad day is one when an
unusually large share of the 150 names moved >= 1 ATR (top decile of the 250
sessions before it). The test asks whether those movers continue or reverse
over the next session's open -> close, raw (the owner's book) and against XIU.

Data: day-135c's daily panel (risk_rules.Daily), FMP dividend-adjusted bars
for the 150 names, 2016-01-04 -> 2026-10-14, from the day-135b cache.

    python breadth_reversal.py        # writes data/breadth_day135d.json
"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import numpy as np

import replay_weeks as W
import risk_rules as R

ROOT = Path(__file__).resolve().parent
OUT = ROOT/'data'/'breadth_day135d.json'
MOVER = 1.0
BROAD_Q = 0.90
WINDOW = 250
MIN_NAMES = 50
PLANT = -0.30
DRAWS, SEED = 1000, 135
BAR_T = 3.0


def breadth(d):
    """B[i]: the share of names whose move on session i-1 (seen at D = i) was
    >= 1 ATR, among names with a valid move; and the mover mask."""
    ok = ~np.isnan(d.m)
    n = ok.sum(axis=0)
    movers = ok & (np.abs(np.where(ok, d.m, 0.0)) >= MOVER)
    B = np.where(n >= MIN_NAMES, movers.sum(axis=0) / np.maximum(n, 1), np.nan)
    return B, movers


def broad_days(B):
    """Causal labels: broad[i] when B[i] >= the 90th percentile of the WINDOW
    breadths before it (sessions strictly before D-1); eligible[i] when that
    threshold exists."""
    s = len(B)
    broad = np.zeros(s, dtype=bool)
    eligible = np.zeros(s, dtype=bool)
    thr = np.full(s, np.nan)
    for i in range(s):
        if np.isnan(B[i]):
            continue
        past = B[max(0, i - WINDOW):i]
        past = past[~np.isnan(past)]
        if len(past) < WINDOW:
            continue
        thr[i] = float(np.quantile(past, BROAD_Q))
        eligible[i] = True
        broad[i] = B[i] >= thr[i]
    return broad, eligible, thr


def clustered(values, groups):
    if len(values) < 2:
        return {'n': int(len(values)), 'mean': None, 'se': None, 't': None}
    mean, se, t = R.clustered_t(values, groups)
    return {'n': int(len(values)), 'sessions': int(len(set(np.asarray(groups).tolist()))),
            'mean': mean, 'se': se, 't': t, 'median': float(np.median(values))}


def population(d, movers, mask_sessions, y):
    """(values, session ids) of y over the movers on the masked sessions."""
    rows, cols = np.nonzero(movers & mask_sessions[None, :] & ~np.isnan(y))
    return y[rows, cols], cols


def placebo(y, movers, eligible, k, observed, rng):
    """Relabel k broad sessions among eligible sessions that have movers."""
    valid = movers & ~np.isnan(y)
    S = np.where(valid, y, 0.0).sum(axis=0)
    N = valid.sum(axis=0)
    pool = np.nonzero(eligible & (N > 0))[0]
    hits = 0
    for _ in range(DRAWS):
        pick = rng.choice(pool, size=k, replace=False)
        m = S[pick].sum() / N[pick].sum()
        hits += abs(m) >= abs(observed)
    return hits / DRAWS


def blocks(values, sessions, nblocks=4):
    order = sorted(set(sessions.tolist()))
    edges = np.array_split(np.array(order), nblocks)
    out = []
    for e in edges:
        m = np.isin(sessions, e)
        out.append(float(values[m].mean()) if m.any() else None)
    return out


def verdict(stats, p, blk, control_t):
    mean, t, med = stats['mean'], stats['t'], stats['median']
    if mean is None or t is None:
        return 'UNDERPOWERED'
    if mean < 0 and t <= -BAR_T and p < 0.01 and sum(b is not None and b < 0 for b in blk) >= 3 and med < 0:
        return 'REVERSAL'
    if mean > 0 and t >= BAR_T and p < 0.01 and sum(b is not None and b > 0 for b in blk) >= 3 and med > 0:
        return 'CONTINUATION'
    return 'NULL' if control_t is not None and control_t <= -BAR_T else 'UNDERPOWERED'


def run(d):
    B, movers = breadth(d)
    broad, eligible, thr = broad_days(B)
    sign = np.sign(d.m)
    out = {'broad_sessions': int(broad.sum()), 'eligible_sessions': int(eligible.sum()),
           'breadth_median_all': float(np.nanmedian(B[eligible])),
           'breadth_median_broad': float(np.nanmedian(B[broad])),
           'threshold_median': float(np.nanmedian(thr[eligible]))}
    rng = np.random.default_rng(SEED)
    for name, y in (('raw', sign * d.r), ('vs_xiu', sign * d.adj)):
        vp, sp = population(d, movers, broad, y)
        vc, sc = population(d, movers, eligible & ~broad, y)
        sP, sC = clustered(vp, sp), clustered(vc, sc)
        diff = sP['mean'] - sC['mean']
        se_d = math.sqrt(sP['se'] ** 2 + sC['se'] ** 2)
        p = placebo(y, movers, eligible, int(broad.sum()), sP['mean'], rng)
        blk = blocks(vp, sp)
        control_t = PLANT / sP['se'] if sP['se'] else None
        out[name] = {'after_broad_days': sP, 'after_other_days': sC,
                     'difference': {'mean': diff, 'se': se_d, 't': diff / se_d if se_d else None},
                     'placebo_p': p, 'blocks': blk,
                     'control': {'planted_pct': PLANT, 't_planted': control_t,
                                 'mde80_pct': (BAR_T + 0.84) * sP['se']},
                     'verdict': verdict(sP, p, blk, control_t)}
    # Descriptive: broad DOWN days and broad UP days apart (direction = the
    # sign of the median move among that session's movers).
    direction = np.zeros(len(B))
    for i in np.nonzero(broad)[0]:
        mv = d.m[movers[:, i], i]
        direction[i] = np.sign(np.median(mv)) if len(mv) else 0
    split = {}
    for label, dirv in (('after a broad DOWN day', -1), ('after a broad UP day', 1)):
        mask = broad & (direction == dirv)
        vp, sp = population(d, movers, mask, sign * d.r)
        split[label] = {'sessions': int(mask.sum()), **clustered(vp, sp)}
        # within those, the movers that went WITH the day's direction vs against
        rows, cols = np.nonzero(movers & mask[None, :] & ~np.isnan(d.r))
        with_dir = np.sign(d.m[rows, cols]) == dirv
        y = (sign * d.r)[rows, cols]
        split[label]['movers_with_the_day'] = clustered(y[with_dir], cols[with_dir])
        split[label]['movers_against_the_day'] = clustered(y[~with_dir], cols[~with_dir])
    out['split_by_direction'] = split
    # The market itself after a broad day, signed by the day's direction.
    idx = np.nonzero(broad & (direction != 0) & ~np.isnan(d.mr))[0]
    ym = direction[idx] * d.mr[idx]
    se = float(np.std(ym, ddof=1) / math.sqrt(len(ym))) if len(ym) > 1 else None
    out['market'] = {'n': int(len(ym)), 'mean': float(ym.mean()) if len(ym) else None, 'se': se,
                     't': float(ym.mean() / se) if se else None,
                     'mde80_pct': (BAR_T + 0.84) * se if se else None,
                     'reading': "XIU open -> close on D, signed by D-1's direction; + continues, - turns back"}
    return out


def main():
    from replay_drift import Fetch
    fetch = W.robust(Fetch(W.CACHE))
    tickers, _ = W.names()
    d = R.Daily(fetch, tickers)
    res = run(d)
    out = {'registered': 'PREREGISTER_day135d_breadth.md', 'window': [d.cal[0], d.cal[-1]],
           'sessions': len(d.cal), 'names': len(d.tickers), 'fetch_failures': fetch.failures, **res}
    OUT.write_text(json.dumps(out, indent=1, sort_keys=True))
    print(json.dumps(out, indent=1, sort_keys=True))
    return 0


if __name__ == '__main__':
    sys.exit(main())
