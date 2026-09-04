#!/usr/bin/env python3
"""
validate_us.py — day-85. Five US strategies at two horizons.

Pre-registered in PREREGISTER_day85.md. The bar was fixed there and is not
restated loosely: |t| >= 3 on the market-relative statistic AND the same sign
in all four contiguous blocks. Both, not either.

  H1  overnight vs intraday decomposition        intraday
  H2  post-earnings-announcement drift           weekly
  H3  earnings-gap continuation vs fade          intraday
  H4  cross-sectional weekly reversal            weekly
  H5  52-week-high proximity momentum            weekly

A DISCLOSED DEVIATION ON H1. The pre-registration requires a market-relative
statistic on every arm. For H1 that transform is DEGENERATE: the benchmark here
is the equal-weighted cross-section, so subtracting it from a cross-sectional
mean gives identically zero and would "prove" no effect by construction. H1 is
therefore reported in ABSOLUTE terms with SPY's own split printed beside it as
an external check. This is a deviation from the registered protocol, it is
recorded here rather than quietly applied, and it does not touch the other four
arms.

WHY THE ARMS ARE CLUSTERED DIFFERENTLY. Cross-sectional arms (H1, H4, H5)
resample DATES, because every name shares that day's market move. Event arms
(H2, H3) resample NAMES, because one issuer contributes many announcements.
Using the wrong one treats correlated observations as independent information
and narrows every interval.

SURVIVORSHIP, which cannot be removed with free data. The universe is TODAY's
listing, so names that fell and delisted are absent. This inflates loser-side
results — H4 ranks INTO that hole, which is why it carries day-32's three
dissolving tests as an extra hurdle and H5 does not.
"""

from __future__ import annotations

import argparse
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "data")
BOOT = 2000
SEED = 0
ADOPT_T = 3.0
BLOCKS = 4
SPREAD_BPS = 5.0          # round-trip, US large caps; both gross and net shown


# ── loading ────────────────────────────────────────────────────────────────

def load_panel() -> pd.DataFrame:
    p = os.path.join(DATA, "us_daily.csv")
    if not os.path.exists(p):
        raise FileNotFoundError(f"{p} missing — run `python build_us.py` first.")
    df = pd.read_csv(p)
    df = df.sort_values(["t", "date"]).reset_index(drop=True)
    # the market: equal-weighted cross-section, per window
    for col in ("daily", "intraday", "overnight"):
        df[f"mkt_{col}"] = df.groupby("date")[col].transform("mean")
        df[f"rel_{col}"] = df[col] - df[f"mkt_{col}"]
    return df


def load_earnings() -> pd.DataFrame:
    p = os.path.join(DATA, "us_earnings.csv")
    if not os.path.exists(p):
        raise FileNotFoundError(f"{p} missing — run `python build_us.py` first.")
    return pd.read_csv(p)


# ── statistics ─────────────────────────────────────────────────────────────

def boot(rows: list, field: str, cluster: str, n: int = BOOT,
         seed: int = SEED) -> tuple:
    """Mean with a CLUSTERED 95% interval. `cluster` is 'date' or 't'."""
    by: dict = {}
    for r in rows:
        v = r.get(field)
        if v is None or not np.isfinite(v):
            continue
        by.setdefault(r[cluster], []).append(v)
    keys = sorted(by)
    if len(keys) < 20:
        return (None, None, None)
    flat = [v for k in keys for v in by[k]]
    rng = np.random.default_rng(seed)
    draws = []
    for _ in range(n):
        pick = rng.integers(0, len(keys), size=len(keys))
        d = [v for i in pick for v in by[keys[i]]]
        if d:
            draws.append(float(np.mean(d)))
    if not draws:
        return (None, None, None)
    return (float(np.mean(flat)), float(np.quantile(draws, 0.025)),
            float(np.quantile(draws, 0.975)))


def se_of(lo, hi):
    return None if lo is None else (hi - lo) / (2 * 1.96)


def power(rows, field, cluster, edge, seed=SEED + 7):
    """POSITIVE CONTROL. edge / sd, never (mean + edge) / sd — the day-56 error."""
    _, lo, hi = boot(rows, field, cluster, n=800, seed=seed)
    sd = se_of(lo, hi)
    return None if not sd else edge / sd


