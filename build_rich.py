#!/usr/bin/env python3
"""
build_rich.py — a WIDE feature panel from bars we already download for free.

WHY THIS EXISTS. Day-43 established that `r0`/`gap`/`vp` carry no usable signal
(gradient boosting AUC 0.5022, z=1.32, on 122,234 out-of-sample rows, while the
same harness detects a planted 52% coin at z=15). The conclusion drawn from it
was "only new paid data can help". That was too quick, and this file is the
correction: the engine downloads full OHLCV bars every morning and then reduces
them to three scalars. Everything else in those bars — the SHAPE of the opening
range, where the price sits inside it, how today's move compares to the name's
own recent volatility, where the name ranks against the rest of the universe —
is discarded before the model ever sees it. None of it costs a cent and none of
it has ever been tested.

Four families, all computable at 9:45 with no look-ahead:

  SHAPE     the opening window is currently compressed to its net return. Its
            range, its close-location-value, and its wicks are thrown away, so
            "opened low, closed on the high" and "opened high, closed on the
            low" can produce the identical r0.

  SCALED    r0 and gap are pooled RAW across names. +0.5% is a large move for
            BCE and noise for SHOP, and the k-NN standardises globally, not per
            name — so the pooled neighbourhood mixes moves of totally different
            significance. Dividing by each name's own trailing volatility is the
            obvious fix and has never been tried.

  CONTEXT   multi-day momentum, realised-volatility regime, distance from the
            20-day high/low, and yesterday's own afternoon move.

  CROSS     the book is long AND short, so what pays is a name's move RELATIVE
            to the universe, not its absolute direction (day-28). Yet every
            feature is absolute. Same-day cross-sectional rank of r0 and gap is
            known at 9:45 and is the natural feature for a relative bet.

SURVIVORSHIP: today's TSX Composite list applied backwards, same as build_pool.
Fine for comparing feature sets on identical rows; do not read absolute levels.
"""

from __future__ import annotations

import argparse
import os
import sys
from concurrent.futures import ThreadPoolExecutor

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from adapters import YahooDirectAdapter  # noqa: E402
from build_pool import constituents  # noqa: E402
from validate_exit import SCRATCH  # noqa: E402


