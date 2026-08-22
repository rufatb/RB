"""Day-57: position state carried across days.

Everything before this was stateless — the 9:46 engine published a pair and
forgot it. These lock the properties that make a position different from a
pick: a written exit, marks that fail closed, and exposure visible before the
day rather than reconstructed after it.
"""

import datetime as dt

import pytest

import positions as P

TODAY = dt.date(2026, 8, 24)


def _book():
    rows = P.open_position([], "SRPT", "LONG", 100, 18.40, "2026-08-12",
                           "catalyst", "close on PDUFA outcome",
                           event_date="2026-09-03", event_kind="PDUFA")
    return P.open_position(rows, "IONS", "SHORT", 50, 41.00, "2026-08-22",
                           "catalyst", "close on AdCom outcome",
                           event_date="2026-08-30", event_kind="AdCom")


def test_a_position_cannot_be_opened_without_a_written_exit():
    with pytest.raises(ValueError, match="exit_condition is required"):
        P.open_position([], "ABC", "LONG", 10, 5.0, "2026-08-24", "manual", "  ")


def test_open_position_validates_side_and_size():
    with pytest.raises(ValueError):
        P.open_position([], "ABC", "SIDEWAYS", 10, 5.0, "2026-08-24", "m", "x")
    with pytest.raises(ValueError):
        P.open_position([], "ABC", "LONG", 0, 5.0, "2026-08-24", "m", "x")
    with pytest.raises(ValueError):
        P.open_position([], "ABC", "LONG", 10, 0, "2026-08-24", "m", "x")


def test_pnl_signs_are_right_for_both_sides():
    assert P.pnl("LONG", 100.0, 110.0, 1)[0] == pytest.approx(10.0)
    assert P.pnl("SHORT", 100.0, 110.0, 1)[0] == pytest.approx(-10.0)
    assert P.pnl("SHORT", 100.0, 90.0, 1)[0] == pytest.approx(10.0)
    assert P.pnl("LONG", 10.0, 11.0, 100)[1] == pytest.approx(100.0)


def test_a_missing_mark_is_stale_and_never_carried_at_cost():
    """Day-42's lesson: absence of data must not read as absence of movement."""
    b = P.mark_book(_book(), {"SRPT": 21.05}, TODAY)   # IONS has no mark
    ions = [l for l in b["legs"] if l["ticker"] == "IONS"][0]
    assert ions["stale"] is True and ions["pnl_usd"] is None
    assert b["stale"] == 1
    # book totals come from the MARKED leg only, not from IONS at cost
    assert b["net_usd"] == pytest.approx(100 * 18.40 * (21.05/18.40 - 1))


def test_closed_positions_are_excluded_from_the_book():
    rows = P.close_position(_book(), "1", 21.05, "2026-08-24")
    b = P.mark_book(rows, {"SRPT": 21.05, "IONS": 39.60}, TODAY)
    assert [l["ticker"] for l in b["legs"]] == ["IONS"]


def test_closing_an_unknown_or_already_closed_position_raises():
    rows = P.close_position(_book(), "1", 21.05, "2026-08-24")
    with pytest.raises(KeyError):
        P.close_position(rows, "1", 21.05, "2026-08-25")
    with pytest.raises(KeyError):
        P.close_position(rows, "99", 1.0, "2026-08-25")


def test_net_exposure_flags_a_directional_book():
    """Day-47 made $73 on an unhedged short book and the attribution showed
    every cent was the tape. This number has to be visible before the day."""
    legs = P.mark_book(_book(), {"SRPT": 18.40, "IONS": 41.00}, TODAY)["legs"]
    x = P.net_exposure(legs)
    assert -1.0 <= x <= 1.0
    long_only = P.mark_book(
        P.open_position([], "A", "LONG", 10, 10.0, "2026-08-20", "m", "x"),
        {"A": 10.0}, TODAY)["legs"]
    assert P.net_exposure(long_only) == pytest.approx(1.0)
    assert P.net_exposure([]) == 0.0


def test_event_windows_are_flagged_before_they_open_not_after():
    legs = P.mark_book(_book(), {"SRPT": 21.05, "IONS": 39.60}, TODAY)["legs"]
    closing, upcoming = P.due_today(legs, TODAY, warn_days=7)
    assert [l["ticker"] for l in closing] == []
    assert [(l["ticker"], d) for l, d in upcoming] == [("IONS", 6)]
    # on the day itself it moves to `closing`
    closing, _ = P.due_today(legs, dt.date(2026, 8, 30))
    assert [l["ticker"] for l in closing] == ["IONS"]


def test_days_held_counts_from_entry():
    assert P.days_held("2026-08-12", TODAY) == 12


def test_ids_are_unique_and_survive_closes():
    rows = _book()
    rows = P.close_position(rows, "1", 20.0, "2026-08-24")
    rows = P.open_position(rows, "XYZ", "LONG", 1, 1.0, "2026-08-24", "m", "x")
    assert [r["id"] for r in rows] == ["1", "2", "3"]
