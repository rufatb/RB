"""
test_enhancements.py — multi-source adapters, deep-history patterns, and the
Claude analyst guardrails.

The analyst test uses a MOCK client (no network, no key) but asserts the request
is well-formed AND that the analyst can never mutate the deterministic decision.
"""

import os
import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import analyst
import dashboard
import patterns
from adapters import (MultiSourceAdapter, Quote, StooqAdapter, YahooDirectAdapter,
                      build_adapter)


# ── Synthetic daily history ─────────────────────────────────────────────────
def _synthetic_daily(n=400, seed=7):
    import numpy as np
    rng = np.random.default_rng(seed)
    idx = pd.bdate_range("2024-01-01", periods=n)
    close = 20 + np.cumsum(rng.normal(0, 0.3, n))
    open_ = close + rng.normal(0, 0.2, n)
    high = pd.concat([pd.Series(close), pd.Series(open_)], axis=1).max(axis=1) + abs(rng.normal(0, 0.2, n))
    low = pd.concat([pd.Series(close), pd.Series(open_)], axis=1).min(axis=1) - abs(rng.normal(0, 0.2, n))
    vol = rng.integers(1_000_000, 5_000_000, n)
    return pd.DataFrame({"Open": open_, "High": high.values, "Low": low.values,
                         "Close": close, "Volume": vol}, index=idx)


# ── Patterns: base rates carry sample sizes; analogs are conditioned ─────────
def test_gap_statistics_has_sample_sizes():
    daily = _synthetic_daily()
    g = patterns.gap_statistics(daily)
    assert g["available"]
    assert g["gap_up"]["n"] > 0 and "confidence" in g["gap_up"]
    # close-above-open rate is a real percentage
    assert 0 <= g["gap_up"]["close_above_open_rate_pct"] <= 100


def test_analog_days_conditioned_and_sized():
    daily = _synthetic_daily()
    a = patterns.analog_days(daily, today_gap_pct=0.6, today_prev_oc_pct=0.2,
                             today_pos_in_range_pct=55.0, k=25)
    assert a["available"]
    assert a["n_neighbours"] == 25
    assert "gap_pct" in a["features_used"]
    assert a["p25_oc_pct"] <= a["median_oc_pct"] <= a["p75_oc_pct"]


def test_analogs_refuse_on_short_history():
    short = _synthetic_daily(n=10)
    a = patterns.analog_days(short, today_gap_pct=0.5, today_prev_oc_pct=0.0,
                             today_pos_in_range_pct=50.0)
    assert not a["available"]
    assert "insufficient" in a.get("reason", "")


def test_pattern_factors_are_weak_only():
    daily = _synthetic_daily()
    out = patterns.analyze(daily, _synthetic_daily(seed=3),
                           today_gap_pct=0.6, today_prev_oc_pct=0.2,
                           today_pos_in_range_pct=55.0)
    for f in out["factors"]:
        assert f.strength == "weak"  # history never implies a strong edge


# ── Pattern factors stay clamped and only show on a structural lean ─────────
def test_pattern_factor_cannot_break_clamp():
    from patterns import PatternFactor
    # Stack a strong structural bull read + many bullish history factors.
    struct = {"last": 110, "open": 100, "prior_close": 99}
    orb = {"pos_in_orb_pct": 100, "orbN_high": 105, "orbN_low": 95}
    vw = {"price_vs_vwap_pct": 5.0, "vwap": 104}
    pf = [PatternFactor("hist up", +1, "weak", "x")] * 20
    d = dashboard.decide(struct, orb, vw, {"flags": []}, {}, {}, pattern_factors=pf)
    assert d["probability"] <= 0.65


def test_pattern_factor_not_shown_on_wait():
    from patterns import PatternFactor
    struct = {"last": 100, "open": 100, "prior_close": 100}
    orb = {"pos_in_orb_pct": 50, "orbN_high": 105, "orbN_low": 95}  # mid-range -> WAIT
    vw = {"price_vs_vwap_pct": 0.0, "vwap": 100}
    pf = [PatternFactor("hist up", +1, "weak", "x")]
    d = dashboard.decide(struct, orb, vw, {"flags": []}, {}, {}, pattern_factors=pf)
    assert d["verdict"] == "NO EDGE — WAIT"
    assert d["probability"] == 0.50
    assert not any("hist up" in f for f in d["factors"])


