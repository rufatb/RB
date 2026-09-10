"""Replication cannot select another winner or reuse the development sample."""
import copy
import pytest
import validate_pairs as V
import pairs as P


def panels():
    dev = {"best_cell": "distance@2.0", "sample": {
        "tickers": ["A"], "first_date": "2020-01-01", "last_date": "2021-12-31"}}
    hold = {"best_cell": "cointegration@1.5", "placebo": {"p95": 0.05},
            "cells": {"distance@2.0": {"net": 0.10, "t": 3.5},
                      "cointegration@1.5": {"net": 0.50, "t": 5.0}},
            "sample": {"tickers": ["A"], "first_date": "2022-01-01",
                       "last_date": "2023-12-31"}}
    return dev, hold


def test_holdouts_new_winner_cannot_rescue_development_selected_failure():
    dev, hold = panels()
    hold["cells"][dev["best_cell"]] = {"net": -0.1, "t": -4.0}
    result = V.assess_replication(dev, hold)
    assert not result["selected_cell_passes"] and not result["replicates"]


def test_same_issuer_date_sample_is_not_a_holdout():
    dev, hold = panels()
    hold["sample"] = copy.deepcopy(dev["sample"])
    result = V.assess_replication(dev, hold)
    assert result["selected_cell_passes"]
    assert not result["disjoint_observations"] and not result["replicates"]


def test_unknown_provenance_cannot_certify_replication():
    dev, hold = panels()
    del hold["sample"]
    assert not V.assess_replication(dev, hold)["replicates"]


def test_frozen_cell_can_replicate_in_later_observations():
    dev, hold = panels()
    assert V.assess_replication(dev, hold)["replicates"]


def test_mde80_exceeds_significance_threshold():
    rows = [{"t": i, "gross": x, "net": x - 0.1}
            for i, x in enumerate([0.2, -0.2, 0.3, -0.1] * 8)]
    r = V.summarise(rows, "synthetic")
    assert r["mde80"] == pytest.approx((3 + 0.8416212335729143) * r["se"])
    assert r["mde80"] > r["mde"]


@pytest.mark.parametrize("intraday", ["nan", "100"])
def test_panel_cannot_smuggle_missing_or_wrong_unit_returns(tmp_path, intraday):
    p = tmp_path / "panel.csv"
    p.write_text("t,date,open,close,intraday,volume\n"
                 f"A,2026-08-04,100,101,{intraday},1000\n")
    with pytest.raises(ValueError):
        P.load_wide(str(p))


def test_zero_return_beats_losses_and_finite_placebo_never_reports_zero_p(monkeypatch):
    import numpy as np
    wide = {"intraday": np.zeros((2, 4)), "tickers": np.array(list("ABCD")),
            "dates": np.array(["2026-08-04", "2026-08-05"]),
            "close": np.ones((2, 4)), "volume": np.ones((2, 4)),
            "dropped_incomplete": 0}
    monkeypatch.setattr(P, "load_wide", lambda p: wide)
    monkeypatch.setattr(P, "generate_signals", lambda w, m, t: [(m, t)])
    def returns(signals, intra, permute=None):
        net = 0.0 if signals == [("distance", 1.5)] and permute is None else -0.1
        return [dict(t=0, i=0, j=1, gross=net + 0.1, net=net)]
    monkeypatch.setattr(P, "attribute", returns)
    result = V.run("synthetic", draws=4, verbose=False)
    assert result["best_cell"] == "distance@1.5" and result["best"]["net"] == 0.0
    assert result["placebo"]["p_value"] == pytest.approx(1 / 5)
