"""Day-72: what the intraday pair costs to express.

The engine's edge is measured at zero, so the spread is not a cost on top of
the edge -- it IS the expected outcome. These lock the arithmetic and, above
all, lock the one wrong answer that would be catastrophic: reporting an unknown
spread as zero, which says the trade is free.
"""

import cost as C


def test_spread_is_basis_points_of_the_mid():
    assert abs(C.spread_bps({"bid": 9.99, "ask": 10.01}) - 20.0) < 0.1


def test_a_one_sided_or_missing_quote_is_unknown_never_zero():
    """Zero is the most expensive wrong answer available: it says the trade is
    free."""
    for q in ({"bid": 10.0, "ask": None}, {"bid": None, "ask": 10.0}, {},
              {"bid": 0, "ask": 0}):
        assert C.spread_bps(q) is None


def test_a_crossed_book_is_unknown_rather_than_negative():
    assert C.spread_bps({"bid": 10.05, "ask": 9.95}) is None


def test_the_cost_is_a_full_spread_because_both_crossings_are_certain():
    """The strategy is flat by 15:55 every day. There is no version of this
    trade that pays the spread once."""
    d = C.drag(20.0, shares=1000, price=50.0)
    assert abs(d["usd"] - 20.0 / 10000 * 1000 * 50.0) < 1e-9


def test_the_spread_is_expressed_against_the_measured_typical_move():
    # Against the CONSTANT, not a copy of its value. This assertion held a
    # literal 0.97 and so had to be edited when day-87 adopted the ledger
    # re-derivation — a test that breaks on a legitimate change is testing the
    # number rather than the arithmetic.
    d = C.drag(25.0, shares=None, price=None)
    assert abs(d["share_of_move"] - 0.25 / C.TYPICAL_MOVE_PCT) < 1e-9
    assert d["usd"] is None                 # no size given, none invented


def test_the_typical_move_is_the_ledger_re_derivation_not_the_universe_one():
    """Pins the day-87 decision so the value cannot drift back silently.

    0.69% is the median |capture| over the ledger's own scored legs. 0.97% was
    day-70's figure for the whole universe, which is the wrong population for a
    denominator whose numerators are a pick's spread and the picks' hit rate.
    The change is AGAINST us — the old number understated the drag.
    """
    assert C.TYPICAL_MOVE_PCT == 0.69
    import validate_typicalmove as V
    lo, hi = V.run()["ci"]
    assert lo <= C.TYPICAL_MOVE_PCT <= hi, (
        f"the shipped constant {C.TYPICAL_MOVE_PCT} is outside its own "
        f"re-derivation [{lo}, {hi}] — re-open DECISION_day87.md")


def test_an_unknown_spread_produces_no_dollar_figure():
    d = C.drag(None, shares=1000, price=50.0)
    assert d["usd"] is None and d["share_of_move"] is None


def test_the_directional_term_is_negative_at_the_live_record():
    """34/70 is below a coin flip, and the report should not round that up."""
    assert C.edge_bps(34, 70) < 0


def test_the_directional_term_is_zero_at_exactly_even():
    assert abs(C.edge_bps(35, 70)) < 1e-9


def test_a_real_edge_would_show_as_positive_basis_points():
    assert C.edge_bps(42, 70) > 0


def test_an_empty_record_does_not_divide_by_zero():
    assert C.edge_bps(0, 0) == 0.0


def test_render_states_the_arithmetic_is_not_a_forecast():
    rows = [{"ticker": "ABX.TO", "shares": 100, "price": 30.0,
             "cost": C.drag(30.0, 100, 30.0)}]
    out = " ".join(C.render(rows))
    assert "arithmetic, not a forecast" in out
    assert "it IS the outcome" in out


def test_render_names_an_unknown_spread_as_unknown_in_the_report():
    rows = [{"ticker": "X.TO", "shares": 100, "price": 30.0,
             "cost": C.drag(None, 100, 30.0)}]
    out = " ".join(C.render(rows))
    assert "UNKNOWN" in out and "Not zero: unknown" in out


def test_render_is_silent_with_nothing_to_price():
    assert C.render([]) == []


# ── day-87: a post-close spread is not a tradeable spread ──────────────────

def _et(y, mo, d, h, mi):
    import datetime as dt
    from zoneinfo import ZoneInfo
    return dt.datetime(y, mo, d, h, mi, tzinfo=ZoneInfo("America/New_York"))


def test_the_9_46_run_is_inside_trading_hours():
    assert not C.outside_trading_hours(_et(2026, 9, 4, 9, 46))


def test_an_after_close_run_is_flagged():
    """On 2026-09-04 the same two-leg book costed $24.39 at 09:46 and $94 at
    17:33. The second is last posted bid/ask, not a tradeable spread."""
    assert C.outside_trading_hours(_et(2026, 9, 4, 17, 33))


def test_the_boundaries_are_the_session_not_the_hour():
    assert C.outside_trading_hours(_et(2026, 9, 4, 9, 29))
    assert not C.outside_trading_hours(_et(2026, 9, 4, 9, 30))
    assert not C.outside_trading_hours(_et(2026, 9, 4, 15, 59))
    assert C.outside_trading_hours(_et(2026, 9, 4, 16, 0))


def test_a_weekend_is_outside_regardless_of_the_clock():
    assert C.outside_trading_hours(_et(2026, 9, 5, 12, 0))    # Sat
    assert C.outside_trading_hours(_et(2026, 9, 6, 12, 0))    # Sun


def test_a_naive_datetime_is_read_as_eastern_not_utc():
    import datetime as dt
    assert not C.outside_trading_hours(dt.datetime(2026, 9, 4, 10, 0))


def test_it_labels_rather_than_gates():
    """A missing warning is the acceptable failure; a blocked order is not.
    It cannot see holidays, and the docstring says so."""
    flat = " ".join(C.outside_trading_hours.__doc__.split())
    assert "not holidays" in flat
    assert "never a gate" in flat
