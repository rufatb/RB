#!/usr/bin/env python3
"""
adcom.py — FDA Advisory Committee meetings: scheduled ones, and how votes went.

WHY THIS IS THE MOST INFORMATIVE FREE INPUT IN THE STACK. A PDUFA date is when
an answer arrives. An AdCom is where the UNCERTAINTY RESOLVES — a public panel
of outside experts votes on the evidence, weeks before the agency rules, and the
stock usually moves more on the vote than on the decision that follows it. The
FDA is not bound by the vote, but it is the single best public read on how the
evidence is landing.

WHY NOT THE FEDERAL REGISTER. It announces these meetings and is free, but the
notices mix forward announcements with retrospective summaries inside committee
renewal documents, and nothing in them maps a sponsor to a ticker. Tried and
rejected: the extraction was noisy and would have needed a second name-matching
hop. Company 8-Ks carry the same facts, already attributed to a filer, through
machinery this repo already runs (`pdufa.py`).

TWO FORMATS, BOTH REAL, AND THE SECOND IS WHY DIRECTION IS NOT INFERRED FROM
THE TALLY. Observed live:

    REPL  "Advisory Committee voted 10 to 3 that the efficacy results from the
           IGNYTE study are evaluable and clinically meaningful"
    CAPR  "Advisory Committee voted that available evidence did not support the
           effectiveness of Deramiocel..."

The first is favourable with a tally. The second is plainly unfavourable and has
NO tally at all. And a tally alone cannot be read: "10 to 3" is good news only
if the question was framed positively, and panels are routinely asked whether
the evidence FAILS to support a use. So direction is taken from the LANGUAGE,
the tally is reported beside it, and when the language is ambiguous the tool
says so and prints the sentence rather than guessing.

WHAT IT DOES NOT DO. It does not convert a vote into a probability of approval.
The FDA follows its panels most of the time but not always, and day-56
established this repo cannot yet measure outcome frequencies reliably enough to
attach a number. The vote is reported as what it is: the most informative public
evidence available before the decision.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from pdufa import BIO_SIC, TICKER_RE, _get, strip_html  # noqa: E402
from validate_exit import SCRATCH  # noqa: E402

FTS = "https://efts.sec.gov/LATEST/search-index"
SCHEDULED = '"Advisory Committee meeting"'
VOTED = '"Advisory Committee voted"'

DATE_RE = re.compile(
    r"(?:Advisory Committee|AdCom)[^.]{0,120}?"
    r"(?:on|scheduled for)\s+([A-Z][a-z]+\s+\d{1,2},\s+20\d\d)")
TALLY_RE = re.compile(r"voted\s+(\d{1,2})\s*(?:to|-|–|—)\s*(\d{1,2})")
# "voted 3 in favor and 9 against" — an EXPLICIT, labelled tally. This must be
# read before any keyword test: Capricor's 8-K of 2026-08-13 contains exactly
# this sentence, and a substring match on "in favor" classified a 3-9 REJECTION
# as favourable. The numbers are unambiguous where the keyword is not.
FAVOR_AGAINST_RE = re.compile(
    r"(\d{1,2})\s+in favou?r\s+(?:and\s+)?(\d{1,2})\s+against", re.I)
UNFAVOURABLE = [
    r"did not support", r"does not support", r"voted against",
    r"do not outweigh", r"was not favorable", r"failed to (?:show|demonstrate)",
]
FAVOURABLE = [
    r"in favor", r"voted that .{0,60}support", r"benefits? outweigh",
    r"clinically meaningful", r"is favorable", r"supports? the (?:effectiveness|approval)",
]


def vote_direction(text: str) -> str:
    """'favourable' | 'unfavourable' | 'unclear' from the LANGUAGE, not the tally.

    ORDER MATTERS, and both rules were learned from real filings:

    1. An EXPLICIT labelled tally beats every keyword. Capricor's 8-K reads
       "voted 3 in favor and 9 against" — a rejection whose sentence contains
       the phrase "in favor". Reading the keyword first classified it as
       FAVOURABLE, which is the single worst error this file could make.
    2. Unfavourable keywords beat favourable ones: "did not support" contains
       "support", so a naive favourable check matches the sentence saying the
       opposite.
    """
    m = FAVOR_AGAINST_RE.search(text)
    if m:
        return "favourable" if int(m.group(1)) > int(m.group(2)) else "unfavourable"
    low = text.lower()
    if any(re.search(p, low) for p in UNFAVOURABLE):
        return "unfavourable"
    if any(re.search(p, low) for p in FAVOURABLE):
        return "favourable"
    return "unclear"


def vote_tally(text: str) -> tuple | None:
    """(for, against). Prefers the labelled form, which is unambiguous."""
    m = FAVOR_AGAINST_RE.search(text) or TALLY_RE.search(text)
    return (int(m.group(1)), int(m.group(2))) if m else None


def vote_sentence(text: str, width: int = 260) -> str:
    i = text.find("Advisory Committee voted")
    if i < 0:
        return ""
    return re.sub(r"\s+", " ", text[i:i + width]).strip()


def meeting_dates(text: str, after: dt.date) -> list:
    out = []
    for s in DATE_RE.findall(text):
        try:
            d = dt.datetime.strptime(s, "%B %d, %Y").date()
        except ValueError:
            continue
        if d > after and d.isoformat() not in out:
            out.append(d.isoformat())
    return out


def _search(phrase: str, start: str, end: str) -> list:
    u = (f"{FTS}?q={urllib.parse.quote(phrase)}&forms=8-K"
         f"&startdt={start}&enddt={end}")
    return json.loads(_get(u)).get("hits", {}).get("hits", [])


def build(months_back: int = 6, today: dt.date | None = None,
          cache_path: str | None = None) -> dict:
    today = today or dt.date.today()
    start = (today - dt.timedelta(days=30 * months_back)).isoformat()
    seen, upcoming, votes = set(), [], []
    for phrase in (SCHEDULED, VOTED):
        for h in _search(phrase, start, today.isoformat()):
            s = h.get("_source", {})
            if (s.get("sics") or [""])[0] not in BIO_SIC:
                continue
            cik, acc = (s.get("ciks") or [""])[0].lstrip("0"), s.get("adsh", "")
            if not cik or (cik, acc) in seen:
                continue
            seen.add((cik, acc))
            name = (s.get("display_names") or [""])[0]
            tm = TICKER_RE.search(re.sub(r"\s*\(CIK.*", "", name).strip())
            try:
                text = strip_html(_get(f"https://www.sec.gov/Archives/edgar/"
                                       f"data/{cik}/{acc}.txt"))
            except Exception:
                continue
            base = {"ticker": tm.group(1) if tm else "",
                    "company": re.sub(r"\s*\(.*", "", name).strip(),
                    "filed": s.get("file_date", ""), "cik": cik}
            if "Advisory Committee voted" in text:
                votes.append({**base, "direction": vote_direction(text),
                              "tally": vote_tally(text),
                              "sentence": vote_sentence(text)})
            for d in meeting_dates(text, today):
                upcoming.append({**base, "date": d})
            time.sleep(0.12)
    upcoming.sort(key=lambda r: r["date"])
    votes.sort(key=lambda r: r["filed"], reverse=True)
    out = {"upcoming": upcoming, "votes": votes}
    if cache_path:
        json.dump(out, open(cache_path, "w"), indent=1)
    return out


def render(data: dict, today: dt.date, horizon: int = 120,
           vote_days: int = 120) -> str:
    L = ["▎ADVISORY COMMITTEES — where the uncertainty resolves before the PDUFA"]
    up = [u for u in data.get("upcoming", [])
          if 0 <= (dt.date.fromisoformat(u["date"]) - today).days <= horizon]
    for u in up:
        d = (dt.date.fromisoformat(u["date"]) - today).days
        L.append(f"   SCHEDULED  {u['date']}  ({d:>3}d)  {u['ticker'] or '?':<6} "
                 f"{u['company'][:34]}")
    recent = [v for v in data.get("votes", [])
              if v["filed"] and (today - dt.date.fromisoformat(v["filed"])).days
              <= vote_days]
    for v in recent:
        tal = f" {v['tally'][0]}-{v['tally'][1]}" if v.get("tally") else ""
        mark = {"favourable": "  ", "unfavourable": "⚠ "}.get(v["direction"], "? ")
        L.append(f"   {mark}VOTED{tal}  {v['filed']}  {v['ticker'] or '?':<6} "
                 f"{v['direction'].upper()}")
        if v["direction"] == "unclear" and v.get("sentence"):
            L.append(f"        language ambiguous — read it: \"{v['sentence'][:150]}\"")
    if len(L) == 1:
        L.append("   none scheduled or voted in the window")
    else:
        L.append("   ── the FDA is NOT bound by these votes, and no probability")
        L.append("      of approval is derived from them here.")
    return "\n".join(L)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--months-back", type=int, default=6)
    ap.add_argument("--horizon", type=int, default=120)
    ap.add_argument("--cache", default=os.path.join(SCRATCH, "adcom.json"))
    a = ap.parse_args(argv)
    today = dt.date.today()
    print(render(build(a.months_back, today, a.cache), today, a.horizon))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
