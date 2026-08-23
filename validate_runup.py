#!/usr/bin/env python3
"""
validate_runup.py — is there a WEEK-to-MONTH trade before an FDA decision?

THE QUESTION THIS ANSWERS, and it is the one the report cannot currently reach.
Day-68 measured what happens ON the decision: a rejection takes -15.2% and an
approval is indistinguishable from a random window. Both are outcomes, and a
portfolio manager cannot act on either without knowing which arrives. The
tradeable question sits earlier:

    if you take a position N days BEFORE a scheduled FDA decision, knowing
    only that the date exists, and you exit BEFORE the print — what happens?

That is a week-to-month horizon, it never carries the binary, and — unlike
everything measured so far in this domain — it is a position you can size,
because its outcome does not depend on an agency's letter.

WHY IT MIGHT BE THERE. The run-up into a catalyst is one of the most-repeated
claims in biotech trading: attention builds, specialists accumulate, options
demand lifts the underlying. It is also exactly the kind of claim this repo has
refuted thirty-six times, so it gets the same gates and the same
pre-registration.

THE POOLED SAMPLE IS THE ONLY HONEST ONE. Splitting run-up by outcome (what did
CRL names do beforehand, versus approvals) is a different and useless question:
ex ante you do not know which you are holding. Every headline number here pools
both, exactly as a trader would experience it. The outcome split is printed
afterwards for diagnosis only, clearly marked as NOT tradeable.

THE BENCHMARK IS XBI, NOT SPY, and that choice does real work. These are all
small-cap biotech; over a month they move with their sector far more than with
the market. A raw +4% run-up in a month when XBI rose 5% is not a run-up, it is
beta, and a study that reports it as an edge has measured the sector.

THE LOOK-AHEAD THAT CANNOT BE FULLY REMOVED, stated plainly. The historical
sample dates each event by the 8-K announcement — the day the decision actually
landed. Live, you would enter off the PDUFA goal date the company disclosed
months earlier, and the FDA does not always act on it: decisions come early,
get extended, or slip. So the measured entry is better-timed than a real one
could be, and whatever this finds is an UPPER BOUND on what is capturable.
`pdufa.py` shows how often disclosed dates move; that is the size of the gap.

PRE-REGISTERED BEFORE RUNNING, and binding:

  ADOPT only if the pooled, XBI-relative drift over a horizon is non-zero at
  |z| >= 3 under an EVENT-CLUSTERED bootstrap, AND the placebo (random dates,
  same tickers, same horizon) shows nothing, AND the positive control is
  detected. Four horizons are tested (5, 10, 20, 40 trading days), so the bar
  is raised to |z| >= 3.5 to cover having asked four questions instead of one.

  REJECT otherwise. This would be rejection #37.
"""

from __future__ import annotations

import argparse
import datetime as dt
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from validate_catalyst import fetch_prices, load_events  # noqa: E402
from validate_exit import SCRATCH  # noqa: E402

EVENTS = os.path.join(SCRATCH, "catalyst_events.csv")
HORIZONS = (5, 10, 20, 40)
BAR_Z = 3.5                 # raised from 3.0: four horizons, not one
BOOT = 2000
BENCH = "XBI"               # small-cap biotech, not the S&P


def bench_series(ticker: str = BENCH) -> pd.Series | None:
    px = fetch_prices([ticker], workers=1)
    s = px.get(ticker)
    return s["Close"].dropna() if s is not None else None


def _rel(p: np.ndarray, i: int, h: int, b: np.ndarray | None,
         bi: int | None) -> float | None:
    """Return from close(i-h-1) to close(i-2), minus the benchmark's own.

    ENDS AT i-2, NOT AT THE EVENT. `window_returns` established that an 8-K
    filed the morning after an after-close announcement puts the reaction on
    t-1, so a window that runs to t-1 can contain the print itself. Stopping at
    t-2 costs a day of drift and guarantees the binary is excluded, which is
    the entire point of measuring this separately.
    """
    if i - h - 1 < 0 or i - 2 < 0:
        return None
    r = (p[i - 2] / p[i - h - 1] - 1) * 100
    if b is None or bi is None or bi - h - 1 < 0 or bi - 2 < 0:
        return None
    rb = (b[bi - 2] / b[bi - h - 1] - 1) * 100
    return r - rb


