"""
test_hold.py — the mid-session conditional hold-to-close check (hold.py).
Key property: the conditional uses only days that actually visited the level,
and today's in-progress bar is excluded (its close is the future = lookahead).
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import hold


def _frame(rows):
    df = pd.DataFrame(rows, columns=["Open", "High", "Low", "Close"])
    df["Volume"] = 1000
    df.index = pd.bdate_range("2024-01-01", periods=len(df))
    return df


def test_conditional_counts_only_visiting_days():
    # Level = 99% of open. Day A visits (low 98) and closes above level (100.5);
    # day B visits and closes below (97); day C never visits (low 99.5).
    rows = [(100, 101, 98.0, 100.5), (100, 101, 98.0, 97.0), (100, 101, 99.5, 100.2)] * 10
    s = hold.conditional_close_stats(_frame(rows), 0.99, below=True)
    assert s["available"] and s["n"] == 20            # day C excluded
    assert s["p_close_above_here_raw"] == 50.0        # A above, B below
    assert s["p_close_above_open"] == 50.0            # A closed above open, B didn't


def test_conditional_thin_sample_refused():
    rows = [(100, 101, 98.0, 100.5)] * 5
    s = hold.conditional_close_stats(_frame(rows), 0.99, below=True)
    assert not s["available"] and "20" in s["reason"]


def test_runup_side_uses_high():
    # For a short underwater (price ABOVE open), condition on HIGH visits.
    rows = [(100, 102.0, 99.0, 101.5), (100, 102.0, 99.0, 99.5)] * 12
    s = hold.conditional_close_stats(_frame(rows), 1.01, below=False)
    assert s["available"] and s["n"] == 24
    assert s["p_close_above_here_raw"] == 50.0
