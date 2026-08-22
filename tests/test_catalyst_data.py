"""Day-55: the free-data catalyst pipeline.

The harvester's job is to be survivorship-free, so the tests that matter are
the ones guarding the two places bias can re-enter: the SIC filter (which
decides what counts as a biotech event) and the ticker recovery (which decides
whether dead companies reach the price step at all).
"""

import datetime as dt

import numpy as np
import pandas as pd
import pytest

import build_catalyst as bc
import validate_catalyst as vc


def _hit(cik, date, sic, name="ACME PHARMA", adsh="0001-24-000001"):
    return {"_source": {"ciks": [cik], "file_date": date, "sics": [sic],
                        "display_names": [f"{name}  (CIK {cik})"], "adsh": adsh}}


def test_only_pharma_and_biotech_sic_codes_enter_the_sample():
    """'complete response letter' appears in unrelated filings too."""
    hits = [_hit("0000123", "2015-03-02", "2836"),      # biological products
            _hit("0000124", "2015-03-03", "2834"),      # pharma preparations
            _hit("0000125", "2015-03-04", "6022"),      # a bank
            _hit("0000126", "2015-03-05", "7372")]      # a software company
    rows = bc.rows_from_hits(hits, "CRL")
    assert [r["cik"] for r in rows] == ["123", "124"]


def test_one_row_per_filer_per_date_even_with_many_documents():
    """A single 8-K indexes several documents; the EVENT happened once."""
    hits = [_hit("0000123", "2015-03-02", "2836"),
            _hit("0000123", "2015-03-02", "2836"),
            _hit("0000123", "2015-03-02", "2836")]
    assert len(bc.rows_from_hits(hits, "CRL")) == 1


def test_company_name_is_stripped_of_the_cik_suffix():
    rows = bc.rows_from_hits([_hit("0000897075", "2015-12-01", "2836",
                                   "REPROS THERAPEUTICS INC.")], "CRL")
    assert rows[0]["name"] == "REPROS THERAPEUTICS INC."


def test_ticker_regex_reads_the_press_release_boilerplate():
    """The route that works for DELISTED issuers, where every SEC ticker API
    returns empty. Verified live against Repros Therapeutics -> RPRX."""
    for text, want in [
        ("Repros Therapeutics Inc. (Nasdaq: RPRX) today announced", "RPRX"),
        ("Acme Bio (NASDAQ: ABCD) reported", "ABCD"),
        ("Foo Pharma (NYSE American: FP) said", "FP"),
        ("Bar Inc. (NYSE: BAR) announced", "BAR"),
        ("Baz (OTCQB: BAZZ) disclosed", "BAZZ"),
    ]:
        m = bc.TICK_RE.search(text)
        assert m and m.group(1) == want, text


def test_ticker_regex_takes_the_filer_not_a_partner_named_later():
    """The filer's own symbol is in the dateline; partners appear downstream."""
    t = ("Acme Bio (Nasdaq: ACME) today announced that its partner "
         "Globex Pharmaceuticals (Nasdaq: GLBX) will co-commercialise.")
    assert bc.TICK_RE.search(t).group(1) == "ACME"


def test_ticker_recovery_counts_failures_instead_of_swallowing_them():
    """2,214 silent 403s hid the first version's total failure (day-29 rule)."""
    stats = {}
    bc.ticker_from_filing("0", "bad-accession-that-404s", {}, stats)
    assert sum(stats.values()) == 1


def _series(n=60, start=100.0):
    idx = pd.bdate_range("2015-01-01", periods=n)
    return pd.DataFrame({"Close": np.linspace(start, start, n)}, index=idx)


def test_window_returns_needs_history_on_both_sides():
    px = _series(60)
    assert vc.window_returns(px, dt.datetime(2015, 1, 2)) is None      # no run-up
    assert vc.window_returns(px, dt.datetime(2015, 3, 24)) is None     # no follow
    assert vc.window_returns(px, dt.datetime(2015, 2, 16)) is not None


def test_event_window_spans_the_filing_date_ambiguity():
    """An after-close announcement is filed the NEXT morning, so the drop can
    land on t-1 or t. A crash on the day before the filing must be caught."""
    idx = pd.bdate_range("2015-01-01", periods=60)
    p = np.full(60, 100.0)
    p[30:] = 40.0                       # -60% starting the day before filing
    w = vc.window_returns(pd.DataFrame({"Close": p}, index=idx), idx[31])
    assert w["event"] < -50


def test_pre_event_window_cannot_see_the_event():
    """`pre20` must end before the reaction or the ceiling test is circular.

    The two windows are contiguous and share their boundary: `pre20` runs
    close(t-22) -> close(t-2) and `event` runs close(t-2) -> close(t+1). So a
    move landing ON close(t-2) belongs to pre20, which is correct — it happened
    before the window the announcement can move. The first version of this test
    put the crash exactly on that boundary and read the resulting -90% pre20 as
    leakage; it was the test that was ambiguous, not the code.
    """
    idx = pd.bdate_range("2015-01-01", periods=60)
    p = np.full(60, 100.0)
    p[30:] = 10.0                       # crash strictly inside the event window
    w = vc.window_returns(pd.DataFrame({"Close": p}, index=idx), idx[31])
    assert w["pre20"] == pytest.approx(0.0, abs=1e-9)
    assert w["event"] == pytest.approx(-90.0, abs=1e-9)


def test_a_move_on_the_boundary_close_counts_as_pre_event():
    """Pins the convention above so a later refactor cannot drift it."""
    idx = pd.bdate_range("2015-01-01", periods=60)
    p = np.full(60, 100.0)
    p[29:] = 10.0                       # lands ON close(t-2)
    w = vc.window_returns(pd.DataFrame({"Close": p}, index=idx), idx[31])
    assert w["pre20"] == pytest.approx(-90.0, abs=1e-9)
    assert w["event"] == pytest.approx(0.0, abs=1e-9)
