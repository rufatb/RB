"""Day-71: P(CRL), the number every breakeven in this repo has been missing.

The danger in a base rate is not that it is slightly wrong. It is that a ratio
whose numerator and denominator come from different populations looks exactly
like a rate. These lock the population, the de-duplication, and the audit that
decides whether the approval leg can be trusted.
"""

import json

import baserate as B


class _domestic:
    """Every registrant in these fixtures files 8-Ks. The foreign-issuer case
    has its own test; stubbing here keeps the other tests off the network and
    focused on the matching logic they are about."""

    def __init__(self, value=True):
        self.value = value

    def __enter__(self):
        self.orig = B.files_8k
        B.files_8k = lambda cik, cache: self.value
        return self

    def __exit__(self, *a):
        B.files_8k = self.orig


def _row(cik, kind, date, name="Zymeworks Inc."):
    return {"cik": cik, "kind": kind, "date": date, "name": name,
            "sic": "2836", "accession": f"{cik}-{date}", "ticker": ""}


# ── the harvest
def test_one_decision_announced_twice_is_one_decision():
    """The 8-K, then its amendment, then an exhibit that trips the same search."""
    rows = [_row("1", "CRL", "2024-03-01"), _row("1", "CRL", "2024-03-04"),
            _row("1", "CRL", "2024-03-08")]
    assert len(B.dedupe(rows)) == 1


def test_the_same_sponsor_can_have_two_decisions_far_apart():
    rows = [_row("1", "CRL", "2024-03-01"), _row("1", "CRL", "2024-09-01")]
    assert len(B.dedupe(rows)) == 2


def test_a_rejection_and_an_approval_are_never_collapsed_together():
    """A CRL then an approval after resubmission is two decisions, not one."""
    rows = [_row("1", "CRL", "2024-03-01"), _row("1", "APPROVAL", "2024-03-02")]
    assert len(B.dedupe(rows)) == 2


def test_the_rate_counts_both_legs_from_the_same_window():
    rows = ([_row(str(i), "CRL", "2020-01-01") for i in range(20)] +
            [_row(str(100 + i), "APPROVAL", "2020-01-01") for i in range(80)])
    r = B.raw_rate(rows, "2019-01-01", "2021-01-01")
    assert r["n_crl"] == 20 and r["n_appr"] == 80 and r["n"] == 100
    assert abs(r["p"] - 0.20) < 1e-9


def test_events_outside_the_window_are_excluded_from_both_legs():
    rows = [_row("1", "CRL", "2010-01-01"), _row("2", "APPROVAL", "2020-01-01")]
    r = B.raw_rate(rows, "2015-01-01", "2026-12-31")
    assert r["n_crl"] == 0 and r["n_appr"] == 1


def test_wilson_is_used_because_normal_approximation_breaks_at_the_edges():
    lo, hi = B.wilson(0, 20)
    assert lo == 0.0 and 0 < hi < 0.20        # never a degenerate [0, 0]
    lo, hi = B.wilson(50, 100)
    assert lo < 0.5 < hi and hi - lo < 0.25


# ── name matching, which is where a coverage audit quietly goes wrong
def test_corporate_furniture_is_stripped_but_identity_is_kept():
    assert B.tokens("ZYMEWORKS INC.") == {"zymeworks"}
    assert B.tokens("Acme Pharmaceuticals, Inc.") == {"acme"}


def test_two_different_companies_do_not_match_on_a_shared_prefix():
    assert not B.same_company("GENENTECH INC", "GENELABS TECHNOLOGIES INC")


def test_the_same_company_matches_across_punctuation_and_suffixes():
    assert B.same_company("ZYMEWORKS INC.", "Zymeworks Inc")
    assert B.same_company("Eli Lilly and Company", "LILLY ELI & CO")


def test_a_name_that_is_only_furniture_never_matches_anything():
    """Otherwise every sponsor matches every registrant on 'inc'."""
    assert B.tokens("Inc.") == set()
    assert not B.same_company("Inc.", "Pharmaceuticals Inc")


# ── the audit
def test_a_private_sponsors_absent_filing_is_not_counted_as_a_miss():
    """A private company has no 8-K to find. Counting that as a coverage
    failure would manufacture a problem that does not exist."""
    fda = [{"applno": "1", "date": "2024-05-01", "sponsor": "PRIVATE BIOTECH",
            "type": "NDA", "priority": "PRIORITY"}]
    cap = B.capture_rate([], fda, [("Zymeworks Inc", "1")])
    assert cap["fda_public"] == 0
    assert cap["fda_total"] == 1


