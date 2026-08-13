#!/usr/bin/env python3
"""
validate_shape.py — the SHAPE of the bet (day-38): how many picks, when to sit
out, and how long to hold.

WHY THIS EXISTS: day-37's sweep varied how the signal is USED across legs, side
mix, bar, selector and weekday -- but it always took a two-sided book, always
traded every session, and always held to that day's close. Three natural
questions were therefore still unanswered:

  1. ONE PICK A DAY -- not one per side, but a single directional bet: the
     highest-conviction name on the board regardless of which side it is on.
     Day-37 only ever tested 1 leg PER SIDE, which is a different thing.
  2. NO-TRADE DAYS -- an explicit abstention rule, rather than the implicit one
     a higher bar produces. Day-29 raised the bar and rejected it; that is not
     the same as sitting out when the board is ambiguous.
  3. LONGER HOLDS -- 3 days and 1 week, at BOOK level. Day-24 measured one
     night per leg and day-32 measured event swings; neither answered "what if
     the daily book simply held longer".

METHOD: same discipline as day-37, because the failure mode is the same. One
walk-forward pass supplies every configuration's model output, the grid is
swept jointly, and the whole grid is re-run on placebo books whose directional
calls are randomised. A winner must clear the PLACEBO'S BEST, not zero.

OVERLAPPING WINDOWS: a 3- or 5-day hold opened every session overlaps itself,
so consecutive observations are not independent and a naive t-stat is inflated
(roughly by sqrt(N)). Every multi-day t here is therefore computed on
NON-OVERLAPPING trades -- every Nth session -- while the mean uses all of them.

PER-DAY-OF-RISK: a 5-day hold that returns +0.25% is not better than a 1-day
hold that returns +0.10%; it ties up capital five times as long and eats five
times the overnight gap risk. Results report mean per trade AND per day held.

RESULTS (2026-08-13, first run -- recorded so the verdict is permanent):

  *** REJECTED (#26, #27, #28). None of the three shapes has an edge. The
      grid's best config is BELOW the placebo median: p = 0.920. ***

  best REAL config    : +0.1249%/day of risk
  best PLACEBO config : median +0.1643%, 90th +0.2175%, max +0.2956%
  A randomly-sided book routinely beats the best real one on this grid.

  1. ONE PICK PER DAY -- rejected. one-best/1 day/no abstention returns
     -0.0196%/trade, WORSE than the two-sided pair (+0.0004%). And the single
     pick is 83% LONG (239 long / 49 short): "one pick" is not a concentrated
     bet on the model's best idea, it is a directional bet on the market
     wearing a pick's clothing. Concentration also triples the volatility
     (std 1.149 vs 0.451) and takes the worst trade from -1.71% to -4.32%.

  2. NO-TRADE DAYS -- rejected. Five abstention rules (min conviction, top
     pick must be dense, conviction margin over the runner-up, deep board,
     none). No rule helps consistently: `top-dense` improves one-best and
     hurts pair1/pair2/one-dense, and every sign flips across shapes. That
     pattern is noise, not a filter. (Day-29 separately rejected simply
     raising the bar.)

  3. THREE-DAY AND ONE-WEEK HOLDS -- rejected, and this is the important one
     because the raw numbers look GREAT until decomposed:

       one-best / 5 days : +0.5393% per trade   <-- looks like a real edge
       whole universe    : +0.5298% over 5 days <-- the market paid that
       one-best / 3 days : +0.2507% per trade
       whole universe    : +0.2805% over 3 days <-- BELOW the market

     The entire multi-day gain is market drift collected by an 83% long book
     over a rising two-year sample. Selection adds ~0.01%. Hedge it properly
     (pair2/5d) and the drift disappears: +0.1123% per trade, t +0.94.

     The risk side is worse than the return side is good:
       pair2   / 1 day : std 0.451  worst trade  -1.71%
       one-best/ 5 days: std 4.584  worst trade -19.84%
     Ten times the volatility and a worst trade that would erase a year of
     the printed edge, in exchange for the market return you could have had
     from an index fund without the single-name risk.

  This also matches day-24 (one night doubles volatility, 2.3x worse tail)
  and day-32 (event swings: no edge) -- three independent measurements now
  say the same thing: this engine's signal does not survive past one session,
  and what looks like a multi-day edge is beta.

Usage:
    python validate_shape.py                 # full sweep + null
    python validate_shape.py --nulls 200
"""

