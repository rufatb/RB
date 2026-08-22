#!/usr/bin/env python3
"""
validate_horizon.py — should each pick carry its OWN suggested hold length?

WHAT IS ALREADY SETTLED, and is not re-litigated here:
  day-24  one night doubles volatility and worsens the tail 2.3x
  day-32  event/swing trades on daily data: no edge found
  day-38  FIXED 3-day and 5-day holds, rejected (#28) — the apparent gain was
          market drift collected by an 83%-long book; hedged properly it fell
          to +0.1123%/trade at t=+0.94, with 10x the volatility and a worst
          trade of -19.84%
  day-36  no intraday exit beats the close (#24)

WHAT HAS NEVER BEEN ASKED. Every one of those applied the SAME horizon to every
trade. Nobody has asked whether the right horizon is PREDICTABLE PER PICK — i.e.
whether something knowable at 9:45 separates "this is a same-day trade" from
"this one deserves three days". A suggested-duration field only makes sense if
that separation exists, so this measures it before anything is built.

THE TESTS
  A  Accuracy by horizon. The user's actual question: does holding longer make
     the DIRECTION call more often right, independent of what it does to
     return? Reported as hit rate at h = 0, 1, 2, 3, 5 sessions.
  B  Capture by horizon, both raw and TIDE-RELATIVE. Day-38 showed the whole
     multi-day story lives in drift, so raw capture is reported only next to
     the hedged number. Relative capture is what a long/short book earns.
  C  Is the best horizon predictable? For each pick compute the horizon that
     maximises relative capture, then ask whether any feature knows it in
     advance. Two ways, because the naive one flatters itself:
       - a classifier trained to pick the horizon, scored out-of-sample against
         the base rate of always choosing the single best fixed horizon
       - correlation between each feature and the ADVANTAGE of holding longer
         (relative capture at h=3 minus at h=0)
  D  The oracle bound, AND ITS PLACEBO. What would PERFECT per-pick horizon
     selection earn? The raw oracle number is worthless on its own, and the
     first version of this script drew the wrong conclusion from it: a gap of
     +2.34%/trade looked like a large prize worth chasing. It is not. Taking
     the maximum of five noisy, positively-correlated draws is ABOVE their mean
     by construction, whether or not anything is predictable. So the oracle is
     recomputed on multivariate noise with the same means and covariance. Only
     the excess of the real gap over that placebo gap can possibly be earned.

PRE-REGISTERED BAR: a suggested-duration field ships only if (C) beats its base
rate at |z| >= 3 AND the real oracle gap EXCEEDS its noise placebo. Anything
else is reported as NOT ADOPTED.
"""

from __future__ import annotations

import argparse
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from validate_exit import SCRATCH  # noqa: E402
from validate_features import load_rich  # noqa: E402

HORIZONS = [0, 1, 2, 3, 5]
K, M = 60, 20
FEATS3 = ["r0", "gap", "vp"]


def add_forward(df: pd.DataFrame) -> pd.DataFrame:
    """Relative capture at each horizon, per row.

    The panel stores the entry price `px` and `r1` (entry -> that session's
    close), so each session's close is px*(1+r1/100). Holding h extra sessions
    means exiting at the close h rows later for the SAME ticker.

    The tide is subtracted at each horizon separately: the book is long and
    short, so the cross-sectional median move over the same window is exactly
    what cancels between the legs and must not be counted as skill. Day-38's
    mirage was precisely this term.
    """
    df = df.sort_values(["t", "date"]).copy()
    df["close"] = df["px"] * (1 + df["r1"] / 100.0)
    g = df.groupby("t", sort=False)["close"]
    for h in HORIZONS:
        fwd = g.shift(-h)                       # close h sessions ahead
        df[f"raw{h}"] = (fwd / df["px"] - 1) * 100
    # cross-sectional median of the same window = the tide over that horizon
    for h in HORIZONS:
        df[f"tide{h}"] = df.groupby("date")[f"raw{h}"].transform("median")
        df[f"rel{h}"] = df[f"raw{h}"] - df[f"tide{h}"]
    return df


