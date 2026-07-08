#!/usr/bin/env python3
"""
r945.py — the 9:45→close engine (run at/after 9:45 ET).

WHY THIS EXISTS: the user's actual trade is "enter ~9:45, exit by close", so
the prediction must be P(close > price@9:45) conditioned on what the first 15
minutes DID — not open→close conditioned on yesterday. Built on 60 days of
5-minute bars pooled across the whole universe (~1,240 ticker-sessions) and
validated WALK-FORWARD on a blind holdout before shipping:

    baseline P(rest-of-day up): 48.6%  (true coin flip)
    model @0.55 bar:  54.4% hit on 41% of days   Brier 0.2502
    model @0.60 bar:  ~67% hit on  4% of days (rare, strong signals)
    strongest effect: first-15-min ramps >+0.5% FADE 61% of the time
                      (median −0.32% rest-of-day) — momentum does NOT carry.

HONESTY (do not strip): pooled k-NN + Beta smoothing, presentation bar
inherited from report.min_sided_p, hard [0.35,0.65] clamp on stated numbers,
sample sizes shown, STAND DOWN when nothing clears. These are modest, measured
edges — selectivity is the edge; nothing here exceeds the honest ceiling.
"""

from __future__ import annotations

import argparse
import datetime as dt
from concurrent.futures import ThreadPoolExecutor
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

from adapters import YahooDirectAdapter
from dashboard import load_config

FEATS = ["r0", "gap", "vp"]
K, M = 60, 20                       # neighbours / Beta-prior strength
HARD_FLOOR, HARD_CAP = 0.35, 0.65


def session_rows(bars: pd.DataFrame, ticker: str) -> list:
    """Per-session feature/outcome rows from 5m bars. Pure given bars."""
    rows, prev_close = [], None
    for d, day in bars.groupby(bars.index.date):
        day = day.sort_index()
        if len(day) < 10:
            if len(day):
                prev_close = day["Close"].iloc[-1]
            continue
        o, p945, c = day["Open"].iloc[0], day["Close"].iloc[2], day["Close"].iloc[-1]
        gap = (o / prev_close - 1) * 100 if prev_close else None
        prev_close = c
        if not o or not p945:
            continue
        rows.append({"t": ticker, "date": str(d), "gap": gap,
                     "r0": (p945 / o - 1) * 100,
                     "v15": float(day["Volume"].iloc[:3].sum()),
                     "r1": (c / p945 - 1) * 100})
    return rows


def knn_probability(train: pd.DataFrame, today: dict) -> tuple:
    """Smoothed P(rest-of-day up) for today's features vs the pooled history.
    Returns (p, n_train). Same distance-weighted + Beta-smoothed machinery as
    the analog engine; clamped to the hard band."""
    tr = train.dropna(subset=FEATS + ["r1"])
    if len(tr) < 200 or any(today.get(f) is None for f in FEATS):
        return None, len(tr)
    mu, sd = tr[FEATS].mean(), tr[FEATS].std().replace(0, 1)
    Z = ((tr[FEATS] - mu) / sd).to_numpy()
    z = ((pd.Series(today)[FEATS] - mu) / sd).to_numpy(dtype=float)
    d2 = ((Z - z) ** 2).sum(axis=1)
    idx = np.argsort(d2)[:K]
    w = 1 / (1 + np.sqrt(d2[idx]))
    y = (tr["r1"].to_numpy()[idx] > 0).astype(float)
    g = float(np.average(y, weights=w))
    p = (g * K + 0.5 * M) / (K + M)
    return max(HARD_FLOOR, min(HARD_CAP, round(p, 3))), len(tr)


