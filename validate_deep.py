#!/usr/bin/env python3
"""
validate_deep.py — the deep-data validation (day-13/14): ~1 year of 5-minute
bars for the US cross-listings of the TSX universe, pulled from TwelveData
(TWELVEDATA_API_KEY env var; the key is NEVER stored in this repo).

WHY US lines: the free tier gates TSX symbols, but 19/21 universe names are
dual-listed (same company, same flows, USD line). For VALIDATING which
mechanics are real — base rates, ramp-fade, qualification edge, selector
gradients — the US line is an independent, deeper replication sample
(~250 sessions/name vs Yahoo's 60-day cap). CAVEAT (do not strip): levels
and prices from US lines must never feed the live TSX report; FX moves the
lines apart intraday even though direction correlates strongly.

PRE-REGISTERED PROTOCOL (written before results were seen):
  Periods: unique sessions split into 4 equal contiguous calendar blocks.
  A claim VALIDATES only if directionally consistent in ALL FOUR periods.
  Q1 base rate P(close > 9:45 price)
  Q2 ramp-fade: P(fade | first-15m > +0.5%) and bounce: P(up | < -0.5%)
  Q3 the 0.55-bar walk-forward k-NN qualification: hit vs the period base
  Q4 pair selectors (densest vs max-P): hit + capture per period
This protocol exists because three in-window "edges" (68% selector, breadth,
crowding) evaporated under window rolls — see STRATEGY.md days 9-13.

RESULTS (2026-07-16, first run — recorded so the verdicts are permanent):
  Q1 base rate: 50.4-54.7% by quarter (mild long drift, regime-dependent).
  Q2 REFUTED: ramp-fade. Fade after +0.5% ramps = 45.4/50.5/42.7/47.4% —
     below 50% in 3 of 4 quarters. The 60d "61% fade" was a window mirage.
  Q3 NOT VALIDATED: the 0.55-bar qualified pool beat its naive-side base in
     only 3 of 4 quarters (P1: 47.3% vs 53.3% — worse). No pool-level edge.
  Q4 VALIDATED (the only one): densest pair leg beat the pool AND max-P in
     all four quarters (54.7/54.3/56.0/52.9%; capture +0.024/+0.060/+0.121/
     +0.150%). Pooled: 239/439 = 54.4%, z=1.86 vs coin (p≈0.03), weighted
     capture +0.094%/leg PRE-COST. Real, thin, marginal — state it exactly
     that way.
"""

import json
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import validate_pair as vp
from dashboard import load_config

DATA_DIR = os.environ.get(
    "TD_DATA_DIR",
    "/tmp/claude-0/-home-user-RB/d95b4cd3-d26b-5086-a494-1dd8151521a7/scratchpad/td_data")


def require_data(where: str = None) -> str:
    """The bar cache, or an actionable message. Never a bare FileNotFoundError.

    DAY-82. The default above is a SCRATCHPAD path belonging to a session that
    ended long ago, and the container is reset between sessions — so this
    harness and the three that import it could not re-run at all, and said so
    only as `FileNotFoundError: .../td_data`. The inventory claimed these files
    were the reproducibility layer; for four of them that claim was false.

    The data is not recoverable from this repo (it was never committed — the
    5-minute bar cache is large and came from a paid feed). Point TD_DATA_DIR
    at a rebuilt cache to re-run. Saying that plainly is the difference between
    a harness that is BLOCKED and one that is broken.
    """
    d = where or DATA_DIR
    if not os.path.isdir(d):
        raise SystemExit(
            f"{os.path.basename(sys.argv[0]) or 'this harness'} needs the "
            f"5-minute bar cache and it is not present.\n"
            f"  looked in : {d}\n"
            f"  fix       : set TD_DATA_DIR to a directory of session JSON "
            f"files, e.g.\n"
            f"              TD_DATA_DIR=/path/to/td_data python "
            f"{os.path.basename(sys.argv[0])}\n"
            f"  note      : the default path is a scratchpad from an earlier "
            f"session and is gone.\n"
            f"              The cache was never committed, so this study "
            f"cannot be re-derived\n"
            f"              from this repository alone. See INVENTORY.md.")
    return d


