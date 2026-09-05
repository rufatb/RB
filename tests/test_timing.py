"""Day-89: entry time x hold duration, and the rule that stops a 35-cell grid
manufacturing a winner.

The failure this study exists to avoid is not subtle and it has already
happened once here. Day-39 raced entry times, found 09:50 at +0.1034%/leg, and
its own placebo's MEDIAN winner came in at +0.1212%. The best of many noisy
cells is high by construction. So every test below defends one rule:

    the statistic is BEST CELL vs the PLACEBO'S BEST CELL, never vs zero.
"""

import numpy as np
import pytest

import validate_timing as T


def cell(n_sessions=120, effect=0.0, sd=1.0, seed=0, per=4):
    rng = np.random.default_rng(seed)
    out = []
    for i in range(n_sessions):
        d = f"2026-{1 + i // 28:02d}-{1 + i % 28:02d}"
        for _ in range(per):
            out.append({"date": d, "t": "X", "side": "LONG", "hit": 1,
                        "rel": effect + rng.normal(0, sd)})
    return out


def grid(n_cells=35, effect=0.0, seed=0):
    return {f"c{i}": cell(effect=effect, seed=seed + i) for i in range(n_cells)}


# ── the placebo distribution itself ────────────────────────────────────────

def test_the_placebo_reports_a_positive_max_even_on_pure_noise():
    """THE POINT OF THE WHOLE STUDY. With 35 all-noise cells the best one is
    reliably above zero, so comparing a winner to zero proves nothing."""
    pb = T.placebo_max(grid(35, effect=0.0, seed=1), n=120)
    assert pb["p50"] > 0, "a 35-cell max should sit above zero on pure noise"
    assert pb["p95"] > pb["p50"]


def test_a_bigger_grid_produces_a_bigger_placebo_max():
    """More cells, more chances — the bar has to rise with the grid."""
    small = T.placebo_max(grid(5, seed=2), n=120)
    big = T.placebo_max(grid(40, seed=2), n=120)
    assert big["p95"] > small["p95"]


def test_the_placebo_needs_no_real_effect_to_be_computed():
    assert T.placebo_max(grid(6, effect=0.0, seed=3), n=60)


# ── the verdict enforces the rule ──────────────────────────────────────────

def _stat(mean, t=5.0, blocks=(0.1, 0.1, 0.1, 0.1)):
    return {"mean": mean, "t": t, "blocks": list(blocks)}


def test_a_winner_below_the_placebo_95th_is_REJECTED():
    """Day-39's exact case: a cell that looks strong against zero and is not
    strong against its own grid's noise."""
    pb = {"p50": 0.09, "p95": 0.12, "max": 0.20, "n": 200}
    v = T.verdict("entry 09:50", _stat(0.1034), pb)
    assert "REJECTED" in v
    assert "by chance" in v


def test_a_winner_above_the_placebo_but_below_t_fails():
    pb = {"p50": 0.02, "p95": 0.05, "max": 0.08, "n": 200}
    v = T.verdict("c1", _stat(0.30, t=1.4), pb)
    assert "FAILS the bar" in v


def test_a_winner_that_flips_sign_across_blocks_fails():
    pb = {"p50": 0.02, "p95": 0.05, "max": 0.08, "n": 200}
    v = T.verdict("c1", _stat(0.30, t=5.0, blocks=(0.4, -0.2, 0.3, 0.4)), pb)
    assert "FLIPS" in v


def test_only_all_three_together_pass():
    pb = {"p50": 0.02, "p95": 0.05, "max": 0.08, "n": 200}
    v = T.verdict("c1", _stat(0.30, t=5.0), pb)
    assert "CLEARS ALL THREE" in v


def test_no_placebo_means_no_winner_is_declared():
    """Refusing is the correct output when the control could not be built."""
    assert "NO PLACEBO" in T.verdict("c1", _stat(0.9), {})


# ── the panel must actually be re-cut, not reused ──────────────────────────

def bars(n_days=30, per_day=7, seed=0):
    import pandas as pd
    rng = np.random.default_rng(seed)
    idx, rows = [], []
    for d in range(n_days):
        day = pd.Timestamp("2026-03-02") + pd.Timedelta(days=d)
        for b in range(per_day):
            idx.append(day + pd.Timedelta(hours=9, minutes=30 + 60 * b))
            p = 100 + rng.normal(0, 1)
            rows.append({"Open": p, "High": p + 1, "Low": p - 1,
                         "Close": p + rng.normal(0, 0.3), "Volume": 1e5})
    return pd.DataFrame(rows, index=pd.DatetimeIndex(idx))


def test_moving_the_entry_moves_both_r0_and_r1():
    """Entry time changes what is KNOWN and what is left to capture. A cut
    that only moved one end would be measuring the clock, not the engine."""
    b = bars()
    a0 = T.session_rows(b, "X", 0, 5)
    a2 = T.session_rows(b, "X", 2, 5)
    assert len(a0) == len(a2)
    assert a0[0]["r0"] != a2[0]["r0"], "r0 did not move with the entry"
    assert a0[0]["r1"] != a2[0]["r1"], "r1 did not move with the entry"
    assert a0[0]["entry_px"] != a2[0]["entry_px"]


def test_the_volume_feature_accumulates_up_to_the_entry_bar():
    b = bars()
    assert (T.session_rows(b, "X", 3, 5)[0]["v15"]
            > T.session_rows(b, "X", 0, 5)[0]["v15"])


def test_a_session_with_too_few_bars_is_skipped():
    assert T.session_rows(bars(n_days=5, per_day=3), "X", 0, 5) == []


# ── cell statistics ────────────────────────────────────────────────────────

def test_a_cell_with_too_few_sessions_returns_no_mean():
    assert T.cell_stat(cell(n_sessions=5))["mean"] is None


def test_a_planted_effect_is_visible_in_a_cell():
    """Rule 4: the harness must be able to see a real effect."""
    s = T.cell_stat(cell(n_sessions=200, effect=0.5, seed=7))
    assert s["mean"] > 0.3 and abs(s["t"]) > 3


def test_the_contract_is_stated_in_the_source():
    flat = " ".join(open(T.__file__).read().split())
    assert "never against zero" in flat or "never vs zero" in flat
    assert "re-fitted at every entry" in flat.lower() or \
           "RE-FITTED AT EVERY ENTRY" in " ".join(open(T.__file__).read().split())
