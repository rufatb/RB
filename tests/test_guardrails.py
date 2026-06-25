"""
test_guardrails.py — the honesty constraints are TESTED, not just hoped for.

WHY these tests exist: the whole value of this tool is that it refuses to
inflate confidence and refuses to read stale data. If a future edit breaks a
guardrail, these tests fail loudly. Do not delete them to make CI green.
"""

import datetime as dt
import sys
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import dashboard
import metrics
import risk
from adapters import ManualAdapter, Quote


# ── Probability clamp [0.35, 0.65] ──────────────────────────────────────────
@pytest.mark.parametrize("raw,expected_lo,expected_hi", [
    (0.99, 0.35, 0.65),
    (0.80, 0.35, 0.65),
    (0.01, 0.35, 0.65),
    (0.50, 0.35, 0.65),
])
def test_probability_is_clamped(raw, expected_lo, expected_hi):
    p = dashboard.clamp_probability(raw)
    assert expected_lo <= p <= expected_hi


def test_probability_cap_is_hard_065():
    assert dashboard.clamp_probability(10.0) == 0.65
    assert dashboard.clamp_probability(-10.0) == 0.35


def test_decision_never_exceeds_cap_even_when_all_bullish():
    # Stack every bullish factor; probability must still respect the cap and
    # conviction must never become "High".
    struct = {"last": 110, "open": 100, "prior_close": 99,
              "pct_vs_open": 10, "pct_vs_prior_close": 11}
    orb = {"pos_in_orb_pct": 100, "orbN_high": 105, "orbN_low": 95}
    vw = {"price_vs_vwap_pct": 5.0, "vwap": 104}
    sf = {"flags": []}
    rel = {"vs_tsx": "outperforming", "vs_peers": "outperforming"}
    momo = {}
    d = dashboard.decide(struct, orb, vw, sf, rel, momo)
    assert d["probability"] <= 0.65
    assert d["conviction"] in ("None", "Low", "Medium")
    assert d["conviction"] != "High"


# ── WAIT defaults ───────────────────────────────────────────────────────────
def test_mid_range_is_no_edge_wait():
    struct = {"last": 100, "open": 100, "prior_close": 100,
              "pct_vs_open": 0, "pct_vs_prior_close": 0}
    orb = {"pos_in_orb_pct": 50, "orbN_high": 105, "orbN_low": 95}
    vw = {"price_vs_vwap_pct": 0.0, "vwap": 100}
    d = dashboard.decide(struct, orb, vw, {"flags": []}, {}, {})
    assert d["verdict"] == "NO EDGE — WAIT"
    assert d["probability"] == 0.50


def test_conflict_collapses_to_wait():
    # above open but below VWAP -> conflict -> WAIT
    struct = {"last": 101, "open": 100, "prior_close": 100}
    orb = {"pos_in_orb_pct": 50, "orbN_high": 105, "orbN_low": 95}
    vw = {"price_vs_vwap_pct": -2.0, "vwap": 103}
    d = dashboard.decide(struct, orb, vw, {"flags": []}, {}, {})
    assert d["verdict"] == "NO EDGE — WAIT"


def test_spike_fade_flag_vetoes_continuation():
    struct = {"last": 104, "open": 100, "prior_close": 100}
    orb = {"pos_in_orb_pct": 90, "orbN_high": 103, "orbN_low": 99}
    vw = {"price_vs_vwap_pct": 1.0, "vwap": 103}
    sf = {"flags": ["FADE WARNING — opening drive >50% retraced"]}
    d = dashboard.decide(struct, orb, vw, sf, {}, {})
    assert d["verdict"] == "NO EDGE — WAIT"
    assert d["probability"] == 0.50


# ── Data integrity guard ────────────────────────────────────────────────────
def _now(tz="America/Toronto"):
    return dt.datetime(2026, 6, 25, 9, 35, tzinfo=ZoneInfo(tz))


def test_guard_fails_on_stale_quote():
    tz = "America/Toronto"
    now = _now(tz)
    stale = Quote(ticker="AC.TO", last=20, open=20, high=21, low=19,
                  prior_close=20, volume=1000, source="yahoo",
                  as_of=now - dt.timedelta(minutes=120),
                  session_date=now.date())
    g = dashboard.data_integrity_guard(
        stale, now=now, exchange_tz=tz,
        market_open=dt.time(9, 30), market_close=dt.time(16, 0),
        max_stale_minutes=20,
    )
    assert not g.passed


