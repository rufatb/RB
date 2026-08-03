#!/usr/bin/env python3
"""
dashboard.py — Pre-Open Brief entry point.

Runs ~09:31 ET and prints an HONEST, CALIBRATED intraday decision-support brief.

READ THIS FIRST — THE DESIGN PHILOSOPHY IS LOAD-BEARING:
    This is decision SUPPORT, not a predictor. It was specified by a trader who
    watched an AI manufacture confident intraday calls that flipped with the
    price. The constraints below are NON-NEGOTIABLE and are commented in-code so
    future edits don't "helpfully" remove them:

      1. No fabricated data. Missing -> labelled proxy or "unavailable".
      2. No confidence inflation. p(close>open) defaults to 0.50 and is CLAMPED
         to [0.35, 0.65]. Conflicts / mid-range -> "NO EDGE — WAIT".
      3. Data integrity is checked FIRST. Stale/cached feeds refuse a read.
      4. Levels over predictions. The deliverable is invalidation + triggers.
      5. Risk-first. Size from stop distance, never conviction.
      6. Read-only. Never places orders.
"""

from __future__ import annotations

import argparse
import datetime as dt
import sys
from typing import Optional
from zoneinfo import ZoneInfo

import pandas as pd
import yaml

import analyst
import metrics
import patterns
import risk
from adapters import DataAdapter, MultiSourceAdapter, Quote, build_adapter

try:
    from rich.console import Console
    from rich.panel import Panel
    from rich.table import Table
    from rich.text import Text
    _RICH = True
except Exception:  # pragma: no cover - rich optional at runtime
    _RICH = False


# ─────────────────────────────────────────────────────────────────────────────
# Probability clamp — HARD GUARDRAIL.
# WHY: open-to-close direction for a single stock is near a coin flip. Letting a
# model emit 0.8 "up" is exactly the failure mode this tool exists to prevent.
# This is asserted AND covered by a test (tests/test_guardrails.py).
# ─────────────────────────────────────────────────────────────────────────────
HARD_FLOOR, HARD_CAP = 0.35, 0.65   # absolute limits; config may NARROW, never widen


def clamp_probability(p: float, floor: float = HARD_FLOOR, cap: float = HARD_CAP) -> float:
    # Config-supplied bounds are honoured only inside the hard band — a config
    # edit can make the tool MORE conservative, never less.
    floor = max(HARD_FLOOR, floor)
    cap = min(HARD_CAP, cap)
    clamped = max(floor, min(cap, p))
    # Defensive assertion: the contract is that nothing downstream ever sees a
    # probability outside the band for an intraday open-to-close call.
    assert HARD_FLOOR <= clamped <= HARD_CAP, "probability clamp violated"
    return clamped


# ─────────────────────────────────────────────────────────────────────────────
# Decision engine
# ─────────────────────────────────────────────────────────────────────────────
class GuardResult:
    def __init__(self):
        self.passed = True
        self.reasons: list[str] = []
        self.timestamps: dict = {}

    def fail(self, reason: str):
        self.passed = False
        self.reasons.append(reason)


def data_integrity_guard(
    quote: Quote,
    *,
    now: dt.datetime,
    exchange_tz: str,
    market_open: dt.time,
    market_close: dt.time,
    max_stale_minutes: int,
    second_quote: Optional[Quote] = None,
    source_conflict_pct: float = 2.0,
) -> GuardResult:
    """
    Runs FIRST. Free feeds (incl. Yahoo) routinely serve cached/stale data —
    sometimes months old — with no error. A directional read on unverified data
    is the cardinal sin here, so this gate is mandatory and loud on failure.

    Manual source is trusted (the human vouches for live broker L1) and skips
    the staleness fail, but is still surfaced as source=manual.
    """
    g = GuardResult()
    g.timestamps["as_of"] = quote.as_of
    g.timestamps["session_date"] = quote.session_date
    g.timestamps["source"] = quote.source

    today = now.date()
    in_session = market_open <= now.time() <= market_close

    if quote.source == "manual":
        # Trusted by user vouch — but record that staleness was bypassed.
        g.reasons.append("source=manual — staleness bypassed by user vouch")
        return g

    # No timestamp at all -> cannot verify -> stale by definition.
    if quote.as_of is None:
        g.fail("quote carries no timestamp — cannot verify it is live")
        return g

    # Session date must be today (in exchange tz).
    if quote.session_date is not None and quote.session_date != today:
        g.fail(f"quote session date {quote.session_date} != today {today}")

    # Last-trade age check (only meaningful during market hours).
    age_min = (now - quote.as_of).total_seconds() / 60.0
    g.timestamps["age_min"] = age_min
    if in_session and age_min > max_stale_minutes:
        g.fail(f"last trade is {age_min:.0f} min old (> {max_stale_minutes} max)")

    if quote.as_of.date() != today:
        g.fail(f"last trade timestamp dated {quote.as_of.date()} != today {today}")

    # Cross-source conflict check.
    if second_quote is not None and second_quote.last and quote.last:
        diff = abs(second_quote.last - quote.last) / quote.last * 100.0
        g.timestamps["source_conflict_pct"] = diff
        if diff > source_conflict_pct:
            g.fail(
                f"SOURCE CONFLICT: {quote.source}={quote.last} vs "
                f"{second_quote.source}={second_quote.last} ({diff:.1f}% apart)"
            )
    return g


