#!/usr/bin/env python3
"""
validate_density.py — does the DENSITY selector systematically pick the names
that move least?

WHAT PROMPTED IT (day-47). The tape fell -1.334% and 13 of 15 qualified shorts
hit. Ranked by capture, the top eight were all `sparse` or `mid`; the two
`dense` names — the only two the selector actually sizes — ranked 9th and 14th
of 15, and the highest-conviction pick of the day (BCE, sided-P 0.617) closed
UP. The book still made money because one leg carried it, but the selector had
drawn from the bottom of the day's distribution.

THE MECHANISM BEING TESTED. `nd` is the mean distance to the k nearest
neighbours in (r0, gap, vp) space. A name whose opening behaviour is
unremarkable sits in the middle of a dense cloud every single day. Unremarkable
opening behaviour is mostly a property of LOW-VOLATILITY names — so `dense` may
be a proxy for "this name does not move much", and picking it maximises
familiarity while minimising the very move the position needs. config.yaml has
carried a version of this suspicion since day-14 ("low-volatility names hijack
the density selection") but it was only ever asserted, never measured directly.

Three questions, each with a pre-registered direction:
  Q1  Is `nd` negatively correlated with the name's trailing volatility?
      (If dense == low-vol, this is where it shows.)
  Q2  Among QUALIFIED picks, does `nd` predict the SIZE of the subsequent move?
      Prediction under the hypothesis: dense -> smaller |r1|.
  Q3  Does it predict signed CAPTURE — i.e. does it cost money, or merely
      reduce variance? Reducing variance is not a defect; this engine has
      adopted three variance results already.

Q3 is the one that decides anything. Q1 and Q2 can both be true while capture
is unaffected, and in that case density is doing exactly what a tie-break
should: picking the calmer name for the same expected return.

PER-QUARTER, always: this repo's standing rule is that a result which does not
hold in all four quarters is a window artifact (day-12, day-14, day-22, day-40
all died that way).
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

K, M = 60, 20
FEATS3 = ["r0", "gap", "vp"]


def knn_walk(df: pd.DataFrame, feats: list, folds: int = 8,
             min_train: int = 90) -> pd.DataFrame:
    """Walk-forward p_up and nd for every row, exactly as the live engine does:
    standardise on the training window, k nearest by Euclidean distance,
    distance-weighted vote, Beta-smoothed to the training base rate."""
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
        base = float(y.mean())
        nn = NearestNeighbors(n_neighbors=min(K, len(Ztr))).fit(Ztr)
        dist, idx = nn.kneighbors(Zte)
        w = 1.0 / (1.0 + dist)
        te["p_up"] = ((w * y[idx]).sum(1) + M * base) / (w.sum(1) + M)
        te["nd"] = dist.mean(1)
        out.append(te)
        print(f"    fold {sess[a]}..{sess[b-1]}  train {len(tr):,}  test {len(te):,}",
              flush=True)
    return pd.concat(out) if out else pd.DataFrame()


def quarters(df: pd.DataFrame) -> list:
    d = sorted(df["date"].unique())
    cuts = np.linspace(0, len(d), 5).astype(int)
    return [set(d[cuts[i]:cuts[i + 1]]) for i in range(4)]


def tercile_table(q: pd.DataFrame, label: str) -> None:
    """Capture and |move| by nd tercile among the QUALIFIED picks."""
    q = q.copy()
    q["tag"] = pd.qcut(q["nd"], 3, labels=["dense", "mid", "sparse"])
    print(f"\n  {label}  (n={len(q):,} qualified picks)")
    print(f"    {'tag':<8}{'n':>7}{'hit':>8}{'capture':>10}{'|move|':>9}{'nd':>8}"
          f"{'vol20':>8}")
    for t in ("dense", "mid", "sparse"):
        s = q[q["tag"] == t]
        if s.empty:
            continue
        print(f"    {t:<8}{len(s):>7}{s['hit'].mean():>8.1%}"
              f"{s['capture'].mean():>+10.4f}{s['capture'].abs().mean():>9.3f}"
              f"{s['nd'].mean():>8.3f}{s['vol20'].mean():>8.3f}")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pool", default=os.path.join(SCRATCH, "rich_1h.csv"))
    ap.add_argument("--folds", type=int, default=8)
    ap.add_argument("--min-train", type=int, default=90)
    ap.add_argument("--bar", type=float, default=0.55)
    a = ap.parse_args(argv)

    df = load_rich(a.pool)
    feats = [f for f in FEATS3 if df[f].notna().mean() > 0.5]
    print("=" * 76)
    print("DENSITY: does the selector systematically pick the names that move least?")
    print("=" * 76)
    print(f"pool {os.path.basename(a.pool)}: {len(df):,} rows / "
          f"{df['date'].nunique()} sessions   features {'+'.join(feats)}")

    scored = knn_walk(df, feats, a.folds, a.min_train)
    if scored.empty:
        print("no folds produced — aborting")
        return 2

    # Q1 -------------------------------------------------------------------
    v = scored.dropna(subset=["vol20", "nd"])
    r = float(np.corrcoef(v["nd"], v["vol20"])[0, 1])
    print(f"\nQ1  corr(nd, vol20) = {r:+.4f}  on n={len(v):,}")
    print("    positive => sparse names ARE the volatile ones "
          "(and dense the calm ones)")

    # Q2/Q3 ----------------------------------------------------------------
    q = scored[(scored["p_up"] >= a.bar) | (1 - scored["p_up"] >= a.bar)].copy()
    q["side"] = np.where(q["p_up"] >= a.bar, 1, -1)
    q["capture"] = q["r1"] * q["side"]
    q["hit"] = (q["capture"] > 0).astype(int)
    tercile_table(q, "POOLED")

    print("\n  PER QUARTER — capture by tercile (the standing four-quarter rule)")
    print(f"    {'quarter':<10}{'dense':>10}{'mid':>10}{'sparse':>10}"
          f"{'sparse-dense':>14}")
    wins = 0
    for i, qs in enumerate(quarters(scored), 1):
        s = q[q["date"].isin(qs)].copy()
        if len(s) < 50:
            continue
        s["tag"] = pd.qcut(s["nd"], 3, labels=["dense", "mid", "sparse"])
        m = {t: s[s["tag"] == t]["capture"].mean() for t in ("dense", "mid", "sparse")}
        d = m["sparse"] - m["dense"]
        wins += d > 0
        print(f"    Q{i:<9}{m['dense']:>+10.4f}{m['mid']:>+10.4f}"
              f"{m['sparse']:>+10.4f}{d:>+14.4f}")
    print(f"\n    sparse beat dense in {wins} of 4 quarters "
          f"(the adoption bar is 4 of 4)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
