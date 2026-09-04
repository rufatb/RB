#!/usr/bin/env python3
"""
validate_holdout.py — day-86. H5 on names the day-85 study never saw.

Pre-registered in PREREGISTER_day86.md. The bar is INHERITED from day-85 and
not restated loosely: |t| >= 3 block-bootstrapped at block = horizon, the same
sign in all four contiguous blocks, outside placebo, and — because H5's
profitable orientation buys losers — clearing day-32's three dissolving tests.

WHY A HELD-OUT SET AND NOT JUST A BIGGER ONE. Day-85 left H5 at |t| = 2.46,
short of the bar. Adding names to the SAME universe would put the original 578
inside the wider sample, so the re-run would re-read the draw that generated
the hypothesis and report a tighter interval around the same numbers. That is
not confirmation. Day-52 did this correctly — a TSX-generated hypothesis taken
to 500 S&P names — and this is that shape. The original 578 are excluded, and
a disjointness assertion fails the run if any leak in.

THE FAILURE THIS IS BUILT TO HAVE. Survivorship worsens as the universe widens:
smaller names delist more often and the delisted ones are absent, while H5's
profitable direction is long the most beaten-down decile — exactly where they
would have been. Day-85's size test already showed the effect 3.9x larger in
the smallest liquidity quartile than the largest.

So the liquidity gradient is not a footnote here, it is the second hypothesis.
Registered in advance: if the effect GROWS as the universe extends into smaller
names, that is the survivorship signature and counts AGAINST H5. A result that
lives only in the small quartiles does not clear whatever its |t|.

THE SIGN IS PRE-COMMITTED to day-85's, which is NEGATIVE (names near their
52-week high underperform). A significant result with the opposite sign is a
failed replication, not a discovery.
"""

from __future__ import annotations

import argparse
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import validate_us as U  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "data")
EXPECTED_SIGN = -1.0        # day-85's sign, committed before this run


class SampleLeak(AssertionError):
    """A day-85 name reached the replication set. Never downgraded."""


def load_split() -> tuple:
    """The held-out panel and the original name list, verified disjoint."""
    hp = os.path.join(DATA, "us_daily_holdout.csv")
    op = os.path.join(DATA, "us_daily.csv")
    for p in (hp, op):
        if not os.path.exists(p):
            raise FileNotFoundError(
                f"{p} missing — run `python build_us.py` (and the --skip 600 "
                f"--tag _holdout build) first.")
    orig = set(pd.read_csv(op, usecols=["t"])["t"].unique())
    df = pd.read_csv(hp).sort_values(["t", "date"]).reset_index(drop=True)
    leak = sorted(set(df["t"].unique()) & orig)
    if leak:
        raise SampleLeak(
            f"{len(leak)} day-85 names are in the replication set "
            f"({', '.join(leak[:8])}…). This would re-read the draw that "
            f"produced the hypothesis rather than replicate it.")
    for col in ("daily", "intraday", "overnight"):
        df[f"mkt_{col}"] = df.groupby("date")[col].transform("mean")
        df[f"rel_{col}"] = df[col] - df[f"mkt_{col}"]
    return df, orig


def prepare(df: pd.DataFrame) -> pd.DataFrame:
    df = U.add_forward(df, horizons=(5, 20))
    df["hi252"] = df.groupby("t", sort=False)["close"].transform(
        lambda s: s.rolling(252, min_periods=200).max())
    df["prox"] = df["close"] / df["hi252"]
    df["dv"] = df["close"] * df["volume"]
    return df


def by_quartile(df: pd.DataFrame, horizon: int) -> list:
    """H5b: the effect per liquidity quartile, on the held-out names.

    Registered prediction — an effect that grows as the names get smaller is
    the survivorship signature, not a stronger finding.
    """
    df = df.copy()
    df["liq"] = df.groupby("date")["dv"].transform(
        lambda x: pd.qcut(x.rank(method="first"), 4, labels=False,
                          duplicates="drop"))
    out = []
    for q in range(4):
        rows = U.decile_rows(df[df["liq"] == q], "prox", horizon, True)
        if not rows:
            out.append((q, None, None))
            continue
        m, lo, hi = U.boot(rows, "spread", "date", block=horizon)
        out.append((q, m, U.se_of(lo, hi)))
    return out


def gradient_verdict(qs: list) -> str:
    """Small-quartile-only, or a monotone growth into small caps, fails."""
    vals = [m for _, m, _ in qs if m is not None]
    if len(vals) < 4:
        return "NOT COMPUTABLE — a liquidity quartile is too thin"
    small, large = abs(vals[0]), abs(vals[3])
    if not (all(v > 0 for v in vals) or all(v < 0 for v in vals)):
        return "FAILS — the sign flips across liquidity quartiles"
    if large == 0 or small / max(large, 1e-9) >= 2.0:
        return (f"FAILS the registered gradient rule — {small / max(large, 1e-9):.1f}x "
                f"larger in the smallest quartile than the largest, which is "
                f"the survivorship signature")
    return (f"passes — {small / max(large, 1e-9):.1f}x small-vs-large, not "
            f"concentrated in the illiquid names")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--spread", type=float, default=U.SPREAD_BPS * 2)
    a = ap.parse_args(argv)

    print("loading the HELD-OUT panel (day-85 names excluded by assertion)")
    df, orig = load_split()
    print(f"  {len(df):,} ticker-days, {df['t'].nunique()} names, "
          f"{df['date'].min()} .. {df['date'].max()}")
    print(f"  disjoint from the {len(orig)} day-85 names: verified")
    df = prepare(df)

    for h in (5, 20):
        rows = U.decile_rows(df, "prox", h, long_high=True)
        if not rows:
            print(f"\n▎H5a {h}d — no usable sessions")
            continue
        d = U.dissolving_tests(df, "prox", h, True)
        print("\n" + "=" * 68)
        print(U.report(f"H5a REPLICATION — 52-week-high proximity, {h}d, "
                       f"held-out names", rows, "spread", "date",
                       placebo=U.placebo_xs(df, "prox", h, True),
                       spread_bps=a.spread, extra=d, block=h,
                       dissolved=U.failed_tests(d)))
        m, lo, hi = U.boot(rows, "spread", "date", block=h)
        if m is not None:
            same = np.sign(m) == EXPECTED_SIGN
            print(f"   sign       day-85 committed {EXPECTED_SIGN:+.0f}; "
                  f"held-out is {np.sign(m):+.0f} — "
                  f"{'replicates' if same else 'FAILED REPLICATION'}")

        print(f"\n▎H5b liquidity gradient, {h}d — the registered decider")
        qs = by_quartile(df, h)
        for q, mq, seq in qs:
            label = ["smallest", "2nd", "3rd", "largest"][q]
            if mq is None:
                print(f"   {label:<9} not computable")
            else:
                print(f"   {label:<9} {mq:+7.3f}%   SE {seq:.3f}"
                      f"   |t|={abs(mq / seq):.2f}" if seq else
                      f"   {label:<9} {mq:+7.3f}%")
        print(f"   -> {gradient_verdict(qs)}")

    print("\n" + "=" * 68)
    print("   ── the original 578 names are NOT in this sample. A superset")
    print("      would have re-read the draw that produced the hypothesis.")
    print("   ── survivorship worsens as the universe widens, and H5 buys the")
    print("      most beaten-down decile. The gradient rule is registered in")
    print("      PREREGISTER_day86.md and is not negotiable after the fact.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
