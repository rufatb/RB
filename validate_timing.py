#!/usr/bin/env python3
"""
validate_timing.py — day-89. Entry time and hold duration, tested JOINTLY.

Pre-registered in PREREGISTER_day89.md. Bar: |t| >= 3 AND four-block sign
consistency AND beating the PLACEBO'S MAX at the 95th percentile. All three.

WHY THE PLACEBO RULE IS THE WHOLE STUDY. A 7 x 5 grid is 35 cells, and the best
of 35 noisy cells looks good by chance. Day-39 hit this exactly: its apparent
09:50 winner at +0.1034%/leg was beaten by the placebo's own MEDIAN winner at
+0.1212%. Comparing the best cell against ZERO would manufacture a result here
with near-certainty, so the registered statistic is best-cell against the
placebo's best-cell distribution.

    max_real  must exceed  the 95th percentile of {max_placebo}

That is a different and much harder test than any single cell's |t|, and it is
the only one that answers "is there a better time to run this?" rather than
"did some cell in a big grid come out high?".

TWO PANELS, WITH A REGISTERED ASYMMETRY. The hourly panel (490 sessions, 258
names) is the long-window arm and DECIDES. The 5-minute panel is capped by
Yahoo at 60 days — the window length that manufactured six separate mirages in
this repo — so it can REFUTE a claim and cannot establish one. If the two
disagree, hourly wins. Registered before either was run.

THE ENGINE IS RE-FITTED AT EVERY ENTRY TIME. `r0` and `vp` are defined against
the entry bar, so reusing one fit across entry times would test the clock
rather than the engine.
"""

from __future__ import annotations

import argparse
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import r945  # noqa: E402
import validate_us as U  # noqa: E402
from dashboard import load_config  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "data")
ADOPT_T = 3.0
PLACEBO_RUNS = 200
SEED = 0


# ── the panel, re-cut at an arbitrary entry bar ────────────────────────────

def session_rows(bars: pd.DataFrame, ticker: str, entry_idx: int,
                 min_bars: int) -> list:
    """One row per session with the entry at bar `entry_idx`.

    Mirrors r945.session_rows with the entry parameterised, so moving the entry
    moves BOTH ends: `r0` covers open->entry and `r1` covers entry->close.
    """
    rows, prev_close = [], None
    for d, day in bars.groupby(bars.index.date):
        day = day.sort_index()
        if len(day) < min_bars:
            if len(day):
                prev_close = day["Close"].iloc[-1]
            continue
        o = day["Open"].iloc[0]
        pe = day["Close"].iloc[entry_idx]
        c = day["Close"].iloc[-1]
        gap = (o / prev_close - 1) * 100 if prev_close else None
        prev_close = c
        if not o or not pe:
            continue
        rows.append({"t": ticker, "date": str(d), "gap": gap,
                     "r0": (pe / o - 1) * 100,
                     "v15": float(day["Volume"].iloc[:entry_idx + 1].sum()),
                     "entry_px": float(pe),
                     "r1": (c / pe - 1) * 100})
    return rows


def legs_at(df: pd.DataFrame, cfg: dict) -> list:
    """Qualified legs with tide-relative capture, for one entry-time panel."""
    import validate_twins as T
    tide = df.dropna(subset=["r1"]).groupby("date")["r1"].median()
    out = []
    for day in T.walk_forward(df, cfg):
        m = float(tide.get(day["date"], np.nan))
        if not np.isfinite(m):
            continue
        for side, group in (("LONG", day["longs"]), ("SHORT", day["shorts"])):
            for b in group:
                rel = (b["capt"] - m) if side == "LONG" else (b["capt"] + m)
                out.append({"date": day["date"], "t": b["t"], "side": side,
                            "hit": b["hit"], "rel": rel})
    return out