def blocks(rows: list, field: str, k: int = BLOCKS) -> list:
    dates = sorted({r["date"] for r in rows})
    if len(dates) < k * 10:
        return []
    out = []
    for chunk in np.array_split(np.array(dates), k):
        s = set(chunk.tolist())
        v = [r[field] for r in rows
             if r["date"] in s and r.get(field) is not None
             and np.isfinite(r[field])]
        out.append(float(np.mean(v)) if v else float("nan"))
    return out


def consistent(bs: list) -> bool:
    return bool(bs) and all(np.isfinite(b) for b in bs) and (
        all(b > 0 for b in bs) or all(b < 0 for b in bs))


def win_rate(rows: list, field: str) -> tuple:
    v = [r[field] for r in rows if r.get(field) is not None and np.isfinite(r[field])]
    if not v:
        return (None, 0)
    return (float(np.mean([x > 0 for x in v]) * 100), len(v))


def net_of_cost(m, spread_bps: float):
    """Cost moves an effect TOWARD zero and stops there.

    The naive `m - cost * sign(m)` overshoots: a +0.016% gross effect became
    -0.034% net against a 5bp round trip, which reads as a reversed edge rather
    than an erased one. An effect smaller than its cost is worth zero, not
    worth its own negative.
    """
    if m is None:
        return None
    cost = spread_bps / 100.0
    return float(np.sign(m) * max(0.0, abs(m) - cost))


def verdict(m, lo, hi, bs, plo, phi, net) -> str:
    if m is None:
        return "NOT COMPUTABLE"
    se = se_of(lo, hi)
    t = m / se if se else None
    mde = ADOPT_T * se if se else None
    if t is None:
        return "NOT COMPUTABLE"
    if abs(t) < ADOPT_T and mde is not None and abs(m) < mde:
        return f"UNDERPOWERED — cannot resolve below {mde:.3f}%"
    if abs(t) < ADOPT_T:
        return f"BELOW the bar (|t|={abs(t):.2f} < {ADOPT_T:.0f})"
    if not consistent(bs):
        return (f"FAILS block consistency (|t|={abs(t):.2f} clears, "
                f"sign flips across blocks)")
    if plo is not None and plo <= m <= phi:
        return f"INSIDE the placebo band [{plo:+.3f}, {phi:+.3f}]"
    if net is not None and net == 0.0 and m != 0.0:
        return (f"CLEARS gross (|t|={abs(t):.2f}) but is ERASED by cost — "
                f"the whole effect is smaller than the round trip")
    return f"CLEARS the bar (|t|={abs(t):.2f}, consistent, outside placebo)"


def report(title: str, rows: list, field: str, cluster: str,
           placebo: tuple = (None, None), control_edge: float = 0.10,
           spread_bps: float = SPREAD_BPS, extra: list = None) -> str:
    m, lo, hi = boot(rows, field, cluster)
    L = [f"▎{title}", f"   n={len(rows):,}  clustered by "
         f"{'session' if cluster == 'date' else 'name'} "
         f"({len({r[cluster] for r in rows}):,} clusters)"]
    if m is None:
        return "\n".join(L + ["   not computable on this sample"])
    wr, nw = win_rate(rows, field)
    net = net_of_cost(m, spread_bps)
    L.append(f"   effect     {m:+7.3f}%   95% [{lo:+.3f}, {hi:+.3f}]"
             + (f"   win {wr:.1f}%" if wr is not None else ""))
    bs = blocks(rows, field)
    if bs:
        L.append("   blocks     " + "  ".join(f"{b:+.3f}" for b in bs)
                 + f"   {'consistent' if consistent(bs) else 'SIGN FLIPS'}")
    plo, phi = placebo
    if plo is not None:
        L.append(f"   placebo    [{plo:+.3f}, {phi:+.3f}] — observed is "
                 f"{'INSIDE it' if plo <= m <= phi else 'OUTSIDE it'}")
    z = power(rows, field, cluster, control_edge)
    if z:
        L.append(f"   control    a planted {control_edge:.2f}% edge registers "
                 f"at z={z:.2f}")
    if net is not None:
        L.append(f"   net        {net:+.3f}% after {spread_bps:.0f}bps round trip")
    for line in (extra or []):
        L.append(f"   {line}")
    L.append(f"   -> {verdict(m, lo, hi, bs, plo, phi, net)}")
    return "\n".join(L)


# ── H1: overnight vs intraday ──────────────────────────────────────────────

