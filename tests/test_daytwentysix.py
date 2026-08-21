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


# ── day-28: relative (tide-removed) capture ─────────────────────────────────
def test_relative_capture_separates_selection_from_tape():
    """Day-28's exact case: RY 'HIT' absolutely (-0.404% on a -0.352% tide) but
    was a MEDIAN name contributing almost nothing market-neutral, while CP's
    +0.369% on that falling tide was a genuinely good pick."""
    import ledger
    tides = {"2026-08-05": -0.352}
    rows = [{"date": "2026-08-05", "side": "LONG", "r1": "0.369", "hit": "1"},
            {"date": "2026-08-05", "side": "SHORT", "r1": "-0.404", "hit": "1"},
            {"date": "2026-08-05", "side": "LONG", "r1": "0.369", "hit": "1"},
            {"date": "2026-08-05", "side": "SHORT", "r1": "-0.404", "hit": "1"}]
    line = ledger.relative_line(rows, tides)
    assert "relative capture" in line and "4 legs" in line
    # the long beat the tide by ~0.72; the short by only ~0.05
    assert abs((0.369 - -0.352) - 0.721) < 0.01
    assert abs(-(-0.404 - -0.352) - 0.052) < 0.01


def test_tide_needs_a_real_universe_not_the_picks():
    """A tide from <10 names is a selected sample — refuse it."""
    import ledger
    prints = [{"date": "2026-08-05", "ticker": f"T{i}.TO", "p945": "100"} for i in range(5)]
    assert ledger.tide_by_date(prints, lambda t, d: 101.0) == {}
    prints = [{"date": "2026-08-05", "ticker": f"T{i}.TO", "p945": "100"} for i in range(12)]
    assert ledger.tide_by_date(prints, lambda t, d: 101.0)["2026-08-05"] > 0.9


def test_universe_prints_are_publish_once(tmp_path):
    import ledger
    p = str(tmp_path / "prints.csv")
    rows = [{"ticker": "A.TO", "p945": 10.0}, {"ticker": "B.TO", "p945": 20.0}]
    assert ledger.append_universe_prints(rows, "2026-08-05", p) == 2
    assert ledger.append_universe_prints(rows, "2026-08-05", p) == 0   # no dupes
    assert ledger.append_universe_prints(rows, "2026-08-06", p) == 2


def test_relative_line_is_honest_when_prints_missing():
    import ledger
    assert "recording started day-28" in ledger.relative_line([], {})


def test_run_result_exposes_evaluated_prints_for_the_tide():
    """Day-29 bug: main() read `out`, a local of run(), so a NameError swallowed
    by `except: pass` meant NO universe prints were ever written and the
    relative-capture metric would have silently stopped accruing on day one."""
    import inspect

    import r945
    src = inspect.getsource(r945.run)
    assert '"evaluated"' in src, "run() must expose evaluated prints"
    main_src = inspect.getsource(r945.main)
    assert 'res.get("evaluated")' in main_src, "main() must read them off the result"
    assert "except Exception:\n                pass" not in main_src, \
        "print-saving failures must be reported, never swallowed"


# ── day-31: two legs per side, capacity unchanged ───────────────────────────
def test_two_legs_per_side_splits_the_same_book_not_more():
    """Capacity is IDENTICAL to the 1+1 book — extra legs divide the same money.
    Half the book per side, equal-risk within a side."""
    import r945
    picks = [{"last": 100.0, "vol": 1.0, "side_hint": "LONG"},
             {"last": 100.0, "vol": 1.0, "side_hint": "LONG"},
             {"last": 100.0, "vol": 1.0, "side_hint": "SHORT"},
             {"last": 100.0, "vol": 1.0, "side_hint": "SHORT"}]
    r945.allocate_book(picks, equity=100_000, max_book_pct=50)
    total = sum(p["alloc"] for p in picks)
    assert total <= 50_000
    for side in ("LONG", "SHORT"):
        s = sum(p["alloc"] for p in picks if p["side_hint"] == side)
        assert abs(s - 25_000) < 200, f"{side} side should hold half the book"


def test_a_missing_side_leaves_its_half_in_cash():
    """Day-18 contract survives day-31: one side absent must not double the
    other, it must reduce total exposure."""
    import r945
    picks = [{"last": 100.0, "vol": 1.0, "side_hint": "LONG"},
             {"last": 100.0, "vol": 1.0, "side_hint": "LONG"}]
    r945.allocate_book(picks, equity=100_000, max_book_pct=50)
    assert sum(p["alloc"] for p in picks) <= 25_100


