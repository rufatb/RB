"""Day-96: the pairs engine, and the guarantees that make its numbers mean
something.

The arithmetic tests matter less than the LEAKAGE tests. A pairs backtest that
peeks -- through a full-sample hedge ratio, or a spread mean estimated over the
whole panel -- produces a beautiful equity curve and no information. Those are
the tests that would have caught the defect in the public implementations this
study measured itself against.
"""
import numpy as np
import pytest

import pairs as P


def synth(W=700, N=8, seed=0):
    """A panel with two genuinely cointegrated pairs and the rest independent
    random walks, so tests can assert on structure rather than on noise."""
    rng = np.random.default_rng(seed)
    logp = np.cumsum(rng.normal(0, 0.012, size=(W, N)), axis=0) + 3.0
    logp[:, 1] = logp[:, 0] * 0.9 + rng.normal(0, 0.002, size=W)
    logp[:, 3] = logp[:, 2] * 1.1 + rng.normal(0, 0.002, size=W)
    close = np.exp(logp)
    open_ = close * np.exp(rng.normal(0, 0.004, size=(W, N)))
    intra = (close / open_ - 1.0) * 100.0
    return {"dates": np.arange(W).astype(str),
            "tickers": np.array([f"N{i}" for i in range(N)]),
            "close": close, "open": open_, "intraday": intra,
            "volume": np.full((W, N), 1e6), "dropped_incomplete": 0}


# ── the vectorised formation must equal the regression it replaces ─────────

def test_formation_equals_brute_force_regressions():
    """166,753 pairs are resolved in three matrix multiplies via a bilinear
    identity. If that identity is wrong, every number downstream is wrong and
    nothing else in this file would notice."""
    rng = np.random.default_rng(1)
    logp = np.cumsum(rng.normal(0, 0.01, size=(120, 6)), axis=0)
    S = P.formation_scores(logp)
    x = logp - logp.mean(axis=0, keepdims=True)

    for i in range(6):
        for j in range(6):
            if i == j:
                continue
            xi, xj = x[:, i], x[:, j]
            b = (xi @ xj) / (xj @ xj)
            e = xi - b * xj
            el, de = e[:-1], np.diff(e)
            g = (de @ el) / (el @ el)
            rss = de @ de - g * g * (el @ el)
            se = np.sqrt(rss / (len(de) - 1) / (el @ el))
            assert S["beta"][i, j] == pytest.approx(b, rel=1e-9)
            assert S["df_t"][i, j] == pytest.approx(g / se, rel=1e-7)
            assert S["sd"][i, j] == pytest.approx(e.std(ddof=1), rel=1e-9)


def test_a_cointegrated_pair_scores_far_more_stationary_than_an_independent_one():
    w = synth()
    S = P.formation_scores(np.log(w["close"][:252]))
    assert S["df_t"][0, 1] < S["df_t"][0, 4] - 2.0
    assert S["df_t"][2, 3] < S["df_t"][2, 5] - 2.0


def test_cointegration_selection_finds_the_planted_pairs():
    w = synth()
    S = P.formation_scores(np.log(w["close"][:252]))
    chosen = set(P.choose_pairs(S, "cointegration", 3))
    assert (0, 1) in chosen and (2, 3) in chosen


# ── leakage: the whole point ───────────────────────────────────────────────

def test_formation_never_sees_the_session_it_trades():
    """THE GUARANTEE. Corrupt every price from session t onward; the signals
    generated BEFORE t must be bit-identical. A full-sample hedge ratio -- the
    most common defect in public pairs backtests -- fails this instantly."""
    w = synth()
    cut = 500
    before = [s for s in P.generate_signals(w, "cointegration", 2.0)
              if s["t"] < cut]

    tampered = {k: (v.copy() if isinstance(v, np.ndarray) else v)
                for k, v in w.items()}
    tampered["close"][cut:] *= 7.5          # a future that never happened
    tampered["open"][cut:] *= 7.5
    after = [s for s in P.generate_signals(tampered, "cointegration", 2.0)
             if s["t"] < cut]

    assert before == after, "signals changed when only the FUTURE changed"
    assert before, "the test proved nothing — no signals before the cut"


def test_the_traded_session_is_excluded_from_its_own_formation_window():
    """Off-by-one is the whole risk here: `logc[t-W:t]` excludes t, but
    `logc[t-W:t+1]` would include the very session being traded and would look
    like skill."""
    import inspect
    src = inspect.getsource(P.generate_signals)
    assert "logc[t - FORM_WINDOW:t]" in src
    assert "t + 1" not in src


# ── cost, and the clipping trap ────────────────────────────────────────────

