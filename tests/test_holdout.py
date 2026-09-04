"""Day-86: the out-of-sample test of H5, and the guards that make it one.

The failure this study exists to avoid is subtle and would not look like an
error: re-running a hypothesis on a SUPERSET of the sample that produced it
reports a tighter interval around the same numbers and reads as confirmation.
The disjointness assertion is therefore load-bearing, not hygiene.
"""

import numpy as np
import pandas as pd
import pytest

import validate_holdout as H


def _panel(names, seed=0, n_days=60):
    rng = np.random.default_rng(seed)
    rows = []
    for d in range(n_days):
        for t in names:
            rows.append({"t": t, "date": f"2026-{1 + d // 28:02d}-{1 + d % 28:02d}",
                         "close": 100.0, "volume": 1e6, "open": 100.0,
                         "prev_close": 100.0, "overnight": rng.normal(),
                         "intraday": rng.normal(), "daily": rng.normal()})
    return pd.DataFrame(rows)


def test_a_leaked_name_stops_the_run(tmp_path, monkeypatch):
    """THE FAILURE THIS STUDY WAS BUILT TO AVOID."""
    monkeypatch.setattr(H, "DATA", str(tmp_path))
    _panel(["AAA", "BBB"]).to_csv(tmp_path / "us_daily.csv", index=False)
    _panel(["BBB", "CCC"]).to_csv(tmp_path / "us_daily_holdout.csv", index=False)
    with pytest.raises(H.SampleLeak) as e:
        H.load_split()
    assert "re-read the draw" in str(e.value)


def test_a_disjoint_split_loads(tmp_path, monkeypatch):
    monkeypatch.setattr(H, "DATA", str(tmp_path))
    _panel(["AAA", "BBB"]).to_csv(tmp_path / "us_daily.csv", index=False)
    _panel(["CCC", "DDD"]).to_csv(tmp_path / "us_daily_holdout.csv", index=False)
    df, orig = H.load_split()
    assert orig == {"AAA", "BBB"}
    assert set(df["t"]) == {"CCC", "DDD"}


def test_a_missing_panel_refuses_instead_of_defaulting(tmp_path, monkeypatch):
    monkeypatch.setattr(H, "DATA", str(tmp_path))
    with pytest.raises(FileNotFoundError):
        H.load_split()


# ── the registered gradient rule ───────────────────────────────────────────

def q(vals):
    return [(i, v, 0.05) for i, v in enumerate(vals)]


def test_an_effect_concentrated_in_small_caps_fails_the_gradient_rule():
    """Day-85's own size test ran -1.863 .. -0.475, which is 3.9x. Registered
    in advance as the survivorship signature."""
    v = H.gradient_verdict(q([-1.863, -1.235, -1.056, -0.475]))
    assert "FAILS the registered gradient rule" in v
    assert "3.9x" in v


def test_an_evenly_spread_effect_passes():
    assert H.gradient_verdict(q([-0.40, -0.35, -0.38, -0.33])).startswith("passes")


def test_a_sign_flip_across_quartiles_fails():
    assert "sign flips" in H.gradient_verdict(q([-0.4, -0.3, +0.2, -0.3]))


def test_a_missing_quartile_is_not_computable_not_a_failure():
    """Missing evidence is not adverse evidence."""
    out = H.gradient_verdict([(0, -0.4, 0.05), (1, None, None),
                              (2, -0.3, 0.05), (3, -0.2, 0.05)])
    assert "NOT COMPUTABLE" in out


def test_exactly_double_is_a_failure_the_boundary_is_not_generous():
    assert "FAILS" in H.gradient_verdict(q([-0.40, -0.30, -0.25, -0.20]))


# ── the sign is pre-committed ──────────────────────────────────────────────

def test_the_expected_sign_is_day_85s_and_is_negative():
    assert H.EXPECTED_SIGN == -1.0


def test_a_failed_replication_is_named_as_one_in_the_source():
    """An opposite-signed significant result is not a discovery."""
    flat = " ".join(open(H.__file__).read().split())
    assert "FAILED REPLICATION" in flat
    assert "not a discovery" in flat
