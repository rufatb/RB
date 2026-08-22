"""Day-57: the forward FDA decision calendar, built free from 8-K disclosures."""

import datetime as dt

import pdufa


def test_extracts_pdufa_dates_in_disclosure_order():
    t = ("...accepted the filing with a PDUFA date of January 29, 2027 and a "
         "second programme carrying a PDUFA target action date of "
         "December 27, 2026...")
    assert pdufa.parse_dates(t) == ["2027-01-29", "2026-12-27"]


def test_repeated_dates_are_reported_once():
    t = "PDUFA date of March 3, 2027 ... reiterate the PDUFA date of March 3, 2027"
    assert pdufa.parse_dates(t) == ["2027-03-03"]


def test_unparseable_dates_do_not_crash_the_calendar():
    assert pdufa.parse_dates("PDUFA date of Smarch 41, 2027") == []
    assert pdufa.parse_dates("no dates here at all") == []


def test_review_signals_name_where_the_review_stands():
    t = ("Mid-cycle meeting completed; FDA identified no major safety or "
         "efficacy concerns and granted Priority Review. PDUFA date of "
         "May 1, 2027.")
    s = pdufa.review_signals(t)
    assert "mid-cycle meeting" in s
    assert "priority review" in s
    assert "no major concerns flagged" in s


def test_a_negated_adcom_supersedes_the_bare_mention():
    """'does not plan to hold an Advisory Committee' must not read as 'AdCom'."""
    t = ("The FDA does not currently plan to hold an Advisory Committee "
         "meeting. PDUFA date of May 1, 2027.")
    s = pdufa.review_signals(t)
    assert "AdCom NOT planned" in s and "AdCom mentioned" not in s


def test_a_prior_crl_is_flagged():
    t = "Following the Complete Response Letter, PDUFA date of June 2, 2027."
    assert "prior CRL" in pdufa.review_signals(t)


def test_context_returns_the_sentence_around_the_date():
    t = ("Some preamble. Mid-cycle meeting completed for relutrigine; FDA "
         "identified no major safety or efficacy concerns. PDUFA date of "
         "January 29, 2027. Trailing text.")
    c = pdufa.context_for(t)
    assert "January 29, 2027" in c and "mid-cycle" in c.lower()


def test_dedupe_keeps_the_most_recent_disclosure_of_one_decision():
    rows = [{"ticker": "JAZZ", "date": "2026-08-25", "filed": "2026-05-05",
             "cik": "1", "signals": ["priority review"]},
            {"ticker": "JAZZ", "date": "2026-08-25", "filed": "2026-08-03",
             "cik": "1", "signals": ["mid-cycle meeting"]}]
    out = pdufa.dedupe(rows)
    assert len(out) == 1 and out[0]["filed"] == "2026-08-03"
    # signals from the superseded filing are not lost
    assert set(out[0]["signals"]) == {"priority review", "mid-cycle meeting"}


def test_two_different_dates_for_one_sponsor_are_two_decisions():
    rows = [{"ticker": "IONS", "date": "2026-09-22", "filed": "2026-04-29",
             "cik": "2", "signals": []},
            {"ticker": "IONS", "date": "2026-10-26", "filed": "2026-04-29",
             "cik": "2", "signals": []}]
    assert len(pdufa.dedupe(rows)) == 2


def test_render_states_that_dates_are_disclosures_not_confirmations():
    cal = [{"date": "2026-08-25", "ticker": "ZYME", "company": "Zymeworks Inc.",
            "filed": "2026-05-07", "cik": "3", "signals": ["priority review"],
            "context": ""}]
    out = pdufa.render(cal, dt.date(2026, 8, 22), 120)
    assert "ZYME" in out and "3d" in out
    assert "not FDA confirmations" in out and "no probability is implied" in out


def test_render_is_explicit_when_nothing_is_scheduled():
    assert "nothing scheduled" in pdufa.render([], dt.date(2026, 8, 22))