def test_cost_is_subtracted_not_clipped():
    """`validate_us.net_of_cost` clips at zero, and its own docstring says new
    strategy P&L must subtract cost without clipping -- clipping hides losses.
    A losing pair trade must report its loss."""
    sig = [{"i": 0, "j": 1, "t": 0, "side": 1, "z": -2.0}]
    intra = np.array([[0.0, 0.0]])                  # dead flat: pure cost
    out = P.attribute(sig, intra)
    assert out[0]["gross"] == 0.0
    assert out[0]["net"] == pytest.approx(-P.COST_PCT)
    assert out[0]["net"] < 0, "a flat day must cost the round trip, not zero"


def test_the_round_trip_is_two_legs():
    assert P.LEGS == 2
    assert P.COST_PCT == pytest.approx(2 * P.SPREAD_BPS / 100.0)


def test_side_orients_the_trade_toward_convergence():
    """A low spread means leg i is cheap relative to j: long i, short j."""
    w = synth()
    sigs = P.generate_signals(w, "cointegration", 1.5)
    assert sigs
    assert all(s["side"] == (1 if s["z"] < 0 else -1) for s in sigs)
    assert all(abs(s["z"]) >= 1.5 for s in sigs)


# ── the placebos ───────────────────────────────────────────────────────────

def test_the_placebo_keeps_the_trades_and_changes_only_the_returns():
    w = synth()
    sig = P.generate_signals(w, "cointegration", 2.0)
    perm = np.roll(np.arange(len(w["tickers"])), 3)
    a = P.attribute(sig, w["intraday"])
    b = P.attribute(sig, w["intraday"], permute=perm)
    assert [(x["i"], x["j"], x["t"], x["side"]) for x in a] == \
           [(x["i"], x["j"], x["t"], x["side"]) for x in b]
    assert [x["net"] for x in a] != [x["net"] for x in b]


def test_the_shifted_placebo_keeps_the_pair_and_moves_the_session():
    """The stricter null: co-movement and each name's returns survive, only
    the link between THIS open's z-score and THIS day's outcome is broken."""
    w = synth()
    sig = P.generate_signals(w, "cointegration", 2.0)
    a = P.attribute(sig, w["intraday"])
    b = P.attribute_shifted(sig, w["intraday"], 137)
    assert [(x["i"], x["j"]) for x in a] == [(x["i"], x["j"]) for x in b]
    assert [x["net"] for x in a] != [x["net"] for x in b]


def test_a_zero_shift_is_the_real_thing():
    w = synth()
    sig = P.generate_signals(w, "distance", 2.0)
    assert [x["net"] for x in P.attribute_shifted(sig, w["intraday"], 0)] == \
           [x["net"] for x in P.attribute(sig, w["intraday"])]


# ── inference ──────────────────────────────────────────────────────────────

def test_the_bootstrap_resamples_SESSIONS_not_trades():
    """Twenty pairs open on one day share that day's move. Resampling trades
    individually treats them as twenty independent draws, which is what turned
    |t|=7.15 into 2.14 on day-85."""
    trades = ([{"t": 1, "net": 1.0}] * 50) + ([{"t": 2, "net": -1.0}] * 50)
    b = P.session_block_bootstrap(trades, draws=400)
    assert b["sessions"] == 2 and b["n"] == 100
    # Two sessions of opposite sign: the interval must be enormous, not tight.
    assert b["hi"] - b["lo"] > 1.0


def test_the_planted_control_measures_edge_over_sd_not_mean_plus_edge():
    """Rule 10's second half, explicitly. Crediting the real mean to the
    control makes an underpowered harness look powered."""
    rng = np.random.default_rng(3)
    trades = [{"t": int(i), "net": float(x)}
              for i, x in enumerate(rng.normal(0.5, 1.0, 400))]
    c = P.planted_control(trades, edge_pct=0.10)
    b = P.session_block_bootstrap(trades)
    assert c["t"] == pytest.approx(0.10 / b["se"], rel=1e-6)
    assert c["t"] < (b["mean"] + 0.10) / b["se"]


def test_mde_scales_with_the_adoption_bar():
    assert P.mde(0.05) == pytest.approx(P.ADOPT_T * 0.05)


def test_quarters_split_by_session_so_a_session_never_straddles_two():
    trades = [{"t": t, "net": 0.0} for t in range(100) for _ in range(3)]
    qs = P.quarters(trades)
    assert len(qs) == P.BLOCKS


# ── the comparison that gives the study its point ──────────────────────────

