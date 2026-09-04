"""Day-88: the earnings filter, and the exact control that validates it.

This study exists because earnings.py has said since day-53 that the benefit
of gating on earnings could not be measured. The thing that makes it
measurable now is not the sample size — it is that Item 2.02 timestamps give
an EXACT control rather than a statistical one:

    an announcement accepted after 16:00 cannot move a leg that is flat by
    15:55, so excluding those days must do NOTHING.

Every test below protects that control or the pairing it depends on.
"""

import numpy as np
import pytest

import validate_earnfilter as E


def legs(n_days=80, n_names=10, flagged=(), edge=0.0, seed=0,
         flag="in_window"):
    """Legs with a KNOWN effect planted on the flagged ones."""
    rng = np.random.default_rng(seed)
    out = []
    for d in range(n_days):
        date = f"2026-{1 + d // 28:02d}-{1 + d % 28:02d}"
        for i in range(n_names):
            t = f"T{i}"
            hit_flag = (date, t) in flagged
            rel = rng.normal(-edge if hit_flag else 0.0, 1.0)
            row = {"date": date, "t": t, "side": "LONG",
                   "hit": int(rel > 0), "capt": rel, "rel": rel,
                   "in_window": False, "after_close": False}
            row[flag] = hit_flag
            out.append(row)
    return out


def _flag_every_day(n_days=80, name="T0"):
    return {(f"2026-{1 + d // 28:02d}-{1 + d % 28:02d}", name)
            for d in range(n_days)}


# ── the pairing, which day-87 got wrong once already ───────────────────────

def test_the_comparison_is_paired_within_a_session():
    """The filter and the baseline share the same days. Comparing unpaired
    aggregates would measure the days, not the filter — the exact mistake the
    board-vs-pair figures made before they were paired."""
    f = _flag_every_day()
    g = E.paired_gap(legs(flagged=f, edge=3.0, seed=1), "in_window")
    assert len(g) == 80
    assert all(r["dropped"] == 1 for r in g)


def test_a_session_with_nothing_flagged_is_skipped():
    """No drop means no comparison to make — not a zero to average in."""
    assert E.paired_gap(legs(), "in_window") == []


def test_a_session_where_everything_is_flagged_is_skipped():
    """An empty remainder has no mean; it must not be counted as zero."""
    allf = {(f"2026-{1 + d // 28:02d}-{1 + d % 28:02d}", f"T{i}")
            for d in range(80) for i in range(10)}
    assert E.paired_gap(legs(flagged=allf), "in_window") == []


# ── the planted effect must be detected, and its sign must be right ────────

def test_removing_genuinely_worse_legs_raises_the_remainder():
    """Rule 4: the harness must SEE a real filter effect."""
    g = E.paired_gap(legs(flagged=_flag_every_day(), edge=4.0, seed=2),
                     "in_window")
    m, lo, hi = __import__("validate_us").boot(g, "gap", "date")
    assert m > 0 and lo > 0, f"planted filter effect not detected: {m} [{lo},{hi}]"


def test_removing_average_legs_does_nothing():
    g = E.paired_gap(legs(flagged=_flag_every_day(), edge=0.0, seed=3),
                     "in_window")
    _, lo, hi = __import__("validate_us").boot(g, "gap", "date")
    assert lo < 0 < hi


def test_removing_BETTER_legs_lowers_the_remainder():
    """The sign must track reality, not the hypothesis."""
    g = E.paired_gap(legs(flagged=_flag_every_day(), edge=-4.0, seed=4),
                     "in_window")
    m, _, hi = __import__("validate_us").boot(g, "gap", "date")
    assert m < 0 and hi < 0


# ── the placebo arm is the whole study ─────────────────────────────────────

def test_the_placebo_fires_when_dropping_after_close_days_moves_the_number():
    """THE FAILURE THIS STUDY WAS BUILT TO HAVE. If excluding announcements
    that land after the leg is flat changes anything, the study is measuring
    the act of dropping rows and H1 is void."""
    out = E.summarise(legs(flagged=_flag_every_day(), edge=4.0, seed=5,
                           flag="after_close"),
                      "after_close", "placebo", placebo=True)
    assert "PLACEBO FIRED" in out and "VOID" in out


def test_the_placebo_stays_silent_on_a_genuine_null():
    out = E.summarise(legs(flagged=_flag_every_day(), edge=0.0, seed=6,
                           flag="after_close"),
                      "after_close", "placebo", placebo=True)
    assert "placebo silent" in out
    assert "PLACEBO FIRED" not in out


def test_the_two_timing_classes_are_never_pooled():
    """BEFORE_OPEN can move the window; AFTER_CLOSE cannot. Pooling them
    would destroy the only exact control this study has."""
    assert set(E.IN_WINDOW) == {"BEFORE_OPEN", "IN_SESSION"}
    assert set(E.AFTER) == {"AFTER_CLOSE"}
    assert not set(E.IN_WINDOW) & set(E.AFTER)


def test_in_session_counts_as_inside_the_window():
    """An 11am announcement lands inside a 10:30->close leg."""
    assert "IN_SESSION" in E.IN_WINDOW


# ── reporting contracts ────────────────────────────────────────────────────

def test_the_dropped_legs_are_reported_not_just_the_remainder():
    """H1 can only improve if the dropped rows are genuinely worse. Reporting
    the remainder alone would hide whether that is true."""
    out = E.summarise(legs(flagged=_flag_every_day(), edge=4.0, seed=7),
                      "in_window", "H1")
    assert "dropped" in out and "kept" in out


def test_a_filter_that_drops_nothing_says_so_rather_than_reporting_zero():
    out = E.summarise(legs(), "in_window", "H1")
    assert "not testable" in out


def test_the_mechanism_caveat_is_in_the_source():
    flat = " ".join(open(E.__file__).read().split())
    assert "MECHANISM sample" in flat
    assert "10:30" in flat


def test_the_control_is_described_as_exact_not_statistical():
    flat = " ".join(open(E.__file__).read().split())
    assert "EXACT, NOT STATISTICAL" in flat or "exact, not statistical" in flat