def test_a_public_sponsors_approval_that_the_harvest_found_counts_as_captured():
    fda = [{"applno": "1", "date": "2024-05-01", "sponsor": "ZYMEWORKS INC",
            "type": "NDA", "priority": "PRIORITY"}]
    mine = [{"name": "Zymeworks Inc.", "date": "2024-05-02"}]
    with _domestic():
        cap = B.capture_rate(mine, fda, [("Zymeworks Inc", "1")])
    assert cap["fda_public"] == 1 and cap["found"] == 1 and cap["rate"] == 1.0


def test_a_public_sponsors_approval_the_harvest_missed_is_reported_as_a_miss():
    fda = [{"applno": "1", "date": "2024-05-01", "sponsor": "ZYMEWORKS INC",
            "type": "NDA", "priority": "PRIORITY"}]
    with _domestic():
        cap = B.capture_rate([], fda, [("Zymeworks Inc", "1")])
    assert cap["fda_public"] == 1 and cap["found"] == 0 and cap["rate"] == 0.0
    assert cap["misses"]


def test_an_approval_matched_to_a_filing_months_away_is_not_the_same_event():
    fda = [{"applno": "1", "date": "2024-05-01", "sponsor": "ZYMEWORKS INC",
            "type": "NDA", "priority": "PRIORITY"}]
    mine = [{"name": "Zymeworks Inc.", "date": "2024-11-02"}]
    with _domestic():
        assert B.capture_rate(mine, fda, [("Zymeworks Inc", "1")])["found"] == 0


# ── the correction
def test_the_correction_scales_only_the_approval_leg():
    """Rejections are assumed captured MORE completely, so scaling both would
    erase the very asymmetry the correction exists to handle."""
    raw = {"n_crl": 20, "n_appr": 40}
    c = B.corrected(raw, 0.5)
    assert abs(c["n_appr_adj"] - 80) < 1e-9
    assert abs(c["p"] - 20 / 100) < 1e-9


def test_the_correction_always_lowers_the_estimate():
    raw = {"n_crl": 20, "n_appr": 80}
    assert B.corrected(raw, 0.6)["p"] < 20 / 100


def test_a_missing_capture_rate_produces_no_correction_rather_than_a_guess():
    assert B.corrected({"n_crl": 1, "n_appr": 1}, 0) == {}
    assert B.corrected({"n_crl": 1, "n_appr": 1}, float("nan")) == {}


# ── the report
def _rendered(capture=None, corr=None):
    raw = {"n_crl": 30, "n_appr": 70, "n": 100, "p": 0.30,
           "lo": 0.22, "hi": 0.40}
    return B.render(raw, capture or {}, corr or {}, "2015-01-01", "2026-12-31")


def test_the_report_always_says_the_rate_is_unconditional():
    out = _rendered()
    assert "UNCONDITIONAL" in out
    assert "prior you argue away from" in out


def test_the_report_names_the_supplement_bias_and_its_direction():
    out = _rendered()
    assert "Supplements" in out and "DOWN" in out


def test_a_failed_audit_is_stated_not_silently_skipped():
    out = _rendered()
    assert "UNAVAILABLE" in out and "unverified" in out


def test_the_report_says_the_rejection_leg_cannot_be_audited_at_all():
    """The FDA publishes no rejections, so half the ratio has no external
    check. A reader who is not told that will assume both legs were verified."""
    out = _rendered()
    assert "publishes no rejections" in out
    assert "no external record to audit" in out


def test_the_bracket_never_presents_itself_as_a_correction():
    """It was called 'corrected', and the word was doing the arguing."""
    out = _rendered({"fda_total": 1000, "fda_public": 400, "found": 200,
                     "rate": 0.5, "misses": []},
                    {"n_appr_adj": 140.0, "p": 0.176, "capture": 0.5})
    flat = " ".join(out.split())
    assert "CORRECTED" not in out
    assert "absent by construction, not missing" in flat
    assert "FLOOR" in out and "CEILING" in out
    # the bracket must state its own limits, not just its ends
    assert "not decisive against one of 20%" in flat


def test_a_completed_audit_shows_the_capture_rate_and_what_was_missed():
    out = _rendered({"fda_total": 1000, "fda_public": 400, "found": 200,
                     "rate": 0.5, "misses": ["2024-05-01 SOMECO"]},
                    {"n_appr_adj": 140.0, "p": 0.176, "capture": 0.5})
    assert "50% capture" in out
    assert "FLOOR" in out and "17.6%" in out
    assert "CEILING" in out and "30.0%" in out
    assert "2024-05-01 SOMECO" in out


