"""Day-84: short interest as a selection input, and the controls that make its
verdict usable.

Pre-registered in PREREGISTER_day84.md. Two failures this study was BUILT to
have are tested hardest:

  1. LOOK-AHEAD through the settlement/publication gap. Using the settlement
     date as the availability date manufactures an edge that looks real.
  2. A TICKER THAT IS NOT A COMPANY. `B` is Barrick today and was Barnes Group
     before 2025; `GOLD` was Randgold, then Barrick, then Gold.com. Joining on
     the ticker alone silently pairs one company's short interest with
     another's returns.
"""

import numpy as np
import pytest

import build_shortinterest as B
import validate_shortinterest as S


# ── the issuer name is the authority, not the ticker ───────────────────────

def test_a_rename_is_accepted():
    """TransCanada -> TC Energy, 2019. Same company; rejecting it would throw
    away 33 legitimate reports, which it did on the first build."""
    assert B.is_expected_issuer("TRP.TO", "TransCanada Corporation")
    assert B.is_expected_issuer("TRP.TO", "TC Energy Corporation")


def test_a_ticker_reassigned_to_another_company_is_rejected():
    """The fault the check exists for: three different issuers under two
    tickers, and only the name separates them."""
    assert B.is_expected_issuer("ABX.TO", "Barrick Gold Corp.")
    assert B.is_expected_issuer("ABX.TO", "Barrick Mining Corporation")
    assert not B.is_expected_issuer("ABX.TO", "Barnes Group Inc.")
    assert not B.is_expected_issuer("ABX.TO", "Gold.com, Inc.")
    assert not B.is_expected_issuer("ABX.TO", "Randgold Resources Limited Ame")


def test_an_unregistered_name_raises_rather_than_passing():
    with pytest.raises(B.IssuerMismatch):
        B.is_expected_issuer("NOSUCH.TO", "Anything At All")


def test_rows_for_counts_what_it_rejects_instead_of_dropping_it_silently():
    payload = [{"issueName": "Barrick Gold Corp.", "settlementDate": "2024-01-15",
                "currentShortPositionQuantity": 1, "previousShortPositionQuantity": 1,
                "averageDailyVolumeQuantity": 1, "daysToCoverQuantity": 1.0,
                "changePercent": 0.0},
               {"issueName": "Barnes Group Inc.", "settlementDate": "2024-01-15",
                "currentShortPositionQuantity": 9, "previousShortPositionQuantity": 9,
                "averageDailyVolumeQuantity": 9, "daysToCoverQuantity": 9.0,
                "changePercent": 0.0}]
    rows, wrong = B.rows_for("ABX.TO", "B", payload)
    assert len(rows) == 1 and wrong == 1
    assert rows[0]["si"] == 1, "the WRONG company's number was kept"


# ── point-in-time: the look-ahead trap ─────────────────────────────────────

def test_publish_date_is_strictly_after_settlement():
    assert str(B.publish_date("2026-08-14").date()) > "2026-08-14"


def test_publish_date_moves_with_the_lag():
    a = B.publish_date("2026-08-14", 9)
    b = B.publish_date("2026-08-14", 15)
    assert b > a


def si_frame():
    import pandas as pd
    return pd.DataFrame([
        {"tsx": "RY.TO", "settlement_date": "2026-01-15",
         "publish_date": "2026-01-28", "si": 100, "si_prev": 90,
         "adv": 10, "dtc": 10.0, "change_pct": 11.1},
        {"tsx": "RY.TO", "settlement_date": "2026-01-30",
         "publish_date": "2026-02-12", "si": 200, "si_prev": 100,
         "adv": 10, "dtc": 20.0, "change_pct": 100.0}])


def test_the_join_never_returns_a_report_published_after_the_session():
    """THE FAILURE THIS STUDY WAS BUILT TO HAVE."""
    si = si_frame()
    assert S.as_of(si, "RY.TO", "2026-02-01")["dtc"] == 10.0
    assert S.as_of(si, "RY.TO", "2026-02-20")["dtc"] == 20.0


