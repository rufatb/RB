#!/usr/bin/env python3
"""
validate_pair.py — the day-9 experiment behind THE PAIR's selection rule.
Re-run it any time; the rule must keep earning its place.

QUESTION: when the daily deliverable is exactly ONE long and ONE short, which
selection-time variable should pick them?

METHOD (no hindsight): replay the 60d/5m dataset walk-forward. For each
session d, train the pooled k-NN only on sessions < d, qualify at the 0.55
bar, apply the live peer gate, then (A) log every qualified pick with its
selection-time variables + outcome, and (B) apply each candidate top-1 rule.
Sessions split chronologically: first 60% = DISCOVERY, last 40% = CONFIRM,
plus an independent odd/even split and a 2nd-densest placebo in part C.
A variable/rule only counts if it helps on BOTH splits (replication
discipline: a pattern is not real until it survives a split it wasn't
discovered on).

SHIPPED FINDING (2026-07-11): densest (min k-NN neighbour distance) top-1 hit
68.0% discovery / 69.2% confirm / 70.5% odd / 66.7% even, both sides ~68%,
n=89, p≈0.0007 vs the 51% board base; 2nd-densest placebo 53.9%; max-P 50.0%
on discovery. Sided P again showed no gradient above the bar. Crowded-sector
legs (>=3 same-group confirmations) hit 44%/33% — warning, not yet a gate.
NOTE the density hypothesis was PRE-REGISTERED (day-7 instrumentation) before
this test — this is a confirmation, not a fishing trip. Expect live
performance BELOW these numbers; the ledger's PAIR line is the arbiter.

WALKED BACK (2026-07-15, day-12): re-run after the rolling 60d window moved
by just THREE sessions — densest fell to 52.7% full-period (z=0.21, p=0.42
vs the board base), the placebo beat it on two of four splits, and max-P
swung 50%→68% between odd/even. The day-11 "p≈0.0007" was inflated: legs are
serially correlated (two per day, shared market direction; both directions
often share the same tide) and all four "splits" reused one training window,
so the effective sample was far below n=89. LESSON (now a standing rule): a
selector claim must survive a WINDOW-ROLL re-run, not just in-window splits.
Densest remains the deterministic tie-break; the stated pair expectation is
the qualified-pick base ~52-56%.
"""

import os
import sys
from concurrent.futures import ThreadPoolExecutor
from math import erf, sqrt

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import r945
from adapters import YahooDirectAdapter
from dashboard import load_config

MIN_P = 0.55


def build_dataset(cfg, workers=8):
    a = YahooDirectAdapter(exchange_tz=cfg["exchange_tz"])

    def fetch(t):
        try:
            return t, a._bars_df(a._chart(t, "5m", "60d"))
        except Exception:
            return t, pd.DataFrame()

    with ThreadPoolExecutor(max_workers=workers) as ex:
        fetched = dict(ex.map(fetch, cfg["scan"]["universe"]))
    rows = []
    for t, bars in fetched.items():
        if not bars.empty:
            rows += r945.session_rows(bars, t)
    return pd.DataFrame(rows)


def walk_forward(df, cfg):
    """Per-session qualified boards, trained strictly on the past."""
    groups = cfg.get("peer_groups") or {}
    min_opp = cfg.get("peer_contradiction_min", 3)
    g_of = {t: g for g, ms in groups.items() for t in ms}
    day_log = []
    for d in sorted(df["date"].unique()):
        train = df[df["date"] < d].copy()
        if len(train.dropna(subset=["r0", "gap", "v15", "r1"])) < 200:
            continue
        med = train.groupby("t")["v15"].median()
        train["vp"] = train.apply(
            lambda r: r["v15"] / med[r["t"]] if med.get(r["t"]) else None, axis=1)
        board = []
        for _, row in df[df["date"] == d].iterrows():
            t = row["t"]
            vp = row["v15"] / med[t] if t in med and med[t] else None
            p, n, nd = r945.knn_probability(
                train, {"r0": row["r0"], "gap": row["gap"], "vp": vp})
            if p is None:
                continue
            side = "LONG" if p >= MIN_P else ("SHORT" if 1 - p >= MIN_P else None)
            if side is None:
                continue
            board.append({"date": d, "t": t, "side": side,
                          "sided": p if side == "LONG" else 1 - p, "nd": nd,
                          "r0": row["r0"], "gap": row["gap"], "vp": vp,
                          "r0_aligned": row["r0"] if side == "LONG" else -row["r0"],
                          "hit": int(row["r1"] > 0) if side == "LONG" else int(row["r1"] < 0),
                          "capt": row["r1"] if side == "LONG" else -row["r1"]})
        longs = sorted([b for b in board if b["side"] == "LONG"], key=lambda b: -b["sided"])
        shorts = sorted([b for b in board if b["side"] == "SHORT"], key=lambda b: -b["sided"])
        ln, sn = {}, {}
        for b in longs:
            g = g_of.get(b["t"]);  ln[g] = ln.get(g, 0) + 1 if g else 0
        for b in shorts:
            g = g_of.get(b["t"]);  sn[g] = sn.get(g, 0) + 1 if g else 0
        longs = [b for b in longs if not (g_of.get(b["t"]) and sn.get(g_of[b["t"]], 0) >= min_opp)]
        shorts = [b for b in shorts if not (g_of.get(b["t"]) and ln.get(g_of[b["t"]], 0) >= min_opp)]
        for b in longs:
            g = g_of.get(b["t"]); b["conf"] = (ln.get(g, 0) - 1) if g else 0
        for b in shorts:
            g = g_of.get(b["t"]); b["conf"] = (sn.get(g, 0) - 1) if g else 0
        day_log.append({"date": d, "longs": longs, "shorts": shorts})
    return day_log


