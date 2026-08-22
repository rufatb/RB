"""Day-60: the catalyst opportunity screen.

The screen's job is to say what the market has ALREADY priced, so a human
judgement about the drug applies to the residual. These lock the two ways it
could mislead: inventing a probability, and reading a small implied move as
a bargain.
"""

import datetime as dt

import screen as S


def _chain(spot, call_px, put_px, call_iv=0.8, put_iv=0.8):
    strikes = [spot * 0.9, spot, spot * 1.1]
    calls = [{"strike": k, "lastPrice": call_px, "impliedVolatility": call_iv}
             for k in strikes]
    puts = [{"strike": k, "lastPrice": put_px, "impliedVolatility": put_iv}
            for k in strikes]
    return calls, puts


def test_implied_move_is_the_atm_straddle_over_spot():
    c, p = _chain(100.0, 15.0, 16.0)
    assert S.implied_move(c, p, 100.0) == 0.31


def test_implied_move_is_none_without_a_usable_chain():
    assert S.implied_move([], [], 100.0) is None
    assert S.implied_move(*_chain(100.0, 1.0, 1.0), 0) is None


def test_skew_is_put_iv_minus_call_iv():
    c, p = _chain(100.0, 5.0, 5.0, call_iv=0.60, put_iv=0.85)
    assert abs(S.skew(c, p, 100.0) - 0.25) < 1e-9


def test_expiry_must_cover_the_event_not_precede_it():
    """An expiry before the decision prices a different question entirely."""
    ev = dt.date(2026, 8, 25)
    before = int(dt.datetime(2026, 8, 21).timestamp())
    after = int(dt.datetime(2026, 9, 18).timestamp())
    later = int(dt.datetime(2026, 10, 16).timestamp())
    assert S.pick_expiry([before, after, later], ev) == after
    assert S.pick_expiry([before], ev) is None


def test_a_small_implied_move_is_immateriality_not_a_bargain():
    """Live, this tagged RPRX (+/-4%) as a 'cheap binary'. It is a diversified
    royalty portfolio — the market was saying the event does not matter."""
    label, why = S.stance(0.04, None, 3, [])
    assert label == "not material"
    assert "immaterial to the enterprise" in why
    assert "cheap" not in why.lower() and "underpric" not in why.lower()


def test_a_large_implied_move_is_labelled_existential_not_expensive():
    label, why = S.stance(0.53, None, 69, [])
    assert label == "existential"
    assert "company-defining" in why and "the DRUG" in why


def test_a_typical_move_is_a_material_binary():
    assert S.stance(0.31, None, 3, [])[0] == "material binary"


def test_put_bid_over_calls_is_reported_as_fear_not_forecast():
    _, why = S.stance(0.31, 0.25, 3, [])
    assert "CRL insurance" in why


def test_filing_signals_are_carried_into_the_stance():
    _, why = S.stance(0.31, None, 30, ["review EXTENDED", "prior CRL"])
    assert "EXTENDED" in why and "RESUBMISSION" in why


def test_missing_options_are_named_never_guessed():
    label, why = S.stance(None, None, 10, [])
    assert label == "no options" and "no listed chain" in why


def test_render_never_states_an_approval_probability():
    rows = [{"date": "2026-08-25", "days": 3, "ticker": "ZYME",
             "company": "Zymeworks Inc.", "spot": 28.67, "move": 0.31,
             "skew": None, "expiry": "2026-09-18", "signals": ["priority review"],
             "stance": "material binary", "why": "+/-31% implied"}]
    out = S.render(rows, dt.date(2026, 8, 22))
    assert "P(CRL) is deliberately NOT supplied" in out
    assert "would be fabricated" in out
    assert "$19.78" in out and "$37.56" in out       # priced range shown


def test_render_says_so_when_nothing_is_in_the_window():
    assert "nothing scheduled" in S.render([], dt.date(2026, 8, 22))


# ── day-70: the verdict. The screen used to print four inputs and leave the
# reader to combine them. These lock the synthesis — and, more importantly,
# lock the two ways a synthesis could do real damage: recommending a long into
# a print the evidence does not support, and inventing the probability that
# would justify one.

import catalyst as C


def _row(**kw):
    r = {"date": "2026-09-22", "days": 31, "ticker": "ZYME",
         "company": "Zymeworks Inc.", "spot": 28.67, "move": 0.31,
         "skew": None, "call_pct": 0.15, "put_pct": 0.16, "signals": [],
         "fund": None, "stance": "material binary", "why": "+/-31% implied"}
    r.update(kw)
    return r


def test_breakeven_is_put_cost_over_the_measured_median_drop():
    """The one number the screen owes a PM: how likely the bad outcome has to
    be before the premium makes sense."""
    be = S.put_breakeven(0.09)
    assert abs(be - 0.09 / 0.152) < 1e-9
    assert 0.58 < be < 0.60


