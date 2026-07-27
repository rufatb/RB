#!/usr/bin/env python3
"""
validate_twins.py — the deep validation, rebuilt FREE and 2x bigger (day-22).

WHY THIS EXISTS: validate_deep.py needs a TwelveData key AND a scratchpad of
pre-downloaded JSON that does not survive a session. That made the repo's only
deep-validation protocol unrunnable — so claims could not be re-checked, which
is precisely how a 60-day artifact becomes permanent. This script rebuilds an
equivalent (larger) dataset from Yahoo alone, every time, with no key.

THE DATA: Yahoo caps 5-minute bars at 60 days, but serves HOURLY bars for 720.
TSX hourly bars come back with volume zeroed (86% of rows — measured), which
kills the `vp` feature; the US dual-listings do not, so the 20 twins are used
exactly as day-14 used them. Result: ~9,651 ticker-sessions over ~490 sessions
— nearly 2x the paid TwelveData study's 5,160.

THE CAVEAT (do not strip): the first hourly bar closes at 10:30, so this set's
entry is 10:30, NOT the live 9:45. It is a MECHANISM sample — it can refute or
support how a rule behaves, and it cannot certify live 9:45 levels or prices.
US lines also diverge from TSX intraday via FX. Nothing here may be quoted as a
live expectation; the ledger's PAIR line remains the arbiter.

PRE-REGISTERED PROTOCOL (inherited from validate_deep.py): sessions split into
4 contiguous calendar blocks; a claim validates only if directionally
consistent in ALL FOUR.

RESULTS (2026-07-27, first run — recorded so the verdicts are permanent):
  * NO selector separates from placebo: densest 50.1% / max-P 48.3% /
    2nd-densest 50.7% / random 50.2% across 809 legs — a spread well inside
    one standard error (1.7pp). At this horizon the selection layer is inert.
  * REJECTED beta-matched pairing (H1): quarters +0.009/+0.046/-0.060/+0.016.
  * REJECTED tide-removed training target (H2): +0.020/-0.001/+0.004/-0.032.
  * REJECTED both combined (H3): +0.036/-0.021/+0.052/+0.044, and its effect
    is smaller than the 2nd-densest placebo's.
  * REJECTED "one-legged days are structurally worse": +0.029%/day vs hedged
    -0.012%, quarters flip sign.
  * REFUTED the short-side capture asymmetry ("~2.7x more per win"): 1.00x for
    shorts, 0.98x for longs.
  * ADOPTED equal-risk leg weighting: NET std 0.587 -> 0.518, lower in ALL
    FOUR quarters, worst day -2.22% -> -1.52%, mean unchanged. It is a variance
    identity, not a prediction — which is why it survived where alpha did not.

Usage:
    python validate_twins.py                 # rebuild + run the full protocol
    python validate_twins.py --cache DIR     # reuse a previously built csv
"""

from __future__ import annotations

import argparse
import os
import sys
import time

import numpy as np
import pandas as pd
import requests

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import r945
from dashboard import load_config

# TSX name -> US dual-listing. The row keeps the TSX label so config
# peer_groups apply unchanged.
TWINS = {
    "RY.TO": "RY", "TD.TO": "TD", "BNS.TO": "BNS", "BMO.TO": "BMO",
    "CM.TO": "CM", "ENB.TO": "ENB", "TRP.TO": "TRP", "CNQ.TO": "CNQ",
    "SU.TO": "SU", "CVE.TO": "CVE", "CP.TO": "CP", "CNR.TO": "CNI",
    "SHOP.TO": "SHOP", "ABX.TO": "B", "AEM.TO": "AEM", "NTR.TO": "NTR",
    "MFC.TO": "MFC", "SLF.TO": "SLF", "BCE.TO": "BCE", "T.TO": "TU",
}
HEADERS = {"User-Agent": "Mozilla/5.0"}
ENTRY_IDX, MIN_BARS = 0, 5          # first hourly bar closes 10:30


def fetch_hourly(us: str, days: int = 720, tries: int = 4):
    """Hourly bars via the raw chart endpoint, failing over query1 -> query2."""
    now = time.time()
    for host in ("query1", "query2"):
        for attempt in range(tries):
            try:
                r = requests.get(
                    f"https://{host}.finance.yahoo.com/v8/finance/chart/{us}",
                    params={"interval": "1h", "period1": int(now - days * 86400),
                            "period2": int(now)},
                    headers=HEADERS, timeout=45)
                res = (r.json().get("chart") or {}).get("result")
                if res:
                    return res[0]
            except Exception:
                time.sleep(1.5 * (attempt + 1))
    return None