def test_load_returns_none_when_never_computed_rather_than_a_default():
    """A caller must say 'not computed', never substitute a plausible number."""
    assert B.load("/nonexistent/baserate.json") is None


def test_the_audit_scales_to_a_real_registrant_list():
    """The naive form is 1,556 sponsors x 10,403 registrants of set
    intersection, inside a morning report. The index must not change any
    answer while making that tractable."""
    import random
    random.seed(0)
    regs = [(f"Company{i} Pharmaceuticals Inc", str(i)) for i in range(10000)]
    regs.append(("Zymeworks Inc", "99999"))
    fda = [{"applno": "1", "date": "2024-05-01", "sponsor": "ZYMEWORKS INC",
            "type": "NDA", "priority": "PRIORITY"},
           {"applno": "2", "date": "2024-05-01", "sponsor": "NOT LISTED LLC",
            "type": "NDA", "priority": "STANDARD"}]
    with _domestic():
        cap = B.capture_rate([{"name": "Zymeworks Inc.", "date": "2024-05-01"}],
                             fda, regs)
    assert cap["fda_public"] == 1 and cap["found"] == 1


# ── the stratification that attacks the "unconditional" caveat
def test_sponsors_are_split_by_how_often_they_face_the_agency():
    rows = ([_row("big", "APPROVAL", f"2020-0{i}-01") for i in range(1, 9)] +
            [_row("small", "CRL", "2020-01-01")])
    s = B.by_sponsor_frequency(rows, "2015-01-01", "2026-12-31")
    assert s["serial filer"]["n"] == 8 and s["serial filer"]["n_crl"] == 0
    assert s["single-asset"]["n"] == 1 and s["single-asset"]["n_crl"] == 1


def test_a_mid_frequency_sponsor_falls_into_neither_bucket():
    """Four decisions is neither a developer with one drug nor a regulatory
    function. Forcing it into a bucket would blur the contrast being tested."""
    rows = [_row("mid", "APPROVAL", f"2020-0{i}-01") for i in range(1, 5)]
    s = B.by_sponsor_frequency(rows, "2015-01-01", "2026-12-31")
    assert s["serial filer"]["n"] == 0 and s["single-asset"]["n"] == 0


def test_each_stratum_carries_its_own_interval_because_one_will_be_small():
    rows = ([_row("big", "APPROVAL", f"2020-0{i}-01") for i in range(1, 9)] +
            [_row("small", "CRL", "2020-01-01")])
    s = B.by_sponsor_frequency(rows, "2015-01-01", "2026-12-31")
    single = s["single-asset"]
    assert single["lo"] < single["p"] <= single["hi"]
    assert single["hi"] - single["lo"] > 0.4      # n=1 must look like n=1


def test_a_foreign_private_issuer_is_not_expected_to_have_filed_an_8k():
    """Caught on a live run: the misses were Takeda, Novartis, AstraZeneca and
    Sanofi. All SEC registrants, none of which has ever filed an 8-K -- a
    foreign private issuer reports on 20-F and 6-K. Counting their approvals as
    ones the harvest should have found would understate the capture rate,
    inflate the correction, and push P(CRL) down for a reason that has nothing
    to do with the FDA."""
    fda = [{"applno": "1", "date": "2024-05-01", "sponsor": "NOVARTIS PHARMS CORP",
            "type": "NDA", "priority": "PRIORITY"}]
    orig = B.files_8k
    B.files_8k = lambda cik, cache: False        # a 20-F/6-K filer
    try:
        cap = B.capture_rate([], fda, [("NOVARTIS AG", "1")])
    finally:
        B.files_8k = orig
    assert cap["fda_public"] == 0 and not cap["misses"]


def test_a_domestic_8k_filer_is_still_expected_to_have_filed_one():
    fda = [{"applno": "1", "date": "2024-05-01", "sponsor": "ZYMEWORKS INC",
            "type": "NDA", "priority": "PRIORITY"}]
    orig = B.files_8k
    B.files_8k = lambda cik, cache: True
    try:
        cap = B.capture_rate([], fda, [("Zymeworks Inc", "1")])
    finally:
        B.files_8k = orig
    assert cap["fda_public"] == 1 and cap["found"] == 0


