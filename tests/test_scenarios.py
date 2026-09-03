"""Day-82 §7: the report must never show the PM an error. Five scenarios.

The Definition of Done names five days the report has to survive: a normal day,
a holiday, a day with no qualifying pair, a day with a stale quote, and a day
with the network refusing. Every failure must become a STATED, BOUNDED
consequence — which name, what is unavailable — never a traceback, never a bare
warning, and never a silently missing section.

"Unpriceable" is an acceptable output. A stack trace is not. Failing closed and
saying so is required; failing closed quietly to keep the page tidy is the
thing this file exists to prevent.
"""

import datetime as dt

import pytest

import view as V

NOW = dt.datetime(2026, 9, 3, 9, 46)
TODAY = dt.date(2026, 9, 3)


def base(**over):
    d = {"now": NOW, "today": TODAY, "tz": "America/Toronto", "offline": False,
         "book": {"legs": [], "net_pct": None, "net_usd": None, "gross": 0,
                  "stale": 0},
         "closing": [], "upcoming": [], "cal": [], "priced": {}, "settled": {},
         "mark_errors": {}, "ledger_rows": [], "pair_note": "nothing"}
    d.update(over)
    return d


def held(**over):
    l = {"id": 1, "ticker": "ZYME", "side": "LONG", "entry_px": 24.90,
         "mark": 29.38, "pnl_pct": 17.99, "pnl_usd": 1792.0, "days": 14,
         "event_kind": "PDUFA", "event_date": "2026-08-25",
         "exit_condition": "close on PDUFA outcome", "thesis": "",
         "upside": 36.0, "downside": 20.5}
    l.update(over)
    return l


def setup_function():
    V.C.setup(force=False)


def assert_clean(out: str):
    """No traceback, no exception class leaking, no empty page."""
    assert out.strip(), "the report rendered nothing at all"
    for marker in ("Traceback (most recent call last)", '  File "', "  ^^^"):
        assert marker not in out, f"traceback leaked into the report: {marker}"
    # A bare exception repr with no explanation is the 'bare warning' §6 bans.
    for line in out.split("\n"):
        s = line.strip()
        if s.startswith(("Exception", "ValueError", "KeyError", "TypeError")):
            raise AssertionError(f"unexplained exception in output: {s}")


# ── 1. a normal day ─────────────────────────────────────────────────────────

def test_normal_day_renders_a_book_an_action_and_a_record():
    d = base(book={"legs": [held()], "net_pct": 17.99, "net_usd": 1792.0,
                   "gross": 9960, "stale": 0},
             closing=[held()], settled={"ZYME": {"outcome": "APPROVED"}},
             ledger_rows=[{"role": "pair", "hit": "1", "side": "LONG",
                           "r1": "0.5"}] * 44
                         + [{"role": "pair", "hit": "0", "side": "LONG",
                             "r1": "-0.5"}] * 49)
    out = V.render(d)
    assert_clean(out)
    assert "BOOK" in out and "DO TODAY" in out and "RECORD" in out
    assert "+17.99%" in out


# ── 2. a holiday / pre-open: the engine has not run ─────────────────────────

def test_a_holiday_says_nothing_to_do_rather_than_inventing_a_trade():
    """The old report manufactured a pair every session, which trains a reader
    to trade a coin flip. A quiet day must be allowed to be quiet."""
    d = base(pair_note="nothing — engine not ready")
    out = V.render(d)
    assert_clean(out)
    assert "nothing due" in out and "normal morning" in out
    assert "BUY" not in out and "SHORT " not in out


def test_pre_open_does_not_present_the_absent_pair_as_a_decision():
    out = V.render(base(pair_note="nothing — too early; ready 09:46"))
    assert_clean(out)
    assert "too early" in out


# ── 3. no qualifying pair ───────────────────────────────────────────────────

def test_no_qualifying_pair_is_reported_as_a_refusal_not_a_gap():
    """A side that did not qualify must say so; a missing section reads as an
    oversight and invites the reader to assume the engine simply had nothing."""
    d = base(pair_note="SU.TO", shadow=False,
             publish={"already": False},
             res={"max_chase_pct": 0.04,
                  "pair": {"long": {"sided": 0.56,
                                    "pick": {"t": "SU.TO", "p945": 93.36,
                                             "shares": 135, "alloc": 12613}},
                           "short": {"status": "NONE", "pick": None}}},
             cost=[{"ticker": "SU.TO", "cost": {"bps": 16, "usd": 20}}])
    out = V.render(d)
    assert_clean(out)
    assert "none qualified" in out and "not forced" in out
    assert "BUY" in out and "SU.TO" in out