def session_features(bars: pd.DataFrame, ticker: str, n_entry: int) -> list:
    """One row per session. Everything is knowable at the entry bar's close.

    `n_entry` is how many bars form the entry window (3 for 5m = 09:30-09:45,
    1 for 1h = 09:30-10:30). The outcome `r1` runs from that close to the
    session close.
    """
    out = []
    days = [(d, g.sort_index()) for d, g in bars.groupby(bars.index.date)]
    hist: list = []                      # completed sessions, oldest first
    for d, day in days:
        if len(day) < n_entry + 2:
            continue
        o = float(day["Open"].iloc[0])
        w = day.iloc[:n_entry]           # the entry window
        pe = float(w["Close"].iloc[-1])
        hi, lo = float(w["High"].max()), float(w["Low"].min())
        c = float(day["Close"].iloc[-1])
        if not o or not pe or hi <= lo:
            hist.append({"c": c, "o": o, "hi": float(day["High"].max()),
                         "lo": float(day["Low"].min())})
            continue

        prev = hist[-1]["c"] if hist else None
        r0 = (pe / o - 1) * 100
        gap = (o / prev - 1) * 100 if prev else None

        # ---- CONTEXT from strictly-earlier sessions only ----
        closes = np.array([h["c"] for h in hist], dtype=float)
        ret1 = ret5 = ret20 = vol20 = dhi = dlo = prev_r1 = None
        if len(closes) >= 2:
            ret1 = (closes[-1] / closes[-2] - 1) * 100
        if len(closes) >= 6:
            ret5 = (closes[-1] / closes[-6] - 1) * 100
        if len(closes) >= 21:
            ret20 = (closes[-1] / closes[-21] - 1) * 100
            rr = np.diff(closes[-21:]) / closes[-21:-1]
            vol20 = float(np.std(rr) * 100) or None
            dhi = (closes[-1] / max(h["hi"] for h in hist[-20:]) - 1) * 100
            dlo = (closes[-1] / min(h["lo"] for h in hist[-20:]) - 1) * 100
        if hist and hist[-1].get("r1") is not None:
            prev_r1 = hist[-1]["r1"]

        row = {
            "t": ticker, "date": str(d), "px": pe, "r1": (c / pe - 1) * 100,
            "v15": float(day["Volume"].iloc[:n_entry].fillna(0).sum()),
            # --- the three shipped features ---
            "r0": r0, "gap": gap,
            # --- SHAPE of the opening window ---
            "rng0": (hi - lo) / o * 100,
            "clv": (pe - lo) / (hi - lo),                  # 0 = on the low, 1 = high
            "wick_up": (hi - max(o, pe)) / (hi - lo),
            "wick_dn": (min(o, pe) - lo) / (hi - lo),
            # --- CONTEXT ---
            "ret1": ret1, "ret5": ret5, "ret20": ret20, "vol20": vol20,
            "dist_hi": dhi, "dist_lo": dlo, "prev_r1": prev_r1,
            "dow": pd.Timestamp(d).dayofweek,
        }
        # --- SCALED: the same moves in units of the name's own normal day ---
        if vol20:
            row["r0_z"] = r0 / vol20
            row["gap_z"] = (gap / vol20) if gap is not None else None
            row["rng0_z"] = row["rng0"] / vol20
        hist.append({"c": c, "o": o, "hi": float(day["High"].max()),
                     "lo": float(day["Low"].min()), "r1": row["r1"]})
        out.append(row)
    return out


def add_cross_sectional(df: pd.DataFrame) -> pd.DataFrame:
    """Same-day rank/deviation features. Uses only 9:45 information."""
    df = df.copy()
    for col in ("r0", "gap", "rng0", "r0_z"):
        if col not in df:
            continue
        g = df.groupby("date")[col]
        df[f"{col}_rank"] = g.rank(pct=True)
        df[f"{col}_dev"] = df[col] - g.transform("median")
    # how wide is the whole tape this morning — a regime marker, not a name feature
    df["xs_disp"] = df.groupby("date")["r0"].transform("std")
    return df


def build(interval: str, rng: str, n_entry: int, out_path: str,
          workers: int = 16) -> pd.DataFrame:
    a = YahooDirectAdapter(exchange_tz="America/Toronto")
    uni = constituents(SCRATCH)

    def one(t):
        try:
            return session_features(a._bars_df(a._chart(t, interval, rng)), t, n_entry)
        except Exception:
            return []

    rows: list = []
    with ThreadPoolExecutor(max_workers=workers) as ex:
        for n, r in enumerate(ex.map(one, uni), 1):
            rows += r
            if n % 50 == 0:
                print(f"    {n}/{len(uni)} names, {len(rows):,} rows", flush=True)
    df = add_cross_sectional(pd.DataFrame(rows))
    df.to_csv(out_path, index=False)
    print(f"  {interval}: {len(df):,} rows / {df['t'].nunique()} names / "
          f"{df['date'].nunique()} sessions -> {os.path.basename(out_path)}")
    return df


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--cache", default=SCRATCH)
    ap.add_argument("--force", action="store_true")
    a = ap.parse_args(argv)
    os.makedirs(a.cache, exist_ok=True)
    for interval, rng, n_entry, name in (("5m", "60d", 3, "rich_5m.csv"),
                                         ("1h", "720d", 1, "rich_1h.csv")):
        p = os.path.join(a.cache, name)
        if os.path.exists(p) and not a.force:
            print(f"  {name}: cached")
            continue
        print(f"  building {name} ...", flush=True)
        build(interval, rng, n_entry, p)


if __name__ == "__main__":
    main()
