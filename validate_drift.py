#!/usr/bin/env python3
"""
validate_drift.py — day-83b. Does an FDA decision keep moving the stock AFTER
it is public?

Pre-registered in PREREGISTER_day83b.md before any result was computed.

WHY THIS SHAPE AND NOT ANOTHER. The portfolio manager trades shares, long or
short, on a morning recommendation with a hold duration. Day-51 rejected
exactly that shape (#32) and its closing sentence is the reason this study is
allowed to exist at all:

    "A duration field cannot manufacture event awareness out of OHLCV bars."

The engine now has the event feed day-51 lacked. 1,097 dated FDA decisions with
a known outcome mean:

    the DURATION is a fact      it runs from the announcement, not a guess
    the DIRECTION is known      the 8-K states approval or rejection at entry

So this is not predicting a binary. The binary has resolved and is public. The
only question is whether the market finishes repricing it on the day — the
classic post-announcement drift question, expressible in shares.

WHAT DECIDES IT IS THE MARKET-RELATIVE NUMBER. Day-38 and day-51 both found an
apparent multi-day gain that turned out to be market drift collected by a
long-biased book. This study is built to fail the same way if it is going to:
every raw figure is printed beside its market-relative twin, and the bar
applies to the relative one.

THE ARMS ARE NEVER POOLED. An approval and a rejection are different events;
averaging a possible rise against a possible fall would hide both.
"""

from __future__ import annotations

import argparse
import datetime as dt
import os
import sys
from collections import defaultdict

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import validate_catalyst as V  # noqa: E402

BOOT = 4000
SEED = 0
HOLD = 5                 # sessions; fixed by the pre-registration
ADOPT_T = 3.0
BENCH = "SPY"            # the market leg for the relative figure


def _series(px, t):
    df = px.get(t)
    if df is None or df.empty:
        return None
    s = df["Close"].dropna()
    return s if len(s) > 40 else None


def drift_rows(events, px, bench, hold: int = HOLD) -> tuple:
    """One row per event: raw and market-relative return over `hold` sessions.

    Entry is the close of the announcement window (t+1 in `window_returns`),
    which is the first close a reader of the 8-K could actually have traded.
    """
    out, drop = [], defaultdict(int)
    bidx = {d.date(): i for i, d in enumerate(bench.index)} if bench is not None else {}
    bvals = bench.to_numpy(dtype=float) if bench is not None else None
    for _, e in events.iterrows():
        t = (e.get("ticker") or "").strip().upper()
        s = _series(px, t)
        if s is None:
            drop["no prices"] += 1
            continue
        idx = s.index
        try:
            when = pd_ts(e["date"], idx)
            i = idx.searchsorted(when)
        except Exception:
            drop["unusable date"] += 1
            continue
        entry = min(i + 1, len(s) - 1)          # first tradable close
        if entry < 25 or entry + hold >= len(s):
            drop["window off the end"] += 1
            continue
        p = s.to_numpy(dtype=float)
        raw = (p[entry + hold] / p[entry] - 1) * 100
        rel = raw
        if bvals is not None:
            d0 = idx[entry].date()
            j = bidx.get(d0)
            if j is not None and j + hold < len(bvals):
                rel = raw - (bvals[j + hold] / bvals[j] - 1) * 100
            else:
                drop["no market window"] += 1
                continue
        out.append({"ticker": t, "kind": e["kind"], "date": str(e["date"])[:10],
                    "raw": raw, "rel": rel})
    return out, dict(drop)


def pd_ts(value, idx):
    import pandas as pd
    ts = pd.Timestamp(value)
    return ts.tz_localize(idx.tz) if idx.tz is not None and ts.tz is None else ts


def _by_name(rows: list) -> dict:
    d = defaultdict(list)
    for r in rows:
        d[r["ticker"]].append(r)
    return d


def boot_mean(rows: list, field: str, n: int = BOOT, seed: int = SEED) -> tuple:
    """Mean with a NAME-clustered 95% interval.

    684 events come from 195 names and one biotech contributes many decisions;
    resampling events would treat those as independent information.
    """
    by = _by_name(rows)
    names = sorted(by)
    if len(names) < 5:
        return (None, None, None)
    rng = np.random.default_rng(seed)
    vals = []
    for _ in range(n):
        pick = rng.integers(0, len(names), size=len(names))
        draw = [r[field] for i in pick for r in by[names[i]]]
        if draw:
            vals.append(float(np.mean(draw)))
    if not vals:
        return (None, None, None)
    return (float(np.mean([r[field] for r in rows])),
            float(np.quantile(vals, 0.025)), float(np.quantile(vals, 0.975)))


def t_stat(rows: list, field: str) -> float | None:
    """t on the name-clustered interval, so it matches the bar it is judged by."""
    m, lo, hi = boot_mean(rows, field)
    if m is None or hi == lo:
        return None
    return m / ((hi - lo) / (2 * 1.96))


def power(rows: list, field: str, edge: float) -> float | None:
    """POSITIVE CONTROL: z for a planted drift. edge / sd, never (mean+edge)/sd."""
    _, lo, hi = boot_mean(rows, field, n=1500, seed=SEED + 7)
    if lo is None:
        return None
    sd = (hi - lo) / (2 * 1.96)
    return edge / sd if sd > 0 else float("inf")


