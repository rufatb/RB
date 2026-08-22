"""Day-61: the balance sheet behind a catalyst.

catalyst.py can say a downside is an ASSUMPTION; this says what the floor
actually is. The ZYME matrix justified -18% with "$322.5M existing cash".
The 10-Q says $179M and 70.96M shares — $2.53/share, against a $28.67 price.
"""

import datetime as dt

import pytest

import fundamentals as F

TODAY = dt.date(2026, 8, 22)


def _facts(cash=179_413_000, cash_end="2026-06-30", shares=70_959_241,
           burn=-77_666_000, burn_start="2026-01-01", burn_end="2026-06-30",
           inv=None, inv_end="2023-12-31"):
    us = {"CashAndCashEquivalentsAtCarryingValue":
          {"units": {"USD": [{"val": cash, "end": cash_end, "form": "10-Q"}]}},
          "NetCashProvidedByUsedInOperatingActivities":
          {"units": {"USD": [{"val": burn, "start": burn_start,
                              "end": burn_end, "form": "10-Q"}]}}}
    if inv is not None:
        us["ShortTermInvestments"] = {
            "units": {"USD": [{"val": inv, "end": inv_end, "form": "10-K"}]}}
    return {"entityName": "TEST BIO",
            "facts": {"us-gaap": us,
                      "dei": {"EntityCommonStockSharesOutstanding":
                              {"units": {"shares": [{"val": shares,
                                                     "end": "2026-08-04"}]}}}}}


def _sum(monkeypatch, facts, **kw):
    monkeypatch.setattr(F, "company_facts", lambda cik, cache_dir=None: facts)
    return F.summarise("1", TODAY, **kw)


def test_cash_per_share_is_computed_from_the_filing(monkeypatch):
    s = _sum(monkeypatch, _facts())
    assert s["cash"] == 179_413_000
    assert s["cash_per_share"] == pytest.approx(2.528, abs=1e-3)


def test_the_zyme_cash_floor_claim_does_not_survive_the_balance_sheet(monkeypatch):
    """A -18% floor to $20.50 cannot rest on cash of $2.53/share."""
    s = _sum(monkeypatch, _facts())
    lines = "\n".join(F.render(s, 28.67))
    assert "$2.53/share" in lines
    assert "11.3x" in lines
    assert "PIPELINE, not cash" in lines


def test_stale_short_term_investments_are_excluded_not_added(monkeypatch):
    """ZYME's ShortTermInvestments tag last reported in 2023; counting it would
    have overstated liquidity by $217M."""
    s = _sum(monkeypatch, _facts(inv=216_770_000, inv_end="2023-12-31"))
    assert s["cash"] == 179_413_000
    assert any("EXCLUDED as stale" in n for n in s["notes"])


def test_recent_short_term_investments_are_included(monkeypatch):
    s = _sum(monkeypatch, _facts(inv=50_000_000, inv_end="2026-06-30"))
    assert s["cash"] == 229_413_000
    assert not any("stale" in n for n in s["notes"])


def test_burn_is_annualised_from_the_period_the_filing_covers(monkeypatch):
    """A 6-month cash-flow figure is not a quarterly burn."""
    s = _sum(monkeypatch, _facts())            # -77.7M over ~6 months
    assert s["burn_q"] == pytest.approx(38_833_000, rel=0.02)
    assert s["runway_q"] == pytest.approx(4.6, abs=0.2)


def test_a_short_runway_warns_that_dilution_is_independent_of_the_fda(monkeypatch):
    s = _sum(monkeypatch, _facts(cash=37_000_000, shares=105_000_000,
                                 burn=-40_000_000))
    lines = "\n".join(F.render(s, 1.18))
    assert "dilution likely regardless of the FDA" in lines


def test_a_long_runway_does_not_warn(monkeypatch):
    s = _sum(monkeypatch, _facts(cash=792_000_000, shares=173_000_000,
                                 burn=-164_000_000))
    assert "dilution likely" not in "\n".join(F.render(s, 36.73))


def test_positive_operating_cash_flow_is_not_treated_as_burn(monkeypatch):
    s = _sum(monkeypatch, _facts(burn=+50_000_000))
    assert s["burn_q"] is None and s["runway_q"] is None


def test_missing_facts_yield_none_never_a_fabricated_balance_sheet(monkeypatch):
    monkeypatch.setattr(F, "company_facts", lambda cik, cache_dir=None: None)
    s = F.summarise("1", TODAY)
    assert s["cash"] is None and s["cash_per_share"] is None
    assert "XBRL facts unavailable" in s["notes"]


def test_latest_prefers_the_most_recently_ended_tag(monkeypatch):
    f = _facts()
    f["facts"]["us-gaap"]["CashCashEquivalentsRestrictedCashAndRestrictedCash"
                          "Equivalents"] = {
        "units": {"USD": [{"val": 999, "end": "2020-01-01", "form": "10-K"}]}}
    s = _sum(monkeypatch, f)
    assert s["cash"] == 179_413_000        # the 2026 figure, not the 2020 one
