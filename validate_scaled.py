#!/usr/bin/env python3
"""
validate_scaled.py — the four-quarter test on the ONE candidate still standing.

WHERE THIS CAME FROM. Day-46 swept six feature families x two targets on the
TSX panel. `scaled` (r0 and gap expressed in units of each name's OWN trailing
volatility, rather than raw percent pooled across BCE and SHOP alike) was the
only family positive in all four cells, and the `y_rel` target — "does this name
beat the day's median" rather than "does it go up" — beat `y_abs` almost
everywhere. Neither cleared the pre-registered |z|>=3 bar on TSX, so nothing was
adopted.

Day-51 re-ran the identical sweep on 500 S&P 500 names, 719 sessions, 294,949
out-of-sample rows — a different market, to confirm or kill a hypothesis
GENERATED on TSX rows rather than re-reading the draw that produced it:

    y_rel   scaled   TSX z=+2.72  ->  US z=+6.03   (AUC 0.5045 -> 0.5064)

Same sign, clears the bar out-of-sample, effect size essentially identical. That
is a genuine replication and the first thing in fifty-one days to survive one.

WHY THE SCRIPT'S OWN VERDICT STILL SAID "NOT ADOPTED". The pre-registered bar
also required sign agreement on the NATIVE 5-minute panel, and that leg is
uninformative: 60 sessions is all Yahoo will serve, and the native positive
control came back at z=-1.71 and z=+2.32 — it cannot reliably detect a PLANTED
52% coin, so it can neither confirm nor refute anything. The bar was
unsatisfiable with free data, which is a flaw in the bar, not evidence about the
feature. Day-46 flagged exactly this and it was not fixed.

SO THIS IS THE REPLACEMENT TEST, and it is stricter where it can be:
  1. `scaled` vs `shipped` head to head on the SAME rows, both markets.
  2. Per quarter, on both. This repo's standing rule is that a result which
     does not hold in all four quarters is a window artifact — day-12, day-14,
     day-22 and day-40 all died that way.
  3. Effect size in economic terms, not just z. AUC 0.506 on 295k rows is
     overwhelmingly significant and still nearly worthless; significance and
     usefulness are different questions and only the second one pays.

PRE-REGISTERED, before running: adopt only if `scaled` beats `shipped` on y_rel
in ALL FOUR quarters on BOTH markets. Anything less is reported and not shipped.
"""

from __future__ import annotations

import argparse
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from validate_ceiling import auc, se_auc  # noqa: E402
from validate_exit import SCRATCH  # noqa: E402
from validate_features import boost, load_rich, usable  # noqa: E402

ARMS = {"shipped": ["r0", "gap", "vp"],
        "scaled":  ["r0_z", "gap_z", "rng0_z", "vol20"]}


def walk(df: pd.DataFrame, feats: list, target: str, folds: int,
         min_train: int) -> pd.DataFrame:
    """Return per-row out-of-sample scores tagged with their session."""
    sess = sorted(df["date"].unique())
    edges = np.linspace(min_train, len(sess), folds + 1).astype(int)
    out = []
    for a, b in zip(edges[:-1], edges[1:]):
        if b <= a:
            continue
        tr = df[df["date"].isin(sess[:a])].dropna(subset=[target])
        te = df[df["date"].isin(sess[a:b])].dropna(subset=[target]).copy()
        if te.empty or len(tr) < 500:
            continue
        te["score"] = boost(tr[feats].to_numpy(float), tr[target].to_numpy(int),
                            te[feats].to_numpy(float))
        out.append(te[["date", target, "score"]])
    return pd.concat(out) if out else pd.DataFrame()


def quarters(dates) -> list:
    d = sorted(set(dates))
    cuts = np.linspace(0, len(d), 5).astype(int)
    return [set(d[cuts[i]:cuts[i + 1]]) for i in range(4)]


def run(path: str, label: str, target: str, folds: int, min_train: int) -> dict:
    df = load_rich(path)
    print(f"\n{'=' * 74}\n{label}\n{'=' * 74}")
    print(f"{len(df):,} rows / {df['t'].nunique()} names / "
          f"{df['date'].nunique()} sessions   target {target}")
    scores = {}
    for arm, feats in ARMS.items():
        f = usable(df, feats)
        if not f:
            print(f"  {arm}: no usable columns")
            continue
        scores[arm] = walk(df, f, target, folds, min_train)

    if len(scores) < 2:
        return {}
    qs = quarters(scores["shipped"]["date"])
    print(f"\n  {'quarter':<10}{'shipped AUC':>14}{'scaled AUC':>13}"
          f"{'diff':>9}{'n':>10}")
    wins = 0
    for i, q in enumerate(qs, 1):
        row = {}
        for arm, s in scores.items():
            sub = s[s["date"].isin(q)]
            row[arm] = auc(sub[target].to_numpy(), sub["score"].to_numpy())
            n = len(sub)
        d = row["scaled"] - row["shipped"]
        wins += d > 0
        print(f"  Q{i:<9}{row['shipped']:>14.4f}{row['scaled']:>13.4f}"
              f"{d:>+9.4f}{n:>10,}")
    pooled = {}
    for arm, s in scores.items():
        pooled[arm] = (auc(s[target].to_numpy(), s["score"].to_numpy()), len(s))
    z = {a: (v[0] - 0.5) / se_auc(scores[a][target].to_numpy())
         for a, v in pooled.items()}
    print(f"  {'POOLED':<10}{pooled['shipped'][0]:>14.4f}"
          f"{pooled['scaled'][0]:>13.4f}"
          f"{pooled['scaled'][0] - pooled['shipped'][0]:>+9.4f}"
          f"{pooled['shipped'][1]:>10,}")
    print(f"  z: shipped {z['shipped']:+.2f}   scaled {z['scaled']:+.2f}")
    print(f"  -> scaled beat shipped in {wins} of 4 quarters")
    return {"wins": wins, "pooled": pooled, "z": z}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--target", default="y_rel")
    ap.add_argument("--folds", type=int, default=5)
    a = ap.parse_args(argv)
    print("PRE-REGISTERED: adopt only if `scaled` beats `shipped` on the target")
    print("in ALL FOUR quarters on BOTH markets. Significance is not the test;")
    print("consistency across independent windows is.")

    tsx = run(os.path.join(SCRATCH, "rich_1h.csv"),
              "TSX (hypothesis was generated here)", a.target, a.folds, 120)
    us = run(os.path.join(SCRATCH, "rich_us_1h.csv"),
             "S&P 500 (out-of-sample replication market)", a.target, a.folds, 120)

    print("\n" + "=" * 74 + "\nVERDICT\n" + "=" * 74)
    if not tsx or not us:
        print("  a panel failed to produce arms — inconclusive")
        return 2
    ok = tsx["wins"] == 4 and us["wins"] == 4
    print(f"  TSX quarters won by scaled: {tsx['wins']}/4")
    print(f"  US  quarters won by scaled: {us['wins']}/4")
    lift = us["pooled"]["scaled"][0] - us["pooled"]["shipped"][0]
    print(f"  pooled AUC lift on the replication market: {lift:+.4f}")
    print(f"  -> {'ADOPT' if ok else 'NOT ADOPTED — the four-quarter rule is not met'}")
    if not ok:
        print("     A feature that wins on pooled data but loses a quarter is")
        print("     the exact shape of every artifact this repo has killed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
