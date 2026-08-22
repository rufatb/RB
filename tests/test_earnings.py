"""Day-65: earnings proximity — the event risk the 9:45 model cannot see.

Deliberately a WARNING and not a gate. No free source gives historical TSX
announcement dates, so the cost of trading through one is unmeasured, and
these tests pin that the module never claims otherwise.
"""

import datetime as dt

import earnings as E

TODAY = dt.date(2026, 8, 22)


def test_a_report_today_is_inside_the_session_window():
    d, label = E.classify("2026-08-22", TODAY)
    assert d == 0 and "inside the session window" in label


def test_tomorrow_is_distinguished_from_today():
    """A report after today's close cannot move a leg flat by 3:55."""
    d, label = E.classify("2026-08-23", TODAY)
    assert d == 1 and "not in today's window" in label


def test_a_recent_report_notes_the_pool_may_not_represent_it():
    d, label = E.classify("2026-08-20", TODAY)
    assert d == -2 and "pool may not represent" in label


def test_a_distant_date_is_just_counted():
    d, label = E.classify("2026-09-05", TODAY)
    assert d == 14 and label == "in 14d"


def test_picks_reporting_within_a_day_are_flagged():
    cal = {"RY.TO": {"dates": ["2026-08-22"], "error": None}}
    out = E.render(cal, TODAY, picks={"RY.TO"})
    assert "⚠ " in out and "RY.TO" in out


def test_a_non_pick_far_out_does_not_crowd_the_page():
    cal = {"BMO.TO": {"dates": ["2026-08-27"], "error": None}}
    assert E.render(cal, TODAY, picks=set()) == ""


def test_a_pick_further_out_is_still_shown():
    cal = {"BMO.TO": {"dates": ["2026-08-27"], "error": None}}
    out = E.render(cal, TODAY, picks={"BMO.TO"}, horizon=7)
    assert "BMO.TO" in out and "in 5d" in out


def test_a_fetch_failure_is_unknown_never_clear():
    cal = {"RY.TO": {"dates": [], "error": "HTTPError"}}
    out = E.render(cal, TODAY, picks={"RY.TO"})
    assert "could not check" in out and "unknown, not clear" in out


def test_the_block_never_claims_to_be_backtested():
    cal = {"RY.TO": {"dates": ["2026-08-22"], "error": None}}
    out = E.render(cal, TODAY, picks={"RY.TO"})
    assert "NOT backtested" in out
    assert "a WARNING, not a gate" in out
    assert "never been measured here" in out