def decide(struct, orb, vw, sf, rel, momo, pattern_factors=None, prob_cfg=None) -> dict:
    """
    Turn measurements into an HONEST verdict + capped probability.

    The baseline is 0.50 + WAIT. Probability only moves off 0.50 when SPECIFIC,
    NAMED structural factors line up — and never past the clamp. Conflicting
    signals or a mid-range price collapse back to WAIT. This intentionally
    refuses to manufacture an edge.

    `pattern_factors` (from patterns.py) are historical base-rate leans. They are
    deliberately WEAK: each counts as at most a fraction of one structural factor,
    so deep history can tip a coin-flip but never manufacture conviction on its
    own. They are still subject to the same [0.35, 0.65] clamp.
    """
    p = 0.50
    factors: list[str] = []         # named reasons that moved p off 0.50
    bull, bear = 0, 0

    last = struct.get("last")
    open_ = struct.get("open")
    pos = orb.get("pos_in_orb_pct")
    vwap_pct = vw.get("price_vs_vwap_pct")

    # --- structural factors (each NAMED so the brief can show its work) -------
    if open_ is not None and last is not None:
        if last > open_:
            bull += 1; factors.append("price holding above open (+)")
        elif last < open_:
            bear += 1; factors.append("price below open (−)")

    if vwap_pct is not None:
        if vwap_pct > 0.1:
            bull += 1; factors.append("price above session VWAP (+)")
        elif vwap_pct < -0.1:
            bear += 1; factors.append("price below session VWAP (−)")

    if pos is not None:
        if pos >= 70:
            bull += 1; factors.append("in upper third of opening range (+)")
        elif pos <= 30:
            bear += 1; factors.append("in lower third of opening range (−)")

    # --- spike-fade flags VETO continuation. They precede chop, not trend. ---
    fade_flag = any("FADE" in f or "NEUTRALIZED" in f or "FAILED-BREAKOUT" in f
                    for f in sf.get("flags", []))

    # Convert tallies to a small, capped nudge. 0.03 per net factor is modest by
    # design — we never let a couple of intraday reads imply strong conviction.
    net = bull - bear
    p = 0.50 + 0.03 * net

    # Historical base-rate lean: even weaker (0.015 each). Recorded as named
    # factors but only shown when there is already a structural lean — base rates
    # alone do not create a tradeable intraday edge.
    pat_lean = 0
    pat_names: list[str] = []
    for pf in (pattern_factors or []):
        pat_lean += getattr(pf, "direction", 0)
        pat_names.append(f"{getattr(pf, 'name', 'pattern')} — {getattr(pf, 'detail', '')} [weak/history]")
    p += 0.015 * pat_lean

    conviction = "None"
    verdict = "NO EDGE — WAIT"

    mid_range = pos is not None and 30 < pos < 70
    conflict = bull > 0 and bear > 0

    if fade_flag:
        factors.append("spike-fade flag present — continuation vetoed")
        verdict = "NO EDGE — WAIT"
        p = 0.50
    elif conflict or mid_range or net == 0:
        verdict = "NO EDGE — WAIT"
        p = 0.50
        if mid_range:
            factors.append("price mid opening-range — no-trade zone")
    elif net >= 2:
        verdict = "BULL LEAN"
        conviction = "Low" if net == 2 else "Medium"  # Medium needs >=3 confluence
    elif net <= -2:
        verdict = "BEAR LEAN"
        conviction = "Low" if net == -2 else "Medium"
    else:  # |net| == 1 -> too thin to call
        verdict = "NO EDGE — WAIT"
        p = 0.50

    # Medium conviction requires explicit multi-factor confluence; High is
    # UNAVAILABLE for intraday by design. Enforce that here.
    if conviction == "Medium" and abs(net) < 3:
        conviction = "Low"
    assert conviction in ("None", "Low", "Medium"), "High conviction is forbidden intraday"

    if verdict == "NO EDGE — WAIT":
        p = 0.50  # WAIT is always the honest coin flip — history doesn't override
    else:
        factors.extend(pat_names)  # surface history leans only when structure agrees

    # FINAL clamp — config bounds (prob_cfg) may narrow the band, never widen it.
    pc = prob_cfg or {}
    p = clamp_probability(p, floor=pc.get("floor", HARD_FLOOR), cap=pc.get("cap", HARD_CAP))

    return {
        "verdict": verdict,
        "probability": p,
        "conviction": conviction,
        "factors": factors,
        "bull": bull,
        "bear": bear,
    }


