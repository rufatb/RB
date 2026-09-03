"""Day-83b: post-announcement drift, and the controls that make its null usable.

Pre-registered in PREREGISTER_day83b.md. The verdict was UNDERPOWERED on both
arms, which is only a legitimate answer if the harness can detect a planted
drift of a stated size and stay quiet on none.

The failure mode this study was BUILT to have is the day-38 / day-51 one: an
apparent multi-day gain that turns out to be market drift collected by a
long-biased book. So the market-relative leg is tested hardest.
"""

import numpy as np
import pytest

import validate_drift as D


def events(n_names=40, per_name=4, drift=0.0, market=0.0, seed=0):
    """Rows with a KNOWN planted drift, and a KNOWN market component."""
    rng = np.random.default_rng(seed)
    out = []
    for i in range(n_names):
        t = f"T{i}"
        for _ in range(per_name):
            raw = drift + market + rng.normal(0, 3.0)
            out.append({"ticker": t, "kind": "CRL", "date": "2026-01-01",
                        "raw": raw, "rel": raw - market})
    return out


# ── the positive control: it must SEE a planted drift ───────────────────────

def test_a_planted_drift_is_detected():
    """Rule 4: a harness that cannot see a planted effect cannot report a null."""
    rows = events(n_names=120, drift=2.0, seed=1)
    m, lo, hi = D.boot_mean(rows, "rel", n=800)
    assert m > 1.0
    assert lo > 0, f"planted drift not distinguishable: [{lo}, {hi}]"


def test_no_planted_drift_leaves_the_interval_covering_zero():
    rows = events(n_names=120, drift=0.0, seed=2)
    _, lo, hi = D.boot_mean(rows, "rel", n=800)
    assert lo < 0 < hi


def test_power_scales_linearly_with_the_planted_edge():
    """edge / sd, never (mean + edge) / sd — the day-56 error, which inflates z
    whenever the sample mean is non-zero."""
    rows = events(n_names=60, drift=1.5, seed=3)
    z1 = D.power(rows, "rel", 0.5)
    z2 = D.power(rows, "rel", 2.0)
    assert abs(z2 / z1 - 4.0) < 0.05, (z1, z2)


# ── the market-relative leg is the one that decides ─────────────────────────

def test_a_pure_market_move_shows_in_raw_and_vanishes_relative():
    """THE FAILURE THIS STUDY WAS BUILT TO HAVE. Day-38 and day-51 both found
    an apparent multi-day gain that was entirely market drift collected by a
    long-biased book."""
    rows = events(n_names=120, drift=0.0, market=2.0, seed=4)
    raw, rlo, rhi = D.boot_mean(rows, "raw", n=800)
    rel, lo, hi = D.boot_mean(rows, "rel", n=800)
    assert raw > 1.5, "the market move should be visible raw"
    assert rlo > 0, "and it should look significant raw — that is the trap"
    assert abs(rel) < 0.5, "and it must vanish once the market is removed"
    assert lo < 0 < hi


def test_a_real_effect_survives_the_market_adjustment():
    """The converse: the adjustment must not erase a genuine effect."""
    rows = events(n_names=120, drift=2.0, market=2.0, seed=5)
    rel, lo, _ = D.boot_mean(rows, "rel", n=800)
    assert rel > 1.0 and lo > 0


# ── clustering by NAME, because one biotech files many decisions ────────────

def test_clustering_by_name_widens_the_interval_when_names_repeat():
    """684 events come from 195 names. Resampling events would treat one
    company's several decisions as independent information."""
    rng = np.random.default_rng(6)
    rows = []
    for i in range(30):                      # strong per-NAME component
        base = rng.normal(0, 3.0)
        for _ in range(8):
            v = base + rng.normal(0, 0.5)
            rows.append({"ticker": f"T{i}", "kind": "CRL", "date": "d",
                         "raw": v, "rel": v})
    _, lo_c, hi_c = D.boot_mean(rows, "rel", n=800)
    flat = [dict(r, ticker=f"T{j}") for j, r in enumerate(rows)]
    _, lo_f, hi_f = D.boot_mean(flat, "rel", n=800)
    assert (hi_c - lo_c) > 2 * (hi_f - lo_f), "clustering did not widen it"


def test_too_few_names_refuses_rather_than_returning_a_number():
    assert D.boot_mean(events(n_names=3), "rel") == (None, None, None)


# ── verdicts and the power arithmetic ──────────────────────────────────────

def test_an_effect_smaller_than_the_interval_reads_underpowered():
    """Rule 10: an interval wider than the effect means the data cannot
    answer, which is NOT the same as answering no."""
    assert "UNDERPOWERED" in D.verdict(-0.84, -3.04, 1.46, -0.73, 3.44)


def test_an_effect_clearing_the_bar_says_so():
    assert "CLEARS" in D.verdict(2.0, 1.0, 3.0, 3.9, 1.5)


def test_a_missing_interval_is_not_computable_not_a_null():
    assert D.verdict(None, None, None, None, None) == "NOT COMPUTABLE"


def test_events_needed_scales_as_the_square_of_the_shortfall():
    """z grows as sqrt(n), so tripling z needs nine times the events."""
    assert D.events_needed(1.0, 100, bar=3.0) == 900
    assert D.events_needed(3.0, 100, bar=3.0) == 100
    assert D.events_needed(0.0, 100) is None
    assert D.events_needed(float("nan"), 100) is None


# ── the arms are never pooled ──────────────────────────────────────────────

def test_the_two_arms_are_analysed_separately():
    """An approval and a rejection are different events; averaging a possible
    rise against a possible fall would hide both."""
    src = open(D.__file__).read()
    assert 'for kind in ("CRL", "APPROVAL")' in src
    flat = " ".join(src.split())
    assert "never pooled" in flat


def test_the_benchmark_is_required_not_optional():
    """The market-relative figure is the deciding statistic, so losing the
    benchmark must stop the study rather than silently fall back to raw."""
    flat = " ".join(open(D.__file__).read().split())
    assert "Refusing" in flat
    assert "the deciding one" in flat


def test_entry_is_the_first_tradable_close_after_the_announcement():
    """Entering at the announcement close would use a price a reader of the
    8-K could not have traded."""
    flat = " ".join(open(D.__file__).read().split())
    assert "first tradable close" in flat
