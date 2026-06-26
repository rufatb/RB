#!/usr/bin/env python3
"""
scan.py — TSX opportunity scanner.

WHAT IT DOES: runs the SAME honest engine across a universe of liquid TSX names
and ranks them by how confident an open-to-close (close vs open) call can be —
long OR short — so you can decide whether AC.TO is the best use of risk today or
whether a different name offers a cleaner setup. Designed to be re-run on a
5-minute cadence (the structure sharpens after the open).

HONESTY CONSTRAINTS (inherited from the rest of the tool; do not strip):
    * The probability is still CAPPED at [0.35, 0.65]. "More confident" means
      the strongest multi-factor confluence within that band — never a
      manufactured high-conviction call. High conviction is unavailable intraday.
    * Every candidate must pass the data-integrity guard first. Stale/unverified
      names are excluded from ranking, not silently trusted.
    * If NOTHING clears NO-EDGE — WAIT, the scanner says "stand down". It will
      not invent an opportunity to have something to say.
    * Macro context (crude, TSX, CAD, VIX) is context, not signal — it is shared
      across candidates and labelled as such.
"""

from __future__ import annotations

import argparse
import datetime as dt
from concurrent.futures import ThreadPoolExecutor, as_completed
from zoneinfo import ZoneInfo

import pandas as pd

import metrics
import patterns
from adapters import build_adapter
from dashboard import (build_levels, data_integrity_guard, decide, load_config,
                       parse_hhmm, safe_pct_change, _pos_in_trailing_range)

# Liquid TSX names used when config has no scan.universe. AC.TO is always added.
DEFAULT_UNIVERSE = [
    "AC.TO", "RY.TO", "TD.TO", "BNS.TO", "BMO.TO", "CM.TO",
    "ENB.TO", "TRP.TO", "CNQ.TO", "SU.TO", "CVE.TO",
    "CP.TO", "CNR.TO", "SHOP.TO", "ABX.TO", "AEM.TO",
    "NTR.TO", "MFC.TO", "SLF.TO", "BCE.TO", "T.TO",
]

_CONV_RANK = {"Medium": 2, "Low": 1, "None": 0}


def _confidence_score(c: dict) -> float:
    """Higher = a more confident, better-confluence setup. Used only for ranking;
    the underlying probability is still clamped to [0.35, 0.65]."""
    if not c.get("passed") or c.get("verdict") == "NO EDGE — WAIT":
        return -1.0
    p = c.get("probability", 0.5)
    return _CONV_RANK.get(c.get("conviction"), 0) + abs(p - 0.5) * 10


# ─────────────────────────────────────────────────────────────────────────────
# Per-candidate evaluation — the full engine, sharing macro context.
# ─────────────────────────────────────────────────────────────────────────────
def evaluate(adapter, ticker, cfg, now, mkt_open, mkt_close, macro) -> dict:
    out = {"ticker": ticker, "passed": False, "verdict": "ERROR", "note": ""}
    try:
        quote = adapter.get_quote(ticker)
        guard = data_integrity_guard(
            quote, now=now, exchange_tz=cfg["exchange_tz"],
            market_open=mkt_open, market_close=mkt_close,
            max_stale_minutes=cfg["guard"]["max_stale_minutes"],
            source_conflict_pct=cfg["guard"]["source_conflict_pct"],
        )
        out["passed"] = guard.passed
        out["guard_reasons"] = guard.reasons
        if not guard.passed:
            out["verdict"] = "DATA NOT VERIFIED"
            return out

        try:
            intraday = adapter.get_intraday_bars(ticker, "1m")
        except Exception:
            intraday = pd.DataFrame()
        try:
            daily = adapter.get_daily_bars(ticker, cfg["levels"]["daily_lookback_days"])
        except Exception:
            daily = pd.DataFrame()

        struct = metrics.structure(quote)
        orb = metrics.opening_range(intraday, quote.last, cfg["levels"]["orb_minutes"])
        vw = metrics.vwap(intraday, quote.last)
        sf = metrics.spike_fade(intraday, quote.open, cfg["levels"]["spike_fade_window_min"])
        levels = metrics.key_levels(daily, cfg["levels"]["swing_lookback_days"])

        prev_oc = None
        if not daily.empty and len(daily) >= 1 and "Open" in daily:
            p = daily.iloc[-1]
            if p["Open"]:
                prev_oc = (p["Close"] - p["Open"]) / p["Open"] * 100
        pos = _pos_in_trailing_range(daily, quote.last)
        pat = patterns.analyze(
            daily, macro.get("crude_daily", pd.DataFrame()),
            today_gap_pct=struct.get("gap_pct"),
            today_prev_oc_pct=prev_oc, today_pos_in_range_pct=pos,
        ) if cfg.get("patterns", {}).get("enabled", True) else {}

        rel = metrics.relative_strength(
            struct.get("pct_vs_prior_close"), macro.get("tsx_pct"), macro.get("peer_avg"))
        decision = decide(struct, orb, vw, sf, rel, {},
                          pattern_factors=pat.get("factors") if pat else None)
        lv = build_levels(struct, orb, levels)

        analog = (pat or {}).get("analog_days", {})
        out.update({
            "verdict": decision["verdict"],
            "probability": decision["probability"],
            "conviction": decision["conviction"],
            "factors": decision["factors"],
            "last": struct.get("last"), "open": struct.get("open"),
            "gap_pct": struct.get("gap_pct"),
            "pct_vs_open": struct.get("pct_vs_open"),
            "orb_low": orb.get("orbN_low"), "orb_high": orb.get("orbN_high"),
            "vwap_pct": vw.get("price_vs_vwap_pct"),
            "spike_fade": sf.get("flags", []),
            "bull_trigger": lv.get("bull_trigger"), "bear_trigger": lv.get("bear_trigger"),
            "bull_target": lv.get("bull_target"), "bear_target": lv.get("bear_target"),
            "rel_vs_tsx": rel.get("vs_tsx"),
            "analog_ci": (
                f"{analog['p25_oc_pct']}..{analog['p75_oc_pct']}% (n={analog['n_neighbours']})"
                if analog.get("available") else "unavailable"),
            "history_days": (pat or {}).get("history_days", 0),
        })
    except Exception as e:
        out["note"] = f"error: {e}"
    return out


