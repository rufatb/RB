"""
test_daytwelve.py — day-12 close lesson: the engine predicts the destination,
not the road. Both live legs swung ~1% against correct/near-correct calls
before finishing (CNQ dipped -1.3% then closed flat; CP popped +0.5% against
the short then paid). Encoded: per-session max adverse excursion after the
9:45 entry (session_rows mae_dn/mae_up) pooled into printed path
expectations on each pair leg, so a normal mid-day swing reads as normal.
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import r945


def _day_bars(closes, lows=None, highs=None, start="2026-07-10 09:30",
              volume=1000):
    idx = pd.date_range(start, periods=len(closes), freq="5min",
                        tz="America/Toronto")
    closes = np.asarray(closes, dtype=float)
    return pd.DataFrame({
        "Open": closes, "Close": closes,
        "Low": np.asarray(lows, dtype=float) if lows is not None else closes,
        "High": np.asarray(highs, dtype=float) if highs is not None else closes,
        "Volume": [volume] * len(closes)}, index=idx)


def test_session_rows_mae_measures_post_945_extremes():
    # 12 bars; p945 = bar index 2 close = 100. After 9:45 the low touches 98.7
    # (-1.3%, the live CNQ shape) and the high touches 100.5 (+0.5%).
    closes = [100, 100, 100, 99.5, 99.0, 98.8, 99.2, 99.8, 100.2, 100.4, 100.1, 100.0]
    lows = [100, 100, 100, 99.3, 98.9, 98.7, 99.0, 99.6, 100.0, 100.2, 100.0, 99.9]
    highs = [100, 100, 100, 99.7, 99.2, 99.0, 99.5, 100.0, 100.4, 100.5, 100.3, 100.1]
    rows = r945.session_rows(_day_bars(closes, lows, highs), "X.TO")
    assert len(rows) == 1
    r = rows[0]
    assert r["mae_dn"] == pytest.approx(-1.3, abs=0.01)   # worst dip after 9:45
    assert r["mae_up"] == pytest.approx(0.5, abs=0.01)    # worst pop after 9:45
    assert r["r1"] == pytest.approx(0.0, abs=0.01)        # destination: flat


def test_session_rows_mae_ignores_pre_945_extremes():
    # A wild 9:30-9:45 range must not contaminate the post-entry excursion.
    closes = [100.0] * 12
    lows = [95.0, 96.0, 100.0] + [99.8] * 9
    highs = [105.0, 104.0, 100.0] + [100.2] * 9
    r = r945.session_rows(_day_bars(closes, lows, highs), "X.TO")[0]
    assert r["mae_dn"] == pytest.approx(-0.2, abs=0.01)
    assert r["mae_up"] == pytest.approx(0.2, abs=0.01)


def test_render_prints_path_expectation_on_pair_legs(capsys):
    pick = {"t": "CNQ.TO", "p_up": 0.59, "nd": 0.4, "confidence": "dense",
            "p945": 60.21, "last": 60.18, "r0": 0.22, "gap": 0.18,
            "shares": 415, "alloc": 24975.0, "adverse_2pct": 500.0}
    res = {"now": "2026-07-15T09:47:00", "n_names": 21, "longs": [pick],
           "shorts": [], "excluded": [], "min_p": 0.55, "too_early": False,
           "pair": r945.pair_of_day([pick], []),
           "late_min": 1.0, "stale_after_min": 20, "spent_drift_pct": 0.3,
           "max_chase_pct": 0.15,
           "path_stats": {"n": 1200, "long": (-0.62, -1.10), "short": (0.58, 1.05)}}
    r945.render(res, book=True)
    out = capsys.readouterr().out
    assert "normal swing AGAINST this leg" in out
    assert "-0.6%" in out and "-1.1%" in out and "hold to 3:55" in out


def test_render_omits_path_line_when_stats_unavailable(capsys):
    # Honesty rule: never fabricate — no stats, no line.
    pick = {"t": "CNQ.TO", "p_up": 0.59, "nd": 0.4, "confidence": "dense",
            "p945": 60.21, "last": 60.18, "r0": 0.22, "gap": 0.18,
            "shares": 415, "alloc": 24975.0, "adverse_2pct": 500.0}
    res = {"now": "2026-07-15T09:47:00", "n_names": 21, "longs": [pick],
           "shorts": [], "excluded": [], "min_p": 0.55, "too_early": False,
           "pair": r945.pair_of_day([pick], []),
           "late_min": 1.0, "stale_after_min": 20, "spent_drift_pct": 0.3,
           "max_chase_pct": 0.15, "path_stats": None}
    r945.render(res, book=True)
    assert "normal swing AGAINST" not in capsys.readouterr().out