def test_pair_of_day_returns_extra_legs_densest_first():
    import r945
    L = [{"t": "A.TO", "p_up": 0.60, "nd": 0.9, "confidence": "mid"},
         {"t": "B.TO", "p_up": 0.58, "nd": 0.2, "confidence": "dense"},
         {"t": "C.TO", "p_up": 0.57, "nd": 0.5, "confidence": "mid"}]
    pair = r945.pair_of_day(L, [], legs_per_side=2)
    assert pair["long"]["pick"]["t"] == "B.TO"          # densest is primary
    assert [x["t"] for x in pair["long"]["extra"]] == ["C.TO"]   # next densest
    assert r945.pair_of_day(L, [], legs_per_side=1)["long"].get("extra") is None


def test_printed_contract_matches_the_configured_leg_count():
    """Day-31: the header said 'one long + one short' and 'equal-weight' after
    the book became up-to-2-per-side, equal-RISK. A printed contract that
    contradicts the behaviour is the same defect class as the stale README."""
    import io
    from contextlib import redirect_stdout

    import r945
    pick = {"t": "A.TO", "p_up": 0.42, "nd": 0.3, "confidence": "dense",
            "p945": 62.03, "last": 62.03, "r0": 0.67, "gap": -0.29,
            "shares": 212, "alloc": 13150.0, "adverse_2pct": 263.0}
    res = {"now": "2026-08-10T09:47:00", "n_names": 21, "longs": [], "shorts": [pick],
           "excluded": [], "min_p": 0.55, "too_early": False,
           "pair": r945.pair_of_day([], [pick], legs_per_side=2),
           "late_min": 1.0, "stale_after_min": 20, "spent_drift_pct": 0.3,
           "max_chase_pct": 0.04, "ready_at_iso": "2026-08-10T09:46:00",
           "entry_window_min": 10, "legs_per_side": 2}
    buf = io.StringIO()
    with redirect_stdout(buf):
        r945.render(res, book=True)
    out = buf.getvalue()
    assert "one long + one short" not in out
    assert "up to 2 per side" in out
    assert "equal-weight" not in out and "equal-RISK" in out
    assert "CLOSE EVERY LEG BY 3:55" in out


# ── day-35: hit rate excluding economic scratches ───────────────────────────
def test_decisive_line_excludes_scratches_and_is_less_flattering():
    """The hit column is a pure sign test: +0.015% counts as much as +1.5%.
    On the live record 11% of legs end inside +/-0.10% and most landed on the
    winning side, inflating the headline by ~3pp. This line removes that."""
    import ledger
    rows = ([{"side": "LONG", "r1": "0.015"}] * 3          # scratch 'wins'
            + [{"side": "LONG", "r1": "1.50"}] * 3          # real wins
            + [{"side": "LONG", "r1": "-1.50"}] * 4)        # real losses
    line = ledger.decisive_line(rows, threshold=0.10)
    assert "3/7 (43%)" in line and "3 scratches excluded" in line
    # headline would read 6/10 = 60%; decisive is the LESS flattering 43%
    assert sum(1 for r in rows if float(r["r1"]) > 0) / len(rows) == 0.6


def test_decisive_line_is_honest_when_underpowered():
    import ledger
    assert "needs more scored legs" in ledger.decisive_line(
        [{"side": "LONG", "r1": "1.0"}] * 5)


# ── day-36: the exit-time study's two load-bearing mechanics ────────────────
def test_curve_risk_adjusts_so_early_exits_are_compared_fairly():
    """The trap this locks: at 09:50 barely any price movement has happened,
    so an early exit posts a smaller MEAN for a purely mechanical reason. A
    naive raw-mean comparison would always crown the close. `ir` (mean/std) and
    `scaled` (ir * close std) are what make the comparison fair."""
    import validate_exit as ve
    # the close earns a BIGGER mean, but buys it with far more dispersion
    idx = {}
    legs = []
    for i in range(60):
        early, late = (0.10, 0.60) if i % 3 else (-0.05, -0.60)
        idx[("T%d" % i, "d", 5)] = early
        idx[("T%d" % i, "d", 375)] = late
        legs.append({"t": "T%d" % i, "date": "d", "side": "LONG"})
    cv = ve.curve(legs, [5, 375], idx)
    assert cv.iloc[0]["mean"] < cv.iloc[-1]["mean"], "raw mean favours the close"
    assert cv.iloc[0]["ir"] > cv.iloc[-1]["ir"], "risk-adjusted favours early"
    # `scaled` restates the early exit at close-equivalent size
    assert cv.iloc[0]["scaled"] > cv.iloc[-1]["mean"]