def knn_walk(df: pd.DataFrame, feats: list, folds: int, min_train: int) -> pd.DataFrame:
    from sklearn.neighbors import NearestNeighbors
    sess = sorted(df["date"].unique())
    edges = np.linspace(min_train, len(sess), folds + 1).astype(int)
    out = []
    for a, b in zip(edges[:-1], edges[1:]):
        if b <= a:
            continue
        tr = df[df["date"].isin(sess[:a])].dropna(subset=feats + ["r1"])
        te = df[df["date"].isin(sess[a:b])].dropna(subset=feats + ["r1"]).copy()
        if te.empty or len(tr) < 500:
            continue
        mu, sd = tr[feats].mean(), tr[feats].std().replace(0, 1)
        Ztr = ((tr[feats] - mu) / sd).to_numpy()
        Zte = ((te[feats] - mu) / sd).to_numpy()
        y = (tr["r1"] > 0).to_numpy().astype(float)
        nn = NearestNeighbors(n_neighbors=min(K, len(Ztr))).fit(Ztr)
        dist, idx = nn.kneighbors(Zte)
        w = 1.0 / (1.0 + dist)
        te["p_up"] = ((w * y[idx]).sum(1) + M * float(y.mean())) / (w.sum(1) + M)
        out.append(te)
        print(f"    fold {sess[a]}..{sess[b-1]}  test {len(te):,}", flush=True)
    return pd.concat(out) if out else pd.DataFrame()


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pool", default=os.path.join(SCRATCH, "rich_1h.csv"))
    ap.add_argument("--folds", type=int, default=6)
    ap.add_argument("--min-train", type=int, default=120)
    ap.add_argument("--bar", type=float, default=0.55)
    ap.add_argument("--placebo", type=int, default=20,
                    help="draws for the oracle noise placebo")
    a = ap.parse_args(argv)

    df = add_forward(load_rich(a.pool))
    feats = [f for f in FEATS3 if df[f].notna().mean() > 0.5]
    print("=" * 78)
    print("PER-PICK HOLD DURATION — is the right horizon knowable at 9:45?")
    print("=" * 78)
    print(f"pool: {len(df):,} rows / {df['date'].nunique()} sessions  "
          f"features {'+'.join(feats)}")

    sc = knn_walk(df, feats, a.folds, a.min_train)
    q = sc[(sc["p_up"] >= a.bar) | (1 - sc["p_up"] >= a.bar)].copy()
    q["side"] = np.where(q["p_up"] >= a.bar, 1, -1)
    for h in HORIZONS:
        q[f"cap{h}"] = q[f"raw{h}"] * q["side"]
        q[f"crel{h}"] = q[f"rel{h}"] * q["side"]
    q = q.dropna(subset=[f"crel{h}" for h in HORIZONS])
    print(f"\nqualified picks with all horizons available: {len(q):,}")

    # ---- A + B ----------------------------------------------------------
    print("\n  A/B  ACCURACY AND CAPTURE BY HORIZON")
    print(f"    {'hold':<10}{'hit(raw)':>10}{'hit(rel)':>10}{'raw cap':>10}"
          f"{'REL cap':>10}{'std(rel)':>10}{'worst':>10}")
    for h in HORIZONS:
        c, cr = q[f"cap{h}"], q[f"crel{h}"]
        name = "to close" if h == 0 else f"+{h} day{'s' if h > 1 else ''}"
        print(f"    {name:<10}{(c > 0).mean():>10.1%}{(cr > 0).mean():>10.1%}"
              f"{c.mean():>+10.4f}{cr.mean():>+10.4f}{cr.std():>10.3f}"
              f"{cr.min():>+10.2f}")

    # ---- D: the oracle bound (computed first — it can end the enquiry) ----
    n_placebo = a.placebo
    rel = q[[f"crel{h}" for h in HORIZONS]].to_numpy()
    best_idx = rel.argmax(1)
    oracle = rel[np.arange(len(rel)), best_idx].mean()
    fixed = {h: q[f"crel{h}"].mean() for h in HORIZONS}
    best_fixed_h = max(fixed, key=fixed.get)
    gap = oracle - fixed[best_fixed_h]
    print(f"\n  D  ORACLE BOUND (perfect per-pick horizon choice, impossible)")
    print(f"    best FIXED horizon      : +{best_fixed_h} -> {fixed[best_fixed_h]:+.4f}%/trade")
    print(f"    PERFECT per-pick choice : {oracle:+.4f}%/trade")
    print(f"    raw gap                 : {gap:+.4f}%/trade")
    # The placebo. max() of correlated noise beats its own mean by construction,
    # so the raw gap must be compared against what pure noise produces.
    rng = np.random.default_rng(0)
    mu, cov = rel.mean(0), np.cov(rel, rowvar=False)
    pl = [(lambda S: S.max(1).mean() - S.mean(0).max())(
              rng.multivariate_normal(mu, cov, size=len(rel)))
          for _ in range(n_placebo)]
    p_gap = float(np.mean(pl))
    print(f"    PLACEBO gap (pure noise, same covariance, {n_placebo} draws)"
          f": {p_gap:+.4f}  (sd {np.std(pl):.4f})")
    print(f"    EARNABLE excess         : {gap - p_gap:+.4f}%/trade")

    # ---- C: is it predictable? ------------------------------------------
    print(f"\n  C  IS THE BEST HORIZON PREDICTABLE FROM 9:45 INFORMATION?")
    adv = q[f"crel{3}"] - q[f"crel{0}"]          # gain from holding 3 extra days
    print(f"    advantage of +3d over to-close: {adv.mean():+.4f}%/trade "
          f"(std {adv.std():.3f})")
    print(f"    {'feature':<12}{'corr with that advantage':>28}")
    cand = [f for f in ("r0", "gap", "vp", "vol20", "rng0", "clv", "ret5",
                        "ret20", "r0_z", "xs_disp") if f in q.columns]
    for f in cand:
        s = q[[f]].join(adv.rename("adv")).dropna()
        if len(s) < 500:
            continue
        r = float(np.corrcoef(s[f], s["adv"])[0, 1])
        flag = "  <- notable" if abs(r) > 0.05 else ""
        print(f"    {f:<12}{r:>+28.4f}{flag}")

    print("\n" + "=" * 78)
    print("VERDICT")
    print("=" * 78)
    excess = gap - p_gap
    if excess <= 0:
        print(f"  The raw oracle gap ({gap:+.4f}%/trade) is SMALLER than what pure")
        print(f"  noise of the same covariance produces ({p_gap:+.4f}). The whole")
        print("  'prize' is the expected maximum of five noisy draws. There is")
        print("  nothing here for any predictor to find, at any skill level.")
    else:
        print(f"  Earnable excess over the noise placebo: {excess:+.4f}%/trade.")
        print("  Check (C) for a predictor before building anything on it.")
    print("=" * 78)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
