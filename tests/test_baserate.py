"""Day-71: P(CRL), the number every breakeven in this repo has been missing.

The danger in a base rate is not that it is slightly wrong. It is that a ratio
whose numerator and denominator come from different populations looks exactly
like a rate. These lock the population, the de-duplication, and the audit that
decides whether the approval leg can be trusted.
"""

import json

import baserate as B


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
    cap = B.capture_rate([], fda, ["Zymeworks Inc"])
    assert cap["fda_public"] == 0
    assert cap["fda_total"] == 1


def test_a_public_sponsors_approval_that_the_harvest_found_counts_as_captured():
    fda = [{"applno": "1", "date": "2024-05-01", "sponsor": "ZYMEWORKS INC",
            "type": "NDA", "priority": "PRIORITY"}]
    mine = [{"name": "Zymeworks Inc.", "date": "2024-05-02"}]
    cap = B.capture_rate(mine, fda, ["Zymeworks Inc"])
    assert cap["fda_public"] == 1 and cap["found"] == 1 and cap["rate"] == 1.0


def test_a_public_sponsors_approval_the_harvest_missed_is_reported_as_a_miss():
    fda = [{"applno": "1", "date": "2024-05-01", "sponsor": "ZYMEWORKS INC",
            "type": "NDA", "priority": "PRIORITY"}]
    cap = B.capture_rate([], fda, ["Zymeworks Inc"])
    assert cap["fda_public"] == 1 and cap["found"] == 0 and cap["rate"] == 0.0
    assert cap["misses"]


def test_an_approval_matched_to_a_filing_months_away_is_not_the_same_event():
    fda = [{"applno": "1", "date": "2024-05-01", "sponsor": "ZYMEWORKS INC",
            "type": "NDA", "priority": "PRIORITY"}]
    mine = [{"name": "Zymeworks Inc.", "date": "2024-11-02"}]
    assert B.capture_rate(mine, fda, ["Zymeworks Inc"])["found"] == 0


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


def test_a_completed_audit_shows_the_capture_rate_and_what_was_missed():
    out = _rendered({"fda_total": 1000, "fda_public": 400, "found": 200,
                     "rate": 0.5, "misses": ["2024-05-01 SOMECO"]},
                    {"n_appr_adj": 140.0, "p": 0.176, "capture": 0.5})
    assert "50% capture" in out
    assert "CORRECTED P(CRL) = 17.6%" in out
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
    regs = [f"Company{i} Pharmaceuticals Inc" for i in range(10000)]
    regs.append("Zymeworks Inc")
    fda = [{"applno": "1", "date": "2024-05-01", "sponsor": "ZYMEWORKS INC",
            "type": "NDA", "priority": "PRIORITY"},
           {"applno": "2", "date": "2024-05-01", "sponsor": "NOT LISTED LLC",
            "type": "NDA", "priority": "STANDARD"}]
    cap = B.capture_rate([{"name": "Zymeworks Inc.", "date": "2024-05-01"}],
                         fda, regs)
    assert cap["fda_public"] == 1 and cap["found"] == 1
