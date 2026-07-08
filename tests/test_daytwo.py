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


# ── AT A GLANCE / the_call (concise-output contract) ────────────────────────
def _cand2(tk, side_dir, edge, eod_p, trig=10.0, open_=9.9):
    r = {"ticker": tk, "eod_p": eod_p, "open": open_,
         "bull_trigger_level": trig, "bear_trigger_level": trig,
         "cls": {"edge": edge, "lenses": ["base_rate", "macro"],
                 "direction": side_dir, "tier": "Medium"}}
    return r


def test_the_call_picks_highest_edge_across_sides():
    sel = {"longs": [_cand2("L1", 1, 2.0, 0.60)],
           "shorts": [_cand2("S1", -1, 3.1, 0.40), _cand2("S2", -1, 1.0, 0.42)]}
    call = report.the_call(sel)
    assert call["pick"]["ticker"] == "S1" and call["side"] == "SHORT"


def test_the_call_none_when_empty():
    assert report.the_call({"longs": [], "shorts": []}) is None
