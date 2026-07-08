#!/usr/bin/env python3
"""
confirm.py — "am I allowed to enter yet?" live trigger confirmation.

WHY (the most-repeated failure across five live days): entries keep happening
BEFORE the stated trigger — seeing the break and buying without the 5-min
HOLD. On day 5 the user bought MFC at 59.04 under a 59.10 trigger; the hold
never occurred all day, the plan said NO TRADE, and the entire loss came from
the early entry (MFC actually closed above its open — the prediction was
right). This tool gives a 5-second answer before any fill:

    python confirm.py --ticker MFC.TO --side long [--level 59.10]

Verdicts: CONFIRMED (5-min hold satisfied as of now) / BROKE BUT NOT HELD /
NOT BROKEN. If --level is omitted, the opening-range extreme is used.
"""

from __future__ import annotations

import argparse

from adapters import build_adapter
from dashboard import load_config


def hold_status(closes: list, level: float, side: str, hold: int = 5) -> str:
    """Pure: status of a break-and-hold trigger given the day's 1-min closes.
    'CONFIRMED' only when the LAST `hold` closes are all beyond the level —
    i.e., the hold condition is true right now, not just at some point today."""
    beyond = [(c > level) if side == "long" else (c < level) for c in closes]
    if not any(beyond):
        return "NOT BROKEN"
    if len(beyond) >= hold and all(beyond[-hold:]):
        return "CONFIRMED"
    return "BROKE BUT NOT HELD"


def main(argv=None):
    p = argparse.ArgumentParser(description="Live break-and-hold trigger check")
    p.add_argument("--ticker", required=True)
    p.add_argument("--side", choices=["long", "short"], required=True)
    p.add_argument("--level", type=float, default=None,
                   help="trigger level (default: today's opening-range extreme)")
    p.add_argument("--config", default="config.yaml")
    args = p.parse_args(argv)

    cfg = load_config(args.config)
    a = build_adapter(cfg.get("data_sources", {}).get("primary", "yahoo_direct"),
                      exchange_tz=cfg["exchange_tz"])
    bars = a.get_intraday_bars(args.ticker, "1m")
    if bars is None or bars.empty:
        print("⚠ no intraday bars — cannot confirm anything; do not enter blind")
        return 1
    orb = bars.iloc[:cfg["levels"]["orb_minutes"]]
    level = args.level if args.level is not None else (
        float(orb["High"].max()) if args.side == "long" else float(orb["Low"].min()))
    closes = bars["Close"].dropna().tolist()
    status = hold_status(closes, level, args.side)
    last = closes[-1]
    asof = bars.index[-1]
    print(f"{args.ticker} {args.side.upper()} trigger {level:.2f} — {status}")
    print(f"  last {last:.2f}  as-of {asof}")
    if status == "CONFIRMED":
        print("  ✅ entry condition satisfied RIGHT NOW. Stop = the open; size from it.")
    elif status == "BROKE BUT NOT HELD":
        print("  ⛔ DO NOT ENTER — it poked through but hasn't HELD 5 minutes. "
              "This exact pattern (enter on the poke) caused the MFC day-5 loss.")
    else:
        print("  ⛔ DO NOT ENTER — the trigger hasn't even broken yet.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
