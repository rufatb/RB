"""Day-81: the fair-value diagnostics, with planted positive controls.

Day-80 shipped a warning that named a mechanism it could not detect. It said a
single past crash inflates the EMPIRICAL estimate; on planted controls a crash
inflates the LOGNORMAL one, and does not even clear the gap bar. "No live name
trips the tolerance" was then reported as reassurance when it was the reading a
misaimed diagnostic returns.

So every diagnostic here is required to FIRE on its own planted defect and stay
QUIET on the others. Rule 4: a harness that cannot detect a planted edge cannot
report a null. Bars are pre-registered in PREREGISTER_day81.md.
"""

import numpy as np

import fairvalue as F


def series(seed=7, n=900, sd=0.008, drift=0.0, crash=None, recentre=True):
    """A price path with a KNOWN defect, or none.

    The realised drift is forced to the target AFTER the crash is planted, so
    each control varies exactly one thing. That matters: a -55% day is both a
    fat tail and a permanent level shift, and left uncorrected it trips the
    drift bar too — real, but it would stop the crash case from isolating the
    tail. `recentre=False` keeps the realistic version, tested separately.
    """
    rng = np.random.default_rng(seed)
    r = rng.normal(drift, sd, n)
    if crash is not None:
        r[n // 2] = crash
    if recentre:
        r = r - r.mean() + drift
    return 100 * np.cumprod(1 + r)


CLEAN = series()
DRIFTY = series(drift=-0.000567)          # about -40% over the history
CRASHED = series(crash=-0.55)             # one -55% day, drift held at zero
CRASHED_RAW = series(crash=-0.55, recentre=False)   # crash AND its level shift


# ── the controls ────────────────────────────────────────────────────────────

def test_clean_control_trips_nothing():
    """The null case. If this fires, every warning below is noise."""
    c = F.cross_check(CLEAN, 21, F.put_fair_value(CLEAN, 21, seed=1))
    assert c["blame"] == "", c["why"]
    assert abs(c["drift"]) < F.DRIFT_TOL * 100
    assert not c["tail"]["heavy"]


def test_planted_crash_is_caught_and_blamed_on_the_lognormal():
    """The case day-80 was built for and could not see.

    Its gap is only ~22%, under DISAGREE_TOL, so the old check printed nothing.
    """
    c = F.cross_check(CRASHED, 21, F.put_fair_value(CRASHED, 21, seed=1))
    assert c["tail"]["heavy"]
    assert c["blame"] == "LOGNORMAL", "the tail must not be blamed on drift"
    assert c["tail"]["drop"] > 0.5


def test_both_faults_are_named_when_both_are_present():
    """A real crash is a fat tail AND a level shift. Report both, not the first.

    Reporting only the first match would narrow the finding silently — the
    same fault as day-80, one layer down. Four of five live names trip both.
    """
    c = F.cross_check(CRASHED_RAW, 21, F.put_fair_value(CRASHED_RAW, 21, seed=1))
    legs = [leg for leg, _ in c["faults"]]
    assert legs == ["LOGNORMAL", "EMPIRICAL"]
    assert "and" in c["why"]


def test_a_crash_inflates_the_lognormal_not_the_empirical():
    """The day-80 docstring asserted the opposite. Direction, pinned."""
    e_clean = F.put_fair_value(CLEAN, 21, seed=1)
    e_crash = F.put_fair_value(CRASHED, 21, seed=1)
    l_clean = F.lognormal_put(F.realised_vol(CLEAN), 21)
    l_crash = F.lognormal_put(F.realised_vol(CRASHED), 21)
    assert (l_crash / l_clean) > (e_crash / e_clean)


def test_planted_drift_is_caught_and_blamed_on_the_empirical():
    c = F.cross_check(DRIFTY, 21, F.put_fair_value(DRIFTY, 21, seed=1))
    assert c["drifty"] and c["blame"] == "EMPIRICAL"
    assert not c["tail"]["heavy"], "drift must not masquerade as a tail"


def test_the_two_defects_cancel_in_the_gap():
    """Why a single tolerance could never have worked, in one measurement.

    Each defect ALONE opens a ~43% gap. Together they open 14% — under the
    0.40 bar — because a crash's level shift lifts the empirical leg while its
    own fat tail lifts the lognormal leg, and the two subtract. The worst name
    on the board reads as the cleanest. Gap magnitude is not a diagnostic.
    """
    g = {n: F.cross_check(s, 21, F.put_fair_value(s, 21, seed=1))["gap"]
         for n, s in (("drift", DRIFTY), ("tail", CRASHED),
                      ("both", CRASHED_RAW))}
    assert g["drift"] > 0.40 and g["tail"] > 0.40
    assert g["both"] < 0.40
    assert g["both"] < min(g["drift"], g["tail"]) / 2


def test_the_demoted_trim_check_is_flat_on_both_defects():
    """Kept in the file, so keep the reason it proves nothing on its own."""
    for s in (CLEAN, CRASHED):
        e = F.put_fair_value(s, 21, seed=1)
        t = F.trimmed_fv(s, 21, seed=1)
        assert abs(e - t) / t < 0.10


# ── the estimators themselves ───────────────────────────────────────────────

def test_lognormal_matches_the_closed_form_for_a_driftless_normal():
    """E[max(0,-r)] = sigma_T / sqrt(2pi) when there is no drift."""
    v, h = 0.30, 21
    approx = 0.3989 * v * np.sqrt(h / 252) * 100
    assert abs(F.lognormal_put(v, h) - approx) / approx < 0.01


def test_fair_value_rises_with_horizon():
    a = F.put_fair_value(CLEAN, 5, seed=1)
    b = F.put_fair_value(CLEAN, 63, seed=1)
    assert b > a


def test_short_history_returns_none_rather_than_a_guess():
    assert F.put_fair_value(CLEAN[:30], 21) is None
    assert F.fair_put(CLEAN[:30], 21) is None


def test_the_event_leg_is_an_increment_not_the_whole_multiple():
    """own3 * (mult - 1). Using own3 * mult would double-count the ordinary."""
    fv = F.fair_put(CLEAN, 21)
    m = F.EVENT_MULT[fv["bucket"]]
    assert abs(fv["event"] - fv["own3"] * (m - 1.0)) < 1e-9
    assert fv["fair"] > fv["ordinary"]


def test_verdict_boundaries_and_the_unpriced_fallback():
    fv = F.fair_put(CLEAN, 21)
    f = fv["fair"]
    assert F.verdict(f * 0.5, fv)[0].startswith("CHEAP")
    assert F.verdict(f * 1.0, fv)[0] == "roughly FAIR"
    assert F.verdict(f * 2.0, fv)[0].startswith("RICH")
    assert F.verdict(None, fv)[0] == "unpriced"
    assert F.verdict(3.0, None)[0] == "unpriced"


def test_render_says_what_is_measured_and_what_is_not():
    # normalised: the sentence wraps, and where it wraps changed when the
    # sample description was corrected on day-82
    out = " ".join(" ".join(F.render(4.0, F.fair_put(CLEAN, 21), 21)).split())
    assert "NOT backtested" in out
    assert "FAIR VALUE is measured" in out


def test_render_warns_on_a_planted_crash():
    fv = F.fair_put(CRASHED, 21)
    out = "\n".join(F.render(4.0, fv, 21))
    assert "⚠" in out and "lognormal" in out.lower()


def test_the_sample_description_matches_what_the_script_actually_draws():
    """`N_RANDOM = 7440` was printed as "measured on ... 7,440 random windows"
    and no committed script produced it — a day-79 figure from a study whose
    code was never committed, asserted long after it stopped being derivable.
    """
    import validate_eventmult as V
    assert not hasattr(F, "N_RANDOM"), "the unprovenanced figure came back"
    assert F.BOOT_REPLICATES == V.BOOT
    assert F.RESAMPLES_PER_NAME == 240      # put_fair_value's default
    out = "\n".join(F.render(4.0, F.fair_put(CLEAN, 21), 21))
    assert "7,440" not in out
    assert "bootstrap replicates" in out


def test_the_module_docstring_retracts_the_figure_rather_than_asserting_it():
    """A docstring asserting what the code does not do is the same defect one
    layer up, and it is where the claim survived longest.

    The number may still APPEAR — saying "this said 7,440 until day-82" is how
    the record is kept — but only inside the retraction. Asserting its mere
    absence would have forced deleting the explanation along with the claim.
    """
    doc = " ".join((F.__doc__ or "").split())
    if "7,440" in doc:
        i = doc.index("7,440")
        context = doc[max(0, i - 120):i + 160]
        assert "until day-82" in context, "the figure is asserted, not retracted"
        assert "no committed script produces" in context
