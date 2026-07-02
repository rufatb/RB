"""
test_daytwo.py — day-2 lessons: macro-lens concentration detection and the
hold.py macro-drift surface.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import report


def _pick(lenses):
    return {"cls": {"lenses": lenses}}


def test_macro_concentration_counts():
    picks = [_pick(["base_rate", "macro"]), _pick(["base_rate", "macro"]),
             _pick(["base_rate", "structure"])]
    n, total = report.macro_concentration(picks)
    assert (n, total) == (2, 3)


def test_macro_concentration_empty():
    assert report.macro_concentration([]) == (0, 0)


def test_concentration_warning_threshold():
    # >=50% macro-dependent should trip the warning condition used in render
    picks = [_pick(["base_rate", "macro"]), _pick(["base_rate", "macro"]),
             _pick(["base_rate"]), _pick(["base_rate", "macro"])]
    n, total = report.macro_concentration(picks)
    assert total >= 2 and n / total >= 0.5
