"""Synthetic audits of research correctness, not evidence for a market strategy."""

import numpy as np
import pandas as pd
import pytest

import r945
import validate_ceiling as vc


@pytest.mark.parametrize("case", ["balanced", "imbalanced", "constant", "ties", "clamped"])
def test_ceiling_knn_matches_live_scorer_including_prior_and_clamps(case):
    rng = np.random.default_rng(91)
    x = rng.normal(size=(350, 3))
    target = rng.integers(0, 2, len(x))
    test = rng.normal(size=(12, 3))
    if case == "imbalanced":
        target = (rng.random(len(x)) < .83).astype(int)
    elif case == "constant":
        x[:, 1], test[:, 1] = 2., 2.
    elif case == "ties":
        x = np.round(x)
        test = np.round(test)
    elif case == "clamped":
        target[:] = 1
    frame = pd.DataFrame(x, columns=r945.FEATS)
    frame["r1"] = np.where(target == 1, 1., -1.)
    expected = np.array([r945.knn_probability(frame, dict(zip(r945.FEATS, row)))[0]
                         for row in test])
    observed = vc.knn_scores(x, target, test)
    np.testing.assert_array_equal(observed, expected)
    if case == "clamped":
        np.testing.assert_array_equal(observed, np.full(len(test), r945.HARD_CAP))


def test_legacy_scorer_is_preserved_and_demonstrably_not_shipped():
    rng = np.random.default_rng(9)
    x = rng.normal(size=(300, 3))
    target = np.ones(len(x), dtype=int)
    test = np.zeros((1, 3))
    assert vc.legacy_knn_scores(x, target, test)[0] == pytest.approx(1.)
    assert vc.knn_scores(x, target, test)[0] == r945.HARD_CAP


def test_knn_abstains_with_insufficient_training_support():
    x = np.zeros((199, 3))
    target = np.zeros(len(x))
    assert np.isnan(vc.knn_scores(x, target, np.zeros((2, 3)))).all()
    frame = pd.DataFrame(x, columns=r945.FEATS).assign(r1=-1.)
    assert r945.knn_probability(frame, dict.fromkeys(r945.FEATS, 0.))[0] is None


@pytest.mark.parametrize("value", [np.nan, np.inf, -np.inf])
def test_nonfinite_feature_input_is_an_explicit_error(value):
    x = np.zeros((200, 3))
    x[0, 0] = value
    with pytest.raises(ValueError, match="finite"):
        vc.knn_scores(x, np.zeros(200), np.zeros((1, 3)))


def test_auc_influence_handles_ties_and_is_centered():
    labels = np.array([0, 0, 1, 1, 0, 1])
    scores = np.array([.1, .4, .4, .9, .9, .9])
    a, influence = vc.auc_influence(labels, scores)
    assert a == pytest.approx(vc.auc(labels, scores))
    assert influence.sum() == pytest.approx(0, abs=1e-12)
    assert influence[labels == 1].sum() == pytest.approx(0, abs=1e-12)
    assert influence[labels == 0].sum() == pytest.approx(0, abs=1e-12)


def synthetic_session_scores():
    rng = np.random.default_rng(72)
    sessions = np.repeat(np.arange(50), 12)
    labels = rng.integers(0, 2, len(sessions))
    scores = rng.normal(size=len(sessions)) + .1 * labels
    return labels, scores, sessions


def test_repeating_correlated_rows_does_not_inflate_session_precision():
    labels, scores, sessions = synthetic_session_scores()
    result = vc.auc_summary(labels, scores, sessions)
    repeated = vc.auc_summary(np.repeat(labels, 10), np.repeat(scores, 10),
                              np.repeat(sessions, 10))
    assert repeated["n"] == result["n"] * 10
    for key in ("auc", "se", "z", "mde80", "sessions"):
        assert repeated[key] == pytest.approx(result[key])
    assert vc.se_auc(np.repeat(labels, 10)) < vc.se_auc(labels) / 3


def test_cluster_se_matches_manual_session_sandwich():
    influence = np.array([.02, .03, -.01, -.01, -.01, -.02])
    sessions = np.repeat(["a", "b", "c"], 2)
    observed, n = vc.clustered_se(influence, sessions)
    expected = np.sqrt(3 / 2 * (.05 ** 2 + (-.02) ** 2 + (-.03) ** 2))
    assert n == 3
    assert observed == pytest.approx(expected)


def test_paired_auc_uses_covariance_and_identical_models_have_no_improvement():
    labels, scores, sessions = synthetic_session_scores()
    result = vc.auc_summary(labels, scores, sessions, reference=scores.copy())
    assert result["estimate"] == 0
    assert result["se"] == 0
    assert not result["valid_inference"]
    assert np.isnan(result["z"])
    assert np.isnan(result["mde80"])


def test_paired_auc_standard_error_uses_difference_of_influences():
    labels, scores, sessions = synthetic_session_scores()
    reference = scores + np.random.default_rng(4).normal(size=len(scores))
    result = vc.auc_summary(labels, scores, sessions, reference=reference)
    a, i = vc.auc_influence(labels, scores)
    b, j = vc.auc_influence(labels, reference)
    se, _ = vc.clustered_se(i - j, sessions)
    assert result["estimate"] == pytest.approx(a - b)
    assert result["se"] == pytest.approx(se)