def bars_df(result: dict) -> pd.DataFrame:
    ts = result.get("timestamp") or []
    q = (result.get("indicators", {}).get("quote") or [{}])[0]
    if not ts:
        return pd.DataFrame()
    idx = pd.to_datetime(ts, unit="s", utc=True).tz_convert("America/New_York")
    df = pd.DataFrame({"Open": q.get("open"), "High": q.get("high"),
                       "Low": q.get("low"), "Close": q.get("close"),
                       "Volume": q.get("volume")}, index=idx).dropna(subset=["Close"])
    return df.between_time("09:30", "15:59")   # regular session only


def session_rows(bars: pd.DataFrame, ticker: str) -> list:
    """Mirrors r945.session_rows exactly, with the entry bar parameterised to
    this dataset's granularity (first hourly bar instead of the third 5m bar)."""
    rows, prev_close = [], None
    for d, day in bars.groupby(bars.index.date):
        day = day.sort_index()
        if len(day) < MIN_BARS:
            if len(day):
                prev_close = day["Close"].iloc[-1]
            continue
        o, pe, c = day["Open"].iloc[0], day["Close"].iloc[ENTRY_IDX], day["Close"].iloc[-1]
        gap = (o / prev_close - 1) * 100 if prev_close else None
        prev_close = c
        if not o or not pe:
            continue
        rows.append({"t": ticker, "date": str(d), "gap": gap,
                     "r0": (pe / o - 1) * 100,
                     "v15": float(day["Volume"].iloc[:ENTRY_IDX + 1].sum()),
                     "r1": (c / pe - 1) * 100})
    return rows


def build(cache: str | None = None) -> pd.DataFrame:
    if cache and os.path.exists(cache):
        print(f"using cached dataset {cache}")
        return pd.read_csv(cache)
    rows = []
    for i, (tsx, us) in enumerate(TWINS.items(), 1):
        res = fetch_hourly(us)
        if not res:
            print(f"  [{i}/{len(TWINS)}] {tsx:9s} FETCH FAILED — skipped")
            continue
        b = bars_df(res)
        rows += session_rows(b, tsx)
        print(f"  [{i}/{len(TWINS)}] {tsx:9s}<-{us:5s} {len(b):5d} bars", flush=True)
    df = pd.DataFrame(rows)
    if cache:
        df.to_csv(cache, index=False)
    return df


# ── walk-forward, faithful to live r945: rolling window, past-only training ──
def walk_forward(df: pd.DataFrame, cfg: dict, train_sessions: int = 60,
                 min_train: int = 200) -> list:
    groups = cfg.get("peer_groups") or {}
    g_of = {t: g for g, ms in groups.items() for t in ms}
    min_opp = cfg.get("peer_contradiction_min", 3)
    min_p = (cfg.get("report") or {}).get("min_sided_p", 0.55)
    df = df.dropna(subset=["r1"]).copy()
    df["m"] = df.groupby("date")["r1"].transform("median")   # the tide
    dates = sorted(df["date"].unique())
    day_log = []
    for i, d in enumerate(dates):
        win = set(dates[max(0, i - train_sessions):i])
        if not win:
            continue
        train = df[df["date"].isin(win)].copy()
        med = train.groupby("t")["v15"].median()
        train["vp"] = [r.v15 / med[r.t] if med.get(r.t) else np.nan
                       for r in train.itertuples()]
        if len(train.dropna(subset=r945.FEATS + ["r1"])) < min_train:
            continue
        vol = train.groupby("t")["r1"].std()
        board = []
        for row in df[df["date"] == d].itertuples():
            vp = row.v15 / med[row.t] if row.t in med.index and med[row.t] else None
            p, _, nd = r945.knn_probability(
                train, {"r0": row.r0, "gap": row.gap, "vp": vp})
            if p is None:
                continue
            side = "LONG" if p >= min_p else ("SHORT" if 1 - p >= min_p else None)
            if side is None:
                continue
            board.append({"date": d, "t": row.t, "side": side, "nd": nd,
                          "sided": p if side == "LONG" else 1 - p,
                          "vol": float(vol.get(row.t)) if np.isfinite(vol.get(row.t, np.nan)) else None,
                          "hit": int(row.r1 > 0) if side == "LONG" else int(row.r1 < 0),
                          "capt": row.r1 if side == "LONG" else -row.r1})
        longs = sorted([b for b in board if b["side"] == "LONG"], key=lambda b: -b["sided"])
        shorts = sorted([b for b in board if b["side"] == "SHORT"], key=lambda b: -b["sided"])
        ln, sn = {}, {}
        for b in longs:
            if g_of.get(b["t"]):
                ln[g_of[b["t"]]] = ln.get(g_of[b["t"]], 0) + 1
        for b in shorts:
            if g_of.get(b["t"]):
                sn[g_of[b["t"]]] = sn.get(g_of[b["t"]], 0) + 1
        longs = [b for b in longs if not (g_of.get(b["t"]) and sn.get(g_of[b["t"]], 0) >= min_opp)]
        shorts = [b for b in shorts if not (g_of.get(b["t"]) and ln.get(g_of[b["t"]], 0) >= min_opp)]
        day_log.append({"date": d, "longs": longs, "shorts": shorts})
    return day_log


