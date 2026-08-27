#!/usr/bin/env python3
"""
resolved.py — did the binary already settle, and which way?

THE BUG THIS EXISTS TO FIX, caught live on 2026-08-27. Zymeworks' PDUFA had
been decided two days earlier — approved, a $250M milestone earned — and the
morning report was still pricing it as pending:

    ZYME — PDUFA in -2d (2026-08-25)
    implied P NOW at $28.61 : 52%
    from here: +25.8% if approved, -28.4% if not  ->  risk/reward 0.91:1
    CARRY IT NAKED — at the measured median rejection that is $1,027 at risk

Every one of those lines is false about a settled event. There is no rejection
risk left to carry, no implied probability to read off the price, and the
"risk/reward" of a resolved binary is not a quantity. A negative day count was
printed and nothing acted on it.

The failure is worse than cosmetic. A holder reading "$1,027 at risk from a
rejection" on a position whose rejection risk is ZERO is being pushed toward
selling something for the wrong reason — and the same arithmetic, run on a name
that was actually rejected, would understate the damage just as badly.

WHAT IT DOES. For a position whose event date has passed, it asks EDGAR whether
the sponsor announced an outcome, and runs the same `classify.py` used to build
the historical sample. Three answers, and the third is not a failure:

    APPROVED / REJECTED   an 8-K on or after the date announces one
    ANNOUNCED, UNCLEAR    a filing landed but the classifier will not call it
    NO FILING FOUND       the FDA may have slipped the date, or the sponsor has
                          not filed yet. NOT "nothing happened".

WHY EDGAR AND NOT THE PRICE. A 10% move is not an outcome, it is a hint. The
filing is the fact, and this repo already has the machinery to read one — the
same classifier, the same fetch path, the same fail-closed discipline. Guessing
the outcome from the tape would be inventing data the way a cash-floor
assumption invents a balance sheet.

FAILS CLOSED, in the direction that matters. An unreachable EDGAR reports
UNKNOWN and the report keeps saying the position needs a human. It never
reports "resolved" without a filing that says so.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# 8-K items that carry material news. 8.01 (Other Events) and 7.01 (Reg FD) are
# how an FDA decision usually arrives; 2.02 is earnings and is not evidence.
NEWS_ITEMS = ("8.01", "7.01")
LOOK_DAYS = 21          # a decision can slip; a sponsor files within days


def _cik_for(ticker: str) -> str | None:
    try:
        import sixk
        return sixk.us_ticker_map().get(ticker.upper())
    except Exception:
        return None


def filings_after(cik: str, since: str, until: str | None = None) -> list:
    """8-Ks filed on or after `since`, newest first."""
    import build_catalyst as BC
    sub = json.loads(BC._get(
        f"https://data.sec.gov/submissions/CIK{int(cik):010d}.json"))
    r = sub.get("filings", {}).get("recent", {})
    out = []
    for form, d, items, acc in zip(r.get("form", []), r.get("filingDate", []),
                                   r.get("items", [""] * len(r.get("form", []))),
                                   r.get("accessionNumber", [])):
        if not form.startswith("8-K") or d < since:
            continue
        if until and d > until:
            continue
        out.append({"date": d, "items": items, "accession": acc})
    return sorted(out, key=lambda x: x["date"], reverse=True)


def filing_text(cik: str, accession: str, cap_docs: int = 6) -> str:
    import build_catalyst as BC
    a = accession.replace("-", "")
    idx = json.loads(BC._get(
        f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{a}/index.json"))
    names = [it["name"] for it in idx["directory"]["item"]
             if it["name"].endswith((".htm", ".txt"))]
    parts = []
    for n in names[:cap_docs]:
        try:
            parts.append(BC._strip(BC._get(
                f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{a}/{n}")))
        except Exception:
            continue
    return " ".join(parts)


def check(ticker: str, event_date: str, today: dt.date | None = None) -> dict:
    """Has this name's decision landed? Reads filings, never the tape."""
    today = today or dt.date.today()
    out = {"ticker": ticker, "event_date": event_date, "outcome": "UNKNOWN",
           "filed": None, "why": "", "accession": None}
    try:
        ev = dt.date.fromisoformat(event_date)
    except ValueError:
        out["why"] = "event date unparseable"
        return out
    if ev > today:
        out["outcome"] = "PENDING"
        out["why"] = f"the decision is still {(ev - today).days}d away"
        return out
    cik = _cik_for(ticker)
    if not cik:
        out["why"] = f"no CIK for {ticker} — cannot check, which is not 'clean'"
        return out
    try:
        fs = filings_after(cik, ev.isoformat(),
                           (ev + dt.timedelta(days=LOOK_DAYS)).isoformat())
    except Exception as e:
        out["why"] = f"EDGAR unreachable ({type(e).__name__}) — UNKNOWN, not clear"
        return out
    news = [f for f in fs if any(i in (f["items"] or "") for i in NEWS_ITEMS)]
    if not news:
        out["outcome"] = "NO FILING"
        out["why"] = ("no material 8-K since the date — the FDA may have "
                      "slipped it, or the sponsor has not filed")
        return out
    import classify
    for f in reversed(news):                 # oldest first: the announcement
        try:
            text = filing_text(cik, f["accession"])
        except Exception:
            continue
        crl, _ = classify.classify_crl(text, f["date"])
        appr, _ = classify.classify_approval(text, f["date"])
        if crl and not appr:
            return {**out, "outcome": "REJECTED", "filed": f["date"],
                    "accession": f["accession"],
                    "why": "8-K announces a complete response letter"}
        if appr and not crl:
            return {**out, "outcome": "APPROVED", "filed": f["date"],
                    "accession": f["accession"],
                    "why": "8-K announces an FDA approval"}
        if appr and crl:
            return {**out, "outcome": "UNCLEAR", "filed": f["date"],
                    "accession": f["accession"],
                    "why": "the filing reads as BOTH — read it yourself"}
    return {**out, "outcome": "UNCLEAR", "filed": news[0]["date"],
            "accession": news[0]["accession"],
            "why": "a material 8-K landed but the classifier will not call it"}