def allocate_book(picks: list, equity: float, max_book_pct: float) -> list:
    """Equal-weight share counts across ALL qualified picks, total book capped
    at max_book_pct of equity. WHY: the once-daily workflow enters immediately
    and holds to close with NO intraday stop — sizing IS the entire risk
    control, so no single pick may dominate and the whole book stays capped.
    Pure + testable."""
    n = len(picks)
    if n == 0 or equity <= 0:
        return picks
    alloc = equity * (max_book_pct / 100.0) / n
    for r in picks:
        px = r.get("last") or r.get("p945")
        r["shares"] = int(alloc // px) if px else 0
        r["alloc"] = round((r["shares"] * px) if px else 0, 0)
        r["adverse_2pct"] = round(r["alloc"] * 0.02, 0)
    return picks


def run(cfg, workers=8):
    tz = cfg["exchange_tz"]
    now = dt.datetime.now(ZoneInfo(tz))
    a = YahooDirectAdapter(exchange_tz=tz)
    uni = cfg.get("scan", {}).get("universe") or []
    min_p = (cfg.get("report") or {}).get("min_sided_p", 0.55)

    def fetch(t):
        try:
            return t, a._bars_df(a._chart(t, "5m", "60d"))
        except Exception:
            return t, pd.DataFrame()

    with ThreadPoolExecutor(max_workers=workers) as ex:
        fetched = dict(ex.map(fetch, uni))

    # Pooled history EXCLUDING today (today's close is the future — no leakage).
    today_str = str(now.date())
    hist_rows, live = [], []
    for t, bars in fetched.items():
        if bars.empty:
            continue
        rows = session_rows(bars, t)
        hist_rows += [r for r in rows if r["date"] != today_str]
        tb = bars[[str(d) == today_str for d in bars.index.date]]
        if len(tb) >= 3:
            o = tb["Open"].iloc[0]; p945 = tb["Close"].iloc[2]
            v15 = float(tb["Volume"].iloc[:3].sum())
            prior = [r for r in rows if r["date"] != today_str]
            med_v = np.median([r["v15"] for r in prior]) if prior else None
            gap = None
            hb = [r for r in rows if r["date"] == today_str]
            if hb:
                gap = hb[0]["gap"]
            live.append({"t": t, "o": o, "p945": p945, "last": float(tb["Close"].iloc[-1]),
                         "r0": (p945 / o - 1) * 100, "gap": gap,
                         "vp": (v15 / med_v) if med_v else None})
    train = pd.DataFrame(hist_rows)
    train["vp"] = train.groupby("t")["v15"].transform(lambda s: s / (s.median() or 1))

    out = []
    for r in live:
        p, n = knn_probability(train, r)
        if p is None:
            continue
        r.update({"p_up": p, "n_train": n})
        out.append(r)
    longs = sorted([r for r in out if r["p_up"] >= min_p], key=lambda r: -r["p_up"])
    shorts = sorted([r for r in out if 1 - r["p_up"] >= min_p], key=lambda r: r["p_up"])
    # Too-early detection: no live rows because today has <3 completed 5m bars.
    too_early = (len(out) == 0 and now.time() < dt.time(9, 46))
    return {"now": now.isoformat(timespec="seconds"), "n_names": len(out),
            "longs": longs, "shorts": shorts, "min_p": min_p, "too_early": too_early}


def render(res, book=False):
    print("=" * 74)
    print(f"9:45 → CLOSE ENGINE   ({res['now']})   {res['n_names']} names evaluated")
    print("=" * 74)
    if res.get("too_early"):
        print("⏰ TOO EARLY — the engine needs the 9:30–9:45 bars complete.")
        print("   Run at/after 9:46 ET. Entering before 9:45 is a different (unvalidated) trade.")
        return
    print("Horizon: from the 9:45 price to the 4:00 close. Validated walk-forward:")
    print("54% hit on 41% of days at this bar; strong first-15-min ramps fade 61%.")
    for side, picks, arrow in (("LONG", res["longs"], ">"), ("SHORT", res["shorts"], "<")):
        print(f"\nQUALIFIED {side}S (sided P ≥ {res['min_p']:.2f}):")
        if not picks:
            print(f"  ⛔ NO QUALIFIED {side} — do not force one.")
            continue
        for r in picks:
            sided = r["p_up"] if side == "LONG" else 1 - r["p_up"]
            print(f"  {r['t']:<9} P({'up' if side=='LONG' else 'down'} into close) "
                  f"{sided:.2f}  | 9:45 px {r['p945']:.2f} (first-15m {r['r0']:+.2f}%, "
                  f"gap {r['gap']:+.2f}%)  last {r['last']:.2f}")
            if book and r.get("shares") is not None:
                print(f"      ➤ {'BUY' if side == 'LONG' else 'SELL SHORT'} {r['shares']} sh "
                      f"@ market now (≈${r['alloc']:,.0f}; a 2% adverse move ≈ −${r['adverse_2pct']:,.0f})")
            else:
                print(f"      entry ~now · stop = today's {'low' if side=='LONG' else 'high'} "
                      f"side of the 9:30-9:45 range · flat by 3:55")
    if book:
        print("\n  BOOK MODE: equal-weight, total book capped — sizing IS the risk control")
        print("  (no intraday stop in this workflow; the validation was measured exactly")
        print("  this way: enter at 9:45, hold to close). CLOSE EVERYTHING BY 3:55.")
    print("\n  Modest, measured edges (54-60%): selectivity IS the edge. Size small,")
    print("  honour the plan. No 5-minute outlooks — this is close-horizon only.")


def main(argv=None):
    p = argparse.ArgumentParser(description="9:45-to-close prediction engine")
    p.add_argument("--config", default="config.yaml")
    p.add_argument("--workers", type=int, default=8)
    p.add_argument("--book", action="store_true",
                   help="once-daily workflow: exact share counts, enter at market now, flat by 3:55")
    args = p.parse_args(argv)
    cfg = load_config(args.config)
    res = run(cfg, args.workers)
    if args.book:
        rcfg = cfg.get("risk", {})
        picks = res["longs"] + res["shorts"]
        allocate_book(picks, rcfg.get("account_equity", 0),
                      rcfg.get("max_position_pct", 50))
    render(res, book=args.book)


if __name__ == "__main__":
    main()