def _locate(idx: pd.Index, when) -> int | None:
    try:
        ts = pd.Timestamp(when)
        if idx.tz is not None:
            ts = ts.tz_localize(idx.tz) if ts.tz is None else ts.tz_convert(idx.tz)
        i = int(idx.searchsorted(ts))
    except Exception:
        return None
    return i if 0 < i < len(idx) else None


def sample(events: pd.DataFrame, px: dict, bench: pd.Series,
           horizons=HORIZONS) -> pd.DataFrame:
    b = bench.to_numpy(dtype=float)
    rows = []
    for _, e in events.iterrows():
        s = px.get(e["ticker"])
        if s is None:
            continue
        ser = s["Close"].dropna()
        i = _locate(ser.index, e["date"])
        bi = _locate(bench.index, e["date"])
        if i is None or bi is None:
            continue
        p = ser.to_numpy(dtype=float)
        row = {"ticker": e["ticker"], "date": pd.Timestamp(e["date"]),
               "kind": e["kind"]}
        ok = False
        for h in horizons:
            v = _rel(p, i, h, b, bi)
            row[f"h{h}"] = v
            ok = ok or v is not None
        if ok:
            rows.append(row)
    return pd.DataFrame(rows)


def clustered_mean(vals: pd.DataFrame, col: str, boot: int = BOOT,
                   seed: int = 0) -> dict:
    """Mean drift with a bootstrap over EVENT DATES.

    Several sponsors can share a decision date, and biotech moves together on
    any given week. Resampling rows would treat one week as many independent
    observations of a month-long drift.
    """
    d = vals[["date", col]].dropna()
    if len(d) < 30:
        return {"n": len(d), "mean": float("nan"), "sd": float("nan"),
                "z": float("nan"), "median": float("nan"), "win": float("nan")}
    x = d[col].to_numpy(dtype=float)
    obs = float(np.mean(x))
    rng = np.random.default_rng(seed)
    keys = d["date"].dt.date.to_numpy()
    groups = {}
    for k, v in zip(keys, x):
        groups.setdefault(k, []).append(v)
    uk = list(groups)
    out = []
    for _ in range(boot):
        pick = rng.choice(len(uk), size=len(uk), replace=True)
        vv = [v for j in pick for v in groups[uk[j]]]
        if len(vv) >= 30:
            out.append(np.mean(vv))
    sd = float(np.std(out)) if out else float("nan")
    return {"n": len(d), "mean": obs, "sd": sd,
            "z": obs / sd if sd and sd == sd and sd > 0 else float("nan"),
            "median": float(np.median(x)),
            "win": float((x > 0).mean())}


def placebo(px: dict, bench: pd.Series, tickers: list, per: int = 4,
            seed: int = 11, horizons=HORIZONS) -> pd.DataFrame:
    """Random dates on the same names. If arbitrary windows drift as much as
    pre-decision ones, the label is not what is being measured."""
    rng = np.random.default_rng(seed)
    rows = []
    for t in tickers:
        s = px.get(t)
        if s is None:
            continue
        ser = s["Close"].dropna()
        if len(ser) < 120:
            continue
        for _ in range(per):
            i = int(rng.integers(60, len(ser) - 3))
            when = ser.index[i]
            rows.append({"ticker": t, "date": pd.Timestamp(when), "kind": "PLACEBO"})
    fake = pd.DataFrame(rows)
    return sample(fake, px, bench, horizons) if len(fake) else pd.DataFrame()


def positive_control(vals: pd.DataFrame, col: str, edge: float = 1.0,
                     seed: int = 7) -> dict:
    """Plant a drift of known size and confirm the harness sees it.

    1.0% over the horizon is roughly the smallest number that could pay for
    two crossings of a biotech spread. A harness that cannot see it cannot
    report a null about a tradeable effect."""
    d = vals.copy()
    d[col] = d[col] + edge
    return clustered_mean(d, col, boot=500, seed=seed)


