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
    assert "no approval probability is estimated here" in out
    assert "the molecule decides the trade" in out
    assert "$19.78" in out and "$37.56" in out       # priced range shown


def test_render_says_so_when_nothing_is_in_the_window():
    assert "nothing scheduled" in S.render([], dt.date(2026, 8, 22))
