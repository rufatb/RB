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
    """Rule 2: absence of a mark is not absence of movement.

    The leg must be visible as unpriced AND the reason named. Which wording
    carries it depends on whether ANY leg could be marked -- see the two tests
    at the end of this file -- so this asserts the surfacing, not the phrasing.
    """
    d = digest(book={"legs": [leg(mark=None, pnl_pct=None, pnl_usd=None)],
                     "net_pct": 0.0, "net_usd": 0.0, "gross": 0, "stale": 1},
               mark_errors={"ZYME": "HTTPError"})
    out = V.render(d)
    assert "stale" in out and "HTTPError" in out
    assert "+0.00%" not in out


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
    assert "IS the expectation" in out


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


# ── a re-read must show the PUBLISHED board, not a fresh one ────────────────

def test_a_re_read_says_it_is_a_re_read():
    """The board is the 9:46 instruction; a later run reads it back.

    Saying so is the difference between an order and a reminder.
    """
    d = _pair_digest()
    d["publish"] = {"already": True,
                    "restore_note": "restored exactly from the published board"}
    out = V.render(d)
    assert "re-read of the 9:46 board" in out
    # Restored exactly -> no caveat ON THAT LINE. Asserting "re-derived" is
    # absent from the whole page was too broad: an unrelated tension about a
    # re-derived constant now legitimately uses the same word.
    line = next(l for l in out.split("\n") if "re-read of the 9:46 board" in l)
    assert "re-derived" not in line


def test_a_re_read_whose_sizes_were_re_derived_says_so():
    """An approximate restore must not read like an exact one."""
    d = _pair_digest()
    d["publish"] = {"already": True,
                    "restore_note": "share counts re-derived from the "
                                    "published allocation and the 9:45 print"}
    out = V.render(d)
    assert "re-read of the 9:46 board" in out and "re-derived" in out


def test_an_unrestorable_size_is_blank_not_recomputed():
    """DAY-81. SU.TO published at 135 shares and read back at 136.

    `allocate_book` sizes off the LIVE price and ran before the publish-once
    guard, so every re-read re-sized against the current tape while the page
    claimed the counts came from the published board. A size the ledger does
    not score is worse than no size at all.
    """
    d = _pair_digest()
    d["publish"] = {"already": True, "restored": False,
                    "restore_note": "1 leg(s) could not be restored"}
    d["res"]["pair"]["long"]["pick"]["shares"] = None
    out = V.render(d)
    assert "not restorable" in out
    assert "do not size from here" in out
    assert "135 sh" not in out and "136 sh" not in out


# ── the discipline that keeps it short ──────────────────────────────────────

def _fat_digest():
    """A busy morning: a position, an exit, a pair, and ranked opportunities."""
    fv = {"fair": 26.3, "ordinary": 20.0, "own3": 3.0, "event": 6.3,
          "fair_lo": 24.0, "fair_hi": 29.0,
          "cross": {"faults": [("LOGNORMAL", "sigma is outlier-driven")]}}
    def opp(t, days, ratio, call):
        return {"ticker": t, "days": days, "put_pct": 0.117, "fv": fv,
                "fv_ratio": ratio, "verdict": {"call": call}}
    d = _pair_digest()
    d.update(
        book={"legs": [leg()], "net_pct": 13.53, "net_usd": 1348.0,
              "gross": 9960, "stale": 0},
        closing=[leg()], settled={"ZYME": {"outcome": "APPROVED"}},
        cal=[{"date": "2027-05-13", "ticker": "", "company": "BRISTOL MYERS"}],
        ledger_rows=[{"role": "pair", "hit": "1"}] * 38
                    + [{"role": "pair", "hit": "0"}] * 47,
        ranked={"buckets": {
            "WEEK": [],
            "MONTH": [opp("IONS", 22, 0.89, "DOWNSIDE IS THE CHEAPER SIDE")],
            "QUARTER": [opp("PRAX", 118, 0.44, "STAND ASIDE INTO THE PRINT"),
                        opp("CYTK", 75, 0.84, "STAND ASIDE INTO THE PRINT")]},
            "skipped": [("INO", "quote failed its checks")], "base": {}})
    return d


def test_no_line_overflows_the_column():
    """Wrapped text is the whole point; an overflowing line breaks the layout.

    Overflow crept back three times, so it is asserted rather than eyeballed.
    """
    V.C.setup(force=False)
    over = [l for l in V.render(_fat_digest()).split("\n") if len(l) > 76]
    assert not over, "over-width:\n" + "\n".join(f"{len(l)}: {l}" for l in over)


