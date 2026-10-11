#!/usr/bin/env python3
"""H7 and H8 of PREREGISTER_day130_learning.md (amendment 2), on the replay picks.

H7  meta-labelling: a ridge logistic model, leave-one-session-out, predicts
    whether a pick is right from model, side, confidence, the gap the pick's
    way, the market's gap the pick's way, signed move_atr and atr_pct.
H8  volatility sizing: per session, equal weights vs 1/ATR weights.

    python replay_metalabel.py --rows ROWS.json --replay .rb-state/replay [--out FILE]

ROWS.json is the day-130 execution lab's replay rows (one per pick, with the
session, side, ticker, kind, conf, r, r_gap). Research only.
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

import numpy as np

ET = ZoneInfo('America/New_York')


def _daily(path):
    d = json.loads(Path(path).read_text())
    q = d['indicators']['quote'][0]
    return {dt.datetime.fromtimestamp(ts, ET).date(): (q['open'][i], q['close'][i])
            for i, ts in enumerate(d['timestamp']) if q['open'][i] and q['close'][i]}


def features(rows, replay):
    panel = {(p['session'], p['ticker']): p for p in json.loads((Path(replay)/'panel.json').read_text())}
    xiu = _daily(Path(replay)/'raw'/'XIU.TO_1d_2y.json')
    days = sorted(xiu)
    X, y, r, sess, atr = [], [], [], [], []
    for row in rows:
        d = dt.date.fromisoformat(row['session'])
        prev = [k for k in days if k < d]
        if d not in xiu or not prev:
            continue
        s = 1 if row['side'] == 'LONG' else -1
        mkt_gap = s * (xiu[d][0] / xiu[prev[-1]][1] - 1) * 100
        p = panel.get((row['session'], row['ticker'])) or {}
        if p.get('atr_pct') is None or p.get('move_atr') is None or row.get('r_gap') is None:
            continue
        X.append([1.0, float(row['kind'] == 'jev_forced'), float(s > 0), float(row['conf'] or 0.5),
                  float(row['r_gap'] > 0), float(mkt_gap > 0), s * p['move_atr'], p['atr_pct']])
        y.append(1.0 if row['r'] > 0 else 0.0)
        r.append(row['r'])
        sess.append(row['session'])
        atr.append(p['atr_pct'])
    return np.array(X), np.array(y), np.array(r), sess, np.array(atr)


def fit(X, y, l2=1.0, iters=50):
    """Ridge logistic regression by Newton steps; the intercept is not penalised."""
    mu, sd = X[:, 1:].mean(0), X[:, 1:].std(0) + 1e-9
    Z = np.hstack([X[:, :1], (X[:, 1:] - mu) / sd])
    w = np.zeros(Z.shape[1])
    pen = np.eye(Z.shape[1]) * l2
    pen[0, 0] = 0
    for _ in range(iters):
        p = 1 / (1 + np.exp(-Z @ w))
        g = Z.T @ (p - y) + pen @ w
        H = (Z * (p * (1 - p))[:, None]).T @ Z + pen
        w -= np.linalg.solve(H, g)
    return w, mu, sd


def predict(model, X):
    w, mu, sd = model
    Z = np.hstack([X[:, :1], (X[:, 1:] - mu) / sd])
    return 1 / (1 + np.exp(-Z @ w))


def auc(scores, labels):
    order = np.argsort(scores)
    ranks = np.empty(len(scores))
    ranks[order] = np.arange(1, len(scores) + 1)
    pos = labels == 1
    n1, n0 = pos.sum(), (~pos).sum()
    return float((ranks[pos].sum() - n1 * (n1 + 1) / 2) / (n1 * n0)) if n1 and n0 else float('nan')


def loso(X, y, sess):
    pred = np.zeros(len(y))
    for s in sorted(set(sess)):
        test = np.array([x == s for x in sess])
        pred[test] = predict(fit(X[~test], y[~test]), X[test])
    return pred


def clustered_diff(keep, r, sess):
    """Mean of kept minus dropped, t clustered by session (per-session differences)."""
    diffs = []
    for s in sorted(set(sess)):
        idx = [i for i, x in enumerate(sess) if x == s]
        k = [r[i] for i in idx if keep[i]]
        d = [r[i] for i in idx if not keep[i]]
        if k and d:
            diffs.append(st.mean(k) - st.mean(d))
    if len(diffs) < 3:
        return float('nan'), float('nan'), len(diffs)
    return st.mean(diffs), st.mean(diffs) / (st.stdev(diffs) / math.sqrt(len(diffs))), len(diffs)


def h7(X, y, r, sess, draws=200, seed=5):
    pred = loso(X, y, sess)
    a = auc(pred, y)
    keep = pred > 0.5
    diff, t, k = clustered_diff(keep, r, sess)
    rng = random.Random(seed)
    beat = 0
    for _ in range(draws):
        yy = y.copy()
        idx = list(range(len(yy)))
        rng.shuffle(idx)
        beat += auc(loso(X, yy[idx], sess), yy[idx]) >= a
    out = {'picks': int(len(y)), 'sessions': len(set(sess)), 'auc_oos': round(a, 3),
           'kept': int(keep.sum()), 'kept_mean_pct': round(float(r[keep].mean()), 3) if keep.any() else None,
           'dropped_mean_pct': round(float(r[~keep].mean()), 3) if (~keep).any() else None,
           'kept_minus_dropped_pct': round(diff, 3), 'clustered_t': round(t, 2), 'sessions_compared': k,
           'placebo_p': round((beat + 1) / (draws + 1), 3),
           'weights_full_sample': dict(zip(['intercept', 'jev_forced', 'long', 'confidence', 'gap_with_pick',
                                            'market_gap_with_pick', 'move_atr_signed', 'atr_pct'],
                                           [round(float(v), 3) for v in fit(X, y)[0]]))}
    out['passes'] = out['auc_oos'] >= 0.58 and out['clustered_t'] >= 3 and out['placebo_p'] < 0.01
    return out


def h8(r, sess, atr):
    eq, iv = [], []
    for s in sorted(set(sess)):
        idx = [i for i, x in enumerate(sess) if x == s]
        w = np.array([1 / atr[i] for i in idx])
        w = w / w.sum()
        eq.append(float(np.mean([r[i] for i in idx])))
        iv.append(float(sum(wi * r[i] for wi, i in zip(w, idx))))
    out = {'sessions': len(eq), 'equal_mean_pct': round(st.mean(eq), 3), 'equal_sd': round(st.stdev(eq), 3),
           'inverse_atr_mean_pct': round(st.mean(iv), 3), 'inverse_atr_sd': round(st.stdev(iv), 3)}
    out['sd_cut_pct'] = round(100 * (1 - out['inverse_atr_sd'] / out['equal_sd']), 1)
    out['passes'] = out['sd_cut_pct'] >= 15 and out['inverse_atr_mean_pct'] - out['equal_mean_pct'] >= -0.05
    return out


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--rows', required=True)
    p.add_argument('--replay', default='.rb-state/replay')
    p.add_argument('--out')
    a = p.parse_args(argv)
    rows = json.loads(Path(a.rows).read_text())
    X, y, r, sess, atr = features(rows, a.replay)
    res = {'test': 'day130-H7-H8', 'H7_meta_labelling': h7(X, y, r, sess), 'H8_volatility_sizing': h8(r, sess, atr)}
    print(json.dumps(res, indent=1))
    if a.out:
        Path(a.out).write_text(json.dumps(res, indent=1) + '\n')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
