"""Day-80: a record of what the SYSTEM said to do.

Three records existed and none held a recommendation. When this system said
"exit ZYME" twice and holding was right, nothing captured that it had said so.
An adviser whose recommendations are not written down cannot be evaluated.
"""

import datetime as dt

import advice as A

TODAY = dt.date(2026, 8, 30)


def test_advice_must_come_from_a_closed_set():
    """'Consider trimming' is not an action and cannot be scored."""
    try:
        A.record([], "ZYME", "consider trimming", "b", 5, 10.0, TODAY)
        assert False, "expected a rejection"
    except ValueError:
        pass


def test_the_same_advice_twice_in_one_day_is_one_recommendation():
    """Re-running the morning report must not multiply the record."""
    rows, n = A.record([], "ZYME", "EXIT", "catalyst resolved", 5, 28.6, TODAY)
    assert n == 1
    rows, n = A.record(rows, "ZYME", "EXIT", "catalyst resolved", 5, 28.6, TODAY)
    assert n == 0 and len(rows) == 1


def test_the_same_ticker_can_carry_different_advice():
    rows, _ = A.record([], "ZYME", "EXIT", "b", 5, 28.6, TODAY)
    rows, n = A.record(rows, "ZYME", "HEDGE", "b", 5, 28.6, TODAY)
    assert n == 1 and len(rows) == 2


def test_advice_is_not_due_before_its_horizon():
    rows, _ = A.record([], "ZYME", "EXIT", "b", 10, 28.6, TODAY)
    assert A.due(rows, TODAY + dt.timedelta(days=3)) == []
    assert len(A.due(rows, TODAY + dt.timedelta(days=10))) == 1


def test_marking_never_back_edits_something_already_judged():
    rows, _ = A.record([], "ZYME", "EXIT", "b", 5, 100.0, TODAY)
    rows, n = A.mark(rows, lambda t: 90.0, TODAY + dt.timedelta(days=5))
    assert n == 1 and rows[0]["move_pct"] == "-10.000"
    rows, n = A.mark(rows, lambda t: 50.0, TODAY + dt.timedelta(days=9))
    assert n == 0 and rows[0]["move_pct"] == "-10.000"


def test_the_move_is_stored_raw_and_the_sign_applied_per_action():
    """A -10% move is good advice after SELL and bad after BUY. Storing the
    judgement would let the file flatter itself."""
    sell, _ = A.record([], "X", "SELL", "b", 5, 100.0, TODAY)
    buy, _ = A.record([], "Y", "BUY", "b", 5, 100.0, TODAY)
    sell, _ = A.mark(sell, lambda t: 90.0, TODAY + dt.timedelta(days=5))
    buy, _ = A.mark(buy, lambda t: 90.0, TODAY + dt.timedelta(days=5))
    assert sell[0]["move_pct"] == buy[0]["move_pct"] == "-10.000"
    assert "1/1" in A.report(sell)      # the sell was right
    assert "0/1" in A.report(buy)       # the buy was wrong


def test_hold_and_stand_aside_are_never_scored():
    """They carry no directional claim; scoring them would score the market."""
    rows, _ = A.record([], "X", "HOLD", "b", 5, 100.0, TODAY)
    rows, _ = A.record(rows, "Y", "STAND ASIDE", "b", 5, 100.0, TODAY)
    rows, _ = A.mark(rows, lambda t: 130.0, TODAY + dt.timedelta(days=5))
    out = A.report(rows)
    assert "none with a directional claim" in out


def test_an_empty_record_says_nothing_can_be_judged_yet():
    out = A.report([])
    assert "0 scored" in out and "saying so is the point" in out


def test_every_recommendation_carries_the_measurement_it_rests_on():
    """Five measured claims have been retracted in eleven days. Advice must be
    findable from its basis when the basis moves."""
    rows, _ = A.record([], "ZYME", "EXIT", "approval leg t=+2.42, below bar",
                       5, 28.6, TODAY)
    assert "approval leg" in rows[0]["basis"]
    assert rows[0]["horizon_days"] == "5"
    assert rows[0]["px_at_advice"] == "28.6000"


# ── day-88: the record must not fill with rows that can never be judged ────

def test_unmarkable_advice_is_not_recorded():
    """`due()` skips a row with no px_at_advice forever, so recording one
    creates permanent dead weight in a file whose purpose is falsifiability.
    brief counts them instead."""
    import inspect

    import brief as B
    src = inspect.getsource(B.build)
    block = src[src.index("RECORD THE ADVICE"):]
    assert 'if _l.get("mark") is None' in block
    assert "advice_unpriced" in src


def test_due_skips_rows_with_no_price_rather_than_crashing():
    import datetime as dt

    import advice as A
    rows = [{"issued": "2026-08-20", "ticker": "X", "action": "EXIT",
             "basis": "b", "horizon_days": "5", "px_at_advice": "",
             "px_at_horizon": "", "move_pct": "", "judged": "", "note": ""}]
    assert A.due(rows, dt.date(2026, 9, 8)) == []
    marked, n = A.mark(rows, lambda t: 10.0, dt.date(2026, 9, 8))
    assert n == 0


def test_marking_happens_before_recording_so_today_is_not_judged_today():
    import inspect

    import brief as B
    src = inspect.getsource(B.build)
    assert src.index("_adv.mark") < src.index("_adv.record")