def test_a_busy_morning_still_fits_on_one_screen():
    V.C.setup(force=False)
    n = len(V.render(_fat_digest()).split("\n"))
    assert n <= 50, f"the short page has grown to {n} lines"


# ── opportunities are ranked by value, not by date ──────────────────────────

def test_opportunities_are_ranked_cheapest_first_across_horizons():
    """PRAX at 0.44x sits 118d out and was invisible in a date-ordered list.

    The screen's whole output is the ranking; showing the FDA's diary instead
    hides the one name it exists to surface.
    """
    out = V.render(_fat_digest())
    body = out[out.index("OPPORTUNITIES"):]
    assert body.index("PRAX") < body.index("CYTK") < body.index("IONS")


def test_a_ranked_but_unreliable_fair_value_is_marked_in_place():
    out = V.render(_fat_digest())
    assert "~PRAX" in out
    assert "not a price to act on" in out


def test_the_absent_long_side_gives_its_reason():
    """Absent without a reason reads as an oversight rather than a decision."""
    out = V.render(_fat_digest())
    assert "no long ranked" in out
    assert "|t|>=3" in out          # the bar it failed, not just that it failed


def test_names_excluded_for_a_bad_quote_are_named():
    assert "INO" in V.render(_fat_digest())


def test_verdicts_are_tagged_not_truncated_mid_word():
    """"DOWNSIDE IS THE CHEAPER SI" is not a verdict."""
    out = V.render(_fat_digest())
    assert "downside cheaper" in out
    assert "CHEAPER SI\n" not in out and "CHEAPER SI " not in out


def test_an_unmapped_verdict_falls_through_rather_than_blanking():
    """A new verdict string must still print, not vanish."""
    d = _fat_digest()
    d["ranked"]["buckets"]["MONTH"][0]["verdict"] = {"call": "SOMETHING NEW"}
    assert "something new" in V.render(d)


def test_the_tilde_hint_names_a_name_actually_shown():
    """It named COGT, which is excluded from the ranking and never marked ~."""
    out = V.render(_fat_digest())
    import re
    m = re.search(r"fairvalue\.py (\w+)", out)
    assert m, "no hint printed"
    assert f"~{m.group(1)}" in out, f"{m.group(1)} is not marked ~ on the page"


# ── the record must not go stale in silence ─────────────────────────────────

def test_legs_scored_this_morning_are_reported():
    """On 2026-09-01 the page showed 38/85 while four legs sat unscored.

    The report told the reader to run `ledger.py --score` after the close and
    nobody did — the day-80 finding about the catalyst ledger, repeated.
    """
    out = V.render(digest(scored_now=4))
    assert "4 leg(s) scored this morning" in out


def test_a_failed_scoring_run_says_the_record_is_stale():
    """Rule 1. A silent failure here leaves a stale hit rate beside advice."""
    out = V.render(digest(score_error="HTTPError: 429"))
    assert "scoring failed" in out and "STALE" in out


def test_legs_held_back_for_an_open_session_are_reported():
    """Day-24: scoring mid-session writes live prices in as outcomes."""
    out = V.render(digest(held_back=4))
    assert "held back" in out and "not closed" in out


# ── an unpriced book must not read as a flat one ────────────────────────────

def test_a_book_with_no_markable_leg_says_unpriced_not_zero():
    """Seen live 2026-09-02: one transient quote failure blanked the book.

    `mark_book` totals only what it could price, so a fully-unmarked book
    returns +0.00% on $0 — which at a glance reads as a flat, fully-priced
    book. It is the opposite: nothing is known. Rule 2.
    """
    d = digest(book={"legs": [leg(mark=None, pnl_pct=None, pnl_usd=None)],
                     "net_pct": 0.0, "net_usd": 0.0, "gross": 0.0, "stale": 1},
               mark_errors={"ZYME": "RuntimeError"})
    out = V.render(d)
    assert "UNPRICED" in out
    assert "not zero" in out
    assert "+0.00%" not in out


def test_a_partly_marked_book_still_shows_its_total_and_the_exclusion():
    """Only the ALL-unmarked case is unknowable; a partial book still totals,
    and must still say that the stale leg is excluded from that total."""
    d = digest(book={"legs": [leg()], "net_pct": 13.53, "net_usd": 1348.0,
                     "gross": 9960, "stale": 1})
    out = V.render(d)
    assert "UNPRICED" not in out and "+13.53%" in out
    assert "EXCLUDED" in out