def test_windows_are_incremental_not_cumulative():
    """A cumulative curve makes one good stretch look like a trend at every
    later exit. `windows` must difference it, so a leg that earns everything
    before 10:00 and nothing after shows ONE positive window, not eight."""
    import validate_exit as ve
    idx, legs = {}, []
    for i in range(40):
        legs.append({"t": "T%d" % i, "date": "d", "side": "LONG"})
        for m in (15, 45, 75, 135, 195, 255, 315, 375):
            idx[("T%d" % i, "d", m)] = 0.50      # all earned before 10:00, flat after
    w = ve.windows(legs, idx, "test")
    assert abs(w.iloc[0]["mean"] - 0.50) < 1e-9, "first window holds the move"
    assert all(abs(m) < 1e-9 for m in w["mean"].iloc[1:]), "later windows flat"


def test_windows_respects_side_sign():
    """A SHORT leg that falls has POSITIVE capture. Getting this backwards
    would invert every verdict in the study."""
    import validate_exit as ve
    idx, legs = {}, []
    for i in range(40):
        legs.append({"t": "T%d" % i, "date": "d", "side": "SHORT"})
        idx[("T%d" % i, "d", 15)] = -0.30       # price fell -> short profits
        idx[("T%d" % i, "d", 45)] = -0.30
    w = ve.windows(legs, idx, "test", edges=(0, 15, 45))
    assert w.iloc[0]["mean"] > 0


# ── day-37: the sweep's null must actually destroy the signal ───────────────
def test_placebo_destroys_a_real_edge():
    """The whole verdict rests on the null being a real null. If the placebo
    leaked the directional call, a rigged dataset would still 'win' under it
    and every rejection in the sweep would be unearned. Build days where the
    model is PERFECT, then confirm the placebo strips the edge away."""
    import numpy as np
    import validate_sweep as vs
    rng0 = np.random.default_rng(0)
    days = []
    for i in range(120):
        r = rng0.normal(0, 1, 8)
        p = np.where(r > 0, 0.9, 0.1)          # oracle: p_up knows the outcome
        days.append({"date": "d%03d" % i, "dow": "Mon",
                     "p": p, "nd": rng0.random(8), "r": r})
    real = vs.book_returns(days, 2, "long+short", 0.55, "densest", "all")
    null = vs.book_returns(days, 2, "long+short", 0.55, "densest", "all",
                           rng=np.random.default_rng(1))
    assert real.mean() > 0.5, "oracle config should be strongly positive"
    assert abs(null.mean()) < 0.2, "placebo must strip the edge"
    assert real.mean() > 4 * abs(null.mean())


def test_sweep_book_is_half_per_side_and_full_when_one_sided():
    """Capacity accounting: a hedged book puts half on each side, a single-sided
    book deploys the whole thing. Getting this wrong would make long-only look
    artificially small (or large) against the shipped config it is compared to."""
    import numpy as np
    import validate_sweep as vs
    days = [{"date": "d", "dow": "Mon", "p": np.array([0.9, 0.1]),
             "nd": np.array([0.1, 0.2]), "r": np.array([1.0, -1.0])}]
    both = vs.book_returns(days, 1, "long+short", 0.55, "densest", "all")
    lng = vs.book_returns(days, 1, "long-only", 0.55, "densest", "all")
    assert abs(both[0] - 1.0) < 1e-9, "0.5*(+1) + 0.5*(+1) from the short"
    assert abs(lng[0] - 2 * 0.5 * 1.0) < 1e-9, "long-only deploys fully"