def build_levels(struct, orb, levels) -> dict:
    """
    The actionable output: invalidation + confirmation triggers + no-trade zone.
    Levels beat predictions — "wait for X to break/hold" is the deliverable.
    """
    open_ = struct.get("open")
    out = {
        "invalidation": None,
        "bull_trigger": None, "bull_target": None, "bull_trigger_level": None,
        "bear_trigger": None, "bear_target": None, "bear_trigger_level": None,
        "no_trade_zone": None,
    }
    if open_ is None:
        return out

    orb_hi = orb.get("orbN_high")
    orb_lo = orb.get("orbN_low")

    # Invalidation framed as an event, not a price guess.
    out["invalidation"] = (
        "5-min close back below the open after a long trigger "
        "(or above the open after a short)"
    )

    # A target must sit MEANINGFULLY beyond the trigger (>= 0.3%), otherwise the
    # hypothetical trade has ~0R reward — a bug caught in live use where a
    # resistance shelf equal to the ORB high produced "target 24.95 => 0.00R".
    MIN_TARGET_DIST = 0.003

    def _pick(cands, ref, above: bool):
        good = [c for c in cands if c is not None and
                ((c > ref * (1 + MIN_TARGET_DIST)) if above else (c < ref * (1 - MIN_TARGET_DIST)))]
        if not good:
            return None
        return min(good) if above else max(good)

    if orb_hi is not None:
        out["bull_trigger"] = f"break & 5-min hold above opening-range high {orb_hi:.2f}"
        out["bull_trigger_level"] = round(orb_hi, 4)
        out["bull_target"] = _pick(
            [*levels.get("resistance", []), levels.get("prior_high"), levels.get("high_52w")],
            orb_hi, above=True)
    if orb_lo is not None:
        out["bear_trigger"] = f"break & 5-min hold below opening-range low {orb_lo:.2f}"
        out["bear_trigger_level"] = round(orb_lo, 4)
        out["bear_target"] = _pick(
            [*levels.get("demand_shelves", []), levels.get("prior_low"), levels.get("low_52w")],
            orb_lo, above=False)
    if orb_hi is not None and orb_lo is not None:
        out["no_trade_zone"] = (orb_lo, orb_hi)
    return out


# ─────────────────────────────────────────────────────────────────────────────
# Holiday / weekday gate (for scheduled runs)
# ─────────────────────────────────────────────────────────────────────────────
def _nth_weekday(year: int, month: int, weekday: int, n: int) -> dt.date:
    """The n-th `weekday` (Mon=0) of a month. Pure + testable."""
    d = dt.date(year, month, 1)
    d += dt.timedelta(days=(weekday - d.weekday()) % 7)
    return d + dt.timedelta(weeks=n - 1)


def _easter(year: int) -> dt.date:
    """Anonymous Gregorian computus — Good Friday is Easter minus two days."""
    a, b, c = year % 19, year // 100, year % 100
    d, e = b // 4, b % 4
    f, g = (b + 8) // 25, (b - (b + 8) // 25 + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = c // 4, c % 4
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    month = (h + l - 7 * m + 114) // 31
    return dt.date(year, month, (h + l - 7 * m + 114) % 31 + 1)


def tsx_holidays(year: int) -> set:
    """TSX statutory closures for a year, computed rather than tabulated so it
    never expires. Weekend statutory days observe on the following Monday.

    WHY THIS EXISTS (day-26): `is_trading_day` depended on the OPTIONAL
    `pandas_market_calendars`, and on a machine where it was not installed the
    `except` branch returned True for EVERY weekday — so the Civic Holiday
    (2026-08-03) reported as a trading day. A safety check must not be one
    `pip install` away from silently returning the unsafe answer. Verified
    against pandas_market_calendars for 2024-2027. Pure + testable."""
    def observed(d):
        if d.weekday() == 5:
            return d + dt.timedelta(days=2)
        if d.weekday() == 6:
            return d + dt.timedelta(days=1)
        return d

    good_friday = _easter(year) - dt.timedelta(days=2)
    victoria = dt.date(year, 5, 25) - dt.timedelta(days=1)
    while victoria.weekday() != 0:                     # Monday before May 25
        victoria -= dt.timedelta(days=1)
    boxing = observed(dt.date(year, 12, 26))
    christmas = observed(dt.date(year, 12, 25))
    if boxing == christmas:                            # never collide
        boxing += dt.timedelta(days=1)
    return {
        observed(dt.date(year, 1, 1)),                 # New Year's Day
        _nth_weekday(year, 2, 0, 3),                   # Family Day
        good_friday,
        victoria,                                      # Victoria Day
        observed(dt.date(year, 7, 1)),                 # Canada Day
        _nth_weekday(year, 8, 0, 1),                   # Civic Holiday
        _nth_weekday(year, 9, 0, 1),                   # Labour Day
        _nth_weekday(year, 10, 0, 2),                  # Thanksgiving
        christmas,
        boxing,
    }


def is_trading_day(day: dt.date, exchange: str = "TSX") -> bool:
    """
    Skip weekends and exchange holidays. Prefers pandas_market_calendars when
    available; otherwise uses the built-in TSX table — NOT a bare weekday
    check, which silently called every holiday a trading day (day-26).
    """
    if day.weekday() >= 5:
        return False
    try:
        import pandas_market_calendars as mcal
        cal = mcal.get_calendar(exchange)
        return not cal.schedule(start_date=day, end_date=day).empty
    except Exception:
        if exchange.upper() in ("TSX", "TSXV", "XTSE"):
            return day not in tsx_holidays(day.year)
        return True     # unknown exchange: defer to the data guard


