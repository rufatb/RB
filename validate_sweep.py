#!/usr/bin/env python3
"""
validate_sweep.py — the holistic sweep (day-37). Every knob at once, plus the
null that says whether any winner is real.

WHY THIS EXISTS: 24 levers have been tested ONE AT A TIME against a fixed
baseline. That is the wrong shape of question after a losing run. It cannot
answer "is there ANY configuration of this strategy that works", and testing
levers serially also hides the multiple-comparisons cost -- 24 one-off tests at
p<0.05 produce roughly one false winner by construction, and this repo has
adopted 3 things.

WHAT IT SWEEPS (the dimensions asked for, jointly, not serially):
  * legs per side      1, 2, 3, 4
  * side mix           long+short / long-only / short-only
  * qualification bar  0.50 .. 0.65
  * selector           densest / max_p / sparsest / random
  * weekday            all, Mon, Tue, Wed, Thu, Fri
That is 4*3*4*4*6 = 1,152 configurations on 288 test sessions.

THE POINT OF THE NULL (this is the part that matters): with 1,152 configs, the
BEST one always looks good. So the same sweep is re-run on placebo books whose
directional calls carry no information -- same names, same days, same sizes,
same tide, sides assigned at random. If the real best config does not clear the
placebo best config, the strategy has found nothing, and every "winner" in the
table is mining.

DATA: the 20 US dual-listings, hourly, ~2 years (see validate_twins.py for why
this set exists and its caveats). One expensive walk-forward pass builds a
per-name table of out-of-sample p_up; the 1,152 configs are then cheap
re-slicings of that one table, so no configuration gets a different model.

RESULTS (2026-08-13, first run -- recorded so the verdict is permanent):

  *** REJECTED (#25): no configuration of this strategy has a demonstrated
      edge. The shipped config is not merely unlucky -- it is average. ***

  SHIPPED CONFIG (2 legs / both sides / 0.55 / densest / all days):
      mean +0.0004%/session, t +0.01, 48% positive -> RANK 449 OF 800.
  That is the cleanest statement of the problem: out of 800 ways to run this
  strategy, the one being traded sits in the middle, and the middle is zero.

  THE APPARENT WINNER, and why it is not one. Best config was long-only /
  bar 0.60 / Thursday / 1 leg at +0.512%/session, t +2.09, and the calibrated
  null gave p = 0.040 -- the first thing in 25 tests to clear a placebo band.
  It fails on inspection, four ways:
    1. QUARTERS: +0.573 / -0.564 / +0.538 / +1.067. Q2 is strongly negative,
       so it fails the all-four-quarters bar that has governed since day-14.
    2. n = 37 Thursdays, 6-11 per quarter.
    3. THE SELECTOR IS BACKWARDS: random +0.512 beats densest +0.361, max_p
       +0.371, sparsest +0.333. If the model were ranking well, densest would
       lead. Random leading is the signature of no skill -- the "edge" is not
       coming from the model's ordering at all.
    4. It is not a Thursday tape effect either: buying the WHOLE universe on
       Thursdays pays +0.009%/session.
  The null's own median best config was +0.368%/session. A grid this size
  manufactures half-percent "winners" from pure noise as a matter of routine;
  that is exactly what the null is for, and why a bare p-value is not enough.

  WHAT THE SWEEP RULES OUT (the dimensions asked for, tested jointly):
  legs per side 1-4, long-only / short-only / both, qualification bar
  0.50-0.65, four selectors, and every weekday. Nothing in that space
  survives. Combined with day-36 (exit time is flat), day-24 (overnight
  doubles volatility), day-32 (multi-day: no edge) and day-21 (entry time:
  9:35 refuted, 9:40 rejected), the knobs are exhausted.

Usage:
    python validate_sweep.py                 # full sweep + null
    python validate_sweep.py --nulls 200     # more placebo draws
    python validate_sweep.py --stress        # re-run the winner's autopsy
"""

from __future__ import annotations

import argparse
import itertools
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from dashboard import load_config  # noqa: E402
from r945 import FEATS, extrapolation_check, knn_probability  # noqa: E402
from validate_exit import SCRATCH  # noqa: E402

LEGS = [1, 2, 3, 4]
MIXES = ["long+short", "long-only", "short-only"]
BARS = [0.50, 0.55, 0.60, 0.65]
SELECTORS = ["densest", "max_p", "sparsest", "random"]
DAYS = ["all", "Mon", "Tue", "Wed", "Thu", "Fri"]


