#!/usr/bin/env python3
"""
validate_features.py — do RICHER features, built from bars we already have,
carry signal the shipped three do not?

Day-43 answered "is the ceiling the model or the information?" for the shipped
feature set and found the information: gradient boosting with ~100x the k-NN's
capacity reached AUC 0.5022 (z=1.32) on 122k out-of-sample rows while the same
pipeline detected a planted 52% coin at z=15. The conclusion attached to it —
"only new paid data can help" — skipped a step. The bars already downloaded
every morning are reduced to three scalars and the rest is thrown away. This
tests the rest, at zero cost, before anyone buys a feed.

TWO THINGS ARE VARIED, not one.

1. FEATURE FAMILIES (build_rich.py)
     shipped   r0, gap, vp                     — the baseline to beat
     shape     opening-range width, close-location-value, wicks
     scaled    r0 and gap in units of the name's OWN trailing volatility
     context   multi-day momentum, vol regime, distance from 20d high/low
     cross     same-day cross-sectional rank and deviation from the median
     all       everything at once

2. THE TARGET. Everything ever tested here predicted `r1 > 0` — absolute
   direction. But the book is long AND short, so the tape cancels between the
   legs and what actually pays is whether a name beats the OTHERS (day-28's
   relative-capture finding, and the day-45 attribution which showed residual
   market exposure is ~0 and every bit of P&L is cross-sectional). Predicting
   absolute direction to place a relative bet is a mismatch that has stood
   since day one. So each family is tested against both:
     y_abs   r1 > 0                     (what is shipped)
     y_rel   r1 > that day's median r1   (what the book actually needs)

PROTOCOL, unchanged from day-43 because it is what makes a null trustworthy:
walk-forward split by SESSION (never by row — two legs of one day share market
direction and a row-wise split leaks), and every single run also fits the
identical pipeline to a synthetic feature carrying a known weak edge. If the
control does not light up, the run reports INCONCLUSIVE instead of a verdict.

MULTIPLE COMPARISONS: this tries 6 families x 2 targets = 12 combinations, so
the best-looking arm is selected out of twelve and its nominal z is optimistic.
The adoption bar is stated BEFORE the run and is deliberately higher than a
nominal 2 sigma: |z| >= 3 on the deep panel AND the same sign at the native
9:45 decision point. Anything less is reported as "not adopted".
"""

from __future__ import annotations

import argparse
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from validate_ceiling import auc, brier, se_auc  # noqa: E402
from validate_exit import SCRATCH  # noqa: E402


def boost(Xtr, ytr, Xte, seed: int = 0):
    """Highest-capacity learner only — this script probes the CEILING.

    Day-43's `fit_models` also fits the shipped k-NN, which scores each test row
    against every training row. At this panel's size (120k train x 25k test per
    fold) that is ~3e9 distance evaluations per fold and the first attempt at
    this sweep was killed before printing a line. The k-NN's job was to show
    that the SHIPPED model is no weaker than the alternatives, and day-43
    already established that; here the only question is whether a strong learner
    can find anything at all, so fit the strong learner and nothing else.

    HistGradientBoosting rather than GradientBoosting: same family, binned
    splits, ~20x faster above 10^5 rows, and it takes NaNs natively so a family
    with partial coverage is not silently reduced to its complete-case subset.
    """
    from sklearn.ensemble import HistGradientBoostingClassifier
    m = HistGradientBoostingClassifier(random_state=seed, max_iter=300,
                                       learning_rate=0.05, max_depth=3,
                                       early_stopping=False)
    return m.fit(Xtr, ytr).predict_proba(Xte)[:, 1]

FAMILIES = {
    "shipped": ["r0", "gap", "vp"],
    "shape":   ["rng0", "clv", "wick_up", "wick_dn"],
    "scaled":  ["r0_z", "gap_z", "rng0_z", "vol20"],
    "context": ["ret1", "ret5", "ret20", "vol20", "dist_hi", "dist_lo", "prev_r1"],
    "cross":   ["r0_rank", "r0_dev", "gap_rank", "gap_dev", "rng0_rank", "xs_disp"],
}
FAMILIES["all"] = sorted({f for v in FAMILIES.values() for f in v})

ADOPT_Z = 3.0          # pre-registered, above nominal 2s because 12 arms are tried


def load_rich(path: str, min_price: float = 5.0) -> pd.DataFrame:
    df = pd.read_csv(path)
    df = df[(df["px"] >= min_price) & df["r1"].notna()]
    # vp exactly as the live engine builds it, but leak-free: the normaliser is
    # an expanding median shifted one session back, never the whole sample.
    df = df.sort_values(["t", "date"])
    med = (df.groupby("t")["v15"]
             .apply(lambda s: s.shift(1).expanding(min_periods=20).median())
             .reset_index(level=0, drop=True))
    df["vp"] = df["v15"] / med.replace(0, np.nan)
    if (df["v15"].fillna(0) == 0).mean() > 0.25:
        df["vp"] = np.nan                      # day-43: not computable on 1h
    df["y_abs"] = (df["r1"] > 0).astype(int)
    df["y_rel"] = (df["r1"] > df.groupby("date")["r1"].transform("median")).astype(int)
    return df.sort_values("date").reset_index(drop=True)


