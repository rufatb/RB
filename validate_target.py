#!/usr/bin/env python3
"""
validate_target.py — train on CROSS-SECTIONAL rank instead of absolute direction?

THE MISMATCH, which has stood since day one. The k-NN is trained on
`r1 > 0` — "will this name go up?" — but the book is long AND short, so the
tape cancels between the legs and the only thing that pays is whether a name
beats the OTHER names. Day-45's attribution made this concrete: residual market
exposure measures +0.009%/session (t=+0.78, indistinguishable from the zero it
is designed to be) while every bit of P&L, good or bad, is the cross-sectional
term. The engine has been predicting one quantity to bet on a different one.

Day-46's sweep hinted at it — `y_rel` beat `y_abs` for nearly every feature
family on both markets — but that was measured as AUC ON THE TARGET, which is
close to circular: a model trained on y_rel naturally predicts y_rel better.
That says nothing about whether the resulting BOOK earns more.

So this is end-to-end. Both arms run the whole shipped pipeline — same k-NN,
same 0.55 qualification bar, same densest-leg tie-break, same up-to-2-per-side
— and differ ONLY in the training label:

    shipped   y = (r1 > 0)                          absolute direction
    xs        y = (r1 > that session's median r1)    cross-sectional rank

and are scored on the metric that actually pays: TIDE-RELATIVE capture per leg.

A SIDE EFFECT WORTH MEASURING. Under `y_abs`, a heavy tape drags every name's
probability the same way — day-47 published a board where 15 of 15 qualified
names were shorts, leaving the book ~50% net short and its P&L dominated by the
tape rather than the picks (TIDE +0.666%, SELECTION -0.518%). Under `y_rel`
roughly half the universe beats the median BY CONSTRUCTION, so both sides
should almost always have candidates. If that holds it removes the one-legged
day, which day-47 showed is where the hedge silently disappears. That is a
VARIANCE benefit, and all three changes ever adopted here were variance results.

PRE-REGISTERED, before running:
  ADOPT only if `xs` beats `shipped` on tide-relative capture per leg in ALL
  FOUR quarters on BOTH markets — the standing rule that killed day-12, -14,
  -22, -40 and -52. A pooled win with a lost quarter is the exact shape of
  every artifact this repo has thrown away.
  The one-legged-day reduction is reported either way but CANNOT justify
  adoption on its own: a rule that trades more often while predicting no better
  is just more exposure.
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


def knn_two_targets(df: pd.DataFrame, feats: list, folds: int,
                    min_train: int) -> pd.DataFrame:
    """Walk-forward p_up under BOTH labels on the SAME rows, plus nd.

    Both arms see identical training windows and identical neighbourhoods —
    only the label differs — so any difference downstream is the target and
    nothing else.
    """
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
        nn = NearestNeighbors(n_neighbors=min(K, len(Ztr))).fit(Ztr)
        dist, idx = nn.kneighbors(Zte)
        w = 1.0 / (1.0 + dist)
        te["nd"] = dist.mean(1)
        for arm, col in (("shipped", "y_abs"), ("xs", "y_rel")):
            y = tr[col].to_numpy().astype(float)
            te[f"p_{arm}"] = ((w * y[idx]).sum(1) + M * float(y.mean())) / (w.sum(1) + M)
        out.append(te)
        print(f"    fold {sess[a]}..{sess[b-1]}  test {len(te):,}", flush=True)
    return pd.concat(out) if out else pd.DataFrame()


def book_legs(day: pd.DataFrame, pcol: str, bar: float, per_side: int) -> list:
    """The shipped selection: qualify at `bar`, then densest-first per side."""
    legs = []
    for side, mask in (("LONG", day[pcol] >= bar), ("SHORT", 1 - day[pcol] >= bar)):
        cand = day[mask].nsmallest(per_side, "nd")
        for _, r in cand.iterrows():
            legs.append((side, r["rel"] * (1 if side == "LONG" else -1)))
    return legs


def evaluate(sc: pd.DataFrame, arm: str, bar: float, per_side: int) -> dict:
    """Per-session book, scored on tide-relative capture per leg."""
    pcol = f"p_{arm}"
    per_leg, one_sided, sessions = [], 0, 0
    by_q: dict = {}
    for date, day in sc.groupby("date"):
        legs = book_legs(day, pcol, bar, per_side)
        if not legs:
            continue
        sessions += 1
        sides = {s for s, _ in legs}
        if len(sides) < 2:
            one_sided += 1
        vals = [v for _, v in legs]
        per_leg += vals
        by_q.setdefault(date, []).extend(vals)
    return {"per_leg": np.array(per_leg, dtype=float), "by_date": by_q,
            "sessions": sessions, "one_sided": one_sided}


def quarters(dates) -> list:
    d = sorted(set(dates))
    cuts = np.linspace(0, len(d), 5).astype(int)
    return [set(d[cuts[i]:cuts[i + 1]]) for i in range(4)]


def run(path: str, label: str, folds: int, min_train: int, bar: float,
        per_side: int) -> dict:
    df = load_rich(path)
    feats = [f for f in FEATS3 if df[f].notna().mean() > 0.5]
    print(f"\n{'=' * 76}\n{label}\n{'=' * 76}")
    print(f"{len(df):,} rows / {df['t'].nunique()} names / "
          f"{df['date'].nunique()} sessions   features {'+'.join(feats)}")
    sc = knn_two_targets(df, feats, folds, min_train)
    if sc.empty:
        return {}
    # tide-relative move, computed once and shared by both arms
    sc["rel"] = sc["r1"] - sc.groupby("date")["r1"].transform("median")

    res = {a: evaluate(sc, a, bar, per_side) for a in ("shipped", "xs")}
    qs = quarters(sc["date"])
    print(f"\n  tide-relative capture per leg (the metric that pays)")
    print(f"  {'quarter':<10}{'shipped':>11}{'xs':>11}{'diff':>10}"
          f"{'legs(sh)':>10}{'legs(xs)':>10}")
    wins = 0
    for i, q in enumerate(qs, 1):
        m = {}
        n = {}
        for arm in ("shipped", "xs"):
            v = [x for d, xs in res[arm]["by_date"].items() if d in q for x in xs]
            m[arm] = float(np.mean(v)) if v else float("nan")
            n[arm] = len(v)
        d = m["xs"] - m["shipped"]
        wins += d > 0
        print(f"  Q{i:<9}{m['shipped']:>+11.4f}{m['xs']:>+11.4f}{d:>+10.4f}"
              f"{n['shipped']:>10,}{n['xs']:>10,}")
    pm = {a: float(res[a]["per_leg"].mean()) for a in res}
    print(f"  {'POOLED':<10}{pm['shipped']:>+11.4f}{pm['xs']:>+11.4f}"
          f"{pm['xs'] - pm['shipped']:>+10.4f}"
          f"{len(res['shipped']['per_leg']):>10,}"
          f"{len(res['xs']['per_leg']):>10,}")
    for a in ("shipped", "xs"):
        r = res[a]
        print(f"    {a:<8} one-legged sessions: {r['one_sided']}/{r['sessions']} "
              f"({r['one_sided']/max(r['sessions'],1):.1%})   "
              f"std/leg {r['per_leg'].std():.3f}")
    print(f"  -> xs beat shipped in {wins} of 4 quarters")
    return {"wins": wins, "pooled": pm, "res": res}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--folds", type=int, default=5)
    ap.add_argument("--min-train", type=int, default=120)
    ap.add_argument("--bar", type=float, default=0.55)
    ap.add_argument("--per-side", type=int, default=2)
    a = ap.parse_args(argv)
    print("PRE-REGISTERED: adopt only if `xs` beats `shipped` on tide-relative")
    print("capture per leg in ALL FOUR quarters on BOTH markets. Fewer")
    print("one-legged days is reported but cannot justify adoption alone.")

    tsx = run(os.path.join(SCRATCH, "rich_1h.csv"), "TSX — the traded market",
              a.folds, a.min_train, a.bar, a.per_side)
    us = run(os.path.join(SCRATCH, "rich_us_1h.csv"),
             "S&P 500 — independent replication", a.folds, a.min_train,
             a.bar, a.per_side)

    print("\n" + "=" * 76 + "\nVERDICT\n" + "=" * 76)
    if not tsx or not us:
        print("  a panel failed — inconclusive")
        return 2
    ok = tsx["wins"] == 4 and us["wins"] == 4
    print(f"  TSX quarters won by xs: {tsx['wins']}/4   "
          f"pooled {tsx['pooled']['xs'] - tsx['pooled']['shipped']:+.4f}%/leg")
    print(f"  US  quarters won by xs: {us['wins']}/4   "
          f"pooled {us['pooled']['xs'] - us['pooled']['shipped']:+.4f}%/leg")
    print(f"  -> {'ADOPT' if ok else 'NOT ADOPTED — four-quarter rule not met'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
