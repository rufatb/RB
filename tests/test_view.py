"""Day-81: the one-screen decision view.

The full page is 461 lines and 77% of them are one section. A page that long
gets skimmed once and then trusted, which is the worst outcome: every caveat
present, none of them seen.

The rule this file enforces is that concision may drop DETAIL but never DOUBT.
A fair value flagged unreliable in the long page must still be flagged here.
"""

import datetime as dt

import view as V

TODAY = dt.date(2026, 8, 31)
NOW = dt.datetime(2026, 8, 31, 9, 46)


def digest(**over):
    d = {
        "now": NOW, "today": TODAY, "tz": "America/Toronto", "offline": True,
        "book": {"legs": [], "net_pct": None, "net_usd": None, "gross": 0,
                 "stale": 0},
        "closing": [], "upcoming": [], "pair_note": "nothing — engine not run",
        "cal": [], "priced": {}, "settled": {}, "mark_errors": {},
        "ledger_rows": [],
    }
    d.update(over)
    return d


def leg(**over):
    l = {"id": 1, "ticker": "ZYME", "side": "LONG", "entry_px": 24.90,
         "mark": 28.27, "pnl_pct": 13.53, "pnl_usd": 1348.0, "days": 12,
         "event_kind": "PDUFA", "event_date": "2026-08-25",
         "exit_condition": "close on PDUFA outcome", "thesis": "",
         "upside": 36.0, "downside": 20.5}
    l.update(over)
    return l


def setup_function():
    V.C.setup(force=False)          # deterministic, colour off


# ── it must fit on a screen ─────────────────────────────────────────────────

def test_the_whole_point_is_that_it_fits_on_one_screen():
    d = digest(book={"legs": [leg()], "net_pct": 13.53, "net_usd": 1348.0,
                     "gross": 9960, "stale": 0},
               closing=[leg()],
               cal=[{"date": "2026-09-22", "ticker": "IONS", "company": "X"}])
    out = V.render(d)
    assert len(out.split("\n")) < 60, "the short page has stopped being short"


def test_a_flat_book_says_so_rather_than_printing_an_empty_table():
    assert "flat" in V.render(digest())


# ── concision may drop detail, never doubt ──────────────────────────────────

def test_an_unreliable_fair_value_is_still_marked():
    """THE RULE. A caveat the long page carries must survive the short one."""
    fv = {"fair": 5.0, "ordinary": 4.0, "own3": 2.0, "event": 1.0,
          "fair_lo": 4.5, "fair_hi": 5.5,
          "cross": {"faults": [("LOGNORMAL", "sigma is outlier-driven")]}}
    d = digest(cal=[{"date": "2026-09-22", "ticker": "IONS", "company": "X"}],
               priced={"IONS": {"ticker": "IONS", "fv": fv, "put_pct": 0.05}})
    out = V.render(d)
    assert "~" in out
    assert "indicative only" in out


def test_a_clean_fair_value_is_not_marked():
    """A mark that appears on everything conveys nothing."""
    fv = {"fair": 5.0, "ordinary": 4.0, "own3": 2.0, "event": 1.0,
          "fair_lo": 4.5, "fair_hi": 5.5, "cross": {"faults": []}}
    d = digest(cal=[{"date": "2026-09-22", "ticker": "IONS", "company": "X"}],
               priced={"IONS": {"ticker": "IONS", "fv": fv, "put_pct": 0.05}})
    assert "~put" not in V.render(d)


def test_an_unmarkable_position_is_surfaced_not_hidden():
    """Rule 2: absence of a mark is not absence of movement."""
    d = digest(book={"legs": [leg(mark=None, pnl_pct=None, pnl_usd=None)],
                     "net_pct": 0.0, "net_usd": 0.0, "gross": 0, "stale": 1},
               mark_errors={"ZYME": "HTTPError"})
    out = V.render(d)
    assert "EXCLUDED" in out and "HTTPError" in out


def test_a_decision_with_no_ticker_is_reported_as_unpriceable():
    """BMY's 2027 PDUFA resolves to no ticker and cannot be priced at all.

    Printing a blank column would read as a name with no quote, which is a
    different and much less serious problem.
    """
    d = digest(cal=[{"date": "2027-05-13", "ticker": "",
                     "company": "BRISTOL MYERS SQUIBB CO"}])
    out = V.render(d)
    assert "no ticker resolved" in out
    assert "BRISTOL MYERS SQUIBB" in out


# ── the action section ──────────────────────────────────────────────────────

