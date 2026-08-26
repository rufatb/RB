"""Day-66: announcement vs mention — the classifier that unblocks day-56.

Day-56 killed the catalyst backtest because random windows were
indistinguishable from event windows (t=+0.31). That was a verdict on the
LABELS. Every case below is a real filing diagnosed by hand first.
"""

import classify as C

# Ardelyx 8-K, 2021-07-30. A LOAN AGREEMENT amendment that references a CRL
# issued two days earlier. Inside any sane date window, and still a mention.
ARDX_LOAN = ("amended the Loan Agreement to November 1, 2021. Without such "
             "extension, following the July 28, 2021 issuance by the U.S. Food "
             "and Drug Administration of a complete response letter for "
             "tenapanor for the control of serum phosphorus")

ALDX = ("furnished a press release to announce receipt of a Complete Response "
        "Letter from the U.S. Food & Drug Administration on March 17, 2026")

RGNX = ("REGENXBIO Inc. announced that it received a Complete Response Letter "
        "from the U.S. Food and Drug Administration regarding the Company's "
        "Biologics License Application on February 9, 2026")

VNDA = ("Vanda issued a press release announcing that it had received a "
        "Complete Response Letter from the U.S. Food and Drug Administration "
        "regarding Vanda's supplemental New Drug Application")

AXSM_LATER = ("the Company continues to work with the FDA following the "
              "complete response letter and expects to resubmit")


def test_a_loan_agreement_referencing_a_two_day_old_crl_is_a_mention():
    """The date lag is 2 days — inside the window — so the MENTION VETO has to
    outrank the date test, which is exactly how the classifier is ordered."""
    ok, why = C.classify_crl(ARDX_LOAN, "2021-07-30")
    assert ok is False
    assert "previously disclosed" in why


def test_announcement_phrasing_with_a_same_day_date_passes():
    ok, why = C.classify_crl(ALDX, "2026-03-17")
    assert ok is True and "date lag 0d" in why


def test_announcement_phrasing_with_a_one_day_lag_passes():
    ok, why = C.classify_crl(RGNX, "2026-02-10")
    assert ok is True and "date lag 1d" in why


def test_present_tense_announcement_without_a_date_passes():
    ok, why = C.classify_crl(VNDA, "2024-03-07")
    assert ok is True and "no date stated" in why


def test_a_retrospective_reference_without_announcement_phrasing_fails():
    ok, why = C.classify_crl(AXSM_LATER, "2022-06-02")
    assert ok is False


def test_a_stale_date_beside_announcement_phrasing_is_rejected():
    t = ("the Company announced that it received a Complete Response Letter "
         "on January 4, 2026 and has since met with the agency")
    ok, why = C.classify_crl(t, "2026-06-30")
    assert ok is False and "from the filing" in why


def test_absent_phrase_is_not_an_announcement():
    ok, why = C.classify_crl("no such letter here", "2026-01-01")
    assert ok is False and why == "phrase absent"


def test_an_unparseable_filing_date_still_honours_the_phrasing():
    ok, why = C.classify_crl(VNDA, "not-a-date")
    assert ok is True and "unparseable" in why


def test_the_classifier_fails_closed_toward_mention():
    """Losing a real event costs sample size; admitting a false one poisons the
    labels, and poisoned labels are what day-56 measured."""
    ambiguous = "The complete response letter remains under discussion."
    assert C.classify_crl(ambiguous, "2026-01-01")[0] is False


def test_approval_side_uses_the_same_discipline():
    ann = ("the Company announced that its therapy was approved by the U.S. "
           "Food and Drug Administration")
    ment = ("its therapy, previously approved by the U.S. Food and Drug "
            "Administration in 2019, continues to be marketed")
    assert C.classify_approval(ann, "2026-01-01")[0] is True
    assert C.classify_approval(ment, "2026-01-01")[0] is False


# ── day-74: two recall bugs, both found by one real filing.
# Zymeworks' 8-K of 2026-08-25 announces an FDA approval in its first sentence
# and was classified "phrase absent". It is kept as a fixture because a
# regression here silently undercounts the approval leg of the base rate.

import os

FIXTURE = os.path.join(os.path.dirname(__file__), "fixtures_zyme_8k.txt")


def _zyme():
    with open(FIXTURE) as f:
        return f.read()


def test_the_real_filing_that_broke_the_classifier_is_now_caught():
    ok, why = C.classify_approval(_zyme(), "2026-08-25")
    assert ok, why


def test_that_filing_is_not_also_read_as_a_rejection():
    ok, _ = C.classify_crl(_zyme(), "2026-08-25")
    assert not ok


def test_the_anchor_no_longer_hardcodes_a_preposition():
    """'FDA approval of' was a literal string; the filing said 'approval for'
    and later 'approval in'."""
    for prep in ("of", "for", "in", "to"):
        t = (f"The Company announced today that it has received FDA approval "
             f"{prep} its lead programme.")
        ok, why = C.classify_approval(t, "2026-08-25")
        assert ok, f"{prep}: {why}"


def test_a_parenthetical_gloss_between_agency_and_approval_is_spanned():
    t = ('The Company issued a press release announcing that it has received '
         'U.S. Food and Drug Administration ("FDA") approval for two regimens.')
    assert C.classify_approval(t, "2026-08-25")[0]


def test_every_occurrence_is_examined_not_only_the_first():
    """A filing whose opening refers to a prior approval and whose body
    announces a new one was judged entirely on the reference."""
    t = ("As previously disclosed, the FDA approved the Company's first "
         "product in 2019. " + "Filler sentence. " * 40 +
         "Today the Company announced that the FDA has approved its second "
         "product.")
    ok, why = C.classify_approval(t, "2026-08-25")
    assert ok, why


def test_widening_the_anchor_did_not_loosen_the_mention_veto():
    """Strictness unchanged, thoroughness increased -- a pure reference must
    still be rejected however it is phrased."""
    for t in ("As previously disclosed, the Company received FDA approval for "
              "its lead programme last year.",
              "Following the issuance of FDA approval in March, the Company "
              "amended its loan agreement."):
        ok, why = C.classify_approval(t, "2026-08-25")
        assert not ok, why


def test_a_filing_that_only_names_the_agency_is_not_an_approval():
    t = ("The Company intends to submit a New Drug Application to the U.S. "
         "Food and Drug Administration later this year.")
    assert not C.classify_approval(t, "2026-08-25")[0]


def test_html_entities_are_decoded_before_any_phrase_test_runs():
    """EDGAR filings are full of them. Tag-stripping without entity-decoding is
    half a job, and it ran the phrase tests against text no pattern could
    match."""
    import build_catalyst as BC
    raw = b'<p>Administration (&#8220;FDA&#8221;) approval&nbsp;for two</p>'
    out = BC._strip(raw)
    assert "&#8220;" not in out and "&nbsp;" not in out
    assert '("FDA") approval' in out.replace("“", '"').replace("”", '"')