# ── day-38: multi-day holds must not be scored with an inflated t-stat ──────
def test_multiday_t_uses_non_overlapping_trades():
    """A 3-day hold opened every session overlaps itself, so consecutive
    observations are not independent and a naive t is inflated by ~sqrt(N).
    `stat` must de-overlap before testing: same mean, smaller |t|."""
    import numpy as np
    import validate_shape as vh
    rng = np.random.default_rng(3)
    vals = rng.normal(0.05, 1.0, 300)
    m1, pd1, t1, n1 = vh.stat(vals, 1)
    m3, pd3, t3, n3 = vh.stat(vals, 3)
    assert m1 == m3 == vals.mean(), "mean uses every trade"
    assert n1 == n3 == 300, "n reports every trade"
    assert abs(t3) < abs(t1), "de-overlapped t must be smaller"
    assert abs(pd3 - vals.mean() / 3) < 1e-12, "per-day divides by the hold"


def test_per_day_of_risk_penalises_longer_holds():
    """A 5-day hold returning +0.5% is not better than a 1-day hold returning
    +0.2%: it ties up capital five times as long. Ranking on raw per-trade
    return would invert that, which is exactly how a drift-collecting
    multi-day book gets mistaken for an edge."""
    import numpy as np
    import validate_shape as vh
    long_hold = vh.stat(np.full(100, 0.50), 5)
    short_hold = vh.stat(np.full(100, 0.20), 1)
    assert long_hold[0] > short_hold[0], "raw per-trade favours the long hold"
    assert long_hold[1] < short_hold[1], "per day of risk reverses it"


def test_abstention_rules_can_actually_skip_days():
    """A no-trade rule that never fires would silently make every abstention
    config identical to 'none' and manufacture a fake null result."""
    import numpy as np
    import validate_shape as vh
    weak = {"p": np.array([0.56, 0.44]), "nd": np.array([0.9, 0.1]),
            "r": {1: np.array([1.0, -1.0])}, "date": "d", "dow": "Mon"}
    assert vh.skip(weak, "p>=0.60", 0.55) is True      # no name reaches 0.60
    assert vh.skip(weak, "none", 0.55) is False
    assert vh.skip(weak, "deep-board", 0.55) is True   # only 2 qualified
    flat = {"p": np.array([0.30, 0.31]), "nd": np.array([0.1, 0.2]),
            "r": {1: np.array([1.0, -1.0])}, "date": "d", "dow": "Mon"}
    assert vh.skip(flat, "margin", 0.55) is True       # 0.70 vs 0.69, no margin


# ── day-39: the entry-time race must not peek ───────────────────────────────
def _bars(n=30, start="09:30"):
    import pandas as pd
    idx = pd.date_range(f"2026-08-03 {start}", periods=n, freq="5min")
    px = [100.0 + i for i in range(n)]
    return pd.DataFrame({"Open": px, "High": px, "Low": px, "Close": px,
                         "Volume": [10.0] * n}, index=idx)


def test_entry_features_and_outcome_split_at_the_decision_bar():
    """The load-bearing property of an entry-time race: at decision bar i,
    r0 and v15 may use bars 0..i ONLY, and the outcome must run from bar i to
    the close. An off-by-one here would let a later entry silently read part of
    its own outcome and win the race by cheating."""
    import validate_entry as ve
    b = _bars()
    r2 = ve.rows_at(b, "X", 2, min_bars=5)[0]      # close of the 3rd bar = 102
    r5 = ve.rows_at(b, "X", 5, min_bars=5)[0]      # close of the 6th bar = 105
    assert abs(r2["r0"] - (102 / 100 - 1) * 100) < 1e-9
    assert abs(r5["r0"] - (105 / 100 - 1) * 100) < 1e-9
    # volume accumulates through the decision bar and no further
    assert r2["v15"] == 30.0 and r5["v15"] == 60.0
    # outcome starts AT the decision bar, so a later entry has less left
    assert abs(r2["r1"] - (129 / 102 - 1) * 100) < 1e-9
    assert r5["r1"] < r2["r1"], "a later entry must have a shorter horizon"


def test_entry_race_refuses_sessions_too_short_for_the_decision_bar():
    """A half-day with fewer bars than the decision index must be dropped, not
    silently scored off its last available bar — that would compare different
    entry times on different sessions."""
    import validate_entry as ve
    short = _bars(n=6)
    assert ve.rows_at(short, "X", 2, min_bars=5) != []
    assert ve.rows_at(short, "X", 11, min_bars=5) == []


