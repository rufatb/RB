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

def _todays(**over):
    rows = [{"ticker": "SLF.TO", "side": "LONG", "role": "pair",
             "leg": "primary", "weight": "0.2630", "shares": "120",
             "p945": "109.05", "p_sided": "0.56", "confidence": "sparse"},
            {"ticker": "TD.TO", "side": "LONG", "role": "pair", "leg": "extra",
             "weight": "0.2344", "shares": "70", "p945": "120.00",
             "p_sided": "0.54", "confidence": "dense"},
            {"ticker": "CP.TO", "side": "SHORT", "role": "pair",
             "leg": "primary", "weight": "0.2256", "shares": "91",
             "p945": "123.09", "p_sided": "0.57", "confidence": "dense"}]
    for r in rows:
        r.update(over)
    return rows


def test_a_re_read_shows_the_PUBLISHED_names_not_a_fresh_pick():
    """THE DEFECT. At 10:40 the board published SHORT CP.TO; at 10:43 the
    engine picked SHORT RY.TO and the page printed RY.TO -- a name the ledger
    will never score, because the board is written once and RY.TO is not on it.

    The 9:46 board is the instruction. A later run reads it back.
    """
    import r945
    res = {"pair": {"long": {"pick": {"t": "SLF.TO", "shares": 999}},
                    "short": {"pick": {"t": "RY.TO", "shares": 88}}}}
    picks = [res["pair"]["long"]["pick"], res["pair"]["short"]["pick"]]
    ok, note = r945._restore_published(res, picks, _todays(), 50000.0)
    assert ok and "exactly" in note
    assert res["pair"]["short"]["pick"]["t"] == "CP.TO", "fresh pick survived"
    assert res["pair"]["long"]["pick"]["shares"] == 120
    assert [p["t"] for p in picks] == ["SLF.TO", "CP.TO"]


def test_the_second_leg_is_restored_as_an_extra_not_as_the_instruction():
    import r945
    res = {"pair": {}}
    ok, _ = r945._restore_published(res, [], _todays(), 50000.0)
    assert res["pair"]["long"]["pick"]["t"] == "SLF.TO"
    assert [e["t"] for e in res["pair"]["long"]["extra"]] == ["TD.TO"]


def test_a_side_absent_from_the_board_restores_as_none():
    """A board with no short leg must not acquire one on a re-read."""
    import r945
    res = {"pair": {"short": {"pick": {"t": "RY.TO", "shares": 88}}}}
    rows = [r for r in _todays() if r["side"] == "LONG"]
    r945._restore_published(res, [], rows, 50000.0)
    assert res["pair"]["short"]["pick"] is None
    assert res["pair"]["short"]["status"] == "NONE"


def test_a_pre_day81_board_re_derives_and_says_so():
    """Rows without `shares`/`leg`: the allocation is exact, the share count is
    not (the original divisor was the live price at publish and is gone), and
    the primary leg is inferred from ledger order."""
    import r945
    rows = _todays()
    for r in rows:
        r["shares"], r["leg"] = "", ""
    res = {"pair": {}}
    ok, note = r945._restore_published(res, [], rows, 50000.0)
    assert ok and "predates day-81" in note and "inferred" in note
    assert res["pair"]["long"]["pick"]["t"] == "SLF.TO"      # ledger order
    assert res["pair"]["long"]["pick"]["shares"] == int(0.2630 * 50000 // 109.05)


def test_a_board_with_no_pair_legs_restores_nothing_and_says_so():
    import r945
    res = {"pair": {"long": {"pick": {"t": "X", "shares": 1}}}}
    ok, note = r945._restore_published(res, [], [], 50000.0)
    assert not ok and "no pair legs" in note


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


# ── day-88: H2 needs the ALTERNATIVES' spreads, not just the chosen legs' ──

def test_spreads_are_measured_for_every_qualified_name(monkeypatch, tmp_path):
    """REGRESSION. From day-82 to day-88 `publish` costed only the pair legs,
    so day-82's H2 -- the chosen leg's spread minus the cheapest qualified
    alternative's -- could never be computed however many sessions accrued.
    The data collection has to match the registered question."""
    import r945 as R
    asked = {}

    class _FakeCost:
        @staticmethod
        def assess(rows):
            asked["tickers"] = {r["ticker"] for r in rows}
            return [{"ticker": r["ticker"], "cost": {"bps": 5.0}} for r in rows]

    import sys as _s
    monkeypatch.setitem(_s.modules, "cost", _FakeCost)
    monkeypatch.setitem(_s.modules, "ledger", _StubLedger(tmp_path))

    longs = [{"t": "ABX.TO", "p_up": 0.62, "p945": 40.0, "nd": 1.0},
             {"t": "AEM.TO", "p_up": 0.58, "p945": 290.0, "nd": 1.1}]
    shorts = [{"t": "SLF.TO", "p_up": 0.38, "p945": 111.0, "nd": 1.0},
              {"t": "CM.TO", "p_up": 0.36, "p945": 163.0, "nd": 1.2},
              {"t": "TD.TO", "p_up": 0.44, "p945": 169.0, "nd": 1.3}]
    res = {"now": "2026-09-07T09:46", "longs": longs, "shorts": shorts,
           "pair": {"long": {"pick": longs[0], "extra": []},
                    "short": {"pick": shorts[0], "extra": [shorts[1]]}}}
    R.publish(res, {"risk": {"account_equity": 25000, "max_position_pct": 50},
                    "pair": {}})
    assert asked["tickers"] == {"ABX.TO", "AEM.TO", "SLF.TO", "CM.TO", "TD.TO"}, \
        f"only costed {asked['tickers']} — the alternatives were skipped"


class _StubLedger:
    """Captures the rows publish would write, without touching the real file."""
    FIELDS = ["date", "ticker", "side", "p_sided", "confidence", "p945",
              "role", "leg", "weight", "shares", "spread_bps", "r1", "hit"]

    def __init__(self, tmp):
        self.rows = []
        self.tmp = tmp

    def load(self, *a, **k):
        return []

    def append_picks(self, rows, *a, **k):
        self.rows.extend(rows)
        return len(rows)

    def append_universe_prints(self, *a, **k):
        return 0