def test_the_coverage_gate_failing_is_stated():
    out = V.render(base(pair_note="nothing — coverage gate failed"))
    assert_clean(out)
    assert "coverage gate failed" in out


# ── 4. a stale quote ────────────────────────────────────────────────────────

def test_a_stale_quote_never_reads_as_a_flat_book():
    """mark_book totals only what it could price, so an all-unmarked book
    returns +0.00% on $0 — a flat, fully-priced book at a glance."""
    d = base(book={"legs": [held(mark=None, pnl_pct=None, pnl_usd=None)],
                   "net_pct": 0.0, "net_usd": 0.0, "gross": 0.0, "stale": 1},
             mark_errors={"ZYME": "RuntimeError"})
    out = V.render(d)
    assert_clean(out)
    assert "UNPRICED" in out and "not zero" in out
    assert "ZYME" in out and "RuntimeError" in out
    assert "+0.00%" not in out


def test_a_partly_stale_book_totals_what_it_can_and_flags_the_rest():
    d = base(book={"legs": [held(), held(id=2, ticker="IONS", mark=None,
                                         pnl_pct=None, pnl_usd=None)],
                   "net_pct": 17.99, "net_usd": 1792.0, "gross": 9960,
                   "stale": 1},
             mark_errors={"IONS": "HTTPError"})
    out = V.render(d)
    assert_clean(out)
    assert "+17.99%" in out and "EXCLUDED" in out and "HTTPError" in out


# ── 5. the network refusing ─────────────────────────────────────────────────

def test_everything_unavailable_still_renders_a_usable_page():
    """The dead-network shape: nothing markable, nothing priceable, no pair."""
    d = base(book={"legs": [held(mark=None, pnl_pct=None, pnl_usd=None)],
                   "net_pct": 0.0, "net_usd": 0.0, "gross": 0.0, "stale": 1},
             mark_errors={"ZYME": "ConnectionError"},
             cal=[{"date": "2026-09-22", "ticker": "IONS", "company": "IONIS"},
                  {"date": "2026-10-30", "ticker": "INO", "company": "INOVIO"}],
             pair_note="nothing — engine not ready",
             score_error="ConnectionError: connection refused")
    out = V.render(d)
    assert_clean(out)
    assert "UNPRICED" in out
    assert "unpriced" in out and "IONS" in out
    assert "scoring failed" in out and "STALE" in out


def test_a_scoring_failure_says_the_record_is_stale_not_nothing():
    """Silence here leaves a stale hit rate sitting beside live advice."""
    out = V.render(base(score_error="HTTPError: 429"))
    assert_clean(out)
    assert "STALE" in out


# ── the count must match the list it summarises ─────────────────────────────

def test_a_trimmed_list_says_how_many_it_trimmed():
    """It printed '9 calendar name(s) unpriced' above a list of 8 — a report
    contradicting itself in adjacent lines.

    Names are now grouped by their TYPED reason, so the trim applies per group;
    the invariant asserted is unchanged — a trimmed list states the remainder.
    """
    cal = [{"date": f"2026-10-{d:02d}", "ticker": f"T{d}", "company": "X"}
           for d in range(1, 13)]
    out = V.render(base(cal=cal))
    assert_clean(out)
    assert "12 calendar name(s)" in out
    assert "+6 more" in out          # 12 names, 6 shown per reason group


@pytest.mark.parametrize("missing", [
    "book", "closing", "upcoming", "cal", "priced", "settled",
    "mark_errors", "ledger_rows", "pair_note",
])
def test_any_single_missing_digest_key_still_renders(missing):
    """A partial build must degrade, not raise. Each key is a section that can
    legitimately fail to populate when its source is unavailable."""
    d = base()
    d.pop(missing, None)
    assert_clean(V.render(d))


# ── the integration proof: build() itself, not just the renderer ────────────

