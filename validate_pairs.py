#!/usr/bin/env python3
"""validate_pairs.py — day-96. The registered test of intraday pairs.

Evaluates the six cells in PREREGISTER_day96.md (2 formation methods x 3 entry
thresholds), placebo-max over the pair grid, session-clustered block bootstrap,
four chronological quarters, holdout replication, liquidity-quartile size test,
MDE always, planted-edge control measured as edge/sd.

Read AUDIT_day96_preflight.md for deviations and interpretation limits.
Replication must test the development-selected cell, not a new holdout winner.

THE STATISTIC IS NOT "IS THE BEST PAIR PROFITABLE". Of course the best of
166,753 candidates looks profitable -- that is what "best of" means. The
statistic is whether the best REAL cell beats the 95th percentile of the best
PLACEBO cell, where the placebo keeps the real pair selection and the real
z-score timing and only changes whose returns the legs earn.

Read-only research. Nothing here places, sizes or cancels an order.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time

import numpy as np

import pairs as P

PLACEBO_DRAWS = 500        # replicates of the best-cell distribution


def cells() -> list:
    return [(m, th) for m in P.METHODS for th in P.THRESHOLDS]


def liquidity_quartiles(wide: dict) -> np.ndarray:
    """Per-name liquidity rank, from median dollar volume over the panel.

    Day-86: an effect concentrated in the smallest quartile is concentrated
    exactly where survivorship removed the names, and `SIZE_RATIO_MAX = 2.0`
    is the ratio criterion that catches it. The sign-based test this replaced
    passed a 25x concentration for 54 days.
    """
    dv = wide["close"] * wide["volume"]
    med = np.nanmedian(dv, axis=0)
    order = np.argsort(np.argsort(med))
    return (order * 4 // max(len(med), 1)).astype(int)


def summarise(trades: list, label: str) -> dict:
    b = P.session_block_bootstrap(trades)
    gross = float(np.mean([t["gross"] for t in trades])) if trades else None
    hits = sum(1 for t in trades if t["net"] > 0)
    return {"cell": label, "n": b["n"], "sessions": b["sessions"],
            "gross": gross, "net": b["mean"], "lo": b["lo"], "hi": b["hi"],
            "se": b["se"], "t": b["t"],
            "mde": P.mde(b["se"]) if b["se"] else None,
            "mde80": (P.ADOPT_T + 0.8416212335729143) * b["se"] if b["se"] else None,
            "hit_rate": (hits / len(trades)) if trades else None}


def run(panel: str, draws: int = PLACEBO_DRAWS, seed: int = P.SEED,
        verbose: bool = True) -> dict:
    t0 = time.time()
    wide = P.load_wide(panel)
    intra = wide["intraday"]
    N = len(wide["tickers"])
    if verbose:
        print(f"panel {os.path.basename(panel)}: {N} names, "
              f"{len(wide['dates'])} sessions, "
              f"{wide['dropped_incomplete']} dropped for incomplete history",
              flush=True)

    # ── one expensive signal pass per cell, reused by every placebo draw ────
    signals, real = {}, {}
    for m, th in cells():
        key = f"{m}@{th}"
        signals[key] = P.generate_signals(wide, m, th)
        real[key] = summarise(P.attribute(signals[key], intra), key)
        if verbose:
            r = real[key]
            print(f"  {key:22s} n={r['n']:6d}  gross={r['gross']:+.4f}%  "
                  f"net={r['net']:+.4f}%  t={r['t'] or float('nan'):+.2f}",
                  flush=True)

    best_key = max(real, key=lambda k: real[k]["net"]
                   if real[k]["net"] is not None else -np.inf)
    best = real[best_key]

    # ── placebo-max over the SAME grid ─────────────────────────────────────
    rng = np.random.default_rng(seed)
    placebo_best, placebo_all = [], {k: [] for k in real}
    for d in range(draws):
        perm = rng.permutation(N)
        cell_means = []
        for key, sig in signals.items():
            tr = P.attribute(sig, intra, permute=perm)
            m = float(np.mean([x["net"] for x in tr])) if tr else -9e9
            cell_means.append(m)
            placebo_all[key].append(m)
        placebo_best.append(max(cell_means))
        if verbose and (d + 1) % 100 == 0:
            print(f"    placebo {d + 1}/{draws}", flush=True)

    pb = np.array(placebo_best, dtype=float)
    p95 = float(np.percentile(pb, 95))
    observed = best["net"] if best["net"] is not None else -np.inf
    p_value = float((1 + (pb >= observed).sum()) / (len(pb) + 1))

    # ── the rest of the registered bars ────────────────────────────────────
    best_trades = P.attribute(signals[best_key], intra)
    qs = P.quarters(best_trades)
    control = P.planted_control(best_trades)

    quart = liquidity_quartiles(wide)
    by_q = {}
    for q in range(4):
        sel = [t for t in best_trades
               if quart[t["i"]] == q and quart[t["j"]] == q]
        by_q[q] = {"n": len(sel),
                   "net": float(np.mean([t["net"] for t in sel])) if sel else None}
    finite = [v["net"] for v in by_q.values() if v["net"] is not None]
    if len(finite) >= 2 and min(abs(x) for x in finite) > 0:
        size_ratio = max(abs(x) for x in finite) / min(abs(x) for x in finite)
    else:
        size_ratio = None

    return {"panel": os.path.basename(panel), "names": N,
            "sample": {"tickers": wide["tickers"].tolist(),
                       "first_date": str(wide["dates"][0]),
                       "last_date": str(wide["dates"][-1])},
            "sessions": len(wide["dates"]),
            "dropped_incomplete": wide["dropped_incomplete"],
            "cells": real, "best_cell": best_key, "best": best,
            "placebo": {"draws": draws, "p95": p95,
                        "mean": float(pb.mean()), "max": float(pb.max()),
                        "p_value": p_value,
                        "per_cell_mean": {k: float(np.mean(v))
                                          for k, v in placebo_all.items()}},
            "quarters": qs, "control": control,
            "size_by_quartile": by_q, "size_ratio": size_ratio,
            "elapsed_sec": round(time.time() - t0, 1)}


# ── verdict ────────────────────────────────────────────────────────────────

def assess_replication(development: dict, holdout: dict) -> dict:
    """Freeze the selected cell and require disjoint issuer/date observations.

    Disjoint observations are necessary, not proof of independent market
    shocks. Unknown sample provenance cannot certify a holdout. These checks
    apply to future runs; original published study artifacts remain intact.
    """
    key = development["best_cell"]
    cell = holdout.get("cells", {}).get(key) or {}
    net, t = cell.get("net"), cell.get("t")
    p95 = holdout.get("placebo", {}).get("p95")
    selected_passes = bool(net is not None and t is not None and p95 is not None
                           and np.isfinite([net, t, p95]).all()
                           and net > 0 and net > p95 and t >= P.ADOPT_T)
    a, b = development.get("sample", {}), holdout.get("sample", {})
    fields = ("tickers", "first_date", "last_date")
    known = all(a.get(k) and b.get(k) for k in fields)
    shared = sorted(set(a.get("tickers", [])) & set(b.get("tickers", [])))
    overlap = (max(a["first_date"], b["first_date"]) <=
               min(a["last_date"], b["last_date"])) if known else None
    disjoint = bool(known and not (shared and overlap))
    return {"selected_cell": key, "selected_cell_passes": selected_passes,
            "sample_provenance_known": bool(known),
            "shared_issuers": len(shared), "date_ranges_overlap": overlap,
            "disjoint_observations": disjoint,
            "replicates": selected_passes and disjoint}

def verdict(res: dict) -> dict:
    """The five registered bars. Any failure is a rejection; the bars were
    fixed at cac0666 and do not move."""
    b = res["best"]
    checks = {}
    checks["placebo_max"] = bool(b["net"] is not None
                                 and b["net"] > res["placebo"]["p95"])
    checks["t_ge_3"] = bool(b["t"] is not None and abs(b["t"]) >= P.ADOPT_T
                            and b["net"] > 0)
    qs = [q for q in res["quarters"] if q is not None]
    checks["four_quarters"] = bool(len(qs) == P.BLOCKS
                                   and all(q > 0 for q in qs))
    checks["size_ratio"] = bool(res["size_ratio"] is not None
                                and res["size_ratio"] <= P.SIZE_RATIO_MAX)
    checks["holdout"] = res.get("holdout_replicates")
    passed = all(v is True for v in checks.values())
    return {"checks": checks, "adopt": passed}


def report(res: dict, hold: dict | None = None) -> str:
    L = []
    A = L.append
    A("DAY-96 — INTRADAY RELATIVE-VALUE PAIRS")
    A("Pre-registered PREREGISTER_day96.md @ cac0666, before any outcome.")
    A("DAILY-BAR PROXY: entry is the OPEN, not 09:46. Nothing here certifies")
    A("the 09:46->15:59 contract.")
    A("Open-derived signals assume same-open fills: an idealized proxy, not an executable entry.")
    A("Returns and 10bp costs use ONE LEG'S notional; divide both by two for gross-book returns.")
    A("The fixed-signal return-reassignment placebo is conditional, not a full selection re-fit.")
    A("")
    A(f"panel {res['panel']}: {res['names']} names, {res['sessions']} sessions")
    A(f"  {res['dropped_incomplete']} names dropped for incomplete history —")
    A("  requiring 10 full years SELECTS SURVIVORS, so the survivorship")
    A("  problem below is if anything understated.")
    A("")
    A("THE SIX REGISTERED CELLS (net of 10bp round trip, cost subtracted not clipped)")
    A(f"  {'cell':24s}{'n':>7}{'gross%':>10}{'net%':>10}{'t':>8}{'hit':>8}")
    for k, c in res["cells"].items():
        A(f"  {k:24s}{c['n']:>7}{c['gross']:>10.4f}{c['net']:>10.4f}"
          f"{(c['t'] or 0):>8.2f}{(c['hit_rate'] or 0) * 100:>7.1f}%")
    A("")
    b, pl = res["best"], res["placebo"]
    A(f"BEST REAL CELL: {res['best_cell']}  net={b['net']:+.4f}%/trade")
    A("")
    A("PLACEBO-MAX OVER THE PAIR GRID — the comparison that matters")
    A("  Real pair selection, real z-score timing; only WHOSE returns the legs")
    A("  earn is permuted. The best of six cells is taken on EVERY draw, so")
    A("  the distribution already contains the advantage of picking a winner.")
    A(f"  placebo best-cell mean   {pl['mean']:+.4f}%")
    A(f"  placebo best-cell p95    {pl['p95']:+.4f}%   <- the bar")
    A(f"  placebo best-cell max    {pl['max']:+.4f}%")
    A(f"  real best cell           {b['net']:+.4f}%")
    A(f"  p-value vs placebo-max   {pl['p_value']:.3f}  ({pl['draws']} draws)")
    A("")
    A("POWER (rule 10 — a null without this is an unlabelled UNDERPOWERED)")
    A(f"  SE {b['se']:.4f}%   MDE at |t|>=3.0: {b['mde']:.4f}%/trade")
    if b.get("mde80") is not None:
        A(f"  Approximate MDE at 80% power: {b['mde80']:.4f}% on one-leg notional")
    A("  The planted-return diagnostic measures SE sensitivity, not end-to-end strategy detection.")
    c = res["control"]
    A(f"  planted +{c['edge']:.2f}%/trade control: t={c['t']:.2f} "
      f"{'DETECTED' if c['detected'] else 'NOT DETECTED — harness underpowered'}")
    A("    (measured as edge/sd, never (mean+edge)/sd)")
    A("")
    A("FOUR CHRONOLOGICAL QUARTERS (net%/trade)")
    A("  " + "  ".join(f"Q{i + 1} {q:+.4f}" for i, q in
                       enumerate(res["quarters"]) if q is not None))
    A("")
    A("LIQUIDITY QUARTILE (survivorship's fingerprint — day-86)")
    for q, v in res["size_by_quartile"].items():
        net = f"{v['net']:+.4f}%" if v["net"] is not None else "n/a"
        A(f"  Q{q} (smallest first)  n={v['n']:5d}  net={net}")
    sr = res["size_ratio"]
    A(f"  ratio max/min = {sr:.2f}" if sr is not None
      else "  ratio NOT COMPUTABLE — a data limit, not a finding")
    A(f"  bar: <= {P.SIZE_RATIO_MAX}")
    if hold:
        A("")
        A(f"HOLDOUT {hold['panel']}: {hold['names']} names")
        hb = hold["best"]
        A(f"  same cell {res['best_cell']}: "
          f"net={hold['cells'][res['best_cell']]['net']:+.4f}%")
        A(f"  its own best {hold['best_cell']}: net={hb['net']:+.4f}%  "
          f"vs placebo p95 {hold['placebo']['p95']:+.4f}%")
    A("")
    v = verdict(res)
    A("THE FIVE REGISTERED BARS")
    for k, ok in v["checks"].items():
        mark = "PASS" if ok is True else ("FAIL" if ok is False else "n/a")
        A(f"  {k:16s} {mark}")
    A("")
    A("VERDICT: " + ("ADOPT (shadow only — see registration)" if v["adopt"]
                     else "REJECTED"))
    return "\n".join(L)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--panel", default=os.path.join(P.DATA, "us_daily.csv"))
    ap.add_argument("--holdout", default=os.path.join(P.DATA,
                                                      "us_daily_holdout.csv"))
    ap.add_argument("--draws", type=int, default=PLACEBO_DRAWS)
    ap.add_argument("--no-holdout", action="store_true")
    ap.add_argument("--json")
    a = ap.parse_args(argv)

    res = run(a.panel, draws=a.draws)
    hold = None
    if not a.no_holdout and os.path.exists(a.holdout):
        print("\n--- holdout ---", flush=True)
        hold = run(a.holdout, draws=max(a.draws // 5, 50))
        res["replication"] = assess_replication(res, hold)
        res["holdout_replicates"] = res["replication"]["replicates"]
    print("\n" + report(res, hold))
    if a.json:
        with open(a.json, "w") as f:
            json.dump({"development": res, "holdout": hold}, f, indent=2)
    return 0 if verdict(res)["adopt"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