# ─────────────────────────────────────────────────────────────────────────────
# Orchestration
# ─────────────────────────────────────────────────────────────────────────────
def scan_once(config: dict, source: str, cross_check, max_workers: int = 8) -> dict:
    tz = config["exchange_tz"]
    now = dt.datetime.now(ZoneInfo(tz))
    mkt_open, mkt_close = parse_hhmm(config["market_open"]), parse_hhmm(config["market_close"])
    adapter = build_adapter(source, exchange_tz=tz, cross_check=cross_check)

    # Shared macro context — fetched ONCE, reused across candidates.
    corr = config["correlated"]
    peers = [safe_pct_change(adapter, p, tz) for p in corr["airline_peers"]]
    peers_valid = [p for p in peers if p is not None]
    try:
        crude_daily = adapter.get_daily_bars(corr["crude"], config["levels"]["daily_lookback_days"])
    except Exception:
        crude_daily = pd.DataFrame()
    macro = {
        "crude_pct": safe_pct_change(adapter, corr["crude"], tz),
        "tsx_pct": safe_pct_change(adapter, corr["tsx"], tz),
        "cad_pct": safe_pct_change(adapter, corr["cadusd"], tz),
        "vix_pct": safe_pct_change(adapter, corr["vix"], tz),
        "peer_avg": sum(peers_valid) / len(peers_valid) if peers_valid else None,
        "crude_daily": crude_daily,
    }

    universe = config.get("scan", {}).get("universe") or DEFAULT_UNIVERSE
    if config["ticker"] not in universe:
        universe = [config["ticker"], *universe]

    results = []
    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        futs = {ex.submit(evaluate, adapter, t, config, now, mkt_open, mkt_close, macro): t
                for t in universe}
        for f in as_completed(futs):
            results.append(f.result())

    ranked = rank(results, config["ticker"])
    ranked.update({"generated_at": now.isoformat(timespec="seconds"), "macro": macro})
    return ranked


def rank(results: list, anchor: str) -> dict:
    """Pure ranking/selection — score, sort, pick leaders/best/anchor. Testable
    without any network. A leader is a guard-passed, non-WAIT candidate."""
    for r in results:
        r["score"] = _confidence_score(r)
    results = sorted(results, key=lambda r: r["score"], reverse=True)
    leaders = [r for r in results if r["score"] > 0]
    ac = next((r for r in results if r["ticker"] == anchor), None)
    best = leaders[0] if leaders else None
    return {"results": results, "leaders": leaders, "best": best, "ac": ac, "anchor": anchor}


# ─────────────────────────────────────────────────────────────────────────────
# Rendering
# ─────────────────────────────────────────────────────────────────────────────
def _side(r):
    return "LONG" if r["verdict"] == "BULL LEAN" else "SHORT" if r["verdict"] == "BEAR LEAN" else "—"


