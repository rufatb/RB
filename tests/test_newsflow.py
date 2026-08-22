"""Day-62: overnight filing flow for held and watched names.

Two failure modes to guard: burying a material filing under routine noise,
and reporting a fetch failure as silence.
"""

import datetime as dt

import newsflow as N

TODAY = dt.date(2026, 8, 22)
SINCE = TODAY - dt.timedelta(days=45)


def _f(date, form, items="", cik="1"):
    return {"date": date, "form": form,
            "items": [x for x in items.split(",") if x], "accession": "a",
            "cik": cik}


def test_a_share_offering_is_flagged_not_filed_under_routine():
    """INO filed two 424B5s in eight days against 1.9 quarters of runway.
    The first version of this file treated a prospectus supplement as
    housekeeping."""
    desc, flag = N.describe(_f("2026-07-30", "424B5"))
    assert flag is True
    assert "SHARES BEING SOLD" in desc and "dilution" in desc


def test_a_shelf_registration_is_capacity_not_an_event():
    desc, flag = N.describe(_f("2026-07-01", "S-3"))
    assert flag is False and "capacity to sell" in desc


def test_red_flag_items_are_flagged():
    for item in ("3.01", "1.02", "5.02", "4.02", "2.04", "3.02"):
        _, flag = N.describe(_f("2026-08-01", "8-K", item))
        assert flag is True, item


def test_routine_items_are_not_flagged():
    for item in ("2.02", "7.01", "8.01", "1.01"):
        _, flag = N.describe(_f("2026-08-01", "8-K", item))
        assert flag is False, item


def test_delisting_notice_is_named_even_if_the_company_avoids_the_word():
    desc, _ = N.describe(_f("2026-08-01", "8-K", "3.01"))
    assert "DELISTING" in desc


def test_item_9_01_exhibits_never_stands_alone_as_the_description():
    desc, _ = N.describe(_f("2026-08-01", "8-K", "8.01,9.01"))
    assert "exhibits" not in desc and "FDA news" in desc


def test_form_4_is_reported_as_fact_not_signal():
    desc, flag = N.describe(_f("2026-08-01", "4"))
    assert flag is False and "a fact, not a signal" in desc


def test_repetitive_forms_collapse_into_one_counted_line():
    """CYTK's twelve Form 4s buried an INO offering three lines below."""
    filings = [_f(f"2026-07-{d:02d}", "4") for d in (14, 16, 23, 27, 30)]
    flagged, notable, bulk = N.summarise_name(filings)
    assert flagged == [] and notable == []
    assert "5 insider transactions" in bulk and "2026-07-14..2026-07-30" in bulk


def test_a_single_bulk_filing_shows_one_date_not_a_range():
    _, _, bulk = N.summarise_name([_f("2026-07-08", "4")])
    assert "2026-07-08" in bulk and ".." not in bulk


def test_material_filings_keep_their_own_line_beside_bulk():
    filings = [_f("2026-07-30", "424B5")] + [_f("2026-07-16", "4")] * 3
    flagged, notable, bulk = N.summarise_name(filings)
    assert len(flagged) == 1 and "3 insider transactions" in bulk


def test_a_fetch_failure_is_never_reported_as_silence():
    """'No news' and 'no data' look identical in a report and mean opposites."""
    out = N.render({"ZYME": {"filings": [], "error": "HTTPError"}}, SINCE, TODAY)
    assert "could not check" in out and "ZYME (HTTPError)" in out
    assert "no data is NOT the same as no news" in out
    assert "quiet: ZYME" not in out


def test_a_genuinely_quiet_name_is_listed_as_quiet():
    out = N.render({"ZYME": {"filings": [], "error": None}}, SINCE, TODAY)
    assert "quiet: ZYME" in out


def test_flagged_filings_sort_above_routine_ones_for_a_name():
    flow = {"INO": {"error": None, "filings": [
        _f("2026-08-12", "8-K", "2.02"), _f("2026-07-30", "424B5")]}}
    out = N.render(flow, SINCE, TODAY)
    lines = [l for l in out.splitlines() if "INO" in l]
    assert "424B5" in lines[0] and lines[0].strip().startswith("⚠")
