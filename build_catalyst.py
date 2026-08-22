#!/usr/bin/env python3
"""
build_catalyst.py — a survivorship-free FDA catalyst dataset from FREE sources.

THE PROBLEM WITH BUYING THIS DATA, and why the free route is not a compromise.
Commercial catalyst calendars are built from today's tickers. Biotechs that took
a Complete Response Letter and died are gone from those lists, so a backtest
built on them is missing precisely the outcomes that bankrupt people. Day-40
caught a milder version of this in the TSX universe and it still distorted every
absolute number.

EDGAR does not forget. A company that delisted in 2016 still has every 8-K it
ever filed, indexed and full-text searchable. That makes SEC full-text search
the PRIMARY source for this question and arguably better than a paid feed:

  CRL events        8-K containing "complete response letter". A CRL is a
                    material event, so a listed issuer must disclose it. The
                    FDA itself never publishes CRLs — they are confidential by
                    statute — so the issuer's own 8-K is the only public record
                    and EDGAR is where it lives forever.
  APPROVAL events   8-K containing approval language. Cross-checkable against
                    openFDA's Drugs@FDA, which is free and authoritative for
                    approvals (but, again, silent on rejections).

Both sides filtered to pharma/biotech SIC codes (2833-2836 pharmaceutical and
biological products, 8731 commercial research) so that "complete response
letter" in an unrelated context does not enter the sample.

THE HONEST WEAK LINK is the ticker, not the event. EDGAR keys on CIK; the
submissions API returns an EMPTY ticker list for delisted registrants (verified:
Repros Therapeutics, CIK 897075, delisted, tickers []). So events are captured
survivorship-free while PRICES may not be, which would reintroduce the bias at
the last step. This script therefore resolves tickers by three routes and
REPORTS the coverage rather than quietly dropping what it cannot map — an
unmappable event is recorded with a blank ticker so the size of the hole stays
visible in the output.

Rate limits: SEC asks for <10 requests/second and a descriptive User-Agent.
This stays well under that and caches everything to disk, so a re-run is free.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from validate_exit import SCRATCH  # noqa: E402


def _strip(raw: bytes, cap: int = 400_000) -> str:
    t = raw[:cap].decode("utf8", "replace")
    t = re.sub(r"<[^>]+>", " ", t)
    return re.sub(r"\s+", " ", t)

UA = {"User-Agent": "RB-research/1.0 (non-commercial backtest)",
      "Accept": "application/json"}
FTS = "https://efts.sec.gov/LATEST/search-index"
# 2833-2836 pharma/biological, 8731 commercial physical & biological research
BIO_SIC = {"2833", "2834", "2835", "2836", "8731"}
# DAY-66: search ANNOUNCEMENT phrasing, not the bare noun. The bare noun
# returned 4,463 matches of which most were retrospective mentions, and
# day-56 measured the result: event windows were indistinguishable from
# random ones. Each hit is then classified by classify.py, which fails
# closed toward "mention".
# ARCHITECTURE: BROAD SEARCH, STRICT CLASSIFIER. A first attempt narrowed the
# SEARCH to one announcement phrasing and returned 22 CRLs and ZERO approvals
# over five years -- trading contamination for sample starvation, which is just
# a different way to have no study. Recall belongs at the search stage and
# precision at the filter, so every plausible phrasing is queried and
# classify.py decides. Hits overlap heavily; (cik, date) de-duplicates them.
PHRASES = {
    "CRL": ['"received a Complete Response Letter"',
            '"Complete Response Letter from the U.S. Food and Drug Administration"',
            '"issued a Complete Response Letter"',
            '"receipt of a Complete Response Letter"'],
    "APPROVAL": ['"approved by the U.S. Food and Drug Administration"',
                 '"FDA has approved"',
                 '"announced FDA approval"',
                 '"received FDA approval"',
                 '"U.S. Food and Drug Administration has approved"'],
}


def _get(url: str, tries: int = 4) -> bytes:
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers=UA)
            return urllib.request.urlopen(req, timeout=60).read()
        except Exception:
            if i == tries - 1:
                raise
            time.sleep(2 ** i)
    raise RuntimeError("unreachable")


def search_year(phrase: str, year: int, page_size: int = 100) -> list:
    """All 8-K hits for a phrase in one calendar year.

    Chunked by year because EDGAR's full-text index caps how deep `from` may
    page; a year of one phrase stays comfortably inside it.
    """
    out, frm = [], 0
    while True:
        u = (f"{FTS}?q={urllib.parse.quote(phrase)}&forms=8-K"
             f"&startdt={year}-01-01&enddt={year}-12-31&from={frm}")
        d = json.loads(_get(u))
        hits = d.get("hits", {}).get("hits", [])
        total = d.get("hits", {}).get("total", {}).get("value", 0)
        out += hits
        frm += len(hits)
        if not hits or frm >= min(total, 9000):
            return out
        time.sleep(0.15)


def rows_from_hits(hits: list, kind: str, verify: bool = False,
                   stats: dict | None = None) -> list:
    """One row per (cik, date) — a filing may index several documents.

    With `verify`, each candidate's full text is classified (day-66) and only
    ANNOUNCEMENTS survive. Slower by one fetch per hit, and the reason the
    resulting labels mean anything.
    """
    seen, rows = set(), []
    stats = stats if stats is not None else {}
    for h in hits:
        s = h.get("_source", {})
        sic = (s.get("sics") or [""])[0]
        if sic not in BIO_SIC:
            continue
        cik = (s.get("ciks") or [""])[0]
        date = s.get("file_date")
        if not cik or not date or (cik, date) in seen:
            continue
        seen.add((cik, date))
        if verify:
            import classify
            try:
                txt = _strip(_get(f"https://www.sec.gov/Archives/edgar/data/"
                                  f"{cik.lstrip('0')}/{s.get('adsh','')}.txt"))
            except Exception as e:
                stats[f"fetch:{type(e).__name__}"] = stats.get(
                    f"fetch:{type(e).__name__}", 0) + 1
                continue
            fn = (classify.classify_crl if kind == "CRL"
                  else classify.classify_approval)
            ok, why = fn(txt, date)
            if not ok:
                stats[why[:38]] = stats.get(why[:38], 0) + 1
                continue
            time.sleep(0.12)
        name = (s.get("display_names") or [""])[0]
        rows.append({"kind": kind, "cik": cik.lstrip("0"), "date": date,
                     "name": re.sub(r"\s*\(CIK.*", "", name).strip(),
                     "sic": sic, "accession": s.get("adsh", ""), "ticker": ""})
    return rows


def ticker_map(cache: str) -> dict:
    """CIK -> ticker for CURRENT registrants (SEC's own file). Delisted names
    are absent by construction — that gap is the whole point of measuring
    coverage rather than assuming it."""
    p = os.path.join(cache, "cik_tickers.json")
    if not os.path.exists(p):
        d = json.loads(_get("https://www.sec.gov/files/company_tickers.json"))
        m = {str(v["cik_str"]): v["ticker"] for v in d.values()}
        json.dump(m, open(p, "w"))
    return json.load(open(p))


TICK_RE = re.compile(
    r"\((?:the\s+)?(?:Nasdaq|NASDAQ|NYSE|NYSE\s+American|NYSE\s+MKT|AMEX|OTCQB|"
    r"OTC\s+Markets)[^)]{0,30}?:\s*([A-Z]{1,5})\s*\)")


def ticker_from_filing(cik: str, accession: str, cache: dict,
                       stats: dict) -> str:
    """Last resort for a delisted issuer: read the FULL SUBMISSION text.

    First attempt read the `-index.htm` page for a 'Trading Symbol' cell and
    recovered ZERO from 2,214 filings. Two reasons, both worth recording:

      1. `Accept: application/json` is MANDATORY on sec.gov — without it every
         request returns 403 regardless of User-Agent. Verified by isolation.
      2. Even served correctly, the index page carries no ticker, and the
         structured `dei:TradingSymbol` cover-page tag only exists from ~2019,
         so it is absent for exactly the older delisted names that matter most.

    What DOES work across the whole period is the press release inside the
    submission: biotech 8-Ks almost always write "(Nasdaq: RPRX)" in the
    boilerplate. Verified on Repros Therapeutics (delisted, 2015) -> RPRX.

    A partner company named in the same release can also match, so the FIRST
    occurrence is taken — the filer's own identifier appears in the dateline
    before any partner is discussed. Failures are COUNTED, never swallowed:
    2,214 silent 403s are what hid the bug the first time (the day-29 rule).
    """
    key = f"{cik}:{accession}"
    if key in cache:
        return cache[key]
    tick = ""
    try:
        raw = _get(f"https://www.sec.gov/Archives/edgar/data/{cik}/"
                   f"{accession}.txt")[:400_000]
        m = TICK_RE.search(raw.decode("utf8", "replace"))
        if m:
            tick = m.group(1)
        else:
            stats["no_match"] = stats.get("no_match", 0) + 1
    except Exception as e:
        stats[type(e).__name__] = stats.get(type(e).__name__, 0) + 1
    cache[key] = tick
    time.sleep(0.12)
    return tick


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", type=int, default=2004)
    ap.add_argument("--end", type=int, default=2026)
    ap.add_argument("--cache", default=SCRATCH)
    ap.add_argument("--resolve-delisted", action="store_true",
                    help="fetch cover pages for CIKs the SEC ticker file misses")
    a = ap.parse_args(argv)
    os.makedirs(a.cache, exist_ok=True)
    out_path = os.path.join(a.cache, "catalyst_events.csv")

    rows, reasons = [], {}
    for kind, phrases in PHRASES.items():
        for y in range(a.start, a.end + 1):
            hits = []
            for phrase in phrases:
                try:
                    hits += search_year(phrase, y)
                except Exception as e:
                    print(f"  {kind} {y} [{phrase[:28]}]: FAILED "
                          f"({type(e).__name__})", flush=True)
            seen_here = set()
            uniq = []
            for h in hits:
                k = h.get("_source", {}).get("adsh", "")
                if k and k not in seen_here:
                    seen_here.add(k)
                    uniq.append(h)
            r = rows_from_hits(uniq, kind, verify=True, stats=reasons)
            rows += r
            print(f"  {kind} {y}: {len(uniq):>4} unique hits -> {len(r):>3} "
                  "verified events", flush=True)

    if reasons:
        print("\nrejected by the announcement classifier:")
        for k, v in sorted(reasons.items(), key=lambda x: -x[1])[:8]:
            print(f"    {v:>5}  {k}")
    tm = ticker_map(a.cache)
    fcache: dict = {}
    hit = 0
    for r in rows:
        r["ticker"] = tm.get(r["cik"], "")
        if r["ticker"]:
            hit += 1
    print(f"\nticker resolved from SEC current-registrant file: "
          f"{hit}/{len(rows)} ({hit/max(len(rows),1):.0%})")

    if a.resolve_delisted:
        miss = [r for r in rows if not r["ticker"]]
        stats: dict = {}
        print(f"resolving {len(miss)} unmapped (likely delisted) from filings...")
        for i, r in enumerate(miss, 1):
            r["ticker"] = ticker_from_filing(r["cik"], r["accession"], fcache, stats)
            if i % 200 == 0:
                got = sum(1 for x in miss if x["ticker"])
                print(f"    {i}/{len(miss)}  recovered {got}", flush=True)
        hit2 = sum(1 for r in rows if r["ticker"])
        print(f"ticker resolved after filing pass: {hit2}/{len(rows)} "
              f"({hit2/max(len(rows),1):.0%})")
        if stats:
            print(f"  unresolved breakdown: {stats}")

    with open(out_path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["kind", "cik", "date", "name", "sic",
                                          "accession", "ticker"])
        w.writeheader()
        w.writerows(sorted(rows, key=lambda r: (r["date"], r["cik"])))
    n_crl = sum(1 for r in rows if r["kind"] == "CRL")
    print(f"\nwrote {len(rows):,} events ({n_crl} CRL / {len(rows)-n_crl} approval) "
          f"-> {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
