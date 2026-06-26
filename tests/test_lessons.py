"""
test_lessons.py — locks in the discipline rules learned from live trading
(see STRATEGY.md): off-sample detection, EOD lens-alignment, and scan
persistence. These are the guards that would have blocked the SHOP/CVE losses.
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import metrics
import patterns
import scan


def _synthetic_daily(n=400, seed=5):
    rng = np.random.default_rng(seed)
    idx = pd.bdate_range("2024-01-01", periods=n)
    close = 30 + np.cumsum(rng.normal(0, 0.3, n))
    open_ = close + rng.normal(0, 0.2, n)
    hi = np.maximum(close, open_) + abs(rng.normal(0, 0.2, n))
    lo = np.minimum(close, open_) - abs(rng.normal(0, 0.2, n))
    return pd.DataFrame({"Open": open_, "High": hi, "Low": lo, "Close": close,
                         "Volume": rng.integers(1e6, 5e6, n)}, index=idx)


# ── Off-sample detection ────────────────────────────────────────────────────
def test_off_sample_flagged_for_extreme_gap():
    daily = _synthetic_daily()
    # A wildly large gap that no historical day matches -> off-sample.
    a = patterns.analog_days(daily, today_gap_pct=50.0, today_prev_oc_pct=0.0,
                             today_pos_in_range_pct=50.0)
    assert a["available"]
    assert a["off_sample"] is True
    assert "gap_pct" in a["off_sample_reason"]


def test_in_sample_not_flagged():
    daily = _synthetic_daily()
    a = patterns.analog_days(daily, today_gap_pct=0.1, today_prev_oc_pct=0.0,
                             today_pos_in_range_pct=50.0)
    assert a["available"] and a["off_sample"] is False


# ── EOD alignment (the SHOP/CVE conflict gate) ──────────────────────────────
def test_alignment_conflicted_when_structure_fights_baserate():
    # Intraday says LONG (BULL LEAN) but base rate says DOWN (green 24%) -> CVE case
    al = metrics.eod_alignment("BULL LEAN", analog_green_pct=24.0)
    assert al["alignment"] == "conflicted"


def test_alignment_aligned_long():
    al = metrics.eod_alignment("BULL LEAN", analog_green_pct=70.0)
    assert al["alignment"] == "aligned-long"


def test_alignment_aligned_short():
    al = metrics.eod_alignment("BEAR LEAN", analog_green_pct=30.0)
    assert al["alignment"] == "aligned-short"


def test_alignment_off_sample_downgrade():
    al = metrics.eod_alignment("BULL LEAN", analog_green_pct=70.0, off_sample=True)
    assert al["alignment"] == "aligned-but-off-sample"


def test_alignment_neutral_when_no_lens():
    al = metrics.eod_alignment("NO EDGE — WAIT", analog_green_pct=50.0)
    assert al["alignment"] == "neutral"


def test_alignment_macro_can_conflict():
    # structure + base rate long, but macro bearish -> conflicted
    al = metrics.eod_alignment("BULL LEAN", analog_green_pct=70.0, macro_dir=-1)
    assert al["alignment"] == "conflicted"


# ── Scan persistence (the snapshot-chasing fix) ─────────────────────────────
def test_persistence_increments_on_repeat():
    today = "2026-06-26"
    results = [{"ticker": "RY.TO", "verdict": "BEAR LEAN"}]
    _, st1 = scan.apply_persistence(results, {}, today)
    assert st1["RY.TO"]["streak"] == 1
    # same verdict next scan -> streak 2
    results = [{"ticker": "RY.TO", "verdict": "BEAR LEAN"}]
    res2, st2 = scan.apply_persistence(results, st1, today)
    assert res2[0]["streak"] == 2 and st2["RY.TO"]["streak"] == 2


def test_persistence_resets_on_verdict_change():
    today = "2026-06-26"
    prev = {"RY.TO": {"date": today, "verdict": "BEAR LEAN", "streak": 3}}
    results = [{"ticker": "RY.TO", "verdict": "BULL LEAN"}]  # flipped
    res, _ = scan.apply_persistence(results, prev, today)
    assert res[0]["streak"] == 1  # rotation kills the streak


def test_persistence_resets_on_new_day():
    prev = {"RY.TO": {"date": "2026-06-25", "verdict": "BEAR LEAN", "streak": 5}}
    results = [{"ticker": "RY.TO", "verdict": "BEAR LEAN"}]
    res, _ = scan.apply_persistence(results, prev, "2026-06-26")
    assert res[0]["streak"] == 1  # yesterday's streak doesn't carry over
