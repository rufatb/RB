"""Day-75: did the binary already settle, and which way?

Caught live on 2026-08-27. Zymeworks' PDUFA had been decided two days earlier
-- approved -- and the report was still pricing it as pending, quoting $1,027
of rejection risk on a position whose rejection risk was zero. A negative day
count was printed and nothing acted on it.
"""

import datetime as dt

import resolved as R

TODAY = dt.date(2026, 8, 27)


def test_a_future_date_is_pending_and_renders_nothing():
    r = R.check("ZYME", "2026-12-01", TODAY)
    assert r["outcome"] == "PENDING"
    assert R.render(r) == []


def test_an_unparseable_date_never_claims_resolution():
    assert R.check("ZYME", "not-a-date", TODAY)["outcome"] == "UNKNOWN"


def test_an_unresolvable_ticker_is_unknown_not_clean():
    r = R.check("NOPE_XYZ", "2026-08-01", TODAY)
    assert r["outcome"] == "UNKNOWN"
    assert "not 'clean'" in r["why"]


def _stub(monkey, filings, texts):
    R.filings_after = lambda cik, since, until=None: filings
    R.filing_text = lambda cik, acc, cap_docs=6: texts.get(acc, "")
    R._cik_for = lambda t: "1"


def test_an_approval_filing_resolves_the_position(monkeypatch):
    _stub(monkeypatch, [{"date": "2026-08-25", "items": "7.01,8.01",
                         "accession": "A"}],
          {"A": "The Company announced that the FDA has approved its therapy."})
    r = R.check("ZYME", "2026-08-25", TODAY)
    assert r["outcome"] == "APPROVED" and r["filed"] == "2026-08-25"


def test_a_rejection_filing_resolves_the_other_way(monkeypatch):
    _stub(monkeypatch, [{"date": "2026-08-25", "items": "8.01",
                         "accession": "A"}],
          {"A": "The Company announced that it has received a Complete "
                "Response Letter from the FDA."})
    r = R.check("ZYME", "2026-08-25", TODAY)
    assert r["outcome"] == "REJECTED"
    assert "measured CRL distribution described the RISK" in " ".join(R.render(r))


def test_no_filing_is_not_evidence_that_nothing_happened(monkeypatch):
    _stub(monkeypatch, [], {})
    r = R.check("ZYME", "2026-08-25", TODAY)
    assert r["outcome"] == "NO FILING"
    assert "not evidence" in " ".join(R.render(r))


def test_an_earnings_8k_alone_does_not_count_as_an_outcome(monkeypatch):
    """Item 2.02 is results, not a decision."""
    _stub(monkeypatch, [{"date": "2026-08-26", "items": "2.02,9.01",
                         "accession": "A"}], {"A": "Quarterly results."})
    assert R.check("ZYME", "2026-08-25", TODAY)["outcome"] == "NO FILING"


def test_a_filing_the_classifier_will_not_call_is_flagged_not_guessed(monkeypatch):
    _stub(monkeypatch, [{"date": "2026-08-25", "items": "8.01",
                         "accession": "A"}],
          {"A": "The Company provided a regulatory update."})
    r = R.check("ZYME", "2026-08-25", TODAY)
    assert r["outcome"] == "UNCLEAR"
    assert "assume a pending event" in " ".join(R.render(r))


def test_edgar_being_unreachable_reports_unknown_not_resolved(monkeypatch):
    R._cik_for = lambda t: "1"

    def boom(*a, **k):
        raise TimeoutError("slow")
    R.filings_after = boom
    r = R.check("ZYME", "2026-08-25", TODAY)
    assert r["outcome"] == "UNKNOWN"
    assert "UNKNOWN, not clear" in r["why"]


def test_a_settled_approval_tells_the_holder_the_thesis_is_spent():
    lines = " ".join(R.render({"outcome": "APPROVED", "filed": "2026-08-25",
                               "why": "", "ticker": "ZYME",
                               "event_date": "2026-08-25"}))
    assert "binary is settled" in lines
    assert "should be ignored" in lines
    assert "catalyst thesis is spent" in lines