# ─────────────────────────────────────────────────────────────────────────────
# Rendering
# ─────────────────────────────────────────────────────────────────────────────
def _fmt(x, nd=2, suffix=""):
    if x is None:
        return "unavailable"
    if isinstance(x, float):
        return f"{x:.{nd}f}{suffix}"
    return f"{x}{suffix}"


def render(brief: dict, console=None):
    if _RICH and console is not None:
        _render_rich(brief, console)
    else:
        _render_plain(brief)


def _section(title):
    return f"\n{'═' * 70}\n{title}\n{'═' * 70}"


def _render_plain(b):
    g = b["guard"]
    print(_section("1. DATA INTEGRITY"))
    status = "PASS" if g.passed else "FAIL"
    print(f"  status      : {status}")
    print(f"  source      : {g.timestamps.get('source')}")
    print(f"  as-of       : {g.timestamps.get('as_of')}")
    print(f"  session     : {g.timestamps.get('session_date')}")
    if "age_min" in g.timestamps:
        print(f"  trade age   : {g.timestamps['age_min']:.1f} min")
    src = b.get("sources", {})
    if src.get("cross_check"):
        cq = ", ".join(f"{q['source']}={q['last']}" for q in src.get("cross_quotes", [])) or "none returned"
        print(f"  cross-check : {', '.join(src['cross_check'])}  ->  {cq}")
    if "source_conflict_pct" in g.timestamps:
        print(f"  src divergence: {g.timestamps['source_conflict_pct']:.2f}%")
    for r in g.reasons:
        print(f"  note        : {r}")

    if not g.passed:
        print("\n⚠ DATA NOT VERIFIED LIVE — " + "; ".join(g.reasons))
        print("  No directional read produced. Paste broker Level-1 to proceed")
        print("  (use --manual). Static reference below only.\n")
        _render_static(b)
        return

    d = b["decision"]
    print(_section("2. VERDICT"))
    print(f"  {d['verdict']}")
    print(_section("3. PROBABILITY (capped [0.35, 0.65])"))
    print(f"  p(close > open) = {d['probability']:.2f}   (default 0.50)")
    if d["factors"]:
        for f in d["factors"]:
            print(f"    • {f}")
    else:
        print("    • no named factor moved it off 0.50")
    print(_section("4. CONVICTION"))
    print(f"  {d['conviction']}   (High is unavailable intraday by design)")

    _render_static(b)


def _render_patterns(b):
    p = b.get("patterns") or {}
    if not p:
        return
    print(_section("9. HISTORICAL PATTERNS (base rates — context, not forecasts)"))
    print(f"  history analysed: {p.get('history_days', 0)} daily bars")

    g = p.get("gap_statistics", {})
    if g.get("available"):
        for key, label in [("gap_up", "after gap-up"), ("gap_down", "after gap-down")]:
            s = g.get(key, {})
            if s.get("n"):
                fill = f", fill {s['fill_rate_pct']}%" if s.get("fill_rate_pct") is not None else ""
                print(f"  {label:<15}: close>open {s['close_above_open_rate_pct']}%  "
                      f"avg {s['avg_oc_pct']}%{fill}  (n={s['n']}, {s['confidence']})")

    a = p.get("analog_days", {})
    if a.get("available"):
        print(f"  analog days    : {a['green_rate_pct']}% closed>open  "
              f"median {a['median_oc_pct']}%  range[{a['p25_oc_pct']}..{a['p75_oc_pct']}]%  "
              f"(n={a['n_neighbours']} similar setups; feats={','.join(a['features_used'])})")
        if a.get("off_sample"):
            print(f"  ⚠ OFF-SAMPLE   : {a['off_sample_reason']} — base rate UNRELIABLE today")
    elif a.get("reason"):
        print(f"  analog days    : unavailable — {a['reason']}")

    al = b.get("alignment")
    if al:
        tag = {"aligned-long": "✅ ALIGNED LONG", "aligned-short": "✅ ALIGNED SHORT",
               "conflicted": "⛔ CONFLICTED", "neutral": "· neutral",
               "aligned-but-off-sample": "⚠ ALIGNED BUT OFF-SAMPLE"}.get(al["alignment"], al["alignment"])
        print(f"  EOD alignment  : {tag} — {al['note']}")

    cr = p.get("crude_regime", {})
    if cr.get("available"):
        print(f"  crude regime   : {cr['regime']} (rolling corr {cr['rolling_corr']}, "
              f"{cr['window_days']}d; full {cr['full_sample_corr']})")

    print(f"  caveat         : {p.get('caveat', '')}")