def render(scan: dict):
    print("=" * 74)
    print(f"TSX INTRADAY SCAN  ({scan['generated_at']})")
    print("=" * 74)
    m = scan["macro"]
    def f(x): return "n/a" if x is None else f"{x:+.2f}%"
    print(f"macro (context only): crude {f(m['crude_pct'])}  TSX {f(m['tsx_pct'])}  "
          f"CAD {f(m['cad_pct'])}  VIX {f(m['vix_pct'])}")

    print("\nRanked candidates (probability is CAPPED at [0.35,0.65]):")
    print(f"  {'ticker':<9}{'verdict':<14}{'side':<6}{'p':>5}  {'conv':<7}{'last':>8}  notes")
    shown = [r for r in scan["results"] if r["verdict"] not in ("ERROR",)][:12]
    for r in shown:
        if not r.get("passed"):
            print(f"  {r['ticker']:<9}{'NOT VERIFIED':<14}{'—':<6}{'—':>5}  {'—':<7}"
                  f"{'—':>8}  {(r.get('guard_reasons') or [''])[0][:30]}")
            continue
        p = r.get("probability", 0.5)
        sf = " ⚑fade" if r.get("spike_fade") else ""
        print(f"  {r['ticker']:<9}{r['verdict']:<14}{_side(r):<6}{p:>5.2f}  "
              f"{r.get('conviction','None'):<7}{(r.get('last') or 0):>8.2f}  "
              f"vsVWAP {r.get('vwap_pct') if r.get('vwap_pct') is None else round(r['vwap_pct'],2)}{sf}")

    print("\n" + "-" * 74)
    print("RECOMMENDATION")
    print("-" * 74)
    ac, best = scan["ac"], scan["best"]
    anchor = scan["anchor"]

    if ac:
        if ac.get("passed"):
            print(f"  {anchor}: {ac['verdict']}  (p={ac.get('probability',0.5):.2f}, "
                  f"conviction {ac.get('conviction','None')}).")
        else:
            print(f"  {anchor}: data not verified live — {(ac.get('guard_reasons') or ['?'])[0]}")

    if not best:
        print("  No TSX name clears NO-EDGE — WAIT right now. Honest call: STAND DOWN.")
        print("  Nothing on the board offers a clean intraday open-to-close edge.")
        print("  (Re-scan after the open / in 5 min — structure sharpens then.)")
        return

    side = _side(best)
    if best["ticker"] == anchor:
        print(f"  {anchor} IS the best available setup right now: {side}.")
    else:
        ac_go = ac and ac.get("passed") and ac["verdict"] != "NO EDGE — WAIT"
        verb = "is a NO-GO" if not ac_go else "is tradeable but weaker"
        print(f"  CALL: {anchor} {verb}. Better opportunity → {best['ticker']} {side}.")

    print(f"\n  >>> {best['ticker']} — {side}  |  p(close>open)={best.get('probability',0.5):.2f}  "
          f"|  conviction {best.get('conviction','None')}")
    trig = best["bull_trigger"] if side == "LONG" else best["bear_trigger"]
    tgt = best["bull_target"] if side == "LONG" else best["bear_target"]
    print(f"      trigger : {trig}")
    print(f"      target  : {tgt}")
    print(f"      analog CI (open->close of similar days): {best.get('analog_ci')}")
    print(f"      why     : {'; '.join(best.get('factors', [])) or 'structural confluence'}")
    print(f"      context : rel-to-TSX {best.get('rel_vs_tsx')}; "
          f"history {best.get('history_days')} days")
    print("\n  NOTE: even the best read is a CAPPED ~0.6x probability — a lean, not a "
          "sure thing. Size from the stop, honour the invalidation, re-check in 5 min.")


def main(argv=None):
    p = argparse.ArgumentParser(description="TSX intraday opportunity scanner")
    p.add_argument("--config", default="config.yaml")
    p.add_argument("--source", default=None)
    p.add_argument("--cross-check", default=None)
    p.add_argument("--workers", type=int, default=8)
    args = p.parse_args(argv)
    config = load_config(args.config)
    source = args.source or config.get("data_sources", {}).get("primary", "yahoo_direct")
    cc = ([s.strip() for s in args.cross_check.split(",")] if args.cross_check
          else config.get("data_sources", {}).get("cross_check"))
    render(scan_once(config, source, cc, max_workers=args.workers))


if __name__ == "__main__":
    main()
