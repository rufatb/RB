"""Day-64: the scored record for catalyst trades.

The intraday engine can say "no edge" as a MEASUREMENT because 356 legs were
recorded before the answer was knowable. The catalyst stack had apparatus and
zero scored outcomes. These lock the properties that make the record usable.
"""

import datetime as dt

import catledger as C

TODAY = dt.date(2026, 8, 22)


def _screened(ticker="ZYME", date="2026-08-25", spot=28.67, move=0.31):
    return [{"ticker": ticker, "date": date, "spot": spot, "move": move,
             "skew": 0.12, "stance": "material binary",
             "fund": {"cash_per_share": 2.53, "runway_q": 4.6}}]


def test_a_screened_event_is_logged_with_what_was_knowable_then():
    rows, n = C.log_screen([], _screened(), TODAY)
    assert n == 1
    r = rows[0]
    assert r["ticker"] == "ZYME" and r["px_at_log"] == "28.6700"
    assert r["implied_move"] == "0.3100" and r["cash_per_share"] == "2.5300"
    assert r["outcome"] == "" and r["move_actual"] == ""


def test_the_same_event_is_never_logged_twice():
    """A PDUFA appears in the screen every morning for months. Re-logging it
    daily would turn one event into ninety rows and make any hit rate
    meaningless."""
    rows, _ = C.log_screen([], _screened(), TODAY)
    rows, n = C.log_screen(rows, _screened(), TODAY + dt.timedelta(days=1))
    assert n == 0 and len(rows) == 1


def test_two_events_for_one_sponsor_are_two_rows():
    rows, _ = C.log_screen([], _screened(date="2026-09-22"), TODAY)
    rows, n = C.log_screen(rows, _screened(date="2026-10-26"), TODAY)
    assert n == 1 and len(rows) == 2


def test_untraded_screens_are_logged_too():
    """Recording only the trades taken would measure the trader, not the
    screen. Both questions have to stay answerable."""
    rows, _ = C.log_screen([], _screened(), TODAY, traded=set())
    assert rows[0]["traded"] == "0"
    rows2, _ = C.log_screen([], _screened(), TODAY, traded={"ZYME"})
    assert rows2[0]["traded"] == "1"


def test_scoring_waits_for_the_event_to_settle():
    """A decision announced on the date is often disclosed after the close."""
    rows, _ = C.log_screen([], _screened(date="2026-08-21"), TODAY)
    _, n = C.score(rows, lambda t: 40.0, TODAY)          # 1 day after
    assert n == 0
    _, n = C.score(rows, lambda t: 40.0, TODAY + dt.timedelta(days=3))
    assert n == 1


def test_scoring_records_the_realised_move_against_the_logged_price():
    rows, _ = C.log_screen([], _screened(date="2026-08-10"), TODAY)
    rows, _ = C.score(rows, lambda t: 14.335, TODAY)     # exactly -50%
    assert rows[0]["move_actual"] == "-50.000"
    assert rows[0]["px_after"] == "14.3350"


def test_an_unfetchable_price_leaves_the_row_unscored():
    rows, _ = C.log_screen([], _screened(date="2026-08-10"), TODAY)
    rows, n = C.score(rows, lambda t: None, TODAY)
    assert n == 0 and rows[0]["move_actual"] == ""


def test_a_scored_row_is_never_rescored():
    rows, _ = C.log_screen([], _screened(date="2026-08-10"), TODAY)
    rows, _ = C.score(rows, lambda t: 40.0, TODAY)
    first = rows[0]["move_actual"]
    rows, n = C.score(rows, lambda t: 99.0, TODAY + dt.timedelta(days=5))
    assert n == 0 and rows[0]["move_actual"] == first


def test_the_report_refuses_to_pretend_before_anything_resolves():
    rows, _ = C.log_screen([], _screened(), TODAY)
    out = C.report(rows)
    assert "No event has resolved yet" in out
    assert "evidence rather than opinion" in out


def test_the_report_warns_that_a_thin_record_proves_nothing():
    rows = []
    for i in range(5):
        rows, _ = C.log_screen(rows, _screened(ticker=f"T{i}",
                                               date="2026-08-10"), TODAY)
    rows, _ = C.score(rows, lambda t: 40.0, TODAY)
    out = C.report(rows)
    assert "far too few to conclude anything" in out
    assert "not so it can be quoted" in out


def test_the_report_separates_traded_from_screened_only():
    rows, _ = C.log_screen([], _screened(date="2026-08-10"), TODAY,
                           traded={"ZYME"})
    rows, _ = C.log_screen(rows, _screened(ticker="ABCD", date="2026-08-10"),
                           TODAY)
    rows, _ = C.score(rows, lambda t: 40.0, TODAY)
    out = C.report(rows)
    assert "traded" in out and "screened only" in out


def test_exceeded_implied_is_counted_against_the_logged_implied_move():
    """The falsifiable claim: do outcomes beat what the market priced?"""
    rows, _ = C.log_screen([], _screened(date="2026-08-10", move=0.10), TODAY)
    rows, _ = C.score(rows, lambda t: 28.67 * 1.5, TODAY)   # +50% vs 10% implied
    assert "exceeded implied 1/1" in C.report(rows)
