#!/usr/bin/env python3
"""
quotes.py — one option-quote path, with typed failures and a feed control.

THE DEFECT THIS FIXES, and it had been mislabelling the board for weeks. The
screen wrapped its whole option fetch in one `except Exception` that recorded
the exception CLASS and nothing else, and its silent paths — no expiry matched,
no spot, no puts — recorded nothing at all. Every one of those arrived in the
report as the same sentence:

    ⚠ 6 calendar name(s) unpriced — quotes failed their checks

which reads as *these names are illiquid*. Run at 06:47 ET on 2026-09-03, the
checks failed for **every name on the board**. They also failed for SPY:

    SPY   ATM put   bid=0.0  ask=0.0  openInterest=0   volume=7488
    AAPL  ATM put   bid=0.0  ask=0.0  openInterest=0   volume=2139

SPY options are the most liquid contracts in existence. A zero two-sided quote
on SPY is not a fact about SPY, it is a fact about the FEED: Yahoo's free chain
zeroes bid/ask and openInterest outside market hours. The report was telling
the portfolio manager that half the calendar was unpriceable when what had
actually happened was that the market was shut.

THE IDEA THAT FIXES IT is the one this repo already applies to statistics:
**a positive control.** Before drawing any conclusion about a name, price a
contract whose liquidity is not in question. If the control has no two-sided
quote, the feed is not live and NO per-name conclusion may be drawn — the right
output is one line saying the options feed is closed, not fourteen lines
implying fourteen illiquid companies.

WHAT IS DELIBERATELY NOT HERE. No fallback pricing, no synthetic bid/ask, no
carrying a stale quote forward. When the feed is shut the answer is that it is
shut (rule 2). A number invented to keep the page full is worse than a blank.
"""

from __future__ import annotations

import datetime as dt
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# ── typed failures ──────────────────────────────────────────────────────────
# A reason the report can act on, not an exception class. Ordered roughly by
# how early the pipeline gives up.
OK = "OK"
NO_TICKER = "NO_TICKER"                  # nothing to look up at all
CHAIN_ERROR = "CHAIN_ERROR"              # the fetch itself raised
NO_SPOT = "NO_SPOT"                      # quote came back without a price
NO_EXPIRIES = "NO_EXPIRIES"              # chain offers no expiry dates
NO_EXPIRY_AFTER_EVENT = "NO_EXPIRY_AFTER_EVENT"   # none covers the decision
NO_PUTS = "NO_PUTS"                      # expiry has no put contracts
NO_TWO_SIDED = "NO_TWO_SIDED"            # no bid/ask; only a last trade
ZERO_OI = "ZERO_OI"                      # no open interest on the ATM strike
PARITY_BREAK = "PARITY_BREAK"            # put-call parity violated past tol
FEED_CLOSED = "FEED_CLOSED"              # the CONTROL has no two-sided quote

# Failures that say something about the NAME, versus about the FEED. Only the
# first kind may be reported as a property of the company.
ABOUT_THE_NAME = {NO_TICKER, NO_EXPIRY_AFTER_EVENT, NO_PUTS, PARITY_BREAK}
ABOUT_THE_FEED = {FEED_CLOSED, CHAIN_ERROR, NO_SPOT, NO_EXPIRIES}
# NO_TWO_SIDED and ZERO_OI are ambiguous in isolation — they are a property of
# the name during market hours and of the feed outside them, which is precisely
# why the control exists to disambiguate them.

EXPLAIN = {
    OK: "priced",
    NO_TICKER: "no ticker resolved — cannot be looked up at all",
    CHAIN_ERROR: "the options fetch failed",
    NO_SPOT: "quote returned no price",
    NO_EXPIRIES: "chain offers no expiry dates",
    NO_EXPIRY_AFTER_EVENT: "no listed expiry covers the decision date",
    NO_PUTS: "no put contracts at the chosen expiry",
    NO_TWO_SIDED: "no bid/ask — only a last trade, which may be stale",
    ZERO_OI: "no open interest on the at-the-money strike",
    PARITY_BREAK: "put-call parity violated — the quote is not trustworthy",
    FEED_CLOSED: "the options feed is not live (market closed or delayed)",
}

# The control contract. Liquidity is not in question, so a failure here is a
# statement about the feed and never about the name.
CONTROL_TICKER = "SPY"


