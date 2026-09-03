#!/usr/bin/env python3
"""
screen.py — catalyst OPPORTUNITIES, not just a calendar of dates.

WHAT WAS MISSING. `pdufa.py` answers "what is scheduled". A portfolio manager
needs the next question answered: of everything scheduled, which ones are worth
work, and what is the market already paying? A date with no price context is a
diary entry, not an opportunity.

THE INPUT THAT MAKES THIS POSSIBLE, and it is free. An FDA decision is a dated
binary, so the options market prices it explicitly. The at-the-money straddle
expiring just after the event is the market's own estimate of how far the stock
moves — no analyst target required, and no probability of my own invented. Two
readings come out of it:

  IMPLIED MOVE   ATM call + ATM put, over spot. "The market expects roughly
                 +/-N% out of this decision." A name with a PDUFA in eight days
                 and a 12% implied move is priced for a different event than one
                 with a 60% implied move.

  SKEW           ATM put IV minus ATM call IV. Positive means downside
                 protection costs more than upside — the market is paying up to
                 be insured against a CRL. Negative means the reverse. It is a
                 read on FEAR, not on the FDA.

WHAT IT NOW DOES WITH THAT, and did not before day-70. Printing implied move,
skew, cash and runway in four separate lines is a data dump, not analysis; it
pushes the hardest step onto the reader. Every name now carries a VERDICT that
combines them against the day-68 measurement, and the hinge is one number:

  BREAKEVEN P(CRL)   put cost / |measured median rejection|. A put at 9% of
                     spot against the measured -15.2% median needs a rejection
                     to be ~59% likely just to break even. Most catalyst
                     "lottery tickets" do not survive being asked that.

AND SINCE DAY-71 THE BREAKEVEN IS COMPARED, not just stated. This module used
to say a base rate "would be fabricated" because 8-Ks give the numerator and
not the denominator. `baserate.py` disproved that by drawing BOTH legs from one
harvest: for sponsors whose decision is material enough to announce either way,
P(rejection) is 21% [16%, 27%] over 202 decisions. So a 89% breakeven now reads
as "this name would have to be 3.3-5.6x worse than average" — a claim about the
DRUG, which is the claim a reader should be made to state out loud.

WHAT IT STILL REFUSES TO DO is attach a probability to THIS name. The base rate
is unconditional and is labelled so everywhere it appears; nothing here knows
anything about the molecule.

HOW TO READ THE STANCE LINE. It describes the SETUP and nothing else, and it
reads the implied move as MATERIALITY rather than as value — a +/-4% print is
the market saying the decision does not move the enterprise, not that the
options are cheap. That distinction was learned the hard way (see `stance`).
The VERDICT line below it is where the judgement lives.
"""

from __future__ import annotations

import argparse
import datetime as dt
import http.cookiejar
import json
import os
import sys
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import sanity as _sn  # noqa: E402  — module scope on purpose: an `except
#   _sn.Impossible` whose import sat inside the try would raise NameError from
#   the handler and hide the real failure. That is the day-29 pattern exactly.
from validate_exit import SCRATCH  # noqa: E402

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120 Safari/537.36")
H = {"User-Agent": UA, "Accept": "application/json,text/plain,*/*"}
# THRESHOLDS ANCHORED TO A MEASUREMENT, not to round numbers. These were 0.20
# and 0.45 — defensible-sounding figures with nothing behind them, and one of
# them produced a false sentence in the live report: IONS at +/-16% was told it
# was "smaller than the 15.2% median rejection", which it is not. A threshold
# that cannot be stated truthfully in the line it triggers is the wrong
# threshold.
#
# Both are now multiples of the MEASURED median rejection (catalyst.CRL_MEDIAN,
# -15.2%, day-68), which is the only size in this domain this repo has actually
# established:
#
#   IMMATERIAL  half the median rejection. Below this the market cannot be
#               pricing a company-level binary at all — whatever the FDA says,
#               the enterprise barely moves. RPRX at +/-3% is the case.
#   RICH        three times the median rejection. Above this the tape is
#               already paying near the measured TAIL (p10 -60.4%), not the
#               median, so both sides are dear.
#
# DAY-72: the median moved from -15.20% to -8.97% when the bar-interval bug was
# found (see catalyst.py), so both thresholds moved with it. They are anchored
# to a measurement precisely so that correcting the measurement corrects them,
# rather than leaving two stale round numbers behind.
_CRL = 11.79                      # day-77 median, n=71, explicit-range daily bars
IMMATERIAL_MOVE = _CRL / 2 / 100          # 0.076
RICH_MOVE = _CRL * 3 / 100                # 0.456
CHEAP_MOVE = IMMATERIAL_MOVE              # name kept: callers outside this file


class Yahoo:
    """Options access needs a cookie + crumb since 2023; plain GETs return 401."""

    def __init__(self):
        self.cj = http.cookiejar.CookieJar()
        self.op = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(self.cj))
        self.crumb = None

    def _get(self, url: str) -> bytes:
        return self.op.open(urllib.request.Request(url, headers=H),
                            timeout=40).read()

    def auth(self) -> None:
        if self.crumb:
            return
        try:
            self._get("https://fc.yahoo.com")
        except Exception:
            pass                      # seeds the cookie even on an error status
        self.crumb = self._get(
            "https://query2.finance.yahoo.com/v1/test/getcrumb").decode()

    def chain(self, ticker: str, expiry: int | None = None) -> dict:
        self.auth()
        u = (f"https://query2.finance.yahoo.com/v7/finance/options/{ticker}"
             f"?crumb={self.crumb}")
        if expiry:
            u += f"&date={expiry}"
        return json.loads(self._get(u))["optionChain"]["result"][0]


def pick_expiry(expiries: list, after: dt.date) -> int | None:
    """The first expiry that still covers the event. An expiry BEFORE the
    decision prices a different question entirely."""
    for e in sorted(expiries):
        if dt.datetime.utcfromtimestamp(e).date() >= after:
            return e
    return None