def tercile_report(sub, var):
    s = sub.dropna(subset=[var])
    if len(s) < 12:
        return f"    {var:<12} n too small"
    q1, q2 = s[var].quantile([1 / 3, 2 / 3])
    lo, mi, hi = s[s[var] <= q1], s[(s[var] > q1) & (s[var] <= q2)], s[s[var] > q2]
    r = np.corrcoef(s[var], s["hit"])[0, 1] if s[var].std() > 0 else 0.0
    return (f"    {var:<12} lo {lo['hit'].mean()*100:4.0f}% (n={len(lo):>3}) | "
            f"mid {mi['hit'].mean()*100:4.0f}% (n={len(mi):>3}) | "
            f"hi {hi['hit'].mean()*100:4.0f}% (n={len(hi):>3}) | r={r:+.3f}")


RULES = {
    "max_p": lambda pk: max(pk, key=lambda b: b["sided"]),
    "densest": lambda pk: min(pk, key=lambda b: b["nd"]),
    "peer_conf": lambda pk: max(pk, key=lambda b: (b["conf"], b["sided"])),
    "anti_ramp": lambda pk: min(pk, key=lambda b: b["r0_aligned"]),
    "2nd_densest (placebo)": lambda pk: sorted(pk, key=lambda b: b["nd"])[1] if len(pk) > 1 else pk[0],
}


def rule_run(day_log, pred, rule):
    return [rule(dl[side]) for dl in day_log if pred(dl["date"])
            for side in ("longs", "shorts") if dl[side]]


def main():
    cfg = load_config(os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.yaml"))
    df = build_dataset(cfg)
    print(f"dataset: {len(df)} ticker-sessions, {df['t'].nunique()} names")
    day_log = walk_forward(df, cfg)
    days = [dl["date"] for dl in day_log]
    cut = days[int(len(days) * 0.6)]
    P = pd.DataFrame([b for dl in day_log for b in dl["longs"] + dl["shorts"]])
    P["split"] = np.where(P["date"] < cut, "DISCOVERY", "CONFIRM")
    base = P["hit"].mean()
    print(f"walk-forward: {len(days)} sessions, {len(P)} qualified picks, base hit {base*100:.1f}%\n")

    print("A) VARIABLE vs HIT (terciles; r = point-biserial) — needs BOTH splits to count")
    for split in ("DISCOVERY", "CONFIRM"):
        sub = P[P["split"] == split]
        print(f"  {split} (n={len(sub)}, base {sub['hit'].mean()*100:.0f}%)")
        for var in ("sided", "nd", "conf", "r0_aligned", "gap", "vp"):
            print(tercile_report(sub, var))
        print()

    print("B) TOP-1 RULE COMPARISON (one long + one short per session where available)")
    splits = [("DISCOVERY", lambda d: d < cut), ("CONFIRM", lambda d: d >= cut)]
    idx_of = {d: i for i, d in enumerate(days)}
    splits += [("odd", lambda d: idx_of[d] % 2 == 1), ("even", lambda d: idx_of[d] % 2 == 0)]
    for sname, pred in splits:
        print(f"  {sname}")
        for rname, rule in RULES.items():
            res = rule_run(day_log, pred, rule)
            if res:
                print(f"    {rname:<22} n={len(res):>3}  hit {np.mean([b['hit'] for b in res])*100:4.1f}%  "
                      f"avg capture {np.mean([b['capt'] for b in res]):+.3f}%")
        print()

    allr = rule_run(day_log, lambda d: True, RULES["densest"])
    n, h = len(allr), sum(b["hit"] for b in allr)
    z = (h - n * base - 0.5) / sqrt(n * base * (1 - base))
    print(f"C) densest, full period: {h}/{n} = {h/n*100:.1f}% vs board base {base*100:.1f}%  "
          f"z={z:.2f}  one-sided p≈{(1 - 0.5*(1 + erf(z/sqrt(2)))):.4f}")
    for side in ("LONG", "SHORT"):
        s = [b for b in allr if b["side"] == side]
        if s:
            print(f"   {side}: {sum(b['hit'] for b in s)}/{len(s)} = "
                  f"{np.mean([b['hit'] for b in s])*100:.1f}%")
    cr = [b for b in allr if b["conf"] >= 3]
    if cr:
        print(f"   crowded legs (conf>=3): {sum(b['hit'] for b in cr)}/{len(cr)} = "
              f"{np.mean([b['hit'] for b in cr])*100:.0f}% — the printed warning")


if __name__ == "__main__":
    main()
