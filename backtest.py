#!/usr/bin/env python3
"""
backtest.py — honest, lookahead-safe evaluation of the Pre-Open Brief.

WHAT WE ARE MEASURING
    The tool predicts intraday open-to-close DIRECTION (will today close above
    its open?) and, more importantly, when to say NO EDGE — WAIT. So the
    backtest scores: directional hit rate on the days it leaned, probability
    calibration, and how those compare to the naive baselines (always-up and a
    coin flip). A tool built to resist false confidence should look *honest*
    here — near coin-flip with good calibration — not magically accurate.

AVOIDING HINDSIGHT / LOOKAHEAD BIAS (the explicit requirement) — how:
    1. EXPANDING WINDOW. For day t, every statistic (analogs, gap base rates) is
       computed from days STRICTLY BEFORE t. Day t is never in its own candidate
       pool, so its outcome can't leak into its prediction.
    2. DECISION-TIME INFORMATION ONLY. The decision uses only what's knowable at
       9:31–9:35: today's open, the first 1–5 minutes of bars (Tier B), the gap
       vs prior close, and prior days. Today's HIGH / LOW / CLOSE are never read
       when forming the call — only when scoring it afterward.
    3. NO TUNING ON TEST DATA. Thresholds/clamps are the shipped defaults; we do
       not fit anything to the evaluation set.
    4. HONEST DATA LIMITS. Free feeds only return ~7 days of 1-minute bars, so
       the full intraday engine (ORB/VWAP/spike-fade) can only be replayed over
       a handful of recent days (Tier B, flagged anecdotal). The long history
       (Tier A) can only test the daily-derivable pattern engine. We do NOT
       fabricate intraday history to pad the sample.

USAGE
    python backtest.py                 # AC.TO, full available daily history
    python backtest.py --ticker XOM --days 750
"""

from __future__ import annotations

import argparse
import math
from dataclasses import dataclass
from typing import Optional

import numpy as np
import pandas as pd

import metrics
import patterns
from adapters import YahooDirectAdapter
from dashboard import _pos_in_trailing_range, clamp_probability, decide


# ─────────────────────────────────────────────────────────────────────────────
# Scoring helpers
# ─────────────────────────────────────────────────────────────────────────────
@dataclass
class Sample:
    p_up: float          # predicted P(close > open), already clamped
    realized_up: bool    # did it actually close above open?
    leaned: bool         # did the engine commit to a side (not WAIT)?
    direction: int       # +1 / -1 / 0 (0 = WAIT)


def brier(samples: list[Sample]) -> float:
    """Mean squared error of probability vs outcome. 0.25 = always saying 0.50."""
    if not samples:
        return float("nan")
    return float(np.mean([(s.p_up - (1.0 if s.realized_up else 0.0)) ** 2 for s in samples]))


def binom_p_value(hits: int, n: int, p0: float = 0.5) -> float:
    """Two-sided test that hit rate != p0. Exact for small n, normal approx for
    large n (exact binomial overflows floats for n in the hundreds)."""
    if n == 0:
        return float("nan")
    if n <= 60:
        from math import comb
        obs = abs(hits - n * p0)
        tail = sum(comb(n, k) * (p0 ** k) * ((1 - p0) ** (n - k))
                   for k in range(n + 1) if abs(k - n * p0) >= obs - 1e-9)
        return min(1.0, tail)
    # Normal approximation with continuity correction.
    mu = n * p0
    sd = math.sqrt(n * p0 * (1 - p0))
    z = (abs(hits - mu) - 0.5) / sd
    return round(min(1.0, math.erfc(z / math.sqrt(2))), 4)


def calibration_table(samples: list[Sample], bins=((0.35, 0.45), (0.45, 0.55), (0.55, 0.65))):
    rows = []
    for lo, hi in bins:
        grp = [s for s in samples if lo <= s.p_up < hi or (hi == 0.65 and s.p_up == 0.65)]
        if not grp:
            rows.append((lo, hi, 0, None, None))
            continue
        pred = np.mean([s.p_up for s in grp])
        real = np.mean([1.0 if s.realized_up else 0.0 for s in grp])
        rows.append((lo, hi, len(grp), pred, real))
    return rows


