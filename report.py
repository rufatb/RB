#!/usr/bin/env python3
"""
report.py — THE single 9:31 entry point.

One command runs the whole pipeline in working order and prints a clean,
interpretable morning report for an open-to-close intraday trader:

    python report.py                # the 9:31 morning report
    python report.py --check       # preflight: verify every configured API

Pipeline: API preflight → data-integrity guard → full-universe evaluation
(structure + deep-history analogs + macro + optional sentiment) → cross-lens
selection → calibrated EOD probabilities → entry/invalidation levels → sized
risk plans. Every honesty guardrail applies: hard [0.35, 0.65] probability
clamp, off-sample and conflict exclusion, STAND DOWN when nothing qualifies.

Scheduling (cron, America/Toronto):
    31 9 * * 1-5  cd /path/to/repo && TZ=America/Toronto python report.py >> report.log 2>&1
"""

from __future__ import annotations

import argparse
import datetime as dt
import os
import sys
from zoneinfo import ZoneInfo

import risk
from adapters import build_adapter
from dashboard import is_trading_day, load_config
from scan import open_select

CHECKMARK, CROSS, WARN = "✅", "❌", "⚠️"


# ─────────────────────────────────────────────────────────────────────────────
# Preflight — verify every configured API actually works before relying on it.
# ─────────────────────────────────────────────────────────────────────────────
def preflight(config: dict) -> dict:
    """Test each configured data source + optional services. Returns a report
    dict; never raises. A failed cross-check degrades, a failed primary blocks."""
    tz = config["exchange_tz"]
    ticker = config["ticker"]
    ds = config.get("data_sources", {})
    primary = ds.get("primary", "yahoo_direct")
    cross = ds.get("cross_check") or []
    checks = []

    def check_source(name):
        try:
            adp = build_adapter(name, exchange_tz=tz)
            q = adp.get_quote(ticker)
            if q.last is None:
                return (name, False, "connected but returned no price")
            age = ""
            if q.as_of is not None:
                mins = (dt.datetime.now(ZoneInfo(tz)) - q.as_of).total_seconds() / 60
                age = f", as-of {mins:.0f}m ago"
            return (name, True, f"{ticker} last={q.last}{age} (session {q.session_date})")
        except Exception as e:
            return (name, False, f"{type(e).__name__}: {str(e)[:70]}")

    checks.append(("primary: " + primary, *check_source(primary)[1:]))
    for cc in cross:
        checks.append(("cross-check: " + cc, *check_source(cc)[1:]))

    # Optional key-based services: report presence honestly, never fake.
    for env, label in (("FINNHUB_API_KEY", "finnhub key"),
                       ("TWELVEDATA_API_KEY", "twelvedata key")):
        checks.append((label, bool(os.environ.get(env)),
                       "set" if os.environ.get(env) else "not set (optional)"))
    has_claude = bool(os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN"))
    checks.append(("claude analyst", has_claude,
                   "key present" if has_claude else "no ANTHROPIC_API_KEY (analyst disabled, optional)"))

    today = dt.datetime.now(ZoneInfo(tz)).date()
    trading = is_trading_day(today, "TSX")
    checks.append(("trading day", trading,
                   str(today) if trading else f"{today} is a weekend/TSX holiday"))

    primary_ok = checks[0][1]
    return {"checks": checks, "primary_ok": primary_ok, "trading_day": trading}


def render_preflight(pf: dict) -> None:
    print("─" * 74)
    print("PREFLIGHT — API & environment checks")
    print("─" * 74)
    for name, ok, detail in pf["checks"]:
        # Cross-checks and key-based extras are non-fatal — warn, don't fail.
        soft = "optional" in detail or name.startswith("cross-check")
        mark = CHECKMARK if ok else (WARN if soft else CROSS)
        print(f"  {mark} {name:<22} {detail}{' (non-fatal)' if (not ok and soft) else ''}")
    if not pf["primary_ok"]:
        print(f"\n  {CROSS} PRIMARY SOURCE FAILED — the report cannot produce a "
              "verified-live read. Fix the source or use --source/manual input.")


# ─────────────────────────────────────────────────────────────────────────────
# The morning report
# ─────────────────────────────────────────────────────────────────────────────
def _fmt(x, nd=2, pfx=""):
    return "n/a" if x is None else f"{pfx}{x:.{nd}f}"


def _risk_line(r: dict, is_long: bool, rcfg: dict) -> str:
    """Sized hypothetical: entry at the trigger, stop at the open (invalidation)."""
    entry = r.get("bull_trigger_level") if is_long else r.get("bear_trigger_level")
    stop = r.get("open")
    if entry is None or stop is None or entry == stop:
        return "sizing unavailable (no trigger/stop levels)"
    plan = risk.position_size(
        account_equity=rcfg["account_equity"],
        risk_per_trade_pct=rcfg["risk_per_trade_pct"],
        entry=entry, stop=stop, side="long" if is_long else "short",
        max_position_pct=rcfg.get("max_position_pct", 100.0),
    )
    note = f"  [{plan.notes[0]}]" if plan.notes else ""
    return (f"size {plan.shares} sh @ {entry:.2f}, stop {stop:.2f} "
            f"(≈${plan.risk_dollars:.0f} at stop){note}")


def render_report(sel: dict, config: dict, pf: dict) -> None:
    tz = config["exchange_tz"]
    print("=" * 74)
    print(f"MORNING REPORT — TSX open-to-close selection   {sel['generated_at']}")
    print("=" * 74)

    m = sel["macro"]
    f = lambda x: "n/a" if x is None else f"{x:+.2f}%"
    print(f"macro (context, not signal): crude {f(m['crude_pct'])}  "
          f"TSX {f(m['tsx_pct'])}  CAD {f(m['cad_pct'])}  VIX {f(m['vix_pct'])}")
    n_ver = sel.get("n_verified")
    print(f"universe: {sel['n_universe']} scanned · "
          f"{n_ver if n_ver is not None else '?'} verified live · "
          f"{sel['n_qualified']} qualified the cross-lens gate")
    if n_ver == 0:
        print(f"{WARN} NO name passed the data-integrity guard — feed is stale "
              "(pre-market, holiday,\n   or delayed source). Run at/after 9:31 ET "
              "on a trading day for a live read.")

    rcfg = config.get("risk", {})

    def block(title, picks, is_long):
        print("\n" + "─" * 74)
        print(title)
        print("─" * 74)
        if not picks:
            print("  (none qualified today)")
            return
        for i, r in enumerate(picks, 1):
            cls = r["cls"]
            eod_p = r.get("eod_p")
            green = r.get("analog_green")
            print(f"  {i}. {r['ticker']}  —  calibrated P(close{'>' if is_long else '<'}open) "
                  f"≈ {_fmt((eod_p if is_long else (None if eod_p is None else 1 - eod_p)))}  "
                  f"·  tier {cls['tier']}")
            print(f"     base rate : {_fmt(green, 1)}% of similar days closed green "
                  f"(raw {_fmt(r.get('analog_green_raw'), 1)}%, smoothed; "
                  f"{r.get('analog_ci')})")
            print(f"     agreeing  : {', '.join(cls['lenses'])}")
            trig = r.get("bull_trigger") if is_long else r.get("bear_trigger")
            print(f"     entry     : {trig or 'unavailable'}")
            print(f"     exit if   : 5-min close back through the open "
                  f"({_fmt(r.get('open'))}) — the thesis is then wrong; do not hold & hope")
            print(f"     risk      : {_risk_line(r, is_long, rcfg)}")

    block(f"TOP LONGS — most likely to close ABOVE their open", sel["longs"], True)
    block(f"TOP SHORTS — most likely to close BELOW their open", sel["shorts"], False)

    if not sel["longs"] and not sel["shorts"]:
        print("\n  ⛔ STAND DOWN — no name cleared the gates today (verified data, "
              "in-sample base\n  rate with a real tilt, and confirming lenses). "
              "No trade IS the honest call.")

    print("\n" + "─" * 74)
    print("HOW TO READ THIS (honesty footer)")
    print("─" * 74)
    print("  • Probabilities are CALIBRATED and HARD-CAPPED to [0.35, 0.65]: even the")
    print("    best pick is a modest lean, never a sure thing (backtest: single-name")
    print("    open-to-close is ~coin-flip; raw base rates were overconfident).")
    print("  • Enter on the TRIGGER, not before. Inside the opening range = no-trade.")
    print("  • The OPEN is the invalidation. Size from that stop — never conviction.")
    print("  • Spread small risk across picks; do not bet the day on one name.")
    print("  • Read-only decision support, not financial advice. It never places orders.")


def main(argv=None):
    p = argparse.ArgumentParser(description="9:31 TSX morning report (single entry point)")
    p.add_argument("--config", default="config.yaml")
    p.add_argument("--source", default=None, help="override primary data source")
    p.add_argument("--check", action="store_true", help="preflight only: verify APIs & exit")
    p.add_argument("--top", type=int, default=None)
    p.add_argument("--workers", type=int, default=8)
    args = p.parse_args(argv)

    config = load_config(args.config)
    source = args.source or config.get("data_sources", {}).get("primary", "yahoo_direct")
    cross = config.get("data_sources", {}).get("cross_check")

    pf = preflight(config)
    render_preflight(pf)
    if args.check:
        return 0 if pf["primary_ok"] else 1
    if not pf["primary_ok"]:
        return 1  # no fabricated report on a dead primary source

    top_n = args.top or config.get("scan", {}).get("top_n", 3)
    sel = open_select(config, source, cross, top_n=top_n, max_workers=args.workers)
    print()
    render_report(sel, config, pf)
    return 0


if __name__ == "__main__":
    sys.exit(main())