def _render_static(b):
    s = b["struct"]; orb = b["orb"]; vw = b["vwap"]; sf = b["spike_fade"]
    print(_section("5. OPENING STRUCTURE"))
    print(f"  open {_fmt(s['open'])}  last {_fmt(s['last'])}  "
          f"prior close {_fmt(s['prior_close'])}")
    print(f"  gap {_fmt(s['gap_pct'],2,'%')}  vs open {_fmt(s['pct_vs_open'],2,'%')}  "
          f"vs prior close {_fmt(s['pct_vs_prior_close'],2,'%')}")
    print(f"  ORB(5m) {_fmt(orb['orbN_low'])}–{_fmt(orb['orbN_high'])}  "
          f"pos {_fmt(orb['pos_in_orb_pct'],0,'%')}")
    print(f"  VWAP {_fmt(vw['vwap'])}  price vs VWAP {_fmt(vw['price_vs_vwap_pct'],2,'%')}")
    print(f"  volume pace {_fmt(b['vol_pace'].get('pace'),2,'x')}  "
          f"(cum {_fmt(b['vol_pace'].get('cumulative'),0)} / ADV {_fmt(b['vol_pace'].get('adv'),0)})")
    print(f"  net-buy PROXY: {b['proxy']['value']}  [{b['proxy']['_label']}]")
    if sf["flags"]:
        for fl in sf["flags"]:
            print(f"  ⚑ {fl}")
    else:
        print("  spike-fade: no flags")

    lv = b["levels_actionable"]
    print(_section("6. LEVELS (the actionable part)"))
    print(f"  invalidation : {lv['invalidation']}")
    print(f"  bull trigger : {lv['bull_trigger']}")
    print(f"  bull target  : {_fmt(lv['bull_target'])}")
    print(f"  bear trigger : {lv['bear_trigger']}")
    print(f"  bear target  : {_fmt(lv['bear_target'])}")
    if lv["no_trade_zone"]:
        lo, hi = lv["no_trade_zone"]
        print(f"  NO-TRADE zone: {lo:.2f}–{hi:.2f} (mid opening range)")

    c = b["context"]
    print(_section("7. CONTEXT (context only — NOT signals)"))
    print(f"  crude (WTI)  : {_fmt(c.get('crude'),2,'%')}   <-- dominant fuel lever")
    print(f"  TSX          : {_fmt(c.get('tsx'),2,'%')}")
    print(f"  CAD/USD      : {_fmt(c.get('cadusd'),2,'%')}")
    print(f"  VIX          : {_fmt(c.get('vix'),2,'%')}")
    print(f"  peer avg     : {_fmt(c.get('peer_avg'),2,'%')}")
    rel = b["rel_strength"]
    print(f"  rel strength : vs TSX {rel['vs_tsx']} | vs peers {rel['vs_peers']}")

    rp = b.get("risk_plan")
    print(_section("8. RISK (hypothetical trigger->stop; read-only)"))
    if rp is None:
        print("  no level pair available to size a hypothetical trade")
    else:
        print(f"  side {rp.side}  entry {rp.entry:.2f}  stop {rp.stop:.2f}  "
              f"stop dist {rp.stop_distance:.2f}")
        print(f"  risk ${rp.risk_dollars:.2f}  -> {rp.shares} shares  "
              f"(position ${rp.position_value:,.0f})")
        for name, lvl, r in rp.r_multiples:
            print(f"    target {name} {lvl:.2f}  =>  {r:.2f}R")
        print(f"  overnight margin cost/day: {_fmt(rp.overnight_margin_cost,2,' $')}")
        for g_pct, impact in rp.gap_risk:
            print(f"    gap {g_pct:.0f}% against -> ${impact:,.0f} on position")

    _render_patterns(b)

    if b.get("analyst") is not None:
        a = b["analyst"]
        title = "10. CLAUDE ANALYST (advisory context — does NOT set the verdict)"
        print(_section(title))
        if getattr(a, "enabled", False):
            print(f"  [model: {a.model}]")
            for line in a.text.splitlines():
                print(f"  {line}" if line.strip() else "")
        else:
            print(f"  {a.text}")

    if b.get("headlines"):
        print(_section("11. HEADLINES (context, NOT signal)"))
        for h in b["headlines"][:3]:
            print(f"  • {h}")

    print(f"\n(brief generated {b['generated_at']}  |  every number is as-of its source time)")
    print("Read-only tool. It never places orders.\n")


def _render_rich(b, console):
    g = b["guard"]
    color = "green" if g.passed else "red"
    head = Text(f"PRE-OPEN BRIEF — {b['ticker']}", style="bold")
    console.print(Panel(head, style=color))

    t = Table(title="1. DATA INTEGRITY", show_header=False)
    t.add_row("status", "[green]PASS[/green]" if g.passed else "[red]FAIL[/red]")
    t.add_row("source", str(g.timestamps.get("source")))
    t.add_row("as-of", str(g.timestamps.get("as_of")))
    t.add_row("session", str(g.timestamps.get("session_date")))
    if "age_min" in g.timestamps:
        t.add_row("trade age", f"{g.timestamps['age_min']:.1f} min")
    for r in g.reasons:
        t.add_row("note", r)
    console.print(t)

    if not g.passed:
        console.print(Panel(
            "⚠ DATA NOT VERIFIED LIVE — " + "; ".join(g.reasons) +
            "\nNo directional read produced. Paste broker Level-1 (--manual) to proceed.",
            style="bold red",
        ))
        # Fall back to plain static reference (kept DRY).
        _render_static(b)
        return

    d = b["decision"]
    vcolor = {"BULL LEAN": "green", "BEAR LEAN": "red"}.get(d["verdict"], "yellow")
    console.print(Panel(f"2. VERDICT: [bold]{d['verdict']}[/bold]", style=vcolor))
    pt = Table(title="3. PROBABILITY (capped [0.35, 0.65])", show_header=False)
    pt.add_row("p(close > open)", f"{d['probability']:.2f}  (default 0.50)")
    for f in (d["factors"] or ["no named factor moved it off 0.50"]):
        pt.add_row("factor", f)
    console.print(pt)
    console.print(Panel(
        f"4. CONVICTION: [bold]{d['conviction']}[/bold]  "
        f"(High is unavailable intraday by design)", style="cyan"))

    # Static sections reuse the plain renderer for brevity & single source.
    _render_static(b)