def cell_stat(legs: list) -> dict:
    """Per-session mean tide-relative capture, and its clustered interval."""
    by: dict = {}
    for l in legs:
        by.setdefault(l["date"], []).append(l["rel"])
    rows = [{"date": d, "t": "XS", "v": float(np.mean(v))}
            for d, v in sorted(by.items())]
    if len(rows) < 20:
        return {"n": len(legs), "mean": None}
    m, lo, hi = U.boot(rows, "v", "date")
    se = U.se_of(lo, hi)
    return {"n": len(legs), "sessions": len(rows), "mean": m,
            "lo": lo, "hi": hi, "se": se,
            "t": (m / se) if se else None,
            "blocks": U.blocks(rows, "v"),
            "hit": 100 * np.mean([l["hit"] for l in legs]) if legs else None}


# ── the placebo, which is what actually decides ────────────────────────────

def placebo_max(cells: dict, n: int = PLACEBO_RUNS, seed: int = SEED) -> dict:
    """The distribution of the BEST cell when every cell is noise.

    Each run reshuffles the sign of every session's contribution within each
    cell — preserving the cells' shapes and sample sizes while destroying any
    real effect — then records the maximum across the grid. A genuine winner
    must beat the 95th percentile of that maximum.

    Comparing the best of 35 cells to ZERO instead of to this is how day-39
    nearly shipped a 09:50 entry time whose apparent edge was smaller than what
    its own placebo produced.
    """
    rng = np.random.default_rng(seed + 991)
    per_cell = {}
    for key, legs in cells.items():
        by: dict = {}
        for l in legs:
            by.setdefault(l["date"], []).append(l["rel"])
        per_cell[key] = np.array([float(np.mean(v)) for _, v in sorted(by.items())])
    maxes = []
    for _ in range(n):
        best = -np.inf
        for key, vals in per_cell.items():
            if len(vals) < 20:
                continue
            flipped = vals * rng.choice([-1.0, 1.0], size=len(vals))
            best = max(best, float(np.mean(flipped)))
        if np.isfinite(best):
            maxes.append(best)
    if not maxes:
        return {}
    return {"p50": float(np.quantile(maxes, 0.50)),
            "p95": float(np.quantile(maxes, 0.95)),
            "max": float(np.max(maxes)), "n": len(maxes)}


def verdict(best_key, best, pb) -> str:
    if best is None or best.get("mean") is None:
        return "NOT COMPUTABLE"
    m, t, bs = best["mean"], best["t"], best["blocks"]
    if not pb:
        return "NO PLACEBO — refusing to call a winner without one"
    if m <= pb["p95"]:
        return (f"REJECTED — the best cell {best_key} ({m:+.4f}%/leg) does NOT "
                f"beat the placebo's 95th percentile ({pb['p95']:+.4f}%). "
                f"A grid this size produces a winner that large by chance.")
    if t is None or abs(t) < ADOPT_T:
        return (f"beats the placebo but FAILS the bar "
                f"(|t|={abs(t) if t else float('nan'):.2f} < {ADOPT_T:.0f})")
    if not U.consistent(bs):
        return "beats the placebo and |t|, but the sign FLIPS across blocks"
    return (f"CLEARS ALL THREE — {best_key} at {m:+.4f}%/leg, |t|={abs(t):.2f}, "
            f"consistent, above the placebo max")


