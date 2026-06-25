"""
patterns.py — deep historical pattern mining over as much history as the data
source provides.

PURPOSE (per the request): surface base-rate patterns that a casual reader
wouldn't compute by hand — gap-fill tendencies, day-of-week seasonality,
opening-drive follow-through, "analog days" (historically similar setups and
what they did next), and the crude-oil correlation regime.

HONESTY CONSTRAINTS (do not strip):
    * Every statistic is a BASE RATE with its SAMPLE SIZE attached. A pattern
      computed on 6 days is labelled low-confidence; we never dress up a small
      sample as an edge.
    * These are CONTEXT. They may nudge the capped probability only as named
      factors, and never past the [0.35, 0.65] clamp. They are not predictions.
    * Nothing is fabricated. If history is too short, the field says so.
    * Survivorship / regime caveat is stated in the output: the past is not the
      future, and a base rate is not a setup-specific forecast.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

import numpy as np
import pandas as pd


# Minimum samples before we treat a base rate as anything but anecdotal.
MIN_CONFIDENT_N = 30


def _confidence(n: int) -> str:
    if n >= 100:
        return "ok"
    if n >= MIN_CONFIDENT_N:
        return "low"
    return "anecdotal"


def _daily_oc(daily: pd.DataFrame) -> pd.DataFrame:
    """Add open->close %, gap %, prior-day-move %, and weekday columns."""
    df = daily.copy()
    if df.empty or "Open" not in df:
        return df
    df = df.dropna(subset=["Open", "Close"])
    df["oc_pct"] = (df["Close"] - df["Open"]) / df["Open"] * 100
    df["prev_close"] = df["Close"].shift(1)
    df["gap_pct"] = (df["Open"] - df["prev_close"]) / df["prev_close"] * 100
    df["prev_oc"] = df["oc_pct"].shift(1)
    df["co_pct"] = (df["Close"] - df["prev_close"]) / df["prev_close"] * 100  # close-to-close
    if isinstance(df.index, pd.DatetimeIndex):
        df["weekday"] = df.index.dayofweek
    return df


# ─────────────────────────────────────────────────────────────────────────────
# Gap behaviour: when AC opens with a gap, does it tend to FILL (fade toward
# prior close) or CONTINUE? Split by gap direction.
# ─────────────────────────────────────────────────────────────────────────────
def gap_statistics(daily: pd.DataFrame, gap_threshold: float = 0.5) -> dict:
    out = {"_label": "base rates — context, not a forecast", "available": False}
    df = _daily_oc(daily)
    if df.empty or "gap_pct" not in df:
        return out
    df = df.dropna(subset=["gap_pct", "oc_pct", "prev_close"])

    def summarize(sub: pd.DataFrame) -> dict:
        n = len(sub)
        if n == 0:
            return {"n": 0}
        # "Fill" = price traded back through prior close intraday. We approximate
        # with: gap-up days whose LOW <= prior close (or gap-down whose HIGH >=).
        fills = 0
        if "Low" in sub and "High" in sub:
            up = sub[sub["gap_pct"] > 0]
            dn = sub[sub["gap_pct"] < 0]
            fills = int((up["Low"] <= up["prev_close"]).sum() +
                        (dn["High"] >= dn["prev_close"]).sum())
        green = int((sub["oc_pct"] > 0).sum())
        return {
            "n": n,
            "confidence": _confidence(n),
            "fill_rate_pct": round(fills / n * 100, 1) if ("Low" in sub) else None,
            "close_above_open_rate_pct": round(green / n * 100, 1),
            "avg_oc_pct": round(float(sub["oc_pct"].mean()), 3),
            "median_oc_pct": round(float(sub["oc_pct"].median()), 3),
        }

    out.update({
        "available": True,
        "gap_threshold_pct": gap_threshold,
        "gap_up": summarize(df[df["gap_pct"] >= gap_threshold]),
        "gap_down": summarize(df[df["gap_pct"] <= -gap_threshold]),
        "flat_open": summarize(df[df["gap_pct"].abs() < gap_threshold]),
        "total_days": len(df),
    })
    return out


# ─────────────────────────────────────────────────────────────────────────────
# Day-of-week seasonality of open-to-close. Mostly noise on single names — we
# compute it AND say so, so the reader can see how thin any "edge" is.
# ─────────────────────────────────────────────────────────────────────────────
def weekday_seasonality(daily: pd.DataFrame) -> dict:
    out = {"_label": "usually noise on single names — shown for honesty", "available": False}
    df = _daily_oc(daily)
    if df.empty or "weekday" not in df:
        return out
    names = {0: "Mon", 1: "Tue", 2: "Wed", 3: "Thu", 4: "Fri"}
    rows = {}
    for wd, name in names.items():
        sub = df[df["weekday"] == wd].dropna(subset=["oc_pct"])
        n = len(sub)
        if n:
            rows[name] = {
                "n": n, "confidence": _confidence(n),
                "avg_oc_pct": round(float(sub["oc_pct"].mean()), 3),
                "green_rate_pct": round(float((sub["oc_pct"] > 0).mean() * 100), 1),
            }
    out.update({"available": bool(rows), "by_weekday": rows})
    return out


# ─────────────────────────────────────────────────────────────────────────────
# Opening-drive follow-through: when the FIRST part of the day moves up, does the
# rest of the day tend to continue or reverse? Computed from daily proxies
# (open vs prior close as the "drive", oc as the rest). Honest proxy label.
# ─────────────────────────────────────────────────────────────────────────────
def gap_continuation(daily: pd.DataFrame, gap_threshold: float = 0.5) -> dict:
    out = {"_label": "PROXY: gap as opening drive, open->close as the rest", "available": False}
    df = _daily_oc(daily).dropna(subset=["gap_pct", "oc_pct"])
    if df.empty:
        return out

    def rate(sub, sign):
        n = len(sub)
        if n == 0:
            return {"n": 0}
        cont = (sub["oc_pct"] > 0) if sign > 0 else (sub["oc_pct"] < 0)
        return {"n": n, "confidence": _confidence(n),
                "continuation_rate_pct": round(float(cont.mean() * 100), 1)}

    out.update({
        "available": True,
        "after_gap_up": rate(df[df["gap_pct"] >= gap_threshold], +1),
        "after_gap_down": rate(df[df["gap_pct"] <= -gap_threshold], -1),
    })
    return out


# ─────────────────────────────────────────────────────────────────────────────
# ANALOG DAYS — the "patterns others wouldn't think of" piece.
# Find historical sessions whose SETUP resembles today (similar gap %, similar
# prior-day move, similar position within the recent range), then report the
# DISTRIBUTION of what those days did open-to-close. This is a nearest-neighbour
# base rate conditioned on the actual setup, not a blanket average.
# ─────────────────────────────────────────────────────────────────────────────
def analog_days(
    daily: pd.DataFrame,
    *,
    today_gap_pct: Optional[float],
    today_prev_oc_pct: Optional[float],
    today_pos_in_range_pct: Optional[float],
    k: int = 25,
) -> dict:
    out = {
        "_label": "nearest-neighbour base rate on similar setups — context, not a forecast",
        "available": False,
    }
    df = _daily_oc(daily).dropna(subset=["gap_pct", "oc_pct", "prev_oc"])
    if df.empty or len(df) < MIN_CONFIDENT_N or today_gap_pct is None:
        out["reason"] = "insufficient history for analogs"
        return out

    # Position within a trailing 20-day range, to match today's structural spot.
    if "Low" in df and "High" in df:
        roll_lo = df["Low"].rolling(20).min()
        roll_hi = df["High"].rolling(20).max()
        df = df.assign(pos=(df["Close"] - roll_lo) / (roll_hi - roll_lo) * 100)
    else:
        df = df.assign(pos=np.nan)

    feats = ["gap_pct", "prev_oc"]
    today = {"gap_pct": today_gap_pct, "prev_oc": today_prev_oc_pct or 0.0}
    use_pos = today_pos_in_range_pct is not None and df["pos"].notna().sum() >= MIN_CONFIDENT_N
    if use_pos:
        feats.append("pos")
        today["pos"] = today_pos_in_range_pct

    sub = df.dropna(subset=feats).copy()
    if len(sub) < MIN_CONFIDENT_N:
        out["reason"] = "insufficient comparable history"
        return out

    # Standardize features, then Euclidean distance to today.
    dist = np.zeros(len(sub))
    for f in feats:
        mu, sd = sub[f].mean(), sub[f].std() or 1.0
        dist += ((sub[f] - mu) / sd - (today[f] - mu) / sd) ** 2
    sub = sub.assign(_d=np.sqrt(dist)).sort_values("_d")
    neigh = sub.head(min(k, len(sub)))
    oc = neigh["oc_pct"]

    out.update({
        "available": True,
        "features_used": feats,
        "n_neighbours": len(neigh),
        "green_rate_pct": round(float((oc > 0).mean() * 100), 1),
        "avg_oc_pct": round(float(oc.mean()), 3),
        "median_oc_pct": round(float(oc.median()), 3),
        "p25_oc_pct": round(float(oc.quantile(0.25)), 3),
        "p75_oc_pct": round(float(oc.quantile(0.75)), 3),
        "worst_oc_pct": round(float(oc.min()), 3),
        "best_oc_pct": round(float(oc.max()), 3),
    })
    return out


# ─────────────────────────────────────────────────────────────────────────────
# Crude-oil correlation regime. For an airline, fuel cost is the dominant lever;
# the SIGN and STRENGTH of the AC<->crude return correlation drifts over time.
# We report the recent rolling correlation so the reader knows which regime
# they're in (crude-sensitive vs decoupled).
# ─────────────────────────────────────────────────────────────────────────────
def crude_correlation_regime(
    ac_daily: pd.DataFrame, crude_daily: pd.DataFrame, window: int = 60
) -> dict:
    out = {"_label": "regime context — fuel-cost sensitivity drifts over time", "available": False}
    if ac_daily is None or crude_daily is None or ac_daily.empty or crude_daily.empty:
        return out
    try:
        a = ac_daily["Close"].pct_change()
        c = crude_daily["Close"].pct_change()
        joined = pd.concat([a.rename("ac"), c.rename("crude")], axis=1).dropna()
        if len(joined) < window:
            out["reason"] = f"need {window} overlapping days, have {len(joined)}"
            return out
        recent = joined.tail(window)
        corr = float(recent["ac"].corr(recent["crude"]))
        full = float(joined["ac"].corr(joined["crude"]))
        regime = ("crude-sensitive (inverse, as expected)" if corr < -0.2 else
                  "crude-sensitive (positive — unusual)" if corr > 0.2 else
                  "decoupled from crude right now")
        out.update({
            "available": True, "window_days": window,
            "rolling_corr": round(corr, 3),
            "full_sample_corr": round(full, 3),
            "n_overlap": len(joined),
            "regime": regime,
        })
    except Exception as e:
        out["reason"] = f"correlation failed: {e}"
    return out


# ─────────────────────────────────────────────────────────────────────────────
# Orchestrator: run the full pattern suite and extract the named factors that
# may (within the clamp) nudge the probability.
# ─────────────────────────────────────────────────────────────────────────────
@dataclass
class PatternFactor:
    name: str
    direction: int          # +1 bullish, -1 bearish
    strength: str           # 'weak' only — base rates never imply strong edges
    detail: str


def analyze(
    ac_daily: pd.DataFrame,
    crude_daily: pd.DataFrame,
    *,
    today_gap_pct: Optional[float],
    today_prev_oc_pct: Optional[float],
    today_pos_in_range_pct: Optional[float],
) -> dict:
    gaps = gap_statistics(ac_daily)
    week = weekday_seasonality(ac_daily)
    cont = gap_continuation(ac_daily)
    analogs = analog_days(
        ac_daily,
        today_gap_pct=today_gap_pct,
        today_prev_oc_pct=today_prev_oc_pct,
        today_pos_in_range_pct=today_pos_in_range_pct,
    )
    crude = crude_correlation_regime(ac_daily, crude_daily)

    # Named factors — ONLY from sufficiently-sampled analogs, and only ever weak.
    factors: list[PatternFactor] = []
    if analogs.get("available") and analogs["n_neighbours"] >= MIN_CONFIDENT_N:
        gr = analogs["green_rate_pct"]
        if gr >= 60:
            factors.append(PatternFactor(
                "analog-day base rate leans up", +1, "weak",
                f"{gr:.0f}% of {analogs['n_neighbours']} similar setups closed > open"))
        elif gr <= 40:
            factors.append(PatternFactor(
                "analog-day base rate leans down", -1, "weak",
                f"{gr:.0f}% of {analogs['n_neighbours']} similar setups closed > open"))

    return {
        "gap_statistics": gaps,
        "weekday_seasonality": week,
        "gap_continuation": cont,
        "analog_days": analogs,
        "crude_regime": crude,
        "factors": factors,
        "history_days": int(len(ac_daily)) if ac_daily is not None else 0,
        "caveat": ("Base rates are computed on available history (this data "
                   "source may return limited/sampled history). The past is not "
                   "the future; a base rate is not a setup-specific forecast."),
    }
