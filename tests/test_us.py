"""Day-85: five US strategies, and the controls that make their verdicts usable.

Pre-registered in PREREGISTER_day85.md. The failures this study was built to
have, and which are therefore tested hardest:

  1. SURVIVORSHIP flattering the loser side (H4). Day-32's one "finding" was a
     gap-down bounce that dissolved under three tests; those three tests are
     re-implemented here and must actually fire on planted faults.
  2. MARKET DRIFT read as selection. Day-18, day-38 and day-51 each found an
     apparent multi-day gain that was the tape.
  3. AN EVENT WINDOW that quietly includes the announcement it is predicting.
"""

import numpy as np
import pandas as pd
import pytest

import build_us as B
import validate_us as U


# ── the earnings feed: timing is the whole point ───────────────────────────

def test_announcement_timing_is_classified_not_lumped():
    """BEFORE_OPEN, IN_SESSION and AFTER_CLOSE move different windows."""
    assert B.classify_time("2026-01-29T07:30:00.000Z"[:19]) == "BEFORE_OPEN"
    assert B.classify_time("2026-01-29T11:00:00") == "IN_SESSION"
    assert B.classify_time("2026-01-29T16:31:00") == "AFTER_CLOSE"


def test_unparseable_timing_is_unknown_not_guessed():
    assert B.classify_time("not a date") == "UNKNOWN"


def test_the_boundaries_land_on_the_right_side():
    assert B.classify_time("2026-01-29T09:29:00") == "BEFORE_OPEN"
    assert B.classify_time("2026-01-29T09:30:00") == "IN_SESSION"
    assert B.classify_time("2026-01-29T15:59:00") == "IN_SESSION"
    assert B.classify_time("2026-01-29T16:00:00") == "AFTER_CLOSE"


# ── granularity: rule 9, verify what you GOT ───────────────────────────────

def test_weekly_bars_are_refused_when_daily_was_requested():
    """Day-72: Yahoo answers interval=1d with weekly bars and no error."""
    daily = pd.to_datetime([f"2026-01-{d:02d}" for d in range(1, 29)] * 2)
    weekly = pd.to_datetime(pd.date_range("2020-01-01", periods=60, freq="7D"))
    monthly = pd.to_datetime(pd.date_range("2020-01-01", periods=60, freq="30D"))
    assert B.is_daily(pd.DatetimeIndex(sorted(daily)))
    assert not B.is_daily(weekly)
    assert not B.is_daily(monthly)


def test_too_short_a_series_is_refused():
    assert not B.is_daily(pd.to_datetime(["2026-01-01", "2026-01-02"]))


# ── cost must erase an effect, never reverse it ────────────────────────────

def test_cost_moves_an_effect_toward_zero_and_stops():
    """The bug this replaced turned +0.016% gross into -0.034% net, which
    reads as a reversed edge rather than an erased one."""
    assert U.net_of_cost(0.016, 5.0) == 0.0
    assert U.net_of_cost(-0.016, 5.0) == 0.0
    assert U.net_of_cost(0.20, 5.0) == pytest.approx(0.15)
    assert U.net_of_cost(-0.20, 5.0) == pytest.approx(-0.15)
    assert U.net_of_cost(None, 5.0) is None


def test_an_effect_erased_by_cost_says_so():
    v = U.verdict(0.02, 0.015, 0.025, [0.02] * 4, None, None,
                  U.net_of_cost(0.02, 5.0))
    assert "ERASED by cost" in v


# ── the statistical machinery ──────────────────────────────────────────────

def rows(n=400, effect=0.0, sd=1.0, seed=0, cluster_size=1):
    rng = np.random.default_rng(seed)
    out = []
    for i in range(n):
        for _ in range(cluster_size):
            out.append({"date": f"d{i:04d}", "t": f"T{i % 40}",
                        "x": effect + rng.normal(0, sd)})
    return out


