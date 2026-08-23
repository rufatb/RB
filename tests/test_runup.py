"""Day-72: is there a week-to-month trade BEFORE an FDA decision?

Day-68 measured what happens ON the decision, and a PM cannot act on either
outcome without knowing which arrives. This asks the earlier question, whose
answer is a position you can actually size. These lock the two ways the test
could flatter itself: letting the print inside the window, and reporting sector
beta as an edge.
"""

import numpy as np
import pandas as pd
import pytest

import validate_runup as R


def _series(n=300, start="2024-01-02", drift=0.0):
    idx = pd.bdate_range(start, periods=n)
    p = 100 * np.cumprod(1 + np.full(n, drift))
    return pd.Series(p, index=idx)


def test_the_window_stops_two_sessions_before_the_print():
    """An 8-K filed the morning after an after-close announcement puts the
    reaction on t-1, so a window running to t-1 can contain the binary -- the
    exact thing this test exists to exclude."""
    p = np.full(60, 100.0)
    p[58] = 200.0                      # the reaction, at i-1
    p[59] = 200.0                      # and at i
    b = np.full(60, 100.0)
    v = R._rel(p, 59, 20, b, 59)
    assert v == 0.0                    # the window ends at i-2 and is clean

    inside = np.full(60, 100.0)
    inside[57] = 200.0                 # a move at i-2 IS in the window
    assert R._rel(inside, 59, 20, b, 59) > 0


def test_the_benchmark_is_subtracted_so_sector_beta_is_not_an_edge():
    """A +4% month when XBI rose 5% is not a run-up, it is beta."""
    p = np.full(60, 100.0)
    p[57] = 104.0
    b = np.full(60, 100.0)
    b[57] = 105.0
    v = R._rel(p, 59, 20, b, 59)
    assert v < 0                       # underperformed its sector


def test_no_benchmark_means_no_number_rather_than_a_raw_return():
    p = np.full(60, 100.0)
    assert R._rel(p, 59, 20, None, None) is None


def test_a_short_history_yields_nothing_rather_than_a_partial_window():
    p = np.full(10, 100.0)
    b = np.full(10, 100.0)
    assert R._rel(p, 5, 20, b, 5) is None


def test_a_thin_sample_refuses_to_produce_a_z_score():
    """Fewer than thirty events is not a measurement."""
    d = pd.DataFrame({"date": pd.to_datetime(["2024-01-02"] * 5),
                      "h20": [1.0, 2.0, 3.0, 4.0, 5.0]})
    r = R.clustered_mean(d, "h20", boot=50)
    assert r["n"] == 5 and r["z"] != r["z"]        # NaN, not a number


def test_the_bootstrap_clusters_on_the_event_date():
    """Several sponsors can share a decision date and biotech moves together in
    any given week. Resampling rows would treat one week as many independent
    observations of a month-long drift."""
    same = pd.DataFrame({"date": pd.to_datetime(["2024-01-02"] * 60),
                         "h20": np.r_[np.full(30, 5.0), np.full(30, -5.0)]})
    spread = pd.DataFrame({"date": pd.bdate_range("2024-01-02", periods=60),
                           "h20": np.r_[np.full(30, 5.0), np.full(30, -5.0)]})
    a = R.clustered_mean(same, "h20", boot=300)
    b = R.clustered_mean(spread, "h20", boot=300)
    # one date = one observation, so its bootstrap cannot resolve anything
    assert a["sd"] == 0 or a["sd"] > b["sd"]


def test_power_measures_detectability_not_the_samples_own_drift():
    """The first version added the edge and reported the SHIFTED sample's z --
    (base mean + edge)/sd, not edge/sd. With a base drift of +2.5% it printed
    z=1.92 for a 1% plant, which says nothing about detectability."""
    rng = np.random.default_rng(0)
    x = rng.normal(0.0, 8.0, 200)
    idx = pd.bdate_range("2024-01-02", periods=200)
    quiet = pd.DataFrame({"date": idx, "h20": x})
    drifting = pd.DataFrame({"date": idx, "h20": x + 50.0})   # same noise
    a = R.power(quiet, "h20", edge=1.0, boot=300)
    b = R.power(drifting, "h20", edge=1.0, boot=300)
    # detectability depends ONLY on dispersion, never on the sample's own level
    assert abs(a["z_for_edge"] - b["z_for_edge"]) < 1e-9
    assert abs(a["mde"] - R.BAR_Z * a["sd"]) < 1e-9


def test_an_underpowered_sample_is_not_reported_as_a_null():
    """Rule 4: a harness that cannot detect a planted edge cannot report a
    null. Saying 'no effect' when the MDE exceeds any tradeable drift is a
    claim the data cannot support."""
    noisy = pd.DataFrame({"date": pd.bdate_range("2024-01-02", periods=100),
                          "h20": np.random.default_rng(1).normal(0, 40, 100)})
    p = R.power(noisy, "h20", edge=1.0, boot=200)
    assert not p["detectable"]
    real = {h: R.clustered_mean(noisy, "h20", boot=100) for h in R.HORIZONS}
    out = R.report(real, {}, p, {})
    assert "UNDERPOWERED" in out and "NOT a rejection" in out
    assert "REJECT" not in out


def test_the_bar_is_raised_for_having_asked_four_horizons():
    assert R.BAR_Z > 3.0 and len(R.HORIZONS) == 4


def test_the_module_states_the_look_ahead_it_cannot_remove():
    """The sample is dated by the decision that landed; a live entry uses the
    disclosed PDUFA date, which moves."""
    assert "UPPER BOUND" in R.__doc__
    assert "PDUFA goal date" in R.__doc__
