"""Day-58: the unified morning page.

The brief's value is that it can say "nothing to do" and that it never
presents a layer as stronger than its evidence. These lock both.
"""

import datetime as dt

import brief
import positions as P

TODAY = dt.date(2026, 8, 24)


def _book(marks):
    rows = P.open_position([], "ZYME", "LONG", 400, 24.90, "2026-08-19",
                           "catalyst", "close on PDUFA outcome",
                           event_date="2026-08-25", event_kind="PDUFA")
    return P.mark_book(rows, marks, TODAY)


def test_a_flat_book_says_so_plainly():
    out = brief.render_positions(P.mark_book([], {}, TODAY), TODAY)
    assert "none" in out and "Flat" in out


def test_stale_marks_are_named_and_excluded_not_carried_at_cost():
    out = brief.render_positions(_book({}), TODAY, {"ZYME": "HTTPError"})
    assert "EXCLUDED" in out and "HTTPError" in out
    assert "stale leg is not a flat leg" in out


def test_a_directional_book_is_labelled_directional():
    out = brief.render_positions(_book({"ZYME": 28.67}), TODAY)
    assert "DIRECTIONAL long" in out


def test_binary_window_warning_fires_before_the_event():
    out = brief.render_actions(_book({"ZYME": 28.67}), TODAY, "nothing")
    assert "enters its PDUFA window in 1d" in out
    assert "a decision taken during the gap is not a decision" in out


def test_actions_can_report_nothing_to_do():
    """The old report could not say this; it manufactured a pair every day."""
    out = brief.render_actions(P.mark_book([], {}, TODAY), TODAY,
                               "nothing — no leg qualified")
    assert "nothing due" in out and "nothing — no leg qualified" in out


def _res(long_pick="SU.TO", short_status="OK"):
    longs = [{"t": "SU.TO", "nd": 0.223, "confidence": "mid", "p945": 94.10},
             {"t": "AEM.TO", "nd": 0.579, "confidence": "sparse", "p945": 297.0}]
    shorts = [{"t": "TD.TO", "nd": 0.243, "confidence": "mid", "p945": 163.23},
              {"t": "MFC.TO", "nd": 0.293, "confidence": "mid", "p945": 59.0}]
    pair = {"long": {"pick": longs[0], "extra": [longs[1]], "sided": 0.57},
            "short": ({"status": "NONE", "note": "no qualified short"}
                      if short_status == "NONE"
                      else {"pick": shorts[0], "extra": [], "sided": 0.55})}
    return {"longs": longs, "shorts": shorts, "pair": pair,
            "live_record": {"pair_n": 70, "pair_hits": 34}}


def test_intraday_prints_its_own_record_next_to_the_picks():
    out, _ = brief.render_intraday(_res(), {}, shadow=False)
    assert "34/70" in out and "coin flip" in out


def test_intraday_explains_which_rival_the_pick_beat():
    out, _ = brief.render_intraday(_res(), {}, shadow=False)
    assert "chosen over AEM.TO" in out and "invalidated if" in out


def test_a_near_tie_is_called_arbitrary():
    r = _res()
    r["longs"][1]["nd"] = 0.230          # 0.007 from the pick
    out, _ = brief.render_intraday(r, {}, shadow=False)
    assert "near tie — treat as arbitrary" in out


def test_sector_concentration_is_named_on_the_side_that_has_it():
    cfg = {"peer_groups": {"financials": ["TD.TO", "MFC.TO"]}}
    out, _ = brief.render_intraday(_res(), cfg, shadow=False)
    assert "2 of this side's candidates are financials" in out


def test_a_missing_side_is_never_forced():
    out, note = brief.render_intraday(_res(short_status="NONE"), {}, shadow=False)
    assert "do not force one" in out
    assert "SU.TO" in note and "TD.TO" not in note


def test_shadow_mode_claims_no_capital():
    out, note = brief.render_intraday(_res(), {}, shadow=True)
    assert "NO capital" in out and "shadow" in note


def test_coverage_failure_blocks_the_board():
    out, note = brief.render_intraday({"coverage_fail": "only 9/21 names"},
                                      {}, shadow=False)
    assert "INSUFFICIENT COVERAGE" in out and "nothing" in note