def _atm(rows: list, spot: float) -> dict | None:
    rows = [r for r in rows if r.get("strike") and r.get("lastPrice") is not None]
    return min(rows, key=lambda r: abs(r["strike"] - spot)) if rows else None


def option_price(row: dict) -> tuple:
    """(price, source). MID when a two-sided quote exists, LAST otherwise.

    THE TRAP THIS AVOIDS, and it corrupts the one number the verdict turns on.
    `lastPrice` is whenever that contract last traded — on an illiquid biotech
    strike that can be days ago at a materially different spot. Run live, JAZZ
    priced an ATM put at 3.7% of spot against a 10% implied move: the two legs
    of one straddle disagreeing by more than the event they price. A breakeven
    computed from that is not conservative or aggressive, it is fiction.

    The mid of a live bid/ask is a real, current price. `lastPrice` is a
    historical fact that may not be a price at all, so when it is all there is,
    the source travels with it and the caller says so out loud."""
    b, a = row.get("bid"), row.get("ask")
    if b is not None and a is not None and float(a) > 0 and float(a) >= float(b):
        return (float(b) + float(a)) / 2, "mid"
    lp = row.get("lastPrice")
    return (float(lp), "last") if lp is not None else (None, "none")


def parity_gap(call: dict, put: dict, spot: float) -> float | None:
    """|C - P - (S - K)| over spot. Near zero when both legs are live.

    Put-call parity is an ARBITRAGE identity, not a model — it holds whatever
    anyone thinks the FDA will do, so a large violation is a statement about
    the DATA, not about the stock. It is the cheapest available test of whether
    both quotes are real, and it costs one subtraction."""
    if not call or not put or not spot:
        return None
    c, _ = option_price(call)
    p, _ = option_price(put)
    if c is None or p is None:
        return None
    k = float(call.get("strike") or 0)
    if k <= 0 or float(put.get("strike") or 0) != k:
        return None            # different strikes: parity does not apply
    return abs((c - p) - (spot - k)) / spot


# Above this, one of the two legs is not a current price. Interest-rate carry
# over a two-month expiry is well under 1% of spot, so 3% cannot be explained
# by anything but a stale quote.
PARITY_TOL = 0.03


def implied_move(calls: list, puts: list, spot: float) -> float | None:
    """ATM straddle over spot — the market's expected magnitude, either way."""
    c, p = _atm(calls, spot), _atm(puts, spot)
    if not c or not p or not spot:
        return None
    cp, _ = option_price(c)
    pp, _ = option_price(p)
    if cp is None or pp is None:
        return None
    return (cp + pp) / spot


def leg_costs(calls: list, puts: list, spot: float) -> tuple:
    """ATM call and ATM put, each as a fraction of spot.

    The straddle is one number for a two-sided question. Day-68 measured the
    two sides separately and found them nothing alike, so the cost of each side
    has to be separable too — the put is priced against a MEASURED -15.2%
    median rejection, the call against an approval leg that failed its placebo
    gate. Averaging them into one 'implied move' hides exactly the asymmetry
    that makes the decision."""
    c, p = _atm(calls, spot), _atm(puts, spot)
    if not c or not p or not spot:
        return None, None
    cp, _ = option_price(c)
    pp, _ = option_price(p)
    if cp is None or pp is None:
        return None, None
    return cp / spot, pp / spot


def skew(calls: list, puts: list, spot: float) -> float | None:
    """ATM put IV minus ATM call IV. Positive = downside costs more."""
    c, p = _atm(calls, spot), _atm(puts, spot)
    if not c or not p:
        return None
    ci, pi = c.get("impliedVolatility"), p.get("impliedVolatility")
    if ci is None or pi is None:
        return None
    return float(pi) - float(ci)


def stance(move: float | None, sk: float | None, days: int,
           signals: list) -> tuple:
    """A description of the SETUP and the single reason for it. Never advice.

    THE LABEL THIS GOT WRONG FIRST, and it mattered. A low implied move was
    called a "cheap binary — the options may be underpricing it". Run live, that
    tagged Royalty Pharma at +/-4% and Jazz at +/-10%, and both readings were
    nonsense: RPRX is a diversified royalty portfolio where a single approval
    barely touches the enterprise. The market was not underpricing the event, it
    was telling me the event is IMMATERIAL to the company.

    So the implied move is read as MATERIALITY first, not as value. A single-
    asset developer whose decision is existential prices +/-40%; a large-cap
    with fifty products prices +/-4%. Neither is cheap or dear on that basis
    alone, and a screen that says "cheap" invites exactly the wrong trade.
    """
    if move is None:
        return "no options", "no listed chain covering the event — cash equity only"
    if move < IMMATERIAL_MOVE:
        s = ("not material",
             f"only +/-{move:.0%} implied, under half the measured median "
             "rejection — the market treats this decision as immaterial to the "
             "enterprise, not as a mispriced binary. A diversified or large-cap "
             "sponsor; the event is not the story")
    elif move > RICH_MOVE:
        s = ("existential",
             f"+/-{move:.0%} implied — the market prices this as a company-"
             "defining decision. Edge must come from the DRUG; the setup itself "
             "is dearly priced either way")
    else:
        s = ("material binary",
             f"+/-{move:.0%} implied — a real, priced binary of the size a PDUFA "
             "usually is")
    if sk is not None and sk > 0.15:
        s = (s[0], s[1] + "; puts bid over calls — the tape is paying for CRL "
                          "insurance")
    if "review EXTENDED" in signals:
        s = (s[0], s[1] + "; review was EXTENDED, which historically follows a "
                          "major amendment")
    if "prior CRL" in signals:
        s = (s[0], s[1] + "; this is a RESUBMISSION after a prior CRL")
    return s


