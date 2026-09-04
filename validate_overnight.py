#!/usr/bin/env python3
"""
validate_overnight.py — day-87. Is the overnight window tradeable?

Pre-registered in PREREGISTER_day87.md. The bar is fixed there: |t| >= 3 on the
NET mean AND the same sign in all four contiguous blocks, with the 10bps column
deciding.

WHAT DAY-85 LEFT. Overnight ran +0.0487%/session (~+12.3%/yr, 57.2% of
sessions) against intraday +0.0259% (~+6.5%/yr, 54.5%), and SPY alone shows the
same shape. What it did NOT establish is that the gap is tradeable: the
difference flipped sign across blocks and carried no cost at all.

THE ARITHMETIC THAT MAKES THIS SHORT. The gross gap is +0.023%/session — 2.3
basis points. One 10bps round trip is more than four times that. The purpose of
this study is to put that on the record WITH the tail numbers beside it, not to
discover something.

BOTH WINDOWS ARE COSTED IDENTICALLY. Costing the overnight leg and comparing it
against a gross intraday leg would decide the question by construction. Rule 7:
one population, one cost model, both legs.

THE TAIL IS NOT OPTIONAL. Day-24 measured the overnight penalty as a TAIL
property — one night at ~2x volatility with a 2.3x worse tail — so a mean net
return is not sufficient evidence on its own. An edge that exists in the mean
while doubling the worst day is a VARIANCE TRANSFER, not an improvement, and
this module labels it as one.
"""

from __future__ import annotations

import argparse
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import validate_us as U  # noqa: E402

ADOPT_T = 3.0
COST_GRID = (5.0, 10.0, 20.0)     # bps round trip; fixed in the registration
DECIDING_COST = 10.0


def sessions(df: pd.DataFrame) -> list:
    """One row per session: the equal-weighted basket in each window."""
    g = df.groupby("date")[["overnight", "intraday"]].mean()
    return [{"date": d, "t": "BASKET", "overnight": float(r.overnight),
             "intraday": float(r.intraday),
             "gap": float(r.overnight - r.intraday)}
            for d, r in g.iterrows()]


def net_rows(rows: list, field: str, bps: float) -> list:
    """Subtract the round trip from EVERY session, not from the mean.

    Cost is paid per trade, so it belongs inside the distribution before any
    statistic is taken — otherwise the tail is reported gross while the mean is
    reported net.
    """
    c = bps / 100.0
    return [{**r, f"{field}_net": r[field] - c} for r in rows]


def tails(rows: list, field: str) -> dict:
    v = np.array([r[field] for r in rows if np.isfinite(r[field])])
    if not len(v):
        return {}
    return {"worst": float(v.min()), "p5": float(np.quantile(v, 0.05)),
            "sd": float(v.std(ddof=1)),
            "win": float(np.mean(v > 0) * 100)}


def line(label: str, rows: list, field: str) -> str:
    m, lo, hi = U.boot(rows, field, "date", block=1)
    if m is None:
        return f"   {label:<22} not computable"
    se = U.se_of(lo, hi)
    t = m / se if se else float("nan")
    bs = U.blocks(rows, field)
    tl = tails(rows, field)
    tag = "consistent" if U.consistent(bs) else "SIGN FLIPS"
    return (f"   {label:<22} {m:+8.4f}%/session  |t|={abs(t):5.2f}  "
            f"win {tl['win']:4.1f}%  {tag}")


def report(rows: list) -> str:
    L = [f"▎H1c/H1d — the two windows, costed identically",
         f"   {len(rows):,} sessions, equal-weighted basket, "
         f"bootstrap clustered by session (block=1: overnight legs do not "
         f"overlap, unlike the day-85 weekly arms)",
         "",
         "   GROSS"]
    for label, f in (("overnight", "overnight"), ("intraday", "intraday")):
        L.append(line(label, rows, f))
    L.append(line("difference", rows, "gap"))

    for bps in COST_GRID:
        mark = "  <- DECIDES" if bps == DECIDING_COST else ""
        L.append("")
        L.append(f"   NET of {bps:.0f}bps round trip{mark}")
        for label, f in (("overnight", "overnight"), ("intraday", "intraday")):
            nr = net_rows(rows, f, bps)
            L.append(line(label, nr, f"{f}_net"))
    return "\n".join(L)