def h1(df: pd.DataFrame) -> str:
    daily = df.groupby("date")[["overnight", "intraday", "daily"]].mean()
    rows = [{"date": d, "overnight": r.overnight, "intraday": r.intraday,
             "gap": r.overnight - r.intraday, "t": "MKT"}
            for d, r in daily.iterrows()]
    out = ["▎H1 overnight vs intraday — the window the engine actually trades",
           f"   {len(df):,} ticker-days aggregated to {len(rows):,} sessions",
           "   DISCLOSED DEVIATION: the market-relative transform is degenerate",
           "   here (the benchmark IS the cross-section), so this arm is",
           "   absolute, with SPY printed beside it as an external check."]
    for lbl, f in (("overnight", "overnight"), ("intraday", "intraday")):
        m, lo, hi = boot(rows, f, "date")
        wr, _ = win_rate(rows, f)
        ann = m * 252 if m is not None else None
        out.append(f"   {lbl:<10} {m:+7.4f}%/session  95% [{lo:+.4f}, {hi:+.4f}]"
                   f"   win {wr:.1f}%   ~{ann:+.1f}%/yr")
    out.append("")
    out.append(report("H1 difference (overnight minus intraday)", rows, "gap",
                      "date", control_edge=0.02, spread_bps=0.0,
                      extra=["cost note: an overnight expression crosses the",
                             "spread at the close AND at the open, and day-24",
                             "measured one night at 2x volatility with a 2.3x",
                             "worse tail. Neither is in the figure above."]))
    return "\n".join(out)


def spy_check() -> str:
    try:
        import build_us as B
        res = B.fetch_daily("SPY")
        rows = B.daily_rows("SPY", res) if res else []
    except Exception as e:                      # noqa: BLE001 — reported
        return f"   SPY control unavailable: {e!r}"
    if not rows:
        return "   SPY control unavailable: no usable bars"
    o = float(np.mean([r["overnight"] for r in rows]))
    i = float(np.mean([r["intraday"] for r in rows]))
    return (f"   SPY itself: overnight {o:+.4f}%/session (~{o * 252:+.1f}%/yr), "
            f"intraday {i:+.4f}%/session (~{i * 252:+.1f}%/yr), n={len(rows):,}")


# ── forward returns, shared by the weekly arms ─────────────────────────────

def add_forward(df: pd.DataFrame, horizons=(5, 10, 20)) -> pd.DataFrame:
    g = df.groupby("t", sort=False)
    for h in horizons:
        fwd = g["close"].shift(-h) / df["close"] - 1
        mkt = df.groupby("date")["close"].transform("size")   # placeholder shape
        df[f"f{h}"] = fwd * 100
    # market leg over the SAME window, equal-weighted across names present
    for h in horizons:
        df[f"mf{h}"] = df.groupby("date")[f"f{h}"].transform("mean")
        df[f"rel{h}"] = df[f"f{h}"] - df[f"mf{h}"]
    return df


# ── H2 / H3: the earnings arms ─────────────────────────────────────────────

def earnings_rows(df: pd.DataFrame, ern: pd.DataFrame) -> tuple:
    """Attach each announcement to its REACTION session and forward returns.

    AFTER_CLOSE  -> the reaction is the NEXT session
    BEFORE_OPEN  -> the reaction is the SAME session
    IN_SESSION   -> excluded: daily bars cannot place an intraday announcement
    """
    idx = {}
    for t, sub in df.groupby("t", sort=False):
        idx[t] = (list(sub["date"]), sub.reset_index(drop=True))
    out, drop = [], {"no prices": 0, "in session": 0, "no reaction bar": 0,
                     "no forward window": 0}
    for e in ern.itertuples():
        if e.when == "IN_SESSION":
            drop["in session"] += 1
            continue
        if e.when == "UNKNOWN" or e.t not in idx:
            drop["no prices"] += 1
            continue
        dates, sub = idx[e.t]
        j = np.searchsorted(dates, e.date)
        if e.when == "AFTER_CLOSE":
            j = j + 1 if (j < len(dates) and dates[j] == e.date) else j
        if j >= len(dates) or j < 1:
            drop["no reaction bar"] += 1
            continue
        r = sub.iloc[j]
        if not np.isfinite(r["rel_daily"]) or not np.isfinite(r["rel_intraday"]):
            drop["no reaction bar"] += 1
            continue
        sign = 1.0 if r["rel_daily"] > 0 else -1.0
        row = {"t": e.t, "date": r["date"], "when": e.when,
               "reaction": float(r["rel_daily"]), "sign": sign,
               # H3: the engine's own window on the event day, signed by the gap
               "gap_sign": 1.0 if r["overnight"] > 0 else -1.0,
               "h3": float(r["rel_intraday"]) *
                     (1.0 if r["overnight"] > 0 else -1.0)}
        ok = False
        for h in (5, 10):
            v = r.get(f"rel{h}")
            if v is not None and np.isfinite(v):
                row[f"pead{h}"] = float(v) * sign
                ok = True
        if not ok:
            drop["no forward window"] += 1
        out.append(row)
    return out, drop


