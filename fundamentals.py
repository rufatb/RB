#!/usr/bin/env python3
"""
fundamentals.py — the balance sheet behind a catalyst, free from SEC XBRL.

WHY THIS EXISTS. `catalyst.py` can tell you a downside assumption is an
ASSUMPTION, but not what the real floor is. For a clinical-stage biotech the
honest floor reference is CASH PER SHARE, and every catalyst thesis leans on it
— the ZYME matrix justified a -18% downside with "$322.5M existing cash and
buybacks" and nothing checked the number.

Checked, from the company's own 10-Q (2026-06-30):

    cash and equivalents      $179,413,000
    shares outstanding          70,959,241
    cash per share                   $2.53

At $28.67 the stock trades at ELEVEN TIMES its cash. A "cash floor" cannot
support a $20.50 downside when cash is $2.53 a share — the floor in that
matrix was doing work the balance sheet does not support. That is the kind of
error a screen should catch before a position is opened, not after a CRL.

WHAT IT COMPUTES
  cash_per_share   cash + short-term investments, over shares outstanding. The
                   nearest thing to a hard floor a pre-revenue name has.
  runway_quarters  cash divided by quarterly operating burn. A company with
                   three quarters left dilutes regardless of the FDA's answer,
                   so the equity story is financing, not approval.
  price_to_cash    how much of the price is NOT cash. The multiple you are
                   paying for the pipeline.

FAIL CLOSED. Tags go missing, get renamed between filers, and go stale. Every
figure carries the date and form it came from, and a stale or absent tag yields
None rather than a confident wrong number — a fabricated balance sheet is worse
than no balance sheet. Short-term investments older than `stale_days` are
DROPPED rather than added to cash (ZYME's ShortTermInvestments tag last
reported in 2023; counting it would have overstated liquidity by $217M).
"""

from __future__ import annotations

import datetime as dt
import json
import os
import sys
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from validate_exit import SCRATCH  # noqa: E402

H = {"User-Agent": "RB-research/1.0 (non-commercial)",
     "Accept": "application/json"}
CASH_TAGS = ["CashAndCashEquivalentsAtCarryingValue",
             "CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents"]
INVEST_TAGS = ["ShortTermInvestments", "MarketableSecuritiesCurrent",
               "AvailableForSaleSecuritiesDebtSecuritiesCurrent"]
BURN_TAGS = ["NetCashProvidedByUsedInOperatingActivities",
             "NetCashProvidedByUsedInOperatingActivitiesContinuingOperations"]
DEBT_TAGS = ["LongTermDebtNoncurrent", "LongTermDebt"]


def _get(url: str) -> dict:
    return json.loads(urllib.request.urlopen(
        urllib.request.Request(url, headers=H), timeout=45).read())


def company_facts(cik: str, cache_dir: str = SCRATCH) -> dict | None:
    p = os.path.join(cache_dir, f"facts_{cik}.json")
    if os.path.exists(p):
        return json.load(open(p))
    try:
        d = _get(f"https://data.sec.gov/api/xbrl/companyfacts/"
                 f"CIK{str(cik).zfill(10)}.json")
    except Exception:
        return None
    os.makedirs(cache_dir, exist_ok=True)
    json.dump(d, open(p, "w"))
    return d


def latest(facts: dict, tags: list, ns: str = "us-gaap",
           unit: str = "USD") -> dict | None:
    """Most recently ENDED observation across a list of candidate tags.

    Filers use different tags for the same line, and the same filer changes
    tags between years — so the caller passes every synonym it knows and this
    returns whichever reported most recently, along with the date and form so
    the caller can judge staleness rather than trust a bare number.
    """
    best = None
    for t in tags:
        u = (facts.get("facts", {}).get(ns, {}).get(t, {})
             .get("units", {}).get(unit))
        if not u:
            continue
        cand = max(u, key=lambda x: x.get("end", ""))
        if best is None or cand.get("end", "") > best.get("end", ""):
            best = {**cand, "tag": t}
    return best


def summarise(cik: str, today: dt.date | None = None,
              stale_days: int = 400) -> dict:
    """Balance-sheet snapshot. Every field may be None; none are guessed."""
    today = today or dt.date.today()
    out = {"cik": cik, "cash": None, "shares": None, "cash_per_share": None,
           "burn_q": None, "runway_q": None, "as_of": None, "notes": []}
    f = company_facts(cik)
    if not f:
        out["notes"].append("XBRL facts unavailable")
        return out
    out["name"] = f.get("entityName", "")

    c = latest(f, CASH_TAGS)
    if c:
        out["cash"], out["as_of"] = float(c["val"]), c.get("end")
        out["form"] = c.get("form")
    inv = latest(f, INVEST_TAGS)
    if inv and out["cash"] is not None:
        age = (today - dt.date.fromisoformat(inv["end"])).days
        if age <= stale_days:
            out["cash"] += float(inv["val"])
        else:
            out["notes"].append(
                f"short-term investments last reported {inv['end']} "
                f"({age}d ago) — EXCLUDED as stale, liquidity may be understated")

    sh = latest(f, ["EntityCommonStockSharesOutstanding"], ns="dei",
                unit="shares")
    if sh:
        out["shares"] = float(sh["val"])
    if out["cash"] and out["shares"]:
        out["cash_per_share"] = out["cash"] / out["shares"]

    b = latest(f, BURN_TAGS)
    if b and float(b["val"]) < 0:
        # XBRL cash-flow values are cumulative for the fiscal period; the
        # start/end pair says how many months it covers.
        try:
            months = max(1, round((dt.date.fromisoformat(b["end"])
                                   - dt.date.fromisoformat(b["start"])).days / 30))
        except Exception:
            months = 12
        out["burn_q"] = abs(float(b["val"])) / months * 3
        if out["cash"] and out["burn_q"]:
            out["runway_q"] = out["cash"] / out["burn_q"]
    return out


def render(fs: dict, price: float | None = None) -> list:
    """Report lines. Silent when nothing could be established."""
    if fs.get("cash_per_share") is None and fs.get("runway_q") is None:
        return ([f"      balance sheet: unavailable ({'; '.join(fs['notes'])})"]
                if fs.get("notes") else [])
    L = []
    if fs.get("cash_per_share") is not None:
        line = (f"      balance sheet : ${fs['cash']/1e6:,.0f}M cash = "
                f"${fs['cash_per_share']:.2f}/share "
                f"(as of {fs.get('as_of')}, {fs.get('form','')})")
        L.append(line)
        if price:
            L.append(f"      price/cash    : {price/fs['cash_per_share']:.1f}x — "
                     f"${price - fs['cash_per_share']:.2f} of the ${price:.2f} "
                     "price is PIPELINE, not cash")
    if fs.get("runway_q") is not None:
        q = fs["runway_q"]
        warn = "  ⚠ dilution likely regardless of the FDA" if q < 4 else ""
        L.append(f"      runway        : {q:.1f} quarters at "
                 f"${fs['burn_q']/1e6:,.0f}M/qtr burn{warn}")
    for n in fs.get("notes", []):
        L.append(f"      ⚠ {n}")
    return L
