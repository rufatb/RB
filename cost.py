#!/usr/bin/env python3
r"""
cost.py — what the intraday pair costs to express, which nobody has ever measured.

THE ARITHMETIC THIS REPO HAS BEEN AVOIDING. The intraday engine's direction call
is a coin flip and that is settled: AUC 0.5022 on 122,234 rows, 36 rejections, a
live record of 34/70. Every improvement effort has gone at the hit rate, and the
hit rate is not movable.

But a coin flip is not a zero-expectation trade. It is a NEGATIVE-expectation
trade, by exactly the amount it costs to get in and out:

    E[net] = (hit rate - 1/2) x 2 x E|move|  -  spread  -  fees
             \_______________________/
                    measured at ~0

With the directional term at zero, the spread is not a detail on top of the
edge. It IS the expected outcome. And `adapters.py` says in its own header that
bid/ask is not exposed by any adapter in this repo — so the one term that
actually determines the result of the intraday book has never appeared in the
morning report at all.

THE SIZE OF IT, against the only comparable this repo has measured. Day-70 put
the typical TSX leg at |r1| ~ 1.0%. A 25bp round-trip spread is a quarter of
that gross move, taken with certainty, on both legs, every day. Over the 70
scored legs that is a materially different result from "a coin flip", and it is
the difference between a strategy that is merely useless and one that is
expensive.

WHAT THIS DOES AND DOES NOT DO. It measures and reports. It does NOT re-rank the
picks: the engine's selection rule produced the 70-leg record, and silently
changing the rule would break the only track record this repo has while
pretending to improve it. Where a cheaper name was available at the same
sided-P, that is said out loud and left to the reader.

Everything here is a live quote at pick time. There is no historical spread
series available free, so this cannot be backtested and is not presented as an
improvement to anything — it is a cost that was always being paid and never
shown.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120 Safari/537.36")
H = {"User-Agent": UA, "Accept": "application/json,text/plain,*/*"}
# Day-87 (DECISION_day87.md): re-derived from the LEDGER at 0.69% [0.59, 0.80],
# median |capture| over 363 scored legs / 41 sessions, session-clustered.
#
# It replaces day-70's 0.97%, which measured |r1| across the whole 21-name
# UNIVERSE. That is the wrong population for this constant, and the reason is
# rule 7 rather than a judgement about which study was better run: this number
# is a DENOMINATOR whose numerators are a pick's spread and the picks' own hit
# rate, so it has to describe picks. Selection is not neutral with respect to
# volatility (day-47: the density tag sorts by volatility), so universe prints
# are not a stand-in for selected legs.
#
# The correction goes AGAINST us. Too large a denominator makes the spread look
# like a smaller share of a normal day than it is, so every cost line printed
# before today UNDERSTATED the drag: a 5bp spread read as 5.2% of a typical
# move and is really 7.2%.
TYPICAL_MOVE_PCT = 0.69
# The live record. Kept here so no line can quote an edge the ledger does not
# show; refreshed from ledger.py when it is available.
FALLBACK_HITS, FALLBACK_N = 34, 70


class Quotes:
    """Yahoo quote endpoint — the same cookie+crumb dance screen.py needs."""

    def __init__(self):
        import http.cookiejar
        self.op = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
        self.crumb = None

    def _get(self, url: str) -> bytes:
        return self.op.open(urllib.request.Request(url, headers=H),
                            timeout=30).read()

    def auth(self) -> None:
        if self.crumb:
            return
        try:
            self._get("https://fc.yahoo.com")
        except Exception:
            pass
        self.crumb = self._get(
            "https://query2.finance.yahoo.com/v1/test/getcrumb").decode()

    def get(self, tickers: list) -> dict:
        self.auth()
        u = ("https://query1.finance.yahoo.com/v7/finance/quote?symbols="
             + ",".join(tickers) + f"&crumb={self.crumb}")
        d = json.loads(self._get(u))
        return {r["symbol"]: r
                for r in d.get("quoteResponse", {}).get("result", [])}


def spread_bps(row: dict) -> float | None:
    """Quoted spread in basis points of the mid. None when not two-sided.

    A one-sided or missing quote is reported as unknown, never as zero. Zero is
    the single most expensive wrong answer available here: it would say the
    trade is free.
    """
    b, a = row.get("bid"), row.get("ask")
    if not b or not a or a <= 0 or b <= 0 or a < b:
        return None
    mid = (a + b) / 2
    return (a - b) / mid * 10000 if mid else None


def drag(spread: float | None, shares: float | None,
         price: float | None) -> dict:
    """Round-trip cost in dollars and as a share of the typical move.

    ROUND TRIP, not one way. The strategy is flat by 15:55 every day, so both
    crossings are certain — there is no version of this trade that pays the
    spread once. Half-spread each way, twice, is one full spread.
    """
    out = {"bps": spread, "usd": None, "share_of_move": None}
    if spread is None:
        return out
    out["share_of_move"] = spread / 100 / TYPICAL_MOVE_PCT
    if shares and price:
        out["usd"] = spread / 10000 * float(shares) * float(price)
    return out


def edge_bps(hits: int = FALLBACK_HITS, n: int = FALLBACK_N,
             move_pct: float = TYPICAL_MOVE_PCT) -> float:
    """The directional term, in the same units as the spread.

    (p - 1/2) x 2 x E|move|. At 34/70 this is NEGATIVE before any cost, which
    is worth stating in the same breath as the spread rather than rounding to
    'a coin flip' — the record is what it is.
    """
    if not n:
        return 0.0
    return (hits / n - 0.5) * 2 * move_pct * 100


def live_record() -> tuple:
    try:
        import ledger
        s = ledger.live_summary(ledger.load()) or {}
        if s.get("pair_n"):
            return int(s["pair_hits"]), int(s["pair_n"])
    except Exception:
        pass
    return FALLBACK_HITS, FALLBACK_N


def assess(picks: list) -> list:
    """picks: [{ticker, shares, price}] -> the same rows with cost attached."""
    if not picks:
        return []
    q = Quotes()
    try:
        quotes = q.get([p["ticker"] for p in picks])
    except Exception as e:
        return [{**p, "cost": {"bps": None, "usd": None,
                               "share_of_move": None},
                 "error": type(e).__name__} for p in picks]
    out = []
    for p in picks:
        r = quotes.get(p["ticker"], {})
        s = spread_bps(r)
        out.append({**p, "cost": drag(s, p.get("shares"), p.get("price")),
                    "bid": r.get("bid"), "ask": r.get("ask")})
    return out


def render(rows: list) -> list:
    if not rows:
        return []
    hits, n = live_record()
    e = edge_bps(hits, n)
    L = ["   ── COST TO EXPRESS, which is the whole expected outcome here"]
    known = [r for r in rows if r["cost"]["bps"] is not None]
    total = sum(r["cost"]["usd"] or 0 for r in known)
    for r in rows:
        c = r["cost"]
        if c["bps"] is None:
            L.append(f"      {r['ticker']:<9} spread UNKNOWN — no two-sided "
                     "quote. Not zero: unknown.")
            continue
        usd = f"  ~${c['usd']:,.0f} round trip" if c["usd"] else ""
        L.append(f"      {r['ticker']:<9} spread {c['bps']:>5.0f} bps = "
                 f"{c['share_of_move']:>4.0%} of the typical "
                 f"{TYPICAL_MOVE_PCT:.2f}% move{usd}")
    if known:
        L.append(f"      directional term at the live record ({hits}/{n}): "
                 f"{e:+.0f} bps per leg")
        L.append(f"      spread term: -{sum(r['cost']['bps'] for r in known)/len(known):.0f}"
                 " bps per leg, paid with certainty on both crossings")
        if total:
            L.append(f"      so today's pair starts ~${total:,.0f} behind "
                     "before the market moves at all.")
        L.append("      This is arithmetic, not a forecast. The engine's edge "
                 "is measured at")
        L.append("      zero, so the spread is not a cost ON TOP of the edge — "
                 "it IS the outcome.")
    return L


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("tickers", nargs="+")
    ap.add_argument("--shares", type=float, default=None)
    ap.add_argument("--price", type=float, default=None)
    a = ap.parse_args(argv)
    rows = assess([{"ticker": t, "shares": a.shares, "price": a.price}
                   for t in a.tickers])
    print("\n".join(render(rows)) or "no quotes")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
