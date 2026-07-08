"""
test_dayfive.py — day-5 lessons: the morning presentation bar (CP case) and
the live trigger-hold checker (MFC case). Real numbers from live trading are
the regression cases.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import report
from confirm import hold_status


def _r(eod_p, tier):
    return {"eod_p": eod_p, "cls": {"tier": tier, "edge": 1, "lenses": ["base_rate"]}}


def test_cp_case_suppressed():
    # CP day-5: sided P 0.52, tier Low -> must NOT be presentable
    assert not report.presentable(_r(0.48, "Low"), "SHORT")


def test_mfc_case_presentable():
    # MFC day-5: P 0.61, tier Medium -> presentable (its prediction was right)
    assert report.presentable(_r(0.61, "Medium"), "LONG")


def test_bar_requires_both_p_and_tier():
    assert not report.presentable(_r(0.61, "Low"), "LONG")      # good P, no lens
    assert not report.presentable(_r(0.53, "Medium"), "LONG")   # lens, weak P
    assert not report.presentable(_r(None, "Medium"), "LONG")


def test_the_call_respects_bar():
    sel = {"longs": [_r(0.53, "Medium")], "shorts": [_r(0.48, "Low")]}
    assert report.the_call(sel) is None            # nothing presentable -> stand down


# ── hold_status: MFC's real day-5 pattern (poked 59.10 but never held) ──────
def test_broke_but_not_held_is_do_not_enter():
    closes = [58.9, 59.0, 59.12, 59.05, 58.98, 59.02]   # one poke above 59.10
    assert hold_status(closes, 59.10, "long") == "BROKE BUT NOT HELD"


def test_confirmed_requires_last_five_beyond():
    closes = [58.9, 59.12, 59.15, 59.13, 59.16, 59.2]   # last 5 all above
    assert hold_status(closes, 59.10, "long") == "CONFIRMED"


def test_not_broken():
    assert hold_status([58.9, 59.0, 59.05], 59.10, "long") == "NOT BROKEN"


def test_short_side_hold():
    closes = [125.3, 125.1, 125.0, 124.9, 124.95, 124.8]  # last 5 below 125.2
    assert hold_status(closes, 125.20, "short") == "CONFIRMED"
