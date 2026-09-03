"""Day-82 §2: the option-quote path, typed, with a feed control.

The screen wrapped its whole option fetch in one `except Exception` recording
only the exception class, and its silent paths recorded nothing, so six
distinct causes reached the report as one sentence: "quotes failed their
checks". Run at 06:47 ET that sentence covered every name on the board — and
SPY, whose at-the-money put quoted 0.00/0.00.

The control is the fix: price a contract whose liquidity is not in question
before drawing any conclusion about a name.
"""

import quotes as Q


def chain_stub(spot=100.0, expiries=(1_800_000_000,), bid=1.0, ask=1.2,
               oi=500, puts=True, raises=False):
    """A minimal Yahoo-shaped chain, so the control logic is testable offline."""
    def fn(ticker, expiry=None):
        if raises:
            raise ConnectionError("simulated")
        if expiry is None:
            return {"quote": {"regularMarketPrice": spot},
                    "expirationDates": list(expiries)}
        rows = ([{"strike": spot, "bid": bid, "ask": ask, "lastPrice": 1.1,
                  "openInterest": oi}] if puts else [])
        return {"options": [{"calls": [], "puts": rows}]}
    return fn


# ── the control decides whether a failure is about the name or the feed ─────

def test_a_two_sided_control_means_the_feed_is_live():
    live, why = Q.feed_is_live(chain_stub(bid=1.0, ask=1.2))
    assert live and "quotes" in why


def test_a_zero_quote_on_the_control_means_the_feed_is_not_live():
    """THE CASE THIS EXISTS FOR. SPY's ATM put at 0.00/0.00 is not a fact
    about SPY. It is a fact about the feed."""
    live, why = Q.feed_is_live(chain_stub(bid=0.0, ask=0.0))
    assert not live
    assert "no two-sided quote" in why
    assert "no per-name liquidity conclusion" in why


def test_a_control_that_cannot_be_fetched_is_not_live():
    live, why = Q.feed_is_live(chain_stub(raises=True))
    assert not live and "chain failed" in why


def test_a_control_with_no_puts_is_not_live():
    live, why = Q.feed_is_live(chain_stub(puts=False))
    assert not live and "no puts" in why


# ── the typed reasons ───────────────────────────────────────────────────────

def atm(bid=1.0, ask=1.2, oi=500):
    return {"strike": 100.0, "bid": bid, "ask": ask, "openInterest": oi}


def test_a_clean_quote_classifies_ok():
    assert Q.classify(100.0, [1], 1, [atm()], atm(), 0.001, 0.03) == Q.OK


def test_each_stage_reports_its_own_reason_not_a_generic_failure():
    """Six causes reached the report as one sentence and the reader could act
    on none of them."""
    assert Q.classify(None, [1], 1, [atm()], atm(), 0, 0.03) == Q.NO_SPOT
    assert Q.classify(100.0, [], None, [], None, 0, 0.03) == Q.NO_EXPIRIES
    assert Q.classify(100.0, [1], None, [], None, 0, 0.03) == \
        Q.NO_EXPIRY_AFTER_EVENT
    assert Q.classify(100.0, [1], 1, [], None, 0, 0.03) == Q.NO_PUTS
    assert Q.classify(100.0, [1], 1, [atm()], None, 0, 0.03) == Q.NO_PUTS


def test_the_earliest_cause_wins_over_a_later_one():
    """A name with no expiry covering its decision is not ALSO 'no two-sided
    quote' — reporting the later cause would send the reader after the wrong
    problem."""
    assert Q.classify(100.0, [1], None, [], atm(bid=0, ask=0), 0, 0.03) == \
        Q.NO_EXPIRY_AFTER_EVENT


def test_a_missing_two_sided_quote_is_the_name_when_the_feed_is_live():
    r = Q.classify(100.0, [1], 1, [atm()], atm(bid=0, ask=0), 0, 0.03,
                   feed_live=True)
    assert r == Q.NO_TWO_SIDED


def test_the_same_missing_quote_is_the_FEED_when_the_control_failed():
    """The identical observation means opposite things depending on the
    control, which is the entire point of having one."""
    r = Q.classify(100.0, [1], 1, [atm()], atm(bid=0, ask=0), 0, 0.03,
                   feed_live=False)
    assert r == Q.FEED_CLOSED


def test_zero_open_interest_is_also_disambiguated_by_the_control():
    assert Q.classify(100.0, [1], 1, [atm()], atm(oi=0), 0, 0.03,
                      feed_live=True) == Q.ZERO_OI
    assert Q.classify(100.0, [1], 1, [atm()], atm(oi=0), 0, 0.03,
                      feed_live=False) == Q.FEED_CLOSED


def test_a_parity_break_is_a_property_of_the_name():
    assert Q.classify(100.0, [1], 1, [atm()], atm(), 0.5, 0.03) == \
        Q.PARITY_BREAK
    assert Q.PARITY_BREAK in Q.ABOUT_THE_NAME


def test_feed_failures_are_not_attributed_to_the_company():
    """Reporting an outage as a property of a company is the mislabelling this
    module exists to stop."""
    for r in (Q.FEED_CLOSED, Q.CHAIN_ERROR, Q.NO_SPOT, Q.NO_EXPIRIES):
        assert r in Q.ABOUT_THE_FEED
        assert r not in Q.ABOUT_THE_NAME


def test_every_reason_has_a_plain_explanation():
    """A typed reason nobody can read is the generic sentence again."""
    for name, val in vars(Q).items():
        if name.isupper() and isinstance(val, str) and name != "CONTROL_TICKER":
            if val in (Q.OK,) or not name.startswith(("NO_", "ZERO", "PARITY",
                                                      "FEED", "CHAIN")):
                continue
            assert val in Q.EXPLAIN, f"{name} has no explanation"
            assert len(Q.EXPLAIN[val]) > 10


# ── the summary: one line for an outage, never one per name ─────────────────

def test_a_dead_feed_summarises_once():
    qs = [Q.Quote(f"T{i}", Q.FEED_CLOSED) for i in range(6)]
    lines = Q.summarise(qs, False, "control SPY has no two-sided quote")
    assert len(lines) == 3
    assert "OPTIONS FEED NOT LIVE" in lines[0]
    assert "nothing here says a name is illiquid" in lines[2]


def test_a_live_feed_groups_by_reason():
    qs = [Q.Quote("AAA", Q.ZERO_OI), Q.Quote("BBB", Q.ZERO_OI),
          Q.Quote("CCC", Q.NO_PUTS), Q.Quote("DDD", Q.OK)]
    lines = Q.summarise(qs, True, "live")
    joined = " ".join(lines)
    assert "AAA, BBB" in joined and "CCC" in joined
    assert "DDD" not in joined            # priced names are not failures


def test_summarise_on_an_empty_board_says_nothing():
    assert Q.summarise([], True, "live") == []


def test_quote_reports_ok_and_its_own_reason():
    q = Q.Quote("IONS", Q.OK, spot=61.33, put_pct=0.05)
    assert q.ok and q.spot == 61.33
    bad = Q.Quote("INO", Q.PARITY_BREAK, detail="gap 0.044")
    assert not bad.ok and bad.about_the_name
    assert "parity" in bad.why() and "0.044" in bad.why()
