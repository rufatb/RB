"""
test_open_select.py — the once-at-open selection logic (base-rate-primary,
confirmation-gated). Validates the new primary strategy deterministically,
since live data can't be exercised on a holiday / off-hours.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import scan
import sentiment


def _cand(ticker, verdict="NO EDGE — WAIT", green=None, macro=0, sent=0,
          off=False, passed=True, p=0.5):
    return {"ticker": ticker, "verdict": verdict, "analog_green": green,
            "macro_dir": macro, "sentiment_dir": sent, "off_sample": off,
            "passed": passed, "probability": p}


# ── score_candidate: base rate sets direction ───────────────────────────────
def test_base_rate_sets_long_direction():
    c = _cand("X", green=70)  # 70% green -> long
    s = scan.score_candidate(c)
    assert s["direction"] == 1 and s["tier"] in ("Low", "Medium")


def test_base_rate_sets_short_direction():
    c = _cand("X", green=30)  # 30% green -> short
    s = scan.score_candidate(c)
    assert s["direction"] == -1


def test_neutral_base_rate_skipped():
    assert scan.score_candidate(_cand("X", green=50))["tier"] == "skip"


def test_no_base_rate_skipped():
    assert scan.score_candidate(_cand("X", green=None))["tier"] == "skip"


# ── Confirmations & conflicts (the CVE/SHOP lesson) ─────────────────────────
def test_confirmation_lifts_to_medium():
    # base rate long + macro confirms long -> Medium
    s = scan.score_candidate(_cand("X", green=70, macro=1))
    assert s["tier"] == "Medium" and "macro" in s["lenses"]


def test_base_rate_alone_is_low():
    s = scan.score_candidate(_cand("X", green=70))
    assert s["tier"] == "Low"


def test_net_opposition_excluded():
    # base rate long, but structure AND macro oppose -> conflict -> skip (CVE case)
    s = scan.score_candidate(_cand("X", green=70, verdict="BEAR LEAN", macro=-1))
    assert s["tier"] == "skip" and "conflict" in s["reason"]


def test_off_sample_excluded():
    s = scan.score_candidate(_cand("X", green=70, macro=1, off=True))
    assert s["tier"] == "skip" and "off-sample" in s["reason"]


def test_unverified_excluded():
    assert scan.score_candidate(_cand("X", green=70, passed=False))["tier"] == "skip"


def test_single_confirmation_offset_by_disagree_is_conflict():
    # 1 agree (macro), 1 disagree (structure) -> disagree>=agree -> skip
    s = scan.score_candidate(_cand("X", green=70, macro=1, verdict="BEAR LEAN"))
    assert s["tier"] == "skip"


# ── open_select splits and ranks (via monkeypatched universe) ───────────────
def test_open_select_splits_and_ranks(monkeypatch):
    fake = [
        _cand("LONGA", verdict="BULL LEAN", green=75, macro=1, p=0.59),   # strong long
        _cand("LONGB", green=58),                                          # weak long
        _cand("SHORTA", verdict="BEAR LEAN", green=28, macro=-1, p=0.41),  # strong short
        _cand("CONFL", green=70, verdict="BEAR LEAN", macro=-1),           # conflict -> out
        _cand("NEUT", green=50),                                           # neutral -> out
    ]
    monkeypatch.setattr(scan, "_evaluate_universe",
                        lambda *a, **k: (fake, {"crude_pct": None, "tsx_pct": None,
                                                "cad_pct": None, "vix_pct": None}, __import__("datetime").datetime(2026, 7, 2)))
    sel = scan.open_select({"ticker": "AC.TO"}, "yahoo_direct", None, top_n=3)
    longs = [r["ticker"] for r in sel["longs"]]
    shorts = [r["ticker"] for r in sel["shorts"]]
    assert longs[0] == "LONGA"          # strongest confluence ranks first
    assert "LONGB" in longs
    assert shorts == ["SHORTA"]
    assert "CONFL" not in longs + shorts and "NEUT" not in longs + shorts


# ── Sentiment lexicon (pure) ────────────────────────────────────────────────
def test_sentiment_scoring_pure():
    sc, pos, neg = sentiment._score_titles(["Company beats estimates, shares surge"])
    assert sc > 0 and pos >= 2
    sc2, _, neg2 = sentiment._score_titles(["Company misses, shares plunge on lawsuit"])
    assert sc2 < 0 and neg2 >= 2


def test_sentiment_dir_unavailable_is_zero():
    assert sentiment.sentiment_dir({"available": False}) == 0
    assert sentiment.sentiment_dir({"available": True, "score": 0.5}) == 1
    assert sentiment.sentiment_dir({"available": True, "score": -0.5}) == -1