SELECTORS = {
    "densest (SHIPPED)": lambda pk: min(pk, key=lambda b: b["nd"]),
    "max-P": lambda pk: max(pk, key=lambda b: b["sided"]),
    "2nd-densest (placebo)": lambda pk: sorted(pk, key=lambda b: b["nd"])[1] if len(pk) > 1 else pk[0],
}


def main(argv=None):
    ap = argparse.ArgumentParser(description="free 2-year deep validation (US twins)")
    ap.add_argument("--cache", default=None, help="csv path to build once and reuse")
    args = ap.parse_args(argv)
    cfg = load_config(os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.yaml"))

    df = build(args.cache)
    if df.empty:
        print("no data fetched — aborting rather than reporting on nothing")
        return 1
    print(f"\ndeep twin set: {len(df)} ticker-sessions, {df['t'].nunique()} names, "
          f"{df['date'].nunique()} sessions ({df['date'].min()}..{df['date'].max()})")
    print("ENTRY = 10:30 (first hourly bar) — MECHANISM proxy, not live 9:45 levels.\n")

    day_log = walk_forward(df, cfg)
    dates = [d["date"] for d in day_log]
    blocks = np.array_split(np.array(dates), 4)
    qof = {d: i for i, b in enumerate(blocks) for d in b}
    allq = [b for d in day_log for b in d["longs"] + d["shorts"]]
    print(f"walk-forward: {len(day_log)} sessions, {len(allq)} qualified picks, "
          f"pool hit {np.mean([b['hit'] for b in allq])*100:.1f}%\n")

    print("A) SELECTORS vs PLACEBO (one standard error ~1.7pp — read the spread, not the rank)")
    for name, rule in SELECTORS.items():
        legs = [rule(d[s]) | {"q": qof[d["date"]]} for d in day_log
                for s in ("longs", "shorts") if d[s]]
        per = "/".join(f"{np.mean([b['hit'] for b in legs if b['q'] == q])*100:.1f}"
                       for q in range(4))
        print(f"   {name:<24} n={len(legs):>4}  hit {np.mean([b['hit'] for b in legs])*100:5.1f}%  "
              f"capt {np.mean([b['capt'] for b in legs]):+.3f}%  by-quarter {per}")

    print("\nB) EQUAL-DOLLAR vs EQUAL-RISK leg weighting (the day-22 adoption)")
    cap = (cfg.get("pair") or {}).get("weight_cap", 0.35)
    rows = []
    for d in day_log:
        if not (d["longs"] and d["shorts"]):
            continue
        legs = [min(d["longs"], key=lambda b: b["nd"]), min(d["shorts"], key=lambda b: b["nd"])]
        v = [b["vol"] for b in legs]
        if any(x is None or not np.isfinite(x) or x <= 0 for x in v):
            continue
        w = np.array([1 / x for x in v]); w = w / w.sum()
        w = np.clip(w, cap, 1 - cap); w = w / w.sum()
        rows.append({"q": qof[d["date"]],
                     "eq": float(np.mean([b["capt"] for b in legs])),
                     "rw": float(np.dot(w, [b["capt"] for b in legs]))})
    R = pd.DataFrame(rows)
    if len(R):
        for lab, c in (("equal-DOLLAR", "eq"), ("equal-RISK  ", "rw")):
            print(f"   {lab}: NET {R[c].mean():+.4f}%/day  std {R[c].std():.3f}  "
                  f"worst {R[c].min():+.2f}%  P(NET>0) {100*(R[c]>0).mean():.1f}%  n={len(R)}")
        ok = sum(R[R.q == q]["rw"].std() < R[R.q == q]["eq"].std() for q in range(4))
        for q in range(4):
            s = R[R.q == q]
            print(f"     Q{q+1} n={len(s):>3}  std {s['eq'].std():.3f} -> {s['rw'].std():.3f} "
                  f"({100*(s['rw'].std()/s['eq'].std()-1):+.1f}%)")
        print(f"   -> quarters with LOWER volatility: {ok}/4 "
              f"({'ADOPTED' if ok == 4 else 'would NOT meet the bar'})")

    print("\nVERDICT RULE: a claim validates only if directionally consistent in "
          "ALL FOUR quarters.\nEntry here is 10:30 — mechanism only. Never quote "
          "these as live 9:45 expectations.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
