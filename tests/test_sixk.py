"""Day-70: the 6-K risk flag.

validate_sixk.py measured two different answers to two different questions —
direction is nothing (rejection #36), magnitude is real (z=+4.55). These lock
the flag to the second answer and keep it away from the first, and they lock
the ticker->CIK guard that stopped thirty-two false joins.
"""

import datetime as dt

import sixk as S

TODAY = dt.date(2026, 8, 22)          # a Saturday-adjacent Friday-ish anchor


def _sub(forms, dates=None):
    dates = dates or ["2026-08-21"] * len(forms)
    return {"filings": {"recent": {"form": forms, "filingDate": dates}}}


def test_root_strips_tsx_suffixes_and_unit_markers():
    assert S.root("ABX.TO") == "ABX"
    assert S.root("AP-UN.TO") == "AP"
    assert S.root("ACO-X.TO") == "ACO"


def test_a_us_domestic_filer_is_rejected_however_well_the_symbol_matches():
    """ARE.TO is Aecon. ARE on the SEC's list is Alexandria Real Estate, and it
    files 10-Ks. Thirty-two names matched like this in the validation run."""
    assert not S.is_canadian_filer(_sub(["10-Q", "8-K", "4"]))


def test_an_mjds_filer_is_accepted():
    assert S.is_canadian_filer(_sub(["40-F", "6-K"]))
    assert S.is_canadian_filer(_sub(["6-K/A"]))


def test_filings_since_returns_only_6ks_and_only_after_the_cutoff():
    sub = _sub(["6-K", "40-F", "6-K", "6-K"],
               ["2026-08-21", "2026-08-20", "2026-06-01", "2026-08-19"])
    assert S.filings_since(sub, "2026-08-18") == ["2026-08-19", "2026-08-21"]


def test_an_unresolvable_ticker_is_unchecked_never_clean():
    """The whole point of the flag is that no filing and no lookup are
    different facts."""
    cache = {}
    cik, status = S.resolve("NOPE.TO", {}, cache)
    assert cik is None and status == "no-cik"


def test_a_transient_error_is_not_cached_as_a_verdict():
    """Caching a timeout as 'not-canadian' would silently retire a real name."""
    cache = {}

    def boom(_):
        raise TimeoutError("slow")
    orig, S.submissions = S.submissions, boom
    try:
        cik, status = S.resolve("ABX.TO", {"ABX": "1"}, cache)
    finally:
        S.submissions = orig
    assert cik is None and status == "TimeoutError"
    assert "ABX.TO" not in cache


def test_the_flag_quotes_the_magnitude_finding_and_never_a_direction_edge():
    lines = "\n".join(S.render(
        [{"ticker": "RY.TO", "status": "ok", "dates": ["2026-08-21"]}], TODAY))
    assert f"{S.WIDER_PP:+.3f}pp" in lines and f"z={S.WIDER_Z:+.2f}" in lines
    assert "NO more predictable in direction" in lines
    assert "nothing here blocks the pick" in lines
    for word in ("edge", "signal", "predicts"):
        assert word not in lines.lower().replace("no more predictable", "")


def test_an_unchecked_name_is_reported_as_unchecked():
    lines = "\n".join(S.render(
        [{"ticker": "X.TO", "status": "TimeoutError", "dates": []}], TODAY))
    assert "UNCHECKED is not clean" in lines


def test_a_clean_checked_name_produces_no_noise():
    assert S.render([{"ticker": "X.TO", "status": "ok", "dates": []}],
                    TODAY) == []
    assert S.render([{"ticker": "X.TO", "status": "no-cik", "dates": []}],
                    TODAY) == []


def test_todays_own_filing_is_excluded_from_the_flag():
    """The measurement is about the session AFTER a filing. A filing dated
    today has no timestamp and may land after the leg is closed."""
    cache = {"RY.TO": {"cik": "1", "status": "ok"}}
    orig = S.submissions
    S.submissions = lambda c: _sub(["6-K", "6-K"],
                                   ["2026-08-22", "2026-08-21"])
    try:
        f = S.flag("RY.TO", TODAY, {}, cache)
    finally:
        S.submissions = orig
    assert f["dates"] == ["2026-08-21"]
