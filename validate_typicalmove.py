#!/usr/bin/env python3
"""
validate_typicalmove.py — re-derive cost.TYPICAL_MOVE_PCT from the ledger.

WHY THIS EXISTS. `TYPICAL_MOVE_PCT = 0.97` is MEASURED — day-70 put |r1| on
this universe at 0.97% (non-event) to 1.11% (after a filing), and the lower
figure was taken so the drag is never flattered. But no script re-derived it,
so it sat in `constants.py` as an unprovenanced measured value: a claim wearing
a measurement's clothes, exactly the state day-79's constants were in for two
days before anyone could check them.

It is not a cosmetic number. Every "spread = N% of the typical move" line the
report prints divides by it, so if the universe's volatility has drifted the
report is quoting the wrong denominator for what the spread costs.

WHAT IS MEASURED. The median absolute 9:46-to-close capture over every scored
leg in the ledger, which is the same window and the same universe the constant
describes. The MEDIAN, not the mean: a handful of violent sessions would drag a
mean upward and flatter the spread by making it look like a smaller share of a
bigger move.

Reported alongside: the mean, the interquartile range, and a session-clustered
interval on the median, because legs on one day share that day's move.
"""

from __future__ import annotations

import argparse
import os
import sys
from collections import defaultdict

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import ledger as L  # noqa: E402

BOOT = 4000
SEED = 0


def moves(rows: list) -> list:
    """|capture| per scored leg, with its session, in percent."""
    out = []
    for r in rows:
        c = L.capture(r)
        if c is None:
            continue
        out.append((r["date"], abs(c)))
    return out


def boot_median(pairs: list, n: int = BOOT, seed: int = SEED) -> tuple:
    """Median with a SESSION-clustered 95% interval.

    Legs on one day share that day's market move, so resampling legs would
    treat one session's worth of correlated magnitudes as independent draws.
    """
    by = defaultdict(list)
    for d, m in pairs:
        by[d].append(m)
    days = sorted(by)
    if len(days) < 5:
        return (None, None, None)
    rng = np.random.default_rng(seed)
    vals = []
    for _ in range(n):
        pick = rng.integers(0, len(days), size=len(days))
        draw = [m for i in pick for m in by[days[i]]]
        if draw:
            vals.append(float(np.median(draw)))
    if not vals:
        return (None, None, None)
    return (float(np.median([m for _, m in pairs])),
            float(np.quantile(vals, 0.025)), float(np.quantile(vals, 0.975)))


def run(rows: list = None) -> dict:
    rows = rows if rows is not None else L.load()
    pairs = moves(rows)
    if not pairs:
        raise SystemExit("no scored legs in the ledger — nothing to re-derive")
    m = [x for _, x in pairs]
    med, lo, hi = boot_median(pairs)
    return {"n": len(pairs), "sessions": len({d for d, _ in pairs}),
            "median": med, "ci": (lo, hi),
            "mean": float(np.mean(m)),
            "q1": float(np.quantile(m, 0.25)),
            "q3": float(np.quantile(m, 0.75))}


def report(r: dict, shipped: float) -> str:
    lo, hi = r["ci"]
    ci = f"[{lo:.2f}%, {hi:.2f}%]" if lo is not None else "[unavailable]"
    agrees = lo is not None and lo <= shipped <= hi
    L_ = ["▎TYPICAL INTRADAY MOVE — re-derived from the ledger",
          f"   {r['n']} scored legs across {r['sessions']} sessions "
          f"(9:46 -> close, this universe)",
          f"   median |capture|  {r['median']:.2f}%   95% {ci}  "
          f"(sessions clustered)",
          f"   mean {r['mean']:.2f}%   IQR {r['q1']:.2f}%-{r['q3']:.2f}%",
          "",
          f"   shipped constant  cost.TYPICAL_MOVE_PCT = {shipped:.2f}%",
          f"   -> the interval {'CONTAINS' if agrees else 'EXCLUDES'} the "
          f"shipped value"]
    if not agrees and lo is not None:
        L_.append("   ⚠ the shipped constant is outside its own re-derivation. "
                  "Every 'spread as a")
        L_.append("     share of the typical move' line divides by it. Do not "
                  "change it here —")
        L_.append("     changing a constant inside the script that checks it "
                  "defeats the check.")
    L_.append("   ── the MEDIAN, not the mean: a few violent sessions would "
              "flatter the spread")
    L_.append("      by making it a smaller share of a bigger move.")
    return "\n".join(L_)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ledger", default=None)
    a = ap.parse_args(argv)
    import cost
    rows = L.load(a.ledger) if a.ledger else L.load()
    print(report(run(rows), cost.TYPICAL_MOVE_PCT))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
