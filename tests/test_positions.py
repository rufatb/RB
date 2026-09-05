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


def test_event_concentration_sees_what_net_exposure_cannot():
    """The live calendar has RPRX, JAZZ and ZYME all on 2026-08-25. A book
    holding all three is a SINGLE-DAY event book however balanced by side.

    Share counts are chosen so the book is genuinely balanced — ~$16.1k long
    against ~$16.0k short — which is the whole point: it looks hedged, and the
    only dimension that matters that morning is not the side.
    """
    rows = []
    for tk, side, px, sh in (("RPRX", "LONG", 61.31, 100),
                             ("ZYME", "LONG", 24.90, 400),
                             ("JAZZ", "SHORT", 254.28, 63)):
        rows = P.open_position(rows, tk, side, sh, px, "2026-08-19",
                               "catalyst", "close on outcome",
                               event_date="2026-08-25", event_kind="PDUFA")
    legs = P.mark_book(rows, {}, TODAY)["legs"]
    # by side this book reads as hedged...
    assert abs(P.net_exposure(legs)) < 0.01
    # ...but every dollar of it resolves on one morning
    clusters = P.event_concentration(legs)
    assert len(clusters) == 1
    d, gross, names = clusters[0]
    assert d == "2026-08-25" and sorted(names) == ["JAZZ", "RPRX", "ZYME"]
    assert gross == pytest.approx(61.31 * 100 + 24.90 * 400 + 254.28 * 63)


def test_a_lone_event_is_not_a_cluster():
    rows = P.open_position([], "ZYME", "LONG", 100, 24.90, "2026-08-19",
                           "catalyst", "close on outcome",
                           event_date="2026-08-25", event_kind="PDUFA")
    assert P.event_concentration(P.mark_book(rows, {}, TODAY)["legs"]) == []


def test_positions_without_an_event_date_never_cluster():
    rows = P.open_position([], "CNR.TO", "SHORT", 76, 175.59, "2026-08-20",
                           "intraday", "flat by 3:55")
    rows = P.open_position(rows, "SU.TO", "LONG", 160, 94.10, "2026-08-20",
                           "intraday", "flat by 3:55")
    assert P.event_concentration(P.mark_book(rows, {}, TODAY)["legs"]) == []


# ── day-88: the API had no door ────────────────────────────────────────────

def test_the_module_exposes_a_cli():
    """CLAUDE.md states 'positions.py records what the user says they did' and
    for 88 days there was no command with which to say it — open_position and
    close_position were defined and unreachable, so a position could only be
    recorded by hand-editing the CSV. It mattered immediately: the page had
    been printing "EXIT ZYME" with no way to record the close."""
    import positions as P
    assert callable(getattr(P, "main", None))
    src = open(P.__file__).read()
    assert '__name__ == "__main__"' in src, "defined but not runnable"
    for cmd in ("open", "close", "list"):
        assert f'add_parser("{cmd}"' in src


def test_open_then_close_round_trips_through_the_cli(tmp_path, monkeypatch):
    import positions as P
    f = str(tmp_path / "p.csv")
    monkeypatch.setattr(P, "POSITIONS", f)
    _load, _save = P.load, P.save
    monkeypatch.setattr(P, "load", lambda path=f: _load(f))
    monkeypatch.setattr(P, "save", lambda rows, path=f: _save(rows, f))

    assert P.main(["open", "zyme", "LONG", "400", "24.90",
                   "--exit-condition", "close on PDUFA outcome"]) == 0
    rows = _load(f)
    assert len(rows) == 1 and rows[0]["ticker"] == "ZYME"
    assert rows[0]["status"] == P.OPEN

    assert P.main(["close", rows[0]["id"], "29.19"]) == 0
    rows = _load(f)
    assert rows[0]["status"] == P.CLOSED
    assert rows[0]["exit_px"].startswith("29.19")


def test_an_exit_condition_is_required_to_open(tmp_path, monkeypatch):
    """A position without a written exit is how a day trade becomes an
    investment. The CLI must not offer a way around that."""
    import positions as P
    f = str(tmp_path / "p.csv")
    monkeypatch.setattr(P, "POSITIONS", f)
    with pytest.raises(SystemExit):
        P.main(["open", "ZYME", "LONG", "400", "24.90"])


def test_closing_an_unknown_id_fails_loudly_and_points_at_list(tmp_path,
                                                               monkeypatch,
                                                               capsys):
    import positions as P
    f = str(tmp_path / "p.csv")
    monkeypatch.setattr(P, "POSITIONS", f)
    _load = P.load
    monkeypatch.setattr(P, "load", lambda path=f: _load(f))
    assert P.main(["close", "99", "10.0"]) == 2
    out = capsys.readouterr().out
    assert "no OPEN position with id 99" in out
    assert "positions.py list" in out


def test_the_cli_never_places_an_order():
    """Read-only, always. It records what the PM says they did."""
    src = open(__import__("positions").__file__).read()
    flat = " ".join(src.split())
    assert "places, sizes and cancels nothing" in flat
    for word in ("submit_order", "place_order", "broker", "api_key"):
        assert word not in src