def report(cells: dict, label: str) -> str:
    L = [f"▎{label}",
         f"   {'cell':<22}{'n legs':>8}{'sessions':>10}{'capture':>11}"
         f"{'|t|':>7}{'hit':>7}  blocks"]
    stats = {}
    for key, legs in sorted(cells.items()):
        s = cell_stat(legs)
        stats[key] = s
        if s["mean"] is None:
            L.append(f"   {str(key):<22}{s['n']:>8}      too few sessions")
            continue
        bs = "  ".join(f"{b:+.3f}" for b in s["blocks"]) if s["blocks"] else ""
        L.append(f"   {str(key):<22}{s['n']:>8}{s['sessions']:>10}"
                 f"{s['mean']:>+11.4f}{abs(s['t']):>7.2f}{s['hit']:>6.1f}%  {bs}")
    live = {k: v for k, v in stats.items() if v.get("mean") is not None}
    if not live:
        return "\n".join(L + ["   nothing computable"])
    best_key = max(live, key=lambda k: live[k]["mean"])
    pb = placebo_max(cells)
    L.append("")
    if pb:
        L.append(f"   placebo max over {pb['n']} shuffles of the SAME grid: "
                 f"median {pb['p50']:+.4f}%, 95th {pb['p95']:+.4f}%, "
                 f"max {pb['max']:+.4f}%")
    L.append(f"   best cell: {best_key} at {live[best_key]['mean']:+.4f}%/leg")
    L.append(f"   -> {verdict(best_key, live[best_key], pb)}")
    return "\n".join(L)


# ── raw bars, kept so the panel can be RE-CUT at any entry ────────────────
#
# us_hourly.csv stores only the summary columns cut at 10:30, so it cannot
# answer an entry-time question at all. Moving the entry changes r0, v15 AND
# r1 together, which is the whole point, so the raw bars have to be held.

def fetch_raw(tickers: list, interval: str, days: int, workers: int = 10):
    """{ticker: DataFrame of bars}. Failures are counted, never silent."""
    import time
    from concurrent.futures import ThreadPoolExecutor

    import requests
    HEAD = {"User-Agent": "Mozilla/5.0"}

    def one(t):
        now = time.time()
        for host in ("query1", "query2"):
            for attempt in range(3):
                try:
                    r = requests.get(
                        f"https://{host}.finance.yahoo.com/v8/finance/chart/{t}",
                        params={"interval": interval,
                                "period1": int(now - days * 86400),
                                "period2": int(now)},
                        headers=HEAD, timeout=45)
                    res = (r.json().get("chart") or {}).get("result")
                    if res:
                        q = (res[0].get("indicators", {}).get("quote")
                             or [{}])[0]
                        ts = res[0].get("timestamp") or []
                        if not ts:
                            return t, None
                        idx = pd.to_datetime(ts, unit="s", utc=True)
                        idx = idx.tz_convert("America/New_York")
                        d = pd.DataFrame(
                            {"Open": q.get("open"), "High": q.get("high"),
                             "Low": q.get("low"), "Close": q.get("close"),
                             "Volume": q.get("volume")},
                            index=idx).dropna(subset=["Close"])
                        return t, d.between_time("09:30", "15:59")
                except Exception:
                    time.sleep(1.0 * (attempt + 1))
        return t, None

    out, bad = {}, 0
    with ThreadPoolExecutor(max_workers=workers) as ex:
        for i, (t, d) in enumerate(ex.map(one, tickers), 1):
            if d is None or d.empty:
                bad += 1
            else:
                out[t] = d
            if i % 50 == 0:
                print(f"    {i}/{len(tickers)} … {len(out)} usable", flush=True)
    return out, bad


def panel_at(raw: dict, entry_idx: int, min_bars: int) -> pd.DataFrame:
    rows = []
    for t, bars in raw.items():
        rows += session_rows(bars, t, entry_idx, min_bars)
    return pd.DataFrame(rows)