def breakeven_pair(put_pct: float | None) -> tuple:
    """(against the MEAN, against the MEDIAN). Both, because they differ a lot.

    AN OPTION PAYS AN EXPECTATION, so the breakeven that decides whether a
    premium is worth paying belongs against the MEAN drawdown (-18.5%). The
    median (-9.0%) answers a different and also necessary question: what should
    a holder picture happening.

    The gap between them IS the fat left tail — 19% of rejections finish worse
    than -40% — and quoting only one of the two hides exactly the feature of
    this distribution that matters most. Day-68 quoted only the median, which
    made every put look roughly twice as dear as its expectation justifies.
    """
    import catalyst as _cat
    return (put_breakeven(put_pct, _cat.CRL_MEAN),
            put_breakeven(put_pct, _cat.CRL_MEDIAN))


def put_breakeven(put_pct: float | None,
                  drop_pct: float = None) -> float | None:
    """The probability of a CRL you must believe for the put to break even.

    THIS IS THE ONE NUMBER THE SCREEN OWES A PORTFOLIO MANAGER. Everything
    upstream is description — implied move, skew, runway. This converts the
    market's price and the repo's MEASURED rejection distribution into the
    single question a position actually turns on: how likely does the bad
    outcome have to be before paying this premium makes sense?

        breakeven P(CRL) = put cost / |median CRL drawdown|

    at a put cost of 9% of spot and the measured -15.2% median, you need to
    believe a rejection is roughly 59% likely. Say that out loud and most
    catalyst 'lottery tickets' die on the spot.

    IT IS AN UPPER BOUND, and that direction matters. It uses the MEDIAN drop,
    but the left tail is much fatter (p10 -57.5%, worst -83.6%), so the true
    expected payoff is larger and the true breakeven lower. Erring toward
    'this is expensive' is the safe direction for a screen that must not talk
    anyone into a position.

    Returns None when the put cannot be priced, and a value above 1.0 when the
    premium exceeds the median drawdown outright — not an error to clamp, it
    means no probability makes the median case pay and the position is a bet on
    the tail alone."""
    import catalyst as _cat
    if put_pct is None:
        return None
    drop = abs(drop_pct if drop_pct is not None else _cat.CRL_MEAN) / 100.0
    return put_pct / drop if drop else None


def against_base_rate(be: float | None) -> list:
    """Turn the breakeven into a comparison, which is what it was missing.

    THE SENTENCE THAT HAD NO ENDING. "The put breaks even if a rejection is
    ~89% likely" is honest and useless on its own: a reader with no base rate
    cannot tell whether 89% is absurd or routine. The module said as much —
    P(CRL) was "deliberately NOT supplied" because 8-Ks give the numerator and
    not the denominator.

    `baserate.py` closes that (day-71) by drawing BOTH legs from the same
    harvest and the same classifier, and by auditing the approval leg against
    Drugs@FDA. So the breakeven can finally be divided by something:

        how much more likely than average would this rejection have to be?

    A multiple near 1 means the market is charging roughly the base rate. A
    multiple of 4 means the premium only pays if this name is four times worse
    than the average decision in the population — which is a claim about the
    drug, and is exactly the claim the reader should be made to state.

    IT STAYS A RANGE, and it stays unconditional. Nothing here knows anything
    about the molecule. Returns [] when the base rate has never been computed,
    because a caller must say "not computed" rather than reach for a plausible
    number.
    """
    if be is None:
        return []
    try:
        import baserate as _br
        s = _br.summary()
    except Exception:
        return []
    if not s:
        return ["no base rate has been computed, so the breakeven above cannot "
                "be compared with anything — run `python baserate.py`"]
    lo_mult, hi_mult = be / s["hi"], be / s["lo"]
    span = (f"{s['lo']:.0%}-{s['hi']:.0%}" if s["audited"]
            else f"~{s['hi']:.0%}")
    if lo_mult < 1.0 < hi_mult or abs(hi_mult - 1) < 0.15:
        tail = (f"which is about the base rate itself — the market is charging "
                f"roughly what this population delivers")
    elif hi_mult <= 1.0:
        tail = (f"BELOW the base rate: the premium is cheaper than an average "
                f"decision in this population would justify")
    else:
        tail = (f"so the premium only pays if this name is "
                f"{lo_mult:.1f}-{hi_mult:.1f}x more likely to be rejected than "
                f"the average decision — that is a claim about the DRUG, and "
                f"it is the claim to argue")
    return [f"against the measured base rate of {span} for "
            f"{s.get('population', 'announced decisions')} "
            f"(n={s['n']:,}, day-71), {tail}. That rate is UNCONDITIONAL — the "
            "prior you argue away from, not an answer for this name"]


