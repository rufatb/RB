"""Day-82: re-deriving cost.TYPICAL_MOVE_PCT, the denominator of the cost line.

It was MEASURED with no script — a claim wearing a measurement's clothes, the
state day-79's constants were in for two days. Re-derived, it disagrees with
what ships.
"""

import numpy as np

import validate_typicalmove as V


def legs(n_sessions=30, per_day=8, size=1.0, seed=0):
    rng = np.random.default_rng(seed)
    out = []
    for d in range(n_sessions):
        day = f"2026-0{d % 9 + 1}-{d % 28 + 1:02d}"
        tide = rng.normal(0, 0.3)
        for _ in range(per_day):
            out.append({"date": day, "side": "LONG",
                        "r1": f"{tide + rng.normal(0, size)}"})
    return out


def test_the_median_is_used_not_the_mean():
    """A handful of violent sessions would drag a mean upward and flatter the
    spread by making it a smaller share of a bigger move."""
    rows = legs(seed=1) + [{"date": "2026-12-31", "side": "LONG", "r1": "80.0"}]
    r = V.run(rows)
    assert r["median"] < r["mean"], "an outlier did not separate them"


def test_absolute_capture_is_used_so_direction_does_not_cancel():
    rows = [{"date": "d1", "side": "LONG", "r1": "1.0"},
            {"date": "d1", "side": "LONG", "r1": "-1.0"}]
    m = V.moves(rows)
    assert [x for _, x in m] == [1.0, 1.0]


def test_unscored_legs_are_skipped_not_counted_as_zero_movement():
    """Counting a blank as zero would drag the median toward zero and make the
    spread look like a larger share of a smaller move — wrong in the opposite
    direction, but still wrong."""
    rows = [{"date": "d1", "side": "LONG", "r1": ""},
            {"date": "d1", "side": "LONG", "r1": "1.0"}]
    assert len(V.moves(rows)) == 1


def _widths(tide_sd, noise, seed=2, n_sessions=40, per_day=10):
    """(clustered, unclustered) interval widths for a given correlation."""
    rng = np.random.default_rng(seed)
    rows = []
    for d in range(n_sessions):
        tide = rng.normal(0, tide_sd)
        for _ in range(per_day):
            rows.append((f"d{d}", abs(tide + rng.normal(0, noise))))
    flat = [(f"{d}-{i}", m) for i, (d, m) in enumerate(rows)]
    _, a, b = V.boot_median(rows, n=600)
    _, c, e = V.boot_median(flat, n=600)
    return (b - a), (e - c)


def test_clustering_widens_the_interval_when_sessions_actually_correlate():
    """Legs on one day share that day's move. This is the regime clustering
    exists for, and here it must matter."""
    clustered, flat = _widths(tide_sd=1.5, noise=0.5)
    assert clustered > 2 * flat, (clustered, flat)


def test_clustering_does_not_inflate_the_interval_when_there_is_no_correlation():
    """The converse, and the reason the first version of this test failed.

    Clustering is not a blanket widening — it responds to how much of the
    variance is shared. With a weak session component the two agree, and a
    test asserting it always widens was asserting a misunderstanding rather
    than a property. In the live ledger the tide is +0.036%/session against
    -0.194% from selection, so this is nearer the real regime than the other.
    """
    clustered, flat = _widths(tide_sd=0.05, noise=1.0)
    assert 0.6 < clustered / flat < 1.6, (clustered, flat)


def test_too_few_sessions_refuses_rather_than_returning_a_number():
    assert V.boot_median([("d1", 1.0), ("d2", 1.0)]) == (None, None, None)


def test_an_empty_ledger_refuses_rather_than_publishing_a_constant():
    import pytest
    with pytest.raises(SystemExit):
        V.run([])


def test_the_report_says_whether_the_shipped_value_survives():
    r = V.run(legs(seed=3))
    out = V.report(r, 0.97)
    assert "CONTAINS" in out or "EXCLUDES" in out
    assert "shipped constant" in out


def test_it_refuses_to_edit_the_constant_it_checks():
    """Changing a constant inside the script that verifies it defeats the
    check. The script reports; a human decides."""
    import ast
    tree = ast.parse(open(V.__file__).read())
    assigned = {t.id for node in ast.walk(tree)
                if isinstance(node, ast.Assign)
                for t in node.targets if isinstance(t, ast.Name)}
    assert "TYPICAL_MOVE_PCT" not in assigned, \
        "the checker assigns the constant it is supposed to check"
    # and it must SAY so in the output when the two disagree, not just abstain
    out = V.report({"n": 300, "sessions": 39, "median": 0.69,
                    "ci": (0.58, 0.79), "mean": 0.86, "q1": 0.32, "q3": 1.17},
                   0.97)
    flat = " ".join(out.split())
    assert "Do not change it here" in flat