class Quote:
    """One option quote, or one typed reason there is not one."""

    __slots__ = ("ticker", "reason", "spot", "expiry", "put_pct", "call_pct",
                 "parity", "oi", "px_source", "detail")

    def __init__(self, ticker, reason=OK, **kw):
        self.ticker, self.reason, self.detail = ticker, reason, kw.pop("detail", "")
        for k in ("spot", "expiry", "put_pct", "call_pct", "parity", "oi",
                  "px_source"):
            setattr(self, k, kw.get(k))

    @property
    def ok(self) -> bool:
        return self.reason == OK

    @property
    def about_the_name(self) -> bool:
        """Is this a statement about the company, or about the plumbing?

        Reporting a feed outage as a property of a company is the exact
        mislabelling this module exists to stop.
        """
        return self.reason in ABOUT_THE_NAME

    def why(self) -> str:
        base = EXPLAIN.get(self.reason, self.reason)
        return f"{base} ({self.detail})" if self.detail else base

    def __repr__(self):
        return f"<Quote {self.ticker} {self.reason}>"


def feed_is_live(chain_fn, control: str = CONTROL_TICKER) -> tuple:
    """(live, why). Price the control before trusting any per-name verdict.

    A two-sided quote on SPY's at-the-money put is present whenever the options
    market is open. Its absence means bid/ask are not being served at all, and
    every `NO_TWO_SIDED` / `ZERO_OI` on the board that run is an artefact of
    that rather than a fact about a company.
    """
    try:
        r = chain_fn(control)
    except Exception as e:
        return False, f"control {control} chain failed ({type(e).__name__})"
    spot = float((r.get("quote") or {}).get("regularMarketPrice") or 0) or None
    exps = r.get("expirationDates") or []
    if not spot or not exps:
        return False, f"control {control} returned no spot or no expiries"
    try:
        rr = chain_fn(control, exps[min(2, len(exps) - 1)])
        puts = ((rr.get("options") or [{}])[0]).get("puts") or []
    except Exception as e:
        return False, f"control {control} expiry chain failed ({type(e).__name__})"
    if not puts:
        return False, f"control {control} has no puts"
    near = min(puts, key=lambda p: abs((p.get("strike") or 0) - spot))
    bid, ask = near.get("bid") or 0, near.get("ask") or 0
    if bid > 0 and ask > 0:
        return True, f"control {control} quotes {bid:.2f}/{ask:.2f}"
    return False, (f"control {control} ATM put has no two-sided quote "
                   f"(bid={bid}, ask={ask}) — the feed is not serving bid/ask, "
                   "so no per-name liquidity conclusion is available")


def classify(spot, expiries, expiry, puts, atm_put, parity, tol,
             feed_live: bool = True) -> str:
    """The first reason this quote is unusable, or OK.

    Ordered so the earliest and most specific cause wins: a name with no expiry
    covering its decision date is not also 'no two-sided quote'.
    """
    if not spot:
        return NO_SPOT
    if not expiries:
        return NO_EXPIRIES
    if not expiry:
        return NO_EXPIRY_AFTER_EVENT
    if not puts:
        return NO_PUTS
    if not atm_put:
        return NO_PUTS
    bid, ask = atm_put.get("bid") or 0, atm_put.get("ask") or 0
    if not (bid > 0 and ask > 0):
        # The control decides whether this is the name or the plumbing.
        return NO_TWO_SIDED if feed_live else FEED_CLOSED
    if parity is not None and parity > tol:
        return PARITY_BREAK
    if not (atm_put.get("openInterest") or 0):
        return ZERO_OI if feed_live else FEED_CLOSED
    return OK


def summarise(quotes: list, feed_live: bool, feed_why: str) -> list:
    """Report lines. One line for a feed outage, never one per name.

    Fourteen names each said to have 'failed their checks' invites fourteen
    wrong conclusions about fourteen companies when one sentence about the
    feed is the whole truth.
    """
    if not quotes:
        return []
    if not feed_live:
        n = sum(1 for q in quotes if not q.ok)
        return [f"OPTIONS FEED NOT LIVE — {n} name(s) unpriced for this reason "
                f"alone, not for anything about the companies.",
                f"  {feed_why}.",
                "  Re-run during market hours; nothing here says a name is "
                "illiquid."]
    out = []
    by = {}
    for q in quotes:
        if not q.ok:
            by.setdefault(q.reason, []).append(q.ticker)
    for reason, names in sorted(by.items()):
        out.append(f"{len(names)} unpriced — {EXPLAIN.get(reason, reason)}: "
                   + ", ".join(sorted(names)[:6])
                   + (f" +{len(names)-6} more" if len(names) > 6 else ""))
    return out


def main(argv=None) -> int:
    """Diagnose the feed and the current board, for a human."""
    import screen as S
    y = S.Yahoo()
    live, why = feed_is_live(y.chain)
    print(f"options feed live: {live}")
    print(f"  {why}")
    if not live:
        print("\nNo per-name liquidity conclusion is available in this state.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