def scored_table(feats: pd.DataFrame, min_train: int = 200) -> pd.DataFrame:
    """One walk-forward pass: out-of-sample p_up / nd / r1 for every name-day.

    Past-only training, exactly as the live engine. Everything the sweep does
    afterwards is a re-slicing of THIS table, so a configuration can never
    accidentally get a different (or a peeking) model.
    """
    dates = sorted(feats["date"].unique())
    rows = []
    for i, d in enumerate(dates):
        if i < min_train:
            continue
        train = feats[feats["date"] < d].dropna(subset=FEATS + ["r1"])
        today = feats[feats["date"] == d]
        if len(train) < 100 or today.empty:
            continue
        for _, r in today.iterrows():
            if any(pd.isna(r[f]) for f in FEATS) or pd.isna(r["r1"]):
                continue
            rec = {f: r[f] for f in FEATS}
            ok, _ = extrapolation_check(train, rec)
            if not ok:
                continue
            res = knn_probability(train, rec)
            if res[0] is None:
                continue
            rows.append({"date": d, "t": r["t"], "p_up": res[0], "nd": res[2],
                         "r1": r["r1"]})
        if (i - min_train) % 25 == 0:
            print(f"    ... {i - min_train} sessions scored", flush=True)
    df = pd.DataFrame(rows)
    df["dow"] = pd.to_datetime(df["date"]).dt.strftime("%a")
    # the tide, so a config's return can be split into tape vs selection
    df["tide"] = df.groupby("date")["r1"].transform("median")
    return df


def to_days(tab: pd.DataFrame) -> list:
    """Pack the scored table into per-session numpy arrays, once.

    The sweep runs 1,152 configs x 101 sweeps = ~116k books. Doing a pandas
    groupby inside each one costs hours; the model output never changes between
    them, so it is packed here and every config is then pure numpy.
    """
    days = []
    for d, g in tab.groupby("date"):
        days.append({"date": d, "dow": g["dow"].iloc[0],
                     "p": g["p_up"].to_numpy(float),
                     "nd": g["nd"].to_numpy(float),
                     "r": g["r1"].to_numpy(float)})
    return days


def _take(order: np.ndarray, mask: np.ndarray, k: int) -> np.ndarray:
    """First k indices of `order` that satisfy `mask`."""
    sel = order[mask[order]]
    return sel[:k]


def book_returns(days: list, legs: int, mix: str, bar: float,
                 selector: str, dow: str, rng=None) -> np.ndarray:
    """Per-session book capture for one configuration.

    Equal weight within a side and half the book per side, matching the shipped
    allocator's SHAPE (its equal-risk refinement is a variance choice and does
    not change which side of zero a config lands on).

    `rng` non-None makes this a PLACEBO: the same names, days, pool sizes and
    weights, but the long/short assignment is drawn at random. That destroys
    the directional call and nothing else, which is exactly the comparison
    needed to tell a real winner from the best of 1,152 coin flips.
    """
    out = []
    for day in days:
        if dow != "all" and day["dow"] != dow:
            continue
        p, nd, r = day["p"], day["nd"], day["r"]
        n = len(r)
        lmask, smask = p >= bar, (1 - p) >= bar
        if rng is not None:
            # same number of qualified longs/shorts, but which names get which
            # side is random -> a book with no directional information
            perm = rng.permutation(n)
            nl, ns = int(lmask.sum()), int(smask.sum())
            lmask = np.zeros(n, bool); smask = np.zeros(n, bool)
            lmask[perm[:nl]] = True
            smask[perm[nl:nl + ns]] = True

        if selector == "densest":
            order = np.argsort(nd, kind="stable")
        elif selector == "sparsest":
            order = np.argsort(-nd, kind="stable")
        elif selector == "max_p":
            order = None                       # side-dependent, handled below
        else:
            order = (rng if rng is not None
                     else np.random.default_rng(7)).permutation(n)

        L = np.array([], int) if mix == "short-only" else _take(
            np.argsort(-p, kind="stable") if order is None else order, lmask, legs)
        S = np.array([], int) if mix == "long-only" else _take(
            np.argsort(p, kind="stable") if order is None else order, smask, legs)
        if not len(L) and not len(S):
            continue
        parts = []
        if len(L):
            parts.append(0.5 * r[L].mean())
        if len(S):
            parts.append(0.5 * -r[S].mean())
        if mix != "long+short":                # single-sided books deploy fully
            parts = [x * 2 for x in parts]
        out.append(sum(parts))
    return np.array(out)


def summarize(days: list, rng=None) -> pd.DataFrame:
    """Every configuration, one row each."""
    rows = []
    for legs, mix, bar, sel, dow in itertools.product(
            LEGS, MIXES, BARS, SELECTORS, DAYS):
        r = book_returns(days, legs, mix, bar, sel, dow, rng=rng)
        if len(r) < 30:
            continue
        sd = r.std(ddof=1)
        rows.append({"legs": legs, "mix": mix, "bar": bar, "sel": sel,
                     "dow": dow, "n": len(r), "mean": r.mean(),
                     "t": r.mean() / (sd / np.sqrt(len(r))) if sd else 0.0,
                     "pos": float((r > 0).mean())})
    return pd.DataFrame(rows)


