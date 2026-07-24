#!/usr/bin/env python3
"""
validate_time_deep.py — is 9:45 the right decision time? (YEAR data version)

Day-21. The original validate_time.py raced decision times on the 60-day
Yahoo window; day-12 taught us 60-day windows produce mirages, so this
re-runs the whole question on the 1-year US-twin dataset (~5,160
ticker-sessions) under the pre-registered four-quarter rule.

For each candidate decision bar i (close of the i-th 5m bar => 9:30+5*(i+1)):
  features known at T: r0 = open->T return, gap, vp = relative volume to T
  outcome:             T -> session close
  machinery:           identical walk-forward k-NN, 0.55 bar, peer gate,
                       densest-leg pair selection as the live report
Reported per quarter: pair-leg hit + capture, plus opportunity count and the
median remaining move (how much day is left to capture).

ADOPTION BAR (pre-registered, written before results): a challenger time
replaces 9:45 only if it beats 9:45 on capture in >=3 of 4 quarters AND its
hit rate is >=50% in all four. Anything else: 9:45 stands.
"""

import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import r945
import validate_deep as vd
from dashboard import load_config

TIMES = [(0, "09:35"), (1, "09:40"), (2, "09:45 *current*"), (3, "09:50"),
         (5, "10:00"), (11, "10:30")]


def session_rows_at(bars: pd.DataFrame, ticker: str, i: int) -> list:
    """r945.session_rows with the decision point at bar index i."""
    rows, prev_close = [], None
    for d, day in bars.groupby(bars.index.date):
        day = day.sort_index()
        if len(day) < max(10, i + 3):
            if len(day):
                prev_close = day["Close"].iloc[-1]
            continue
        o, pT, c = day["Open"].iloc[0], day["Close"].iloc[i], day["Close"].iloc[-1]
        gap = (o / prev_close - 1) * 100 if prev_close else None
        prev_close = c
        if not o or not pT:
            continue
        rows.append({"t": ticker, "date": str(d), "gap": gap,
                     "r0": (pT / o - 1) * 100,
                     "v15": float(day["Volume"].iloc[:i + 1].sum()),
                     "r1": (c / pT - 1) * 100})
    return rows


def pair_legs(df: pd.DataFrame, cfg: dict) -> list:
    """Walk-forward densest pair legs (live machinery, live peer gate)."""
    import validate_pair as vp
    day_log = vp.walk_forward(df, cfg)
    legs = []
    for dl in day_log:
        for side in ("longs", "shorts"):
            if dl[side]:
                legs.append(min(dl[side], key=lambda b: b["nd"]))
    return legs, [dl["date"] for dl in day_log]


def main():
    cfg = load_config(os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.yaml"))
    raw = []
    for f in sorted(os.listdir(vd.DATA_DIR)):
        if f.endswith(".json"):
            raw.append(vd.load_bars(os.path.join(vd.DATA_DIR, f)))
    print(f"deep dataset: {len(raw)} names")

    print(f"\n{'time':<16}{'legs':>5} {'hit':>6} {'capt':>8} | per-quarter capture (hit%)")
    for i, label in TIMES:
        rows = []
        for tsx, bars in raw:
            rows += session_rows_at(bars, tsx, i)
        df = pd.DataFrame(rows)
        legs, days = pair_legs(df, cfg)
        if not legs:
            print(f"{label:<16} no qualified legs")
            continue
        blocks = np.array_split(np.array(days), 4)
        blk = {d: k for k, b in enumerate(blocks) for d in b}
        cells = []
        for q in range(4):
            L = [b for b in legs if blk[b["date"]] == q]
            cells.append(f"Q{q+1} {np.mean([b['capt'] for b in L]):+.3f}% "
                         f"({np.mean([b['hit'] for b in L])*100:.0f}%)" if L else f"Q{q+1} n=0")
        print(f"{label:<16}{len(legs):>5} {np.mean([b['hit'] for b in legs])*100:>5.1f}% "
              f"{np.mean([b['capt'] for b in legs]):>+7.3f}% | " + "  ".join(cells))
        print(f"{'':16}      opportunity: {len(legs)/len(days):.2f} legs/session · "
              f"median remaining move {df['r1'].abs().median():.2f}%")


if __name__ == "__main__":
    main()
