#!/usr/bin/env python3
"""
validate_eventmult.py — re-measure the event multiple, WITH per-tercile intervals.

TWO DEFECTS THIS FIXES, both found on day-81 by the plausibility gate on its
first run.

1. THE POINT ESTIMATE LAY OUTSIDE ITS OWN INTERVAL. `fairvalue.fair_put` builds
   the fair value from the name's TERCILE multiplier (1.54 / 2.29 / 2.91) and
   then brackets it with the OVERALL interval [2.07, 2.86]. For any low-vol
   name the point sits at 1.54 and the interval starts at 2.07, so the printed
   range does not contain the printed number; for a high-vol name 2.91 sits
   above the top of it. Two populations spliced — rule 7, in the arithmetic of
   a single line. It has been shipping since day-79 and nothing noticed until a
   bound was asserted on it.

2. THE DAY-79 MEASUREMENT HAD NO SCRIPT. The constants were committed; the code
   that produced them was not, so nothing could re-derive or check them. A
   number in a source file that cannot be reproduced is a claim, not a
   measurement.

WHAT IS MEASURED. For each FDA decision with usable daily prices:

    event payoff   max(0, -r) over close(t-2) -> close(t+1), the same window
                   validate_catalyst uses, chosen so a post-close announcement
                   filed next morning lands inside it either way
    own 3-day FV   E[max(0,-r)] over random 3-day windows of THAT name, its
                   own ordinary put value over the same span
    multiple       tercile mean payoff / tercile mean own-3d FV

CLUSTERED BY TICKER, NOT BY EVENT. 605 events come from ~196 names, so events
are not independent — one biotech contributes many decisions drawn from one
volatility regime. Resampling events would understate the interval by treating
repeats as fresh information. The bootstrap resamples NAMES.

WHAT THIS STILL DOES NOT ESTABLISH. That trading the gap between fair value and
market price makes money. There is no free historical option price series, so
that remains untestable here, and no run of this script will change it.
"""

from __future__ import annotations

import argparse
import json
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import fairvalue as F                      # noqa: E402
import validate_catalyst as V              # noqa: E402

BOOT = 2000
SEED = 0


def collect(events, px: dict) -> list:
    """One row per event that has usable DAILY prices. Counts what it drops."""
    out, drop = [], {"no prices": 0, "no window": 0, "short history": 0}
    for _, e in events.iterrows():
        t = (e.get("ticker") or "").strip().upper()
        df = px.get(t)
        if df is None or df.empty:
            drop["no prices"] += 1
            continue
        w = V.window_returns(df, e["date"])
        if w is None:
            drop["no window"] += 1
            continue
        closes = df["Close"].dropna().to_numpy(dtype=float)
        own3 = F.put_fair_value(closes, F.SAMPLE_TRADING_DAYS, seed=SEED)
        if own3 is None or own3 <= 0:
            drop["short history"] += 1
            continue
        out.append({"ticker": t, "kind": e["kind"],
                    "payoff": max(0.0, -w["event"]), "own3": own3})
    n_names = len({r["ticker"] for r in out})
    lost = ", ".join(f"{v} {k}" for k, v in drop.items())
    print(f"  usable {len(out):,} events from {n_names} names; dropped {lost}")
    return out


def terciles(rows: list) -> tuple:
    """Edges from the sample itself, not carried over from a previous run."""
    q = np.quantile([r["own3"] for r in rows], [1 / 3, 2 / 3])
    return float(q[0]), float(q[1])


def bucket_of(own3: float, edges: tuple) -> str:
    return "low" if own3 < edges[0] else ("mid" if own3 < edges[1] else "high")


def multiple(rows: list) -> float | None:
    """Mean payoff / mean own-3d value. A RATIO OF MEANS, deliberately.

    Not the mean of per-event ratios: a name whose own3 is near zero produces
    an enormous ratio and would dominate an average of ratios. Both legs come
    from the same rows, which is what rule 7 requires.
    """
    if not rows:
        return None
    d = float(np.mean([r["own3"] for r in rows]))
    return float(np.mean([r["payoff"] for r in rows]) / d) if d > 0 else None


def boot_ci(rows: list, n: int = BOOT, seed: int = SEED) -> tuple:
    """95% interval, resampling NAMES so repeated events are not fresh draws."""
    by = {}
    for r in rows:
        by.setdefault(r["ticker"], []).append(r)
    names = list(by)
    if len(names) < 5:
        return (None, None)
    rng = np.random.default_rng(seed)
    vals = []
    for _ in range(n):
        pick = rng.integers(0, len(names), size=len(names))
        draw = [r for j in pick for r in by[names[j]]]
        m = multiple(draw)
        if m is not None:
            vals.append(m)
    if len(vals) < n // 2:
        return (None, None)
    return (float(np.quantile(vals, 0.025)), float(np.quantile(vals, 0.975)))


def power(rows: list, edge: float = 0.5, seed: int = SEED) -> float:
    """POSITIVE CONTROL (rule 4). Plant a known lift; can the harness see it?

    Measured as edge / sd, never (mean + edge) / sd — the day-56 error.
    """
    by = {}
    for r in rows:
        by.setdefault(r["ticker"], []).append(r)
    names = list(by)
    rng = np.random.default_rng(seed + 99)
    vals = []
    for _ in range(400):
        pick = rng.integers(0, len(names), size=len(names))
        m = multiple([r for j in pick for r in by[names[j]]])
        if m is not None:
            vals.append(m)
    sd = float(np.std(vals))
    return edge / sd if sd > 0 else float("inf")


