#!/usr/bin/env python3
"""
sixk.py — the one thing day-70 measured about the intraday universe.

WHAT WAS MEASURED (validate_sixk.py, 52,919 rows across 78 cross-listed TSX
names, session-clustered bootstrap, positive control passing, placebo at
z=+0.72):

    the session AFTER a 6-K filing
      continues the morning move    48.43%  vs  48.66%   -0.23pp, z=-0.28
      moves further, either way      1.11%  vs   0.97%   +0.140pp, z=+6.35

Direction: nothing, and that is rejection #36. Magnitude: wider, comfortably
past the bar. A name that filed yesterday hands you the same coin flip with a
bigger stake on it — more risk at no more edge, which is not a neutral change,
it is strictly a worse bet.

SO THIS WARNS AND NEVER BLOCKS, for the same reason `earnings.py` does. The
engine's direction call is a coin flip whatever this says (AUC 0.5022 on
122,234 rows), so no flag here rescues a pick; what it can do is tell a reader
that today's pick sits in the wider half of the distribution before they size
it. Sizing is the reader's decision and this module does not make it.

THE LOOKUP IS GUARDED, because the obvious version of it is wrong. Matching
TSX tickers to SEC CIKs by root symbol silently matches other companies —
AC.TO to Associated Capital, ARE.TO to Alexandria Real Estate, CCO.TO to Clear
Channel. Any filer that has never submitted a 40-F or a 6-K is rejected: MJDS
is how Canadian issuers report, and a US domestic filer never uses it. Thirty
-two false matches were caught by that one rule in the validation run.

FAIL CLOSED. A name whose CIK cannot be resolved is reported as UNCHECKED, not
as clean. The whole point of the flag is that absence of a filing and absence
of a lookup are different things.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sys
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from validate_exit import SCRATCH  # noqa: E402

H = {"User-Agent": "RB-research/1.0 (non-commercial)",
     "Accept": "application/json"}          # 403 without the Accept header
CACHE = os.path.join(SCRATCH, "sixk_map.json")
# MEASURED, day-70. Kept here so the report cannot quote a number the
# validation did not produce.
WIDER_PP, WIDER_Z = 0.140, 6.35
DIR_PP, DIR_Z = -0.23, -0.28
N_ROWS, N_NAMES = 52919, 78


def root(ticker: str) -> str:
    """TSX suffixes and unit/class markers off; the SEC lists the root symbol."""
    r = ticker.replace(".TO", "").replace(".V", "")
    for suffix in ("-UN", "-X", "-A", "-B"):
        r = r.replace(suffix, "")
    return r


def _get(url: str, timeout: int = 30) -> dict:
    return json.loads(urllib.request.urlopen(
        urllib.request.Request(url, headers=H), timeout=timeout).read())


TICKERS = os.path.join(SCRATCH, "sec_ticker_cik.json")


def us_ticker_map(path: str = TICKERS) -> dict:
    """ticker -> CIK, keeping EVERY ticker a filer lists.

    WHY THIS DOES NOT REUSE build_catalyst.ticker_map, which already reads the
    same SEC file. That one builds CIK -> ticker, one entry per filer, and the
    SEC's file has one row per SECURITY: Royal Bank lists common and several
    preferred series under a single CIK, so the dict collapses them and
    whichever row came last wins. 7,998 tickers survived out of roughly ten
    thousand, and the casualties included RY, TD, ENB and ABX — four of the
    largest cross-listed names on the exchange this engine trades.

    Inverting a lossy map does not recover what it lost, so this reads the
    source file itself and keys by ticker, where every row is distinct.
    """
    if not os.path.exists(path):
        d = _get("https://www.sec.gov/files/company_tickers.json")
        m = {v["ticker"]: str(v["cik_str"]) for v in d.values()}
        json.dump(m, open(path, "w"))
    return json.load(open(path))


def submissions(cik: str) -> dict:
    return _get(f"https://data.sec.gov/submissions/CIK{int(cik):010d}.json")


def is_canadian_filer(sub: dict) -> bool:
    """Has this filer ever used MJDS? A US domestic filer never has.

    This is the whole guard, and it is worth more than it looks: it is the
    difference between Cameco's filing history and Clear Channel Outdoor's.
    """
    forms = sub.get("filings", {}).get("recent", {}).get("form", [])
    return any(f == "40-F" or f.startswith("6-K") for f in forms)


def filings_since(sub: dict, since: str) -> list:
    rec = sub.get("filings", {}).get("recent", {})
    return sorted(d for f, d in zip(rec.get("form", []),
                                    rec.get("filingDate", []))
                  if f.startswith("6-K") and d >= since)


def load_map(path: str = CACHE) -> dict:
    return json.load(open(path)) if os.path.exists(path) else {}


def resolve(ticker: str, cik_map: dict, cache: dict) -> tuple:
    """(cik, status). status is 'ok', 'not-canadian', 'no-cik' or an error name."""
    if ticker in cache:
        c = cache[ticker]
        return c.get("cik"), c.get("status")
    cik = cik_map.get(root(ticker))
    if not cik:
        cache[ticker] = {"cik": None, "status": "no-cik"}
        return None, "no-cik"
    try:
        sub = submissions(cik)
    except Exception as e:
        return None, type(e).__name__          # NOT cached: a transient error
    status = "ok" if is_canadian_filer(sub) else "not-canadian"
    cache[ticker] = {"cik": cik, "status": status, "name": sub.get("name")}
    return (cik if status == "ok" else None), status


def flag(ticker: str, today: dt.date, cik_map: dict, cache: dict,
         lookback: int = 4) -> dict:
    """Did this name file a 6-K recently enough to matter for today's leg?

    `lookback` covers a long weekend: the measurement is about the FIRST
    session after a filing, and Friday's filing reaches Monday's open.
    """
    cik, status = resolve(ticker, cik_map, cache)
    if status != "ok":
        return {"ticker": ticker, "status": status, "dates": []}
    since = (today - dt.timedelta(days=lookback)).isoformat()
    try:
        dates = [d for d in filings_since(submissions(cik), since)
                 if d < today.isoformat()]
    except Exception as e:
        return {"ticker": ticker, "status": type(e).__name__, "dates": []}
    return {"ticker": ticker, "status": "ok", "dates": dates}


def render(flags: list, today: dt.date) -> list:
    """Report lines. Silent only when every name was checked and found clean."""
    hits = [f for f in flags if f["dates"]]
    unchecked = [f for f in flags
                 if f["status"] not in ("ok", "no-cik", "not-canadian")]
    L = []
    for f in hits:
        L.append(f"   ⚠ {f['ticker']} filed a 6-K on {', '.join(f['dates'])} — "
                 "MEASURED (day-70): the session after")
        L.append(f"     a filing moves {WIDER_PP:+.3f}pp further either way "
                 f"(z={WIDER_Z:+.2f}, n={N_ROWS:,} rows / {N_NAMES} names)")
        L.append(f"     and is NO more predictable in direction ({DIR_PP:+.2f}pp, "
                 f"z={DIR_Z:+.2f}). Same coin,")
        L.append("     bigger stake. Size it accordingly; nothing here blocks "
                 "the pick.")
    for f in unchecked:
        L.append(f"   ⚠ {f['ticker']} could NOT be checked for filings "
                 f"({f['status']}) — UNCHECKED is not clean")
    return L


def check(tickers: list, today: dt.date | None = None,
          cache_path: str = CACHE) -> list:
    today = today or dt.date.today()
    cik_map = us_ticker_map()
    cache = load_map(cache_path)
    out = [flag(t, today, cik_map, cache) for t in tickers]
    try:
        json.dump(cache, open(cache_path, "w"))
    except Exception:
        pass
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("tickers", nargs="+")
    a = ap.parse_args(argv)
    lines = render(check(a.tickers), dt.date.today())
    print("\n".join(lines) if lines else
          "   no recent 6-K filings for the names checked")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
