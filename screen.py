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

WHAT THIS DELIBERATELY DOES NOT DO. It does not estimate a probability of
approval. Day-56 established that this repo cannot yet identify catalyst
outcomes reliably enough to backtest one, so any number I produced would be
unvalidated dressing on a guess. What it CAN do is state precisely what the
market has already priced, so a human judgement about the drug is applied to
the residual rather than to the whole question.

HOW TO READ THE STANCE COLUMN. It is a description of the SETUP, never a
recommendation to buy. "Cheap binary" means the options market is pricing a
smaller move than binaries of this kind usually deliver — which is a reason to
look, not a reason to trade. The molecule decides the trade; this decides where
to spend the afternoon.
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

from validate_exit import SCRATCH  # noqa: E402

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120 Safari/537.36")
H = {"User-Agent": UA, "Accept": "application/json,text/plain,*/*"}
# Binary biotech events historically deliver large moves; an implied move well
# under this is the market pricing a non-event. Not a threshold for trading —
# a threshold for LOOKING.
CHEAP_MOVE = 0.20
RICH_MOVE = 0.45


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


def implied_move(calls: list, puts: list, spot: float) -> float | None:
    """ATM straddle over spot — the market's expected magnitude, either way."""
    c, p = _atm(calls, spot), _atm(puts, spot)
    if not c or not p or not spot:
        return None
    return (float(c["lastPrice"]) + float(p["lastPrice"])) / spot


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
    if move < CHEAP_MOVE:
        s = ("not material",
             f"only +/-{move:.0%} implied — the market treats this decision as "
             "immaterial to the enterprise, not as a mispriced binary. A "
             "diversified or large-cap sponsor; the event is not the story")
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


def screen(cal: list, today: dt.date, horizon: int = 120,
           max_names: int = 12) -> list:
    y, out = Yahoo(), []
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
        except Exception as ex:
            row["error"] = type(ex).__name__
        row["stance"], row["why"] = stance(row["move"], row["skew"], d,
                                           c.get("signals", []))
        out.append(row)
        if len(out) >= max_names:
            break
    return out


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
        if r.get("signals"):
            L.append(f"        filings : {', '.join(r['signals'])}")
        if r.get("error"):
            L.append(f"        ⚠ options unavailable ({r['error']}) — "
                     "the date stands, the pricing does not")
    L.append("   ── no approval probability is estimated here. Day-56 could not")
    L.append("      identify catalyst outcomes well enough to backtest one, so")
    L.append("      the molecule decides the trade; this decides where to look.")
    return "\n".join(L)


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
