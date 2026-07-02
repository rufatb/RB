"""
test_review.py — locks in the full-codebase review changes: calibrated EOD
probability (compress-only shrinkage), config-narrowing-only clamps, analog
smoothing, the position-value cap, target-beyond-trigger levels, config-driven
sector macro, and the report preflight.
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import dashboard
import patterns
import report
import risk
import scan
from adapters import Quote


# ── Calibrated EOD probability ──────────────────────────────────────────────
def test_eod_probability_compresses_toward_half():
    raw = patterns.eod_probability(64.0, shrinkage=1.0)    # inside the clamp band
    half = patterns.eod_probability(64.0, shrinkage=0.5)
    assert raw == 0.64 and half == 0.57
    assert abs(half - 0.5) < abs(raw - 0.5)          # compression happened


def test_eod_probability_never_amplifies():
    # shrinkage > 1 must be coerced down to 1 — never widen a probability
    p = patterns.eod_probability(80.0, shrinkage=5.0)
    assert p == patterns.eod_probability(80.0, shrinkage=1.0)


def test_eod_probability_hard_clamped():
    assert patterns.eod_probability(100.0, shrinkage=1.0) == 0.65
    assert patterns.eod_probability(0.0, shrinkage=1.0) == 0.35
    assert patterns.eod_probability(None) is None


def test_eod_probability_config_cannot_widen():
    # A config asking for cap=0.9 must still be clamped to the hard 0.65
    p = patterns.eod_probability(100.0, shrinkage=1.0, floor=0.05, cap=0.95)
    assert p == 0.65


def test_clamp_probability_config_cannot_widen():
    assert dashboard.clamp_probability(0.99, floor=0.01, cap=0.99) == 0.65
    assert dashboard.clamp_probability(0.01, floor=0.01, cap=0.99) == 0.35
    # …but config CAN narrow
    assert dashboard.clamp_probability(0.64, cap=0.60) == 0.60


# ── Analog smoothing (accuracy fix for small-sample overconfidence) ─────────
def _daily(n=400, seed=3):
    rng = np.random.default_rng(seed)
    idx = pd.bdate_range("2024-01-01", periods=n)
    close = 20 + np.cumsum(rng.normal(0, 0.3, n))
    open_ = close + rng.normal(0, 0.2, n)
    hi = np.maximum(close, open_) + abs(rng.normal(0, 0.2, n))
    lo = np.minimum(close, open_) - abs(rng.normal(0, 0.2, n))
    return pd.DataFrame({"Open": open_, "High": hi, "Low": lo, "Close": close,
                         "Volume": rng.integers(1e6, 5e6, n)}, index=idx)


def test_smoothing_pulls_green_toward_50():
    d = _daily()
    smoothed = patterns.analog_days(d, today_gap_pct=0.4, today_prev_oc_pct=0.1,
                                    today_pos_in_range_pct=50.0, smoothing_m=10)
    raw = smoothed["green_rate_raw_pct"]
    assert abs(smoothed["green_rate_pct"] - 50) <= abs(raw - 50) + 1e-9
    assert smoothed["smoothing_m"] == 10


# ── Position cap (the $102k-position-on-$100k-equity bug) ───────────────────
def test_position_value_capped():
    plan = risk.position_size(account_equity=100_000, risk_per_trade_pct=0.5,
                              entry=24.62, stop=24.50, max_position_pct=50)
    assert plan.position_value <= 50_000 + 25   # ≤ cap (one share of slack)
    assert any("capped" in n for n in plan.notes)


def test_position_uncapped_when_within_limit():
    plan = risk.position_size(account_equity=100_000, risk_per_trade_pct=0.5,
                              entry=20.0, stop=19.0, max_position_pct=50)
    assert plan.shares == 500 and not plan.notes


# ── Levels: target must sit beyond the trigger (0.00R bug) ──────────────────
def test_bull_target_never_equals_trigger():
    struct = {"open": 24.51}
    orb = {"orbN_high": 24.95, "orbN_low": 24.50}
    levels = {"resistance": [24.95], "demand_shelves": [], "prior_high": 24.95,
              "prior_low": 24.0, "high_52w": 26.0, "low_52w": 16.0}
    lv = dashboard.build_levels(struct, orb, levels)
    assert lv["bull_target"] != 24.95            # the old bug returned the trigger
    assert lv["bull_target"] == 26.0             # falls through to a real level
    assert lv["bull_trigger_level"] == 24.95


def test_bear_target_beyond_trigger():
    struct = {"open": 24.51}
    orb = {"orbN_high": 24.95, "orbN_low": 24.50}
    levels = {"resistance": [], "demand_shelves": [24.50], "prior_high": None,
              "prior_low": 24.49, "high_52w": None, "low_52w": 16.45}
    lv = dashboard.build_levels(struct, orb, levels)
    assert lv["bear_target"] == 16.45            # 24.50/24.49 are inside 0.3% — skip


# ── Config-driven sector macro (no hardcoding) ──────────────────────────────
def test_macro_dir_config_override():
    sectors = {"crude_beneficiaries": ["XYZ.TO"], "crude_victims": ["QRS.TO"]}
    assert scan.macro_dir_for("XYZ.TO", +2.0, sectors) == 1
    assert scan.macro_dir_for("QRS.TO", +2.0, sectors) == -1
    assert scan.macro_dir_for("AC.TO", +2.0, sectors) is None  # not in override


def test_score_candidate_config_thresholds():
    c = {"ticker": "X", "passed": True, "verdict": "NO EDGE — WAIT",
         "analog_green": 57.0, "off_sample": False, "macro_dir": 0,
         "sentiment_dir": 0, "probability": 0.5}
    # default 55 threshold -> long
    assert scan.score_candidate(c)["direction"] == 1
    # stricter config -> neutral
    cfg = {"analogs": {"long_threshold": 60, "short_threshold": 40}}
    assert scan.score_candidate(c, cfg)["tier"] == "skip"


# ── Report preflight (mocked adapter — no network) ──────────────────────────
class _FakeAdapter:
    def __init__(self, last):
        self._last = last

    def get_quote(self, t):
        import datetime as dt
        from zoneinfo import ZoneInfo
        now = dt.datetime.now(ZoneInfo("America/Toronto"))
        return Quote(ticker=t, last=self._last, open=self._last, high=self._last,
                     low=self._last, prior_close=self._last, volume=1,
                     source="fake", as_of=now, session_date=now.date())


def test_preflight_reports_primary_ok(monkeypatch):
    monkeypatch.setattr(report, "build_adapter", lambda *a, **k: _FakeAdapter(24.5))
    cfg = {"exchange_tz": "America/Toronto", "ticker": "AC.TO",
           "data_sources": {"primary": "yahoo_direct", "cross_check": []}}
    pf = report.preflight(cfg)
    assert pf["primary_ok"] is True
    assert any(name.startswith("primary") and ok for name, ok, _ in pf["checks"])


def test_preflight_flags_dead_primary(monkeypatch):
    monkeypatch.setattr(report, "build_adapter", lambda *a, **k: _FakeAdapter(None))
    cfg = {"exchange_tz": "America/Toronto", "ticker": "AC.TO",
           "data_sources": {"primary": "yahoo_direct", "cross_check": []}}
    pf = report.preflight(cfg)
    assert pf["primary_ok"] is False
