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
    if two_sided(near):
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
    if number(spot, positive=True) is None:
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
    if not two_sided(atm_put):
        # The control decides whether this is the name or the plumbing.
        return NO_TWO_SIDED if feed_live else FEED_CLOSED
    if parity is not None and (number(parity) is None or parity > tol):
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



# Shared transport and validation for the daily report and legacy diagnostics.
# A last-trade timestamp does NOT certify the timestamp of a bid/ask quote.
import math
import json
import logging
import http.cookiejar
import urllib.error
import urllib.parse
import urllib.request
from zoneinfo import ZoneInfo

log = logging.getLogger(__name__)


def number(value, *, positive=False):
    """Finite numeric value, excluding booleans; None means invalid/missing."""
    if isinstance(value, bool):
        return None
    try:
        x = float(value)
    except (TypeError, ValueError):
        return None
    return x if math.isfinite(x) and (x > 0 if positive else True) else None


def two_sided(row):
    """Strict positive, finite, uncrossed BBO. Last trades are never a fallback."""
    bid, ask = number(row.get("bid"), positive=True), number(row.get("ask"), positive=True)
    if bid is None or ask is None or ask < bid:
        return None
    return bid, ask


def stamp(value):
    """Parse a timezone-aware timestamp or epoch; reject naive datetimes."""
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if not math.isfinite(value):
            raise ValueError("nonfinite timestamp")
        value = dt.datetime.fromtimestamp(value, dt.timezone.utc)
    elif isinstance(value, str):
        value = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    if not isinstance(value, dt.datetime) or value.tzinfo is None:
        raise ValueError("missing or naive timestamp")
    return value.astimezone(dt.timezone.utc)


def fresh(value, now, max_age=120):
    try:
        age = (stamp(now) - stamp(value)).total_seconds()
        return 0 <= age <= max_age
    except (ValueError, TypeError, OverflowError, OSError):
        return False


class YahooMarketData:
    """One authenticated transport, bounded timeouts, per-run response cache.

    Yahoo may supply historical last-trade times without BBO timestamps. Such
    data can mark a fresh trade, but cannot pass validate_equity's BBO gate.
    HTTP failures are raised to the caller; the expected cookie-seeding HTTP
    status is logged. Credentials/cookies/crumbs never appear in log messages.
    """
    def __init__(self, timeout=8):
        self.op = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
        self.crumb = None
        self.timeout = timeout
        self.cache = {}

    def _get(self, url, accept="application/json"):
        """One transport. `accept` MUST match what the endpoint actually serves.

        DAY-94, and it cost a full trading session. Every request sent
        `Accept: application/json`, including the crumb fetch -- but
        /v1/test/getcrumb returns a BARE TOKEN as text/plain, so Yahoo
        correctly refuses it with 406 Not Acceptable. That is HTTP working as
        specified, not an outage and not a block.

        The cascade on 2026-09-09 read as three unrelated faults and was one:

            fc.yahoo.com            404  (logged as expected, and harmless --
                                          it still sets a usable cookie)
            /v1/test/getcrumb       406  <- the real failure, this header
            /v7/finance/quote       401  (no crumb, so unauthorised)

        The reported symptom named the quote endpoint; the cause was two steps
        earlier. Every leg ABSTAINed for want of a spread, the page still
        rendered an order-shaped table, and the day was traded on it.
        """
        request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0",
                                                      "Accept": accept})
        return self.op.open(request, timeout=self.timeout).read()

    def auth(self):
        if self.crumb:
            return
        try:
            self._get("https://fc.yahoo.com")
        except urllib.error.HTTPError as exc:
            log.warning("Yahoo cookie bootstrap HTTP %s; trying crumb endpoint", exc.code)
        # text/plain, NOT json — see _get. Asking for json here returns 406.
        crumb = self._get("https://query2.finance.yahoo.com/v1/test/getcrumb",
                          accept="*/*").decode().strip()
        if not crumb or "<" in crumb or len(crumb) > 256:
            raise ValueError("invalid Yahoo authentication response")
        self.crumb = crumb

    def _json(self, path, params):
        self.auth()
        key = (path, tuple(sorted(params.items())))
        if key not in self.cache:
            url = "https://query2.finance.yahoo.com" + path + "?" + urllib.parse.urlencode(
                {**params, "crumb": self.crumb})
            self.cache[key] = json.loads(self._get(url))
        return self.cache[key]

    def get(self, tickers):
        if not tickers:
            return {}
        result = self._json("/v7/finance/quote", {"symbols": ",".join(sorted(set(tickers)))})
        envelope = result.get("quoteResponse") or {}
        if envelope.get("error"):
            raise ValueError("Yahoo quote response reported an error")
        return {r["symbol"]: r for r in envelope.get("result", [])}

    def chain(self, ticker, expiry=None):
        params = {} if expiry is None else {"date": int(expiry)}
        result = self._json("/v7/finance/options/" + urllib.parse.quote(ticker, safe=""), params)
        envelope = result.get("optionChain") or {}
        if envelope.get("error") or not envelope.get("result"):
            raise ValueError("Yahoo returned no option chain")
        return envelope["result"][0]



