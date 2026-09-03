#!/usr/bin/env python3
"""
validate_straddle.py — day-83. Can the ONE measured intraday signal be traded?

Pre-registered in PREREGISTER_day83.md before any result was computed.

THE ASYMMETRY THIS EXISTS FOR. Day-70 measured two things on the same rows:

    direction after a 6-K     z = +0.72     REJECTION #36
    magnitude |r1| after      z = +6.35     adopted, as a RISK WARNING

The engine can predict HOW FAR, not WHICH WAY. Expressed in shares that is the
worst possible combination — added variance against a coin-flip direction — and
day-70 correctly shipped it as a reason to size DOWN. An option expression
inverts the sign: direction stays a coin, magnitude becomes the payoff.

STAGE 1 IS COST, AND IT CAN END THE STUDY. A straddle crosses two spreads on
entry and two on exit. The share book died of spread after months of work on
direction; testing the cheapest decisive constraint FIRST is the lesson from
that. If the round trip costs more than half the measured magnitude lift, this
is written up REJECTED ON COST and there is no Stage 2.

THE FEED GATE IS NOT OPTIONAL. Yahoo zeroes bid/ask outside market hours — SPY's
at-the-money put quotes 0.00/0.00 pre-market, which computes to a spread of
ZERO. A cost study that runs then concludes trading is free, which is the most
flattering error available and the exact failure `quotes.py` was built to stop.
`cost_now()` refuses unless the control passes.
"""

from __future__ import annotations

import argparse
import datetime as dt
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import quotes as Q  # noqa: E402

# The US cross-listings of the intraday universe. `.TO` lines carry no listed
# options on this feed at all, which is why the expression has to move here.
US_LINES = {"SU.TO": "SU", "BMO.TO": "BMO", "RY.TO": "RY", "CNQ.TO": "CNQ",
            "TD.TO": "TD", "ENB.TO": "ENB", "BNS.TO": "BNS", "CM.TO": "CM",
            "CP.TO": "CP", "CNR.TO": "CNI", "BCE.TO": "BCE", "AC.TO": None,
            "CVE.TO": "CVE", "SLF.TO": "SLF", "T.TO": None}

MIN_OI = 100          # a chain thinner than this is not a market
COST_BAR_FRACTION = 0.5   # pre-registered: cost must be under half the lift


def _mid_spread(row: dict) -> tuple:
    """(mid, spread_pct_of_mid) for one contract, or (None, None).

    Refuses a one-sided quote. `lastPrice` is a historical fact that may not be
    a price at all — substituting it here is explicitly forbidden by the
    pre-registration, because it would silently turn an unquotable contract
    into a cheap one.
    """
    bid, ask = row.get("bid") or 0, row.get("ask") or 0
    if not (bid > 0 and ask > 0 and ask >= bid):
        return (None, None)
    mid = (bid + ask) / 2.0
    return (mid, (ask - bid) / mid) if mid > 0 else (None, None)


def straddle_cost(chain_fn, ticker: str, expiry_index: int = 0) -> dict:
    """Round-trip cost of an ATM straddle, as a percentage of spot.

    Entry crosses the call spread and the put spread; the exit crosses both
    again. The round trip is therefore the FULL spread on both legs, not half.
    """
    out = {"ticker": ticker, "reason": Q.OK, "spot": None, "oi": None,
           "call_spread": None, "put_spread": None, "straddle_pct": None,
           "roundtrip_pct": None}
    try:
        r = chain_fn(ticker)
    except Exception as e:
        out["reason"] = Q.CHAIN_ERROR
        out["detail"] = type(e).__name__
        return out
    spot = float((r.get("quote") or {}).get("regularMarketPrice") or 0) or None
    exps = r.get("expirationDates") or []
    if not spot:
        out["reason"] = Q.NO_SPOT
        return out
    if not exps:
        out["reason"] = Q.NO_EXPIRIES
        return out
    out["spot"] = spot
    try:
        rr = chain_fn(ticker, exps[min(expiry_index, len(exps) - 1)])
        o = (rr.get("options") or [{}])[0]
        calls, puts = o.get("calls") or [], o.get("puts") or []
    except Exception as e:
        out["reason"] = Q.CHAIN_ERROR
        out["detail"] = type(e).__name__
        return out
    if not calls or not puts:
        out["reason"] = Q.NO_PUTS
        return out
    ca = min(calls, key=lambda x: abs((x.get("strike") or 0) - spot))
    pa = min(puts, key=lambda x: abs((x.get("strike") or 0) - spot))
    out["oi"] = (ca.get("openInterest") or 0) + (pa.get("openInterest") or 0)
    cm, cs = _mid_spread(ca)
    pm, ps = _mid_spread(pa)
    if cm is None or pm is None:
        out["reason"] = Q.NO_TWO_SIDED
        return out
    if out["oi"] < MIN_OI:
        out["reason"] = Q.ZERO_OI
        return out
    out["call_spread"], out["put_spread"] = cs, ps
    straddle = cm + pm
    out["straddle_pct"] = straddle / spot * 100.0
    # Full spread on both legs, entry and exit.
    cost = (ca.get("ask") - ca.get("bid")) + (pa.get("ask") - pa.get("bid"))
    out["roundtrip_pct"] = cost / spot * 100.0
    return out


