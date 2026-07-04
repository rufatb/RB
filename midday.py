#!/usr/bin/env python3
"""
midday.py — gated from-NOW-to-close selection (run any time after ~10:00).

WHY (day-3 lesson, encoded from a real scratch-loss): asked for "a long AND a
short", the ad-hoc midday analysis crowned a "Best SHORT" that was 53%
(dead-zone) AND lens-conflicted (day-shape 77% bullish) — it duly failed. A
ranked pick invites the trade no matter the caveats underneath. So midday
selection now applies HARD gates and prints "NO QUALIFIED SHORT/LONG today"
rather than ranking a candidate that doesn't clear. The honest answer to
"what should I short?" is sometimes "nothing", and the tool must say it.

Gates (config `midday:`): a side qualifies on the from-here conditional alone
only past the strong threshold; inside the soft band it must be BACKED by the
day-shape analog, and a contradicting day-shape kills it (the MFC case).
"""

from __future__ import annotations

import argparse
import datetime as dt
from concurrent.futures import ThreadPoolExecutor
from zoneinfo import ZoneInfo

from adapters import build_adapter
from dashboard import load_config, _pos_in_trailing_range
from hold import conditional_close_stats
import patterns
import scan as scan_mod


def midday_gate(p_here, day_green, cfg=None):
    """('long'|'short'|None, reason). Pure + testable.
    p_here = smoothed P(close above current price); day_green = smoothed analog
    green%% for today's opening setup (may be None)."""
    m = (cfg or {}).get("midday") or {}
    strong_l = m.get("strong_long", 55); strong_s = m.get("strong_short", 45)
    soft_l = m.get("soft_long", 52);     soft_s = m.get("soft_short", 48)
    backed_l = m.get("backed_long", 65); backed_s = m.get("backed_short", 35)
    if p_here is None:
        return None, "no conditional available"
    if p_here >= strong_l:
        if day_green is not None and day_green < 45:
            return None, f"conflict: from-here long but day-shape bearish ({day_green:.0f}%)"
        return "long", f"strong from-here ({p_here:.0f}%)"
    if p_here <= strong_s:
        if day_green is not None and day_green > 55:
            return None, f"conflict: from-here short but day-shape bullish ({day_green:.0f}%)"
        return "short", f"strong from-here ({p_here:.0f}%)"
    if p_here >= soft_l and day_green is not None and day_green >= backed_l:
        return "long", f"stacked: from-here {p_here:.0f}% + day-shape {day_green:.0f}%"
    if p_here <= soft_s and day_green is not None and day_green <= backed_s:
        return "short", f"stacked: from-here {p_here:.0f}% + day-shape {day_green:.0f}%"
    return None, f"dead zone ({p_here:.0f}% from here) — coin flip, no trade"


def evaluate(adapter, t, cfg, now, crude_pct):
    try:
        q = adapter.get_quote(t)
        if q.session_date != now.date() or q.last is None or q.open is None:
            return None
        if q.as_of and (now - q.as_of).total_seconds() / 60 > cfg["guard"]["max_stale_minutes"]:
            return None
        d = adapter.get_daily_bars(t, 2600).dropna(subset=["Open", "High", "Low", "Close"])
        if len(d) and d.index[-1].date() == q.session_date:
            d = d.iloc[:-1]
        s = conditional_close_stats(d, q.last / q.open, below=q.last <= q.open)
        if not s.get("available"):
            return None
        gap = (q.open / q.prior_close - 1) * 100 if q.prior_close else None
        prev_oc = None
        if len(d) and d["Open"].iloc[-1]:
            prev_oc = (d["Close"].iloc[-1] - d["Open"].iloc[-1]) / d["Open"].iloc[-1] * 100
        an = patterns.analog_days(d, today_gap_pct=gap, today_prev_oc_pct=prev_oc,
                                  today_pos_in_range_pct=_pos_in_trailing_range(d, q.open),
                                  **{k: v for k, v in ((cfg.get("analogs") or {}).items())
                                     if k in ("k", "smoothing_m")})
        day_green = an.get("green_rate_pct") if an.get("available") and not an.get("off_sample") else None
        side, reason = midday_gate(s["p_close_above_here"], day_green, cfg)
        return {"ticker": t, "last": q.last, "open": q.open,
                "vs_open": round((q.last / q.open - 1) * 100, 2),
                "p_here": s["p_close_above_here"], "n": s["n"],
                "median": s["median_vs_here_pct"], "day_green": day_green,
                "hi": q.high, "lo": q.low,
                "macro": scan_mod.macro_dir_for(t, crude_pct, cfg.get("sectors")),
                "side": side, "reason": reason}
    except Exception:
        return None


def run(cfg, source, workers=8):
    tz = cfg["exchange_tz"]
    now = dt.datetime.now(ZoneInfo(tz))
    a = build_adapter(source, exchange_tz=tz)
    try:
        cq = a.get_quote(cfg["correlated"]["crude"])
        crude = (cq.last / cq.prior_close - 1) * 100 if cq.prior_close else None
    except Exception:
        crude = None
    uni = cfg.get("scan", {}).get("universe") or scan_mod.DEFAULT_UNIVERSE
    with ThreadPoolExecutor(max_workers=workers) as ex:
        rows = [r for r in ex.map(lambda t: evaluate(a, t, cfg, now, crude), uni) if r]
    longs = sorted([r for r in rows if r["side"] == "long"], key=lambda r: r["p_here"], reverse=True)
    shorts = sorted([r for r in rows if r["side"] == "short"], key=lambda r: r["p_here"])
    return {"now": now.isoformat(timespec="seconds"), "crude": crude,
            "rows": rows, "longs": longs, "shorts": shorts}


def render(res):
    crude = res["crude"]
    crude_s = "n/a" if crude is None else f"{crude:+.2f}%"
    print(f"MIDDAY FROM-HERE SELECTION  ({res['now']})   crude {crude_s}")
    for side, picks in (("LONG", res["longs"]), ("SHORT", res["shorts"])):
        print(f"\nQUALIFIED {side}S:")
        if not picks:
            print(f"  ⛔ NO QUALIFIED {side} right now — the honest answer is: don't force one.")
            continue
        for r in picks:
            print(f"  {r['ticker']}  last {r['last']:.2f} ({r['vs_open']:+.2f}% vs open)  "
                  f"P(close {'above' if side == 'LONG' else 'below'} here) "
                  f"{r['p_here'] if side == 'LONG' else round(100 - r['p_here'], 1)}%  "
                  f"median {r['median']:+.2f}%  (n={r['n']})")
            print(f"      why: {r['reason']}  |  day-shape green {r['day_green']}%  "
                  f"|  stop: {'below LOD ' + format(r['lo'], '.2f') if side == 'LONG' else 'above HOD ' + format(r['hi'], '.2f')}")
    print("\n  Gated: dead-zone (48-52%) and lens-conflicted names are NOT shown —")
    print("  a ranked weak pick invites a trade the data doesn't support.")


def main(argv=None):
    p = argparse.ArgumentParser(description="Gated midday from-here selection")
    p.add_argument("--config", default="config.yaml")
    p.add_argument("--source", default=None)
    p.add_argument("--workers", type=int, default=8)
    args = p.parse_args(argv)
    cfg = load_config(args.config)
    src = args.source or cfg.get("data_sources", {}).get("primary", "yahoo_direct")
    render(run(cfg, src, args.workers))


if __name__ == "__main__":
    main()