def test_mde_increases_when_more_models_are_compared():
    labels, scores, sessions = synthetic_session_scores()
    single = vc.auc_summary(labels, scores, sessions, comparisons=1)
    many = vc.auc_summary(labels, scores, sessions, comparisons=5)
    from scipy.stats import norm
    assert many["mde80"] == pytest.approx(
        (norm.isf(.05 / 5) + norm.ppf(.8)) * many["se"])
    assert many["mde80"] > single["mde80"]
    assert many["lower_bound"] < single["lower_bound"]


def test_few_sessions_and_single_class_cannot_support_inference():
    labels, scores, sessions = synthetic_session_scores()
    few = sessions < 5
    result = vc.auc_summary(labels[few], scores[few], sessions[few])
    assert not result["valid_inference"]
    assert np.isnan(result["mde80"])
    single = vc.auc_summary(np.ones(len(labels)), scores, sessions)
    assert not single["valid_inference"]
    assert np.isnan(single["auc"])


def test_walk_forward_never_splits_sessions_or_uses_later_training_labels(monkeypatch):
    dates = pd.date_range("2020-01-01", periods=8).strftime("%Y-%m-%d")
    frame = pd.DataFrame({"date": np.repeat(dates, 100),
                          "r0": np.repeat(np.arange(8), 100),
                          "y": np.tile([0, 1], 400)})
    observed = []

    def fake_fit(x_train, y_train, x_test):
        assert x_train[:, 0].max() < x_test[:, 0].min()
        observed.append((set(x_train[:, 0]), set(x_test[:, 0])))
        return {"synthetic": np.full(len(x_test), .5)}

    monkeypatch.setattr(vc, "fit_models", fake_fit)
    result = vc.walk_forward(frame, ["r0"], folds=3, min_train=5)
    y, scores, sessions = result["synthetic"]
    assert len(observed) == 3
    assert set(sessions) == set(dates[5:])
    assert len(y) == len(scores) == len(sessions) == 300
    assert pd.Series(sessions).value_counts().eq(100).all()


def test_unsupported_fold_is_not_silently_skipped():
    frame = pd.DataFrame({"date": np.repeat(np.arange(8), 2),
                          "r0": np.arange(16), "y": np.tile([0, 1], 8)})
    with pytest.raises(ValueError, match="500/nonempty"):
        vc.walk_forward(frame, ["r0"], folds=3, min_train=5)


def volume_pool(volumes):
    n = len(volumes)
    return pd.DataFrame({"t": ["SYNTHETIC"] * n,
                         "date": pd.date_range("2020-01-01", periods=n).strftime("%Y-%m-%d"),
                         "v15": volumes, "px": 10., "r0": .1, "gap": -.2,
                         "r1": np.resize([.2, -.2], n)})


def test_feature_availability_never_uses_test_period_volume(tmp_path):
    frame = volume_pool([1000.] * 20 + [0.] * 10)
    path = tmp_path / "pool.csv"
    frame.to_csv(path, index=False)
    data, feats = vc.load_pool(str(path), feature_train_sessions=20, as_of="2021-01-01")
    assert "vp" in feats  # future zero bars cannot change the initial feature set
    assert len(data) == 10
    assert data["vp"].eq(0).all()


def test_missing_initial_volume_is_not_rescued_using_future_availability(tmp_path):
    frame = volume_pool([0.] * 20 + [1000.] * 30)
    path = tmp_path / "pool.csv"
    frame.to_csv(path, index=False)
    _, feats = vc.load_pool(str(path), feature_train_sessions=20, as_of="2021-01-01")
    assert feats == ["r0", "gap"]


def test_current_and_future_outcomes_are_excluded_even_if_present(tmp_path, capsys):
    frame = volume_pool([0.] * 25)
    path = tmp_path / "pool.csv"
    frame.to_csv(path, index=False)
    data, _ = vc.load_pool(str(path), feature_train_sessions=20, as_of="2020-01-22")
    assert data["date"].max() == "2020-01-21"
    assert "excluding 4 current/future rows" in capsys.readouterr().out


def test_duplicate_ticker_sessions_fail_explicitly(tmp_path):
    frame = volume_pool([0.] * 25)
    frame = pd.concat([frame, frame.iloc[:1]])
    path = tmp_path / "pool.csv"
    frame.to_csv(path, index=False)
    with pytest.raises(ValueError, match="duplicate ticker/session"):
        vc.load_pool(str(path), as_of="2021-01-01")


def test_a_model_above_chance_but_worse_than_knn_is_not_an_improvement(monkeypatch, capsys):
    rng = np.random.default_rng(13)
    y = rng.integers(0, 2, 2000)
    noise = rng.normal(size=len(y))
    sessions = np.repeat(np.arange(100), 20)
    from scipy.special import expit
    rows = {
        "baseline": (y, np.full(len(y), .5), sessions),
        vc.KNN_NAME: (y, expit(noise + 1.2 * y), sessions),
        "logistic": (y, expit(noise + .9 * y), sessions),
        "grad boost": (y, expit(noise + .7 * y), sessions),
    }
    frame = pd.DataFrame({"t": ["SYNTHETIC"] * len(y), "date": sessions, "y": y})
    monkeypatch.setattr(vc, "load_pool", lambda *args, **kwargs: (frame, ["r0"]))
    monkeypatch.setattr(vc, "walk_forward", lambda *args, **kwargs: rows)
    assert vc.main(["--pool", "synthetic-only.csv"]) == 0
    output = capsys.readouterr().out
    assert "NO CORRECTED PAIRED IMPROVEMENT DETECTED" in output
    assert "EXPLORATORY candidates exceeding" not in output
    assert "MDE80 is an AUC difference" in output
