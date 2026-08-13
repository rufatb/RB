#!/usr/bin/env python3
"""
validate_exit.py — is there a better exit than 15:59? (day-36)

WHY THIS EXISTS: every number this system has ever produced assumes a
9:45 -> close hold. The exit time was never chosen; it was inherited from the
first script and then baked into the ledger, the backtests, the twins study and
the adoption bar. That makes it the single largest untested parameter in the
strategy, and unlike most of the levers tested so far it is FREE to change --
no new data, no new model, just a different clock.

WHAT IT MEASURES: the capture curve. For every leg the engine would have taken,
what is the mean sided capture if the position is closed at 09:50, 09:55, ...
15:55, 16:00 instead of at the close? Four independent samples:

  A. PAIR legs      -- the executed product, walk-forward over the 5m panel
  B. BOARD legs     -- every qualifying name (>= min_sided_p), same walk-forward
  C. LIVE legs      -- the real ledger's pair legs, replayed bar by bar
  D. TWINS          -- 20 US dual-listings, 1h bars, ~2 years (shape only)

PRE-REGISTERED BEFORE LOOKING (this matters -- 75 candidate exits guarantees a
winner by chance; the bar is built to make a lucky spike fail):

  H0: exit time does not matter; capture at T is flat in T.
  An alternative exit T* is ADOPTED only if ALL FIVE hold:
    1. mean capture at T* > mean capture at close, on sample A;
    2. the improvement holds in ALL FOUR contiguous calendar quarters of the
       test period (the standing house bar since day-14);
    3. SMOOTHNESS -- T* +/- 15 minutes also beat the close. A single 5-minute
       spike surrounded by losers is noise by construction;
    4. the sign agrees on sample B (independent legs, same days) AND on
       sample D (independent names, independent 2-year period);
    5. the gain exceeds one standard error of the difference.
  Anything less is reported as NOT ADOPTED, and the close stands.

WHAT IT CANNOT DO: the 5m panel is 60 sessions (Yahoo's cap), so sample A's
walk-forward has ~35 test sessions. That is thin, and it is why adoption
requires sample D's 2-year cross-check rather than treating A as decisive.
The twins' entry is 10:30 (first hourly bar), so D measures the SHAPE of
intraday decay, not live 9:45 levels -- same caveat as validate_twins.py.

RESULTS (2026-08-13, first run -- recorded so the verdict is permanent):

  *** NOT ADOPTED: no exit time beats the close. H0 stands. ***

  D/TWINS is decisive -- 944 PAIR legs over 288 test sessions, and the whole
  capture curve is flat inside +/-0.02%:
      11:30 -0.020 | 12:30 -0.008 | 13:30 +0.007 | 14:30 +0.004
      15:30 -0.004 | close -0.004      (best-vs-close diff +0.011%, 1 se 0.025%)
  Best exit fails smoothness, fails the 1-se bar, 3/4 quarters. Same on A/PAIR
  (124 legs): best raw exit 15:45, +0.007% over the close, 2/4 quarters.

  WHY there is nothing to find (the mechanism, sample-independent): the
  correlation between the move so far and the rest of the day is ~0 at EVERY
  exit -- +0.07 at 10:00, -0.00 at 11:30, -0.04 at 13:00, -0.02 at 15:45. The
  path from 9:45 is close to a martingale. It does not systematically hand
  back what it gave, so there is no peak to exit at.

  DECOMPOSITION (the check that killed the tempting version): splitting capture
  into consecutive windows shows NO window carries the edge on A/PAIR -- every
  t-stat lands in [-0.83, +1.35]. Capture accrues roughly uniformly.

  BEWARE the early-exit mirage. On 3 of 4 samples the best RAW exit was 09:50
  or 10:00, and on the 47 live ledger legs a 10:00 exit "would have" returned
  +0.056% against the close's -0.086%. Three reasons that is not a finding:
    1. it is the best of 75 candidates on 47 legs -- exactly what mining does;
    2. it does not reproduce on A/PAIR, the same rule with 124 legs, nor on
       D/TWINS with 944;
    3. it is driven by ONE window, 10:00->10:30 on the live legs (-0.202%,
       t=-3.59), i.e. one bad half-hour in a small sample, not a decay curve.
  A 0.03-0.06% "edge" is also under a realistic round-trip cost.

  WHAT IS TRUE, and is not actionable yet: variance keeps growing after the
  mean stops. On D/TWINS std runs 0.51 -> 0.96 from 11:30 to the close while
  the mean sits at zero; on A/PAIR the mean is flat from 11:20 (+0.055 ->
  +0.062) while std goes 0.85 -> 1.32. IF that mean-flatness is real, the
  final 4.5 hours buy ~55% more risk for nothing. It fails the adoption bar
  (2/4 quarters, gain well inside 1 se) and 124 legs cannot separate +0.055
  from +0.062. Re-run this script as the live ledger grows; it needs no new
  data and no key, which is the whole point of building it this way.

Usage:
    python validate_exit.py                  # build panel + run everything
    python validate_exit.py --cache DIR      # reuse a built panel
    python validate_exit.py --skip-twins     # 5m samples only (fast)
"""