def verdict(row: dict, vote: dict | None = None) -> dict:
    """One call per name, assembled from what is measured plus this name's facts.

    WHY A SYNTHESIS AT ALL. Until now the screen printed implied move, skew,
    cash per share and runway in separate lines and left the reader to combine
    them. That is not analysis, it is a data dump with good manners — and it
    quietly pushes the hardest step, the one where mistakes cost money, onto
    the person with the least context about how each number was derived.

    THE SPINE OF EVERY VERDICT is the day-68 asymmetry, which is measured here
    and not borrowed:

        a rejection is violent and unpriced   median -15.2%, -15.0pp vs random,
                                              t=-3.41 on 64 events
        an approval is already in the price   median -2.52% against a random
                                              +5.4pp over random, t=+2.42 —
                                              positive, and BELOW the bar

    Read together they say something specific and uncomfortable: on this
    evidence there is no probability of approval at which holding a long
    THROUGH the print has positive measured expectation, because the winning
    outcome pays nothing distinguishable from a random three-day window while
    the losing one takes 15%. A long into a PDUFA is not buying a lottery
    ticket, it is selling insurance — and the screen should say so in those
    words every time, not once in a footnote.

    WHAT IT REFUSES TO DO. It does not supply P(CRL). That number is not
    measurable from 8-K filings (see catalyst.py) and inventing one would
    convert an honest breakeven into a fake edge. The verdict states the
    probability you would have to hold; the conviction is the reader's."""
    import catalyst as _cat
    mv, spot = row.get("move"), row.get("spot")
    f = row.get("fund") or {}
    sig = row.get("signals") or []
    why = []
    be, be_med = breakeven_pair(row.get("put_pct"))
    row["put_be"], row["put_be_median"] = be, be_med

    if mv is None:
        call = "NO PRICED EXPRESSION"
        why.append("no listed chain covers the date, so the only way to hold a "
                   f"view is cash equity — which carries the full measured "
                   f"{_cat.CRL_MEDIAN:.1f}% median rejection with nothing "
                   "capping it")
    elif mv < IMMATERIAL_MOVE:
        call = "NOT AN EVENT TRADE"
        why.append(f"+/-{mv:.0%} implied is less than HALF the "
                   f"{abs(_cat.CRL_MEDIAN):.1f}% median rejection measured here "
                   "— at that size the market cannot be pricing a company-level "
                   "binary, so this is not a mispricing, it is a decision that "
                   "does not move the enterprise")
    else:
        # THE QUOTE IS CHECKED BEFORE IT IS TRUSTED. Everything below turns on
        # one put price, so a stale or one-sided quote does not produce a
        # slightly-off verdict, it produces a confident wrong one. Where the
        # input fails a check, the call says the input failed — it does not
        # quietly pick a rung on the ladder.
        bad = []
        if row.get("parity") is not None and row["parity"] > PARITY_TOL:
            bad.append(f"the two legs violate put-call parity by "
                       f"{row['parity']:.1%} of spot, which no interest rate "
                       "explains — one of these quotes is not a current price")
        if row.get("px_source") == "last":
            bad.append("the put has no two-sided quote; this is its LAST TRADE, "
                       "which on an illiquid strike can be days old at a "
                       "different spot")
        if row.get("put_oi") == 0:
            bad.append("the ATM put has zero open interest — nobody holds this "
                       "contract, so its price is an indication, not a market")
        if bad:
            call = "PRICING UNRELIABLE — VERIFY THE QUOTE"
            why += bad
            if be is not None:
                why.append(f"on the number as fetched the breakeven would be "
                           f"~{be:.0%}, stated only so you know what to check "
                           "it against — do not act on it")
        elif be is None:
            call = "STAND ASIDE INTO THE PRINT"
            why.append("the put covering the date could not be priced, so the "
                       "cost of the only expression with measured support is "
                       "unknown")
        elif be > 1.0:
            call = "PROTECTION IS DEAR — STAND ASIDE"
            why.append(
                f"the put covering the date costs {row['put_pct']:.1%} of spot, "
                f"MORE than the {abs(_cat.CRL_MEAN):.1f}% MEAN rejection "
                "delivers. No probability makes the average case pay; buying it "
                "is a bet on the tail alone (p10 "
                f"{_cat.CRL_P10:.1f}%, {_cat.CRL_WORSE_THAN_40:.0%} of CRLs "
                "finish worse than -40%)")
        elif be > 0.75:
            call = "PROTECTION IS DEAR — STAND ASIDE"
            why.append(
                f"the put costs {row['put_pct']:.1%} of spot; against the "
                f"measured mean rejection ({_cat.CRL_MEAN:.1f}%) it needs one "
                f"to be ~{be:.0%} likely just to break even, and ~{be_med:.0%} "
                "against the median")
        elif be > 0.35:
            call = "STAND ASIDE INTO THE PRINT"
            why.append(
                f"the put costs {row['put_pct']:.1%} of spot — a rejection has "
                f"to be ~{be:.0%} likely to break even against the measured "
                f"mean ({be_med:.0%} against the median). Fairly priced against "
                "what this repo can prove; the edge would have to come from the "
                "drug")
        else:
            call = "DOWNSIDE IS THE CHEAPER SIDE"
            why.append(
                f"the put costs only {row['put_pct']:.1%} of spot — it breaks "
                f"even if a rejection is ~{be:.0%} likely against the measured "
                f"MEAN rejection ({_cat.CRL_MEAN:.1f}%), or ~{be_med:.0%} "
                f"against the median ({_cat.CRL_MEDIAN:.1f}%). The mean is the "
                "one an option pays against; the gap between them is the tail")
        why.append(
            f"the long side is POSITIVE but BELOW THE BAR: approval windows "
            f"beat random ones by {_cat.APPROVAL_VS_RANDOM_PP:+.1f}pp "
            f"(t=+{_cat.APPROVAL_T:.2f}, n={_cat.APPROVAL_N}), which does not "
            f"clear the pre-registered |t| >= {_cat.ADOPT_T:.0f}. Not nothing, "
            "and not enough to act on — the rejection leg separates at "
            f"t={_cat.CRL_T:.2f} by comparison")
        why += against_base_rate(be)

    # Financing is a SECOND binary, and it is not the FDA's. A name that has to
    # raise inside the year dilutes on good news too.
    q = f.get("runway_q")
    if q is not None and q < 4:
        why.append(f"runway {q:.1f} quarters — this name faces a financing "
                   "event independent of the decision; approval does not stop "
                   "the raise, it prices it")
    cps, sp = f.get("cash_per_share"), spot
    if cps and sp and sp / cps > 5:
        why.append(f"${sp - cps:.2f} of the ${sp:.2f} price is pipeline, not "
                   f"cash ({sp/cps:.0f}x cash) — there is no balance-sheet "
                   "floor under a downside case here")
    if "prior CRL" in sig:
        why.append("resubmission after a prior CRL — the same review has "
                   "already said no once")
    if "review EXTENDED" in sig:
        why.append("the review was EXTENDED, which follows a major amendment")

    if vote and vote.get("direction") == "favourable":
        why.append("an advisory committee voted FAVOURABLY; EXTERNALLY 97% of "
                   "those are approved (JAMA 2023) — that pushes the required "
                   "P(CRL) further out of reach, so protection here is dearer "
                   "than it looks")
    elif vote and vote.get("direction") == "unfavourable":
        why.append("an advisory committee voted AGAINST; EXTERNALLY only 67% "
                   "of those are rejected and approval then takes a median "
                   "700 days (JAMA 2023) — the risk being held is TIME, not a "
                   "verdict")
    return {"call": call, "why": why, "breakeven": be}


