#!/usr/bin/env python3
"""Cost diagnostics on the shared validated market-data layer.

Prior tests did not demonstrate a directional edge; they do not prove that
accuracy can never improve. This module preserves baseline selection and
reports spread drag. Entry spread is only a same-spread-at-exit estimate.
Exact-window research in execution.py requires both observed BBOs, fees,
slippage, and short borrow. Missing data never implies zero transaction cost.
"""

from __future__ import annotations

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
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


from quotes import (YahooMarketData as Quotes, two_sided, number, validate_equity,
                    market_client, fetch_equities, quote_failure)


def spread_bps(row: dict) -> float | None:
    """Quoted spread in basis points of the mid. None when not two-sided.

    A one-sided or missing quote is reported as unknown, never as zero. Zero is
    the single most expensive wrong answer available here: it would say the
    trade is free.
    """
    bbo = two_sided(row)
    if not bbo:
        return None
    b, a = bbo
    return (a - b) / ((a + b) / 2) * 10000


def drag(spread: float | None, shares: float | None,
         price: float | None) -> dict:
    """Same-entry/exit-spread proxy in quote currency and share of typical move.

    Two marketable crossings pay half a spread each. The exit spread is not
    known at entry, so this estimate cannot stand in for observed execution.
    The historical key ``usd`` is retained for compatibility; TSX quotes are CAD.
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
    """Equal-payoff diagnostic: (2*p-1)*move, not an expected-return estimate.

    Hit rate alone does not determine P&L when win/loss magnitudes differ.
    ``move_pct`` is a historical median, not conditional mean payoff evidence.
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
    except Exception as exc:
        __import__("logging").getLogger(__name__).warning("Live cost record unavailable: %s", type(exc).__name__)
    return 0, 0


def outside_trading_hours(now=None) -> bool:
    """Is this run outside 09:30-16:00 ET on a weekday?

    A spread quoted after the close is the last posted bid/ask, which is far
    wider than anything tradeable — on 2026-09-04 the same two-leg book costed
    $24.39 at 09:46 and $94 at 17:33. Printing the second as though it were the
    first tells the reader the book is four times more expensive to express
    than it is.

    This detects HOURS, not holidays: a weekday holiday reads as open and its
    spreads will be stale. It is a label on a number, never a gate on an
    action, so the failure mode is a missing warning rather than a blocked
    order.
    """
    import datetime as _dt
    try:
        from zoneinfo import ZoneInfo
        now = now or _dt.datetime.now(ZoneInfo("America/New_York"))
        if now.tzinfo is None:
            now = now.replace(tzinfo=ZoneInfo("America/New_York"))
        else:
            now = now.astimezone(ZoneInfo("America/New_York"))
    except Exception as exc:
        __import__('logging').getLogger(__name__).warning('Trading clock unavailable: %s', type(exc).__name__)
        return True
    if now.weekday() >= 5:
        return True
    m = now.hour * 60 + now.minute
    return not (9 * 60 + 30 <= m < 16 * 60)


def assess(picks: list, now=None, client=None) -> list:
    """Attach shared validated costs; injected/prepared feeds use the same path."""
    if not picks:
        return []
    import datetime as dt
    from zoneinfo import ZoneInfo
    now = now or dt.datetime.now(ZoneInfo('America/New_York'))
    tickers = [p['ticker'] for p in picks]
    try:
        rows = fetch_equities(client or market_client(), tickers, now)
    except Exception as exc:
        rows = {t:quote_failure(t, exc) for t in tickers}
    out = []
    for p in picks:
        r = rows[p['ticker']]
        out.append({**p, 'cost': drag(r['spread_bps'], p.get('shares'), p.get('price')),
                    'bid': r['bid'], 'ask': r['ask'], 'status': r['status'],
                    'reason_code':r.get('reason_code'), 'error_class':r.get('error_class'),
                    'error': None if r['status']=='OK' else r['reason']})
    return out


def render(rows: list, record=None) -> list:
    if not rows:
        return []
    record = record or {}
    hits, n = record.get("pair_hits", 0), record.get("pair_n", 0)
    e = edge_bps(hits, n)
    L = ["   ── COST TO EXPRESS — same-spread-at-exit estimate"]
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
        L.append(f"      equal-payoff diagnostic at the supplied record ({hits}/{n}): "
                 f"{e:+.0f} bps per leg")
        L.append(f"      spread term: -{sum(r['cost']['bps'] for r in known)/len(known):.0f}"
                 " bps per leg, assuming the same spread at exit")
        if total:
            L.append(f"      so today's pair starts ~${total:,.0f} behind "
                     "before the market moves at all.")
        L.append("      This is arithmetic, not a forecast. Hit rate alone does not determine P&L;")
        L.append("      win/loss magnitudes and actual execution costs are required.")
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