def placebo_event(df: pd.DataFrame, rows: list, field: str, h: int,
                  n: int = 60, seed: int = SEED + 31) -> tuple:
    """The same signed hold on RANDOM dates in the SAME names."""
    rng = np.random.default_rng(seed)
    names = sorted({r["t"] for r in rows})
    per = max(1, len(rows) // max(len(names), 1))
    pool = {}
    for t, sub in df.groupby("t", sort=False):
        s = sub.reset_index(drop=True)
        col = s.get(f"rel{h}")
        d = s.get("rel_daily")
        if col is None:
            continue
        pool[t] = (col.to_numpy(dtype=float), d.to_numpy(dtype=float))
    means = []
    for _ in range(n):
        draw = []
        for t in names:
            if t not in pool:
                continue
            fwd, rel = pool[t]
            hi = len(fwd) - h - 1
            if hi <= 5:
                continue
            for k in rng.integers(1, hi, size=per):
                if np.isfinite(fwd[k]) and np.isfinite(rel[k]):
                    draw.append(fwd[k] * (1.0 if rel[k] > 0 else -1.0))
        if draw:
            means.append(float(np.mean(draw)))
    if not means:
        return (None, None)
    return (float(np.quantile(means, 0.025)), float(np.quantile(means, 0.975)))


# ── H4 / H5: the cross-sectional arms ──────────────────────────────────────

def decile_rows(df: pd.DataFrame, key: str, horizon: int,
                long_high: bool) -> list:
    """Per date: mean forward market-relative return of the top decile minus
    the bottom, expressed as the LONG side minus the SHORT side."""
    out = []
    for d, sub in df.groupby("date", sort=False):
        s = sub[np.isfinite(sub[key]) & np.isfinite(sub[f"rel{horizon}"])]
        if len(s) < 30:
            continue
        lo_c, hi_c = s[key].quantile(0.1), s[key].quantile(0.9)
        hi_leg = s[s[key] >= hi_c][f"rel{horizon}"]
        lo_leg = s[s[key] <= lo_c][f"rel{horizon}"]
        if hi_leg.empty or lo_leg.empty:
            continue
        long_leg, short_leg = ((hi_leg, lo_leg) if long_high else (lo_leg, hi_leg))
        out.append({"date": d, "t": "XS",
                    "spread": float(long_leg.mean() - short_leg.mean()),
                    "long": float(long_leg.mean()),
                    "short": float(-short_leg.mean()),
                    "n": len(s)})
    return out


def placebo_xs(df: pd.DataFrame, key: str, horizon: int, long_high: bool,
               n: int = 40, seed: int = SEED + 41) -> tuple:
    """The feature SHUFFLED across names within each date."""
    rng = np.random.default_rng(seed)
    means = []
    sub = df[np.isfinite(df[key]) & np.isfinite(df[f"rel{horizon}"])]
    for _ in range(n):
        s = sub.copy()
        s[key] = s.groupby("date")[key].transform(
            lambda x: x.to_numpy()[rng.permutation(len(x))])
        r = decile_rows(s, key, horizon, long_high)
        if r:
            means.append(float(np.mean([x["spread"] for x in r])))
    if not means:
        return (None, None)
    return (float(np.quantile(means, 0.025)), float(np.quantile(means, 0.975)))


def dissolving_tests(df: pd.DataFrame, key: str, horizon: int,
                     long_high: bool) -> list:
    """Day-32's three. A cross-sectional sort that survives the bar but fails
    these is a survivorship or beta artefact, not an edge."""
    L = []
    rows = decile_rows(df, key, horizon, long_high)
    if not rows:
        return ["dissolving tests: not computable"]
    v = np.array([r["spread"] for r in rows])
    L.append(f"tail test   mean {v.mean():+.3f}%  MEDIAN {np.median(v):+.3f}%  "
             f"win {100 * np.mean(v > 0):.1f}%  "
             f"{'TAIL-CARRIED' if abs(np.median(v)) < abs(v.mean()) / 2 else 'not tail-carried'}")
    mk = df.groupby("date")["daily"].mean()
    up = [r["spread"] for r in rows if mk.get(r["date"], 0) > 0]
    dn = [r["spread"] for r in rows if mk.get(r["date"], 0) <= 0]
    if up and dn:
        same = np.sign(np.mean(up)) == np.sign(np.mean(dn))
        L.append(f"beta test   market-up {np.mean(up):+.3f}%  "
                 f"market-down {np.mean(dn):+.3f}%  "
                 f"{'same sign' if same else 'BETA, NOT SELECTION'}")
    qs = []
    df = df.copy()
    df["dv"] = df["close"] * df["volume"]
    df["liq"] = df.groupby("date")["dv"].transform(
        lambda x: pd.qcut(x.rank(method="first"), 4, labels=False))
    for q in range(4):
        r = decile_rows(df[df["liq"] == q], key, horizon, long_high)
        qs.append(float(np.mean([x["spread"] for x in r])) if r else float("nan"))
    # A quartile too thin for a decile sort yields nan. That is NOT COMPUTABLE
    # and must never print as NOT SIZE-ROBUST — a data limit is not a finding.
    if not all(np.isfinite(q) for q in qs):
        tag = ("NOT COMPUTABLE — a liquidity quartile is too thin for a "
               "decile sort")
    elif all(q > 0 for q in qs) or all(q < 0 for q in qs):
        tag = "size-robust"
    else:
        tag = "NOT SIZE-ROBUST"
    L.append("size test   " + "  ".join(f"{q:+.3f}" for q in qs) + f"   {tag}")
    return L


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--spread", type=float, default=SPREAD_BPS)
    a = ap.parse_args(argv)

    print("loading the US panel")
    df = load_panel()
    print(f"  {len(df):,} ticker-days, {df['t'].nunique()} names, "
          f"{df['date'].min()} .. {df['date'].max()}")
    df = add_forward(df)
    ern = load_earnings()
    print(f"  {len(ern):,} earnings announcements, "
          f"{ern['t'].nunique()} names")

    print("\n" + "=" * 68)
    print(h1(df))
    print(spy_check())

    print("\n" + "=" * 68)
    erows, drop = earnings_rows(df, ern)
    print(f"▎earnings arms — {len(erows):,} usable announcements; dropped "
          + ", ".join(f"{v} {k}" for k, v in drop.items() if v))
    for h in (5, 10):
        sub = [r for r in erows if f"pead{h}" in r]
        if not sub:
            continue
        print()
        print(report(f"H2 post-earnings drift, {h}-session hold "
                     f"(signed by the reaction)", sub, f"pead{h}", "t",
                     placebo=placebo_event(df, sub, f"pead{h}", h),
                     spread_bps=a.spread))
    h3 = [r for r in erows if np.isfinite(r.get("h3", np.nan))]
    if h3:
        print()
        print(report("H3 earnings-day open->close, signed by the gap",
                     h3, "h3", "t", spread_bps=a.spread))

    print("\n" + "=" * 68)
    df["rev"] = df.groupby("t", sort=False)["close"].pct_change(5) * 100
    df["rev"] = df["rev"] - df.groupby("date")["rev"].transform("mean")
    r4 = decile_rows(df, "rev", 5, long_high=False)
    if r4:
        print(report("H4 weekly reversal — long losers, short winners, 5d",
                     r4, "spread", "date",
                     placebo=placebo_xs(df, "rev", 5, False),
                     spread_bps=a.spread * 2,
                     extra=dissolving_tests(df, "rev", 5, False)))

    print("\n" + "=" * 68)
    df["hi252"] = df.groupby("t", sort=False)["close"].transform(
        lambda s: s.rolling(252, min_periods=200).max())
    df["prox"] = df["close"] / df["hi252"]
    for h in (5, 20):
        r5 = decile_rows(df, "prox", h, long_high=True)
        if not r5:
            continue
        print()
        print(report(f"H5 52-week-high proximity — long near highs, {h}d",
                     r5, "spread", "date",
                     placebo=placebo_xs(df, "prox", h, True),
                     spread_bps=a.spread * 2))

    print("\n" + "=" * 68)
    print("   ── survivorship: the universe is TODAY's listing. Delisted names")
    print("      are absent, which inflates loser-side results. H4 ranks into")
    print("      that hole; H5 leans the other way.")
    print("   ── all five arms are reported whatever they did, per the")
    print("      pre-registration. None was dropped and none was promoted.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