# ── day-40: the batched scorer must BE the shipped model, not resemble it ───
def test_batched_scorer_matches_r945_knn_exactly():
    """validate_pool scores 220 names x 500 sessions, which r945.knn_probability
    cannot do (it rebuilds the standardised training matrix on every call). The
    batched version is only legitimate if it is numerically identical — same
    standardisation, K, weighting, Beta prior and clamp. If these ever diverge,
    every wide-universe result would be about a DIFFERENT model than the one
    being traded, and the comparison to 21 names would be meaningless."""
    import numpy as np
    import pandas as pd
    import r945
    import validate_pool as vp
    rng = np.random.default_rng(5)
    train = pd.DataFrame({"r0": rng.normal(0, 0.5, 900),
                          "gap": rng.normal(0, 0.8, 900),
                          "vp": rng.normal(1, 0.2, 900),
                          "r1": rng.normal(0, 1, 900)})
    today = pd.DataFrame({"r0": rng.normal(0, 0.5, 25),
                          "gap": rng.normal(0, 0.8, 25),
                          "vp": rng.normal(1, 0.2, 25)})
    p, nd = vp.score_day(train, today)
    for i in range(len(today)):
        want_p, _, want_nd = r945.knn_probability(
            train, {f: today[f].iloc[i] for f in r945.FEATS})
        assert abs(p[i] - want_p) < 1e-9, f"row {i}: {p[i]} vs {want_p}"
        assert abs(nd[i] - want_nd) < 1e-9, f"row {i} nd: {nd[i]} vs {want_nd}"


def test_batched_scorer_refuses_a_thin_pool_like_the_shipped_one():
    import numpy as np
    import pandas as pd
    import validate_pool as vp
    rng = np.random.default_rng(6)
    thin = pd.DataFrame({"r0": rng.normal(0, 1, 100), "gap": rng.normal(0, 1, 100),
                         "vp": rng.normal(1, 1, 100), "r1": rng.normal(0, 1, 100)})
    assert vp.score_day(thin, thin.head(3))[0] is None


def test_self_relative_density_neutralises_a_permanently_central_name():
    """The day-14 pathology: a low-volatility name sits at the centre of the
    feature cloud every day, so raw `nd` picks it forever. Self-relative
    density must rank it as ordinary while flagging a name that is unusually
    familiar TODAY relative to its own history."""
    import numpy as np
    import validate_pool as vp
    days = []
    for i in range(30):
        days.append({"date": "d%02d" % i, "t": np.array(["UTIL", "MINER"]),
                     "nd": np.array([0.10, 1.00]),      # UTIL always central
                     "p": np.array([0.6, 0.6]), "r": np.array([0.1, 0.1])})
    days.append({"date": "d99", "t": np.array(["UTIL", "MINER"]),
                 "nd": np.array([0.10, 0.30]),          # MINER unusually close
                 "p": np.array([0.6, 0.6]), "r": np.array([0.1, 0.1])})
    vp.add_self_relative(days)
    last = days[-1]
    assert np.argmin(last["nd"]) == 0, "raw density still picks the utility"
    assert np.argmin(last["nd_rel"]) == 1, "self-relative picks the miner"


# ── day-41: the visual board must suppress orders wherever the terminal does ─
def _res(**kw):
    base = {"now": "2026-08-13T09:47:00-04:00", "n_names": 21,
            "ready_at_iso": "2026-08-13T09:46:00-04:00", "entry_window_min": 10,
            "max_chase_pct": 0.04, "coverage": "21/21", "source": "yahoo_direct",
            "longs": [], "shorts": [], "excluded": [],
            "pair": {"long": {"status": "DENSE", "pick": {
                        "t": "ENB.TO", "p945": 71.87, "last": 71.80, "r0": 0.38,
                        "gap": -0.14, "p_up": 0.563, "confidence": "dense",
                        "shares": 163, "alloc": 11703, "adverse_2pct": 234}},
                     "short": {"status": "NONE"}}}
    base.update(kw)
    return base


def test_visual_board_shows_orders_only_on_a_live_book_run():
    import report_html
    page = report_html.render_html(_res(), book=True)
    assert "BUY 163 sh" in page


def test_visual_board_suppresses_orders_on_an_informational_rerun():
    """Day-25's rule: a printed order line IS the instruction, and a re-run can
    see REVISED early bars and mint a DIFFERENT board. The terminal already
    suppresses order lines there; a prettier report that did not would be a
    more dangerous one."""
    import report_html
    page = report_html.render_html(_res(), book=False)
    assert "BUY" not in page and "SELL SHORT" not in page
    assert "Informational run" in page