def test_build_survives_a_dead_network_end_to_end(monkeypatch, tmp_path):
    """THE ACTUAL `run report` PATH, not a hand-built digest.

    Every test above feeds `view.render` a digest shaped by hand, which proves
    the renderer degrades but not that `build()` produces a renderable digest
    when nothing outbound works. Those are different failures and only this
    one is what the PM would hit.
    """
    import requests
    import urllib.request as ur

    class Dead(requests.exceptions.ConnectionError):
        pass

    def refuse(*a, **k):
        raise Dead("connection refused (simulated)")

    for name in ("get", "post", "request"):
        monkeypatch.setattr(requests, name, refuse, raising=False)
    monkeypatch.setattr(requests.Session, "get", refuse, raising=False)
    monkeypatch.setattr(requests.Session, "request", refuse, raising=False)
    monkeypatch.setattr(ur, "urlopen", refuse, raising=False)

    import brief
    d = {}
    brief.build("config.yaml", False, False, 4, digest=d)   # must not raise
    out = V.render(d)
    assert_clean(out)
    assert "MORNING BRIEF" in out
    # It must still say what it could not do, rather than looking healthy.
    assert "UNPRICED" in out or "unpriced" in out or "stale" in out


def test_build_offline_mode_renders_without_touching_the_network():
    """`--offline` is the PM's escape hatch when the feed is down."""
    import brief
    d = {}
    brief.build("config.yaml", False, True, 4, digest=d)
    out = V.render(d)
    assert_clean(out)
    assert "MORNING BRIEF" in out


# ── a feed outage is not fourteen illiquid companies ────────────────────────

def test_a_dead_options_feed_is_reported_once_not_per_name():
    """At 06:47 ET every name on the board failed its checks — and so did SPY,
    whose ATM put quoted 0.00/0.00. Reporting that per name told the PM half
    the calendar was illiquid when the options market was simply shut."""
    priced = {f"T{i}": {"ticker": f"T{i}", "feed_live": False}
              for i in range(1, 7)}
    cal = [{"date": f"2026-10-0{i}", "ticker": f"T{i}", "company": "X"}
           for i in range(1, 7)]
    out = V.render(base(cal=cal, priced=priced))
    assert_clean(out)
    assert "OPTIONS FEED NOT LIVE" in out
    # the sentence is wrapped, so compare on normalised whitespace rather than
    # weakening the assertion to a fragment
    flat = " ".join(out.split())
    assert "nothing here says a name is illiquid" in flat
    assert "failed its checks" not in out


def test_with_a_live_feed_names_are_grouped_by_their_typed_reason():
    """'failed its checks' was one sentence for six distinct causes, and the
    reader could act on none of them."""
    priced = {
        "AAA": {"ticker": "AAA", "feed_live": True,
                "reason_why": "no listed expiry covers the decision date"},
        "BBB": {"ticker": "BBB", "feed_live": True,
                "reason_why": "no open interest on the at-the-money strike"},
    }
    cal = [{"date": "2026-10-01", "ticker": "AAA", "company": "X"},
           {"date": "2026-10-02", "ticker": "BBB", "company": "Y"}]
    out = V.render(base(cal=cal, priced=priced))
    assert_clean(out)
    flat = " ".join(out.split())
    assert "no listed expiry covers the decision date" in flat
    assert "no open interest on the at-the-money strike" in flat


def test_a_total_history_outage_is_a_coverage_failure_not_an_exception():
    """DAY-83. Under a dead feed `hist_rows` is empty, so `pd.DataFrame([])`
    has no columns and `groupby("t")` raised KeyError: 't' — straight out of
    r945.run and out of brief.build, the one path the report is guaranteed
    never to show the PM. A total fetch failure is a coverage failure, which
    this engine already knows how to report."""
    import pandas as pd
    import r945
    assert pd.DataFrame([]).empty          # the shape that caused it
    flat = " ".join(open(r945.__file__).read().split())
    # fragments, because the message is assembled across f-string literals
    assert "NO TRAINING HISTORY" in flat
    assert "the model cannot be fitted" in flat
    assert "data outage" in flat
    # and the guard must precede the groupby it protects
    assert flat.index("NO TRAINING HISTORY") < flat.index('train.groupby("t")')