from __future__ import annotations

import argparse
import datetime as dt
import os
import sys
from concurrent.futures import ThreadPoolExecutor

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from adapters import YahooDirectAdapter  # noqa: E402
from dashboard import load_config  # noqa: E402
from r945 import FEATS, knn_probability, session_rows  # noqa: E402

SCRATCH = os.environ.get(
    "RB_SCRATCH",
    "/tmp/claude-0/-home-user-RB/54eaac79-d1fb-5533-bbe1-7e140504a5d6/scratchpad")


# --------------------------------------------------------------------------
# panel construction
# --------------------------------------------------------------------------

def build_panel(universe: list, workers: int = 12) -> tuple:
    """Long-format 5m panel + the shipped per-session feature table.

    The panel is anchored on the 9:45 print (Close of the third bar) exactly as
    the live engine is, so `capture` here is the same quantity the ledger
    records -- only the exit clock changes. The feature table comes from
    r945.session_rows so the walk-forward trains the SHIPPED model, not a
    lookalike.
    """
    a = YahooDirectAdapter(exchange_tz="America/Toronto")

    def fetch(t):
        try:
            return t, a._bars_df(a._chart(t, "5m", "60d"))
        except Exception:
            return t, pd.DataFrame()

    with ThreadPoolExecutor(max_workers=workers) as ex:
        fetched = dict(ex.map(fetch, universe))

    recs, frows = [], []
    for t, bars in fetched.items():
        if bars.empty:
            continue
        frows += session_rows(bars, t)
        for d, day in bars.groupby(bars.index.date):
            day = day.sort_index()
            if len(day) < 20:          # half-days cannot answer an exit question
                continue
            p945 = float(day["Close"].iloc[2])
            if not p945:
                continue
            t945 = day.index[2]
            for ts, row in day.iloc[3:].iterrows():
                mins = int((ts - t945).total_seconds() // 60)
                if mins <= 0 or mins > 375:
                    continue
                recs.append({"t": t, "date": str(d), "mins": mins,
                             "px": float(row["Close"]), "p945": p945})
    df = pd.DataFrame(recs)
    if not df.empty:
        df["ret"] = (df["px"] / df["p945"] - 1) * 100
    feats = pd.DataFrame(frows)
    if not feats.empty:
        # vp exactly as run() computes it: 15-minute volume over the name's own
        # median 15-minute volume.
        feats["vp"] = feats.groupby("t")["v15"].transform(
            lambda s: s / (s.median() or 1))
    return df, feats


def exit_grid(panel: pd.DataFrame, min_cover: float = 0.9) -> list:
    """Candidate exit offsets present on >= `min_cover` of sessions.

    Guards against a ragged tail: a 16:00 bar that exists on 40% of days would
    otherwise be compared against a 10:00 bar that exists on 100%, and the
    difference would be composition, not timing.
    """
    n_sess = panel.groupby(["t", "date"]).ngroups
    cnt = panel.groupby("mins").size()
    return sorted(int(m) for m in cnt[cnt >= min_cover * n_sess].index)


def capture_at(panel_idx: dict, t: str, date: str, side: str, mins: int):
    """Sided capture (%) for one leg at one exit offset, or None if no bar."""
    r = panel_idx.get((t, date, mins))
    if r is None:
        return None
    return r if side == "LONG" else -r


# --------------------------------------------------------------------------
# walk-forward leg generation (samples A and B)
# --------------------------------------------------------------------------

def walk_forward_legs(feats: pd.DataFrame, cfg: dict, min_train: int = 25,
                      min_p: float = 0.55, legs_per_side: int = 2,
                      need_labels: bool = True) -> list:
    """Regenerate the engine's picks day by day, using only PRIOR sessions.

    Reuses r945.knn_probability, r945.extrapolation_check and r945.peer_gate so
    this measures the SHIPPED model's capture curve rather than a lookalike.
    Returns one record per leg tagged `role` in {pair, board}.

    The training pool for date D is every session strictly before D -- the same
    no-peek rule the live engine follows, and the reason the first `min_train`
    dates produce no legs.
    """
    from r945 import density_label, extrapolation_check, peer_gate, pair_of_day

    dates = sorted(feats["date"].unique())
    legs = []
    for i, d in enumerate(dates):
        if i < min_train:
            continue
        train = feats[feats["date"] < d].dropna(subset=FEATS + ["r1"])
        today = feats[feats["date"] == d]
        if len(train) < 100 or today.empty:
            continue

        # Density cutoffs, computed the shipped way (self-match removed). These
        # only produce the DENSE/MID/SPARSE label; selection ranks on raw `nd`,
        # so a study that never reads the label can skip ~120 k-NN fits per
        # test day. On the 2-year twins that is the difference between minutes
        # and an hour, and it changes no result.
        if need_labels:
            sample = train.sample(n=min(120, len(train)), random_state=7)
            nds = []
            for idx, row in sample.iterrows():
                res = knn_probability(train.drop(index=idx), {f: row[f] for f in FEATS})
                if res[0] is not None:
                    nds.append(res[2])
            cutoffs = ((float(np.quantile(nds, 0.33)), float(np.quantile(nds, 0.67)))
                       if nds else (0.0, 9e9))
        else:
            cutoffs = (0.0, 9e9)

        out = []
        for _, r in today.iterrows():
            rec = {"t": r["t"], "date": d, "r0": r["r0"], "gap": r["gap"],
                   "vp": r["vp"], "p945": None}
            if any(pd.isna(rec[f]) for f in FEATS):
                continue
            ok_x, _ = extrapolation_check(train, rec)
            if not ok_x:
                continue
            res = knn_probability(train, rec)
            if res[0] is None:
                continue
            rec.update({"p_up": res[0], "nd": res[2],
                        "confidence": density_label(res[2], cutoffs)})
            out.append(rec)
        if not out:
            continue

        longs = sorted([r for r in out if r["p_up"] >= min_p], key=lambda r: -r["p_up"])
        shorts = sorted([r for r in out if 1 - r["p_up"] >= min_p], key=lambda r: r["p_up"])
        longs, shorts, _ = peer_gate(longs, shorts, cfg.get("peer_groups"),
                                     cfg.get("peer_contradiction_min", 3))
        pair = pair_of_day(longs, shorts, cfg.get("peer_groups"), "densest",
                           (cfg.get("pair") or {}).get("crowded_conf_warn", 3),
                           legs_per_side)

        chosen = set()
        for side, key in (("LONG", "long"), ("SHORT", "short")):
            leg = pair.get(key) or {}
            if leg.get("status") == "NONE":
                continue
            for r in [leg["pick"]] + list(leg.get("extra") or []):
                chosen.add((r["t"], side))
                legs.append({"t": r["t"], "date": d, "side": side, "role": "pair",
                             "conf": r["confidence"], "p_up": r["p_up"]})
        for side, picks in (("LONG", longs), ("SHORT", shorts)):
            for r in picks:
                if (r["t"], side) in chosen:
                    continue
                legs.append({"t": r["t"], "date": d, "side": side, "role": "board",
                             "conf": r["confidence"], "p_up": r["p_up"]})
    return legs


# --------------------------------------------------------------------------
# reporting helpers
# --------------------------------------------------------------------------

def quarters(dates: list, n: int = 4) -> list:
    """Split sorted unique dates into n contiguous calendar blocks."""
    u = sorted(set(dates))
    if len(u) < n:
        return [set(u)]
    edges = np.linspace(0, len(u), n + 1).astype(int)
    return [set(u[edges[i]:edges[i + 1]]) for i in range(n)]


def curve(legs: list, grid: list, panel_idx: dict, cost_bps: float = 0.0) -> pd.DataFrame:
    """Capture at each candidate exit -- raw, risk-adjusted, and net of cost.

    THE TRAP THIS AVOIDS: comparing raw means across exit times is not a fair
    comparison. At 09:50 only ~0.1% of price movement has happened; by the
    close it is ~0.9%. An early exit therefore posts a smaller mean for a
    purely mechanical reason, and a naive read calls the close "better" when it
    may only be "longer". Two columns fix this:

      ir    = mean / std, the edge per unit of risk actually borne -- the
              quantity that survives being levered up or down;
      scaled= ir * (std at the close), i.e. what the early exit would return if
              it were sized up to carry the SAME risk as a held-to-close leg.

    `cost_bps` is a round-trip execution charge in basis points, applied to
    every exit equally. It does not change which exit wins on raw capture, but
    it decides whether a winning early exit is still worth taking: a 0.03%
    edge does not survive a 0.05% spread.
    """
    out = []
    for m in grid:
        vals = [capture_at(panel_idx, l["t"], l["date"], l["side"], m)
                for l in legs]
        vals = [v for v in vals if v is not None]
        if len(vals) < 20:
            continue
        arr = np.array(vals)
        sd = arr.std(ddof=1)
        out.append({"mins": m, "clock": clock(m), "n": len(arr),
                    "mean": arr.mean(), "std": sd,
                    "se": sd / np.sqrt(len(arr)),
                    "ir": arr.mean() / sd if sd else 0.0,
                    "hit": float((arr > 0).mean()),
                    "net": arr.mean() - cost_bps / 100.0})
    df = pd.DataFrame(out)
    if not df.empty:
        df["scaled"] = df["ir"] * df["std"].iloc[-1]
    return df


def clock(mins: int) -> str:
    base = dt.datetime(2000, 1, 1, 9, 45) + dt.timedelta(minutes=mins)
    return base.strftime("%H:%M")


def twins_panel(cache: str) -> tuple:
    """Sample D: 20 US dual-listings, hourly, ~2 years — the independent check.

    Entry is the first hourly bar's close (10:30), not 09:45, so this measures
    the SHAPE of intraday decay on a different period and a different set of
    names. It cannot certify a live level. Same caveat as validate_twins.py.
    """
    import validate_twins as vt

    ppath = os.path.join(cache, "exit_panel_1h.csv")
    fpath = os.path.join(cache, "exit_feats_1h.csv")
    if os.path.exists(ppath) and os.path.exists(fpath):
        return pd.read_csv(ppath), pd.read_csv(fpath)

    recs, frows = [], []
    for tsx, us in vt.TWINS.items():
        res = vt.fetch_hourly(us)
        if not res:
            continue
        bars = vt.bars_df(res)
        frows += vt.session_rows(bars, tsx)
        for d, day in bars.groupby(bars.index.date):
            day = day.sort_index()
            if len(day) < vt.MIN_BARS:
                continue
            pe = float(day["Close"].iloc[vt.ENTRY_IDX])
            if not pe:
                continue
            te = day.index[vt.ENTRY_IDX]
            for ts, row in day.iloc[vt.ENTRY_IDX + 1:].iterrows():
                mins = int((ts - te).total_seconds() // 60)
                recs.append({"t": tsx, "date": str(d), "mins": mins,
                             "px": float(row["Close"]), "p945": pe})
    panel = pd.DataFrame(recs)
    panel["ret"] = (panel["px"] / panel["p945"] - 1) * 100
    feats = pd.DataFrame(frows)
    feats["vp"] = feats.groupby("t")["v15"].transform(lambda s: s / (s.median() or 1))
    os.makedirs(cache, exist_ok=True)
    panel.to_csv(ppath, index=False)
    feats.to_csv(fpath, index=False)
    return panel, feats


def live_legs(ledger_csv: str = "ledger.csv") -> list:
    """Sample C: the real executed pair legs, straight out of the ledger."""
    if not os.path.exists(ledger_csv):
        return []
    df = pd.read_csv(ledger_csv)
    df = df[(df["role"] == "pair") & df["r1"].notna()]
    return [{"t": r["ticker"], "date": r["date"], "side": r["side"],
             "role": "live"} for _, r in df.iterrows()]


def verdict(cv: pd.DataFrame, legs: list, panel_idx: dict, grid: list,
            label: str) -> dict:
    """Apply the pre-registered bar to a capture curve. Prints as it goes."""
    if cv.empty:
        print(f"  {label}: no curve (too few legs)")
        return {}
    close_row = cv.iloc[-1]
    base = close_row["mean"]
    best = cv.loc[cv["mean"].idxmax()]
    bir = cv.loc[cv["ir"].idxmax()]
    print(f"  {label}: n={int(close_row['n'])} legs, close ({close_row['clock']}) "
          f"mean {base:+.3f}%  std {close_row['std']:.2f}  "
          f"ir {close_row['ir']:+.3f}  hit {close_row['hit']:.0%}")
    print(f"    best RAW exit : {best['clock']} mean {best['mean']:+.3f}% "
          f"hit {best['hit']:.0%}  (diff {best['mean'] - base:+.3f}%, "
          f"1 se ~{best['se']:.3f}%)")
    print(f"    best RISK-ADJ : {bir['clock']} ir {bir['ir']:+.3f} vs close "
          f"{close_row['ir']:+.3f}  -> at close-equivalent size "
          f"{bir['scaled']:+.3f}% vs {base:+.3f}%")

    # criterion 3: smoothness -- the +/- 15 minute neighbours must also beat close
    nb = cv[(cv["mins"] >= best["mins"] - 15) & (cv["mins"] <= best["mins"] + 15)]
    smooth = bool((nb["mean"] > base).all()) and len(nb) >= 3
    # criterion 5: exceeds one standard error of the difference
    beats_se = bool(best["mean"] - base > best["se"])
    print(f"    smooth (+/-15m all beat close): {smooth}   "
          f"gain > 1 se: {beats_se}")

    # criterion 2: all four contiguous quarters
    qs = quarters([l["date"] for l in legs])
    qflags = []
    for q in qs:
        sub = [l for l in legs if l["date"] in q]
        a = [capture_at(panel_idx, l["t"], l["date"], l["side"], int(best["mins"]))
             for l in sub]
        b = [capture_at(panel_idx, l["t"], l["date"], l["side"], grid[-1])
             for l in sub]
        a = [v for v in a if v is not None]
        b = [v for v in b if v is not None]
        qflags.append(bool(a and b and np.mean(a) > np.mean(b)))
    print(f"    quarters improving: {sum(qflags)}/{len(qflags)}  {qflags}")
    return {"base": base, "best": best, "smooth": smooth, "se": beats_se,
            "quarters": qflags, "curve": cv}


def dump_curve(cv: pd.DataFrame, every: int = 6, cost_bps: float = 4.0) -> None:
    """Print the whole capture curve so its SHAPE is visible, not just its max.

    A single winning exit proves nothing across 75 candidates; a monotone trend
    across the whole session is a mechanism. `cost_bps` is charged round-trip so
    an early exit whose edge is smaller than the spread is visibly unprofitable.
    """
    if cv.empty:
        return
    keep = sorted(set(list(range(0, len(cv), every)) + [len(cv) - 1]))
    print(f"    {'exit':>6} {'n':>5} {'mean':>8} {'std':>6} {'ir':>7} "
          f"{'hit':>5} {'net of ' + str(int(cost_bps)) + 'bp':>12}")
    for i in keep:
        r = cv.iloc[i]
        print(f"    {r['clock']:>6} {int(r['n']):>5} {r['mean']:>+8.3f} "
              f"{r['std']:>6.2f} {r['ir']:>+7.3f} {r['hit']:>5.0%} "
              f"{r['mean'] - cost_bps / 100.0:>+12.3f}")


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--cache", default=SCRATCH)
    ap.add_argument("--rebuild", action="store_true")
    ap.add_argument("--config", default="config.yaml")
    args = ap.parse_args(argv)

    cfg = load_config(args.config)
    uni = cfg.get("scan", {}).get("universe") or []
    ppath = os.path.join(args.cache, "exit_panel_5m.csv")
    fpath = os.path.join(args.cache, "exit_feats_5m.csv")

    if os.path.exists(ppath) and os.path.exists(fpath) and not args.rebuild:
        panel, feats = pd.read_csv(ppath), pd.read_csv(fpath)
        print(f"panel: reused {ppath}")
    else:
        os.makedirs(args.cache, exist_ok=True)
        panel, feats = build_panel(uni)
        panel.to_csv(ppath, index=False)
        feats.to_csv(fpath, index=False)
        print(f"panel: built and cached -> {ppath}")

    n_sess = panel.groupby(["t", "date"]).ngroups
    print(f"panel: {len(panel):,} bars / {n_sess:,} ticker-sessions / "
          f"{panel['date'].nunique()} dates / {panel['t'].nunique()} names")
    grid = exit_grid(panel)
    print(f"exit grid: {len(grid)} candidates {clock(grid[0])}..{clock(grid[-1])}")
    panel_idx = {(r.t, r.date, r.mins): r.ret for r in panel.itertuples()}

    print("\n--- LAYER 1: model-free path shape (all 1,260 ticker-sessions) ---")
    layer1(panel, grid)

    print("\n--- LAYER 2: the shipped picks, walk-forward ---")
    legs = walk_forward_legs(feats, cfg,
                             min_p=(cfg.get("report") or {}).get("min_sided_p", 0.55),
                             legs_per_side=(cfg.get("pair") or {}).get("legs_per_side", 2))
    pair_legs = [l for l in legs if l["role"] == "pair"]
    board_legs = [l for l in legs if l["role"] == "board"]
    print(f"generated {len(pair_legs)} PAIR legs and {len(board_legs)} board legs "
          f"over {len(set(l['date'] for l in legs))} test sessions")
    res = {}
    for label, ls in (("A/PAIR", pair_legs), ("B/BOARD", board_legs),
                      ("A+B/ALL", legs)):
        cv = curve(ls, grid, panel_idx)
        res[label] = verdict(cv, ls, panel_idx, grid, label)
        if label == "A/PAIR":
            dump_curve(cv)
            windows(ls, panel_idx, label)

    print("\n--- SAMPLE C: the REAL executed ledger legs, replayed bar by bar ---")
    lv = [l for l in live_legs()
          if (l["t"], l["date"], grid[-1]) in panel_idx]
    print(f"  {len(lv)} of the ledger's pair legs fall inside the 60-day panel")
    if lv:
        res["C/LIVE"] = verdict(curve(lv, grid, panel_idx), lv, panel_idx, grid,
                                "C/LIVE")
        windows(lv, panel_idx, "C/LIVE")

    print("\n--- SAMPLE D: 20 US twins, hourly, ~2 years (independent) ---")
    tp, tf = twins_panel(args.cache)
    tgrid = exit_grid(tp, min_cover=0.8)
    tidx = {(r.t, r.date, r.mins): r.ret for r in tp.itertuples()}
    print(f"  panel: {tp.groupby(['t','date']).ngroups:,} ticker-sessions, "
          f"exits {[clock_from(m, 10, 30) for m in tgrid]}")
    tlegs = walk_forward_legs(tf, cfg, min_train=200, legs_per_side=2,
                              need_labels=False)
    tp_legs = [l for l in tlegs if l["role"] == "pair"]
    print(f"  {len(tp_legs)} PAIR legs over "
          f"{len(set(l['date'] for l in tp_legs))} test sessions")
    tcv = curve(tp_legs, tgrid, tidx)
    if not tcv.empty:
        tcv["clock"] = [clock_from(m, 10, 30) for m in tcv["mins"]]
        res["D/TWINS"] = verdict(tcv, tp_legs, tidx, tgrid, "D/TWINS")
    return panel, feats, grid, panel_idx, legs, res


def windows(legs: list, panel_idx: dict, label: str,
            edges=(0, 15, 45, 75, 135, 195, 255, 315, 375)) -> pd.DataFrame:
    """Where in the day does capture actually accrue?

    The capture CURVE is cumulative, so a single good stretch makes every later
    exit look good and the eye reads a trend that is not there. Differencing it
    into consecutive windows removes that: each row is the capture earned in
    that window alone, so a real "the edge dies at 11:00" shows up as positive
    early rows and zero later ones, and a mirage shows up as noise.
    """
    print(f"\n  incremental capture by window -- {label} (n={len(legs)})")
    rows = []
    for a, b in zip(edges[:-1], edges[1:]):
        v = []
        for l in legs:
            pa = 0.0 if a == 0 else panel_idx.get((l["t"], l["date"], a))
            pb = panel_idx.get((l["t"], l["date"], b))
            if pa is None or pb is None:
                continue
            v.append((pb - pa) * (1 if l["side"] == "LONG" else -1))
        if len(v) < 20:
            continue
        arr = np.array(v)
        se = arr.std(ddof=1) / np.sqrt(len(arr))
        rows.append({"win": f"{clock(a)}->{clock(b)}", "n": len(arr),
                     "mean": arr.mean(), "se": se,
                     "t": arr.mean() / se if se else 0.0})
        print(f"    {rows[-1]['win']:>13}  mean {arr.mean():+.4f}%  "
              f"se {se:.4f}  t {rows[-1]['t']:+.2f}")
    return pd.DataFrame(rows)


def clock_from(mins: int, h: int, m: int) -> str:
    return (dt.datetime(2000, 1, 1, h, m) +
            dt.timedelta(minutes=int(mins))).strftime("%H:%M")


def layer1(panel: pd.DataFrame, grid: list) -> None:
    """Model-free: does the 9:45->T move continue or revert into the close?

    If the rest-of-day move is NEGATIVELY correlated with the move so far, the
    tape hands back what it gave and an earlier exit is structurally better for
    ANY signal. If it is ~zero, exit timing is a pure variance question and the
    close is as good as anything.
    """
    wide = panel.pivot_table(index=["t", "date"], columns="mins", values="ret")
    last = grid[-1]
    if last not in wide.columns:
        return
    rows = []
    for m in grid[:-1]:
        if m not in wide.columns:
            continue
        sub = wide[[m, last]].dropna()
        if len(sub) < 100:
            continue
        so_far = sub[m]
        rest = sub[last] - sub[m]
        rows.append({"clock": clock(m), "n": len(sub),
                     "corr": float(np.corrcoef(so_far, rest)[0, 1]),
                     "frac_range": float(so_far.abs().mean() /
                                         sub[last].abs().mean())})
    df = pd.DataFrame(rows)
    show = df[df["clock"].isin(["10:00", "10:30", "11:00", "11:30", "12:00",
                               "12:30", "13:00", "13:30", "14:00", "14:30",
                               "15:00", "15:30", "15:45"])]
    print("  exit   corr(move so far, rest of day)   |move so far| / |full day|")
    for _, r in show.iterrows():
        print(f"  {r['clock']}          {r['corr']:+.3f}                    "
              f"{r['frac_range']:.2f}")


if __name__ == "__main__":
    main()