def report(real: dict, plac: dict, ctrl: dict, split: dict) -> str:
    L = ["=" * 76,
         "validate_runup — is there a week-to-month trade BEFORE an FDA decision?",
         "=" * 76, "",
         f"pooled, {BENCH}-relative, window ends 2 sessions before the print",
         "so the binary itself is never inside it.", "",
         f"  {'horizon':<10}{'n':>6}{'mean':>9}{'median':>9}{'win%':>8}"
         f"{'z':>8}   placebo z"]
    for h in HORIZONS:
        r, p = real[h], plac.get(h, {})
        L.append(f"  {h:>3}d      {r['n']:>6}{r['mean']:>8.2f}%"
                 f"{r['median']:>8.2f}%{r['win']*100:>7.0f}%{r['z']:>8.2f}"
                 f"      {p.get('z', float('nan')):>6.2f}")
    L += ["", f"[control] a planted +1.00% at 20d is seen at "
              f"z={ctrl['z']:+.2f} (measured {ctrl['mean']:+.2f}%)"]
    ok = abs(ctrl["z"]) >= BAR_Z
    L.append("          " + ("PASS — the harness can detect a drift worth "
                             "trading." if ok else
                             "FAIL — nothing below is readable as a null."))
    pl_ok = all(abs(plac.get(h, {}).get("z", 0)) < BAR_Z for h in HORIZONS)
    L.append(f"[placebo] random windows on the same names: "
             + ("clean." if pl_ok else "FIRED — the label is not the thing."))
    best = max(HORIZONS, key=lambda h: abs(real[h]["z"]) if real[h]["z"] == real[h]["z"] else 0)
    L += ["", "-" * 76, "VERDICT"]
    if not ok:
        L.append("  UNREADABLE — fix the harness before reading anything.")
    elif not pl_ok:
        L.append("  UNREADABLE — the placebo fired.")
    elif abs(real[best]["z"]) >= BAR_Z:
        L.append(f"  ADOPT at {best}d: {real[best]['mean']:+.2f}% "
                 f"{BENCH}-relative, z={real[best]['z']:+.2f}, "
                 f"n={real[best]['n']}.")
        L.append("  This is an UPPER BOUND: the sample is dated by the decision "
                 "that actually")
        L.append("  landed, while a live entry uses the disclosed PDUFA date, "
                 "which moves.")
    else:
        L.append("  REJECT — #37. No horizon clears the pre-registered bar "
                 f"(|z| >= {BAR_Z},")
        L.append("  raised for having asked four). The run-up into an FDA "
                 "decision is one of")
        L.append("  the most-repeated claims in biotech trading and it is not "
                 "in this sample.")
    L += ["", "-" * 76,
          "DIAGNOSTIC ONLY — split by outcome. NOT TRADEABLE: ex ante you do",
          "not know which of these you are holding.", ""]
    for k, d in split.items():
        L.append(f"  {k:<10} 20d {d['mean']:+6.2f}%  median {d['median']:+6.2f}%"
                 f"  n={d['n']}")
    if split.get("CRL") and split.get("APPROVAL"):
        gap = split["CRL"]["mean"] - split["APPROVAL"]["mean"]
        L.append(f"  difference {gap:+.2f}pp — if this were large it would mean "
                 "the market")
        L.append("  anticipates outcomes, which is a different and much bigger "
                 "claim.")
    L.append("-" * 76)
    return "\n".join(L)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--events", default=EVENTS)
    ap.add_argument("--boot", type=int, default=BOOT)
    a = ap.parse_args(argv)
    ev = load_events(a.events)
    ev = ev[ev["ticker"].fillna("").astype(str).str.strip().ne("")]
    print(f"events with a ticker: {len(ev):,}", flush=True)
    tickers = sorted(ev["ticker"].unique())
    px = fetch_prices(tickers)
    bench = bench_series()
    if bench is None:
        print(f"cannot fetch {BENCH} — no benchmark, no readable result")
        return 1
    vals = sample(ev, px, bench)
    print(f"events with usable price history: {len(vals):,}", flush=True)
    real = {h: clustered_mean(vals, f"h{h}", a.boot) for h in HORIZONS}
    pl = placebo(px, bench, tickers)
    plac = {h: clustered_mean(pl, f"h{h}", max(400, a.boot // 4))
            for h in HORIZONS} if len(pl) else {}
    ctrl = positive_control(vals, "h20")
    split = {k: clustered_mean(g, "h20", 400)
             for k, g in vals.groupby("kind")}
    print(report(real, plac, ctrl, split))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
