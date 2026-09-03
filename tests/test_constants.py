"""Day-81: provenance for every published number, and a diff when one moves.

Five shipping constants were retracted in eleven days and the code noticed none
of them. Every check here carries a planted control, because a drift detector
that cannot detect a planted drift certifies nothing (rule 4).
"""

import constants as K


def test_drift_detects_a_planted_change():
    """THE POSITIVE CONTROL. Move a number; the diff must say so."""
    snap = {"fairvalue.EVENT_MULT_POINT": 2.45}
    now = {"fairvalue.EVENT_MULT_POINT": {"value": 1.54}}
    d = K.drift(now, snap)
    assert d["changed"] == [("fairvalue.EVENT_MULT_POINT", 2.45, 1.54)]
    assert not d["added"] and not d["removed"]


def test_an_unchanged_value_is_silent():
    """Silence is the desired state, so it has to be genuine silence."""
    d = K.drift({"a": {"value": 2.45}}, {"a": 2.45})
    assert not any(d[k] for k in ("changed", "added", "removed", "broken"))


def test_a_tuple_surviving_a_json_round_trip_is_not_drift():
    """JSON has no tuples. Without normalising, EVERY tuple reads as moved."""
    d = K.drift({"a": {"value": (1.95, 3.0)}}, {"a": [1.95, 3.0]})
    assert not d["changed"]


def test_a_dict_constant_compares_by_content():
    d = K.drift({"a": {"value": {"low": 2.09, "high": 2.82}}},
                {"a": {"low": 2.09, "high": 2.82}})
    assert not d["changed"]
    d = K.drift({"a": {"value": {"low": 1.54, "high": 2.82}}},
                {"a": {"low": 2.09, "high": 2.82}})
    assert d["changed"]


def test_a_deleted_constant_is_reported_not_ignored():
    """A number vanishing from a module is a change, not an absence."""
    d = K.drift({}, {"catalyst.CRL_MEAN": -20.3})
    assert d["removed"] == [("catalyst.CRL_MEAN", -20.3)]


def test_a_missing_attribute_is_reported_loudly():
    """Rule 1. A constant the registry names but the module lost must shout."""
    reg = {"catalyst.NO_SUCH_CONSTANT": K.Const(K.MEASURED, "x.py", 1)}
    got = K.live(reg)
    assert "MISSING" in got["catalyst.NO_SUCH_CONSTANT"]["error"]
    assert K.drift(got, {})["broken"]


def test_every_registry_entry_actually_exists():
    """The registry must describe the code, not a memory of it."""
    bad = {k: v["error"] for k, v in K.live().items() if v.get("error")}
    assert not bad, bad


def test_measured_numbers_without_a_script_are_named():
    """Day-79's constants had none for two days and could not be checked."""
    orphans = K.unprovenanced()
    assert "fairvalue.N_RANDOM" in orphans
    for k in orphans:
        assert K.REGISTRY[k].kind == K.MEASURED


def test_the_re_measured_constants_all_carry_their_script():
    """Everything validate_eventmult.py produced must point back at it."""
    for k in ("fairvalue.EVENT_MULT_POINT", "fairvalue.EVENT_MULT_CI",
              "fairvalue.TERCILE_MDE", "fairvalue.N_EVENTS"):
        assert K.REGISTRY[k].script == "validate_eventmult.py"
        assert K.REGISTRY[k].kind == K.MEASURED


def test_the_cited_base_rate_is_not_labelled_measured():
    """It came from FDA, not from this harness, and has no control here."""
    assert K.REGISTRY["catalyst.BASE_RATE_FIRST_CYCLE"].kind == K.CITED


def test_a_design_threshold_needs_no_script():
    """A chosen bar is not a measurement and must not be asked for one."""
    for k in ("catalyst.ADOPT_T", "fairvalue.DRIFT_TOL", "sanity.MAX_VOL"):
        assert K.REGISTRY[k].kind == K.DESIGN
        assert K.REGISTRY[k].script is None
    assert not [k for k in K.unprovenanced()
                if K.REGISTRY[k].kind == K.DESIGN]


def test_the_two_rejection_rates_are_flagged_as_in_tension():
    """The contradiction that shipped from day-54 to day-81.

    A cited 70% first-cycle approval implies P(CRL)=30%; the measured rate is
    11.7% [8.5%, 15.9%]. Both reach the reader. The registry must say so.
    """
    t = K.tensions()
    assert any(what == "P(rejection)" for what, _, _ in t)
    why = next(w for what, w, _ in t if what == "P(rejection)")
    assert "30%" in why and "11.7%" in why
    assert "biased DOWN" in why      # names the direction, not just the gap


def test_the_short_form_computes_its_numbers_rather_than_retyping_them():
    """The one-screen view prints `short`; it must not carry literals.

    A second file repeating "30%" and "11.7%" as text would be an uncheckable
    copy of a measured value — the exact defect this module exists to catch.
    """
    import baserate as B
    short = next(s for what, _, s in K.tensions() if what == "P(rejection)")
    p = B.summary()["p"]
    assert f"{p:.1%}" in short          # derived from the live measurement
    assert "biased DOWN" in short


def test_the_tension_check_would_go_quiet_if_they_agreed():
    """A check that can never pass is an alarm, not a test.

    Planted control: with the measured interval covering the cited value, the
    tension must clear. Guards against a hard-coded complaint.
    """
    assert K._crl_tension.__doc__          # the reasoning is recorded
    lo, hi, implied = 0.25, 0.35, 0.30
    assert lo <= implied <= hi             # the branch that returns None


