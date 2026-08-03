"""
test_daytwentysix.py — the holiday-calendar fix.

Day-26: `is_trading_day` depended on the OPTIONAL pandas_market_calendars.
Where it was not installed the except-branch returned True for every weekday,
so the Civic Holiday (2026-08-03) reported as a trading day. A safety check
must not be one `pip install` away from silently returning the unsafe answer.
"""

import datetime as dt
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import dashboard


def test_civic_holiday_is_not_a_trading_day():
    """The day this was found: Monday 2026-08-03, TSX closed."""
    assert dt.date(2026, 8, 3) in dashboard.tsx_holidays(2026)


def test_known_2026_tsx_closures():
    h = dashboard.tsx_holidays(2026)
    for d in [(1, 1), (2, 16), (4, 3), (5, 18), (7, 1),
              (8, 3), (9, 7), (10, 12), (12, 25), (12, 28)]:
        assert dt.date(2026, *d) in h, f"2026-{d[0]:02d}-{d[1]:02d} should be a holiday"
    assert dt.date(2026, 8, 4) not in h          # the next session IS open


def test_weekend_statutory_days_observe_forward():
    """Canada Day 2029 falls on a Sunday -> observed Monday the 2nd."""
    assert dt.date(2029, 7, 2) in dashboard.tsx_holidays(2029)


def test_christmas_and_boxing_day_never_collide():
    for year in range(2024, 2035):
        h = dashboard.tsx_holidays(year)
        dec = sorted(d for d in h if d.month == 12)
        assert len(dec) == len(set(dec)) == 2, f"{year}: {dec}"


def test_good_friday_is_a_friday_before_easter():
    for year in (2024, 2025, 2026, 2027):
        gf = [d for d in dashboard.tsx_holidays(year) if d.weekday() == 4 and d.month in (3, 4)]
        assert gf, f"{year} has no Good Friday"


def test_fallback_path_rejects_a_holiday_without_the_optional_package(monkeypatch):
    """Simulate the machine where the package is missing."""
    import builtins
    real = builtins.__import__

    def blocked(name, *a, **k):
        if name == "pandas_market_calendars":
            raise ImportError("simulated: not installed")
        return real(name, *a, **k)

    monkeypatch.setattr(builtins, "__import__", blocked)
    assert dashboard.is_trading_day(dt.date(2026, 8, 3), "TSX") is False
    assert dashboard.is_trading_day(dt.date(2026, 8, 4), "TSX") is True
    assert dashboard.is_trading_day(dt.date(2026, 8, 1), "TSX") is False   # Saturday


# ── extrapolation guard (day-26) ────────────────────────────────────────────
import numpy as np
import pandas as pd

import r945


def _pool(n=400, seed=0):
    rng = np.random.default_rng(seed)
    return pd.DataFrame({"r0": rng.normal(0, 0.5, n), "gap": rng.normal(0, 0.8, n),
                         "vp": rng.normal(1, 0.2, n), "r1": rng.normal(0, 1, n)})


def test_extreme_gap_is_refused_not_predicted():
    """Tomorrow's real case: Telus's US line closed -12.58% on the TSX holiday,
    so T.TO gaps far beyond anything the 60-day pool contains. k-NN would
    happily return a confident P for a setup it has never seen."""
    tr = _pool()
    ok, why = r945.extrapolation_check(tr, {"r0": 0.1, "gap": -12.6, "vp": 1.0})
    assert not ok and "gap=-12.60" in why and "extrapolating" in why


def test_ordinary_setup_passes():
    tr = _pool()
    ok, why = r945.extrapolation_check(tr, {"r0": 0.1, "gap": 0.3, "vp": 1.0})
    assert ok and why == "ok"


def test_each_feature_is_checked():
    tr = _pool()
    for feat, val in (("r0", 99.0), ("vp", -5.0)):
        row = {"r0": 0.1, "gap": 0.3, "vp": 1.0}
        row[feat] = val
        ok, why = r945.extrapolation_check(tr, row)
        assert not ok and why.startswith(feat)


def test_guard_is_inert_on_a_thin_pool():
    """With too little history the range is meaningless — do not fabricate a
    bound; the min-train check downstream already refuses."""
    ok, _ = r945.extrapolation_check(_pool(n=50), {"r0": 0, "gap": -99, "vp": 1})
    assert ok