def boot_diff(a: list, b: list, n: int = BOOT, seed: int = SEED) -> tuple:
    """95% interval on multiple(a) - multiple(b), names resampled ONCE jointly.

    THE TEST THAT ACTUALLY ANSWERS IT. Overlapping marginal intervals are not
    evidence of no difference — two intervals can overlap while the difference
    excludes zero. The difference has to be bootstrapped directly, and the same
    name must be drawn into both legs on a given replicate or the shared
    volatility regime is double counted.
    """
    by_a, by_b = {}, {}
    for r in a:
        by_a.setdefault(r["ticker"], []).append(r)
    for r in b:
        by_b.setdefault(r["ticker"], []).append(r)
    names = sorted(set(by_a) | set(by_b))
    if len(names) < 5:
        return (None, None, None)
    rng = np.random.default_rng(seed)
    vals = []
    for _ in range(n):
        pick = rng.integers(0, len(names), size=len(names))
        da = [r for j in pick for r in by_a.get(names[j], [])]
        db = [r for j in pick for r in by_b.get(names[j], [])]
        ma, mb = multiple(da), multiple(db)
        if ma is not None and mb is not None:
            vals.append(ma - mb)
    if len(vals) < n // 2:
        return (None, None, None)
    lo, hi = float(np.quantile(vals, 0.025)), float(np.quantile(vals, 0.975))
    return (float(np.mean(vals)), lo, hi)


def run(path: str = None, workers: int = 8) -> dict:
    path = path or os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "data", "catalyst_events.csv")
    ev = V.load_events(path)
    ev = ev[ev["ticker"].astype(str).str.strip() != ""]
    tickers = sorted({t.strip().upper() for t in ev["ticker"]})
    print(f"  {len(ev):,} events across {len(tickers)} tickers")
    px = V.fetch_prices(tickers, workers=workers)
    rows = collect(ev, px)
    if not rows:
        raise SystemExit("no usable events — refusing to emit constants")

    edges = terciles(rows)
    res = {"n_events": len(rows), "n_names": len({r["ticker"] for r in rows}),
           "tercile_edges": edges, "overall": multiple(rows),
           "overall_ci": boot_ci(rows), "power_z_for_0.5x": power(rows),
           "by_bucket": {}}
    sub = {}
    for b in ("low", "mid", "high"):
        sub[b] = [r for r in rows if bucket_of(r["own3"], edges) == b]
        res["by_bucket"][b] = {"n": len(sub[b]), "mult": multiple(sub[b]),
                               "ci": boot_ci(sub[b], seed=SEED + len(b))}
    # Does the tercile structure survive a direct test, or only a visual one?
    res["high_minus_low"] = boot_diff(sub["high"], sub["low"])
    res["mid_minus_low"] = boot_diff(sub["mid"], sub["low"])
    return res


def report(r: dict) -> str:
    L = ["▎EVENT MULTIPLE — re-measured, with per-tercile intervals",
         f"   {r['n_events']:,} decisions across {r['n_names']} names; "
         f"bootstrap resamples NAMES, not events",
         f"   tercile edges on own 3d put value: "
         f"{r['tercile_edges'][0]:.2f}% / {r['tercile_edges'][1]:.2f}%", ""]
    for b in ("low", "mid", "high"):
        d = r["by_bucket"][b]
        lo, hi = d["ci"]
        ci = f"[{lo:.2f}x, {hi:.2f}x]" if lo is not None else "[interval unavailable]"
        L.append(f"   {b:>4}-vol  n={d['n']:>4}   {d['mult']:.2f}x   95% {ci}")
    lo, hi = r["overall_ci"]
    L.append("")
    L.append(f"   overall            {r['overall']:.2f}x   95% "
             f"[{lo:.2f}x, {hi:.2f}x]")
    L.append("")
    L.append("   does the tercile structure survive a DIRECT test?")
    for lab, key in (("high - low", "high_minus_low"),
                     ("mid  - low", "mid_minus_low")):
        m, dlo, dhi = r.get(key, (None, None, None))
        if m is None:
            continue
        mde = (dhi - dlo) / 2.0          # smallest difference this can resolve
        if dlo > 0 or dhi < 0:
            verdict = "DISTINGUISHABLE"
        elif abs(m) < mde:
            verdict = f"UNDERPOWERED — cannot resolve below {mde:.2f}x"
        else:
            verdict = "NOT distinguishable from zero"
        L.append(f"     {lab}  {m:+.2f}x  95% [{dlo:+.2f}, {dhi:+.2f}]  "
                 f"-> {verdict}")
    L.append("     ── rule 10: an interval wider than the effect means the "
             "data cannot answer,")
    L.append("        which is NOT the same as answering no.")
    z = r["power_z_for_0.5x"]
    L.append(f"   positive control: a planted 0.50x lift would register at "
             f"z={z:.1f}")
    if z < 2.0:
        L.append("   ⚠ UNDERPOWERED — this harness cannot resolve the effect "
                 "it is measuring;")
        L.append("     the intervals below are honest but the point estimates "
                 "are not usable.")
    return "\n".join(L)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--json", default=None)
    a = ap.parse_args(argv)
    r = run(workers=a.workers)
    print(report(r))
    if a.json:
        with open(a.json, "w") as f:
            json.dump(r, f, indent=2)
        print(f"\nwrote {a.json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
