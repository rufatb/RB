"""
test_dayeleven.py — day-11 lesson: a LATE run is a different bet. The engine
was run at 10:35 (49 min past the window); its long leg had already moved
+0.66% past the 9:45 print while a fresh 10:30-decision read qualified NO
longs at all. Encoded: late_minutes + per-leg drift verdicts and the LATE
RUN banner (r945), thresholds in config (pair.stale_after_min /
pair.spent_drift_pct).
"""

import datetime as dt
import sys
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import r945

TZ = ZoneInfo("America/Toronto")
OPEN = dt.time(9, 30)


def _at(h, m):
    return dt.datetime(2026, 7, 14, h, m, tzinfo=TZ)


def test_late_minutes_zero_at_946():
    assert r945.late_minutes(_at(9, 46), OPEN) == 0.0
    assert r945.late_minutes(_at(9, 50), OPEN) == 4.0
    assert r945.late_minutes(_at(10, 35), OPEN) == 49.0
    assert r945.late_minutes(_at(9, 40), OPEN) < 0     # early, not late


def test_leg_drift_long_spent_vs_better():
    # Day-11 exact case: CM long, print 166.97, last 168.08 -> +0.66% SPENT
    pct, verdict = r945.leg_drift("LONG", 166.97, 168.08)
    assert pct == pytest.approx(0.665, abs=0.01)
    assert "SPENT" in verdict
    # A long that pulled back below the print is a BETTER entry
    _, verdict2 = r945.leg_drift("LONG", 100.0, 99.80)
    assert "better" in verdict2


def test_leg_drift_short_direction_is_mirrored():
    # Short with price ABOVE the print = selling higher = better entry
    pct, verdict = r945.leg_drift("SHORT", 78.03, 78.25)
    assert pct > 0 and "better" in verdict
    # Short with price already fallen through the print = spent
    _, verdict2 = r945.leg_drift("SHORT", 78.03, 77.70)
    assert "SPENT" in verdict2


def test_leg_drift_small_moves_are_unchanged():
    _, verdict = r945.leg_drift("LONG", 100.0, 100.02)
    assert "unchanged" in verdict
    # config can demand more drift before crying SPENT
    _, verdict2 = r945.leg_drift("LONG", 100.0, 100.4, spent_pct=0.5)
    assert "unchanged" in verdict2


def test_late_run_banner_printed(capsys):
    pick = {"t": "CM.TO", "p_up": 0.58, "nd": 0.4, "confidence": "mid",
            "p945": 166.97, "last": 168.08, "r0": 0.58, "gap": -0.03}
    res = {"now": "2026-07-14T10:35:00", "n_names": 21, "longs": [pick],
           "shorts": [], "excluded": [], "min_p": 0.55, "too_early": False,
           "pair": r945.pair_of_day([pick], []),
           "late_min": 49.0, "stale_after_min": 20, "spent_drift_pct": 0.3}
    r945.render(res)
    out = capsys.readouterr().out
    assert "LATE RUN" in out and "49 min" in out
    assert "SPENT" in out and "+0.66%" in out


def test_fill_bound_short_cp_exact_case():
    # Day-11 close: CP short decided at 128.98 (a winning call, close 128.54,
    # +0.34%) — but a fill AT 128.54 chased -0.34% and captured zero. The
    # bound at 0.15% is 128.79: a 128.54 fill is past it -> NO TRADE.
    bound = r945.fill_bound("SHORT", 128.98, 0.15)
    assert bound == pytest.approx(128.786, abs=0.01)
    assert 128.54 < bound                       # the bad fill violates the bound


def test_fill_bound_long_is_mirrored():
    bound = r945.fill_bound("LONG", 100.0, 0.15)
    assert bound == pytest.approx(100.15)
    assert 100.30 > bound                       # chasing up past the bound


def _res(late_min, book_shares=True):
    pick = {"t": "CM.TO", "p_up": 0.58, "nd": 0.4, "confidence": "mid",
            "p945": 166.97, "last": 167.00, "r0": 0.58, "gap": -0.03}
    if book_shares:
        pick.update({"shares": 148, "alloc": 24716.0, "adverse_2pct": 494.0})
    return {"now": "2026-07-14T10:35:00", "n_names": 21, "longs": [pick],
            "shorts": [], "excluded": [], "min_p": 0.55, "too_early": False,
            "pair": r945.pair_of_day([pick], []),
            "late_min": late_min, "stale_after_min": 20,
            "spent_drift_pct": 0.3, "max_chase_pct": 0.15}


def test_stale_board_prints_no_order_line(capsys):
    # Day-11 close: the CM long happened because "BUY 148 sh @ market now"
    # printed NEXT TO the stale warning. On a stale board the order line
    # must not exist at all.
    r945.render(_res(late_min=49.0), book=True)
    out = capsys.readouterr().out
    assert "NO ORDER" in out and "BUY 148 sh" not in out


def test_fresh_board_prints_order_with_fill_bound(capsys):
    r945.render(_res(late_min=1.0), book=True)
    out = capsys.readouterr().out
    assert "BUY 148 sh" in out
    assert "fill bound: ≤ 167.25" in out and "NO TRADE" in out


def test_on_time_run_has_no_banner(capsys):
    pick = {"t": "CM.TO", "p_up": 0.58, "nd": 0.4, "confidence": "mid",
            "p945": 166.97, "last": 167.00, "r0": 0.58, "gap": -0.03}
    res = {"now": "2026-07-14T09:47:00", "n_names": 21, "longs": [pick],
           "shorts": [], "excluded": [], "min_p": 0.55, "too_early": False,
           "pair": r945.pair_of_day([pick], []),
           "late_min": 1.0, "stale_after_min": 20, "spent_drift_pct": 0.3}
    r945.render(res)
    assert "LATE RUN" not in capsys.readouterr().out