def cost_now(chain_fn=None, tickers: list = None) -> dict:
    """STAGE 1. Measure the round trip, or REFUSE and say why.

    The refusal is the point. Run pre-market this returns a spread of zero for
    every name — 'trading is free' — so the control decides whether any number
    may be recorded at all.
    """
    if chain_fn is None:
        import screen as S
        chain_fn = S.Yahoo().chain
    live, why = Q.feed_is_live(chain_fn)
    out = {"feed_live": live, "feed_why": why, "rows": [], "median": None,
            "n_priced": 0}
    if not live:
        out["refused"] = (
            "cost NOT measured: the options feed is not serving two-sided "
            "quotes. Measuring now would record a spread of zero for every "
            "name, i.e. that trading is free. Re-run during market hours.")
        return out
    names = tickers if tickers is not None else sorted(
        {v for v in US_LINES.values() if v})
    rows = [straddle_cost(chain_fn, t) for t in names]
    out["rows"] = rows
    priced = [r["roundtrip_pct"] for r in rows if r["roundtrip_pct"] is not None]
    out["n_priced"] = len(priced)
    if priced:
        out["median"] = float(np.median(priced))
        out["q1"] = float(np.quantile(priced, 0.25))
        out["q3"] = float(np.quantile(priced, 0.75))
    return out


def verdict(median_cost: float | None, magnitude_lift: float,
            fraction: float = COST_BAR_FRACTION) -> tuple:
    """(passes, sentence). The pre-registered gate, applied without discretion."""
    if median_cost is None:
        return (None, "cost not measurable — no verdict is available")
    bar = fraction * magnitude_lift
    if median_cost < bar:
        return (True, f"round trip {median_cost:.2f}% is under the "
                      f"{fraction:.0%} bar of {bar:.2f}% — Stage 2 proceeds")
    return (False, f"round trip {median_cost:.2f}% EXCEEDS the {fraction:.0%} "
                   f"bar of {bar:.2f}% (lift {magnitude_lift:.2f}%) — "
                   "REJECTED ON COST, and Stage 2 does not run")


def report(c: dict, magnitude_lift: float | None) -> str:
    L = ["▎STAGE 1 — what a straddle costs to put on and take off"]
    if not c["feed_live"]:
        return "\n".join(L + [f"   ⛔ {c['refused']}", f"   {c['feed_why']}"])
    L.append(f"   {c['n_priced']} of {len(c['rows'])} names quotable "
             f"(two-sided, OI >= {MIN_OI})")
    L.append("")
    L.append(f"   {'name':<7}{'spot':>9}{'straddle':>10}{'round trip':>12}"
             f"{'OI':>8}   note")
    for r in sorted(c["rows"], key=lambda x: x["ticker"]):
        if r["roundtrip_pct"] is None:
            L.append(f"   {r['ticker']:<7}{'':>9}{'':>10}{'':>12}{'':>8}   "
                     f"{Q.EXPLAIN.get(r['reason'], r['reason'])}")
            continue
        L.append(f"   {r['ticker']:<7}{r['spot']:>9.2f}"
                 f"{r['straddle_pct']:>9.2f}%{r['roundtrip_pct']:>11.2f}%"
                 f"{r['oi']:>8}")
    if c["median"] is not None:
        L.append("")
        L.append(f"   median round trip {c['median']:.2f}% of spot   "
                 f"IQR {c['q1']:.2f}%-{c['q3']:.2f}%")
    if magnitude_lift is not None:
        ok, sentence = verdict(c["median"], magnitude_lift)
        L.append("")
        L.append(f"   PRE-REGISTERED GATE: {sentence}")
    return "\n".join(L)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--lift", type=float, default=None,
                    help="measured post-filing magnitude lift, %% of spot")
    a = ap.parse_args(argv)
    c = cost_now()
    print(report(c, a.lift))
    return 0 if c["feed_live"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