def test_an_unpriced_book_still_lists_its_positions():
    """The first fix split the header into two branches and left the leg rows
    inside only one, so an unpriced book showed no positions at all — the
    failure hid the very thing it was reporting."""
    d = digest(book={"legs": [leg(mark=None, pnl_pct=None, pnl_usd=None)],
                     "net_pct": 0.0, "net_usd": 0.0, "gross": 0.0, "stale": 1},
               mark_errors={"ZYME": "RuntimeError"})
    out = V.render(d)
    assert "UNPRICED" in out
    assert "ZYME" in out and "24.90" in out      # the row itself


def test_the_tilde_hint_is_absent_when_nothing_is_marked():
    """Pre-market nothing ranks, so nothing carries a ~ — and the hint
    explaining the mark was still printing, pointing at a name not on the
    page."""
    d = digest(priced={"COGT": {"ticker": "COGT", "feed_live": False,
                                "fv": {"fair": 5.0, "cross": {
                                    "faults": [("LOGNORMAL", "x")]}}}})
    out = V.render(d)
    assert "fairvalue.py" not in out


def test_wrapped_lines_indent_their_continuations():
    """Every line shared one pad, so a wrapped warning read as two bullets at
    the same level and hid where one item ended and the next began."""
    V.C.setup(force=False)
    lines = V._wrap("a " * 60, 4)
    assert len(lines) > 1
    assert lines[0].startswith("    ") and lines[0][4] != " "
    assert all(l.startswith("      ") for l in lines[1:])


# ── day-87: the page must show the WHOLE book, not the primary leg only ────

def _two_leg_digest(shadow=False):
    """A two-leg-a-side book, which is what config ships (legs_per_side: 2)."""
    return {
        "shadow": shadow,
        "publish": {},
        "cost": [],
        "res": {"max_chase_pct": 0.04,
                "pair": {
                    "long": {"pick": {"t": "ABX.TO", "p945": 40.0,
                                      "shares": 199, "alloc": 7960.0},
                             "extra": [{"t": "AEM.TO", "p945": 290.0,
                                        "shares": 27, "alloc": 7830.0}]},
                    "short": {"pick": {"t": "SLF.TO", "p945": 111.75,
                                       "shares": 126, "alloc": 14080.0},
                              "extra": [{"t": "CM.TO", "p945": 163.55,
                                         "shares": 65, "alloc": 10631.0}]}}}}


def test_the_extra_legs_reach_the_page():
    """REGRESSION. Between day-81 and day-87 this page read only `pick`, so a
    sized, published, scored leg never appeared. On 2026-09-04 the book held
    SLF 126sh AND CM 65sh; the page showed SLF alone, and CM was the leg that
    won. The page and the ledger must describe the same book."""
    out = "\n".join(V._pair_lines(_two_leg_digest(), "open"))
    for t in ("ABX.TO", "AEM.TO", "SLF.TO", "CM.TO"):
        assert t in out, f"{t} missing from the order block:\n{out}"


def test_every_displayed_leg_carries_its_size_and_fill_bound():
    """A leg printed without a size is a headline pretending to be an order."""
    out = "\n".join(V._pair_lines(_two_leg_digest(), "open"))
    for shares in ("199", "27", "126", "65"):
        assert f"{shares} sh" in out, f"{shares} sh missing:\n{out}"
    assert out.count("fill") == 4


def test_the_extra_leg_takes_the_side_of_its_parent():
    out = "\n".join(V._pair_lines(_two_leg_digest(), "open"))
    long_block = out.split("SHORT")[0]
    assert "AEM.TO" in long_block, "the long extra was rendered on the wrong side"
    assert "CM.TO" not in long_block, "the short extra leaked into the long side"


def test_a_side_with_no_extra_still_renders_its_primary():
    d = _two_leg_digest()
    d["res"]["pair"]["short"]["extra"] = []
    out = "\n".join(V._pair_lines(d, "open"))
    assert "SLF.TO" in out and "CM.TO" not in out


def test_an_extra_without_a_ticker_is_skipped_not_printed_blank():
    d = _two_leg_digest()
    d["res"]["pair"]["short"]["extra"] = [{"p945": 1.0, "shares": 5}]
    out = "\n".join(V._pair_lines(d, "open"))
    assert "SLF.TO" in out
    assert "SHORT  " not in out.replace("SHORT SLF.TO", "")


def test_shadow_mode_shows_the_extra_without_a_size():
    """Shadow mode never prints share counts — for any leg."""
    out = "\n".join(V._pair_lines(_two_leg_digest(shadow=True), "open"))
    assert "CM.TO" in out and "AEM.TO" in out
    assert " sh" not in out
