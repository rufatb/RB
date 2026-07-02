#!/usr/bin/env python3
"""
hold.py — mid-session hold-to-close check (conditional, from HERE).

WHY THIS EXISTS (encoded after a live losing long was justified with the
MORNING base rate): the 9:31 analog probability is conditioned on the OPENING
setup. Once the session has evolved — e.g. price has traded 0.5% below its
open — that morning number NO LONGER APPLIES. The honest question mid-session
is conditional: "on historical days that reached the same drawdown/run-up from
their open, where did they close?" This tool answers exactly that, from the
full daily history, with the same guardrails (real data only, sample sizes
shown, Beta smoothing, no probability ever presented outside [0.35, 0.65]
framing for a directional edge).

USAGE
    python hold.py                      # anchor ticker from config
    python hold.py --ticker CVE.TO --side short

Caveat printed with every result: daily bars cannot time the intraday visit
(a day whose LOW touched this level may have dipped at 9:40 or 15:40), so
these are approximate conditionals — still far more honest than reusing the
morning number after the tape has moved.
"""

from __future__ import annotations

import argparse
import datetime as dt
from zoneinfo import ZoneInfo

import numpy as np

from adapters import build_adapter
from dashboard import load_config

SMOOTH_M = 10  # same Beta-prior convention as patterns.analog_days


def conditional_close_stats(daily, lvl_frac: float, *, below: bool) -> dict:
    """Among days whose LOW (or HIGH, for run-ups) reached open*lvl_frac,
    where did they close relative to that level and to their open?"""
    o = daily["Open"].to_numpy()
    ext = daily["Low"].to_numpy() if below else daily["High"].to_numpy()
    c = daily["Close"].to_numpy()
    lvl = o * lvl_frac
    visited = (ext <= lvl) if below else (ext >= lvl)
    n = int(visited.sum())
    if n < 20:
        return {"available": False, "n": n, "reason": "fewer than 20 comparable days"}
    cv, ov, lv = c[visited], o[visited], lvl[visited]
    above_here = float((cv > lv).mean())
    smoothed = ((cv > lv).sum() + 0.5 * SMOOTH_M) / (n + SMOOTH_M)
    rec = (cv - lv) / lv * 100
    return {
        "available": True, "n": n,
        "p_close_above_here_raw": round(above_here * 100, 1),
        "p_close_above_here": round(float(smoothed) * 100, 1),
        "p_close_above_open": round(float((cv > ov).mean()) * 100, 1),
        "median_vs_here_pct": round(float(np.median(rec)), 2),
        "p25_vs_here_pct": round(float(np.percentile(rec, 25)), 2),
        "p75_vs_here_pct": round(float(np.percentile(rec, 75)), 2),
        "worst_vs_here_pct": round(float(rec.min()), 2),
    }


def run(config: dict, ticker: str, side: str, source: str) -> dict:
    tz = config["exchange_tz"]
    adapter = build_adapter(source, exchange_tz=tz)
    q = adapter.get_quote(ticker)
    if q.last is None or q.open is None:
        return {"error": "no live quote — cannot compute a conditional"}
    daily = adapter.get_daily_bars(ticker, config["levels"]["daily_lookback_days"] + 2200)
    daily = daily.dropna(subset=["Open", "High", "Low", "Close"])
    # Exclude today's in-progress bar — its close is the future; using it would
    # be lookahead.
    if q.session_date is not None and len(daily) and daily.index[-1].date() == q.session_date:
        daily = daily.iloc[:-1]

    lvl_frac = q.last / q.open
    vs_open_pct = (lvl_frac - 1) * 100
    below = q.last <= q.open
    stats = conditional_close_stats(daily, lvl_frac, below=below)

    # Setup match: same-sign small gap as today (keeps the conditional honest
    # to today's shape without shrinking the sample to nothing).
    gaps = (daily["Open"] - daily["Close"].shift(1)) / daily["Close"].shift(1) * 100
    gap_t = None
    if q.prior_close:
        gap_t = (q.open - q.prior_close) / q.prior_close * 100
        if gap_t >= 0:
            matched = daily[(gaps >= 0) & (gaps < max(1.0, gap_t * 2))]
        else:
            matched = daily[(gaps <= 0) & (gaps > min(-1.0, gap_t * 2))]
        stats_matched = conditional_close_stats(matched, lvl_frac, below=below)
    else:
        stats_matched = {"available": False, "n": 0, "reason": "no prior close"}

    return {"ticker": ticker, "side": side, "last": q.last, "open": q.open,
            "vs_open_pct": round(vs_open_pct, 2), "gap_pct": None if gap_t is None else round(gap_t, 2),
            "as_of": str(q.as_of), "session": str(q.session_date),
            "n_history": len(daily), "all_days": stats, "setup_matched": stats_matched}


def render(r: dict, side: str):
    if "error" in r:
        print(f"⚠ {r['error']}")
        return
    print("─" * 74)
    print(f"HOLD-TO-CLOSE CHECK — {r['ticker']}  (as of {r['as_of']})")
    print("─" * 74)
    print(f"live: last {r['last']}  open {r['open']}  → {r['vs_open_pct']:+.2f}% vs open"
          f"   gap {r['gap_pct']:+.2f}%   history {r['n_history']} days")

    def block(label, s):
        if not s.get("available"):
            print(f"\n  {label}: unavailable ({s.get('reason')})")
            return
        print(f"\n  {label}  (n={s['n']} comparable days):")
        print(f"    P(close ABOVE current price): {s['p_close_above_here']}% "
              f"(raw {s['p_close_above_here_raw']}%)")
        print(f"    P(close above the OPEN — full recovery): {s['p_close_above_open']}%")
        print(f"    close vs here: median {s['median_vs_here_pct']:+.2f}%  "
              f"p25 {s['p25_vs_here_pct']:+.2f}%  p75 {s['p75_vs_here_pct']:+.2f}%  "
              f"worst {s['worst_vs_here_pct']:+.2f}%")

    block("ALL days that visited this level vs their open", r["all_days"])
    block("SETUP-MATCHED (similar gap sign/size)", r["setup_matched"])

    s = r["setup_matched"] if r["setup_matched"].get("available") else r["all_days"]
    if s.get("available"):
        p = s["p_close_above_here"]
        fav = p if side == "long" else 100 - p
        print(f"\n  YOUR {side.upper()}: chance the close is on your side of the "
              f"current price ≈ {fav:.0f}%")
        if 45 <= fav <= 55:
            print("  → That is a COIN FLIP, not an edge. Holding from here is hope, "
                  "not signal.")
    print("\n  Caveats: daily bars can't time the intraday visit; conditionals are")
    print("  approximate; the MORNING base rate no longer applies once the day has")
    print("  moved. Honour your invalidation — do not re-justify a broken stop.")


def main(argv=None):
    p = argparse.ArgumentParser(description="Mid-session conditional hold-to-close check")
    p.add_argument("--config", default="config.yaml")
    p.add_argument("--ticker", default=None)
    p.add_argument("--side", choices=["long", "short"], default="long")
    p.add_argument("--source", default=None)
    args = p.parse_args(argv)
    config = load_config(args.config)
    ticker = args.ticker or config["ticker"]
    source = args.source or config.get("data_sources", {}).get("primary", "yahoo_direct")
    render(run(config, ticker, args.side, source), args.side)


if __name__ == "__main__":
    main()