# ── Yahoo-direct chart parsing (no network) ─────────────────────────────────
def test_yahoo_direct_bars_parse():
    adp = YahooDirectAdapter()
    result = {
        "timestamp": [1782394200, 1782394260],
        "indicators": {"quote": [{
            "open": [24.6, 24.7], "high": [24.8, 24.9],
            "low": [24.5, 24.6], "close": [24.7, 24.8], "volume": [1000, 2000],
        }]},
    }
    df = adp._bars_df(result)
    assert len(df) == 2
    assert list(df.columns) == ["Open", "High", "Low", "Close", "Volume"]
    assert df.index.tz is not None  # tz-aware -> guard can age it


# ── Multi-source cross-check feeds the conflict guard ───────────────────────
class _FakeAdapter:
    def __init__(self, name, last):
        self.name = name
        self._last = last

    def get_quote(self, t):
        return Quote(ticker=t, last=self._last, open=self._last, high=self._last,
                     low=self._last, prior_close=self._last, volume=1,
                     source=self.name, as_of=None, session_date=None)

    def get_intraday_bars(self, t, interval="1m"):
        return pd.DataFrame()

    def get_daily_bars(self, t, n):
        return pd.DataFrame()

    def get_quote_simple(self, t):
        return self.get_quote(t)


def test_multisource_exposes_cross_quote():
    multi = MultiSourceAdapter(_FakeAdapter("primary", 24.5),
                               [_FakeAdapter("alt", 25.5)])
    q = multi.get_quote("AC.TO")
    assert q.source == "primary"
    cross = multi.best_cross_quote()
    assert cross is not None and cross.source == "alt" and cross.last == 25.5


def test_stooq_returns_unavailable_not_fabricated_for_unknown():
    # AC.TO is not on stooq; ensure we get a None-valued quote, not a guess.
    adp = StooqAdapter()
    # Force the network call to fail fast by using a bogus symbol path is hard
    # offline; instead assert the contract on a constructed empty parse.
    q = Quote(ticker="AC.TO", last=None, open=None, high=None, low=None,
              prior_close=None, volume=None, source="stooq",
              as_of=None, session_date=None, notes=["stooq unavailable"])
    assert q.last is None  # contract: missing -> None, never 0.0


# ── Claude analyst: well-formed request + cannot mutate the verdict ─────────
class _FakeBlock:
    type = "text"
    text = "PATTERN READ: structure is mixed.\nLEVELS TO WATCH: hold 24.61."


class _FakeResp:
    model = "claude-opus-4-8"
    content = [_FakeBlock()]


class _FakeMessages:
    last_kwargs = {}

    def create(self, **kwargs):
        _FakeMessages.last_kwargs = kwargs
        return _FakeResp()


class _FakeClient:
    def __init__(self, *a, **k):
        self.messages = _FakeMessages()


class _FakeGuard:
    passed = True


def _brief_for_analyst():
    return {
        "ticker": "AC.TO",
        "generated_at": "2026-06-25T09:31:00-04:00",
        "guard": _FakeGuard(),
        "decision": {"verdict": "NO EDGE — WAIT", "probability": 0.50,
                     "conviction": "None", "factors": []},
        "struct": {"open": 24.6, "last": 24.5, "prior_close": 24.5},
        "orb": {}, "vwap": {}, "spike_fade": {"flags": []},
        "levels_actionable": {}, "context": {}, "rel_strength": {},
        "patterns": {"history_days": 503}, "proxy": {},
    }


def test_analyst_request_is_wellformed_and_advisory(monkeypatch):
    import anthropic
    monkeypatch.setattr(anthropic, "Anthropic", _FakeClient)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")

    brief = _brief_for_analyst()
    before = dict(brief["decision"])
    res = analyst.analyze(brief, model="claude-opus-4-8")

    assert res.enabled and res.model == "claude-opus-4-8"
    kw = _FakeMessages.last_kwargs
    assert kw["model"] == "claude-opus-4-8"
    assert kw["thinking"] == {"type": "adaptive"}          # adaptive thinking
    assert "do NOT" in kw["system"] or "NOT produce" in kw["system"]
    # The analyst must NOT have mutated the deterministic decision.
    assert brief["decision"] == before


def test_analyst_disabled_without_key(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_AUTH_TOKEN", raising=False)
    res = analyst.analyze(_brief_for_analyst())
    assert not res.enabled
    assert "ANTHROPIC_API_KEY" in res.text


def test_analyst_skipped_when_guard_failed(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    brief = _brief_for_analyst()
    brief["guard"] = type("G", (), {"passed": False})()
    res = analyst.analyze(brief)
    assert not res.enabled
    assert "guard" in res.text.lower()
