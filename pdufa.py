#!/usr/bin/env python3
"""
pdufa.py — a forward FDA decision calendar, built free from company filings.

WHERE THE DATES COME FROM. A PDUFA date is material, so when the FDA accepts a
filing the company says so in an 8-K: "...with a PDUFA date of January 29,
2027". EDGAR full-text search finds those sentences, which makes a forward
catalyst calendar obtainable for nothing. Verified on Praxis Precision
Medicines (PRAX), whose 8-K of 2026-08-06 yields two dates and this context:

    "PDUFA date of January 29, 2027. Mid-cycle meeting completed for
     relutrigine; FDA identified no major safety or efficacy concerns to date"

THE CONTEXT IS THE POINT, not a decoration. A bare date tells you when to be
nervous. The sentence around it is the company's own account of where the
review stands — mid-cycle meeting held, advisory committee scheduled or waived,
inspection outstanding, review extended three months. That is the raw material
for an approval probability, and it is the part a calendar-only product throws
away.

WHAT THIS IS NOT. It is not a probability, and nothing here estimates one. The
day-56 study established that this repo cannot yet identify catalyst OUTCOMES
reliably enough to backtest them, so any model that turned these sentences into
a number would be unvalidated. What the calendar CAN do is factual and useful
on its own: tell you what is scheduled, and let `catalyst.py` compute the
probability the market is already paying for.

BIAS TO KNOW ABOUT. Companies announce good news promptly and bad news slowly, and
a slipped or extended PDUFA may never be corrected in a later filing. So treat a
date as "last disclosed", not "confirmed", and re-check near the event. Dates
are reported with the filing that stated them so that check is one click away.
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

from validate_exit import SCRATCH  # noqa: E402

UA = {"User-Agent": "RB-research/1.0 (non-commercial)",
      "Accept": "application/json"}
FTS = "https://efts.sec.gov/LATEST/search-index"
PHRASE = '"PDUFA date of"'
BIO_SIC = {"2833", "2834", "2835", "2836", "8731"}

DATE_RE = re.compile(
    r"PDUFA\s+(?:target\s+)?(?:action\s+)?date\s+of\s+"
    r"([A-Z][a-z]+\s+\d{1,2},\s+\d{4})")
TICKER_RE = re.compile(r"\(([A-Z]{1,5})\)\s*$")
# phrases that tell you where a review actually stands
SIGNALS = [
    (r"[Aa]dvisory [Cc]ommittee", "AdCom mentioned"),
    # "does not plan to REQUEST an advisory committee meeting" is Praxis's
    # actual phrasing and the most natural one; covering only hold/convene
    # flagged that filing as "AdCom mentioned" — telling a reader a committee
    # review was coming when the FDA had said the opposite.
    (r"no.{0,20}[Aa]dvisory [Cc]ommittee"
     r"|do(?:es)? not (?:currently )?(?:plan|intend|expect) to "
     r"(?:hold|convene|request|schedule)"
     r"|no plans? to (?:hold|convene|request|schedule)",
     "AdCom NOT planned"),
    (r"[Mm]id-cycle", "mid-cycle meeting"),
    (r"[Pp]riority [Rr]eview", "priority review"),
    (r"[Ee]xtend(?:ed|ing) .{0,30}(?:three|3)[- ]month|extended the (?:review|PDUFA)",
     "review EXTENDED"),
    (r"[Cc]omplete [Rr]esponse [Ll]etter", "prior CRL"),
    (r"no major safety or efficacy concerns", "no major concerns flagged"),
    (r"[Ii]nspection", "inspection referenced"),
]


def _get(url: str, tries: int = 3) -> bytes:
    for i in range(tries):
        try:
            return urllib.request.urlopen(
                urllib.request.Request(url, headers=UA), timeout=60).read()
        except Exception:
            if i == tries - 1:
                raise
            time.sleep(2 ** i)
    raise RuntimeError("unreachable")


def strip_html(raw: bytes, cap: int = 400_000) -> str:
    t = raw[:cap].decode("utf8", "replace")
    t = re.sub(r"<[^>]+>", " ", t)
    t = t.replace("&#59;", ";").replace("&amp;", "&").replace("&nbsp;", " ")
    return re.sub(r"\s+", " ", t)


def parse_dates(text: str) -> list:
    """Unique PDUFA dates in disclosure order, ISO-formatted."""
    out = []
    for s in DATE_RE.findall(text):
        try:
            d = dt.datetime.strptime(s, "%B %d, %Y").date().isoformat()
        except ValueError:
            continue
        if d not in out:
            out.append(d)
    return out


def context_for(text: str, window: int = 220) -> str:
    """The sentence around the first PDUFA mention — the company's own account
    of where the review stands, which is the part worth reading."""
    m = DATE_RE.search(text)
    if not m:
        return ""
    a = max(0, m.start() - window // 2)
    return text[a:m.end() + window].strip()


def signals_near(text: str, date_str: str, radius: int = 900) -> list:
    """Signals attributed to ONE PDUFA date, not to the whole document.

    DAY-67. Praxis's 8-K of 2026-08-06 announces TWO decisions — relutrigine
    (27 Dec 2026) and ulixacaltamide (29 Jan 2027) — and the filing states that
    only RELUTRIGINE's review was extended, after the FDA deemed additional
    sensitivity analyses "a major amendment". Document-level attribution stamped
    "review EXTENDED" onto BOTH dates, telling a reader that a clean review had
    been extended when it had not.

    A sponsor with two programmes has two decisions, and a signal belongs to the
    one it is written next to. This scopes to a window around each mention of
    the date and falls back to the whole document only when the date is absent.
    """
    try:
        pretty = dt.date.fromisoformat(date_str).strftime("%B %-d, %Y")
    except (ValueError, TypeError):
        return review_signals(text)
    alt = pretty.replace(" 0", " ")
    idx = [m.start() for m in re.finditer(re.escape(pretty), text)]
    idx += [m.start() for m in re.finditer(re.escape(alt), text) if not idx]
    if not idx:
        return review_signals(text)
    seg = " ".join(text[max(0, i - radius):i + radius // 3] for i in idx)
    return review_signals(seg)


def review_signals(text: str) -> list:
    """Named review-status markers, de-duplicated, in a stable order."""
    out = []
    for pat, label in SIGNALS:
        if re.search(pat, text) and label not in out:
            out.append(label)
    # a negated AdCom supersedes the bare mention
    if "AdCom NOT planned" in out and "AdCom mentioned" in out:
        out.remove("AdCom mentioned")
    return out


def search(months_back: int = 8, today: dt.date | None = None) -> list:
    today = today or dt.date.today()
    start = (today - dt.timedelta(days=30 * months_back)).isoformat()
    u = (f"{FTS}?q={urllib.parse.quote(PHRASE)}&forms=8-K"
         f"&startdt={start}&enddt={today.isoformat()}")
    return json.loads(_get(u)).get("hits", {}).get("hits", [])


def build(months_back: int = 8, today: dt.date | None = None,
          cache_path: str | None = None) -> list:
    today = today or dt.date.today()
    hits, seen, out = search(months_back, today), set(), []
    for h in hits:
        s = h.get("_source", {})
        if (s.get("sics") or [""])[0] not in BIO_SIC:
            continue
        cik = (s.get("ciks") or [""])[0].lstrip("0")
        acc = s.get("adsh", "")
        if not cik or (cik, acc) in seen:
            continue
        seen.add((cik, acc))
        name = (s.get("display_names") or [""])[0]
        tm = TICKER_RE.search(re.sub(r"\s*\(CIK.*", "", name).strip())
        try:
            text = strip_html(_get(f"https://www.sec.gov/Archives/edgar/data/"
                                   f"{cik}/{acc}.txt"))
        except Exception:
            continue
        for d in parse_dates(text):
            if d <= today.isoformat():
                continue                     # already decided; not a calendar item
            out.append({
                "date": d, "ticker": tm.group(1) if tm else "",
                "company": re.sub(r"\s*\(.*", "", name).strip(),
                "filed": s.get("file_date", ""), "cik": cik, "accession": acc,
                "signals": signals_near(text, d), "context": context_for(text)})
        time.sleep(0.12)
    return dedupe(out, cache_path)


def dedupe(rows: list, cache_path: str | None = None) -> list:
    """One entry per (ticker, date), keeping the MOST RECENTLY FILED disclosure.

    A company restates the same PDUFA date across several 8-Ks, so the raw
    search returns JAZZ 2026-08-25 twice — once from a May filing and once from
    August. They are one decision. The later filing wins because a PDUFA date
    can be extended or moved, and the newest statement is the one still
    operative; keeping the older one would show a date the company has already
    superseded.

    Two DIFFERENT dates for one ticker are kept apart on purpose — a sponsor
    with two programmes genuinely has two decisions (IONS 09-22 and 10-26).
    """
    best: dict = {}
    for r in rows:
        k = (r["ticker"] or r["cik"], r["date"])
        cur = best.get(k)
        if cur is None or r.get("filed", "") > cur.get("filed", ""):
            if cur is not None:
                # keep the union of signals; a later filing may mention fewer
                r = dict(r)
                r["signals"] = sorted(set(r["signals"]) | set(cur["signals"]))
            best[k] = r
    out = sorted(best.values(), key=lambda r: r["date"])
    if cache_path:
        json.dump(out, open(cache_path, "w"), indent=1)
    return out


def render(cal: list, today: dt.date, horizon_days: int = 120) -> str:
    L = ["▎FDA DECISION CALENDAR — next %d days" % horizon_days]
    soon = [c for c in cal
            if 0 <= (dt.date.fromisoformat(c["date"]) - today).days <= horizon_days]
    if not soon:
        L.append("   nothing scheduled in the window (from company filings)")
        return "\n".join(L)
    for c in soon:
        d = (dt.date.fromisoformat(c["date"]) - today).days
        L.append(f"   {c['date']}  ({d:>3}d)  {c['ticker'] or '?':<6} "
                 f"{c['company'][:34]}")
        if c["signals"]:
            L.append(f"        review status: {', '.join(c['signals'])}")
        L.append(f"        disclosed {c['filed']} · last-disclosed date, "
                 "re-check near the event")
    L.append("   (dates are company disclosures, not FDA confirmations; no "
             "probability is implied)")
    return "\n".join(L)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--months-back", type=int, default=8)
    ap.add_argument("--horizon", type=int, default=180)
    ap.add_argument("--cache", default=os.path.join(SCRATCH, "pdufa_calendar.json"))
    a = ap.parse_args(argv)
    today = dt.date.today()
    cal = build(a.months_back, today, a.cache)
    print(render(cal, today, a.horizon))
    print(f"\n[{len(cal)} forward dates -> {a.cache}]")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