def stress(days: list, legs: int, mix: str, bar: float, sel: str,
           dow: str) -> None:
    """Autopsy for whatever config the sweep crowned.

    A calibrated p-value says "this beat the grid's noise"; it does NOT say the
    MODEL did the beating. These four checks separate those, and any candidate
    must pass all of them before it is worth a second thought:
      quarters   -- the house bar since day-14;
      selector   -- if the k-NN ranking is doing the work, `densest` must beat
                    `random`. Random winning means the config found a subset of
                    the tape, not a skillful ordering;
      weekday    -- a lone winning weekday among six is a slice, not a rule;
      tape ctrl  -- what buying the WHOLE universe on those days pays.
    """
    dates = sorted(set(d["date"] for d in days))
    edges = np.linspace(0, len(dates), 5).astype(int)
    qs = [set(dates[edges[i]:edges[i + 1]]) for i in range(4)]
    print(f"\n=== AUTOPSY: {legs} leg(s) / {mix} / bar {bar} / {sel} / {dow} ===")
    cells = []
    for q in qs:
        r = book_returns([d for d in days if d["date"] in q], legs, mix, bar, sel, dow)
        cells.append(f"{r.mean():+.3f}%(n={len(r)})" if len(r) else "n/a")
    full = book_returns(days, legs, mix, bar, sel, dow)
    sd = full.std(ddof=1)
    print("  quarters : " + "  ".join(cells))
    print(f"  full     : {full.mean():+.4f}%  t {full.mean() / (sd / np.sqrt(len(full))):+.2f}"
          f"  n={len(full)}")
    print("  by selector (densest SHOULD lead if the model is ranking well):")
    for s in SELECTORS:
        r = book_returns(days, legs, mix, bar, s, dow)
        print(f"    {s:<9} {r.mean():+.4f}%")
    print("  by weekday:")
    for d in DAYS:
        r = book_returns(days, legs, mix, bar, sel, d)
        if len(r):
            print(f"    {d:<4} n={len(r):>3} {r.mean():+.4f}%")


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--nulls", type=int, default=100)
    ap.add_argument("--stress", action="store_true")
    ap.add_argument("--cache", default=SCRATCH)
    args = ap.parse_args(argv)

    cfg = load_config("config.yaml")
    tpath = os.path.join(args.cache, "sweep_table.csv")
    if os.path.exists(tpath):
        tab = pd.read_csv(tpath)
        print(f"scored table: reused {tpath}")
    else:
        feats = pd.read_csv(os.path.join(args.cache, "exit_feats_1h.csv"))
        print("scoring walk-forward (one pass, ~288 sessions)...", flush=True)
        tab = scored_table(feats)
        tab.to_csv(tpath, index=False)
    print(f"scored table: {len(tab):,} name-days over "
          f"{tab['date'].nunique()} sessions\n")
    days = to_days(tab)

    real = summarize(days)
    real = real.sort_values("mean", ascending=False)
    if args.stress:
        b = real.iloc[0]
        stress(days, int(b["legs"]), b["mix"], float(b["bar"]), b["sel"], b["dow"])
        return real, None
    print(f"=== {len(real)} configurations swept ===")
    print("\nTOP 12 BY MEAN BOOK CAPTURE PER SESSION")
    print(real.head(12).to_string(index=False,
          float_format=lambda v: f"{v:+.4f}"))
    print("\nBOTTOM 5 (the same sweep's losers — note the symmetry)")
    print(real.tail(5).to_string(index=False,
          float_format=lambda v: f"{v:+.4f}"))

    base = real[(real.legs == 2) & (real.mix == "long+short") &
                (real.bar == 0.55) & (real.sel == "densest") & (real.dow == "all")]
    if len(base):
        b = base.iloc[0]
        print(f"\nSHIPPED CONFIG (2 legs / both sides / 0.55 / densest / all days):"
              f"  mean {b['mean']:+.4f}%  t {b['t']:+.2f}  "
              f"positive sessions {b['pos']:.0%}"
              f"   -> rank {list(real.index).index(b.name) + 1} of {len(real)}")

    print(f"\n=== NULL CALIBRATION: {args.nulls} placebo sweeps ===")
    print("same names, days and sizes; sides assigned at random\n")
    best_null = []
    for i in range(args.nulls):
        rng = np.random.default_rng(1000 + i)
        nl = summarize(days, rng=rng)
        best_null.append(nl["mean"].max())
        if (i + 1) % 20 == 0:
            print(f"    ... {i + 1}/{args.nulls} placebo sweeps", flush=True)
    bn = np.array(best_null)
    obs = real["mean"].max()
    p = float((bn >= obs).mean())
    print(f"\n  best REAL config      : {obs:+.4f}% per session")
    print(f"  best PLACEBO config   : median {np.median(bn):+.4f}%, "
          f"90th pct {np.quantile(bn, 0.9):+.4f}%, max {bn.max():+.4f}%")
    print(f"  p-value (P[placebo best >= real best]) = {p:.3f}")
    print("\n  " + ("*** the sweep's best config is INSIDE the noise band: no "
                    "configuration\n      of this strategy has a demonstrated "
                    "edge. ***" if p > 0.05 else
                    "*** the best config CLEARS the placebo band — investigate "
                    "further ***"))
    return real, bn


if __name__ == "__main__":
    main()