# ─────────────────────────────────────────────────────────────────────────────
# Orchestration
# ─────────────────────────────────────────────────────────────────────────────
def load_config(path: str) -> dict:
    with open(path) as f:
        return yaml.safe_load(f)


def parse_hhmm(s: str) -> dt.time:
    h, m = s.split(":")
    return dt.time(int(h), int(m))


def safe_pct_change(adapter: DataAdapter, ticker: str, tz: str) -> Optional[float]:
    """Today's %change for a correlated ticker, freshness-checked individually."""
    try:
        q = adapter.get_quote_simple(ticker)
        if q.last is None or q.prior_close is None:
            return None
        # Individual freshness: if the bar is from a prior day, skip it.
        today = dt.datetime.now(ZoneInfo(tz)).date()
        if q.session_date is not None and q.session_date != today:
            return None
        return metrics.pct(q.last, q.prior_close)
    except Exception:
        return None


def run_once(config: dict, adapter_name: str, manual_kwargs: Optional[dict],
             show_headlines: bool, run_analyst: bool = False) -> dict:
    tz = config["exchange_tz"]
    now = dt.datetime.now(ZoneInfo(tz))
    ticker = config["ticker"]
    mkt_open = parse_hhmm(config["market_open"])
    mkt_close = parse_hhmm(config["market_close"])

    # Multi-source: primary serves metrics, cross-check sources feed the guard.
    cross_check = config.get("data_sources", {}).get("cross_check") if adapter_name != "manual" else None
    adapter = build_adapter(adapter_name, exchange_tz=tz, manual_kwargs=manual_kwargs,
                            cross_check=cross_check)
    quote = adapter.get_quote(ticker)

    # If a multi-source adapter found an independent quote, hand it to the guard.
    second_quote = adapter.best_cross_quote() if isinstance(adapter, MultiSourceAdapter) else None

    # ── GUARD RUNS FIRST ──────────────────────────────────────────────────
    guard = data_integrity_guard(
        quote, now=now, exchange_tz=tz,
        market_open=mkt_open, market_close=mkt_close,
        max_stale_minutes=config["guard"]["max_stale_minutes"],
        second_quote=second_quote,
        source_conflict_pct=config["guard"]["source_conflict_pct"],
    )

    # Bars (may be empty for manual mode — everything degrades gracefully).
    try:
        intraday = adapter.get_intraday_bars(ticker, "1m")
    except Exception:
        intraday = pd.DataFrame()
    try:
        daily = adapter.get_daily_bars(ticker, config["levels"]["daily_lookback_days"])
    except Exception:
        daily = pd.DataFrame()

    struct = metrics.structure(quote)
    orb = metrics.opening_range(intraday, quote.last, config["levels"]["orb_minutes"])
    vw = metrics.vwap(intraday, quote.last)
    cum_vol = float(intraday["Volume"].sum()) if not intraday.empty else quote.volume
    adv = metrics.average_daily_volume(daily)
    vol_pace = metrics.volume_pace(cum_vol, adv, now, mkt_open, mkt_close)
    momo = metrics.momentum(daily, intraday)
    levels = metrics.key_levels(daily, config["levels"]["swing_lookback_days"])
    sf = metrics.spike_fade(intraday, quote.open, config["levels"]["spike_fade_window_min"])
    proxy = metrics.net_buy_proxy(struct, vw)

    # Context (each correlated ticker freshness-checked individually).
    corr = config["correlated"]
    ac_pct = struct.get("pct_vs_prior_close")
    peers = [safe_pct_change(adapter, p, tz) for p in corr["airline_peers"]]
    peers_valid = [p for p in peers if p is not None]
    peer_avg = sum(peers_valid) / len(peers_valid) if peers_valid else None
    context = {
        "crude": safe_pct_change(adapter, corr["crude"], tz),
        "tsx": safe_pct_change(adapter, corr["tsx"], tz),
        "cadusd": safe_pct_change(adapter, corr["cadusd"], tz),
        "vix": safe_pct_change(adapter, corr["vix"], tz),
        "peer_avg": peer_avg,
    }
    rel = metrics.relative_strength(ac_pct, context["tsx"], peer_avg)

    # ── DEEP HISTORICAL PATTERNS ──────────────────────────────────────────
    # Use as much history as the source returns. Crude daily bars power the
    # fuel-cost correlation regime. Every stat is a sample-sized base rate.
    pat = {}
    if config.get("patterns", {}).get("enabled", True):
        try:
            crude_daily = adapter.get_daily_bars(corr["crude"], config["levels"]["daily_lookback_days"])
        except Exception:
            crude_daily = pd.DataFrame()
        today_pos = _pos_in_trailing_range(daily, quote.last)
        prev_oc = None
        if not daily.empty and len(daily) >= 2 and "Open" in daily:
            p = daily.iloc[-1]
            if p["Open"]:
                prev_oc = (p["Close"] - p["Open"]) / p["Open"] * 100
        pat = patterns.analyze(
            daily, crude_daily,
            today_gap_pct=struct.get("gap_pct"),
            today_prev_oc_pct=prev_oc,
            today_pos_in_range_pct=today_pos,
            analog_cfg=config.get("analogs"),
        )

    decision = decide(struct, orb, vw, sf, rel, momo,
                      pattern_factors=pat.get("factors") if pat else None,
                      prob_cfg=config.get("probability"))
    levels_actionable = build_levels(struct, orb, levels)

    # EOD confluence check across the three lenses (lesson from today's losses).
    analog = (pat or {}).get("analog_days", {})
    alignment = metrics.eod_alignment(
        decision["verdict"], analog.get("green_rate_pct"),
        off_sample=bool(analog.get("off_sample")))

    # Hypothetical risk plan (only if guard passed AND we have a level pair).
    risk_plan = None
    if guard.passed:
        risk_plan = _maybe_risk_plan(config, decision, levels_actionable, struct, orb, levels)

    headlines = _maybe_headlines(ticker) if show_headlines else None

    brief = {
        "ticker": ticker,
        "generated_at": now.isoformat(timespec="seconds"),
        "guard": guard,
        "struct": struct,
        "orb": orb,
        "vwap": vw,
        "vol_pace": vol_pace,
        "momentum": momo,
        "spike_fade": sf,
        "proxy": proxy,
        "levels_actionable": levels_actionable,
        "context": context,
        "rel_strength": rel,
        "decision": decision,
        "patterns": pat,
        "alignment": alignment,
        "risk_plan": risk_plan,
        "headlines": headlines,
        "sources": _describe_sources(adapter),
    }

    # ── CLAUDE ANALYST (advisory context only; never overrides the verdict) ──
    ccfg = config.get("claude", {})
    if run_analyst and ccfg.get("enabled", True):
        brief["analyst"] = analyst.analyze(
            brief, model=ccfg.get("model", "claude-opus-4-8"),
            max_tokens=ccfg.get("max_tokens", 1500), enabled=True,
        )
    return brief