def usable(df: pd.DataFrame, feats: list) -> list:
    """Drop columns absent or ~entirely missing, so a family is never silently
    reduced to noise (day-43: `vp` NaN'd out 145,201 of 145,228 rows)."""
    out = []
    for f in feats:
        if f in df.columns and df[f].notna().mean() > 0.5:
            out.append(f)
    return out


def walk_forward(df: pd.DataFrame, feats: list, target: str,
                 folds: int = 5, min_train: int = 120) -> tuple:
    sess = sorted(df["date"].unique())
    edges = np.linspace(min_train, len(sess), folds + 1).astype(int)
    ys, ss = [], []
    for a, b in zip(edges[:-1], edges[1:]):
        if b <= a:
            continue
        # NaNs are kept — the booster handles them natively, so a family is
        # never silently narrowed to whichever rows happen to be complete.
        tr = df[df["date"].isin(sess[:a])].dropna(subset=[target])
        te = df[df["date"].isin(sess[a:b])].dropna(subset=[target])
        if te.empty or len(tr) < 500:
            continue
        ss.append(boost(tr[feats].to_numpy(float), tr[target].to_numpy(int),
                        te[feats].to_numpy(float)))
        ys.append(te[target].to_numpy(int))
    if not ys:
        return None, None
    return np.concatenate(ys), np.concatenate(ss)


def control_z(df: pd.DataFrame, feats: list, target: str, folds: int,
              min_train: int, edge: float = 0.02, seed: int = 0) -> float:
    rng = np.random.default_rng(seed)
    d = df.copy()
    d["ctrl"] = rng.normal(size=len(d)) + (2 * d[target] - 1) * edge * 2.5
    y, s = walk_forward(d, feats + ["ctrl"], target, folds, min_train)
    return float("nan") if y is None else (auc(y, s) - 0.5) / se_auc(y)


def run_panel(path: str, label: str, folds: int, min_train: int) -> dict:
    df = load_rich(path)
    print("\n" + "=" * 78)
    print(f"{label}: {len(df):,} rows / {df['t'].nunique()} names / "
          f"{df['date'].nunique()} sessions")
    print("=" * 78)
    res = {}
    for target in ("y_abs", "y_rel"):
        base = df[target].mean()
        print(f"\n  TARGET {target}   (base rate {base:.4f})")
        print(f"    {'family':<10}{'n feats':>8}{'AUC':>9}{'z':>8}{'acc':>8}{'Brier':>9}{'n':>10}")
        for fam, feats in FAMILIES.items():
            f = usable(df, feats)
            if not f:
                print(f"    {fam:<10}{'-':>8}  (no usable columns in this panel)")
                continue
            y, s = walk_forward(df, f, target, folds, min_train)
            if y is None:
                print(f"    {fam:<10}{len(f):>8}  (insufficient folds)")
                continue
            a, z = auc(y, s), (auc(y, s) - 0.5) / se_auc(y)
            ac = float(((s > 0.5).astype(int) == y).mean())
            print(f"    {fam:<10}{len(f):>8}{a:>9.4f}{z:>8.2f}{ac:>8.1%}"
                  f"{brier(y, s):>9.4f}{len(y):>10,}")
            res[(target, fam)] = (a, z, len(y))
        cz = control_z(df, usable(df, FAMILIES["shipped"]) or ["r0"], target,
                       folds, min_train)
        print(f"    {'[control]':<10}{'+1':>8}{'':>9}{cz:>8.2f}   <- planted 52% coin")
        res[(target, "_control")] = (None, cz, 0)
    return res


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--deep", default=os.path.join(SCRATCH, "rich_1h.csv"))
    ap.add_argument("--native", default=os.path.join(SCRATCH, "rich_5m.csv"))
    ap.add_argument("--folds", type=int, default=5)
    a = ap.parse_args(argv)

    print("PRE-REGISTERED BAR: adopt only if |z| >= 3.0 on the deep panel AND")
    print("the same sign at the native 9:45 decision point. 12 arms are tried,")
    print("so a nominal 2-sigma result here is expected by chance alone.")

    deep = run_panel(a.deep, "DEEP panel (1h entry, ~3 years)", a.folds, 120)
    nat = run_panel(a.native, "NATIVE panel (5m entry = the real 9:45 decision)",
                    a.folds, 25)

    print("\n" + "=" * 78)
    print("VERDICT")
    print("=" * 78)
    for target in ("y_abs", "y_rel"):
        cz = deep.get((target, "_control"), (None, float("nan"), 0))[1]
        if not (abs(cz) >= 3):
            print(f"  {target}: INCONCLUSIVE — control only reached z={cz:.2f}.")
            continue
        cands = {k[1]: v for k, v in deep.items()
                 if k[0] == target and k[1] != "_control"}
        best = max(cands.items(), key=lambda kv: abs(kv[1][1]))
        fam, (au, z, n) = best
        nz = nat.get((target, fam), (None, float("nan"), 0))[1]
        ok = abs(z) >= ADOPT_Z and np.sign(z) == np.sign(nz)
        print(f"  {target}: control z={cz:+.1f} (harness works). "
              f"best family '{fam}' AUC {au:.4f}, z={z:+.2f} on n={n:,}; "
              f"native z={nz:+.2f}")
        print(f"           -> {'ADOPT — pre-register and re-test' if ok else 'NOT ADOPTED (bar not met)'}")
    print("=" * 78)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
