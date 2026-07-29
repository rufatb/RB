"""
test_daytwentyfour.py — day-24 fixes:
  * ledger refuses to score a session that has not closed (the worst bug found
    so far: it wrote live mid-session prices into the permanent record)
  * sector warning is FRACTION-based so two-name groups are no longer invisible

Both are locked because both look like harmless simplifications in reverse: the
close guard looks like an unnecessary check, and the fraction rule looks
equivalent to the old count rule until you notice 6 of 21 names can never
reach a count of 3.
"""

import datetime as dt
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import ledger
import r945

GROUPS = {"telecom": ["BCE.TO", "T.TO"], "financials":
          ["RY.TO", "TD.TO", "BMO.TO", "BNS.TO", "CM.TO", "MFC.TO", "SLF.TO"]}


# ── the close guard ─────────────────────────────────────────────────────────
def test_session_is_final_boundaries():
    close = dt.time(16, 0)
    mid = dt.datetime(2026, 7, 29, 15, 5)
    assert not ledger.session_is_final("2026-07-29", mid, close)   # today, open
    assert ledger.session_is_final("2026-07-28", mid, close)       # yesterday
    assert not ledger.session_is_final("2026-07-30", mid, close)   # future
    after = dt.datetime(2026, 7, 29, 16, 0)
    assert ledger.session_is_final("2026-07-29", after, close)     # at the bell


def test_score_rows_refuses_to_write_mid_session_prices():
    """The day-24 bug, locked: scoring at 15:05 must hold the row back, not
    stamp a live price into the permanent record as an outcome."""
    rows = [{"date": "2026-07-29", "ticker": "ENB.TO", "side": "LONG",
             "p945": "78.36", "r1": "", "hit": ""}]
    rows, n, held = ledger.score_rows(
        rows, lambda t: 77.65, now=dt.datetime(2026, 7, 29, 15, 5))
    assert (n, held) == (0, 1)
    assert rows[0]["r1"] == "" and rows[0]["hit"] == ""
    # after the bell the same row scores normally
    rows, n, held = ledger.score_rows(
        rows, lambda t: 77.65, now=dt.datetime(2026, 7, 29, 16, 1))
    assert (n, held) == (1, 0) and rows[0]["hit"] == "0"


# ── fraction-based sector warning ───────────────────────────────────────────
def test_two_name_sector_fully_aligned_now_warns():
    """Day-15 and day-24 shape: BOTH telecoms qualified the same way. The old
    count rule needed 3 same-group picks, which a 2-name group can never
    reach, so this went unflagged twice."""
    shorts = [{"t": "BCE.TO"}, {"t": "T.TO"}]
    w = r945.sector_warning("BCE.TO", shorts, [], GROUPS)
    assert w and "ENTIRE telecom" in w and "2/2" in w
    assert "not a gate" in w.lower()


def test_partial_group_does_not_warn():
    shorts = [{"t": "BCE.TO"}]
    assert r945.sector_warning("BCE.TO", shorts, [], GROUPS) is None


def test_opposing_peer_cancels_the_full_alignment_warning():
    """If the other telecom is on the OTHER side the sector is not aligned."""
    assert r945.sector_warning("BCE.TO", [{"t": "BCE.TO"}], [{"t": "T.TO"}], GROUPS) is None


def test_large_group_count_rule_still_applies():
    longs = [{"t": x} for x in ("RY.TO", "TD.TO", "BMO.TO", "BNS.TO")]
    w = r945.sector_warning("RY.TO", longs, [], GROUPS)
    assert w and "3 other financials" in w


def test_group_alignment_counts():
    assert r945.group_alignment("BCE.TO", [{"t": "BCE.TO"}, {"t": "T.TO"}], [], GROUPS) == (2, 0, 2)
    assert r945.group_alignment("SHOP.TO", [{"t": "SHOP.TO"}], [], GROUPS) == (0, 0, 0)
