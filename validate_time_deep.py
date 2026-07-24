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

RESULTS (2026-07-24) — 9:45 STANDS.
    time    legs   hit    capture   per-quarter capture
    09:35    431  49.2%   -0.021%   -0.097 / -0.103 / -0.098 / +0.199
    09:40    447  54.4%   +0.125%   -0.000 / +0.051 / +0.247 / +0.191
    09:45    439  54.4%   +0.094%   -0.008 / +0.042 / +0.192 / +0.135
    09:50    443  49.7%   +0.004%   -0.128 / -0.020 / +0.177 / -0.014
    10:00    425  48.0%   -0.025%   -0.037 / +0.028 / -0.069 / -0.029
    10:30    385  50.6%   +0.016%   -0.074 / +0.081 / -0.066 / +0.108

  * 09:35 REFUTED as the "earlier = more opportunity / better entries"
    candidate: hit falls below a coin flip (49.2%), capture is negative in
    3 of 4 quarters, and opportunity is LOWER not higher (1.74 vs 1.78
    legs/session) — two 5m bars do not resolve the opening rotation.
  * 09:40 met the pre-registered bar on the unpaired comparison (beat 9:45
    on capture in 4/4 quarters, hit >=50% in 4/4) — so it got the decisive
    PAIRED test (paired_time.py), which isolates the two channels the
    advantage could come from:
      - same pick, entry 5 min earlier (n=72): mean diff -0.0120%,
        t = -0.60, 9:40 better on only 32/72 legs -> earlier entry is
        worth NOTHING (slightly negative).
      - different pick (n=341): 9:40 +0.077% / 53% hit vs 9:45 +0.078% /
        55% hit -> selection is IDENTICAL.
    Neither channel carries an edge, so the aggregate +0.031pp was
    composition noise. The two times also disagree across datasets (the
    60-day Yahoo/TSX run scored 9:40 at 48.9%), the classic instability
    signature. NOT ADOPTED.
  * Decision: the run time stays 9:46 ET (first moment the 9:45 bar is
    complete). Eighth candidate improvement tested and rejected.
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