def test_a_session_before_any_publication_gets_nothing():
    assert S.as_of(si_frame(), "RY.TO", "2026-01-20") is None


def test_a_name_with_no_report_is_unknown_and_never_zero():
    """Rule 2: absence of data is not absence of short interest."""
    legs = [{"t": "RY.TO", "date": "2026-02-01", "side": "LONG", "capt_rel": 1.0},
            {"t": "AC.TO", "date": "2026-02-01", "side": "LONG", "capt_rel": 1.0}]
    kept, unknown = S.attach(legs, si_frame())
    assert unknown == 1
    assert [k["t"] for k in kept] == ["RY.TO"]
    assert all("dtc" in k for k in kept)


# ── the positive control ───────────────────────────────────────────────────

def gaps(n=200, effect=0.0, sd=1.0, seed=0):
    rng = np.random.default_rng(seed)
    return [{"date": f"2026-{1 + i // 28:02d}-{1 + i % 28:02d}",
             "gap": effect + rng.normal(0, sd)} for i in range(n)]


def test_a_planted_effect_is_detected():
    """Rule 4: a harness that cannot see a planted effect cannot report a null."""
    g = gaps(n=300, effect=0.5, sd=1.0, seed=1)
    m, lo, hi = S.boot_diff(g, "gap")
    assert m > 0.3 and lo > 0, f"planted effect invisible: [{lo}, {hi}]"


def test_no_planted_effect_leaves_the_interval_covering_zero():
    _, lo, hi = S.boot_diff(gaps(n=300, effect=0.0, seed=2), "gap")
    assert lo < 0 < hi


def test_power_scales_linearly_with_the_planted_edge():
    """edge / sd, never (mean + edge) / sd — the day-56 error, which inflates
    z whenever the sample mean happens to be non-zero."""
    g = gaps(n=200, effect=0.4, seed=3)
    z1, z2 = S.power(g, "gap", 0.25), S.power(g, "gap", 1.0)
    assert abs(z2 / z1 - 4.0) < 0.05, (z1, z2)


def test_too_few_sessions_refuses_rather_than_returning_a_number():
    assert S.boot_diff(gaps(n=5), "gap") == (None, None, None)


# ── clustering by session ──────────────────────────────────────────────────

def test_clustering_by_session_widens_the_interval_when_legs_share_a_day():
    """Legs within one session share that day's move and are not independent."""
    rng = np.random.default_rng(4)
    rows = []
    for d in range(40):
        shared = rng.normal(0, 3.0)
        for _ in range(8):
            rows.append({"date": f"d{d:03d}", "gap": shared + rng.normal(0, 0.3)})
    _, lo_c, hi_c = S.boot_diff(rows, "gap")
    flat = [{"date": f"d{i:04d}", "gap": r["gap"]} for i, r in enumerate(rows)]
    _, lo_f, hi_f = S.boot_diff(flat, "gap")
    assert (hi_c - lo_c) > 2 * (hi_f - lo_f), "clustering did not widen it"


# ── four-quarter consistency ───────────────────────────────────────────────

def test_a_sign_flip_across_blocks_fails_consistency():
    assert not S.consistent([0.1, 0.2, -0.3, 0.1])
    assert S.consistent([0.1, 0.2, 0.3, 0.1])
    assert S.consistent([-0.1, -0.2, -0.3, -0.1])
    assert not S.consistent([])


def test_consistency_is_required_even_when_t_clears():
    """The bar is |t|>=3 AND four-quarter consistency. Both, not either."""
    v = S.verdict(1.0, 0.8, 1.2, [0.5, -0.5, 0.9, 0.4], None, None)
    assert "FAILS four-quarter consistency" in v