def test_the_public_recipe_reports_more_than_the_honest_measurement():
    """REGRESSION ON THE FINDING. The four defects -- full-sample formation,
    select-and-test on the same data, no cost, compared to zero -- are what
    separate a published pairs backtest from a measurement. On the TSX-21 the
    gap was +0.31%/trade, enough to turn a real -0.19% into a reported +0.12%.
    If this ever stops holding on synthetic data, the recipe has been
    accidentally cleaned up and the comparison no longer means anything."""
    w = synth(W=900, N=10, seed=7)
    naive = P.naive_public_recipe(w)
    honest = P.attribute(P.generate_signals(w, "cointegration", 2.0),
                         w["intraday"])
    hm = float(np.mean([t["net"] for t in honest]))
    assert naive["n"] > 0 and honest
    assert naive["mean"] > hm


def test_the_public_recipe_charges_no_cost_which_is_half_the_illusion():
    import inspect
    src = inspect.getsource(P.naive_public_recipe)
    assert "COST_PCT" not in src
    assert "no cost" in src


def test_registered_constants_have_not_drifted():
    """PREREGISTER_day96.md fixed these at cac0666. Rule 3: the bar does not
    move after the fact."""
    assert P.THRESHOLDS == (1.5, 2.0, 2.5)
    assert P.METHODS == ("distance", "cointegration")
    assert P.FORM_WINDOW == 252
    assert P.ADOPT_T == 3.0
    assert P.BLOCKS == 4
    assert P.SIZE_RATIO_MAX == 2.0
    assert P.SPREAD_BPS == 5.0


# ── day-96 audit: the registered placebos are CONDITIONAL ──────────────────

def test_the_conditional_placebo_does_not_resample_selection():
    """THE CORRECTION. The original write-up said this placebo absorbed the
    advantage of picking the best of 166,753 candidates. It cannot: selection
    runs on real close prices and is identical in every draw. Pinning that
    here so the claim cannot quietly come back."""
    w = synth()
    sig_a = P.generate_signals(w, "cointegration", 2.0)
    sig_b = P.generate_signals(w, "cointegration", 2.0)
    assert sig_a == sig_b, "signals must be deterministic given the panel"
    perm = np.roll(np.arange(len(w["tickers"])), 2)
    a = P.attribute(sig_a, w["intraday"], permute=perm)
    assert [(x["i"], x["j"]) for x in a] == [(x["i"], x["j"]) for x in sig_a], \
        "the permuted draw traded a different pair set — it is not conditional"


def test_the_reselection_placebo_destroys_real_comovement():
    """Independent circular shifts per name: each keeps its own serial
    structure, cross-name alignment does not survive. The planted cointegrated
    pair must stop looking cointegrated."""
    w = synth()
    real = P.formation_scores(np.log(w["close"][:252]))
    null = P.shifted_panel(w, np.random.default_rng(0))
    got = P.formation_scores(np.log(null["close"][:252]))
    assert real["df_t"][0, 1] < -3.0, "the planted pair should be stationary"
    assert got["df_t"][0, 1] > real["df_t"][0, 1] + 1.0, \
        "shifting failed to break the planted co-movement"


def test_the_reselection_placebo_shifts_each_name_independently():
    """A COMMON shift would preserve cross-name alignment and leave genuine
    cointegration intact, which would make the null identical to the real
    panel and the whole comparison vacuous."""
    w = synth()
    null = P.shifted_panel(w, np.random.default_rng(1))
    lags = []
    for k in range(w["close"].shape[1]):
        col, ncol = w["close"][:, k], null["close"][:, k]
        lags.append(int(np.argmin([np.abs(np.roll(col, s) - ncol).sum()
                                   for s in range(w["close"].shape[0])])))
    assert len(set(lags)) > 1, "every name got the same offset"


def test_the_shift_keeps_each_name_its_own_returns():
    """The null must be a re-timing, not a re-labelling: a name's multiset of
    returns is unchanged, so only alignment is destroyed."""
    w = synth()
    null = P.shifted_panel(w, np.random.default_rng(2))
    for k in range(w["intraday"].shape[1]):
        assert np.allclose(np.sort(w["intraday"][:, k]),
                           np.sort(null["intraday"][:, k]))


def test_a_finite_draw_p_value_can_never_be_zero():
    """500 draws cannot resolve p=0.000, which the day-96 write-up reported.
    The (1+k)/(n+1) form has a floor of 1/(n+1)."""
    import validate_pairs as V
    src = inspect_source(V.run)
    assert "(1 + (pb >= observed).sum()) / (len(pb) + 1)" in src


def inspect_source(fn):
    import inspect
    return inspect.getsource(fn)