def test_visual_board_suppresses_orders_in_shadow_and_after_the_window():
    import report_html
    shadow = report_html.render_html(_res(shadow=True), book=True)
    assert "BUY" not in shadow and "SHADOW" in shadow
    late = report_html.render_html(
        _res(now="2026-08-13T10:30:00-04:00"), book=True)
    assert "BUY" not in late and "window closed" in late.lower()


def test_visual_board_refuses_to_render_a_board_it_must_not_show():
    """too-early and coverage-fail are fail-closed states: the page must carry
    the refusal and no picks at all."""
    import report_html
    early = report_html.render_html(
        {"now": "2026-08-13T09:38:00-04:00", "too_early": True,
         "ready_at": "09:46"}, book=True)
    assert "Too early" in early and 'class="tkt' not in early
    dead = report_html.render_html(
        {"now": "2026-08-13T09:47:00-04:00", "coverage_fail": "only 12/21"},
        book=True)
    assert "No board, no orders" in dead and 'class="tkt' not in dead


def test_visual_board_escapes_untrusted_fields():
    import report_html
    page = report_html.render_html(
        _res(excluded=[{"t": "<img src=x onerror=alert(1)>",
                        "excluded_reason": "r0 out of range"}]), book=True)
    assert "<img src=x" not in page and "&lt;img" in page


def test_visual_board_carries_no_document_scaffold():
    """Artifact wraps the file in its own <!doctype>/<head>/<body>."""
    import report_html
    page = report_html.render_html(_res(), book=True).lower()
    for tag in ("<!doctype", "<html", "<body", "<head>"):
        assert tag not in page


# ---------------------------------------------------------------- day-42
# A stale clone made the 9:46 report print PAIR 24/47 (51%) when the true
# figure was 24/51 (47%), and claim there had been no session the previous
# day. Absence of rows was read as absence of events. These lock the guard.

def _cal(trading):
    return lambda d: d.isoformat() in trading


def test_missing_sessions_flags_a_trading_day_gap():
    import ledger, datetime as dt
    rows = [{"date": "2026-08-12", "ticker": "X"}]
    gaps = ledger.missing_sessions(rows, dt.date(2026, 8, 14),
                                   _cal({"2026-08-13", "2026-08-14"}))
    assert gaps == ["2026-08-13"]


def test_missing_sessions_ignores_weekends_and_holidays():
    import ledger, datetime as dt
    # nothing between the 12th and the 14th is a trading day -> no gap
    gaps = ledger.missing_sessions([{"date": "2026-08-12", "ticker": "X"}],
                                   dt.date(2026, 8, 14), _cal({"2026-08-14"}))
    assert gaps == []


def test_missing_sessions_excludes_today_itself():
    """Today is being published right now; it is never a 'missing' session."""
    import ledger, datetime as dt
    gaps = ledger.missing_sessions([{"date": "2026-08-13", "ticker": "X"}],
                                   dt.date(2026, 8, 14),
                                   _cal({"2026-08-13", "2026-08-14"}))
    assert gaps == []


def test_missing_sessions_empty_ledger_is_not_a_gap():
    import ledger, datetime as dt
    assert ledger.missing_sessions([], dt.date(2026, 8, 14), _cal({"2026-08-14"})) == []


def test_gap_line_silent_when_complete_and_loud_when_not():
    import ledger
    assert ledger.gap_line([]) == ""
    line = ledger.gap_line(["2026-08-13"])
    assert "INCOMPLETE" in line and "2026-08-13" in line


def test_gap_line_truncates_long_gap_lists():
    import ledger
    line = ledger.gap_line([f"2026-08-{d:02d}" for d in range(3, 12)])
    assert "…" in line and len(line.splitlines()) == 2


# ---------------------------------------------------------------- day-43
# `vp` is not computable on the 1-hour panel: Yahoo zeroes ~86% of FIRST
# hourly bars while later bars are ~0.1% zeroed, so the all-bars rate (~12.5%)
# looks survivable and is not. It failed SILENTLY two ways — dropping 145,201
# of 145,228 rows via NaN, or becoming raw share volume when the per-ticker
# median is itself zero. These lock the detector, not the data.

def test_usable_feats_drops_vp_when_entry_volume_is_mostly_zero():
    import pandas as pd, validate_ceiling as vc
    df = pd.DataFrame({"v15": [0.0] * 86 + [1000.0] * 14})
    assert vc.usable_feats(df) == ["r0", "gap"]


