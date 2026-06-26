"""
test_scan.py — the scanner's ranking honours the same honesty rules.

These test the pure ranking logic (no network): WAIT and unverified candidates
never lead, higher confluence/conviction ranks first, and "stand down" is the
result when nothing clears WAIT.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import scan


def _cand(ticker, verdict, p=0.5, conv="None", passed=True):
    return {"ticker": ticker, "verdict": verdict, "probability": p,
            "conviction": conv, "passed": passed}


def test_wait_and_unverified_never_lead():
    results = [
        _cand("AC.TO", "NO EDGE — WAIT", 0.50, "None"),
        _cand("RY.TO", "DATA NOT VERIFIED", passed=False),
        _cand("TD.TO", "BULL LEAN", 0.59, "Low"),
    ]
    r = scan.rank(results, "AC.TO")
    assert r["best"]["ticker"] == "TD.TO"
    assert all(c["verdict"] not in ("NO EDGE — WAIT", "DATA NOT VERIFIED")
               for c in r["leaders"])


def test_stand_down_when_all_wait():
    results = [
        _cand("AC.TO", "NO EDGE — WAIT"),
        _cand("RY.TO", "NO EDGE — WAIT"),
        _cand("TD.TO", "DATA NOT VERIFIED", passed=False),
    ]
    r = scan.rank(results, "AC.TO")
    assert r["best"] is None          # -> render prints STAND DOWN
    assert r["leaders"] == []


def test_higher_conviction_then_probability_distance_wins():
    results = [
        _cand("A", "BULL LEAN", 0.59, "Low"),
        _cand("B", "BEAR LEAN", 0.41, "Medium"),   # medium conviction outranks low
        _cand("C", "BULL LEAN", 0.56, "Low"),
    ]
    r = scan.rank(results, "A")
    assert r["best"]["ticker"] == "B"
    # within equal conviction, larger |p-0.5| ranks higher
    lows = [c for c in r["results"] if c["conviction"] == "Low"]
    assert lows[0]["ticker"] == "A"


def test_score_respects_clamp_inputs():
    # Even a maxed-out clamp (0.65) yields a finite, ordered score; nothing here
    # can express confidence above the cap because p is already clamped upstream.
    hi = scan._confidence_score(_cand("X", "BULL LEAN", 0.65, "Medium"))
    lo = scan._confidence_score(_cand("Y", "BULL LEAN", 0.55, "Low"))
    wait = scan._confidence_score(_cand("Z", "NO EDGE — WAIT", 0.50, "None"))
    assert hi > lo > 0 > wait