def test_a_transient_lookup_failure_is_never_cached_as_a_form_verdict():
    cache = {}
    orig = B.urllib.request.urlopen

    def boom(*a, **k):
        raise TimeoutError("slow")
    B.urllib.request.urlopen = boom
    try:
        assert B.files_8k("1", cache) is False
    finally:
        B.urllib.request.urlopen = orig
    assert cache == {}


def test_summary_serves_the_screening_population_not_the_blended_one():
    """A name with a PDUFA worth screening is one for which the decision is
    material, so BOTH its outcomes get announced. That is the only stratum
    whose two legs are captured symmetrically."""
    import json as _j
    import tempfile
    d = {"computed": "2026-08-22",
         "raw": {"n": 431, "n_crl": 101, "p": 0.234, "lo": 0.197, "hi": 0.277},
         "corrected": {"p": 0.017},
         "strata": {"single-asset": {"n": 202, "n_crl": 42, "p": 0.208,
                                     "lo": 0.16, "hi": 0.27, "n_sponsors": 163},
                    "serial filer": {"n": 69, "n_crl": 12, "p": 0.174,
                                     "lo": 0.10, "hi": 0.28, "n_sponsors": 9}}}
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
        _j.dump(d, f)
        p = f.name
    s = B.summary(p)
    assert s["population"] == "single-asset sponsors"
    assert abs(s["p"] - 0.208) < 1e-9 and s["n"] == 202


def test_a_thin_stratum_falls_back_to_the_blended_figure_and_says_so():
    """Better a wider population than a rate built on twenty decisions."""
    import json as _j
    import tempfile
    d = {"computed": "2026-08-22",
         "raw": {"n": 431, "n_crl": 101, "p": 0.234, "lo": 0.197, "hi": 0.277},
         "corrected": {"p": 0.017},
         "strata": {"single-asset": {"n": 12, "n_crl": 3, "p": 0.25,
                                     "lo": 0.05, "hi": 0.60, "n_sponsors": 9}}}
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
        _j.dump(d, f)
        p = f.name
    s = B.summary(p)
    assert s["population"] == "all announced decisions" and s["n"] == 431


def test_the_report_distinguishes_the_two_questions_the_ends_answer():
    """They are not two estimates of one quantity."""
    out = _rendered({"fda_total": 1556, "fda_public": 499, "found": 29,
                     "rate": 0.058, "misses": []},
                    {"n_appr_adj": 5678.0, "p": 0.017, "capture": 0.058})
    flat = " ".join(out.split())
    assert "not two estimates of one quantity" in flat
    assert "was ANNOUNCED in an 8-K" in flat
    assert "including every routine approval nobody announced" in flat


# ── day-82: the capture audit joins two different populations ───────────────

def test_the_matcher_is_not_the_problem_it_joins_real_pairs():
    """Diagnosed wrongly at first. Raw string equality matched 11 of 334
    sponsors, which looked like a broken join — but that is not what the code
    uses. `same_company` joins the standard case correctly."""
    import baserate as B
    assert B.same_company("AADI BIOSCIENCE, INC.", "AADI")
    assert B.same_company("60 DEGREES PHARMACEUTICALS, INC.",
                          "60 DEGREES PHARMS")
    assert B.same_company("ZYMEWORKS INC.", "ZYMEWORKS")


def test_the_matcher_still_refuses_a_near_miss():
    """A join loose enough to match everything would manufacture capture."""
    import baserate as B
    assert not B.same_company("GENENTECH INC", "GENELABS TECHNOLOGIES INC")
    assert not B.same_company("INC", "CORP")        # furniture only
    assert not B.same_company("", "ZYMEWORKS")


def test_the_floor_docstring_states_it_cannot_be_interpreted():
    """It is retained so the record of the attempt survives, but a reader must
    not take it as a bound. The numerator counts label expansions, supplements,
    device clearances and partner approvals; the denominator counts original
    approvals only."""
    import baserate as B
    doc = " ".join((B.corrected.__doc__ or "").split())   # unwrap
    assert "DIFFERENT POPULATIONS" in doc
    assert "not a lower bound on anything" in doc
    assert "DOES NOT REACH THE MORNING REPORT" in doc


def test_the_report_uses_the_raw_stratum_not_the_floor():
    """Both legs of the raw ratio come from one harvest, one classifier and
    one window — rule 7 satisfied. The floor does not, so it must not be what
    the morning page divides by."""
    import baserate as B
    s = B.summary()
    if s is None:
        return
    assert 0.05 < s["p"] < 0.20, s["p"]
    assert s["lo"] <= s["p"] <= s["hi"]
    assert s["population"] == "single-asset sponsors"