def test_guard_fails_on_wrong_session_date():
    tz = "America/Toronto"
    now = _now(tz)
    old = Quote(ticker="AC.TO", last=20, open=20, high=21, low=19,
                prior_close=20, volume=1000, source="yahoo",
                as_of=now, session_date=dt.date(2026, 1, 2))
    g = dashboard.data_integrity_guard(
        old, now=now, exchange_tz=tz,
        market_open=dt.time(9, 30), market_close=dt.time(16, 0),
        max_stale_minutes=20,
    )
    assert not g.passed


def test_guard_fails_on_missing_timestamp():
    tz = "America/Toronto"
    now = _now(tz)
    q = Quote(ticker="AC.TO", last=20, open=20, high=21, low=19,
              prior_close=20, volume=1000, source="yahoo",
              as_of=None, session_date=None)
    g = dashboard.data_integrity_guard(
        q, now=now, exchange_tz=tz,
        market_open=dt.time(9, 30), market_close=dt.time(16, 0),
        max_stale_minutes=20,
    )
    assert not g.passed


def test_manual_bypasses_staleness():
    tz = "America/Toronto"
    now = _now(tz)
    adapter = ManualAdapter(open=20, last=21, high=21.5, low=19.8,
                            volume=50000, prior_close=20, exchange_tz=tz)
    q = adapter.get_quote("AC.TO")
    g = dashboard.data_integrity_guard(
        q, now=now, exchange_tz=tz,
        market_open=dt.time(9, 30), market_close=dt.time(16, 0),
        max_stale_minutes=20,
    )
    assert g.passed
    assert q.source == "manual"


def test_source_conflict_flagged():
    tz = "America/Toronto"
    now = _now(tz)
    a = Quote(ticker="AC.TO", last=20.0, open=20, high=21, low=19,
              prior_close=20, volume=1000, source="yahoo",
              as_of=now, session_date=now.date())
    b = Quote(ticker="AC.TO", last=25.0, open=20, high=21, low=19,
              prior_close=20, volume=1000, source="ibkr",
              as_of=now, session_date=now.date())
    g = dashboard.data_integrity_guard(
        a, now=now, exchange_tz=tz,
        market_open=dt.time(9, 30), market_close=dt.time(16, 0),
        max_stale_minutes=20, second_quote=b, source_conflict_pct=2.0,
    )
    assert not g.passed


# ── No fabricated order flow — proxy must be labelled ───────────────────────
def test_order_flow_is_proxy_only():
    struct = {"last": 21, "open": 20}
    vw = {"vwap": 20.5}
    p = metrics.net_buy_proxy(struct, vw)
    assert "PROXY" in p["_label"].upper()
    assert "order-flow" in p["_label"].lower() or "order flow" in p["_label"].lower()


# ── Risk sizing comes from stop distance, not conviction ────────────────────
def test_position_size_from_stop_distance():
    plan = risk.position_size(account_equity=100000, risk_per_trade_pct=0.5,
                              entry=20.0, stop=19.5, side="long")
    # risk $ = 500; stop distance = 0.5 -> 1000 shares
    assert plan.risk_dollars == 500
    assert plan.shares == 1000


def test_tighter_stop_means_bigger_size():
    wide = risk.position_size(account_equity=100000, risk_per_trade_pct=0.5,
                              entry=20.0, stop=19.0, side="long")
    tight = risk.position_size(account_equity=100000, risk_per_trade_pct=0.5,
                               entry=20.0, stop=19.8, side="long")
    assert tight.shares > wide.shares


def test_margin_cost_zero_for_cash_account():
    plan = risk.position_size(account_equity=100000, risk_per_trade_pct=0.5,
                              entry=20.0, stop=19.5, side="long")
    plan = risk.overnight_margin_cost(plan, is_margin=False, cad_prime=4.45, margin_spread=3.25)
    assert plan.overnight_margin_cost == 0.0


# ── Spike-fade detector ─────────────────────────────────────────────────────
def test_spike_fade_detects_full_retrace():
    # Drive up to 105 from open 100, then back to 100 -> NEUTRALIZED
    idx = pd.date_range("2026-06-25 09:30", periods=10, freq="1min", tz="America/Toronto")
    highs = [101, 103, 105, 104, 103, 102, 101, 100.5, 100.2, 100]
    df = pd.DataFrame({
        "Open": [100] * 10, "High": highs,
        "Low": [99.5] * 10, "Close": highs, "Volume": [1000] * 10,
    }, index=idx)
    sf = metrics.spike_fade(df, open_price=100, window_min=5)
    assert any("NEUTRALIZED" in f or "FADE" in f for f in sf["flags"])