def _pos_in_trailing_range(daily: pd.DataFrame, last: Optional[float], window: int = 20):
    """Where `last` sits within the trailing N-day range (0=low,100=high)."""
    if daily is None or daily.empty or last is None or "Low" not in daily:
        return None
    win = daily.tail(window)
    lo, hi = float(win["Low"].min()), float(win["High"].max())
    if hi <= lo:
        return None
    return (last - lo) / (hi - lo) * 100.0


def _describe_sources(adapter) -> dict:
    """Human-readable summary of which sources fed this brief."""
    if isinstance(adapter, MultiSourceAdapter):
        return {
            "primary": adapter.primary.name,
            "cross_check": [a.name for a in adapter.cross_check],
            "cross_quotes": [
                {"source": q.source, "last": q.last} for q in adapter.last_cross_quotes
            ],
        }
    return {"primary": adapter.name, "cross_check": [], "cross_quotes": []}


def _maybe_risk_plan(config, decision, lv, struct, orb, levels):
    """Size a HYPOTHETICAL trade at the verdict's trigger with stop = invalidation."""
    rcfg = config["risk"]
    open_ = struct.get("open")
    if open_ is None:
        return None

    if decision["verdict"] == "BULL LEAN" and orb.get("orbN_high"):
        entry = orb["orbN_high"]
        stop = open_                 # invalidation: back below open
        side = "long"
        targets = [("bull target", lv.get("bull_target")), ("52w high", levels.get("high_52w"))]
    elif decision["verdict"] == "BEAR LEAN" and orb.get("orbN_low"):
        entry = orb["orbN_low"]
        stop = open_
        side = "short"
        targets = [("bear target", lv.get("bear_target")), ("52w low", levels.get("low_52w"))]
    else:
        # WAIT: still illustrate a long-bias bracket off the opening range so the
        # user sees the risk math, but only if levels exist.
        if not orb.get("orbN_high") or not orb.get("orbN_low"):
            return None
        entry = orb["orbN_high"]
        stop = orb["orbN_low"]
        side = "long"
        targets = [("bull target", lv.get("bull_target"))]

    if entry is None or stop is None or entry == stop:
        return None
    return risk.build_full_plan(
        account_equity=rcfg["account_equity"],
        risk_per_trade_pct=rcfg["risk_per_trade_pct"],
        entry=entry, stop=stop, side=side, targets=targets,
        is_margin=rcfg["is_margin"], cad_prime=rcfg["cad_prime"],
        margin_spread=rcfg["margin_spread"],
        max_position_pct=rcfg.get("max_position_pct", 100.0),
    )


