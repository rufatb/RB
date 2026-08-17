#!/usr/bin/env python3
"""
build_pool.py — fetch the wide TSX universe once and cache its feature tables.

Separated from the analysis so the slow part (220 names x 2 intervals) runs
once and every later experiment is instant. Two tables:

  pool_5m.csv  — 60 sessions, entry = close of the 3rd 5m bar (09:45), native
                 to the live engine's decision point.
  pool_1h.csv  — ~500 sessions (2 years), entry = close of the 1st hourly bar
                 (10:30). Coarser entry, but 14x the sessions.

TSX hourly volume used to be unusable (day-22 measured 86% of bars zeroed).
Re-measured 2026-08-13: ~13% zeroed on 1h and ~1% on 5m.

DAY-43 CORRECTION — BOTH numbers are right and the conclusion drawn from the
13% was WRONG. The zeros are not spread across the session, they are almost
entirely the FIRST hourly bar. Measured over 720 days on 5 large caps:

    all 1h bars      12.4-12.6% zeroed      <- the reassuring number
    FIRST bar of day 86.1-86.8% zeroed      <- the one that matters
    later bars        0.0- 0.3% zeroed

The 1h pool's entry IS the first bar, so 85.9% of its `v15` values are zero and
`vp` is NOT computable on this panel. Worse, it fails QUIETLY: every ticker's
median v15 is 0, so the usual `v15 / (median or 1)` divides by 1 and yields RAW
SHARE VOLUME — cross-sectionally meaningless (a big name's raw count against a
small name's) and exactly zero on 86% of rows. Any 1h-pool result computed with
`vp` was computed on that, not on volume pace. Comparisons BETWEEN arms of the
same study are unaffected — both arms carried the same broken column — but no
1h result may be described as testing the shipped THREE-feature engine.

`vp` is computable on the 5m pool (0.0% zeroed) and nowhere else. Use
`validate_ceiling.usable_feats()` rather than assuming a column is populated.

SURVIVORSHIP: the constituent list is TODAY's S&P/TSX Composite applied
backwards, so names delisted during the window are absent and recent additions
are present before they joined. That inflates ABSOLUTE returns. It does not
invalidate a comparison BETWEEN pool sizes drawn from the same list, which is
what this data is for — every arm carries the same bias.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.request
from concurrent.futures import ThreadPoolExecutor

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from adapters import YahooDirectAdapter  # noqa: E402
from validate_exit import SCRATCH  # noqa: E402

WIKI = "https://en.wikipedia.org/wiki/S%26P/TSX_Composite_Index"


def constituents(cache: str) -> list:
    """S&P/TSX Composite tickers in Yahoo form (BCE -> BCE.TO, AP.UN -> AP-UN.TO)."""
    path = os.path.join(cache, "tsx_universe.json")
    if os.path.exists(path):
        return json.load(open(path))
    req = urllib.request.Request(WIKI, headers={"User-Agent": "Mozilla/5.0"})
    html = urllib.request.urlopen(req, timeout=60).read().decode("utf8", "replace")
    out = []
    for sym in re.findall(r">([A-Z]{1,5}(?:\.[A-Z]{1,3})?)</a></td>", html):
        y = sym.replace(".", "-") + ".TO"
        if y not in out:
            out.append(y)
    json.dump(out, open(path, "w"))
    return out


def rows_at(bars: pd.DataFrame, ticker: str, i: int, min_bars: int) -> list:
    """Features known at bar `i`'s close; outcome from there to the close."""
    out, prev_close = [], None
    for d, day in bars.groupby(bars.index.date):
        day = day.sort_index()
        if len(day) < max(min_bars, i + 3):
            if len(day):
                prev_close = day["Close"].iloc[-1]
            continue
        o = float(day["Open"].iloc[0])
        pe = float(day["Close"].iloc[i])
        c = float(day["Close"].iloc[-1])
        gap = (o / prev_close - 1) * 100 if prev_close else None
        prev_close = c
        if not o or not pe:
            continue
        out.append({"t": ticker, "date": str(d), "gap": gap,
                    "r0": (pe / o - 1) * 100,
                    "v15": float(day["Volume"].iloc[:i + 1].fillna(0).sum()),
                    "px": pe, "r1": (c / pe - 1) * 100})
    return out


def build(universe: list, interval: str, rng: str, entry_i: int,
          min_bars: int, out_path: str, workers: int = 16) -> pd.DataFrame:
    a = YahooDirectAdapter(exchange_tz="America/Toronto")
    failed = []

    def one(t):
        try:
            b = a._bars_df(a._chart(t, interval, rng))
            return t, b
        except Exception:
            failed.append(t)
            return t, pd.DataFrame()

    rows = []
    with ThreadPoolExecutor(max_workers=workers) as ex:
        for n, (t, b) in enumerate(ex.map(one, universe), 1):
            if not b.empty:
                rows += rows_at(b, t, entry_i, min_bars)
            if n % 40 == 0:
                print(f"    {n}/{len(universe)} fetched, {len(rows):,} rows",
                      flush=True)
    df = pd.DataFrame(rows)
    df.to_csv(out_path, index=False)
    print(f"  {interval}: {len(df):,} rows / {df['t'].nunique()} names / "
          f"{df['date'].nunique()} sessions  ({len(failed)} fetch failures)")
    return df


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--cache", default=SCRATCH)
    args = ap.parse_args(argv)
    os.makedirs(args.cache, exist_ok=True)
    uni = constituents(args.cache)
    print(f"universe: {len(uni)} S&P/TSX Composite names")
    for interval, rng, i, mb, name in (
            ("5m", "60d", 2, 20, "pool_5m.csv"),
            ("1h", "720d", 0, 5, "pool_1h.csv")):
        p = os.path.join(args.cache, name)
        if os.path.exists(p):
            print(f"  {name}: cached")
            continue
        print(f"  building {name} ...", flush=True)
        build(uni, interval, rng, i, mb, p)


if __name__ == "__main__":
    main()
