"""
test_r945.py — the 9:45→close engine: session-row extraction, no-leakage,
smoothing/clamp behavior of the pooled k-NN probability.
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import r945


def _bars(days=3, up=True):
    frames = []
    for i in range(days):
        idx = pd.date_range(f"2026-06-{10+i} 09:30", periods=78, freq="5min",
                            tz="America/Toronto")
        base = 100 + i
        drift = np.linspace(0, 1 if up else -1, 78)
        px = base + drift
        frames.append(pd.DataFrame({"Open": px, "High": px+0.1, "Low": px-0.1,
                                    "Close": px, "Volume": 1000}, index=idx))
    return pd.concat(frames)


def test_session_rows_extracts_features_and_outcome():
    rows = r945.session_rows(_bars(3), "X.TO")
    assert len(rows) == 3
    r = rows[1]
    assert r["gap"] is not None          # uses PRIOR session close
    assert "r0" in r and "r1" in r and r["v15"] > 0


def test_knn_probability_clamped_and_smoothed():
    rng = np.random.default_rng(1)
    n = 600
    train = pd.DataFrame({
        "r0": rng.normal(0, 0.5, n), "gap": rng.normal(0, 0.4, n),
        "vp": rng.uniform(0.5, 2, n),
        "r1": rng.normal(0, 0.5, n),
    })
    # force an extreme pocket: big ramps always fade in this synthetic world
    train.loc[train["r0"] > 0.5, "r1"] = -1.0
    p, ntr, nd = r945.knn_probability(train, {"r0": 1.0, "gap": 0.0, "vp": 1.0})
    assert ntr == n and p is not None
    assert 0.35 <= p <= 0.65            # hard clamp holds even on a pure pocket
    assert p < 0.5                       # learned the fade
    p2 = r945.knn_probability(train, {"r0": None, "gap": 0.0, "vp": 1.0})[0]
    assert p2 is None                    # missing feature -> no fabricated call


def test_knn_refuses_thin_history():
    train = pd.DataFrame({"r0": [0.1]*50, "gap": [0.0]*50, "vp": [1.0]*50,
                          "r1": [0.2]*50})
    p = r945.knn_probability(train, {"r0": 0.1, "gap": 0.0, "vp": 1.0})[0]
    assert p is None                     # <200 rows: not enough to condition on


def test_allocate_book_equal_weight_and_capped():
    picks = [{"last": 100.0}, {"last": 50.0}, {"last": 25.0}]
    r945.allocate_book(picks, equity=100_000, max_book_pct=50)
    total = sum(p["alloc"] for p in picks)
    assert total <= 50_000                       # book cap holds
    assert picks[0]["shares"] == 166             # 16,666 / 100
    assert picks[1]["shares"] == 333
    # equal allocation intent: each ≈ 16.7k
    assert all(abs(p["alloc"] - 16_666) < p["last"] + 1 for p in picks)


def test_allocate_book_empty_safe():
    assert r945.allocate_book([], 100_000, 50) == []


def test_knn_returns_neighbour_distance():
    import numpy as np, pandas as pd
    rng = np.random.default_rng(2)
    train = pd.DataFrame({"r0": rng.normal(0,1,300), "gap": rng.normal(0,1,300),
                          "vp": rng.uniform(0.5,2,300), "r1": rng.normal(0,1,300)})
    p, n, nd = r945.knn_probability(train, {"r0": 0.0, "gap": 0.0, "vp": 1.0})
    assert p is not None and nd > 0


def test_density_label():
    assert r945.density_label(0.1, (0.5, 1.0)) == "dense"
    assert r945.density_label(0.7, (0.5, 1.0)) == "mid"
    assert r945.density_label(2.0, (0.5, 1.0)) == "sparse"


# ── day-81: a re-read must restore the published board, never re-size ───────

def test_restore_puts_the_published_shares_back_on_the_picks():
    """The record is authoritative; the live tape is not."""
    import r945
    picks = [{"t": "SU.TO", "shares": 136, "alloc": 12625},
             {"t": "BMO.TO", "shares": 55, "alloc": 13041}]
    todays = [{"ticker": "SU.TO", "weight": "0.2523", "p945": "93.3600",
               "shares": "135"},
              {"ticker": "BMO.TO", "weight": "0.2608", "p945": "239.0400",
               "shares": "55"}]
    ok, note = r945._restore_published(picks, todays, 50000.0)
    assert ok and "exactly" in note
    assert picks[0]["shares"] == 135, "the re-computation must not survive"
    assert picks[0]["alloc"] == round(0.2523 * 50000)


def test_a_pre_day81_board_re_derives_shares_and_says_so():
    """Rows written before day-81 carry weight but no share count.

    The ALLOCATION is exact; the divisor the original board used was the live
    price at publish and is gone. That is stated, not papered over.
    """
    import r945
    picks = [{"t": "SU.TO", "shares": 136, "alloc": 12625}]
    todays = [{"ticker": "SU.TO", "weight": "0.2523", "p945": "93.3600",
               "shares": ""}]
    ok, note = r945._restore_published(picks, todays, 50000.0)
    assert ok and "re-derived" in note
    assert picks[0]["shares"] == 135


def test_a_leg_absent_from_the_record_is_blanked_not_left_stale():
    """Rule 2: fail closed. A blank is honest, a wrong size is not."""
    import r945
    picks = [{"t": "GHOST.TO", "shares": 999, "alloc": 99999}]
    ok, note = r945._restore_published(picks, [], 50000.0)
    assert not ok and "could not be restored" in note
    assert picks[0]["shares"] is None and picks[0]["alloc"] is None


def test_shares_survive_a_write_and_read(tmp_path):
    """SCHEMA IS NOT BEHAVIOUR, and asserting the former missed the bug.

    The first version of this test checked `"shares" in ledger.FIELDS`. That
    passed while `append_picks` -- which builds its row dict key by key --
    dropped the value, so the header carried a column that was never once
    populated and the very next board published without it. Round-trip it.
    """
    import ledger
    p = str(tmp_path / "ledger.csv")
    ledger.append_picks([{"ticker": "SU.TO", "side": "LONG", "p_sided": 0.556,
                          "confidence": "sparse", "p945": 93.36,
                          "role": "pair", "weight": 0.2523, "shares": 135}],
                        "2026-09-01", p)
    back = ledger.load(p)[0]
    assert back["shares"] == "135"


def test_a_board_row_without_shares_writes_blank_not_none(tmp_path):
    """'None' as text would parse back as a size. Blank is the honest value."""
    import ledger
    p = str(tmp_path / "ledger.csv")
    ledger.append_picks([{"ticker": "X.TO", "side": "LONG", "p_sided": 0.51,
                          "confidence": "n/a", "p945": 10.0, "role": "board",
                          "weight": None, "shares": None}], "2026-09-01", p)
    assert ledger.load(p)[0]["shares"] == ""