# ─────────────────────────────────────────────────────────────────────────────
# Tier A — daily, long history, expanding window. Tests the PATTERN engine.
#
# At 9:31 with only daily data available historically, the intraday structural
# signals (ORB/VWAP/spike-fade) don't exist, so the live tool would WAIT almost
# every day. Tier A therefore isolates one question that *is* answerable over
# long history without lookahead: do the deep-history ANALOG base rates predict
# open-to-close direction out of sample, or are they coin-flips?
# ─────────────────────────────────────────────────────────────────────────────
def tier_a_samples(daily: pd.DataFrame, warmup: int = 120, shrinkage: float = 1.0):
    """Per-day samples for Tier A. Factored out so a test can prove that a
    prediction for day t is invariant to any data after t (no lookahead).

    `shrinkage` maps the analog green%% to the stated probability via
    patterns.eod_probability (1.0 = raw legacy behaviour; the shipped config
    uses a compressive value because the raw probabilities measured as
    overconfident — see README)."""
    df = daily.dropna(subset=["Open", "High", "Low", "Close"]).copy()
    samples: list[Sample] = []
    base_up = 0
    n_days = 0

    for t in range(warmup, len(df)):
        hist = df.iloc[:t]                       # STRICTLY prior — no leakage
        open_t = float(df["Open"].iloc[t])
        close_t = float(df["Close"].iloc[t])
        prev_close = float(df["Close"].iloc[t - 1])
        prev_open = float(df["Open"].iloc[t - 1])
        if prev_close == 0 or prev_open == 0:
            continue

        gap = (open_t - prev_close) / prev_close * 100
        prev_oc = (prev_close - prev_open) / prev_open * 100
        pos = _pos_in_trailing_range(hist, open_t)   # uses open (known at 9:31)

        a = patterns.analog_days(hist, today_gap_pct=gap, today_prev_oc_pct=prev_oc,
                                 today_pos_in_range_pct=pos)
        n_days += 1
        realized_up = close_t > open_t
        base_up += int(realized_up)
        if not a.get("available"):
            continue

        # Map the analog green-rate to a probability through the SAME calibrated
        # pipeline the live tool uses (smoothing happened inside analog_days;
        # shrinkage + hard clamp happen here).
        p_up = patterns.eod_probability(a["green_rate_pct"], shrinkage=shrinkage)
        direction = +1 if p_up > 0.5 else (-1 if p_up < 0.5 else 0)
        samples.append(Sample(p_up, realized_up, direction != 0, direction))

    return samples, base_up, n_days


def tier_a(daily: pd.DataFrame, warmup: int = 120, shrinkage: float = 1.0) -> dict:
    samples, base_up, n_days = tier_a_samples(daily, warmup, shrinkage=shrinkage)
    leans = [s for s in samples if s.leaned]
    hits = sum(1 for s in leans if (s.direction > 0) == s.realized_up)
    return {
        "days_evaluated": n_days,
        "base_rate_up_pct": round(base_up / n_days * 100, 1) if n_days else None,
        "predictions": len(samples),
        "leans": len(leans),
        "lean_hits": hits,
        "lean_hit_rate_pct": round(hits / len(leans) * 100, 1) if leans else None,
        "lean_pvalue_vs_coinflip": round(binom_p_value(hits, len(leans)), 3) if leans else None,
        "brier": round(brier(samples), 4) if samples else None,
        "brier_baseline_always_0.50": 0.25,
        "calibration": calibration_table(samples),
    }


# ─────────────────────────────────────────────────────────────────────────────
# Tier B — full intraday engine over the last ~7 days of 1-minute bars.
# Faithfully replays the real brief at 9:35 (first 5 one-minute bars only).
# Small sample by necessity — flagged anecdotal, never padded.
# ─────────────────────────────────────────────────────────────────────────────
def tier_b(adapter: YahooDirectAdapter, ticker: str, orb_minutes: int = 5) -> dict:
    try:
        # Pull the maximum 1-minute history the free feed allows (~7 days),
        # not just today, so Tier B has more than one session to replay.
        bars = adapter._bars_df(adapter._chart(ticker, "1m", "7d"))
    except Exception as e:
        return {"available": False, "reason": f"intraday fetch failed: {e}"}
    if bars is None or bars.empty:
        return {"available": False, "reason": "no intraday bars returned"}

    bars = bars.copy()
    bars["date"] = bars.index.date
    samples: list[Sample] = []
    per_day = []

    for d, day in bars.groupby("date"):
        day = day.sort_index()
        if len(day) < orb_minutes + 1:
            continue
        decision_bars = day.iloc[:orb_minutes]            # only 9:30–9:35 known
        open_t = float(day["Open"].iloc[0])
        last_at_decision = float(decision_bars["Close"].iloc[-1])
        close_t = float(day["Close"].iloc[-1])            # used ONLY for scoring

        struct = {"open": open_t, "last": last_at_decision, "prior_close": open_t,
                  "high": None, "low": None, "volume": None}
        orb = metrics.opening_range(decision_bars, last_at_decision, orb_minutes)
        vw = metrics.vwap(decision_bars, last_at_decision)
        sf = metrics.spike_fade(decision_bars, open_t, orb_minutes)
        d_out = decide(struct, orb, vw, sf, {}, {})

        realized_up = close_t > open_t
        direction = (+1 if d_out["verdict"] == "BULL LEAN"
                     else -1 if d_out["verdict"] == "BEAR LEAN" else 0)
        samples.append(Sample(d_out["probability"], realized_up, direction != 0, direction))
        per_day.append((str(d), d_out["verdict"], round(d_out["probability"], 2),
                        "UP" if realized_up else "DOWN"))

    leans = [s for s in samples if s.leaned]
    hits = sum(1 for s in leans if (s.direction > 0) == s.realized_up)
    return {
        "available": True,
        "days": len(samples),
        "leans": len(leans),
        "lean_hits": hits,
        "lean_hit_rate_pct": round(hits / len(leans) * 100, 1) if leans else None,
        "wait_days": len(samples) - len(leans),
        "per_day": per_day,
        "note": "ANECDOTAL — only ~7 days of 1-min history exist on the free feed.",
    }