def test_breakeven_above_one_is_reported_not_clamped():
    """A premium above the median drawdown means no probability makes the
    median case pay. Clamping that to 100% would hide it."""
    assert S.put_breakeven(0.20) > 1.0
    assert S.put_breakeven(None) is None


def test_a_dear_put_is_called_dear_and_the_tail_named_as_the_only_case():
    v = S.verdict(_row(put_pct=0.20))
    assert v["call"] == "PROTECTION IS DEAR — STAND ASIDE"
    assert "bet on the tail alone" in " ".join(v["why"])


def test_a_cheap_put_is_the_cheaper_side_with_an_upper_bound_stated():
    v = S.verdict(_row(put_pct=0.04))
    assert v["call"] == "DOWNSIDE IS THE CHEAPER SIDE"
    joined = " ".join(v["why"])
    assert "upper bound" in joined          # median understates the payoff


def test_no_verdict_ever_endorses_holding_a_long_through_the_print():
    """The day-68 asymmetry in one assertion. Approval windows are
    indistinguishable from random ones, so the winning outcome pays nothing
    measurable while the losing one takes 15%."""
    for put in (0.03, 0.09, 0.16, 0.25):
        v = S.verdict(_row(put_pct=put))
        joined = " ".join(v["why"])
        assert "selling insurance, not buying a ticket" in joined
        assert "BUY" not in v["call"] and "LONG" not in v["call"]


def test_an_immaterial_move_is_not_an_event_trade_at_any_put_price():
    """RPRX again: +/-4% is the market saying the decision does not move the
    enterprise. A cheap put on it is not an opportunity."""
    v = S.verdict(_row(move=0.04, put_pct=0.02))
    assert v["call"] == "NOT AN EVENT TRADE"
    assert "does not move the enterprise" in " ".join(v["why"])


def test_no_chain_means_the_full_measured_downside_is_unhedged():
    v = S.verdict(_row(move=None, put_pct=None))
    assert v["call"] == "NO PRICED EXPRESSION"
    assert "nothing capping it" in " ".join(v["why"])


def test_short_runway_is_named_as_a_second_binary_that_is_not_the_fda():
    v = S.verdict(_row(fund={"runway_q": 1.9, "cash_per_share": 2.53,
                             "burn_q": 40e6}))
    joined = " ".join(v["why"])
    assert "financing event independent of the decision" in joined
    assert "approval does not stop the raise" in joined


def test_no_balance_sheet_floor_is_stated_when_price_is_a_multiple_of_cash():
    """The ZYME matrix claimed a cash-backed floor at $20.50 on $2.53 of cash."""
    v = S.verdict(_row(fund={"cash_per_share": 2.53, "runway_q": 4.6}))
    assert "no balance-sheet floor" in " ".join(v["why"])


def test_a_favourable_adcom_makes_protection_dearer_and_is_labelled_external():
    v = S.verdict(_row(), vote={"direction": "favourable"})
    joined = " ".join(v["why"])
    assert "EXTERNALLY 97%" in joined and "JAMA 2023" in joined


def test_an_unfavourable_adcom_is_read_as_time_risk_not_a_verdict():
    v = S.verdict(_row(), vote={"direction": "unfavourable"})
    joined = " ".join(v["why"])
    assert "risk being held is TIME, not a verdict" in joined


def test_the_verdict_never_takes_a_name_out_of_the_screen():
    """A broken synthesis still leaves a real date and a real price worth
    seeing. Fail loud in the line, not by dropping the row."""
    bad = _row(fund="not-a-dict")
    try:
        S.verdict(bad)
        assert False, "expected the malformed row to raise inside verdict()"
    except Exception:
        pass


def test_hold_window_says_when_the_position_stops_being_available():
    assert "had to exist yesterday" in S.hold_window(0, "2026-08-22")
    assert "express or stand aside now" in S.hold_window(3, "2026-08-25")
    assert "working window" in S.hold_window(31, "2026-09-22")
    assert "too early to pay premium" in S.hold_window(90, "2026-11-20")


def test_the_footer_states_the_measured_asymmetry_with_its_test_statistics():
    """The verdicts are only as good as their basis; the basis has to travel
    with them, with the numbers that make it checkable."""
    out = S.render([_row(verdict=S.verdict(_row()))], dt.date(2026, 8, 22))
    assert f"{C.CRL_MEDIAN:.1f}%" in out and f"t={C.CRL_T:.2f}" in out
    assert f"n={C.CRL_N}" in out
    assert "FAILS that same placebo gate" in out


def test_leg_costs_separate_the_two_sides_the_straddle_averages_together():
    c, p = _chain(100.0, 12.0, 18.0)
    call_pct, put_pct = S.leg_costs(c, p, 100.0)
    assert call_pct == 0.12 and put_pct == 0.18
    assert S.leg_costs([], [], 100.0) == (None, None)