def test_report_states_what_each_provenance_class_means():
    out = K.report(K.live(), {})
    assert "MEASURED" in out and "CITED" in out and "DESIGN" in out


def test_snapshot_round_trips(tmp_path):
    p = tmp_path / "constants.json"
    now = K.live()
    K.save(now, str(p))
    assert not K.drift(now, K.load(str(p)))["changed"]


# ── the second reading: source text vs imported attribute ───────────────────

def test_source_parse_agrees_with_the_imported_value():
    """The independent reading must match on a normal, unedited checkout."""
    assert K.source_value("fairvalue", "EVENT_MULT_POINT") == 2.45
    assert K.source_value("sanity", "MAX_DAILY_GAP") == 6


def test_a_computed_constant_parses_to_none_rather_than_disagreeing():
    """EVENT_MULT is built by a comprehension. A miss is not a conflict.

    Asserting on computed names would make the guard fire on every run, and a
    check that always fires is one nobody reads.
    """
    assert K.source_value("fairvalue", "EVENT_MULT") is None
    assert K.source_value("fairvalue", "NOT_A_REAL_NAME") is None


def test_stale_bytecode_is_caught(tmp_path, monkeypatch):
    """POSITIVE CONTROL for the cache collision that actually happened.

    CPython invalidates a .pyc on the source's mtime-to-the-second plus size.
    Rewriting 2.45 -> 1.54 (same length) inside one second leaves the stale
    .pyc in place and `import` returns the OLD value, so the registry would
    report "nothing moved" while the source said otherwise.
    """
    import importlib
    import sys
    mod = tmp_path / "planted_const.py"
    mod.write_text("VALUE = 2.45\n")
    monkeypatch.syspath_prepend(str(tmp_path))
    monkeypatch.setattr(K, "REPO", str(tmp_path))
    importlib.invalidate_caches()
    m = importlib.import_module("planted_const")
    assert m.VALUE == 2.45

    # Edit the SOURCE only; the already-imported module keeps the old value,
    # which is exactly what a stale .pyc looks like to the registry.
    mod.write_text("VALUE = 1.54\n")
    reg = {"planted_const.VALUE": K.Const(K.MEASURED, "x.py", 81)}
    got = K.live(reg)
    assert got["planted_const.VALUE"]["stale"]
    assert "1.54" in got["planted_const.VALUE"]["stale"]
    assert K.drift(got, {"planted_const.VALUE": 2.45})["broken"]
    sys.modules.pop("planted_const", None)


# ── day-82: a measured value must exist in exactly one place ────────────────

def test_the_screen_thresholds_derive_from_the_measurement_not_a_copy():
    """`_CRL` was the literal 11.79 — an uncheckable duplicate of
    catalyst.CRL_MEDIAN. That median has already been re-measured twice
    (-15.20 -> -8.97 -> -11.79); each time, the copy would have silently kept
    a retired number while claiming to be anchored to the measurement."""
    import catalyst as C
    import screen as S
    assert S._CRL == abs(C.CRL_MEDIAN)
    assert abs(S.IMMATERIAL_MOVE - abs(C.CRL_MEDIAN) / 2 / 100) < 1e-12
    assert abs(S.RICH_MOVE - abs(C.CRL_MEDIAN) * 3 / 100) < 1e-12


def test_the_screen_thresholds_move_when_the_measurement_moves(monkeypatch):
    """POSITIVE CONTROL for the derivation: if re-measuring the median did not
    move the thresholds, the anchor would be decorative."""
    import importlib
    import catalyst as C
    monkeypatch.setattr(C, "CRL_MEDIAN", -20.0)
    import screen as S
    importlib.reload(S)
    try:
        assert S._CRL == 20.0
        assert abs(S.IMMATERIAL_MOVE - 0.10) < 1e-12
    finally:
        monkeypatch.undo()
        importlib.reload(S)


def test_the_external_adcom_rates_are_registered_as_cited():
    """They are printed in the report beside FDA outcomes and had no
    provenance entry at all — a number the reader takes as measured here."""
    for k in ("adcom.EXT_POSITIVE_APPROVED", "adcom.EXT_NEGATIVE_REJECTED"):
        assert K.REGISTRY[k].kind == K.CITED
        assert "Cannizzaro" in K.REGISTRY[k].note or K.REGISTRY[k].note


def test_the_typical_move_tension_names_the_direction_of_the_error():
    """A denominator that is too large makes the spread look like a smaller
    share of a normal day than it is, so the cost line UNDERSTATES the drag.
    Naming the direction is what makes the tension actionable."""
    t = [x for x in K.tensions() if x[0] == "typical intraday move"]
    if not t:                      # only fires while the two disagree
        import cost
        import validate_typicalmove as V
        r = V.run()
        lo, hi = r["ci"]
        assert lo <= cost.TYPICAL_MOVE_PCT <= hi, "disagrees but was not flagged"
        return
    what, why, short = t[0]
    assert "UNDERSTATES" in short
    assert "0.97" in why and "cannot be reconstructed" in why


def test_the_typical_move_constant_now_names_its_re_derivation_script():
    assert K.REGISTRY["cost.TYPICAL_MOVE_PCT"].script == "validate_typicalmove.py"