def placebo(rows: list, px, bench, hold: int = HOLD, n: int = 200,
            seed: int = SEED) -> tuple:
    """The same hold on RANDOM dates in the SAME names.

    If this reproduces the effect, what is being measured is a property of the
    companies or the period, not of the announcement.
    """
    rng = np.random.default_rng(seed + 31)
    names = sorted({r["ticker"] for r in rows})
    per = max(1, len(rows) // max(len(names), 1))
    bidx = {d.date(): i for i, d in enumerate(bench.index)} if bench is not None else {}
    bvals = bench.to_numpy(dtype=float) if bench is not None else None
    means = []
    for _ in range(n):
        draw = []
        for t in names:
            s = _series(px, t)
            if s is None:
                continue
            p = s.to_numpy(dtype=float)
            hi = len(p) - hold - 1
            if hi <= 30:
                continue
            for k in rng.integers(25, hi, size=per):
                raw = (p[k + hold] / p[k] - 1) * 100
                if bvals is not None:
                    j = bidx.get(s.index[k].date())
                    if j is None or j + hold >= len(bvals):
                        continue
                    raw -= (bvals[j + hold] / bvals[j] - 1) * 100
                draw.append(raw)
        if draw:
            means.append(float(np.mean(draw)))
    if not means:
        return (None, None)
    return (float(np.quantile(means, 0.025)), float(np.quantile(means, 0.975)))


def events_needed(control_z: float, n: int, bar: float = ADOPT_T) -> int | None:
    """How many events before the bar is reachable for THIS effect size.

    An underpowered null is only useful if it says when it stops being one.
    SE shrinks as 1/sqrt(n), so z grows as sqrt(n): n_needed = n * (bar/z)^2.
    """
    if not control_z or control_z != control_z or control_z <= 0:
        return None
    return int(round(n * (bar / control_z) ** 2))


def verdict(m, lo, hi, t, mde) -> str:
    if m is None or lo is None:
        return "NOT COMPUTABLE"
    if t is not None and abs(t) >= ADOPT_T:
        return f"CLEARS the bar (|t|={abs(t):.2f} >= {ADOPT_T:.0f})"
    if mde is not None and abs(m) < mde:
        return f"UNDERPOWERED — cannot resolve below {mde:.2f}%"
    return f"BELOW the bar (|t|={abs(t):.2f})" if t is not None else "no verdict"


def analyse(rows: list, px, bench, spread_pct: float = 0.0) -> dict:
    out = {"n": len(rows), "names": len({r["ticker"] for r in rows})}
    for field in ("raw", "rel"):
        m, lo, hi = boot_mean(rows, field)
        t = t_stat(rows, field)
        mde = ADOPT_T * ((hi - lo) / (2 * 1.96)) if lo is not None else None
        out[field] = {"mean": m, "ci": (lo, hi), "t": t, "mde": mde,
                      "verdict": verdict(m, lo, hi, t, mde)}
    out["placebo_rel"] = placebo(rows, px, bench)
    out["control_z_1pct"] = power(rows, "rel", 1.0)
    out["events_needed"] = events_needed(out["control_z_1pct"], len(rows))
    out["net_rel"] = (out["rel"]["mean"] - spread_pct
                      if out["rel"]["mean"] is not None else None)
    out["spread_pct"] = spread_pct
    return out


def report(name: str, a: dict) -> str:
    L = [f"▎{name} — {HOLD}-session drift after the announcement",
         f"   {a['n']} events across {a['names']} names"]
    if not a["n"]:
        return "\n".join(L + ["   no usable events"])
    for field, label in (("raw", "raw"), ("rel", "vs market")):
        d = a[field]
        if d["mean"] is None:
            L.append(f"   {label:<10} not computable")
            continue
        lo, hi = d["ci"]
        L.append(f"   {label:<10} {d['mean']:+7.2f}%   95% [{lo:+.2f}, {hi:+.2f}]"
                 f"   -> {d['verdict']}")
    plo, phi = a["placebo_rel"]
    if plo is not None:
        m = a["rel"]["mean"]
        inside = plo <= m <= phi
        L.append(f"   placebo    random dates, same names: "
                 f"[{plo:+.2f}, {phi:+.2f}] — observed is "
                 f"{'INSIDE' if inside else 'OUTSIDE'} it")
    if a["control_z_1pct"] is not None:
        L.append(f"   control    a planted 1.00% drift registers at "
                 f"z={a['control_z_1pct']:.1f}")
        if a.get("events_needed"):
            L.append(f"   power      the |t|>={ADOPT_T:.0f} bar needs "
                     f"~{a['events_needed']:,} events at this effect size "
                     f"(have {a['n']})")
    if a["spread_pct"]:
        L.append(f"   net        {a['net_rel']:+.2f}% after a "
                 f"{a['spread_pct']:.2f}% round-trip spread")
    return "\n".join(L)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--hold", type=int, default=HOLD)
    ap.add_argument("--spread", type=float, default=0.0,
                    help="round-trip share spread, %% of price")
    a = ap.parse_args(argv)
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                        "data", "catalyst_events.csv")
    ev = V.load_events(path)
    ev = ev[ev["ticker"].astype(str).str.strip() != ""]
    tickers = sorted({t.strip().upper() for t in ev["ticker"]})
    print(f"  {len(ev):,} events across {len(tickers)} tickers")
    px = V.fetch_prices(tickers + [BENCH], workers=8)
    bench = _series(px, BENCH)
    if bench is None:
        print(f"  ⚠ {BENCH} unavailable — the market-relative figure, which is "
              "the deciding one, cannot be computed. Refusing.")
        return 2
    rows, drop = drift_rows(ev, px, bench, a.hold)
    print(f"  usable {len(rows):,}; dropped " +
          ", ".join(f"{v} {k}" for k, v in drop.items()))
    for kind in ("CRL", "APPROVAL"):
        sub = [r for r in rows if r["kind"] == kind]
        print()
        print(report(kind, analyse(sub, px, bench, a.spread)))
    print()
    print("   ── the arms are never pooled: an approval and a rejection are")
    print("      different events and averaging them would hide both.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