class SnapshotMarketData:
    """External authenticated BBO publisher's JSON snapshot; validated downstream.

    Schema: {quotes: {symbol: raw_equity}, chains: {symbol: {initial: {...},
    expiries: {epoch: {...}}}}}. No interpolation, field renaming or freshness
    assumptions. This allows a licensed feed to replace Yahoo without changes
    to selection, costs, renderers or monitoring rules.
    """
    def __init__(self,path):
        from pathlib import Path
        self.data=json.loads(Path(path).read_text())
    def get(self,tickers):
        return {t:self.data.get('quotes',{}).get(t,{}) for t in tickers}
    def chain(self,ticker,expiry=None):
        entry=self.data['chains'][ticker]
        return entry['initial'] if expiry is None else entry['expiries'][str(expiry)]


def market_client():
    path=os.environ.get('RB_QUOTES_JSON')
    return SnapshotMarketData(path) if path else YahooMarketData()


def reference_close(row, ticker, now):
    """Dated prior-session context only; never passed into execution or live marks."""
    out = {'status':'UNAVAILABLE'}
    if not row: return out
    try:
        import pandas_market_calendars as mcal
        from urllib.parse import urlparse
        from zoneinfo import ZoneInfo
        today=stamp(now).astimezone(ZoneInfo('America/New_York')).date()
        calendar=mcal.get_calendar('TSX' if ticker.endswith('.TO') else 'NYSE')
        days=calendar.valid_days(start_date=today-dt.timedelta(days=12),end_date=today-dt.timedelta(days=1))
        expected=days[-1].date().isoformat()
        price=number(row.get('close'),positive=True)
        url=urlparse(str(row.get('source_url','')))
        if (row.get('ticker')!=ticker or row.get('currency')!=('CAD' if ticker.endswith('.TO') else 'USD')
            or row.get('session')!=expected or price is None
            or not fresh(row.get('retrieved_at'),now,36*3600)
            or url.scheme!='https' or not url.hostname or url.username or url.password):
            raise ValueError('reference identity/currency/session/source/freshness mismatch')
        return {**row,'close':price,'status':'OK','label':'PRIOR SESSION CLOSE — not a live mark or fill'}
    except (ValueError,KeyError,TypeError,IndexError) as exc:
        return {**out,'reason':str(exc)}

def validate_equity(row, ticker, now, *, currency=None, max_age=120):
    """Validate last trade and BBO independently; a fresh trade is not a fresh BBO."""
    out = {"ticker": ticker, "mark": None, "bid": None, "ask": None,
           "spread_bps": None, "quote_time": None, "status": "UNAVAILABLE",
           "reason": "missing quote", "currency": row.get("currency")}
    if row.get("symbol") != ticker:
        out["reason"] = "symbol mismatch or missing"
        return out
    if currency and row.get("currency") != currency:
        out["reason"] = "currency mismatch or missing"
        return out
    px = number(row.get("regularMarketPrice"), positive=True)
    if px is not None and fresh(row.get("regularMarketTime"), now, max_age):
        out["mark"] = px
    bbo = two_sided(row)
    if bbo is None:
        out["reason"] = "missing, nonfinite, nonpositive or crossed BBO"
        return out
    ts = row.get("bidAskTimestamp", row.get("quoteTime"))
    if not fresh(ts, now, max_age):
        out["reason"] = "BBO timestamp missing, stale or future; last trade is not quote time"
        return out
    out.update(status="OK", reason="validated BBO", bid=bbo[0], ask=bbo[1],
               mark=(bbo[0]+bbo[1])/2, quote_time=stamp(ts).isoformat(),
               spread_bps=(bbo[1]-bbo[0])/((bbo[0]+bbo[1])/2)*10000)
    return out