def position_verdict(leg: dict, row: dict | None, today: dt.date) -> list:
    """The decision on a position ALREADY OPEN, which is a different question.

    WHY IT NEEDED ITS OWN FUNCTION. `verdict()` answers "should this become a
    position", and for an open one that question is already settled — asking it
    again produces advice the holder cannot act on. What a holder faces is
    narrower and harder: the print is coming, the exposure exists, and doing
    nothing is itself a choice that gets made by default if nobody names it.

    THE GAP THIS CLOSES. The screen skips names already held, on the sensible
    grounds that they are not opportunities. The effect was perverse — the one
    position with real money on it got LESS analysis than seven names with
    none, and the analysis it did get stopped at "decide now", which is a
    reminder rather than a recommendation.

    WHAT THE MEASUREMENT SAYS TO A HOLDER, and it is uncomfortable and
    specific. Holding a long through the print is the trade the day-68
    asymmetry argues against most directly: the approval leg is
    indistinguishable from a random window and the rejection leg takes -15.2%
    at the median. That is not an argument for exiting at any price, but it is
    an argument that the reward for carrying the event is not visible in the
    data, while the cost is.

    THREE ROUTES OUT, priced rather than listed:
      EXIT BEFORE       keeps the run-up, forfeits the print. Costs nothing but
                        the gap you did not take.
      HEDGE             keeps the upside, buys the tail. Priced here against
                        the measured median, in the same breakeven terms as
                        every other name.
      CARRY IT NAKED    the default, and the only one that must be chosen out
                        loud. What is at stake is stated in dollars.
    """
    import catalyst as _cat
    d = (dt.date.fromisoformat(leg["event_date"]) - today).days
    mark = leg.get("mark")
    sh = leg.get("shares")
    size = f"{sh:,.0f} share " if sh else ""
    L = [f"      DECISION on the {size}{leg['side']} you already hold, "
         f"{d}d out:"]
    if mark is None:
        L.append("        the mark is STALE, so none of the routes below can be "
                 "priced. Price it by hand before the print; a decision taken "
                 "on a stale mark is a guess with a number attached.")
        return L
    at_risk = mark * abs(_cat.CRL_MEDIAN) / 100 * (leg.get("shares") or 0)
    L.append(f"        CARRY IT NAKED — at the measured median rejection that "
             f"is ${at_risk:,.0f} at risk from here")
    L.append(f"        ({abs(_cat.CRL_MEDIAN):.1f}% of ${mark:,.2f}), and "
             f"{_cat.CRL_WORSE_THAN_40:.0%} of rejections finish worse than "
             "-40%. This is the")
    L.append("        default route: it happens if nobody chooses, which is "
             "the reason to choose.")
    if leg["side"].upper() == "LONG":
        L.append(f"        EXIT BEFORE — banks the move to ${mark:,.2f} and "
                 "forfeits the print. On this")
        L.append(f"        evidence the approval leg is positive but below "
                 f"the bar (+{_cat.APPROVAL_VS_RANDOM_PP:.1f}pp over random,")
        L.append(f"        t=+{_cat.APPROVAL_T:.2f} against a required "
                 f"{_cat.ADOPT_T:.0f}), so what is forfeited is a gap the data "
                 "hints at")
        L.append("        and cannot yet demonstrate.")
    be, be_med = breakeven_pair((row or {}).get("put_pct"))
    if be is not None and (row or {}).get("put_pct") is not None:
        L.append(f"        HEDGE — the put covering the date costs "
                 f"{row['put_pct']:.1%} of spot, so it pays for")
        L.append(f"        itself if a rejection is more than ~{be:.0%} likely "
                 f"against the measured MEAN")
        import catalyst as _c2
        L.append(f"        rejection ({_c2.CRL_MEAN:.1f}%) — or ~{be_med:.0%} "
                 f"against the median ({_c2.CRL_MEDIAN:.1f}%).")
        # A holder needs the comparison at least as much as a screener does:
        # this is the number that decides whether to pay for protection today.
        for x in against_base_rate(be):
            L += ["        " + y for y in _wrap(x, 62)]
        if row.get("parity") is not None and row["parity"] > PARITY_TOL:
            L.append("        ⚠ that quote FAILS the parity check — verify it "
                     "before pricing a hedge on it.")
    else:
        L.append("        HEDGE — no usable put quote covering the date, so "
                 "the only routes are")
        L.append("        exit or carry. Absence of a listed hedge is itself a "
                 "fact about this name.")
    return L


def hold_window(days: int, date: str) -> str:
    """When the position has to exist by, and when it stops being one."""
    if days <= 0:
        return "the date is TODAY — any expression had to exist yesterday"
    if days <= 5:
        return (f"{days}d out — express or stand aside now; premium decays into "
                f"the print and the decision can land early")
    if days <= 45:
        return (f"{days}d out — the working window. Express by D-5 ({date} minus "
                "a week); after that you are paying peak premium")
    return (f"{days}d out — too early to pay premium; the work now is the drug "
            "and the balance sheet, and the position is a later decision")


