"""Day-82 §5a: the selection study, and the controls that make its null usable.

Pre-registered in PREREGISTER_day82.md. The verdict was UNDERPOWERED, which is
only a legitimate answer if the harness can be shown to detect a planted effect
of a stated size and to stay quiet on none. Both are asserted here.
"""

import numpy as np
import pytest

import validate_selection as S


def legs(n_sessions=30, per_day=8, pair_k=2, pair_edge=0.0, seed=0):
    """Synthetic sessions with a KNOWN planted edge on the selected legs.

    Each day gets one shared market move plus per-leg noise, so the session
    clustering the harness claims to handle is actually present in the data.
    """
    rng = np.random.default_rng(seed)
    out = []
    for d in range(n_sessions):
        day = f"2026-01-{d % 28 + 1:02d}-{d}"
        tide = rng.normal(0, 0.4)                 # the shared component
        for i in range(per_day):
            role = "pair" if i < pair_k else "board"
            edge = pair_edge if role == "pair" else 0.0
            c = tide + rng.normal(edge, 0.9)
            out.append({"date": day, "ticker": f"T{i}", "side": "LONG",
                        "role": role, "capture": c,
                        "decisive": abs(c) >= S.L.DECISIVE_PCT})
    return out


# ── the statistics ──────────────────────────────────────────────────────────

def test_a_scratch_is_excluded_from_the_decisive_rate():
    rows = [{"capture": 0.01, "decisive": False},
            {"capture": -1.0, "decisive": True},
            {"capture": +1.0, "decisive": True}]
    assert S.rate(rows) == 0.5
    assert abs(S.mean_capture(rows) - 0.00333) < 1e-3


def test_rate_on_no_decisive_legs_is_none_not_zero():
    """Zero would read as 'never right'. None reads as 'not measured'."""
    assert S.rate([{"capture": 0.01, "decisive": False}]) is None
    assert S.mean_capture([]) is None


# ── the positive control: it must SEE a planted edge ────────────────────────

def test_a_large_planted_edge_is_detected():
    """POSITIVE CONTROL. A harness that cannot see a planted effect cannot
    report a null (rule 4)."""
    rows = legs(n_sessions=120, pair_edge=1.2, seed=3)
    pair = [r for r in rows if r["role"] == "pair"]
    board = [r for r in rows if r["role"] == "board"]
    d, lo, hi = S.boot_diff(pair, board, S.mean_capture, n=800)
    assert d > 0.5, d
    assert lo > 0, f"planted edge not distinguishable: [{lo}, {hi}]"


@pytest.mark.slow
def test_the_false_positive_rate_on_a_true_null_is_near_nominal():
    """It must stay QUIET when there is nothing — but CALIBRATION, not a
    single seed.

    The first version of this test asserted that one seed's null interval
    covers zero, and it failed on seed 4. That is not a bug in the harness: a
    95% interval is SUPPOSED to exclude the truth 5% of the time, so the test
    was guaranteed to be flaky by construction and would have been "fixed" by
    changing the seed — hiding the fact that nobody had measured the rate.
    Measured across 40 independent nulls: 5%, and the difference centres on
    zero.
    """
    fp, n = 0, 40
    diffs = []
    for s in range(n):
        rows = legs(n_sessions=120, pair_edge=0.0, seed=100 + s)
        pair = [r for r in rows if r["role"] == "pair"]
        board = [r for r in rows if r["role"] == "board"]
        d, lo, hi = S.boot_diff(pair, board, S.mean_capture, n=300)
        diffs.append(d)
        if lo is not None and (lo > 0 or hi < 0):
            fp += 1
    assert fp / n <= 0.20, f"false-positive rate {fp}/{n} far above nominal 5%"
    assert abs(float(np.mean(diffs))) < 0.05, "the null is not centred on zero"


def test_power_measures_edge_over_sd_not_mean_plus_edge():
    """The day-56 error. Adding the edge to the mean inflates z whenever the
    mean is non-zero, and the sample mean here is deliberately non-zero."""
    rows = legs(n_sessions=60, pair_edge=0.8, seed=5)
    pair = [r for r in rows if r["role"] == "pair"]
    board = [r for r in rows if r["role"] == "board"]
    z_small = S.power(pair, board, S.mean_capture, 0.10)
    z_big = S.power(pair, board, S.mean_capture, 0.50)
    # z must scale with the PLANTED edge, exactly linearly.
    assert abs(z_big / z_small - 5.0) < 0.05, (z_small, z_big)


