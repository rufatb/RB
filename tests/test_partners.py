"""Day-74: does this company OWN the application, or is it someone else's?

Zymeworks' PDUFA resolved in approval and this repo had twice said to exit, on
the grounds that a single-asset developer is paid too little to carry its own
binary. The reasoning was sound and the premise was wrong: Jazz holds the
application. These lock the distinction that was missing.
"""

import os

import partners as P

FIXTURE = os.path.join(os.path.dirname(__file__), "fixtures_zyme_8k.txt")


def test_the_real_filing_is_read_as_an_OUT_licence():
    p = P.classify(open(FIXTURE).read())
    assert p["role"] == "LICENSOR"
    assert p["holder"] and "Jazz" in p["holder"]
    assert p["royalty"] == "10-20%"
    assert max(p["milestones"]) >= 1300


def test_receive_versus_pay_is_the_discriminator_not_the_word_partner():
    """'Eligible to receive up to $1.3 billion' and 'obligated to pay up to
    $1.3 billion' contain nearly the same words and are opposite positions."""
    out = P.classify("The Company is eligible to receive up to $1.3 billion "
                     "in milestones from its partner.")
    inn = P.classify("The Company is obligated to pay up to $1.3 billion in "
                     "milestones, having licensed the compound from Acme Bio.")
    assert out["role"] == "LICENSOR"
    assert inn["role"] == "LICENSEE"


def test_no_partnership_language_is_not_detected_never_owned_outright():
    """A licence signed years ago may appear in none of these filings."""
    p = P.classify("The Company submitted a New Drug Application in March.")
    assert p["role"] == "not detected"
    assert P.render(p) == []


def test_an_unchecked_row_says_so_rather_than_going_quiet():
    lines = P.render(None)
    assert "NOT CHECKED" in lines[0]
    assert "absence is not evidence" in lines[0]


def test_both_directions_present_is_ambiguous_not_resolved_arbitrarily():
    p = P.classify("The Company is eligible to receive milestone payments of "
                   "$50 million, and is obligated to pay royalties to Acme.")
    assert p["role"] == "ambiguous"
    assert "BOTH sides" in " ".join(P.render(p))


def test_money_is_normalised_to_millions_and_never_inferred():
    assert P.amounts("$250 million and $1.3 billion") == [250.0, 1300.0]
    assert P.amounts("no figures here") == []


def test_the_milestone_line_shows_distinct_figures_not_just_the_largest():
    """A filing states a near-term payment and a lifetime ceiling in one
    paragraph; collapsing them either overstates what landed or hides what is
    still to come."""
    p = P.classify("has earned a milestone payment of $250 million and is "
                   "eligible to receive up to $1.3 billion more")
    line = " ".join(P.render(p))
    assert "$250M" in line and "$1,300M" in line


def test_the_flag_refuses_to_be_a_probability_adjustment():
    p = P.classify(open(FIXTURE).read())
    assert "NOT a probability adjustment" in " ".join(P.render(p))


def test_market_cap_context_only_appears_when_both_inputs_are_given():
    p = P.classify("eligible to receive up to $500 million from its partner")
    assert "market cap" not in " ".join(P.render(p))
    assert "market cap" in " ".join(P.render(p, spot=10.0, shares=50_000_000))