def _maybe_headlines(ticker):
    """Top 3 headlines via yfinance.news. Tagged context, not signal. None on fail."""
    try:
        import yfinance
        news = yfinance.Ticker(ticker).news or []
        titles = []
        for n in news[:3]:
            t = n.get("title") or (n.get("content") or {}).get("title")
            if t:
                titles.append(t)
        return titles or None
    except Exception:
        return None


# ─────────────────────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────────────────────
def build_arg_parser():
    p = argparse.ArgumentParser(description="Pre-Open Brief — intraday decision support (read-only)")
    p.add_argument("--config", default="config.yaml")
    p.add_argument("--ticker", default=None, help="override config ticker")
    p.add_argument("--source", default=None,
                   choices=["yahoo_direct", "yahoo", "yahoo_yf", "stooq", "finnhub",
                            "twelvedata", "manual", "ibkr", "questrade", "polygon", "alpaca"],
                   help="primary data source (default: config data_sources.primary)")
    p.add_argument("--cross-check", default=None,
                   help="comma-separated cross-check sources (override config)")
    p.add_argument("--analyst", dest="analyst", action="store_true", default=None,
                   help="force-enable the Claude analyst layer")
    p.add_argument("--no-analyst", dest="analyst", action="store_false",
                   help="disable the Claude analyst layer")
    p.add_argument("--once", action="store_true", help="run a single brief now and exit")
    p.add_argument("--schedule", action="store_true",
                   help="run continuously, firing at 09:31 exchange-tz on trading days")
    p.add_argument("--headlines", action="store_true", help="include top-3 headlines")
    p.add_argument("--no-rich", action="store_true", help="force plain text output")

    # Manual broker Level-1 override (bypasses staleness fail; tagged manual).
    p.add_argument("--manual", action="store_true", help="paste broker Level-1 numbers")
    p.add_argument("--m-open", type=float)
    p.add_argument("--m-last", type=float)
    p.add_argument("--m-high", type=float)
    p.add_argument("--m-low", type=float)
    p.add_argument("--m-volume", type=float)
    p.add_argument("--m-prior-close", type=float)
    return p


def collect_manual(args) -> dict:
    missing = [k for k in ("m_open", "m_last", "m_high", "m_low", "m_volume")
               if getattr(args, k) is None]
    if missing:
        raise SystemExit(
            "manual mode needs --m-open --m-last --m-high --m-low --m-volume "
            f"(missing: {', '.join(missing)})"
        )
    return dict(
        open=args.m_open, last=args.m_last, high=args.m_high,
        low=args.m_low, volume=args.m_volume, prior_close=args.m_prior_close,
    )


def main(argv=None):
    args = build_arg_parser().parse_args(argv)
    config = load_config(args.config)
    if args.ticker:
        config["ticker"] = args.ticker

    # Source: CLI --source wins, else config data_sources.primary, else yahoo_direct.
    source = args.source or config.get("data_sources", {}).get("primary", "yahoo_direct")
    adapter_name = "manual" if args.manual else source
    manual_kwargs = collect_manual(args) if adapter_name == "manual" else None

    # Cross-check override.
    if args.cross_check is not None:
        config.setdefault("data_sources", {})["cross_check"] = [
            s.strip() for s in args.cross_check.split(",") if s.strip()
        ]

    # Analyst: CLI flag wins, else config claude.enabled.
    run_analyst = args.analyst if args.analyst is not None else config.get("claude", {}).get("enabled", False)

    console = None if (args.no_rich or not _RICH) else Console()

    def fire():
        brief = run_once(config, adapter_name, manual_kwargs, args.headlines, run_analyst)
        render(brief, console)
        return brief

    if args.schedule:
        _run_scheduled(config, fire)
    else:
        fire()  # default + --once both produce one brief
    return 0


def _run_scheduled(config, fire):
    """
    Continuous mode: fire once at 09:31 exchange-tz on trading days.
    A system cron is the more robust option (see README); this is the
    dependency-light fallback using the `schedule` library.
    """
    try:
        import schedule
    except Exception:
        raise SystemExit("--schedule needs the `schedule` package (pip install schedule)")
    import time

    tz = config["exchange_tz"]

    def guarded_fire():
        today = dt.datetime.now(ZoneInfo(tz)).date()
        if not is_trading_day(today, "TSX"):
            print(f"[{today}] market holiday/weekend — skipping brief")
            return
        fire()

    # schedule runs in local server time; we fire at 09:31 and let the brief's
    # own tz handling + the data guard keep it honest about the session.
    schedule.every().day.at("09:31").do(guarded_fire)
    print("scheduled: 09:31 (server local time) on trading days. Ctrl-C to stop.")
    while True:
        schedule.run_pending()
        time.sleep(20)


if __name__ == "__main__":
    sys.exit(main())
