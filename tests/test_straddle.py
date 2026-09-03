"""Day-83 Stage 1: what a straddle costs, and the refusal that protects it.

Pre-registered in PREREGISTER_day83.md. Stage 1 can end the study, so the
things that could make it end WRONGLY are what is tested hardest: a spread
measured while the feed is shut, a one-sided quote treated as a price, and a
round trip counted as half of what it is.
"""

import pytest

import quotes as Q
import validate_straddle as V


def chain_stub(spot=100.0, bid=1.0, ask=1.2, oi=500, expiries=(1_800_000_000,),
               control_two_sided=True, raises=False, puts=True):
    """Yahoo-shaped chain. SPY is the control and is quoted separately, so a
    dead feed can be simulated independently of the names under test."""
    def fn(ticker, expiry=None):
        if raises:
            raise ConnectionError("simulated")
        if expiry is None:
            return {"quote": {"regularMarketPrice": spot},
                    "expirationDates": list(expiries)}
        if ticker == Q.CONTROL_TICKER:
            b, a = (1.0, 1.1) if control_two_sided else (0.0, 0.0)
            return {"options": [{"calls": [], "puts": [
                {"strike": spot, "bid": b, "ask": a, "lastPrice": 1.0,
                 "openInterest": 9999}]}]}
        leg = [{"strike": spot, "bid": bid, "ask": ask, "lastPrice": 1.1,
                "openInterest": oi}]
        return {"options": [{"calls": leg, "puts": leg if puts else []}]}
    return fn


# ── the refusal: a cost measured while the feed is shut is "trading is free" ──

def test_a_dead_feed_refuses_rather_than_reporting_zero_cost():
    """THE CASE THIS EXISTS FOR. Pre-market every bid/ask is 0, which computes
    to a spread of zero for every name. A study that ran then would conclude
    trading is free — the most flattering error available."""
    c = V.cost_now(chain_stub(control_two_sided=False), tickers=["SU"])
    assert c["feed_live"] is False
    assert c["median"] is None
    assert "trading is free" in c["refused"]
    assert c["rows"] == [], "no per-name number may be recorded"


def test_a_live_feed_measures():
    c = V.cost_now(chain_stub(), tickers=["SU", "TD"])
    assert c["feed_live"] and c["n_priced"] == 2
    assert c["median"] is not None


def test_the_report_shows_the_refusal_not_an_empty_table():
    c = V.cost_now(chain_stub(control_two_sided=False), tickers=["SU"])
    out = V.report(c, 0.140)
    assert "⛔" in out and "Re-run during market hours" in out
    assert "median" not in out


# ── a one-sided quote is not a price ────────────────────────────────────────

def test_a_missing_bid_or_ask_yields_no_price():
    assert V._mid_spread({"bid": 0, "ask": 1.2}) == (None, None)
    assert V._mid_spread({"bid": 1.0, "ask": 0}) == (None, None)
    assert V._mid_spread({"lastPrice": 5.0}) == (None, None)


def test_lastprice_is_never_substituted_for_a_two_sided_quote():
    """Explicitly forbidden by the pre-registration: it would turn an
    unquotable contract into a cheap one."""
    fn = chain_stub(bid=0.0, ask=0.0)          # only lastPrice available
    r = V.straddle_cost(fn, "SU")
    assert r["reason"] == Q.NO_TWO_SIDED
    assert r["roundtrip_pct"] is None


def test_a_crossed_quote_is_refused():
    assert V._mid_spread({"bid": 2.0, "ask": 1.0}) == (None, None)


# ── the round trip is the FULL spread on both legs ──────────────────────────

def test_the_round_trip_counts_both_legs_entering_and_exiting():
    """A straddle crosses the call spread and the put spread on the way in and
    again on the way out. Counting half would halve the only certain term in
    the whole study."""
    fn = chain_stub(spot=100.0, bid=1.0, ask=1.2)   # 0.20 wide, two legs
    r = V.straddle_cost(fn, "SU")
    assert abs(r["roundtrip_pct"] - 0.40) < 1e-9     # (0.2 + 0.2) / 100 * 100
    assert abs(r["straddle_pct"] - 2.20) < 1e-9      # (1.1 + 1.1) / 100 * 100


def test_a_wider_spread_costs_more():
    tight = V.straddle_cost(chain_stub(bid=1.00, ask=1.05), "SU")
    wide = V.straddle_cost(chain_stub(bid=1.00, ask=1.60), "SU")
    assert wide["roundtrip_pct"] > tight["roundtrip_pct"] * 5


# ── coverage failures are typed, not silent ────────────────────────────────

def test_a_thin_chain_is_rejected_with_a_reason():
    r = V.straddle_cost(chain_stub(oi=3), "BMO")
    assert r["reason"] == Q.ZERO_OI and r["roundtrip_pct"] is None


def test_a_name_with_no_listed_options_says_so():
    r = V.straddle_cost(chain_stub(expiries=()), "SU.TO")
    assert r["reason"] == Q.NO_EXPIRIES


def test_a_fetch_failure_is_typed_not_swallowed():
    r = V.straddle_cost(chain_stub(raises=True), "SU")
    assert r["reason"] == Q.CHAIN_ERROR and r["detail"] == "ConnectionError"


def test_a_chain_with_no_puts_is_reported():
    assert V.straddle_cost(chain_stub(puts=False), "SU")["reason"] == Q.NO_PUTS


# ── the gate is applied without discretion ─────────────────────────────────

def test_the_bar_is_half_the_measured_lift():
    import sixk
    ok, why = V.verdict(0.05, sixk.WIDER_PP)
    assert ok is True and "under" in why
    ok, why = V.verdict(0.50, sixk.WIDER_PP)
    assert ok is False and "REJECTED ON COST" in why


def test_a_cost_exactly_at_the_bar_does_not_pass():
    """The bar is strict. A tie is not a pass, decided in advance."""
    ok, _ = V.verdict(0.070, 0.140)
    assert ok is False


def test_no_verdict_is_offered_when_cost_could_not_be_measured():
    ok, why = V.verdict(None, 0.140)
    assert ok is None and "no verdict" in why


def test_the_bar_uses_the_registered_constant_not_a_literal():
    import constants as K
    assert K.REGISTRY["validate_straddle.COST_BAR_FRACTION"].kind == K.DESIGN
    assert V.COST_BAR_FRACTION == 0.5


def test_the_measured_lift_is_registered_with_its_script():
    """The bar is half of it, so an unprovenanced lift would make the whole
    gate uncheckable."""
    import constants as K
    assert K.REGISTRY["sixk.WIDER_PP"].script == "validate_sixk.py"
    assert K.REGISTRY["sixk.WIDER_PP"].kind == K.MEASURED


def test_main_exits_nonzero_when_it_could_not_measure(monkeypatch):
    """A refusal must be visible to a caller, not look like a clean run."""
    monkeypatch.setattr(V, "cost_now",
                        lambda *a, **k: {"feed_live": False, "rows": [],
                                         "median": None, "n_priced": 0,
                                         "feed_why": "shut",
                                         "refused": "trading is free"})
    assert V.main([]) == 2