def screen(cal: list, today: dt.date, horizon: int = 120,
           max_names: int = 12, votes: dict | None = None) -> list:
    y, out, votes = Yahoo(), [], votes or {}
    # PRICE THE CONTROL FIRST. A failed check on a name means nothing until we
    # know the feed is serving bid/ask at all: at 06:47 ET every name on the
    # board failed, and so did SPY, whose ATM put quoted 0.00/0.00. Reporting
    # that as "these names failed their checks" told the PM half the calendar
    # was illiquid when the options market was simply shut. See quotes.py.
    import quotes as _q
    feed_live, feed_why = _q.feed_is_live(y.chain)
    for c in cal:
        d = (dt.date.fromisoformat(c["date"]) - today).days
        if not (0 <= d <= horizon) or not c.get("ticker"):
            continue
        row = {**c, "days": d, "spot": None, "move": None, "skew": None}
        try:
            r = y.chain(c["ticker"])
            row["spot"] = float(r["quote"].get("regularMarketPrice") or 0) or None
            e = pick_expiry(r.get("expirationDates", []),
                            dt.date.fromisoformat(c["date"]))
            if e and row["spot"]:
                rr = y.chain(c["ticker"], e)
                o = (rr.get("options") or [{}])[0]
                row["expiry"] = dt.datetime.utcfromtimestamp(e).date().isoformat()
                row["move"] = implied_move(o.get("calls", []), o.get("puts", []),
                                           row["spot"])
                row["skew"] = skew(o.get("calls", []), o.get("puts", []),
                                   row["spot"])
                row["call_pct"], row["put_pct"] = leg_costs(
                    o.get("calls", []), o.get("puts", []), row["spot"])
                ca, pa = (_atm(o.get("calls", []), row["spot"]),
                          _atm(o.get("puts", []), row["spot"]))
                row["px_source"] = option_price(pa)[1] if pa else "none"
                row["parity"] = parity_gap(ca, pa, row["spot"])
                row["put_oi"] = (pa or {}).get("openInterest")
                row["_puts"], row["_atm_put"] = o.get("puts", []), pa
            row["_expiries"] = r.get("expirationDates", [])
        except Exception as ex:
            row["error"] = type(ex).__name__
            row["reason"] = _q.CHAIN_ERROR
            row["reason_detail"] = type(ex).__name__
        # TYPED, not a class name. The old `error` recorded only the exception
        # type and the silent paths -- no expiry, no spot, no puts -- recorded
        # nothing, so every distinct cause reached the report as one sentence.
        if "reason" not in row:
            row["reason"] = _q.classify(
                row.get("spot"), row.get("_expiries"), row.get("expiry"),
                row.get("_puts"), row.get("_atm_put"), row.get("parity"),
                PARITY_TOL, feed_live=feed_live)
        row["reason_why"] = _q.EXPLAIN.get(row["reason"], row["reason"])
        row["feed_live"] = feed_live
        row["stance"], row["why"] = stance(row["move"], row["skew"], d,
                                           c.get("signals", []))
        # The balance sheet is the only hard-ish floor a pre-revenue name has,
        # and every catalyst thesis leans on it without checking. See
        # fundamentals.py: the ZYME matrix claimed a cash-backed floor at
        # $20.50 while the 10-Q shows $2.53/share.
        try:
            import fundamentals as _f
            row["fund"] = _f.summarise(c["cik"], today) if c.get("cik") else None
        except Exception:
            row["fund"] = None
        # The synthesis runs LAST, after every input it reads is on the row.
        # It must never be the reason a name drops out of the screen: a broken
        # verdict still leaves a real date and a real price worth seeing.
        # DAY-79: what protection SHOULD cost, from THIS name's own returns.
        # The breakeven-vs-base-rate number below counts only the CRL branch
        # and undercounts a put by ~2.5x; see fairvalue.py.
        row["fv"] = None
        row["fv_error"] = None
        try:
            import fairvalue as _fv
            from validate_catalyst import daily_range as _dr
            df = _dr(c["ticker"])
            if df is not None and len(df):
                # DAY-72 GATE, before anything counts these bars. Yahoo serves
                # weekly or monthly bars for a daily request without erroring,
                # and every horizon below is measured in BARS.
                _sn.check_prices(df, c["ticker"])
                exp = row.get("expiry")
                dte = ((dt.date.fromisoformat(exp) - today).days * 5 // 7
                       if exp else 21)
                fv = _fv.fair_put(df["Close"].to_numpy(), max(dte, 3))
                # Fail closed on an impossible number (rule 2): drop the fair
                # value and SAY so. One bad name must not stop the report, and
                # must not print either.
                row["fv_warn"] = _sn.check_fair_value(fv, c["ticker"])
                row["fv"] = fv
                row["fv_days"] = max(dte, 3)
        except _sn.Impossible as ex:
            row["fv"], row["fv_error"] = None, f"failed the plausibility gate — {ex}"
        except Exception as ex:
            # Never silently (rule 1, day-29 and day-55). Name it on the row.
            row["fv"] = None
            row["fv_error"] = f"{type(ex).__name__}: {ex}"
        try:
            row["verdict"] = verdict(row, votes.get(c["ticker"]))
        except Exception as ex:
            row["verdict"] = {"call": "VERDICT UNAVAILABLE",
                              "why": [f"synthesis failed ({type(ex).__name__}) "
                                      "— the inputs below stand, the "
                                      "conclusion does not"],
                              "breakeven": None}
        out.append(row)
        if len(out) >= max_names:
            break
    return out