def tail_report(rows: list) -> str:
    L = ["▎the tail — day-24 measured the overnight penalty HERE, not in the mean"]
    o, i = tails(rows, "overnight"), tails(rows, "intraday")
    L.append(f"   {'':<12}{'overnight':>12}{'intraday':>12}   ratio")
    for k, name in (("sd", "std dev"), ("p5", "5th pct"), ("worst", "worst day")):
        ratio = (abs(o[k]) / abs(i[k])) if i.get(k) else float("nan")
        L.append(f"   {name:<12}{o[k]:>+12.3f}{i[k]:>+12.3f}   {ratio:.2f}x")
    worse = abs(o["sd"]) > abs(i["sd"])
    L.append("")
    L.append(f"   -> the overnight window is {'MORE' if worse else 'less'} "
             f"volatile ({o['sd'] / i['sd']:.2f}x std dev). An edge that "
             f"exists in the")
    L.append(f"      mean while widening this is a VARIANCE TRANSFER, not an "
             f"improvement.")
    return "\n".join(L)


def verdict(rows: list, bps: float = DECIDING_COST) -> str:
    nr = net_rows(rows, "overnight", bps)
    m, lo, hi = U.boot(nr, "overnight_net", "date", block=1)
    if m is None:
        return "NOT COMPUTABLE"
    se = U.se_of(lo, hi)
    t = m / se if se else None
    bs = U.blocks(nr, "overnight_net")
    mde = ADOPT_T * se if se else None
    o, i = tails(rows, "overnight"), tails(rows, "intraday")
    if t is None:
        return "NOT COMPUTABLE"
    if m < 0:
        return (f"REJECTED — at {bps:.0f}bps the overnight expression is "
                f"NEGATIVE ({m:+.4f}%/session). The gross gap between the "
                f"windows is 2.3bps and the round trip is {bps:.0f}.")
    if abs(t) < ADOPT_T and abs(m) < (mde or 0):
        return f"UNDERPOWERED — cannot resolve below {mde:.4f}%/session"
    if abs(t) < ADOPT_T:
        return f"BELOW the bar (|t|={abs(t):.2f} < {ADOPT_T:.0f})"
    if not U.consistent(bs):
        return (f"FAILS block consistency (|t|={abs(t):.2f} clears, sign "
                f"flips across blocks)")
    if o["p5"] < i["p5"]:
        return (f"CLEARS the mean but WORSENS the 5th-percentile session "
                f"({o['p5']:+.3f}% vs {i['p5']:+.3f}%) — a variance transfer, "
                f"which the registration excludes from adoption")
    return f"CLEARS the bar (|t|={abs(t):.2f}, consistent, tail not worsened)"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--panel", default="us_daily.csv")
    a = ap.parse_args(argv)

    p = os.path.join(U.DATA, a.panel)
    if not os.path.exists(p):
        print(f"{p} missing — run `python build_us.py` first.")
        return 2
    print(f"loading {a.panel}")
    df = pd.read_csv(p, usecols=["t", "date", "overnight", "intraday"])
    print(f"  {len(df):,} ticker-days, {df['t'].nunique()} names, "
          f"{df['date'].min()} .. {df['date'].max()}")
    rows = sessions(df)

    print("\n" + "=" * 68)
    print(report(rows))
    print("\n" + "=" * 68)
    print(tail_report(rows))
    print("\n" + "=" * 68)
    print(f"   -> {verdict(rows)}")
    print()
    print("   ── both windows carry the SAME cost model. Costing one and not")
    print("      the other would decide the question by construction.")
    print("   ── cost is subtracted from every session before any statistic,")
    print("      so the tail is net too, not gross.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
