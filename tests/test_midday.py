"""
test_midday.py — the gated midday selection. The key cases are TODAY'S REAL
NUMBERS: SHOP (54.3% from-here, 71.7% day-shape) must qualify as a stacked
long; MFC (46.8% from-here, 77.3% day-shape) must be REJECTED, not ranked.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from midday import midday_gate


def test_shop_case_stacked_long_qualifies():
    side, reason = midday_gate(54.3, 71.7)
    assert side == "long" and "stacked" in reason


def test_mfc_case_conflicted_short_rejected():
    side, reason = midday_gate(46.8, 77.3)
    assert side is None            # the day-3 lesson: no "best short" label here


def test_strong_from_here_alone_qualifies():
    assert midday_gate(58.0, None)[0] == "long"
    assert midday_gate(42.0, None)[0] == "short"


def test_strong_but_day_shape_contradicts_rejected():
    side, reason = midday_gate(56.0, 40.0)
    assert side is None and "conflict" in reason
    side, reason = midday_gate(44.0, 60.0)
    assert side is None and "conflict" in reason


def test_dead_zone_rejected():
    for p in (48.5, 50.0, 51.9):
        assert midday_gate(p, 70.0)[0] is None


def test_config_overrides():
    cfg = {"midday": {"strong_long": 60}}
    assert midday_gate(56.0, None, cfg)[0] is None     # stricter gate holds
