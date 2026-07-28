"""
test_daytwentytwo.py — the day-22 changes:
  * equal-RISK leg weighting (the 2nd rule ever to pass the four-quarter bar)
  * the density-cutoff self-inclusion bug fix

Both are locked here because both are easy to "simplify" back into the bugs
they fix: equal-risk looks like an arbitrary complication until you know it
cut NET volatility in all four quarters, and the cutoff fix looks like a
pointless copy until you know the self-match biased every live density label.
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import r945


# ── equal-risk leg weighting ────────────────────────────────────────────────
def test_risk_weighting_gives_the_jumpier_leg_less_money():
    """Inverse-vol: the higher-volatility name must hold FEWER dollars, so one
    jumpy leg cannot dominate the book's P&L (day-22 adoption)."""
    picks = [{"last": 100.0, "vol": 1.0},      # calm
             {"last": 100.0, "vol": 2.0}]      # twice as jumpy
    r945.allocate_book(picks, equity=100_000, max_book_pct=50)
    assert picks[0]["alloc"] > picks[1]["alloc"]
    assert all(p["risk_weighted"] for p in picks)
    # 1/1 : 1/2 -> 2/3 : 1/3, both inside the 35/65 cap
    assert picks[0]["alloc"] / (picks[0]["alloc"] + picks[1]["alloc"]) > 0.6


def test_risk_weighting_respects_the_concentration_cap():
    """A wildly lopsided vol pair must still not become a single-name bet:
    no leg may exceed `weight_cap`'s ceiling (default 65% of the book)."""
    picks = [{"last": 100.0, "vol": 0.1}, {"last": 100.0, "vol": 9.0}]
    r945.allocate_book(picks, equity=100_000, max_book_pct=50, weight_cap=0.35)
    total = sum(p["alloc"] for p in picks)
    assert max(p["alloc"] for p in picks) / total <= 0.66


def test_risk_weighting_preserves_the_total_book_cap():
    """Weighting redistributes the book; it must never inflate it — the share
    counts ARE the risk model (day-13)."""
    picks = [{"last": 100.0, "vol": 1.0}, {"last": 40.0, "vol": 3.0}]
    r945.allocate_book(picks, equity=100_000, max_book_pct=50)
    assert sum(p["alloc"] for p in picks) <= 50_000


def test_equal_dollar_fallback_when_vols_missing_or_not_two_legs():
    """Back-compatible: no vols, or a leg count other than two (the only case
    validated), falls back to the shipped equal-dollar split."""
    picks = [{"last": 100.0}, {"last": 50.0}]
    r945.allocate_book(picks, equity=100_000, max_book_pct=50)
    assert not any(p["risk_weighted"] for p in picks)
    assert picks[0]["alloc"] == picks[1]["alloc"] == 25_000

    three = [{"last": 100.0, "vol": 1.0}, {"last": 100.0, "vol": 2.0},
             {"last": 100.0, "vol": 3.0}]
    r945.allocate_book(three, equity=90_000, max_book_pct=100)
    assert not any(p["risk_weighted"] for p in three)
    assert len({p["alloc"] for p in three}) == 1


def test_risk_weighting_can_be_disabled():
    picks = [{"last": 100.0, "vol": 1.0}, {"last": 100.0, "vol": 4.0}]
    r945.allocate_book(picks, equity=100_000, max_book_pct=50, risk_weight=False)
    assert picks[0]["alloc"] == picks[1]["alloc"]


def test_one_legged_day_still_halves_exposure():
    """Day-18 contract survives the day-22 change: a lone leg gets the standard
    per-leg size, the rest of the book stays in cash."""
    picks = [{"last": 60.70, "vol": 1.2}]
    r945.allocate_book(picks, equity=100_000, max_book_pct=50)
    assert picks[0]["alloc"] <= 25_000


# ── density-cutoff self-inclusion ───────────────────────────────────────────
def test_density_cutoff_excludes_the_row_from_its_own_neighbourhood():
    """A training row measured against a pool CONTAINING itself matches itself
    at distance 0, dragging its neighbour distance down (measured -2.4%). Live
    picks never match themselves, so the cutoffs must be built the same way."""
    rng = np.random.default_rng(0)
    n = 400
    train = pd.DataFrame({
        "r0": rng.normal(0, 1, n), "gap": rng.normal(0, 1, n),
        "vp": rng.normal(1, 0.3, n), "r1": rng.normal(0, 1, n)})
    row = train.iloc[7]
    feats = {f: row[f] for f in r945.FEATS}
    with_self = r945.knn_probability(train, feats)[2]
    without = r945.knn_probability(train.drop(index=7), feats)[2]
    assert with_self < without, "self-match must depress the neighbour distance"


# ── day-23: book-weighted ledger reporting ──────────────────────────────────
def test_book_weighted_return_uses_the_published_weights():
    """Day-23: the two legs are deliberately different sizes since day-22, so
    an equal-weighted capture stops describing the book. Reproduces day-23:
    equal-weighted -0.156%, book-weighted POSITIVE, because the calm winning
    leg held 65% of the money."""
    import ledger
    rows = [
        {"date": "2026-07-28", "ticker": "SLF.TO", "side": "LONG", "role": "pair",
         "weight": "0.6489", "r1": "0.987", "hit": "1", "confidence": "dense"},
        {"date": "2026-07-28", "ticker": "AEM.TO", "side": "SHORT", "role": "pair",
         "weight": "0.3481", "r1": "1.298", "hit": "0", "confidence": "sparse"},
    ]
    line = ledger.book_return_line(rows)
    assert "1 sessions" in line and "(1/1 positive)" in line
    # equal-weighted would be negative; book-weighted must be positive
    equal = (0.987 - 1.298) / 2
    booked = 0.6489 * 0.987 + 0.3481 * -1.298
    assert equal < 0 < booked


def test_book_weighted_line_is_honest_when_no_weights_recorded():
    import ledger
    rows = [{"date": "2026-07-01", "ticker": "X.TO", "side": "LONG",
             "role": "pair", "weight": "", "r1": "0.5", "hit": "1"}]
    assert "recording starts day-23" in ledger.book_return_line(rows)


def test_ledger_roundtrips_rows_written_before_the_weight_column():
    """Old rows have no `weight` key at all — save() must not raise."""
    import ledger, tempfile, os as _os
    fd, path = tempfile.mkstemp(suffix=".csv"); _os.close(fd)
    try:
        ledger.save([{"date": "2026-07-01", "ticker": "X.TO", "side": "LONG",
                      "p_sided": "0.58", "confidence": "dense", "p945": "10.0",
                      "role": "pair", "r1": "0.5", "hit": "1"}], path)
        back = ledger.load(path)
        assert back[0]["weight"] == ""
        assert back[0]["hit"] == "1"
    finally:
        _os.unlink(path)
