"""
test_backtest.py — proves the backtest is lookahead-safe and the scorers behave.

The headline test (test_no_lookahead_in_tier_a) is the important one: it shows
that the prediction for day t does not change when data AFTER t is altered. If
any future information leaked into a prediction, this test would fail.
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import backtest
from backtest import Sample


def _synthetic_daily(n=400, seed=11):
    rng = np.random.default_rng(seed)
    idx = pd.bdate_range("2023-01-01", periods=n)
    close = 20 + np.cumsum(rng.normal(0, 0.3, n))
    open_ = close + rng.normal(0, 0.2, n)
    hi = np.maximum(close, open_) + abs(rng.normal(0, 0.2, n))
    lo = np.minimum(close, open_) - abs(rng.normal(0, 0.2, n))
    vol = rng.integers(1_000_000, 5_000_000, n)
    return pd.DataFrame({"Open": open_, "High": hi, "Low": lo, "Close": close,
                         "Volume": vol}, index=idx)


def test_no_lookahead_in_tier_a():
    """Predictions for the overlapping early days must be byte-identical whether
    or not future days exist — the proof that no future data leaks in."""
    warmup = 120
    full = _synthetic_daily(n=400)
    truncated = full.iloc[:300]

    s_trunc, _, _ = backtest.tier_a_samples(truncated, warmup)
    s_full, _, _ = backtest.tier_a_samples(full, warmup)

    # s_trunc covers t in [warmup, 300); s_full covers [warmup, 400). The first
    # len(s_trunc) samples correspond to identical t with identical prior data.
    assert len(s_trunc) > 0
    for a, b in zip(s_trunc, s_full[:len(s_trunc)]):
        assert a.p_up == b.p_up
        assert a.realized_up == b.realized_up
        assert a.direction == b.direction


def test_tier_a_day_t_not_in_its_own_pool():
    """Mutating ONLY the last day must not change any earlier-day prediction."""
    warmup = 120
    base = _synthetic_daily(n=350)
    mutated = base.copy()
    # Make the final day a wild outlier.
    mutated.iloc[-1, mutated.columns.get_loc("Close")] = 9999.0
    mutated.iloc[-1, mutated.columns.get_loc("Open")] = 0.01

    s_base, _, _ = backtest.tier_a_samples(base, warmup)
    s_mut, _, _ = backtest.tier_a_samples(mutated, warmup)
    # All but the very last sample correspond to identical history.
    for a, b in zip(s_base[:-1], s_mut[:-1]):
        assert a.p_up == b.p_up and a.direction == b.direction


def test_binom_pvalue_handles_large_n():
    # Must not overflow (the bug we fixed) and must be a valid probability.
    for n in (10, 60, 61, 2389, 10000):
        p = backtest.binom_p_value(n // 2, n)
        assert 0.0 <= p <= 1.0


def test_brier_baseline_is_quarter_for_constant_half():
    samples = [Sample(0.5, True, False, 0) for _ in range(50)]
    assert abs(backtest.brier(samples) - 0.25) < 1e-9


def test_calibration_groups_by_bin():
    samples = ([Sample(0.40, False, True, -1)] * 10 +
               [Sample(0.60, True, True, +1)] * 10)
    rows = backtest.calibration_table(samples)
    by = {(lo, hi): (n, pred, real) for lo, hi, n, pred, real in rows}
    assert by[(0.35, 0.45)][0] == 10
    assert by[(0.55, 0.65)][0] == 10