from __future__ import annotations

import argparse
import itertools
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from validate_exit import SCRATCH  # noqa: E402

SHAPES = ["pair2", "pair1", "one-best", "one-dense"]
HORIZONS = [1, 3, 5]
ABSTAIN = ["none", "p>=0.60", "top-dense", "margin", "deep-board"]


def load(cache: str) -> pd.DataFrame:
    """day-37's scored table joined to the 1/3/5-day returns."""
    tab = pd.read_csv(os.path.join(cache, "sweep_table.csv"))
    hor = pd.read_csv(os.path.join(cache, "horizon.csv"))
    tab = tab.drop(columns=[c for c in ("r1",) if c in tab.columns])
    return tab.merge(hor, on=["t", "date"], how="inner")


def to_days(tab: pd.DataFrame) -> list:
    days = []
    for d, g in tab.groupby("date"):
        days.append({"date": d, "dow": g["dow"].iloc[0],
                     "p": g["p_up"].to_numpy(float),
                     "nd": g["nd"].to_numpy(float),
                     "r": {N: g[f"r{N}"].to_numpy(float) for N in HORIZONS}})
    return days


def skip(day: dict, rule: str, bar: float) -> bool:
    """Should the book sit out today? True = no trade.

    Each rule is a different theory of WHEN the engine is unreliable, and each
    is cheap to state: not confident enough, not familiar enough, not decisive
    enough, not enough to choose from.
    """
    p, nd = day["p"], day["nd"]
    sided = np.maximum(p, 1 - p)
    q = sided >= bar
    # every branch is cast to a plain bool: numpy comparisons return np.bool_,
    # which is falsy-correct but fails an `is True` identity check, so a caller
    # testing it that way would silently read every rule as "do not skip".
    if not q.any():
        return True
    if rule == "none":
        return False
    if rule == "p>=0.60":
        return bool(sided.max() < 0.60)
    if rule == "top-dense":
        # the best name must also be one of the more familiar ones today
        return bool(nd[np.argmax(sided)] > np.median(nd))
    if rule == "margin":
        # the top conviction must stand clear of the runner-up
        s = np.sort(sided[q])[::-1]
        return bool(len(s) < 2 or (s[0] - s[1]) < 0.02)
    if rule == "deep-board":
        return bool(int(q.sum()) < 6)
    return False


def book(days: list, shape: str, horizon: int, rule: str, bar: float = 0.55,
         rng=None):
    """Per-trade book capture for one configuration. Returns (all, dates)."""
    out, ds = [], []
    for day in days:
        p, nd, r = day["p"], day["nd"], day["r"][horizon]
        n = len(r)
        ok = np.isfinite(r)
        if not ok.any() or skip(day, rule, bar):
            continue
        lmask, smask = (p >= bar) & ok, ((1 - p) >= bar) & ok
        if rng is not None:
            perm = rng.permutation(n)
            nl, ns = int(lmask.sum()), int(smask.sum())
            lmask = np.zeros(n, bool); smask = np.zeros(n, bool)
            lmask[perm[:nl]] = True
            smask[perm[nl:nl + ns]] = True
            lmask &= ok; smask &= ok

        dense = np.argsort(nd, kind="stable")

        def take(mask, k):
            s = dense[mask[dense]]
            return s[:k]

        if shape in ("pair2", "pair1"):
            k = 2 if shape == "pair2" else 1
            L, S = take(lmask, k), take(smask, k)
            if not len(L) and not len(S):
                continue
            parts = []
            if len(L):
                parts.append(0.5 * r[L].mean())
            if len(S):
                parts.append(0.5 * -r[S].mean())
            val = sum(parts)
        else:
            # ONE pick for the whole day, either side. `one-best` takes the
            # highest sided conviction; `one-dense` takes the most familiar
            # qualified setup. Full book on that single name.
            sided = np.maximum(p, 1 - p)
            cand = np.where((lmask | smask))[0]
            if not len(cand):
                continue
            i = (cand[np.argmax(sided[cand])] if shape == "one-best"
                 else cand[np.argmin(nd[cand])])
            val = r[i] if lmask[i] else -r[i]
        out.append(val)
        ds.append(day["date"])
    return np.array(out), ds


