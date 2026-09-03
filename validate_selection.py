#!/usr/bin/env python3
"""
validate_selection.py — day-82. Does the SELECTION rule earn its place?

Pre-registered in PREREGISTER_day82.md before any result was computed.

THE NATURAL EXPERIMENT THAT WAS ALREADY IN THE LEDGER. `r945.publish` records
every candidate that qualified at the bar, not only the two it traded:

    role="pair"    the legs the density rule SELECTED, and traded
    role="board"   qualified the same day, same universe, same bar, NOT selected

Both are scored against the same 15:59 close. The board rows are therefore a
ready-made counterfactual — "a qualifying name we did not pick" — which makes
this an out-of-sample test of the SELECTION RULE rather than of the model. No
new data was needed; it had been accruing for 38 sessions.

WHY A COST CLAIM AND NOT AN ACCURACY CLAIM. The direction call is measured at
zero. If direction is uninformative among qualifying candidates, then picking
the cheapest one to trade is a strictly positive expected saving that requires
no edge to exist. All three changes ever adopted here were of exactly this
kind.

WHAT THIS CANNOT DO. H2 (the spread saving) is not measurable on the historical
sample, because spreads were never stored until day-82. The snapshot estimate
below assumes the relative ordering of spreads among these names is stable, an
assumption this file does not test. It is labelled an ESTIMATE everywhere and
may not support a rule change — only a decision about whether the prospective
study is worth running.
"""

from __future__ import annotations

import argparse
import os
import sys
from collections import defaultdict

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import ledger as L  # noqa: E402

BOOT = 4000
SEED = 0
COST_BAR_BPS = 2.0          # pre-registered, PREREGISTER_day82.md
ADOPT_T = 3.0               # the standing bar


def scored(rows: list) -> list:
    out = []
    for r in rows:
        c = L.capture(r)
        if c is None:
            continue
        out.append({"date": r["date"], "ticker": r["ticker"],
                    "side": r["side"], "role": r.get("role", ""),
                    "capture": c, "decisive": abs(c) >= L.DECISIVE_PCT})
    return out


def rate(rows: list, decisive_only: bool = True) -> float | None:
    use = [r for r in rows if r["decisive"]] if decisive_only else rows
    if not use:
        return None
    return sum(1 for r in use if r["capture"] > 0) / len(use)


def mean_capture(rows: list) -> float | None:
    return float(np.mean([r["capture"] for r in rows])) if rows else None


def _by_session(rows: list) -> dict:
    d = defaultdict(list)
    for r in rows:
        d[r["date"]].append(r)
    return d


def boot_diff(a: list, b: list, stat, n: int = BOOT, seed: int = SEED) -> tuple:
    """95% interval on stat(a) - stat(b), resampling SESSIONS jointly.

    Legs on one day share that day's market move. Resampling legs would treat
    a session's worth of correlated outcomes as independent draws and shrink
    every interval. The same session is drawn into both arms on a replicate.
    """
    sa, sb = _by_session(a), _by_session(b)
    days = sorted(set(sa) | set(sb))
    if len(days) < 5:
        return (None, None, None)
    rng = np.random.default_rng(seed)
    vals = []
    for _ in range(n):
        pick = rng.integers(0, len(days), size=len(days))
        da = [r for i in pick for r in sa.get(days[i], [])]
        db = [r for i in pick for r in sb.get(days[i], [])]
        x, y = stat(da), stat(db)
        if x is not None and y is not None:
            vals.append(x - y)
    if len(vals) < n // 4:
        return (None, None, None)
    return (float(np.mean(vals)),
            float(np.quantile(vals, 0.025)), float(np.quantile(vals, 0.975)))


def power(a: list, b: list, stat, edge: float, seed: int = SEED) -> float:
    """POSITIVE CONTROL: z for a planted edge of the stated size.

    edge / sd, never (mean + edge) / sd — the day-56 error.
    """
    _, lo, hi = boot_diff(a, b, stat, n=1500, seed=seed + 7)
    if lo is None:
        return float("nan")
    sd = (hi - lo) / (2 * 1.96)
    return edge / sd if sd > 0 else float("inf")


def placebo(all_rows: list, n_a: int, stat, n: int = 400,
            seed: int = SEED) -> tuple:
    """Re-split the same legs at random, WITHIN each session.

    The label must be shuffled the way it is actually assigned. `r945` picks
    the pair from that day's qualifiers, so on every session exactly k legs get
    the "pair" label out of that session's n. A placebo that shuffles across
    the whole pooled sample instead mixes sessions together, destroys the
    within-day structure, and returns an interval that is too narrow — which
    would make an observed difference look more surprising than it is.

    `n_a` is accepted for signature compatibility and deliberately unused: the
    per-session count is taken from the data rather than imposed.
    """
    del n_a
    by = _by_session(all_rows)
    counts = {d: sum(1 for r in rows if r["role"] == "pair")
              for d, rows in by.items()}
    rng = np.random.default_rng(seed + 31)
    vals = []
    for _ in range(n):
        a, b = [], []
        for d, rows in by.items():
            k = counts[d]
            idx = rng.permutation(len(rows))
            a += [rows[i] for i in idx[:k]]
            b += [rows[i] for i in idx[k:]]
        x, y = stat(a), stat(b)
        if x is not None and y is not None:
            vals.append(x - y)
    if not vals:
        return (None, None)
    return (float(np.quantile(vals, 0.025)), float(np.quantile(vals, 0.975)))