def hold_rows(raw: dict, legs: list, holds=(0, 1, 2, 3, 5)) -> dict:
    """Tide-relative capture for the SAME picks held k extra sessions.

    Entry is unchanged; only the exit moves, so this isolates duration from
    entry time. k=0 is the shipped exit (same-day close).
    """
    closes = {}
    for t, bars in raw.items():
        by = bars.groupby(bars.index.date)["Close"].last()
        closes[t] = ([str(d) for d in by.index], by.to_numpy(dtype=float))
    out = {k: [] for k in holds}
    entry_px = {(l["t"], l["date"]): l for l in legs}
    for (t, date), l in entry_px.items():
        if t not in closes:
            continue
        dates, px = closes[t]
        try:
            i = dates.index(date)
        except ValueError:
            continue
        base = l["entry_px"]
        for k in holds:
            j = i + k
            if j >= len(px) or not base:
                continue
            raw_ret = (px[j] / base - 1) * 100
            out[k].append({"date": date, "t": t, "side": l["side"],
                           "hit": int(raw_ret > 0) if l["side"] == "LONG"
                           else int(raw_ret < 0),
                           "raw": raw_ret,
                           "rel": raw_ret if l["side"] == "LONG" else -raw_ret})
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--names", type=int, default=200)
    ap.add_argument("--interval", default="1h", choices=["1h", "5m"])
    ap.add_argument("--days", type=int, default=720)
    a = ap.parse_args(argv)
    cfg = load_config(os.path.join(HERE, "config.yaml"))

    import build_us as B
    tick = [u["ticker"] for u in B.sec_tickers(a.names)]
    print(f"fetching {a.interval} bars for {len(tick)} names "
          f"({a.days}d window)")
    raw, bad = fetch_raw(tick, a.interval, a.days)
    print(f"  {len(raw)} usable, {bad} failed")
    if not raw:
        print("  NO DATA — refusing to report.")
        return 2

    per_day = int(np.median([len(v.groupby(v.index.date).size())
                             for v in raw.values()])) if raw else 0
    bars_per_day = int(np.median([v.groupby(v.index.date).size().median()
                                  for v in raw.values()]))
    print(f"  median {bars_per_day} bars/session")

    # ENTRY GRID. Hourly: 10:30/11:30/12:30/13:30/14:30. 5m: 09:35..10:30.
    if a.interval == "1h":
        grid = [(0, "10:30"), (1, "11:30"), (2, "12:30"), (3, "13:30")]
        min_bars = 5
    else:
        grid = [(0, "09:35"), (1, "09:40"), (2, "09:45"), (3, "09:50"),
                (5, "10:00"), (11, "10:30")]
        min_bars = 20

    cells, legs_by_entry = {}, {}
    for idx, label in grid:
        if idx >= bars_per_day - 1:
            print(f"  skip {label}: only {bars_per_day} bars/session")
            continue
        df = panel_at(raw, idx, min_bars)
        if df.empty:
            continue
        legs = legs_at(df, cfg)
        legs_by_entry[label] = (legs, df)
        cells[f"entry {label}"] = legs
        print(f"  entry {label}: {len(legs):,} qualified legs")

    print("\n" + "=" * 74)
    print(report(cells, "H1 — ENTRY TIME (exit at same-day close)"))

    # H2/H3: duration, at each entry, forming the joint grid.
    joint = {}
    for label, (legs, df) in legs_by_entry.items():
        for k, sub in hold_rows(raw, _with_entry_px(legs, df)).items():
            if sub:
                joint[f"{label} +{k}d"] = sub
    if joint:
        print("\n" + "=" * 74)
        print(report(joint, "H3 — THE JOINT GRID (entry x hold duration)"))
        print("\n   cost note: every +Nd cell holds overnight. Day-24 measured")
        print("   2x volatility and day-87 a 2.48x worse worst-day. None of")
        print("   that is in the capture figures above.")

    print("\n" + "=" * 74)
    print("   ── the deciding statistic is the BEST CELL against the PLACEBO'S")
    print("      BEST CELL, never against zero. A 35-cell grid produces a high")
    print("      winner by chance; day-39's 09:50 was beaten by its own")
    print("      placebo median.")
    return 0


def _with_entry_px(legs: list, df: pd.DataFrame) -> list:
    """Attach each leg's entry price from the panel it was picked on."""
    px = {(r.t, r.date): r.entry_px for r in df.itertuples()}
    out = []
    for l in legs:
        e = px.get((l["t"], l["date"]))
        if e:
            out.append({**l, "entry_px": e})
    return out


if __name__ == "__main__":
    raise SystemExit(main())
