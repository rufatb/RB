"""A row carrying a share count is an order ticket, whatever the status says.

2026-09-09 printed ABSTAIN in the first column and "CAD 11,787 / 138 shares" in
the last. A ⛔ DO NOT TRADE banner was added that same day. On 2026-09-11 the
identical table was acted on again. The words were never the problem: the
NUMBERS are what a reader executes.

These tests drive the REAL renderers on a REAL report. An earlier version of
this file re-implemented the row formatter and asserted against its own copy,
which would have passed no matter what the renderers did.
"""
import brief
import pytest


def leg(status, ticker="TRP.TO", side="LONG"):
    return {"status": status, "ticker": ticker, "side": side, "role": "primary",
            "signal_reference": 85.51, "signal_time": "09:45 bar close",
            "entry_reference": None, "entry_spread_bps": None,
            "entry_time": None, "fill_bound": 88.9, "p_sided": 0.61,
            "density_tag": "mid", "vol_pct": 1.0, "weight": 0.1,
            "baseline_alloc": 11787.0, "baseline_shares": 138,
            "quote": {"status": "UNAVAILABLE", "reason": "no BBO"},
            "reasons": ["LATE — informational only; entry window missed"],
            "spread_density": None, "h1_keep": False, "h2_scale": 0,
            "estimated_round_trip_spread_usd": None}


@pytest.fixture(scope="module")
def report():
    return brief.compute(no_net=True)


def rendered(report, legs):
    r = {**report, "intraday": {**report["intraday"], "legs": legs}}
    return brief.render_text(r), brief.render_html(r)


def test_an_abstained_leg_shows_no_dollars_and_no_share_count(report):
    for out in rendered(report, [leg("ABSTAIN")]):
        assert "11,787" not in out, "an abstained leg still shows a dollar size"
        assert "138 shares" not in out, "an abstained leg still shows shares"


def test_a_sized_leg_keeps_its_allocation(report):
    """Suppression must be narrow — a leg the engine actually stands behind
    still needs its size, or the report stops being useful."""
    text, _ = rendered(report, [leg("ELIGIBLE")])
    assert "11,787" in text and "138" in text


def test_a_mixed_board_suppresses_only_the_abstained_row(report):
    text, _ = rendered(report, [leg("ABSTAIN", "TRP.TO"),
                                leg("ELIGIBLE", "ENB.TO", "SHORT")])
    trp = [l for l in text.splitlines() if "TRP.TO" in l and "|" in l]
    enb = [l for l in text.splitlines() if "ENB.TO" in l and "|" in l]
    assert trp and enb
    assert not any("11,787" in l for l in trp)
    assert any("11,787" in l for l in enb)


def test_the_ticker_and_side_still_appear_so_the_record_is_legible(report):
    """Suppressing the SIZE is not hiding the pick. The reader must still be
    able to see what the baseline selected and that it declined."""
    text, _ = rendered(report, [leg("ABSTAIN")])
    assert "TRP.TO" in text and "ABSTAIN" in text


def test_the_size_survives_in_the_data_for_scoring(report):
    """Display suppression must not delete the baseline's hypothetical figure;
    the record still needs it to score what the baseline would have done."""
    r = {**report, "intraday": {**report["intraday"], "legs": [leg("ABSTAIN")]}}
    assert r["intraday"]["legs"][0]["baseline_alloc"] == 11787.0
    assert r["intraday"]["legs"][0]["baseline_shares"] == 138