def stat(vals: np.ndarray, horizon: int) -> tuple:
    """(mean per trade, mean per day held, t on NON-OVERLAPPING trades, n)."""
    if len(vals) < 20:
        return np.nan, np.nan, np.nan, len(vals)
    indep = vals[::horizon]                 # de-overlap before testing
    sd = indep.std(ddof=1)
    t = indep.mean() / (sd / np.sqrt(len(indep))) if sd else 0.0
    return vals.mean(), vals.mean() / horizon, t, len(vals)


def summarize(days: list, rng=None) -> pd.DataFrame:
    rows = []
    for shape, hz, rule in itertools.product(SHAPES, HORIZONS, ABSTAIN):
        v, _ = book(days, shape, hz, rule, rng=rng)
        m, per_day, t, n = stat(v, hz)
        if np.isnan(m):
            continue
        rows.append({"shape": shape, "hold_d": hz, "abstain": rule, "n": n,
                     "per_trade": m, "per_day": per_day, "t_indep": t,
                     "pos": float((v > 0).mean())})
    return pd.DataFrame(rows)


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--nulls", type=int, default=100)
    ap.add_argument("--cache", default=SCRATCH)
    args = ap.parse_args(argv)

    tab = load(args.cache)
    days = to_days(tab)
    print(f"table: {len(tab):,} name-days over {tab['date'].nunique()} sessions")

    real = summarize(days).sort_values("per_day", ascending=False)
    print(f"\n=== {len(real)} configurations "
          f"({len(SHAPES)} shapes x {len(HORIZONS)} holds x {len(ABSTAIN)} rules) ===")
    print("\nRANKED BY RETURN PER DAY OF CAPITAL AT RISK")
    print(real.to_string(index=False, float_format=lambda v: f"{v:+.4f}"))

    base = real[(real.shape_ if False else real["shape"] == "pair2") &
                (real["hold_d"] == 1) & (real["abstain"] == "none")]
    if len(base):
        b = base.iloc[0]
        print(f"\nSHIPPED (pair2 / 1 day / no abstention): per_trade "
              f"{b['per_trade']:+.4f}%  t {b['t_indep']:+.2f}  "
              f"rank {list(real.index).index(b.name) + 1} of {len(real)}")

    print(f"\n=== NULL: {args.nulls} placebo sweeps (sides randomised) ===")
    best = []
    for i in range(args.nulls):
        nl = summarize(days, rng=np.random.default_rng(2000 + i))
        best.append(nl["per_day"].max())
        if (i + 1) % 25 == 0:
            print(f"    ... {i + 1}/{args.nulls}", flush=True)
    bn = np.array(best)
    obs = real["per_day"].max()
    p = float((bn >= obs).mean())
    print(f"\n  best REAL   : {obs:+.4f}%/day of risk")
    print(f"  best PLACEBO: median {np.median(bn):+.4f}%, "
          f"90th {np.quantile(bn, 0.9):+.4f}%, max {bn.max():+.4f}%")
    print(f"  p = {p:.3f}")
    print("\n  " + ("*** inside the noise band — none of these shapes has a "
                    "demonstrated edge ***" if p > 0.05 else
                    "*** clears the placebo band — run the autopsy ***"))
    return real, bn


if __name__ == "__main__":
    main()