def test_usable_feats_keeps_vp_when_volume_is_populated():
    import pandas as pd, validate_ceiling as vc
    df = pd.DataFrame({"v15": [1000.0] * 99 + [0.0]})
    assert vc.usable_feats(df) == ["r0", "gap", "vp"]


def test_add_vp_never_uses_a_rows_own_or_future_volume():
    """The normaliser is an expanding median shifted one session back."""
    import pandas as pd, numpy as np, validate_ceiling as vc
    n = 40
    df = pd.DataFrame({"t": ["A"] * n,
                       "date": [f"2026-01-{i+1:02d}" for i in range(n)],
                       "v15": np.arange(1.0, n + 1.0)})
    out = vc.add_vp(df)
    # first 20 rows have no 20-observation history -> undefined, not fabricated
    assert out["vp"].iloc[:20].isna().all()
    # row 20 is normalised by the median of rows 0..19 (= 10.5), not by itself
    assert abs(float(out["vp"].iloc[20]) - 21.0 / 10.5) < 1e-9


def test_auc_matches_hand_computed_value():
    import numpy as np, validate_ceiling as vc
    y = np.array([0, 0, 1, 1])
    assert abs(vc.auc(y, np.array([0.1, 0.2, 0.3, 0.4])) - 1.0) < 1e-9
    assert abs(vc.auc(y, np.array([0.4, 0.3, 0.2, 0.1])) - 0.0) < 1e-9
    assert abs(vc.auc(y, np.array([0.5, 0.5, 0.5, 0.5])) - 0.5) < 1e-9


def test_control_feature_actually_carries_its_planted_edge():
    """If this fails, a null result from the harness means nothing."""
    import pandas as pd, numpy as np, validate_ceiling as vc
    rng = np.random.default_rng(1)
    df = pd.DataFrame({"y": rng.integers(0, 2, 20000)})
    out = vc.add_control(df, edge=0.02)
    assert vc.auc(out["y"].to_numpy(), out["ctrl"].to_numpy()) > 0.51


# ---------------------------------------------------------------- day-45
# The book's return splits exactly into market exposure and selection:
#   sum(w*cap) = tide*sum(w*sign) + sum(w*sign*rel)
# Losing days had always been argued verbally as "the market" vs "the picks";
# this reconciles to the book-weighted number with no residual.

def _row(date, tk, side, w, r1):
    return {"date": date, "ticker": tk, "side": side, "weight": str(w),
            "r1": str(r1), "role": "pair"}


def test_attribution_sums_to_the_book_weighted_return():
    import ledger
    rows = [_row("2026-08-18", "A", "LONG", 0.25, -0.492),
            _row("2026-08-18", "B", "LONG", 0.25, -0.537),
            _row("2026-08-18", "C", "SHORT", 0.25, 0.134),
            _row("2026-08-18", "D", "SHORT", 0.25, -0.350)]
    tides = {"2026-08-18": -0.466}
    t_c, s_c, n = ledger.attribution(rows, tides)
    book = sum(float(r["weight"]) * float(r["r1"]) *
               (1 if r["side"] == "LONG" else -1) for r in rows)
    assert n == 1
    assert abs((t_c + s_c) - book) < 1e-9


def test_attribution_perfectly_hedged_book_has_zero_tide_component():
    """Equal weight long and short -> market exposure cancels exactly."""
    import ledger
    rows = [_row("2026-01-05", "A", "LONG", 0.5, 2.0),
            _row("2026-01-05", "B", "SHORT", 0.5, -1.0)]
    t_c, s_c, _ = ledger.attribution(rows, {"2026-01-05": 5.0})
    assert abs(t_c) < 1e-12          # no residual directional exposure
    assert abs(s_c - 0.5 * (2.0 - 5.0) - 0.5 * -(-1.0 - 5.0)) < 1e-12


def test_attribution_one_legged_book_carries_real_tide_exposure():
    """A missing side leaves the book directional — that must show up."""
    import ledger
    t_c, s_c, _ = ledger.attribution(
        [_row("2026-01-06", "A", "SHORT", 0.5, 0.0)], {"2026-01-06": -1.0})
    assert abs(t_c - 0.5) < 1e-12    # short a falling tape = +0.5% of exposure


