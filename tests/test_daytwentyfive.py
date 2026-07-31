"""
test_daytwentyfive.py — the external-audit (day-25) correctness fixes.

Every test here corresponds to a confirmed audit finding. They exist because
each bug was SILENT: the tool printed a confident, well-formatted order while
the number underneath it was wrong.
"""

import datetime as dt
import sys
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import r945

TZ = "America/Toronto"
OPEN_T = dt.time(9, 30)


def _bars(times, tz=TZ, vol=1000.0):
    idx = pd.DatetimeIndex([pd.Timestamp(f"2026-07-30 {t}", tz=tz) for t in times])
    n = len(idx)
    return pd.DataFrame({"Open": [10.0] * n, "High": [10.5] * n, "Low": [9.5] * n,
                         "Close": [10.2] * n, "Volume": [vol] * n}, index=idx)


AFTER = dt.datetime(2026, 7, 30, 9, 47, tzinfo=ZoneInfo(TZ))


# ── C2: the three bars must BE the 09:30/09:35/09:40 bars ───────────────────
def test_valid_signal_bars_accepted():
    ok, why = r945.validate_signal_bars(_bars(["09:30", "09:35", "09:40"]),
                                        OPEN_T, TZ, AFTER)
    assert ok, why


def test_missing_opening_bar_is_rejected():
    """A halted/absent 09:30 bar shifts iloc[2] to 09:45 — the model would be
    fed a different bar than it was validated on, silently."""
    ok, why = r945.validate_signal_bars(_bars(["09:35", "09:40", "09:45"]),
                                        OPEN_T, TZ, AFTER)
    assert not ok and "09:30" in why


def test_gap_in_the_five_minute_grid_is_rejected():
    ok, why = r945.validate_signal_bars(_bars(["09:30", "09:35", "09:45"]),
                                        OPEN_T, TZ, AFTER)
    assert not ok and "not 5" in why


def test_in_progress_third_bar_is_rejected():
    """At 09:43 the 09:40 bar has not closed — its 'close' is the live price."""
    ok, why = r945.validate_signal_bars(
        _bars(["09:30", "09:35", "09:40"]), OPEN_T, TZ,
        dt.datetime(2026, 7, 30, 9, 43, tzinfo=ZoneInfo(TZ)))
    assert not ok and "IN PROGRESS" in why


def test_too_few_bars_and_corrupt_feed_rejected():
    assert not r945.validate_signal_bars(_bars(["09:30", "09:35"]), OPEN_T, TZ, AFTER)[0]
    bad = _bars(["09:30", "09:35", "09:40"])
    bad.loc[bad.index[1], "High"] = 1.0        # High < Low
    ok, why = r945.validate_signal_bars(bad, OPEN_T, TZ, AFTER)
    assert not ok and "High < Low" in why


# ── C8: a partial universe changes a cross-sectional bet ────────────────────
def test_coverage_gate_fails_closed_below_threshold():
    uni = [f"T{i}.TO" for i in range(21)]
    ok, msg = r945.coverage_ok(10, uni, {}, {"T3.TO": "HTTPError"}, 0.8)
    assert not ok and "48%" in msg and "T3.TO" in msg


def test_coverage_gate_passes_when_enough_names_survive():
    uni = [f"T{i}.TO" for i in range(21)]
    ok, msg = r945.coverage_ok(18, uni, {}, {}, 0.8)
    assert ok and "18/21" in msg


# ── C3: the no-chase bound is anchored to the decision price ────────────────
def test_fill_bound_is_measured_from_the_decision_print():
    """Locked because render() passed the LIVE price for months, so the bound
    drifted with the market and authorised an unbounded chase."""
    assert r945.fill_bound("LONG", 100.0, 0.05) == pytest.approx(100.05)
    assert r945.fill_bound("SHORT", 100.0, 0.05) == pytest.approx(99.95)


def test_default_chase_tolerance_is_below_the_measured_edge():
    """The old 0.15% default exceeded the entire +0.094%/leg pre-cost edge."""
    import inspect
    default = inspect.signature(r945.fill_bound).parameters["max_chase_pct"].default
    assert default <= 0.094 / 2


# ── Wilson intervals in the accountability header ───────────────────────────
def test_wilson_interval_matches_known_values():
    import ledger
    lo, hi = ledger.wilson(19, 43)          # today's short record
    assert 0.30 < lo < 0.32 and 0.58 < hi < 0.60
    assert lo <= 0.5 <= hi, "44% on n=43 must still contain a coin flip"


def test_wilson_is_safe_at_boundaries():
    import ledger
    assert ledger.wilson(0, 0) == (0.0, 1.0)
    lo, hi = ledger.wilson(0, 10)
    assert lo == 0.0 and 0 < hi < 1
    lo, hi = ledger.wilson(10, 10)
    assert hi == 1.0 and 0 < lo < 1


def test_live_summary_breaks_out_sides():
    """The aggregate hid it: 50% overall while shorts ran 44%."""
    import ledger
    rows = ([{"side": "LONG", "hit": "1", "role": "pair"}] * 6 +
            [{"side": "SHORT", "hit": "0", "role": "pair"}] * 6)
    s = ledger.live_summary(rows)
    assert s["long_n"] == 6 and s["long_hits"] == 6
    assert s["short_n"] == 6 and s["short_hits"] == 0
    assert s["all_hits"] / s["all_n"] == 0.5      # aggregate looks fine


# ── shadow (paper) mode ─────────────────────────────────────────────────────
def test_shadow_mode_prints_no_order_and_no_size(capsys):
    """A printed share count IS the instruction (day-25). Paper mode must
    remove the order line, not caption it."""
    import r945 as _r
    pick = {"t": "CM.TO", "p_up": 0.58, "nd": 0.4, "confidence": "mid",
            "p945": 166.97, "last": 167.00, "r0": 0.58, "gap": -0.03,
            "shares": 148, "alloc": 24716.0, "adverse_2pct": 494.0}
    res = {"now": "2026-08-03T09:47:00", "n_names": 21, "longs": [pick],
           "shorts": [], "excluded": [], "min_p": 0.55, "too_early": False,
           "pair": _r.pair_of_day([pick], []), "late_min": 1.0,
           "stale_after_min": 20, "spent_drift_pct": 0.3, "max_chase_pct": 0.04,
           "ready_at_iso": "2026-08-03T09:46:00", "entry_window_min": 10,
           "shadow": True}
    _r.render(res, book=True)
    out = capsys.readouterr().out
    assert "SHADOW" in out
    assert "BUY 148 sh" not in out and "SELL SHORT" not in out
    assert "148" not in out.split("SHADOW")[1][:200]


def test_live_mode_still_prints_the_order(capsys):
    """Guard against shadow mode silently disabling live trading."""
    import r945 as _r
    pick = {"t": "CM.TO", "p_up": 0.58, "nd": 0.4, "confidence": "mid",
            "p945": 166.97, "last": 167.00, "r0": 0.58, "gap": -0.03,
            "shares": 148, "alloc": 24716.0, "adverse_2pct": 494.0}
    res = {"now": "2026-08-03T09:47:00", "n_names": 21, "longs": [pick],
           "shorts": [], "excluded": [], "min_p": 0.55, "too_early": False,
           "pair": _r.pair_of_day([pick], []), "late_min": 1.0,
           "stale_after_min": 20, "spent_drift_pct": 0.3, "max_chase_pct": 0.04,
           "ready_at_iso": "2026-08-03T09:46:00", "entry_window_min": 10}
    _r.render(res, book=True)
    out = capsys.readouterr().out
    assert "BUY 148 sh" in out and "SHADOW" not in out
