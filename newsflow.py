#!/usr/bin/env python3
"""
newsflow.py — what changed overnight, for the names you hold and are watching.

WHY. The brief was a snapshot: here is your book, here is what is scheduled.
A portfolio manager's first question in the morning is the one it could not
answer — WHAT MOVED SINCE YESTERDAY. A position waiting three weeks on a PDUFA
is not static; the company keeps filing, and some of those filings matter more
than the decision itself.

WHY 8-K ITEM CODES RATHER THAN HEADLINES. Every 8-K is tagged by the SEC with
the item numbers that triggered it, and those codes are a structured statement
of what KIND of event occurred. That is far better than parsing a press release:
no sentiment model, no keyword guessing, and no possibility of a cheerful
headline hiding a hard disclosure. "Item 3.01" means a delisting notice whether
or not the company chose to use the word.

THE CODES THAT MATTER BEFORE A BINARY EVENT. Most 8-Ks are routine. A handful,
filed in the weeks before a catalyst, change the shape of the position:

    3.01  delisting notice / listing-rule failure — the exchange, not the FDA
    1.02  a material agreement TERMINATED — a partner walking is information
    5.02  officer or director departure — before a decision, unusual
    4.02  non-reliance on previously issued financials — accounting failure
    2.04  triggering event accelerating an obligation — a covenant broke
    3.02  unregistered equity sale — dilution, often at a discount

These are flagged. The rest are reported plainly and left alone, because a
screen that shouts at every filing teaches its reader to ignore it.

FORM 4 IS INCLUDED DELIBERATELY. Insider transactions in the run-up to a
scheduled decision are the one piece of genuinely private judgement that becomes
public. It is reported as a FACT with its date, never as a signal — insiders
sell for tax, diversification, and 10b5-1 plans set months earlier, and reading
intent into a Form 4 is how people talk themselves into a position.

FAIL CLOSED. A name whose filings cannot be fetched is NAMED as unavailable
rather than silently reported as quiet. "No news" and "no data" look identical
in a report and mean opposite things.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sys
import time
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

H = {"User-Agent": "RB-research/1.0 (non-commercial)",
     "Accept": "application/json"}

ITEMS = {
    "1.01": "material agreement signed",
    "1.02": "material agreement TERMINATED",
    "1.03": "bankruptcy or receivership",
    "2.02": "results of operations",
    "2.04": "triggering event accelerating an obligation",
    "3.01": "DELISTING notice / listing-rule failure",
    "3.02": "unregistered equity sale (dilution)",
    "4.01": "auditor changed",
    "4.02": "NON-RELIANCE on prior financials",
    "5.02": "officer/director departure or appointment",
    "5.07": "shareholder vote results",
    "7.01": "Reg FD disclosure",
    "8.01": "other events (FDA news usually lands here)",
    "9.01": "exhibits",
}
# Items that change the shape of a position when they land before a decision.
RED_FLAGS = {"1.02", "1.03", "2.04", "3.01", "3.02", "4.02", "5.02"}


def _get(url: str, tries: int = 3) -> dict:
    for i in range(tries):
        try:
            return json.loads(urllib.request.urlopen(
                urllib.request.Request(url, headers=H), timeout=45).read())
        except Exception:
            if i == tries - 1:
                raise
            time.sleep(2 ** i)
    raise RuntimeError("unreachable")


def recent_filings(cik: str, since: dt.date, limit: int = 40) -> list:
    """Filings for one CIK on or after `since`, newest first."""
    d = _get(f"https://data.sec.gov/submissions/CIK{str(cik).zfill(10)}.json")
    r = d.get("filings", {}).get("recent", {})
    out = []
    for i in range(min(limit, len(r.get("filingDate", [])))):
        fd = r["filingDate"][i]
        if fd < since.isoformat():
            break                       # the feed is reverse-chronological
        out.append({"date": fd, "form": r["form"][i],
                    "items": [x.strip() for x in (r["items"][i] or "").split(",")
                              if x.strip()],
                    "accession": r["accessionNumber"][i],
                    "cik": str(cik).lstrip("0")})
    return out


def describe(f: dict) -> tuple:
    """(one-line description, is_flagged). Pure + testable."""
    form = f["form"]
    if form in ("424B5", "424B4", "424B3"):
        # A prospectus supplement is a shelf TAKEDOWN — shares being sold. For
        # a cash-burning biotech this is the financing story arriving, and the
        # first version of this file filed it under "routine". INO filed two in
        # eight days against 1.9 quarters of runway; that is not routine.
        return "424B5 prospectus supplement — SHARES BEING SOLD (dilution)", True
    if form == "S-3" or form.startswith("S-3"):
        return "S-3 shelf registration — capacity to sell shares", False
    if form == "4":
        return "insider transaction (Form 4) — a fact, not a signal", False
    if form.startswith("SCHEDULE 13"):
        return "13D/G — large holder position change", False
    if form in ("10-Q", "10-K"):
        return f"{form} — periodic report", False
    if form != "8-K":
        return form, False
    named = [ITEMS.get(i, f"item {i}") for i in f["items"] if i != "9.01"]
    flagged = any(i in RED_FLAGS for i in f["items"])
    return ("8-K: " + ("; ".join(named) if named else "unspecified")), flagged


# Forms that are individually uninteresting but collectively worth a line.
BULK = {"4": "insider transactions (Form 4)",
        "144": "proposed insider sales (Form 144)",
        "SCHEDULE 13G": "13G holder filings", "SCHEDULE 13G/A": "13G holder filings",
        "SCHEDULE 13D": "13D holder filings", "SCHEDULE 13D/A": "13D holder filings"}


def gather(names: list, since: dt.date, sleep: float = 0.12) -> dict:
    """{ticker: {"filings": [...], "error": str|None}} — errors are kept."""
    out = {}
    for tk, cik in names:
        if not cik:
            out[tk] = {"filings": [], "error": "no CIK"}
            continue
        try:
            fs = recent_filings(cik, since)
            out[tk] = {"filings": fs, "error": None}
        except Exception as e:
            out[tk] = {"filings": [], "error": type(e).__name__}
        time.sleep(sleep)
    return out


def summarise_name(filings: list) -> tuple:
    """(flagged lines, notable lines, bulk summary). Pure + testable.

    A morning brief is not a filing log. The first version printed every row and
    produced 42 lines for five names — CYTK alone contributed nine Form 4s, which
    buried an INO share offering three lines below. Repetitive forms are counted
    into one line; the things that change a position keep their own.
    """
    flagged, notable, bulk = [], [], {}
    for f in filings:
        key = f["form"].upper()
        if key in BULK:
            bulk.setdefault(BULK[key], []).append(f["date"])
            continue
        desc, flag = describe(f)
        (flagged if flag else notable).append((f["date"], desc))
    bulk_txt = []
    for label, dates in sorted(bulk.items()):
        n = len(dates)
        span = (f"{min(dates)}" if n == 1 else f"{min(dates)}..{max(dates)}")
        bulk_txt.append(f"{n} {label} ({span})")
    return flagged, notable, "; ".join(bulk_txt)


def render(flow: dict, since: dt.date, today: dt.date) -> str:
    days = max(1, (today - since).days)
    L = [f"▎WHAT CHANGED — filings in the last {days}d for names you hold "
         "or are watching"]
    quiet, unavailable, any_flag = [], [], False
    for tk in sorted(flow):
        v = flow[tk]
        if v["error"]:
            unavailable.append(f"{tk} ({v['error']})")
            continue
        if not v["filings"]:
            quiet.append(tk)
            continue
        flagged, notable, bulk = summarise_name(v["filings"])
        any_flag = any_flag or bool(flagged)
        for d, desc in flagged:
            L.append(f"   ⚠ {d}  {tk:<6} {desc}")
        for d, desc in notable:
            L.append(f"     {d}  {tk:<6} {desc}")
        if bulk:
            L.append(f"     {'':10} {tk:<6} {bulk}")
    if quiet:
        L.append(f"   quiet: {', '.join(quiet)}")
    if unavailable:
        L.append(f"   ⚠ could not check: {', '.join(unavailable)} — "
                 "no data is NOT the same as no news")
    if any_flag:
        L.append("   ⚠ flagged items change the shape of a position "
                 "independently of the catalyst.")
    if len(L) == 1:
        L.append("   nothing filed — but see the caveat above if any name "
                 "failed to fetch")
    return "\n".join(L)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=5)
    ap.add_argument("--names", nargs="*", default=[],
                    help="TICKER:CIK pairs, e.g. ZYME:1937653")
    a = ap.parse_args(argv)
    today = dt.date.today()
    since = today - dt.timedelta(days=a.days)
    pairs = [(n.split(":")[0], n.split(":")[1] if ":" in n else "")
             for n in a.names]
    print(render(gather(pairs, since), since, today))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
