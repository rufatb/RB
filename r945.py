#!/usr/bin/env python3
"""
r945.py — the 9:45→close engine (run at/after 9:45 ET).

WHY THIS EXISTS: the user's actual trade is "enter ~9:45, exit by close", so
the prediction must be P(close > price@9:45) conditioned on what the first 15
minutes DID — not open→close conditioned on yesterday. Built on 60 days of
5-minute bars pooled across the whole universe (~1,240 ticker-sessions) and
validated WALK-FORWARD on a blind holdout before shipping:

    baseline P(rest-of-day up): 48.6%  (true coin flip)
    model @0.55 bar:  ~53-55% hit on ~40% of days   Brier ≈0.250
    strongest effect: first-15-min ramps >+0.5% FADE ~61% of the time
                      (median −0.32% rest-of-day) — momentum does NOT carry.
    WALKED BACK (day-6 replication): an early "≥0.60 signals hit ~67%" read
    did NOT replicate (n=9-18 bucket flipped 67%→44% across splits). There is
    NO reliable hit-rate gradient above the 0.55 bar — treat every qualified
    signal as the same ~53-55% lean; do not overweight the "strongest" pick.
    Shorts hit slightly less often but capture ~2.7x more per win (asymmetric
    down-moves).

    DAY-9 (validate_pair.py, walk-forward, 49 sessions, 496 qualified picks):
    the ONE pick per side worth trading is the DENSEST estimate (smallest
    k-NN neighbour distance), not the highest P. Evidence: densest top-1 hit
    68.0% discovery / 69.2% confirm (chronological split), 70.5%/66.7% on an
    independent odd/even split, symmetric by side (68.8% L / 68.3% S), n=89,
    p≈0.0007 vs the 51% board base; the 2nd-densest placebo drops to 53.9%,
    and max-P scored only 50.0% on discovery. Interpretation: a dense
    neighbourhood means "we have seen this exact setup many times"; an
    extreme P usually comes from a sparse corner (extrapolation). Trade
    familiarity, not extremity. ALSO found (both splits): picks whose sector
    direction is CROWDED (>=3 same-group same-direction picks) hit only
    44%/33% — noted as a printed warning, not yet a gate.

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
from dashboard import load_config, parse_hhmm

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
        return None, len(tr), None
    mu, sd = tr[FEATS].mean(), tr[FEATS].std().replace(0, 1)
    Z = ((tr[FEATS] - mu) / sd).to_numpy()
    z = ((pd.Series(today)[FEATS] - mu) / sd).to_numpy(dtype=float)
    d2 = ((Z - z) ** 2).sum(axis=1)
    idx = np.argsort(d2)[:K]
    w = 1 / (1 + np.sqrt(d2[idx]))
    y = (tr["r1"].to_numpy()[idx] > 0).astype(float)
    g = float(np.average(y, weights=w))
    p = (g * K + 0.5 * M) / (K + M)
    nd = float(np.sqrt(d2[idx]).mean())   # neighbour distance: estimate density
    return max(HARD_FLOOR, min(HARD_CAP, round(p, 3))), len(tr), nd


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


def density_label(nd: float, cutoffs: tuple) -> str:
    """dense/mid/sparse tag for a pick's neighbourhood. INSTRUMENTATION ONLY —
    holdout hinted dense estimates hit better (63% vs ~46%) but the pattern
    was non-monotonic on one split, so we TAG and log rather than gate. After
    ~20 live days the tag's live record decides whether it becomes a gate.
    Pre-registered hypothesis: dense > mid/sparse."""
    lo, hi = cutoffs
    return "dense" if nd <= lo else ("sparse" if nd > hi else "mid")


def peer_gate(longs: list, shorts: list, groups: dict, min_opposed: int = 3):
    """Exclude any qualified pick whose direction opposes >= min_opposed
    qualified picks in its own peer group (day-8 lesson: TD short 0.55 against
    six qualified financial longs — the lone laggard got pulled up +1.22%).
    Restrictive-only: it removes picks, never adds. Pure + testable."""
    g_of = {t: g for g, members in (groups or {}).items() for t in members}
    long_n, short_n = {}, {}
    for r in longs:
        g = g_of.get(r["t"]);  long_n[g] = long_n.get(g, 0) + 1 if g else long_n.get(g, 0)
    for r in shorts:
        g = g_of.get(r["t"]); short_n[g] = short_n.get(g, 0) + 1 if g else short_n.get(g, 0)
    excluded = []

    def keep(picks, opposing):
        kept = []
        for r in picks:
            g = g_of.get(r["t"])
            n_op = opposing.get(g, 0) if g else 0
            if g and n_op >= min_opposed:
                r["excluded_reason"] = (f"contradicts {n_op} qualified {g} picks "
                                        "— lone laggard/leader in a moving sector")
                excluded.append(r)
            else:
                kept.append(r)
        return kept

    return keep(longs, short_n), keep(shorts, long_n), excluded


def pair_of_day(longs: list, shorts: list, groups: dict = None,
                selector: str = "densest", crowd_warn: int = 3) -> dict:
    """THE PAIR — the single long + single short the daily workflow trades.

    SELECTION (day-9, validated in validate_pair.py — do not revert to max-P):
    each leg is the DENSEST qualified pick (smallest k-NN neighbour distance),
    because sided P has NO hit-rate gradient above the bar while the densest
    pick hit 68%/69% on both validation splits (2nd-densest placebo: 54%,
    max-P: 50% on discovery). Only 'densest' and 'max_p' (kept for A/B
    comparison) are accepted — an unknown selector raises rather than
    silently picking something unvalidated.

    Leg quality = the pick's density tag (DENSE/MID/SPARSE), NOT its P — a
    P-based label would imply a gradient day-6/day-9 showed doesn't exist.
    A missing leg is stated as NONE — the tool never invents a leg to satisfy
    the habit. A leg with >= crowd_warn same-group same-direction picks gets
    a crowding warning (44%/33% hit in validation) — noted, not yet a gate."""
    assert selector in ("densest", "max_p"), f"unvalidated pair selector: {selector}"
    g_of = {t: g for g, ms in (groups or {}).items() for t in ms}

    def leg(picks, side):
        if not picks:
            return {"status": "NONE", "note": f"no qualified {side} — forcing one is a coin flip"}
        if selector == "densest":
            r = min(picks, key=lambda x: x["nd"] if x.get("nd") is not None else 9e9)
        else:
            r = picks[0]                      # lists arrive sorted by sided P
        sided = r["p_up"] if side == "LONG" else 1 - r["p_up"]
        out = {"status": (r.get("confidence") or "?").upper(), "pick": r, "sided": sided,
               "rank_by_p": 1 + sum(1 for o in picks
                                    if (o["p_up"] if side == "LONG" else 1 - o["p_up"]) > sided)}
        g = g_of.get(r["t"])
        n_conf = sum(1 for o in picks if o is not r and g and g_of.get(o["t"]) == g)
        if g and n_conf >= crowd_warn:
            out["warning"] = (f"{n_conf} other {g} picks point the same way — crowded "
                              f"sector direction hit only 44%/33% in validation")
        return out
    return {"long": leg(longs, "LONG"), "short": leg(shorts, "SHORT")}


def run(cfg, workers=8):
    tz = cfg["exchange_tz"]
    now = dt.datetime.now(ZoneInfo(tz))
    # HARD too-early guard (bug found live at 9:38): between open+10 and
    # open+15 the third 5m bar EXISTS but is IN-PROGRESS — its close is the
    # live price, not the 9:45 print, so features cover ~8 of the validated 15
    # minutes. Refuse to evaluate until the bar is complete (open + 16 min).
    open_t = parse_hhmm(cfg.get("market_open", "09:30"))
    ready = now.replace(hour=open_t.hour, minute=open_t.minute, second=0,
                        microsecond=0) + dt.timedelta(minutes=16)
    if now < ready and now.date() == ready.date():
        return {"now": now.isoformat(timespec="seconds"), "n_names": 0,
                "longs": [], "shorts": [], "min_p": 0.55, "too_early": True,
                "ready_at": ready.strftime("%H:%M")}
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
            # Gap directly from the prior session's last close. (BUG FIX found
            # live: the old path read today's gap from session_rows, which
            # requires >=10 bars — impossible at 9:47, so every name silently
            # dropped. Post-close smoke tests couldn't catch this.)
            prev_bars = bars[[str(d) != today_str for d in bars.index.date]]
            prior_close = float(prev_bars["Close"].iloc[-1]) if len(prev_bars) else None
            gap = (o / prior_close - 1) * 100 if prior_close else None
            live.append({"t": t, "o": o, "p945": p945, "last": float(tb["Close"].iloc[-1]),
                         "r0": (p945 / o - 1) * 100, "gap": gap,
                         "vp": (v15 / med_v) if med_v else None})
    train = pd.DataFrame(hist_rows)
    train["vp"] = train.groupby("t")["v15"].transform(lambda s: s / (s.median() or 1))

    # Density cutoffs from a sample of the training rows' own neighbourhoods.
    sample = train.dropna(subset=FEATS + ["r1"]).sample(
        n=min(120, len(train)), random_state=7) if len(train) else train
    nds = []
    for _, row in sample.iterrows():
        res = knn_probability(train, {f: row[f] for f in FEATS})
        if res[0] is not None:
            nds.append(res[2])
    cutoffs = (float(np.quantile(nds, 0.33)), float(np.quantile(nds, 0.67))) if nds else (0.0, 9e9)

    out = []
    for r in live:
        res = knn_probability(train, r)
        p, n = res[0], res[1]
        if p is None:
            continue
        r.update({"p_up": p, "n_train": n, "nd": res[2],
                  "confidence": density_label(res[2], cutoffs)})
        out.append(r)
    longs = sorted([r for r in out if r["p_up"] >= min_p], key=lambda r: -r["p_up"])
    shorts = sorted([r for r in out if 1 - r["p_up"] >= min_p], key=lambda r: r["p_up"])
    longs, shorts, excluded = peer_gate(
        longs, shorts, cfg.get("peer_groups"),
        cfg.get("peer_contradiction_min", 3))
    # Too-early detection: no live rows because today has <3 completed 5m bars.
    too_early = (len(out) == 0 and now.time() < dt.time(9, 46))
    pcfg = cfg.get("pair") or {}
    return {"now": now.isoformat(timespec="seconds"), "n_names": len(out),
            "longs": longs, "shorts": shorts, "excluded": excluded,
            "pair": pair_of_day(longs, shorts, cfg.get("peer_groups"),
                                pcfg.get("selector", "densest"),
                                pcfg.get("crowded_conf_warn", 3)),
            "min_p": min_p, "too_early": too_early}


def render(res, book=False):
    print("=" * 74)
    print(f"9:45 → CLOSE ENGINE   ({res['now']})   {res['n_names']} names evaluated")
    print("=" * 74)
    if res.get("too_early"):
        print(f"⏰ TOO EARLY — the engine needs the full 9:30–9:45 bars COMPLETE.")
        print(f"   Ready at {res.get('ready_at', '09:46')} ET. A run before then reads the")
        print("   in-progress bar as the 9:45 print — an unvalidated trade. REFUSING.")
        return
    print("Horizon: from the 9:45 price to the 4:00 close. Validated walk-forward:")
    print("board base ~51-54%; THE PAIR (densest leg per side) 68%/69% on both splits.")
    pair = res.get("pair")
    if pair:
        print("\n" + "═" * 74)
        print("THE PAIR — trade these two, nothing else (one long + one short daily)")
        print("═" * 74)
        for side in ("long", "short"):
            lg = pair[side]
            if lg["status"] == "NONE":
                print(f"  {side.upper():<6}: ⛔ {lg['note']}")
                continue
            r = lg["pick"]
            print(f"  {side.upper():<6}: {r['t']}  sided-P {lg['sided']:.2f}  "
                  f"[estimate: {lg['status']}]  9:45 px {r['p945']:.2f}  last {r['last']:.2f}")
            print(f"          first-15m {r['r0']:+.2f}% · gap {r['gap']:+.2f}% · "
                  f"board rank by P: #{lg.get('rank_by_p', '?')} "
                  "(selected by DENSITY — familiarity beats extremity)")
            if book and r.get("shares") is not None:
                print(f"      ➤ {'BUY' if side == 'long' else 'SELL SHORT'} {r['shares']} sh "
                      f"@ market now (≈${r['alloc']:,.0f}; a 2% adverse move ≈ −${r['adverse_2pct']:,.0f})")
            else:
                print(f"      entry ~now · flat by 3:55")
            if lg.get("warning"):
                print(f"      ⚠ {lg['warning']}")
        if pair["long"]["status"] == "NONE" or pair["short"]["status"] == "NONE":
            print("  → One leg is missing: trade the other leg ONLY. A forced leg has no edge.")
    for side, picks in (("LONG", res["longs"]), ("SHORT", res["shorts"])):
        print(f"\nCONTEXT — qualified {side}S (sided P ≥ {res['min_p']:.2f}, NOT sized, "
              "logged for learning):")
        if not picks:
            print(f"  ⛔ NO QUALIFIED {side} — do not force one.")
            continue
        for r in picks:
            sided = r["p_up"] if side == "LONG" else 1 - r["p_up"]
            print(f"  {r['t']:<9} P({'up' if side=='LONG' else 'down'}) {sided:.2f}  "
                  f"9:45 px {r['p945']:.2f}  first-15m {r['r0']:+.2f}%  gap {r['gap']:+.2f}%  "
                  f"[{r.get('confidence','?')}]")
    for r in res.get("excluded", []):
        print(f"\n  ⛔ EXCLUDED: {r['t']} — {r['excluded_reason']}")
    if book:
        print("\n  BOOK MODE: only THE PAIR is sized — one long + one short, equal-weight,")
        print("  total book capped. The pair is ~market-neutral but each leg carries full")
        print("  single-name risk with no intraday stop — sizing IS the risk control.")
        print("  CLOSE BOTH BY 3:55.")
    print("\n  Modest, measured edges: 68%/69% in validation will be LESS live — expect")
    print("  low-60s at best; the ledger's PAIR line is the arbiter. No 5-minute")
    print("  outlooks — this is close-horizon only.")


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
        # Day-9: only THE PAIR is sized/traded. The rest of the board is
        # context + ledger-learning material, never an order.
        pair = res.get("pair") or {}
        pair_picks = [lg["pick"] for lg in (pair.get("long"), pair.get("short"))
                      if lg and lg.get("pick")]
        allocate_book(pair_picks, rcfg.get("account_equity", 0),
                      rcfg.get("max_position_pct", 50))
        # Permanent learning ledger: record picks at PUBLISH time (no hindsight).
        # Pair legs get role=pair (the executed record); the remaining board is
        # role=board — kept so density/crowding instrumentation keeps learning.
        picks = res["longs"] + res["shorts"]
        if picks and not res.get("too_early"):
            import ledger
            date = res["now"][:10]
            pair_ids = {id(r) for r in pair_picks}
            lrows = [{"ticker": r["t"],
                      "side": "LONG" if r["p_up"] >= 0.5 else "SHORT",
                      "p_sided": r["p_up"] if r["p_up"] >= 0.5 else 1 - r["p_up"],
                      "confidence": r.get("confidence", "n/a"),
                      "p945": r["p945"],
                      "role": "pair" if id(r) in pair_ids else "board"} for r in picks]
            n = ledger.append_picks(lrows, date)
            if n:
                print(f"\n  [ledger: {n} picks recorded for {date} "
                      f"({len(pair_picks)} pair / {n - len(pair_picks)} board) — score "
                      "after close with `python ledger.py --score`]")
    render(res, book=args.book)


if __name__ == "__main__":
    main()