def test_a_planted_effect_is_detected():
    """Rule 4: a harness that cannot see a planted effect cannot report a null."""
    m, lo, hi = U.boot(rows(n=600, effect=0.4), "x", "date")
    assert m > 0.25 and lo > 0


def test_no_planted_effect_leaves_the_interval_covering_zero():
    _, lo, hi = U.boot(rows(n=600, effect=0.0, seed=2), "x", "date")
    assert lo < 0 < hi


def test_power_scales_linearly_with_the_planted_edge():
    """edge / sd, never (mean + edge) / sd — the day-56 error."""
    r = rows(n=400, effect=0.3, seed=3)
    z1, z2 = U.power(r, "x", "date", 0.25), U.power(r, "x", "date", 1.0)
    assert abs(z2 / z1 - 4.0) < 0.05


def test_clustering_by_name_widens_the_interval_when_names_repeat():
    """One issuer contributes many announcements; resampling events would
    treat those as independent information."""
    rng = np.random.default_rng(4)
    r = []
    for i in range(30):
        base = rng.normal(0, 3.0)
        for j in range(10):
            r.append({"t": f"T{i}", "date": f"d{i}_{j}",
                      "x": base + rng.normal(0, 0.3)})
    _, lo_n, hi_n = U.boot(r, "x", "t")
    _, lo_d, hi_d = U.boot(r, "x", "date")
    assert (hi_n - lo_n) > 2 * (hi_d - lo_d), "name clustering did not widen it"


def test_too_few_clusters_refuses_rather_than_returning_a_number():
    assert U.boot(rows(n=5), "x", "date") == (None, None, None)


def test_block_consistency_catches_a_sign_flip():
    assert U.consistent([0.1, 0.2, 0.3, 0.1])
    assert not U.consistent([0.1, -0.2, 0.3, 0.1])
    assert not U.consistent([])


def test_the_bar_needs_both_t_and_consistency():
    assert "FAILS block consistency" in U.verdict(
        1.0, 0.8, 1.2, [0.5, -0.5, 0.9, 0.4], None, None, 1.0)


def test_an_effect_inside_the_placebo_band_is_not_an_effect():
    assert "INSIDE the placebo band" in U.verdict(
        1.0, 0.8, 1.2, [0.9, 1.1, 1.0, 1.0], 0.5, 1.5, 1.0)


def test_a_small_effect_with_a_wide_interval_reads_underpowered():
    """Rule 10: cannot resolve is not the same as no effect."""
    assert "UNDERPOWERED" in U.verdict(
        0.01, -0.9, 0.9, [0.1] * 4, None, None, 0.0)


# ── the three dissolving tests must actually fire ──────────────────────────

def panel(n_names=60, n_days=120, effect=0.0, tail=False, beta=False,
          small_only=False, seed=0):
    """A synthetic panel with a PLANTED cross-sectional effect."""
    rng = np.random.default_rng(seed)
    rows_ = []
    for d in range(n_days):
        mkt = rng.normal(0, 1.0)
        for i in range(n_names):
            key = rng.normal()
            e = effect
            if beta:
                e = effect * (1 if mkt > 0 else -1)
            if small_only:
                # Day-32's actual signature: the effect lives in the smallest
                # liquidity quartile and is OUTRIGHT NEGATIVE elsewhere. A
                # merely smaller effect in large caps still shares a sign and
                # is not what that test was written to catch.
                e = effect if i < n_names // 4 else -effect
            fwd = -key * e + mkt + rng.normal(0, 1.0)
            if tail and rng.random() < 0.02:
                fwd += -key * 40.0
            rows_.append({"t": f"T{i}", "date": f"2026-{1 + d // 28:02d}-"
                                                f"{1 + d % 28:02d}",
                          "key": key, "rel5": fwd, "close": 100.0,
                          "volume": 1e6 * (1 + i), "daily": mkt})
    df = pd.DataFrame(rows_)
    df["rel5"] = df["rel5"] - df.groupby("date")["rel5"].transform("mean")
    return df