def sessions_needed(control_z: float, sessions: int,
                    bar: float = ADOPT_T) -> int | None:
    """How many sessions before the bar is reachable for THIS effect size.

    An underpowered null is only useful if it says when it stops being one.
    SE shrinks as 1/sqrt(n), so z grows as sqrt(n): n_needed = n * (bar/z)^2.
    """
    if not control_z or control_z != control_z or control_z <= 0:
        return None
    return int(round(sessions * (bar / control_z) ** 2))


def h1(rows: list) -> dict:
    """Does density selection beat an arbitrary qualifier? (bound, not a test)"""
    pair = [r for r in rows if r["role"] == "pair"]
    board = [r for r in rows if r["role"] == "board"]
    out = {"n_pair": len(pair), "n_board": len(board),
           "sessions": len({r["date"] for r in rows}),
           "rate_pair": rate(pair), "rate_board": rate(board),
           "mean_pair": mean_capture(pair), "mean_board": mean_capture(board)}
    for name, stat in (("rate", rate), ("mean", mean_capture)):
        m, lo, hi = boot_diff(pair, board, stat)
        out[f"{name}_diff"] = m
        out[f"{name}_ci"] = (lo, hi)
        out[f"{name}_mde"] = (hi - lo) / 2 if lo is not None else None
        out[f"{name}_placebo"] = placebo(rows, len(pair), stat)
    out["control_z_for_10pp"] = power(pair, board, rate, 0.10)
    out["control_z_for_0.25pct"] = power(pair, board, mean_capture, 0.25)
    out["sessions_needed_10pp"] = sessions_needed(out["control_z_for_10pp"],
                                                  out["sessions"])
    return out


def verdict(diff, ci, mde) -> str:
    """ADOPTED / REJECTED / UNDERPOWERED, by the pre-registered rules."""
    if diff is None or ci[0] is None:
        return "NOT COMPUTABLE"
    if ci[0] > 0 or ci[1] < 0:
        return "DISTINGUISHABLE"
    if mde is not None and abs(diff) < mde:
        return f"UNDERPOWERED — cannot resolve below {mde:.4f}"
    return "NOT distinguishable from zero"


def report(h: dict) -> str:
    L_ = ["▎H1 — does DENSITY selection beat an arbitrary qualifier?",
          f"   {h['n_pair']} selected legs vs {h['n_board']} qualified-but-not-"
          f"selected, {h['sessions']} sessions",
          "   bootstrap resamples SESSIONS (legs on one day share its move)",
          ""]
    if h["rate_pair"] is not None and h["rate_board"] is not None:
        L_.append(f"   decisive hit rate   selected {h['rate_pair']*100:.1f}%"
                  f"   not-selected {h['rate_board']*100:.1f}%")
    if h["mean_pair"] is not None:
        L_.append(f"   mean capture/leg    selected {h['mean_pair']:+.3f}%"
                  f"   not-selected {h['mean_board']:+.3f}%")
    L_.append("")
    for label, key in (("hit rate", "rate"), ("mean capture", "mean")):
        d, (lo, hi) = h[f"{key}_diff"], h[f"{key}_ci"]
        if d is None:
            L_.append(f"   {label:<14} not computable")
            continue
        v = verdict(d, (lo, hi), h[f"{key}_mde"])
        unit = "pp" if key == "rate" else "%"
        sc = 100 if key == "rate" else 1
        L_.append(f"   {label:<14} {d*sc:+.2f}{unit}  95% "
                  f"[{lo*sc:+.2f}, {hi*sc:+.2f}]  -> {v}")
        plo, phi = h[f"{key}_placebo"]
        if plo is not None:
            inside = plo <= d <= phi
            L_.append(f"   {'':14} placebo [{plo*sc:+.2f}, {phi*sc:+.2f}] — "
                      f"observed is {'INSIDE' if inside else 'OUTSIDE'} it")
    L_ += ["",
           f"   positive control: a planted 10pp lift registers at "
           f"z={h['control_z_for_10pp']:.1f}; a planted 0.25%/leg lift at "
           f"z={h['control_z_for_0.25pct']:.1f}",
           f"   at this effect size the |t|>={ADOPT_T:.0f} bar becomes "
           f"reachable at ~{h['sessions_needed_10pp']} sessions "
           f"(have {h['sessions']})",
           "   ── rule 10: an interval wider than the effect means the data "
           "cannot answer,",
           "      which is NOT the same as answering no."]
    return "\n".join(L_)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ledger", default=None)
    a = ap.parse_args(argv)
    rows = scored(L.load(a.ledger) if a.ledger else L.load())
    if not rows:
        raise SystemExit("no scored legs in the ledger — nothing to test")
    print(report(h1(rows)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
