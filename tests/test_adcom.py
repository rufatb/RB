"""Day-63: FDA Advisory Committee meetings and votes.

An AdCom is where the uncertainty resolves — a public expert panel votes weeks
before the agency rules. Misreading a vote's DIRECTION is the worst error this
module can make, so the real sentences that caused one are pinned here.
"""

import datetime as dt

import adcom as A

TODAY = dt.date(2026, 8, 22)

CAPR_REJECT = ("Advisory Committee voted 3 in favor and 9 against on whether "
               "available evidence provides substantial evidence of "
               "effectiveness of Deramiocel for the treatment of cardiomyopathy")
CAPR_NO_TALLY = ("the Cellular, Tissue and Gene Therapies Advisory Committee "
                 "voted that available evidence did not support the "
                 "effectiveness of Deramiocel")
REPL_PASS = ("Advisory Committee voted 10 to 3 that the efficacy results from "
             "the IGNYTE study are evaluable and clinically meaningful")


def test_a_labelled_tally_beats_the_keyword_in_the_same_sentence():
    """Capricor's 8-K says '3 in favor and 9 against' — a REJECTION whose text
    contains the phrase 'in favor'. Reading the keyword first called it
    FAVOURABLE, which is the single worst error this file could make."""
    assert A.vote_direction(CAPR_REJECT) == "unfavourable"
    assert A.vote_tally(CAPR_REJECT) == (3, 9)


def test_a_labelled_tally_the_other_way_reads_favourable():
    assert A.vote_direction("voted 11 in favor and 2 against") == "favourable"


def test_unfavourable_language_wins_over_the_word_support():
    """'did not support' contains 'support'."""
    assert A.vote_direction(CAPR_NO_TALLY) == "unfavourable"
    assert A.vote_tally(CAPR_NO_TALLY) is None


def test_a_favourable_vote_with_a_to_style_tally():
    assert A.vote_direction(REPL_PASS) == "favourable"
    assert A.vote_tally(REPL_PASS) == (10, 3)


def test_ambiguous_language_is_admitted_not_guessed():
    t = "Advisory Committee voted on the application at yesterday's meeting."
    assert A.vote_direction(t) == "unclear"


def test_an_unclear_vote_prints_the_sentence_for_the_reader():
    data = {"upcoming": [], "votes": [
        {"ticker": "ABCD", "company": "Acme", "filed": "2026-08-20",
         "direction": "unclear", "tally": None,
         "sentence": "Advisory Committee voted on the matter."}]}
    out = A.render(data, TODAY)
    assert "language ambiguous — read it" in out


def test_an_unfavourable_vote_is_visually_flagged():
    data = {"upcoming": [], "votes": [
        {"ticker": "CAPR", "company": "Capricor", "filed": "2026-08-13",
         "direction": "unfavourable", "tally": (3, 9), "sentence": ""}]}
    out = A.render(data, TODAY)
    assert "⚠ VOTED 3-9" in out and "UNFAVOURABLE" in out


def test_meeting_dates_are_forward_only():
    t = ("An Advisory Committee meeting is scheduled for September 15, 2026 "
         "following the earlier meeting on March 2, 2026.")
    assert A.meeting_dates(t, TODAY) == ["2026-09-15"]


def test_unparseable_meeting_dates_do_not_crash():
    assert A.meeting_dates("Advisory Committee on Smarch 40, 2026", TODAY) == []


def test_render_states_the_fda_is_not_bound_by_the_vote():
    data = {"upcoming": [], "votes": [
        {"ticker": "REPL", "company": "Replimune", "filed": "2026-07-31",
         "direction": "favourable", "tally": (10, 3), "sentence": ""}]}
    out = A.render(data, TODAY)
    assert "FDA is NOT bound by these votes" in out
    # day-69: the wording moved from "no probability of approval is derived
    # from them here" to "No probability is derived here" when the EXTERNAL
    # base rates were added beside it. The property is unchanged: this module
    # never derives a probability of its own.
    assert "No probability is" in out and "derived here" in out


def test_an_empty_window_says_so():
    assert "none scheduled or voted" in A.render({"upcoming": [], "votes": []},
                                                 TODAY)


# ── day-69: the conditional is BORROWED, and must always say so ─────────────
def test_external_base_rates_are_printed_with_their_asymmetry():
    """Day-69 could not measure P(approval|vote) from 8-K text: 12 years gave
    45 votes, 16 joined, n=1 on the unfavourable arm. Published research has
    the sample this repo cannot assemble, and the asymmetry is the useful part
    — a positive vote is far more informative than a negative one."""
    data = {"upcoming": [], "votes": [
        {"ticker": "REPL", "company": "Replimune", "filed": "2026-07-31",
         "direction": "favourable", "tally": (10, 3), "sentence": ""}]}
    out = A.render(data, TODAY)
    assert "97%" in out and "67%" in out
    assert "closer to a long delay than to a verdict" in out


def test_borrowed_numbers_are_always_labelled_external():
    """A borrowed measurement quoted as one's own is how a prior becomes a
    claim. It carries someone else's window and assumptions."""
    data = {"upcoming": [], "votes": [
        {"ticker": "X", "company": "Y", "filed": "2026-07-31",
         "direction": "favourable", "tally": None, "sentence": ""}]}
    out = A.render(data, TODAY)
    assert "EXTERNAL" in out
    assert "JAMA" in out and "2010-2021" in out
    assert "No probability is" in out and "derived here" in out


def test_the_external_constants_match_the_cited_study():
    assert A.EXT_POSITIVE_APPROVED == 0.97      # 142/147
    assert A.EXT_NEGATIVE_REJECTED == 0.67      # 40/60
    assert (A.EXT_MEDIAN_DAYS_POS, A.EXT_MEDIAN_DAYS_NEG) == (74, 700)