# ─────────────────────────────────────────────────────────────────────────────
def run(ticker: str, exchange_tz: str, lookback_days: int, shrinkage: float = 1.0) -> dict:
    adapter = YahooDirectAdapter(exchange_tz=exchange_tz)
    daily = adapter.get_daily_bars(ticker, lookback_days)
    a = tier_a(daily, shrinkage=shrinkage) if not daily.empty else {"error": "no daily data"}
    b = tier_b(adapter, ticker)
    return {"ticker": ticker, "daily_bars": int(len(daily)), "tier_a": a, "tier_b": b}


def _print(report: dict):
    print("=" * 74)
    print(f"BACKTEST — {report['ticker']}   ({report['daily_bars']} daily bars available)")
    print("=" * 74)
    print("Anti-lookahead: expanding window (day t uses only days < t); decisions")
    print("use only open + first 1-5 min + prior days; today's H/L/C used only to")
    print("score, never to decide; no tuning on test data.\n")

    a = report["tier_a"]
    print("-" * 74)
    print("TIER A — pattern/analog engine, long history, open-to-close direction")
    print("-" * 74)
    if "error" in a:
        print(f"  {a['error']}")
    else:
        print(f"  days evaluated        : {a['days_evaluated']}")
        print(f"  base rate (close>open): {a['base_rate_up_pct']}%   "
              f"(naive 'always up' hit rate)")
        print(f"  engine predictions    : {a['predictions']}  (leaned on {a['leans']})")
        print(f"  directional hit rate  : {a['lean_hit_rate_pct']}%  on leaned days")
        print(f"  vs coin flip (p-value): {a['lean_pvalue_vs_coinflip']}  "
              f"(>0.05 ⇒ indistinguishable from chance)")
        print(f"  Brier score           : {a['brier']}  "
              f"(baseline always-0.50 = {a['brier_baseline_always_0.50']}; lower is better)")
        print("  calibration (predicted vs realized P(up)):")
        for lo, hi, n, pred, real in a["calibration"]:
            if n == 0:
                print(f"    p∈[{lo:.2f},{hi:.2f}): n=0")
            else:
                print(f"    p∈[{lo:.2f},{hi:.2f}): n={n:<4} predicted {pred:.2f}  realized {real:.2f}")

    b = report["tier_b"]
    print("\n" + "-" * 74)
    print("TIER B — FULL intraday engine replayed at 9:35 (first 5 one-min bars)")
    print("-" * 74)
    if not b.get("available"):
        print(f"  unavailable — {b.get('reason')}")
    else:
        print(f"  {b['note']}")
        print(f"  days replayed : {b['days']}   leaned: {b['leans']}   WAIT: {b['wait_days']}")
        if b["leans"]:
            print(f"  hit rate on leans: {b['lean_hit_rate_pct']}%  ({b['lean_hits']}/{b['leans']})")
        for day, verdict, p, real in b["per_day"]:
            print(f"    {day}  {verdict:<14} p={p:.2f}  actual={real}")

    print("\n" + "=" * 74)
    print("READING IT: a tool built to resist false confidence SHOULD look near")
    print("coin-flip with honest calibration and mostly-WAIT — that is the design")
    print("working, not failing. A high hit rate here would more likely mean a")
    print("lookahead bug than a real edge. Open-to-close on one name is ~random.")
    print("=" * 74)


def main(argv=None):
    p = argparse.ArgumentParser(description="Lookahead-safe backtest of the Pre-Open Brief")
    p.add_argument("--ticker", default="AC.TO")
    p.add_argument("--exchange-tz", default="America/Toronto")
    p.add_argument("--days", type=int, default=2000, help="daily history to request")
    p.add_argument("--shrinkage", type=float, default=0.5,
                   help="probability shrinkage toward 0.5 (1.0 = raw legacy)")
    args = p.parse_args(argv)
    _print(run(args.ticker, args.exchange_tz, args.days, shrinkage=args.shrinkage))


if __name__ == "__main__":
    main()
