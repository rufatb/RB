"""An unstamped bid/ask, and how far it may be trusted.

Yahoo's /v7/finance/quote serves a usable two-sided quote and NO quote
timestamp — no bidAskTimestamp, no quoteTime, sizes 0 or None. `fresh()`
therefore fails on every name, every session, so every leg abstains on this
provider forever. On 2026-09-10 and 09-11 all four legs abstained for exactly
that reason while the books were uncrossed and the spreads were 1.5-15bps.

Refusing an unstamped quote is right. But unstamped is not unverifiable: a
one-minute trade bar IS timestamped, and a quote whose mid lies inside that
bar's range cannot be badly stale. That is a BOUND, not a certificate, so it
gets its own status and two separate opt-in switches.
"""
import datetime as dt

import pytest

import quotes as Q

NOW = dt.datetime(2026, 9, 11, 9, 46, tzinfo=dt.timezone.utc)


def row(bid=10.0, ask=10.02, **kw):
    out = {"symbol": "X.TO", "currency": "CAD", "bid": bid, "ask": ask,
           "regularMarketPrice": (bid + ask) / 2,
           "regularMarketTime": NOW.timestamp()}
    out.update(kw)
    return out


def bar(low=9.99, high=10.03, ts=None):
    return {"ts": (ts or NOW).timestamp(), "low": low, "high": high}


def test_without_a_corroborator_an_unstamped_quote_still_fails():
    """The default must not move. This is the behaviour of every run until
    somebody deliberately turns corroboration on."""
    v = Q.validate_equity(row(), "X.TO", NOW, currency="CAD")
    assert v["status"] == "UNAVAILABLE"
    assert "timestamp missing" in v["reason"]


def test_a_mid_inside_a_fresh_trade_bar_is_corroborated_not_OK():
    """CORROBORATED must never be OK. Nothing downstream may treat a bounded
    quote as a venue-certified one."""
    v = Q.validate_equity(row(), "X.TO", NOW, currency="CAD",
                          corroborate=lambda t: bar())
    assert v["status"] == Q.CORROBORATED
    assert v["status"] != "OK"
    assert v["spread_bps"] == pytest.approx((10.02 - 10.0) / 10.01 * 10000)
    assert v["corroborated_at"]
    assert "NOT an exchange-stamped BBO" in v["reason"]


def test_a_mid_outside_the_bar_is_refused():
    """THE DISCRIMINATING CASE, and it fires on real data: T.TO failed exactly
    here on 2026-09-11 while three other names passed. A quote whose mid is
    outside the prices actually printing may well be stale."""
    v = Q.validate_equity(row(bid=12.0, ask=12.02), "X.TO", NOW,
                          currency="CAD", corroborate=lambda t: bar())
    assert v["status"] == "UNAVAILABLE"


def test_a_stale_bar_corroborates_nothing():
    old = NOW - dt.timedelta(hours=3)
    v = Q.validate_equity(row(), "X.TO", NOW, currency="CAD",
                          corroborate=lambda t: bar(ts=old))
    assert v["status"] == "UNAVAILABLE"


def test_a_crossed_book_is_refused_before_corroboration_is_even_tried():
    """Corroboration answers 'is it current', never 'is it sane'. A crossed
    book is rejected on its own terms -- NTR.TO quoted bid 112.01 / ask 111.91
    on 2026-09-10."""
    called = []
    v = Q.validate_equity(row(bid=10.05, ask=10.0), "X.TO", NOW, currency="CAD",
                          corroborate=lambda t: called.append(t) or bar())
    assert v["status"] == "UNAVAILABLE"
    assert "crossed" in v["reason"]
    assert called == [], "corroboration ran on a book that was already invalid"


def test_a_corroborator_that_raises_is_no_proof_not_a_crash():
    def boom(t):
        raise ConnectionError("provider down")
    v = Q.validate_equity(row(), "X.TO", NOW, currency="CAD", corroborate=boom)
    assert v["status"] == "UNAVAILABLE"


def test_a_missing_or_malformed_bar_is_refused():
    for b in (None, {}, {"ts": NOW.timestamp()},
              {"ts": NOW.timestamp(), "low": 10.03, "high": 9.99},   # inverted
              {"ts": NOW.timestamp(), "low": 0, "high": 10.0}):      # nonpositive
        v = Q.validate_equity(row(), "X.TO", NOW, currency="CAD",
                              corroborate=lambda t, b=b: b)
        assert v["status"] == "UNAVAILABLE", b


def test_a_venue_stamped_quote_never_needs_corroboration():
    """When the venue DOES stamp the quote, that path is unchanged and wins."""
    called = []
    v = Q.validate_equity(row(bidAskTimestamp=NOW.timestamp()), "X.TO", NOW,
                          currency="CAD",
                          corroborate=lambda t: called.append(t) or bar())
    assert v["status"] == "OK"
    assert called == []


def test_the_bar_provider_verifies_the_symbol_it_got_back():
    """Rule 9. Yahoo silently redirects symbols; a bar for another name would
    corroborate nothing about this one."""
    import inspect
    src = inspect.getsource(Q.minute_bar_corroborator)
    assert 'meta.get("symbol") != ticker' in src
    assert "volume" in src, "a zero-volume minute has no range worth comparing"


# ── the two switches ───────────────────────────────────────────────────────

def leg_reasons(quote_status, accept):
    import execution
    cfg = {"risk": {"account_equity": 100000, "max_position_pct": 50},
           "pair": {}, "execution": {"accept_corroborated_bbo": accept}}
    res = {"pair": {"long": {"pick": {"t": "X.TO", "p945": 10.0, "p_up": 0.6,
                                      "vol": 1.0, "alloc": 1000, "shares": 100}},
                    "short": {}},
           "_allocation_done": True}
    # The ask must sit inside r945.fill_bound (max_chase 0.04% -> 10.004), or
    # an unrelated and correct guard abstains and this test measures that
    # instead of the switch it is about.
    q = {"X.TO": {"status": quote_status, "reason": "r", "bid": 10.0,
                  "ask": 10.002, "spread_bps": 2.0}}
    clock = {"eligible": True, "status": "09:46 publication window"}
    return execution.evaluate_legs(res, cfg, q, clock, shadow=False)[0]


def test_corroborated_alone_does_not_clear_the_abstain():
    """Measuring a spread and acting on it are two decisions."""
    leg = leg_reasons(Q.CORROBORATED, accept=False)
    assert leg["status"] == "ABSTAIN" and leg["reasons"]


def test_accepting_corroboration_clears_it_and_keeps_the_spread():
    leg = leg_reasons(Q.CORROBORATED, accept=True)
    assert leg["status"] != "ABSTAIN"
    assert leg["entry_spread_bps"] == 2.0


def test_accepting_corroboration_does_not_excuse_an_unavailable_quote():
    """The switch is narrow: it forgives a MISSING TIMESTAMP, never a missing
    or invalid quote."""
    leg = leg_reasons("UNAVAILABLE", accept=True)
    assert leg["status"] == "ABSTAIN"


def test_both_switches_default_to_off_in_the_shipped_config():
    import yaml
    cfg = yaml.safe_load(open("config.yaml"))
    ex = cfg.get("execution") or {}
    assert not ex.get("corroborate_bbo")
    assert not ex.get("accept_corroborated_bbo")