def load_bars(path):
    d = json.load(open(path))
    rows = d["values"]
    df = pd.DataFrame(rows)
    df["datetime"] = pd.to_datetime(df["datetime"]).dt.tz_localize("America/New_York")
    df = df.set_index("datetime").sort_index()
    out = pd.DataFrame({
        "Open": df["open"].astype(float), "High": df["high"].astype(float),
        "Low": df["low"].astype(float), "Close": df["close"].astype(float),
        "Volume": df["volume"].astype(float)})
    # regular session only — extended-hours bars would corrupt bar-index math
    out = out.between_time("09:30", "15:55")
    return d["tsx"], out


def main():
    import r945
    cfg = load_config(os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.yaml"))
    rows = []
    for f in sorted(os.listdir(DATA_DIR)):
        if not f.endswith(".json"):
            continue
        tsx, bars = load_bars(os.path.join(DATA_DIR, f))
        rows += r945.session_rows(bars, tsx)
    df = pd.DataFrame(rows)
    dates = sorted(df["date"].unique())
    print(f"deep dataset: {len(df)} ticker-sessions, {df['t'].nunique()} names, "
          f"{len(dates)} sessions ({dates[0]} .. {dates[-1]})")

    # 4 contiguous calendar blocks
    blocks = np.array_split(np.array(dates), 4)
    block_of = {d: i for i, blk in enumerate(blocks) for d in blk}
    df["block"] = df["date"].map(block_of)

    print("\nQ1 base rate P(close > 9:45 px) per period:")
    for i in range(4):
        s = df[df["block"] == i]
        print(f"  P{i+1} ({blocks[i][0]}..{blocks[i][-1]}): "
              f"{(s['r1'] > 0).mean()*100:.1f}% (n={len(s)})")

    print("\nQ2 ramp-fade / dip-bounce per period:")
    for i in range(4):
        s = df[df["block"] == i]
        ramp = s[s["r0"] > 0.5]
        dip = s[s["r0"] < -0.5]
        print(f"  P{i+1}: fade after ramp>+0.5%: {(ramp['r1'] < 0).mean()*100:.1f}% "
              f"(n={len(ramp)}) | up after dip<-0.5%: {(dip['r1'] > 0).mean()*100:.1f}% "
              f"(n={len(dip)})")

    print("\nQ3/Q4 walk-forward qualification + selectors (this takes a minute)...")
    day_log = vp.walk_forward(df, cfg)
    for i in range(4):
        legs_d, legs_p, allq = [], [], []
        base = df[df["block"] == i]
        base_up = (base["r1"] > 0).mean()
        for dl in day_log:
            if block_of.get(dl["date"]) != i:
                continue
            allq += dl["longs"] + dl["shorts"]
            for side in ("longs", "shorts"):
                if dl[side]:
                    legs_d.append(min(dl[side], key=lambda b: b["nd"]))
                    legs_p.append(max(dl[side], key=lambda b: b["sided"]))
        if not allq:
            print(f"  P{i+1}: no qualified picks (training warm-up)")
            continue
        sided_base = max(base_up, 1 - base_up)
        print(f"  P{i+1}: qualified {np.mean([b['hit'] for b in allq])*100:.1f}% "
              f"(n={len(allq)}, naive-side base {sided_base*100:.1f}%) | "
              f"densest {np.mean([b['hit'] for b in legs_d])*100:.1f}% "
              f"capt {np.mean([b['capt'] for b in legs_d]):+.3f} (n={len(legs_d)}) | "
              f"max-P {np.mean([b['hit'] for b in legs_p])*100:.1f}% "
              f"capt {np.mean([b['capt'] for b in legs_p]):+.3f}")
    print("\nVERDICT RULE: a claim validates only if directionally consistent in "
          "ALL FOUR periods above.")


if __name__ == "__main__":
    main()