def test_attribution_skips_rows_without_weight_prints_or_outcome():
    import ledger
    rows = [_row("2026-01-07", "A", "LONG", 0.5, 1.0),
            {"date": "2026-01-07", "ticker": "B", "side": "LONG",
             "weight": "", "r1": "1.0", "role": "pair"},          # no weight
            {"date": "2026-01-07", "ticker": "C", "side": "LONG",
             "weight": "0.5", "r1": "", "role": "pair"},          # unscored
            _row("2026-09-09", "D", "LONG", 0.5, 1.0)]            # no tide
    _, _, n = ledger.attribution(rows, {"2026-01-07": 0.0})
    assert n == 1


def test_attribution_line_is_silent_without_data():
    import ledger
    assert "needs universe prints" in ledger.attribution_line([], {})


# ---------------------------------------------------------------- day-47
# A one-legged book is NOT market-neutral. Day-47 closed +$73 on a -1.334%
# tape with ~50% net short exposure: TIDE +0.666%, SELECTION -0.518%. The
# profit was unhedged direction, the picks were the worst of the run, and the
# board never said so. These lock the warning that now says it at 9:46.

def _pair(long_status, short_status, n_short_legs=2):
    def leg(status, n):
        if status == "NONE":
            return {"status": "NONE", "note": "no qualified leg"}
        return {"pick": {"t": "A"}, "extra": [{"t": "B"}] if n > 1 else []}
    return {"long": leg(long_status, 0), "short": leg(short_status, n_short_legs)}


def test_one_sided_warning_names_the_short_exposure():
    import r945
    w = r945.one_sided_warning(_pair("NONE", "OK"))
    assert "NOT MARKET-NEUTRAL" in w and "SHORT" in w
    assert "profits if the market falls" in w


def test_one_sided_warning_names_the_long_exposure():
    import r945
    w = r945.one_sided_warning({"long": {"pick": {"t": "A"}, "extra": []},
                                "short": {"status": "NONE"}})
    assert "LONG" in w and "profits if the market rises" in w


def test_one_sided_warning_handles_an_empty_book():
    """Neither side qualified is correct output, not a directional bet."""
    import r945
    w = r945.one_sided_warning(_pair("NONE", "NONE", 0))
    assert "cash" in w and "NOT MARKET-NEUTRAL" not in w


def test_one_sided_warning_agrees_with_the_attribution_arithmetic():
    """The warning claims ~50% net exposure; attribution must show it."""
    import ledger
    rows = [{"date": "2026-08-19", "ticker": "BCE.TO", "side": "SHORT",
             "weight": "0.2685", "r1": "0.430", "role": "pair"},
            {"date": "2026-08-19", "ticker": "CNQ.TO", "side": "SHORT",
             "weight": "0.2304", "r1": "-1.140", "role": "pair"}]
    t_c, s_c, _ = ledger.attribution(rows, {"2026-08-19": -1.334})
    assert t_c > 0.6 and s_c < -0.5          # tide carried it, picks lost
    assert abs((t_c + s_c) - 0.1472) < 1e-3  # and they reconcile to the book


# ---------------------------------------------------------------- day-49
# Day-47 decided the density gate (NO gate) but the verdict did not propagate:
# four places still advertised it as pending or quoted the refuted 63% holdout
# figure, including a tagline printed on EVERY board. A measurement that
# contradicts shipped text is only half-applied until the text changes too.

def test_no_module_still_advertises_the_density_gate_as_pending():
    import pathlib
    for name in ("r945.py", "ledger.py"):
        src = pathlib.Path(name).read_text(encoding="utf-8")
        assert "~20 live days the tag" not in src, name
        assert "to be judged\non ~20 live days" not in src, name


def test_the_refuted_63_percent_density_claim_is_gone():
    import pathlib
    src = pathlib.Path("r945.py").read_text(encoding="utf-8")
    # it may be NAMED as dead, but never asserted as current evidence
    assert "hinted dense estimates hit better (63%" not in src


def test_board_tagline_does_not_claim_density_is_an_edge():
    import pathlib
    src = pathlib.Path("r945.py").read_text(encoding="utf-8")
    assert "familiarity beats extremity" not in src
    assert "CALMNESS sort, not an edge" in src


def test_density_label_still_tags_correctly():
    """The verdict changed the prose, not the behaviour."""
    import r945
    assert r945.density_label(0.01, (0.05, 0.20)) == "dense"
    assert r945.density_label(0.10, (0.05, 0.20)) == "mid"
    assert r945.density_label(0.50, (0.05, 0.20)) == "sparse"