def test_the_tail_test_flags_an_effect_carried_by_a_few_outliers():
    """Day-32: mean rel-10d +0.980% but MEDIAN +0.010%, win rate 49.9%."""
    out = U.dissolving_tests(panel(effect=0.0, tail=True, seed=5),
                             "key", 5, long_high=False)
    assert any("TAIL-CARRIED" in x for x in out), out


def test_the_beta_test_flags_an_effect_that_only_exists_on_down_days():
    """Day-32: the bounce was +1.105% on market-down days and -0.624% on up."""
    out = U.dissolving_tests(panel(effect=0.6, beta=True, seed=6),
                             "key", 5, long_high=False)
    assert any("BETA, NOT SELECTION" in x for x in out), out


def test_the_size_test_flags_an_effect_confined_to_one_liquidity_quartile():
    out = U.dissolving_tests(panel(n_names=160, effect=1.2, small_only=True,
                                   seed=7), "key", 5, long_high=False)
    assert any("NOT SIZE-ROBUST" in x for x in out), out


def test_a_clean_planted_effect_passes_all_three():
    # 160 names so each liquidity quartile still holds 40 — enough for a
    # decile sort. At 60 names the quartiles are too thin and the answer is
    # NOT COMPUTABLE, which the test below pins separately.
    out = U.dissolving_tests(panel(n_names=160, effect=0.8, seed=8),
                             "key", 5, long_high=False)
    assert any("not tail-carried" in x for x in out), out
    assert any("same sign" in x for x in out), out
    assert any(x.endswith("size-robust") for x in out), out


def test_a_thin_quartile_reads_not_computable_not_not_size_robust():
    """A data limit must never print as a negative finding. At 60 names each
    liquidity quartile holds 15, below the 30 a decile sort needs."""
    out = U.dissolving_tests(panel(n_names=60, effect=0.8, seed=8),
                             "key", 5, long_high=False)
    size = [x for x in out if x.startswith("size test")][0]
    assert "NOT COMPUTABLE" in size and "NOT SIZE-ROBUST" not in size


# ── the cross-sectional sort itself ────────────────────────────────────────

def test_the_decile_sort_recovers_a_planted_sign():
    r = U.decile_rows(panel(effect=1.0, seed=9), "key", 5, long_high=False)
    assert r and float(np.mean([x["spread"] for x in r])) > 0


def test_the_sort_direction_is_honoured():
    p = panel(effect=1.0, seed=10)
    lo = float(np.mean([x["spread"] for x in U.decile_rows(p, "key", 5, False)]))
    hi = float(np.mean([x["spread"] for x in U.decile_rows(p, "key", 5, True)]))
    assert np.sign(lo) != np.sign(hi), "long_high did not reverse the leg"


def test_a_thin_cross_section_is_skipped_not_averaged():
    """Fewer than 30 names on a date cannot support a decile sort."""
    p = panel(n_names=10, seed=11)
    assert U.decile_rows(p, "key", 5, long_high=False) == []


# ── contracts from the pre-registration ────────────────────────────────────

def test_the_h1_deviation_is_disclosed_in_the_source():
    """The registered protocol requires a market-relative statistic; H1 cannot
    have one. That must be stated, not silently applied."""
    flat = " ".join(open(U.__file__).read().split())
    assert "DISCLOSED DEVIATION" in flat
    assert "degenerate" in flat


def test_survivorship_direction_is_stated_per_arm():
    flat = " ".join(open(U.__file__).read().split())
    assert "survivorship" in flat.lower()
    assert "H4 ranks into" in flat


def test_in_session_announcements_are_excluded_not_guessed():
    """Daily bars cannot place an announcement that landed mid-session."""
    flat = " ".join(open(U.__file__).read().split())
    assert "IN_SESSION -> excluded" in flat or "IN_SESSION   -> excluded" in flat


def test_a_missing_panel_refuses_instead_of_defaulting():
    import os
    real = U.DATA
    try:
        U.DATA = "/nonexistent"
        with pytest.raises(FileNotFoundError):
            U.load_panel()
    finally:
        U.DATA = real
