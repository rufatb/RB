"""
metrics.py — all the real, timestamped measurements.

HONESTY CONSTRAINTS (do not strip):
    * Every function computes from actual data or returns None / "unavailable".
    * Nothing here invents order-flow. Where a real metric would need Level-2
      aggressor data we don't have, we expose a clearly LABELLED PROXY instead
      (e.g. `net_buy_proxy`), and the label says it's a proxy.
    * These metrics are inputs to a decision, not a verdict. Momentum indicators
      in particular are computed but flagged non-predictive / often conflicting.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from typing import Optional

import numpy as np
import pandas as pd


# ─────────────────────────────────────────────────────────────────────────────
# Price / structure
# ─────────────────────────────────────────────────────────────────────────────
def pct(a: Optional[float], b: Optional[float]) -> Optional[float]:
    """Percent change from b to a. None-safe; never divides by zero silently."""
    if a is None or b is None or b == 0:
        return None
    return (a - b) / b * 100.0


def structure(quote) -> dict:
    """Open, prior close, last, gaps and the basic % reads."""
    return {
        "open": quote.open,
        "prior_close": quote.prior_close,
        "last": quote.last,
        "high": quote.high,
        "low": quote.low,
        "volume": quote.volume,
        "gap_pct": pct(quote.open, quote.prior_close),
        "pct_vs_open": pct(quote.last, quote.open),
        "pct_vs_prior_close": pct(quote.last, quote.prior_close),
    }


# ─────────────────────────────────────────────────────────────────────────────
# Opening range (ORB)
# ─────────────────────────────────────────────────────────────────────────────
def opening_range(bars: pd.DataFrame, last: Optional[float], orb_minutes: int = 5) -> dict:
    """
    High/low of the first 1-min bar and the first `orb_minutes` of bars, plus
    where `last` sits within the 5-min opening range (0% = low, 100% = high).
    Returns 'unavailable' fields if bars are missing (e.g. manual mode).
    """
    out = {
        "orb1_high": None, "orb1_low": None,
        "orbN_high": None, "orbN_low": None,
        "orbN_minutes": orb_minutes,
        "pos_in_orb_pct": None,
        "available": False,
    }
    if bars is None or bars.empty:
        return out

    first = bars.iloc[0]
    out["orb1_high"] = float(first["High"])
    out["orb1_low"] = float(first["Low"])

    window = bars.iloc[:orb_minutes]
    hi = float(window["High"].max())
    lo = float(window["Low"].min())
    out["orbN_high"] = hi
    out["orbN_low"] = lo
    out["available"] = True

    if last is not None and hi > lo:
        out["pos_in_orb_pct"] = (last - lo) / (hi - lo) * 100.0
    return out


# ─────────────────────────────────────────────────────────────────────────────
# Volume pace
# ─────────────────────────────────────────────────────────────────────────────
def volume_pace(
    cumulative_volume: Optional[float],
    adv: Optional[float],
    now: dt.datetime,
    market_open: dt.time,
    market_close: dt.time,
) -> dict:
    """
    pace = cumulative ÷ (ADV × elapsed-session-fraction).
    >1 means trading faster than an average full day's pace; <1 slower.
    """
    out = {"cumulative": cumulative_volume, "adv": adv, "elapsed_frac": None, "pace": None}
    open_dt = now.replace(hour=market_open.hour, minute=market_open.minute, second=0, microsecond=0)
    close_dt = now.replace(hour=market_close.hour, minute=market_close.minute, second=0, microsecond=0)
    session_secs = (close_dt - open_dt).total_seconds()
    if session_secs <= 0:
        return out
    elapsed = (now - open_dt).total_seconds()
    frac = min(max(elapsed / session_secs, 0.0), 1.0)
    out["elapsed_frac"] = frac
    if cumulative_volume is not None and adv and frac > 0:
        out["pace"] = cumulative_volume / (adv * frac)
    return out


def average_daily_volume(daily: pd.DataFrame, window: int = 20) -> Optional[float]:
    if daily is None or daily.empty or "Volume" not in daily:
        return None
    vols = daily["Volume"].dropna().tail(window)
    if vols.empty:
        return None
    return float(vols.mean())


# ─────────────────────────────────────────────────────────────────────────────
# VWAP
# ─────────────────────────────────────────────────────────────────────────────
def vwap(bars: pd.DataFrame, last: Optional[float]) -> dict:
    out = {"vwap": None, "price_vs_vwap_pct": None, "available": False}
    if bars is None or bars.empty:
        return out
    tp = (bars["High"] + bars["Low"] + bars["Close"]) / 3.0
    vol = bars["Volume"].replace(0, np.nan)
    denom = vol.sum()
    if not denom or denom != denom:
        return out
    vw = float((tp * vol).sum() / denom)
    out["vwap"] = vw
    out["available"] = True
    if last is not None:
        out["price_vs_vwap_pct"] = pct(last, vw)
    return out


# ─────────────────────────────────────────────────────────────────────────────
# Momentum — COMPUTED BUT FLAGGED non-predictive / often conflicting.
# WHY the flag: intraday momentum indicators flip with price and routinely
# disagree. They inform structure; they are not a verdict.
# ─────────────────────────────────────────────────────────────────────────────
def rsi(series: pd.Series, period: int = 14) -> Optional[float]:
    s = series.dropna()
    if len(s) < period + 1:
        return None
    delta = s.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1 / period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / period, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    out = 100 - (100 / (1 + rs))
    val = out.iloc[-1]
    return float(val) if val == val else None


def macd(series: pd.Series, fast=12, slow=26, signal=9) -> dict:
    s = series.dropna()
    out = {"macd": None, "signal": None, "hist": None}
    if len(s) < slow + signal:
        return out
    ema_fast = s.ewm(span=fast, adjust=False).mean()
    ema_slow = s.ewm(span=slow, adjust=False).mean()
    macd_line = ema_fast - ema_slow
    sig = macd_line.ewm(span=signal, adjust=False).mean()
    out["macd"] = float(macd_line.iloc[-1])
    out["signal"] = float(sig.iloc[-1])
    out["hist"] = float(macd_line.iloc[-1] - sig.iloc[-1])
    return out


def momentum(daily: pd.DataFrame, intraday: pd.DataFrame) -> dict:
    """Labelled non-predictive. Returns daily + intraday RSI and daily MACD."""
    out = {
        "_label": "non-predictive; intraday momentum often conflicts — context only",
        "rsi_daily": None,
        "rsi_intraday": None,
        "macd_daily": {"macd": None, "signal": None, "hist": None},
    }
    if daily is not None and not daily.empty and "Close" in daily:
        out["rsi_daily"] = rsi(daily["Close"], 14)
        out["macd_daily"] = macd(daily["Close"])
    if intraday is not None and not intraday.empty and "Close" in intraday:
        out["rsi_intraday"] = rsi(intraday["Close"], 14)
    return out


# ─────────────────────────────────────────────────────────────────────────────
# Key levels + distance-to-level
# ─────────────────────────────────────────────────────────────────────────────
def key_levels(daily: pd.DataFrame, swing_lookback: int = 60) -> dict:
    """
    52w high/low, prior-day H/L/C, and auto-detected swing-low demand shelves /
    swing-high resistance over the lookback window.
    """
    out = {
        "high_52w": None, "low_52w": None,
        "prior_high": None, "prior_low": None, "prior_close": None,
        "demand_shelves": [], "resistance": [],
    }
    if daily is None or daily.empty:
        return out

    last_252 = daily.tail(252)
    out["high_52w"] = float(last_252["High"].max())
    out["low_52w"] = float(last_252["Low"].min())

    # Prior session = last completed daily bar.
    prior = daily.iloc[-1]
    out["prior_high"] = float(prior["High"])
    out["prior_low"] = float(prior["Low"])
    out["prior_close"] = float(prior["Close"])

    # Fractal swing detection: a swing low is a bar whose low is the min of a
    # +/-2 bar neighbourhood; swing high analogous. Cluster nearby levels.
    win = daily.tail(swing_lookback).reset_index(drop=True)
    lows, highs = [], []
    for i in range(2, len(win) - 2):
        lo = win["Low"].iloc[i]
        hi = win["High"].iloc[i]
        if lo == win["Low"].iloc[i - 2:i + 3].min():
            lows.append(float(lo))
        if hi == win["High"].iloc[i - 2:i + 3].max():
            highs.append(float(hi))
    out["demand_shelves"] = _cluster(sorted(set(lows)))
    out["resistance"] = _cluster(sorted(set(highs)))
    return out


def _cluster(levels: list, tol_pct: float = 0.4) -> list:
    """Merge levels within tol_pct of each other into representative shelves."""
    if not levels:
        return []
    clusters = [[levels[0]]]
    for lv in levels[1:]:
        if abs(lv - clusters[-1][-1]) / clusters[-1][-1] * 100 <= tol_pct:
            clusters[-1].append(lv)
        else:
            clusters.append([lv])
    return [round(sum(c) / len(c), 4) for c in clusters]


def distance_to_levels(last: Optional[float], levels: dict) -> list:
    """% and $ from last to each named key level. Sorted by absolute distance."""
    if last is None:
        return []
    rows = []

    def add(name, lvl):
        if lvl is None:
            return
        rows.append({"name": name, "level": lvl, "dist_$": lvl - last, "dist_%": pct(lvl, last)})

    add("52w high", levels.get("high_52w"))
    add("52w low", levels.get("low_52w"))
    add("prior high", levels.get("prior_high"))
    add("prior low", levels.get("prior_low"))
    add("prior close", levels.get("prior_close"))
    for s in levels.get("demand_shelves", []):
        add("demand shelf", s)
    for r in levels.get("resistance", []):
        add("resistance", r)
    rows.sort(key=lambda r: abs(r["dist_$"]))
    return rows


# ─────────────────────────────────────────────────────────────────────────────
# Order-flow PROXY (NOT real order flow)
# WHY: true bid/ask aggressor delta needs Level-2 data none of our supported
# sources provide. Fabricating it is forbidden. We expose a transparent proxy.
# ─────────────────────────────────────────────────────────────────────────────
def net_buy_proxy(struct: dict, vwap_info: dict) -> dict:
    """
    A LABELLED proxy for buying/selling pressure — explicitly NOT order flow.
    Heuristic: price holding above open AND above VWAP -> net-buy proxy lean.
    """
    out = {
        "_label": "PROXY ONLY — not real order-flow / aggressor delta (no L2 data)",
        "value": "unavailable",
        "basis": [],
    }
    last, open_ = struct.get("last"), struct.get("open")
    vw = vwap_info.get("vwap")
    if last is None or open_ is None:
        return out
    above_open = last > open_
    above_vwap = (vw is not None and last > vw)
    if vw is None:
        out["value"] = "weak-buy-proxy" if above_open else "weak-sell-proxy"
        out["basis"] = ["price vs open only (no VWAP)"]
    elif above_open and above_vwap:
        out["value"] = "net-buy-proxy"
        out["basis"] = ["price > open", "price > VWAP"]
    elif (not above_open) and (not above_vwap):
        out["value"] = "net-sell-proxy"
        out["basis"] = ["price < open", "price < VWAP"]
    else:
        out["value"] = "mixed"
        out["basis"] = ["price/open and price/VWAP disagree"]
    return out


# ─────────────────────────────────────────────────────────────────────────────
# Spike–fade detector (the specific pattern that caused the whipsaw)
# ─────────────────────────────────────────────────────────────────────────────
def spike_fade(bars: pd.DataFrame, open_price: Optional[float], window_min: int = 15) -> dict:
    """
    Locate the session extreme in the first `window_min` minutes (the 'opening
    drive'), then measure how much of that drive has retraced.

        retrace > 50% of drive          -> FADE WARNING
        retrace ~100% (back to open)     -> OPENING DRIVE NEUTRALIZED
        lower-highs after the extreme    -> FAILED-BREAKOUT STRUCTURE

    These usually precede chop, not continuation — surfaced prominently.
    """
    out = {
        "available": False,
        "direction": None,        # 'up' or 'down' opening drive
        "extreme": None,
        "retrace_pct": None,
        "flags": [],
    }
    if bars is None or bars.empty or open_price is None:
        return out

    drive = bars.iloc[:window_min]
    if drive.empty:
        return out
    last = float(bars["Close"].iloc[-1])

    up_ext = float(drive["High"].max())
    down_ext = float(drive["Low"].min())
    up_move = up_ext - open_price
    down_move = open_price - down_ext

    # The dominant opening drive = larger absolute move from the open.
    if up_move >= down_move and up_move > 0:
        out["direction"] = "up"
        out["extreme"] = up_ext
        drive_size = up_move
        retrace = (up_ext - last)
    elif down_move > 0:
        out["direction"] = "down"
        out["extreme"] = down_ext
        drive_size = down_move
        retrace = (last - down_ext)
    else:
        out["available"] = True
        out["flags"].append("no measurable opening drive")
        return out

    out["available"] = True
    if drive_size > 0:
        rpct = retrace / drive_size * 100.0
        out["retrace_pct"] = rpct
        if rpct >= 95:
            out["flags"].append("OPENING DRIVE NEUTRALIZED — momentum gone")
        elif rpct > 50:
            out["flags"].append("FADE WARNING — opening drive >50% retraced")

    # Lower-highs after the extreme -> failed-breakout structure.
    after = bars.loc[bars.index >= drive.index[drive["High"].argmax() if out["direction"] == "up"
                                               else drive["Low"].argmin()]]
    highs = after["High"].tolist()
    if len(highs) >= 3 and out["direction"] == "up":
        lower_highs = all(highs[i] <= highs[i - 1] + 1e-9 for i in range(1, min(len(highs), 5)))
        if lower_highs:
            out["flags"].append("FAILED-BREAKOUT STRUCTURE — lower highs after extreme")
    return out


# ─────────────────────────────────────────────────────────────────────────────
# Correlated / relative-strength read — CONTEXT, NOT SIGNAL
# ─────────────────────────────────────────────────────────────────────────────
def relative_strength(ac_pct: Optional[float], tsx_pct: Optional[float], peer_avg_pct: Optional[float]) -> dict:
    """outperforming / inline / lagging vs TSX and airline-peer average."""
    def verdict(ac, ref):
        if ac is None or ref is None:
            return "unavailable"
        diff = ac - ref
        if diff > 0.25:
            return "outperforming"
        if diff < -0.25:
            return "lagging"
        return "inline"

    return {
        "_label": "CONTEXT ONLY — relative strength is not a standalone signal",
        "vs_tsx": verdict(ac_pct, tsx_pct),
        "vs_peers": verdict(ac_pct, peer_avg_pct),
    }
