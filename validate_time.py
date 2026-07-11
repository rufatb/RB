#!/usr/bin/env python3
"""
validate_time.py — is 9:45 the right decision time, or does another time
predict close-direction better (net of the shrinking capture window)?

For each candidate decision time T (a completed 5m bar): features known at T
(r0 = open->T return, gap, vp = relative volume through T), outcome = T->close
return. Same walk-forward k-NN, same 0.55 bar, same peer gate, same densest
PAIR selection as live. Chronological discovery/confirm split + odd/even.
Judged on: pair hit rate AND avg capture (hit rate alone favours late times
mechanically — less time left, smaller moves, easier to be "right").

RESULT (2026-07-11): 9:45 dominated every alternative on every metric and was
the ONLY stable time across all four splits:
    9:40  48.9% hit, +0.073% capture (odd/even 60/38 — noise)
    9:45  68.5% hit, +0.390% capture (68/69/70/67 across splits)
    9:50  58.9%, +0.096%   10:00  61.1%, +0.148%   10:30  64.5%, +0.191%
    11:00 55.3%, +0.075%   (median remaining |move| decays 0.74%→0.53%)
CAVEAT stated honestly: every hyperparameter (K, M, the 0.55 bar, density
selection) was developed against the 9:45 configuration, so alternatives run
with borrowed settings — this test can't prove 9:45 is globally optimal, but
it shows NO alternative beats it and the neighbours (9:40/9:50) are sharply
worse, i.e. the 15-minute mark is a real structural point (opening rotation
has resolved; most of the day remains), not an arbitrary habit.
"""
import os
import sys
import numpy as np
import pandas as pd
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from adapters import YahooDirectAdapter
from dashboard import load_config
import r945

cfg = load_config(os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.yaml"))
GROUPS = cfg.get("peer_groups") or {}
MIN_OPP = cfg.get("peer_contradiction_min", 3)
G_OF = {t: g for g, ms in GROUPS.items() for t in ms}
MIN_P = 0.55

# bar index i -> decision time 9:30 + 5*(i+1)
TIMES = [(0, "09:35"), (1, "09:40"), (2, "09:45 (current)"), (3, "09:50"),
         (4, "09:55"), (5, "10:00"), (8, "10:15"), (11, "10:30"), (17, "11:00")]

a = YahooDirectAdapter(exchange_tz=cfg["exchange_tz"])
def fetch(t):
    try:
        return t, a._bars_df(a._chart(t, "5m", "60d"))
    except Exception:
        return t, pd.DataFrame()
with ThreadPoolExecutor(max_workers=8) as ex:
    fetched = dict(ex.map(fetch, cfg["scan"]["universe"]))

def rows_at(bars, ticker, i):
    """Session rows with the decision point at bar index i (close of that bar)."""
    rows, prev_close = [], None
    for d, day in bars.groupby(bars.index.date):
        day = day.sort_index()
        if len(day) < max(10, i + 3):     # need bar i complete + meaningful rest-of-day
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

def pair_run(df):
    """Walk-forward densest-pair legs for one decision time. Returns leg list."""
    dates = sorted(df["date"].unique())
    legs, day_dates = [], []
    for d in dates:
        train = df[df["date"] < d].copy()
        if len(train.dropna(subset=["r0", "gap", "v15", "r1"])) < 200:
            continue
        med = train.groupby("t")["v15"].median()
        train["vp"] = train.apply(lambda r: r["v15"] / med[r["t"]] if med.get(r["t"]) else None, axis=1)
        board = []
        for _, row in df[df["date"] == d].iterrows():
            t = row["t"]
            vp = row["v15"] / med[t] if t in med and med[t] else None
            p, n, nd = r945.knn_probability(train, {"r0": row["r0"], "gap": row["gap"], "vp": vp})
            if p is None:
                continue
            side = "LONG" if p >= MIN_P else ("SHORT" if 1 - p >= MIN_P else None)
            if side is None:
                continue
            board.append({"date": d, "t": t, "side": side, "nd": nd,
                          "sided": p if side == "LONG" else 1 - p,
                          "hit": int(row["r1"] > 0) if side == "LONG" else int(row["r1"] < 0),
                          "capt": row["r1"] if side == "LONG" else -row["r1"]})
        longs = [b for b in board if b["side"] == "LONG"]
        shorts = [b for b in board if b["side"] == "SHORT"]
        ln, sn = {}, {}
        for b in longs:
            g = G_OF.get(b["t"]);  ln[g] = ln.get(g, 0) + 1 if g else 0
        for b in shorts:
            g = G_OF.get(b["t"]);  sn[g] = sn.get(g, 0) + 1 if g else 0
        longs = [b for b in longs if not (G_OF.get(b["t"]) and sn.get(G_OF[b["t"]], 0) >= MIN_OPP)]
        shorts = [b for b in shorts if not (G_OF.get(b["t"]) and ln.get(G_OF[b["t"]], 0) >= MIN_OPP)]
        day_dates.append(d)
        for pk in (longs, shorts):
            if pk:
                legs.append(min(pk, key=lambda b: b["nd"]))
    return legs, day_dates

print(f"{'time':<16}{'legs':>5} {'hit%':>6} {'capt%':>7}   {'disc%':>6} {'conf%':>6}  {'odd%':>5} {'even%':>6}   {'|move|':>7}")
for i, label in TIMES:
    all_rows = []
    for t, bars in fetched.items():
        if not bars.empty:
            all_rows += rows_at(bars, t, i)
    df = pd.DataFrame(all_rows)
    legs, days = pair_run(df)
    if not legs:
        print(f"{label:<16} no legs")
        continue
    cut = days[int(len(days) * 0.6)]
    idx_of = {d: k for k, d in enumerate(days)}
    def stat(sub):
        return (np.mean([b["hit"] for b in sub]) * 100) if sub else float("nan")
    disc = [b for b in legs if b["date"] < cut]
    conf = [b for b in legs if b["date"] >= cut]
    odd = [b for b in legs if idx_of[b["date"]] % 2 == 1]
    even = [b for b in legs if idx_of[b["date"]] % 2 == 0]
    med_abs = df["r1"].abs().median()      # typical remaining move at this time
    print(f"{label:<16}{len(legs):>5} {stat(legs):>6.1f} "
          f"{np.mean([b['capt'] for b in legs]):>+7.3f}   "
          f"{stat(disc):>6.1f} {stat(conf):>6.1f}  {stat(odd):>5.1f} {stat(even):>6.1f}   "
          f"{med_abs:>6.2f}%")