def matched_pair(calls, puts, spot):
    """Nearest common strike, deterministic; never combine different contracts."""
    if number(spot, positive=True) is None:
        return None, None
    c = {number(r.get("strike"), positive=True): r for r in calls}
    p = {number(r.get("strike"), positive=True): r for r in puts}
    if len(c) != len(calls) or len(p) != len(puts):
        return None, None  # Ambiguous duplicate contracts cannot overwrite evidence.
    strikes = (c.keys() & p.keys()) - {None}
    if not strikes:
        return None, None
    k = min(strikes, key=lambda k: (abs(k-spot), k))
    return c[k], p[k]


def option_mid(row):
    bbo = two_sided(row)
    return ((bbo[0]+bbo[1])/2, "mid") if bbo else (None, "none")


def option_metrics(calls, puts, spot):
    """Pure diagnostic arithmetic on a matched BBO pair; not a freshness claim."""
    c, p = matched_pair(calls, puts, spot)
    empty = {"move": None, "call_pct": None, "put_pct": None, "skew": None,
             "iv": None, "parity": None, "strike": None}
    if not c or not p:
        return empty
    cm, pm = option_mid(c)[0], option_mid(p)[0]
    if cm is None or pm is None:
        return empty
    ci, pi = number(c.get("impliedVolatility"), positive=True), number(p.get("impliedVolatility"), positive=True)
    return {"move": (cm+pm)/spot, "call_pct": cm/spot, "put_pct": pm/spot,
            "strike": float(c["strike"]), "parity": abs(cm-pm-(spot-float(c["strike"])))/spot,
            "skew": pi-ci if ci is not None and pi is not None else None,
            "iv": (ci+pi)/2 if ci is not None and pi is not None else None}


def event_quote(client, ticker, event_end, now, *, max_age=120):
    """One fail-closed event option snapshot. Missing fields never become prices."""
    out = {"ticker": ticker, "status": "UNAVAILABLE", "reason": None,
           "move": None, "iv": None, "put_pct": None, "call_pct": None,
           "skew": None, "parity": None, "spot": None, "expiry": None}
    try:
        initial = client.chain(ticker)
        q = initial.get("quote") or {}
        if q.get("symbol") != ticker or q.get("currency") != "USD":
            raise ValueError("underlying symbol/currency mismatch or missing")
        if not fresh(q.get("regularMarketTime"), now, max_age):
            raise ValueError("underlying timestamp missing, stale or future")
        spot = number(q.get("regularMarketPrice"), positive=True)
        if spot is None:
            raise ValueError("invalid underlying price")
        expiries = [e for e in initial.get("expirationDates", [])
                    if stamp(e).date() > event_end]
        if not expiries:
            raise ValueError("no expiry covers the entire event window")
        expiry = min(expiries)
        chain = client.chain(ticker, expiry)
        if chain.get('quote') and chain['quote'].get('symbol') != ticker:
            raise ValueError('expiry chain underlying symbol mismatch')
        options = chain.get("options") or []
        if len(options) != 1 or options[0].get("expirationDate") != expiry:
            raise ValueError("expiry response mismatch")
        c, p = matched_pair(options[0].get("calls", []), options[0].get("puts", []), spot)
        if not c or not p:
            raise ValueError("no matched call/put strike")
        for leg in (c, p):
            if leg.get("expiration") != expiry or leg.get("currency") != "USD":
                raise ValueError("contract expiry/currency mismatch")
            if not two_sided(leg):
                raise ValueError("invalid contract BBO")
            if not fresh(leg.get("bidAskTimestamp", leg.get("quoteTime")), now, max_age):
                raise ValueError("contract BBO timestamp missing, stale or future")
            if number(leg.get("openInterest"), positive=True) is None:
                raise ValueError("contract has no verified open interest")
        metrics = option_metrics([c], [p], spot)
        # Consistency screen, not exact European parity for American contracts.
        if metrics["parity"] is None or metrics["parity"] > 0.03:
            raise ValueError("call/put/underlying consistency gap exceeds 3%")
        if metrics["iv"] is None:
            raise ValueError("missing or nonfinite implied volatility")
        out.update(metrics, status="OK", reason="validated matched contracts",
                   spot=spot, expiry=stamp(expiry).date().isoformat(),
                   put_oi=p['openInterest'], call_oi=c['openInterest'],
                   as_of=min(stamp(q['regularMarketTime']),
                             *(stamp(l.get('bidAskTimestamp',l.get('quoteTime'))) for l in (c,p))).isoformat())
    except Exception as exc:
        # Report the class and controlled validation text, never URLs with crumbs.
        out["reason"] = str(exc) if isinstance(exc, ValueError) else type(exc).__name__
        log.warning("Option snapshot %s unavailable: %s", ticker, out["reason"])
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