def render(res: dict, leg: dict | None = None) -> list:
    """Lines that replace the pending-binary arithmetic once it is settled."""
    o = res["outcome"]
    if o == "PENDING":
        return []
    L = []
    if o == "APPROVED":
        L.append(f"      ✔ RESOLVED — APPROVED, announced {res['filed']}. The "
                 "binary is settled.")
        L.append("        Every probability, bracket and risk/reward above "
                 "describes an event")
        L.append("        that has already happened and should be ignored. "
                 "What you hold now")
        L.append("        is an ordinary equity position in a company whose "
                 "asset cleared —")
        L.append("        re-underwrite it on that basis or close it; the "
                 "catalyst thesis is spent.")
    elif o == "REJECTED":
        L.append(f"      ✘ RESOLVED — REJECTED, announced {res['filed']}. The "
                 "binary is settled.")
        L.append("        The measured CRL distribution described the RISK, "
                 "not the aftermath.")
        L.append("        What matters now is runway and the resubmission "
                 "path, which are")
        L.append("        different questions from the one this section was "
                 "built to answer.")
    elif o == "NO FILING":
        L.append("      ⚠ the decision date has PASSED with no material 8-K. "
                 "The FDA may have")
        L.append("        slipped it, or the sponsor has not filed yet. This "
                 "is not evidence")
        L.append("        that nothing happened — check before acting on any "
                 "number above.")
    elif o == "UNCLEAR":
        L.append(f"      ⚠ a material 8-K landed {res['filed']} and the "
                 "classifier will not call it.")
        L.append(f"        {res['why']}. Read the filing; the numbers above "
                 "assume a pending event.")
    else:
        L.append(f"      ⚠ outcome UNKNOWN — {res['why']}.")
        L.append("        The arithmetic above assumes the event is still "
                 "pending. Verify that.")
    return L


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("ticker")
    ap.add_argument("event_date")
    a = ap.parse_args(argv)
    r = check(a.ticker, a.event_date)
    print(json.dumps(r, indent=1))
    print("\n".join(render(r)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