# ── session clustering is real, not decorative ──────────────────────────────

def test_clustering_widens_the_interval_when_days_are_correlated():
    """Legs on one day share that day's move. If resampling sessions gave the
    same interval as resampling legs, the clustering would be decoration."""
    rows = legs(n_sessions=40, per_day=10, seed=6)
    pair = [r for r in rows if r["role"] == "pair"]
    board = [r for r in rows if r["role"] == "board"]
    _, lo_c, hi_c = S.boot_diff(pair, board, S.mean_capture, n=800)
    clustered = hi_c - lo_c

    # naive: every leg its own "session", destroying the shared component
    flat_p = [dict(r, date=f"{r['date']}-{i}") for i, r in enumerate(pair)]
    flat_b = [dict(r, date=f"{r['date']}-b{i}") for i, r in enumerate(board)]
    _, lo_f, hi_f = S.boot_diff(flat_p, flat_b, S.mean_capture, n=800)
    assert clustered > (hi_f - lo_f), "clustering did not widen the interval"


# ── the placebo shuffles the label the way it is actually assigned ──────────

def test_the_placebo_shuffles_within_a_session():
    """r945 picks the pair from THAT DAY's qualifiers, so exactly k legs per
    session carry the label. A pooled shuffle mixes sessions, destroys the
    within-day structure, and returns an interval that is too narrow."""
    rows = legs(n_sessions=40, per_day=8, pair_k=2, seed=7)
    lo, hi = S.placebo(rows, 80, S.mean_capture, n=200)
    assert lo < 0 < hi
    # the null placebo must be roughly symmetric about zero
    assert abs(lo + hi) < 0.5 * (hi - lo)


def test_the_placebo_preserves_the_per_session_pair_count():
    """If it did not, it would be testing a different split from the real one."""
    rows = legs(n_sessions=5, per_day=6, pair_k=2, seed=8)
    by = S._by_session(rows)
    assert all(sum(1 for r in v if r["role"] == "pair") == 2
               for v in by.values())


# ── verdicts and the sessions-needed arithmetic ─────────────────────────────

def test_an_effect_smaller_than_the_interval_reads_underpowered():
    """Rule 10: an interval wider than the effect means the data cannot
    answer, which is NOT the same as answering no."""
    v = S.verdict(-0.08, (-0.22, +0.06), 0.14)
    assert "UNDERPOWERED" in v


def test_an_interval_excluding_zero_reads_distinguishable():
    assert S.verdict(0.30, (0.10, 0.50), 0.20) == "DISTINGUISHABLE"


def test_a_missing_interval_is_not_computable_not_a_null():
    assert S.verdict(None, (None, None), None) == "NOT COMPUTABLE"


def test_sessions_needed_scales_as_the_square_of_the_shortfall():
    """z grows as sqrt(n), so reaching 3x the current z needs 9x the sessions."""
    assert S.sessions_needed(1.0, 38, bar=3.0) == 342
    assert S.sessions_needed(3.0, 38, bar=3.0) == 38
    assert S.sessions_needed(0.0, 38) is None
    assert S.sessions_needed(float("nan"), 38) is None


def test_too_few_sessions_refuses_rather_than_returning_a_number():
    rows = legs(n_sessions=3, seed=9)
    pair = [r for r in rows if r["role"] == "pair"]
    board = [r for r in rows if r["role"] == "board"]
    assert S.boot_diff(pair, board, S.mean_capture) == (None, None, None)


def test_the_report_states_the_rule_10_caveat():
    rows = legs(n_sessions=40, seed=10)
    out = S.report(S.h1(rows))
    assert "NOT the same as answering no" in out
    assert "positive control" in out
    assert "95%" in out and "placebo" in out
    # every verdict the harness can emit is one of the registered vocabulary
    assert any(v in out for v in ("UNDERPOWERED", "DISTINGUISHABLE",
                                  "NOT distinguishable", "NOT COMPUTABLE"))


def test_an_empty_ledger_refuses_rather_than_reporting_a_null():
    with pytest.raises(SystemExit):
        S.main(["--ledger", "/nonexistent/ledger.csv"])