def test_a_settled_binary_says_the_thesis_is_spent():
    d = digest(book={"legs": [leg()], "net_pct": 13.53, "net_usd": 1348.0,
                     "gross": 9960, "stale": 0},
               closing=[leg()],
               settled={"ZYME": {"outcome": "APPROVED"}})
    out = V.render(d)
    assert "EXIT ZYME" in out
    assert "SETTLED" in out and "spent" in out


def test_nothing_due_is_a_normal_morning_not_a_prompt_to_trade():
    """The old report manufactured a pair every session. This must not."""
    out = V.render(digest())
    assert "nothing due" in out
    assert "normal morning" in out


def test_the_open_line_does_not_stutter():
    """`pair_note` already starts with 'nothing —'; prefixing it repeated it."""
    out = V.render(digest(pair_note="nothing — engine not ready"))
    assert "nothing — nothing" not in out


def test_an_upcoming_binary_window_demands_a_decision():
    d = digest(upcoming=[(leg(event_date="2026-09-10"), 10)])
    out = V.render(d)
    assert "DECIDE" in out and "10d" in out


# ── the record travels with the advice ──────────────────────────────────────

def test_the_live_record_is_printed_even_when_it_is_bad():
    rows = [{"role": "pair", "hit": "1"}] * 38 + [{"role": "pair", "hit": "0"}] * 47
    out = V.render(digest(ledger_rows=rows))
    assert "38/85" in out and "45%" in out
    assert "coin flip" in out


def test_no_scored_legs_says_so_rather_than_printing_nothing():
    assert "no scored pair legs yet" in V.render(digest())


# ── presentation mechanics ──────────────────────────────────────────────────

def test_colour_is_off_when_not_a_terminal():
    """Piping to a file must give clean text, not escape codes."""
    V.C.setup(force=False)
    out = V.render(digest(book={"legs": [leg()], "net_pct": 13.53,
                                "net_usd": 1348.0, "gross": 9960, "stale": 0}))
    assert "\033[" not in out


def test_the_pnl_bar_clamps_and_says_so():
    """A bar that silently saturates makes +30% and +300% look identical."""
    V.C.setup(force=False)
    assert "▸" in V.bar(300.0)
    assert "▸" not in V.bar(5.0)
    assert V.bar(None).strip() == ""


def test_the_bar_puts_gains_right_of_centre_and_losses_left():
    V.C.setup(force=False)
    up, down = V.bar(20.0), V.bar(-20.0)
    mid = 20 // 2
    assert "█" in up[mid:] and "█" not in up[:mid]
    assert "█" in down[:mid] and "█" not in down[mid + 1:]


def test_render_survives_a_digest_with_nothing_in_it():
    """A partial run must still draw a page rather than raising."""
    assert V.render({})


# ── the pair must print as an ORDER, not a headline ─────────────────────────

def _pair_digest():
    return digest(
        pair_note="SU.TO, BMO.TO", shadow=False,
        res={"max_chase_pct": 0.04,
             "pair": {"long": {"sided": 0.56,
                               "pick": {"t": "SU.TO", "p945": 93.36,
                                        "shares": 135, "alloc": 12613}},
                      "short": {"sided": 0.57,
                                "pick": {"t": "BMO.TO", "p945": 239.04,
                                         "shares": 55, "alloc": 13132}}}},
        cost=[{"ticker": "SU.TO", "cost": {"bps": 16, "usd": 20}},
              {"ticker": "BMO.TO", "cost": {"bps": 5, "usd": 7}}])


def test_the_pair_prints_side_size_and_fill_bound():
    """It first shipped as `OPEN SU.TO, BMO.TO` — unactionable.

    The one line that asks for an action has to carry the action.
    """
    out = V.render(_pair_digest())
    assert "BUY" in out and "SHORT" in out
    assert "SU.TO" in out and "BMO.TO" in out
    assert "135 sh" in out and "55 sh" in out
    assert "fill" in out and "93.4" in out


def test_the_pair_carries_what_it_costs_to_express():
    """The edge is measured at zero, so the spread IS the expectation.

    A BUY printed without it reads far better than it is — dropping doubt.
    """
    out = V.render(_pair_digest())
    assert "$27 behind" in out
    assert "IS" in out and "outcome" in out


def test_an_unknown_spread_is_not_reported_as_zero():
    """Rule 2: absence of a quote is not absence of cost."""
    d = _pair_digest()
    d["cost"] = [{"ticker": "SU.TO", "cost": {"bps": None, "usd": None}}]
    out = V.render(d)
    assert "not zero, unknown" in out


def test_a_side_that_did_not_qualify_is_not_forced():
    d = _pair_digest()
    d["res"]["pair"]["short"] = {"status": "NONE", "pick": None}
    out = V.render(d)
    assert "none qualified" in out and "not forced" in out