def test_an_effect_inside_the_placebo_band_is_not_an_effect():
    """Day-51's oracle gap of +2.34%/trade was smaller than noise's +2.85%."""
    v = S.verdict(1.0, 0.8, 1.2, [0.5, 0.5, 0.9, 0.4], 0.5, 1.5)
    assert "INSIDE the placebo band" in v


def test_a_small_effect_with_a_wide_interval_reads_underpowered():
    """Rule 10: cannot resolve is not the same as no effect."""
    assert "UNDERPOWERED" in S.verdict(0.01, -0.9, 0.9, [0.1] * 4, None, None)


def test_a_clean_pass_says_so():
    v = S.verdict(1.0, 0.8, 1.2, [0.9, 1.1, 1.0, 1.0], -0.1, 0.1)
    assert "CLEARS the bar" in v


# ── the tercile machinery ──────────────────────────────────────────────────

def test_terciles_are_cut_on_the_session_not_the_pool():
    """A session-relative cut, fixed in the pre-registration."""
    legs = [{"date": "d1", "t": f"T{i}", "dtc": float(i), "capt_rel": 0.0,
             "side": "LONG"} for i in range(9)]
    legs += [{"date": "d2", "t": f"T{i}", "dtc": float(i) + 100, "capt_rel": 0.0,
              "side": "LONG"} for i in range(9)]
    top, bot = S.tercile_split(legs, "dtc")
    assert {l["date"] for l in top} == {"d1", "d2"}, "one session dominated the cut"
    assert {l["date"] for l in bot} == {"d1", "d2"}


def test_the_gap_is_differenced_within_a_session():
    """A session-wide shift must cancel, so the tide cannot be counted twice."""
    base = [{"date": "d1", "t": f"T{i}", "dtc": float(i), "capt_rel": 0.0}
            for i in range(9)]
    shifted = [{**r, "capt_rel": r["capt_rel"] + 5.0} for r in base]
    assert S.paired_gap(base, "dtc")[0]["gap"] == \
           pytest.approx(S.paired_gap(shifted, "dtc")[0]["gap"])


def test_the_placebo_shuffles_the_feature_and_finds_nothing_on_noise():
    rng = np.random.default_rng(5)
    legs = [{"date": f"d{d:03d}", "t": f"T{i}", "dtc": rng.normal(),
             "capt_rel": rng.normal()} for d in range(60) for i in range(9)]
    lo, hi = S.placebo_gap(legs, "dtc", n=40)
    assert lo is not None and lo < 0 < hi


def test_demeaning_removes_a_permanent_name_level():
    """If a name simply always sits high, the demeaned feature must not."""
    legs = [{"date": f"d{d:03d}", "t": "HIGH", "dtc": 20.0, "capt_rel": 0.0}
            for d in range(10)]
    out = S.demean(legs, "dtc")
    assert out and all(abs(o["dtc"]) < 1e-9 for o in out)


def test_rank_persistence_sees_a_frozen_sort():
    import pandas as pd
    si = pd.DataFrame([{"settlement_date": f"s{d}", "tsx": f"T{i}",
                        "dtc": float(i)} for d in range(6) for i in range(8)])
    assert S.rank_persistence(si) > 0.99


# ── contracts stated in the pre-registration ───────────────────────────────

def test_the_sides_are_never_pooled():
    src = open(S.__file__).read()
    assert 'for side in ("LONG", "SHORT")' in src
    assert "never pooled" in " ".join(src.split())


def test_the_join_uses_publish_date_and_never_settlement_date():
    src = open(S.as_of.__code__.co_filename).read()
    fn = src[src.index("def as_of("):src.index("def attach(")]
    assert "publish_date" in fn and "settlement_date" not in fn


def test_the_deciding_statistic_is_tide_relative():
    flat = " ".join(open(S.__file__).read().split())
    assert "capt_rel" in flat
    assert "not hit rate" in flat


def test_a_missing_feature_file_refuses_instead_of_defaulting():
    with pytest.raises(FileNotFoundError):
        S.load_si("/nonexistent/short_interest.csv")