def rank_opportunities(rows: list, top: int = 2) -> dict:
    """The best-priced expressions per horizon, ranked by a measured quantity.

    WHY THE SCREEN NEEDED THIS ON TOP OF ITSELF. It lists names in DATE order,
    which is the order a calendar has and not the order a decision has. A
    portfolio manager asking "what are my two best pharma trades this month"
    was being handed eight names sorted by when the FDA happens to be sitting,
    and left to rank them by eye across four different inputs.

    THE RANKING QUANTITY, and there is only one honest candidate: the breakeven
    P(CRL) divided by the MEASURED base rate for this population (day-71). It
    is a pure number, it is comparable across names of any price or size, and
    it says exactly what a PM needs — how far from the average this name would
    have to be before the premium pays. A multiple near 1 is protection priced
    at what the population actually delivers. A multiple of 5 is a lottery
    ticket with a story attached.

    THE HORIZONS ARE THE USER'S, not the calendar's:
        WEEK     <= 10 days   the position has to exist now
        MONTH    11-45 days   the working window; express by D-5
        QUARTER  46+ days     too early to pay premium, right time to research

    WHAT IS DELIBERATELY ABSENT IS A LONG SIDE, and day-72 made that call
    closer rather than easier. On corrected daily bars the approval reaction is
    POSITIVE — +5.4pp over random windows, t=+2.42 on 173 events — where day-68
    had it indistinguishable from noise. That still does not clear the
    pre-registered |t| >= 3, and the bar does not move because a number came
    close to it. So no long is ranked, and the reason printed is the true one:
    positive and below the bar, not absent.

    Names whose quote failed the parity, two-sided or open-interest checks are
    EXCLUDED rather than ranked last: a ranking built on a price known to be
    wrong is worse than a shorter list.
    """
    import baserate as _br
    s = _br.summary()
    buckets = {"WEEK": [], "MONTH": [], "QUARTER": []}
    skipped = []
    for r in rows:
        v = r.get("verdict") or {}
        if v.get("call") in ("PRICING UNRELIABLE — VERIFY THE QUOTE",
                             "VERDICT UNAVAILABLE"):
            skipped.append((r["ticker"], "quote failed its checks"))
            continue
        if v.get("call") == "NOT AN EVENT TRADE":
            skipped.append((r["ticker"], "decision is immaterial to the "
                                         "enterprise"))
            continue
        be = r.get("put_be")
        fv = r.get("fv")
        ratio = None
        if fv and r.get("put_pct") is not None and fv.get("fair"):
            ratio = (r["put_pct"] * 100) / fv["fair"]
        if ratio is None:
            skipped.append((r["ticker"], "no measurable fair value"))
            continue
        d = r["days"]
        key = "WEEK" if d <= 10 else ("MONTH" if d <= 45 else "QUARTER")
        buckets[key].append({**r, "fv_ratio": ratio,
                             "multiple_lo": (be / s["hi"]) if be and s else None,
                             "multiple_hi": (be / s["lo"]) if be and s else None})
    for k in buckets:
        # RANK BY FAIR-VALUE RATIO. Cheapest against what the name's own
        # returns say the protection is worth -- the correct economic
        # comparison, and not the CRL-only breakeven that undercounts a put.
        buckets[k].sort(key=lambda r: r["fv_ratio"])
        buckets[k] = buckets[k][:top]
    return {"buckets": buckets, "skipped": skipped, "base": s}


def render_ranked(ranked: dict, today: dt.date, top: int = 2) -> str:
    """The short list, above the full one. Ranked, not dated."""
    s = ranked.get("base")
    L = [f"▎BEST-PRICED PHARMA EXPRESSIONS — top {top} per horizon"]
    if not s:
        return ("▎BEST-PRICED PHARMA EXPRESSIONS\n   ⚠ no base rate computed, "
                "so nothing can be ranked. Run `python baserate.py`.")
    any_row = False
    for key, label in (("WEEK", "THIS WEEK   (<= 10d — the position has to "
                                "exist now)"),
                       ("MONTH", "THIS MONTH  (11-45d — express by D-5)"),
                       ("QUARTER", "LATER       (46d+ — research now, position "
                                   "later)")):
        L.append(f"   {label}")
        rows = ranked["buckets"][key]
        if not rows:
            L.append("      nothing priced in this window")
            continue
        any_row = True
        for i, r in enumerate(rows, 1):
            L.append(f"      {i}. {r['ticker']:<6} {r['date']}  ({r['days']:>3}d)"
                     f"   put {r['put_pct']:.1%} of spot")
            L.append(f"         vs measured fair value {r['fv']['fair']:.1f}% "
                     f"-> {r['fv_ratio']:.2f}x  ({r['fv']['bucket']}-vol)")
            if r.get("multiple_lo") is not None:
                L.append(f"         [secondary, CRL branch only: needs P(CRL) "
                         f"~{r['put_be']:.0%} = {r['multiple_lo']:.1f}-"
                         f"{r['multiple_hi']:.1f}x the base rate]")
            L.append(f"         {r['verdict']['call']}")
    if any_row:
        L.append("   ── ranked by QUOTED / MEASURED FAIR VALUE, computed from "
                 "each name's own")
        L.append("      returns (605 decisions, 7,440 random windows). Below "
                 "1.0x the market")
        L.append("      charges less than the name's own history says the "
                 "protection is worth.")
        L.append("      The fair value is measured; whether trading the gap "
                 "pays is NOT")
        L.append("      backtested — no free historical option prices exist.")
    import catalyst as _cat
    L.append("   ── NO LONG SIDE IS RANKED, and day-72 made that call closer. On")
    L.append(f"      corrected daily bars the approval reaction is POSITIVE — "
             f"+{_cat.APPROVAL_VS_RANDOM_PP:.1f}pp over")
    L.append(f"      random windows, t=+{_cat.APPROVAL_T:.2f} on "
             f"{_cat.APPROVAL_N} events. It does not clear the")
    L.append(f"      pre-registered |t| >= {_cat.ADOPT_T:.0f}, and the bar does "
             "not move because a number came")
    L.append("      close to it. Positive and below the bar is the honest "
             "reason, and it")
    L.append("      is a different sentence from 'no edge exists'.")
    for t, why in ranked["skipped"][:6]:
        L.append(f"   · {t} not ranked — {why}")
    return "\n".join(L)


