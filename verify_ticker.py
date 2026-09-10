#!/usr/bin/env python3
"""verify_ticker.py — does this symbol exist, and is it the company you meant?

WHY THIS EXISTS. On 2026-09-10 an outside source recommended shorting
"RBC.TO". There is no such listing: Royal Bank of Canada trades as RY.TO, and
RBC.TO returns HTTP 404. An order for it would simply be rejected — but the
worse case is the one that does NOT fail, and this repo has hit it twice:

  * `GOLD` is Gold.com Inc, not Barrick. Reaching for it during a day-84
    feasibility probe returned a real, live, wrong company (dtc 8.00 against
    Barrick's true 1.70) with no error at all.
  * `T` is AT&T, not TELUS. `build_social.EXPECTED_ISSUER` exists solely to
    catch that one, and it does.

A ticker is not a company. A symbol that resolves is not a symbol that
resolves to what you meant, and the difference is silent. So this checks BOTH:
that the venue knows the symbol, and — when you say who you expect — that the
name it returns is that issuer.

    python verify_ticker.py RBC.TO RY.TO TRP.TO
    python verify_ticker.py --expect ABX.TO=barrick GOLD=barrick

Read-only. Places no order, writes no state.
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.parse
import urllib.request

CHART = ("https://query2.finance.yahoo.com/v8/finance/chart/{t}"
         "?interval=1d&range=5d")
UA = {"User-Agent": "Mozilla/5.0", "Accept": "application/json"}

OK = "OK"
NOT_FOUND = "NOT_FOUND"            # the venue has no such symbol
WRONG_ISSUER = "WRONG_ISSUER"      # it resolves — to someone else
NO_PRICE = "NO_PRICE"              # listed but not currently priced
LOOKUP_FAILED = "LOOKUP_FAILED"    # transport failed; UNKNOWN, never OK


def lookup(symbol: str, timeout: float = 20.0) -> dict:
    """Ask the venue. Transport failures are reported, never downgraded to
    'not found' — 'I could not check' and 'it does not exist' are different
    answers and only one of them is safe to act on (rule 1)."""
    url = CHART.format(t=urllib.parse.quote(symbol, safe=""))
    try:
        raw = urllib.request.urlopen(
            urllib.request.Request(url, headers=UA), timeout=timeout).read()
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            return {"status": NOT_FOUND, "detail": "venue returned HTTP 404"}
        return {"status": LOOKUP_FAILED, "detail": f"HTTP {exc.code}"}
    except (urllib.error.URLError, TimeoutError) as exc:
        return {"status": LOOKUP_FAILED, "detail": type(exc).__name__}
    try:
        payload = json.loads(raw)
    except ValueError:
        return {"status": LOOKUP_FAILED, "detail": "unparseable response"}

    chart = payload.get("chart") or {}
    if chart.get("error"):
        code = (chart["error"] or {}).get("code", "")
        status = NOT_FOUND if "NotFound" in str(code) else LOOKUP_FAILED
        return {"status": status, "detail": str(code)}
    result = (chart.get("result") or [{}])[0]
    meta = result.get("meta") or {}
    returned = meta.get("symbol")
    if not returned:
        return {"status": NOT_FOUND, "detail": "no symbol in response"}
    price = meta.get("regularMarketPrice")
    return {"status": OK if price is not None else NO_PRICE,
            "symbol": returned,
            "redirected": returned.upper() != symbol.upper(),
            "name": meta.get("longName") or meta.get("shortName"),
            "currency": meta.get("currency"),
            "exchange": meta.get("fullExchangeName"),
            "price": price}


def check(symbol: str, expect: str | None = None, timeout: float = 20.0) -> dict:
    out = {"asked": symbol, **lookup(symbol, timeout)}
    if out["status"] in (OK, NO_PRICE) and expect:
        name = (out.get("name") or "").lower()
        if expect.lower() not in name:
            out["status"] = WRONG_ISSUER
            out["detail"] = (f"resolves to {out.get('name')!r}, which does not "
                             f"match expected issuer {expect!r}")
    return out


def line(r: dict) -> str:
    s = r["status"]
    if s in (OK, NO_PRICE):
        redirect = f"  (venue answered {r['symbol']})" if r.get("redirected") else ""
        price = f"{r['price']}" if r.get("price") is not None else "unpriced"
        return (f"  {r['asked']:10s} {s:12s} {r.get('name') or '?'} "
                f"[{r.get('exchange')}, {r.get('currency')}] {price}{redirect}")
    return f"  {r['asked']:10s} {s:12s} {r.get('detail', '')}"


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("symbols", nargs="*", help="tickers to verify")
    p.add_argument("--expect", action="append", default=[],
                   metavar="SYM=name-fragment",
                   help="also require the resolved name to contain a fragment")
    p.add_argument("--json", action="store_true")
    a = p.parse_args(argv)

    expects = {}
    for pair in a.expect:
        sym, _, frag = pair.partition("=")
        expects[sym.upper()] = frag
        if sym.upper() not in [s.upper() for s in a.symbols]:
            a.symbols.append(sym)
    if not a.symbols:
        p.error("give at least one symbol")

    results = [check(s, expects.get(s.upper())) for s in a.symbols]
    if a.json:
        print(json.dumps(results, indent=2))
    else:
        for r in results:
            print(line(r))
    bad = [r for r in results if r["status"] != OK]
    if bad:
        print(f"\n  {len(bad)} of {len(results)} did NOT verify clean — "
              "do not act on those without resolving why.")
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
