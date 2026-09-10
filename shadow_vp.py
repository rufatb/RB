#!/usr/bin/env python3
"""Day-95 H1 SHADOW A/B — the vp train/serve skew, measured not fixed.

PREREGISTER_day95b.md: the k-NN compares today's trailing-normalized `vp`
against a training frame normalized by the FULL-WINDOW median, so distances on
the vp axis are systematically shifted. Free data cannot evaluate the fix
(day-93: 21 usable 5-minute sessions; the hourly pool has no vp), so the
registered remedy is a SHADOW: both variants are computed daily, the picks are
logged side by side, and the deliverable is a measured pick-divergence rate —
NOTHING more. No accuracy claim until a paid 5-minute history exists.

SHADOW ONLY. Nothing here feeds selection, sizing, gating or the report's
claims. Every entry point is fail-closed: a shadow error is recorded in the
result dict and must never propagate into the real run (house rule 1 applies
to the real pipeline; the shadow absorbs its own failures BY DESIGN so it can
never become a fifth way to break 09:46).
"""
from __future__ import annotations

import json
import os
from pathlib import Path

import numpy as np
import pandas as pd

ARTIFACT = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                        "data", "shadow_vp.jsonl")

# Trailing variant warm-up, matching validate_ceiling.add_vp: a row's median
# needs enough PRIOR sessions to be a "normal" at all; warm-up rows are NaN
# and drop out of the k-NN (counted, never silently constant-filled).
TRAILING_MIN_PERIODS = 20


def train_variants(hist_rows: list) -> tuple:
    """(shipped, trailing) training frames differing ONLY in vp normalization.

    shipped:  vp = v15 / full-window per-ticker median — what r945.run does.
              A historical row's normalizer includes sessions AFTER it.
    trailing: vp = v15 / expanding median of the same ticker's PRIOR sessions
              — what the live row's own normalization actually is.
    """
    base = pd.DataFrame(hist_rows)
    if base.empty or "v15" not in base.columns:
        raise ValueError("no training rows with v15 to normalize")
    shipped = base.copy()
    shipped["vp"] = shipped.groupby("t")["v15"].transform(
        lambda s: s / (s.median() or 1))
    trailing = base.sort_values(["t", "date"]).copy()
    med = (trailing.groupby("t")["v15"]
           .apply(lambda s: s.shift(1).expanding(min_periods=TRAILING_MIN_PERIODS).median())
           .reset_index(level=0, drop=True))
    trailing["vp"] = trailing["v15"] / med.replace(0, np.nan)
    return shipped, trailing


def _board(frame: pd.DataFrame, live_rows: list, min_p: float,
           groups, selector: str, legs_per_side: int) -> dict:
    """Re-run the shipped selection arithmetic against one vp normalization.

    Reuses r945.knn_probability / peer_gate / pair_of_day verbatim so the
    comparison isolates the normalization and nothing else."""
    import r945
    scored = []
    for r in live_rows:
        p, _n, nd = r945.knn_probability(frame, r)
        if p is None:
            continue
        scored.append({**r, "p_up": p, "nd": nd})
    longs = sorted([r for r in scored if r["p_up"] >= min_p], key=lambda r: -r["p_up"])
    shorts = sorted([r for r in scored if 1 - r["p_up"] >= min_p], key=lambda r: r["p_up"])
    longs, shorts, _excluded = r945.peer_gate(longs, shorts, groups)
    pair = r945.pair_of_day(longs, shorts, groups, selector,
                            legs_per_side=legs_per_side)
    return {"n_scored": len(scored),
            "qualified_longs": [r["t"] for r in longs],
            "qualified_shorts": [r["t"] for r in shorts],
            "pair": {side: ((pair.get(side) or {}).get("pick") or {}).get("t")
                     for side in ("long", "short")}}


def compare(hist_rows: list, live_rows: list, min_p: float = 0.55,
            groups: dict | None = None, selector: str = "densest",
            legs_per_side: int = 2) -> dict:
    """Whether today's pair picks would DIVERGE under the two vp variants.

    Returns a JSON-serializable dict; {'status': 'OK', 'diverged': bool, ...}.
    Never raises into the caller's trading path — a malformed input produces
    {'status': 'ERROR', 'error': ...} so the publish step can record it."""
    try:
        shipped, trailing = train_variants(hist_rows)
        a = _board(shipped, live_rows, min_p, groups, selector, legs_per_side)
        b = _board(trailing, live_rows, min_p, groups, selector, legs_per_side)
        return {"status": "OK",
                "variant_a": "full-window median train normalization (shipped)",
                "variant_b": "trailing-only expanding median train normalization",
                "board_a": a, "board_b": b,
                "diverged": (a["pair"] != b["pair"]
                             or a["qualified_longs"] != b["qualified_longs"]
                             or a["qualified_shorts"] != b["qualified_shorts"]),
                "claim": "pick-divergence measurement only; NOT an accuracy result"}
    except Exception as exc:  # shadow absorbs its own failures BY DESIGN
        return {"status": "ERROR", "error": type(exc).__name__,
                "detail": str(exc)[:200]}


def log(entry: dict, date: str, path: str = ARTIFACT) -> bool:
    """Append one JSONL shadow row per session. Publish-once, like the record.

    Returns True when a row was written, False when the session is already
    logged (a rerun never rewrites or duplicates the shadow record)."""
    sessions = set()
    if os.path.exists(path):
        with open(path) as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    sessions.add(json.loads(line).get("session"))
                except json.JSONDecodeError:
                    # A corrupt line is evidence, not silence: keep it, count it.
                    sessions.add("<corrupt line retained>")
    if date in sessions:
        return False
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a") as fh:
        fh.write(json.dumps({"session": date, **entry},
                            sort_keys=True, allow_nan=False) + "\n")
    return True