def render(rows: list, today: dt.date) -> str:
    if not rows:
        return ("▎CATALYST OPPORTUNITIES\n   nothing scheduled in the window "
                "with a resolvable price")
    L = ["▎CATALYST OPPORTUNITIES — what the market has already priced"]
    for r in rows:
        spot = f"${r['spot']:,.2f}" if r["spot"] else "—"
        mv = f"+/-{r['move']:.0%}" if r["move"] is not None else "—"
        L.append(f"   {r['date']}  ({r['days']:>3}d)  {r['ticker']:<6} "
                 f"{r['company'][:30]:<32} {spot:>9}  implied {mv:>7}")
        L.append(f"        setup   : {r['stance'].upper()} — {r['why']}")
        if r["move"] is not None and r["spot"]:
            up = r["spot"] * (1 + r["move"])
            dn = r["spot"] * (1 - r["move"])
            L.append(f"        priced range on the print: ${dn:,.2f} … ${up:,.2f}"
                     f"  (expiry {r.get('expiry','?')})")
        if r.get("fund"):
            import fundamentals as _f
            L += [("  " + x) for x in _f.render(r["fund"], r.get("spot"))]
        if r.get("signals"):
            L.append(f"        filings : {', '.join(r['signals'])}")
        # Whose application is it? The single fact that would have changed the
        # ZYME call on 2026-08-25 (see partners.py).
        try:
            import partners as _p
            sh = (r.get("fund") or {}).get("shares")
            L += _p.render(r.get("partner"), r.get("spot"), sh)
        except Exception:
            pass
        if r.get("error"):
            L.append(f"        ⚠ options unavailable ({r['error']}) — "
                     "the date stands, the pricing does not")
        if r.get("fv_error"):
            L += _wrap_at(f"⚠ no fair value for {r['ticker']}: "
                          f"{r['fv_error']}. The date and the quote stand; "
                          "the fair-value comparison is withheld.", 8)
        if r.get("fv") and r.get("put_pct") is not None:
            import fairvalue as _fv
            L += _fv.render(r["put_pct"] * 100, r["fv"], r.get("fv_days", 21))
            for w in r.get("fv_warn") or []:
                L += _wrap_at(w, 8)
        v = r.get("verdict")
        if v:
            L.append(f"        VERDICT : {v['call']}")
            for w in v["why"]:
                wrapped = _wrap(w, 64)
                L.append("          - " + wrapped[0])
                L += ["            " + x for x in wrapped[1:]]
            wl = _wrap(hold_window(r["days"], r["date"]), 64)
            L.append("        window  : " + wl[0])
            L += ["                    " + x for x in wl[1:]]
    import catalyst as _cat
    L.append("   ── the spine of every verdict above, MEASURED here (day-68), not")
    L.append("      borrowed: a rejection moves the stock a median "
             f"{_cat.CRL_MEDIAN:.1f}% and")
    L.append(f"      {_cat.CRL_VS_RANDOM_PP:.1f}pp against random windows on the "
             f"same names (t={_cat.CRL_T:.2f}, n={_cat.CRL_N});")
    L.append(f"      an approval is POSITIVE but below the bar "
             f"(+{_cat.APPROVAL_VS_RANDOM_PP:.1f}pp over random, "
             f"t=+{_cat.APPROVAL_T:.2f},")
    L.append(f"      n={_cat.APPROVAL_N}) — not adopted, and no longer the "
             "'already priced' claim")
    L.append("      day-68 made on contaminated bars.")
    try:
        import baserate as _br
        s = _br.summary()
    except Exception:
        s = None
    if s:
        span = (f"{s['lo']:.0%}-{s['hi']:.0%}" if s["audited"]
                else f"~{s['hi']:.0%}")
        L.append(f"   ── the base rate above is {span}: of {s['n']:,} FDA "
                 f"decisions announced in")
        L.append(f"      8-Ks {s['n_crl']:,} were rejections, both legs from one "
                 "harvest and one")
        L.append("      classifier (day-71). The FDA publishes no rejections at "
                 "all — Drugs@FDA")
        L.append("      carries approvals only — so the sponsor's own filing is "
                 "the only free")
        L.append("      trace one leaves, and that is why this number did not "
                 "exist before.")
        L.append("      It is UNCONDITIONAL: the prior you argue away from, not "
                 "an answer.")
        # DAY-78: the most obvious conditioning was tested and did not clear
        # its pre-registered bar. Recorded here so the question is closed
        # rather than quietly re-asked every few weeks.
        L.append("   ── conditioning TESTED (day-78): a sponsor with a prior CRL "
                 "runs 16.0%")
        L.append("      [11.9, 21.2] against 9.9% [8.0, 12.2] without, n=238 vs "
                 "817. The")
        L.append("      pre-registered bar was non-overlapping intervals and "
                 "they overlap by")
        L.append("      0.3pp, so the unconditional rate STANDS. Direction and "
                 "size are worth")
        L.append("      knowing when you read a resubmission; the rate above is "
                 "not adjusted.")
    else:
        L.append("   ── no base rate has been computed, so each breakeven above "
                 "stands alone")
        L.append("      with nothing to compare it against. Run "
                 "`python baserate.py`.")
    return "\n".join(L)


def _wrap_at(text: str, indent: int, width: int = 68) -> list:
    """Wrapped and indented, for the gate's messages beside a name."""
    pad = " " * indent
    lines = _wrap(text, width)
    return [pad + lines[0]] + [pad + "  " + x for x in lines[1:]]


def _wrap(text: str, width: int) -> list:
    out, line = [], ""
    for w in text.split():
        if line and len(line) + 1 + len(w) > width:
            out.append(line)
            line = w
        else:
            line = (line + " " + w) if line else w
    if line:
        out.append(line)
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--calendar",
                    default=os.path.join(SCRATCH, "pdufa_calendar.json"))
    ap.add_argument("--horizon", type=int, default=120)
    ap.add_argument("--max-names", type=int, default=12)
    a = ap.parse_args(argv)
    today = dt.date.today()
    cal = json.load(open(a.calendar)) if os.path.exists(a.calendar) else []
    print(render(screen(cal, today, a.horizon, a.max_names), today))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
