#!/usr/bin/env python3
"""
validate_pool.py — does a universe of HUNDREDS of names beat 21? (day-40)

WHY RE-ASK: day-14 tested 21 -> 61 names and rejected it, but that ran on a
60-day window (day-12's own lesson: 60-day windows produce mirages), without a
placebo, and it conflated two different things. Day-14 did find a real
mechanism, and it is a SELECTOR fault rather than a breadth fault:

    low-volatility utilities and telecoms sit at the centre of the pooled
    feature space EVERY day, so they are permanently "familiar" and hijack the
    density selection -- no signal, tiny moves.

That diagnosis implies a fix nobody tried: rank each name's density against ITS
OWN history rather than against the whole cross-section, so "unusually familiar
for this name today" replaces "closest to the middle of everything". A wide
universe cannot be judged until that is separated out.

TWO CHANNELS, deliberately separated. Growing the universe gives you (a) more
CANDIDATES to choose from and (b) more TRAINING data. Only (a) is what "a
bigger pool to pick from" means, so the model here is trained on the FULL wide
universe in every arm and only the eligible candidate set changes. Same model,
different menu.

THE GRID
    pool size   21 (the shipped names), 21 random, 50, 100, all (~220)
    selector    densest (shipped) / max_p / self-relative density (the day-14
                fix) / random
  Sub-universes below full size are drawn REPEATEDLY and averaged, so a result
  is about breadth and not about which names happened to be drawn.

SAMPLES
    5m , 60 sessions   -- native 09:45 entry, thin
    1h , ~500 sessions -- 2 years, 10:30 entry. First native TSX deep sample
                          this repo has had; TSX hourly volume was 86% zeroed
                          when day-22 checked and is ~13% now.

SURVIVORSHIP: today's index membership applied backwards inflates absolute
returns. Every arm carries the same bias, so the BETWEEN-arm comparison -- the
only thing claimed here -- stands.

RESULTS (2026-08-13) -- REJECTED (#30). Breadth does not help.

  TSX 1h, 218 names, 654 test sessions (~3 years) -- mean book capture %:

      pool          densest    max_p   random  self-relative
      21 shipped    -0.0163  +0.0021  -0.0074   -0.0081
      21 random     -0.0146  -0.0021  -0.0041   -0.0057
      50 random     +0.0018  -0.0078  -0.0024   +0.0056
      100 random    -0.0014  -0.0079  -0.0017   -0.0063
      all (218)     +0.0122  -0.0217  +0.0206   -0.0020

  EVERY arm sits inside +/-0.022%, every t between -1.03 and +0.82, and there
  is no trend with pool size in any column. Best arm (all 218 / random,
  +0.0206%) is BELOW the placebo median (+0.0314%). p = 0.867.

  THE FINDING IS NOT "breadth dilutes the edge" -- it is that THERE IS NO EDGE
  TO DILUTE AT ANY BREADTH. Day-14 concluded "the familiarity edge lives in a
  compact universe"; with 30x the sessions that reads as wrong in an
  instructive way. The 21-name universe is not where the edge lives, it is
  just where 60 days of data were too thin to see its absence.

  THE DAY-14 FIX DOES NOT RESCUE IT. Self-relative density -- ranking a name's
  familiarity against its own history so permanently-central utilities stop
  hijacking selection -- was correctly motivated and changes nothing:
  -0.0020% at full breadth. A better ordering of a signal-free ranking is
  still signal-free.

  THE THIN SAMPLE WOULD HAVE LIED. On 29 native 5m sessions, all-220/densest
  scored -0.2512% (t -1.89) and looked like strong evidence that breadth
  actively HURTS. On 654 sessions the same arm is +0.0122% (t +0.65). Had only
  the 5m run existed, the write-up would have confidently reported a mechanism
  that does not exist -- which is exactly what day-14 did.

  WORTH KEEPING REGARDLESS: build_pool.py now yields 153,112 rows / 218 names /
  715 sessions of NATIVE TSX data. Every previous deep result in this repo
  leaned on 20 US dual-listings as a proxy; this replaces that proxy.
"""

from __future__ import annotations

import argparse
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from r945 import FEATS, HARD_CAP, HARD_FLOOR, K, M  # noqa: E402
from validate_exit import SCRATCH  # noqa: E402

SELECTORS = ["densest", "max_p", "self-relative", "random"]


def score_day(train: pd.DataFrame, today: pd.DataFrame) -> tuple:
    """Batched k-NN for every name on one date.

    NUMERICALLY IDENTICAL to r945.knn_probability -- same standardisation from
    the training pool, same K neighbours, same 1/(1+d) weighting, same Beta
    prior and same hard clamp -- but it standardises the training matrix ONCE
    per session instead of once per name. The shipped function rebuilds that
    matrix on every call, which is fine for 21 names a day and impossible for
    220 names x 500 sessions. tests/ pins the two against each other.
    """
    tr = train.dropna(subset=FEATS + ["r1"])
    if len(tr) < 200:
        return None, None
    mu, sd = tr[FEATS].mean(), tr[FEATS].std().replace(0, 1)
    Z = ((tr[FEATS] - mu) / sd).to_numpy()
    y = (tr["r1"].to_numpy() > 0).astype(float)
    q = ((today[FEATS] - mu) / sd).to_numpy(dtype=float)

    d2 = ((q[:, None, :] - Z[None, :, :]) ** 2).sum(axis=2)   # (n_today, n_tr)
    k = min(K, d2.shape[1])
    idx = np.argpartition(d2, k - 1, axis=1)[:, :k]
    dk = np.take_along_axis(d2, idx, axis=1)
    w = 1.0 / (1.0 + np.sqrt(dk))
    g = (y[idx] * w).sum(axis=1) / w.sum(axis=1)
    p = (g * K + 0.5 * M) / (K + M)
    p = np.clip(np.round(p, 3), HARD_FLOOR, HARD_CAP)
    nd = np.sqrt(dk).mean(axis=1)
    return p, nd


def walk_forward(feats: pd.DataFrame, window: int = 60, warmup: int = 60) -> list:
    """Rolling past-only window over the WIDE universe. One pass, all arms."""
    feats = feats.copy()
    feats["vp"] = feats.groupby("t")["v15"].transform(lambda s: s / (s.median() or 1))
    feats = feats.dropna(subset=FEATS)
    dates = sorted(feats["date"].unique())
    by_date = {d: g for d, g in feats.groupby("date")}
    days = []
    for i, d in enumerate(dates):
        if i < warmup:
            continue
        win = set(dates[max(0, i - window):i])
        train = pd.concat([by_date[x] for x in win if x in by_date])
        today = by_date[d].dropna(subset=["r1"])
        if today.empty:
            continue
        p, nd = score_day(train, today)
        if p is None:
            continue
        days.append({"date": d, "t": today["t"].to_numpy(),
                     "p": p, "nd": nd, "r": today["r1"].to_numpy()})
        if (i - warmup) % 50 == 0:
            print(f"    ... {i - warmup} sessions scored", flush=True)
    return days


def add_self_relative(days: list) -> None:
    """nd measured against the NAME'S OWN running history, not the tape's.

    This is the day-14 fix. A utility that is always at the centre of the
    feature cloud has a low nd every single day; dividing by its own trailing
    median nd makes that ordinary, and only a genuinely unusual-for-it setup
    ranks well.
    """
    hist: dict = {}
    for day in days:
        rel = np.empty(len(day["t"]))
        for j, t in enumerate(day["t"]):
            h = hist.get(t)
            rel[j] = day["nd"][j] / np.median(h) if h and len(h) >= 10 else 1.0
        day["nd_rel"] = rel
        for j, t in enumerate(day["t"]):
            hist.setdefault(t, []).append(day["nd"][j])


def book(days: list, eligible, selector: str, bar: float = 0.55,
         legs: int = 2, rng=None) -> np.ndarray:
    """Book capture per session for one (candidate set, selector) arm."""
    out = []
    for day in days:
        keep = np.array([t in eligible for t in day["t"]])
        if keep.sum() < 4:
            continue
        p, nd, r = day["p"][keep], day["nd"][keep], day["r"][keep]
        ndr = day["nd_rel"][keep]
        n = len(r)
        lm, sm = p >= bar, (1 - p) >= bar
        if rng is not None:
            perm = rng.permutation(n)
            nl, ns = int(lm.sum()), int(sm.sum())
            lm = np.zeros(n, bool); sm = np.zeros(n, bool)
            lm[perm[:nl]] = True
            sm[perm[nl:nl + ns]] = True
        if selector == "densest":
            order = np.argsort(nd, kind="stable")
        elif selector == "self-relative":
            order = np.argsort(ndr, kind="stable")
        elif selector == "random":
            order = (rng or np.random.default_rng(11)).permutation(n)
        else:
            order = None
        L = (np.argsort(-p, kind="stable") if order is None else order)
        S = (np.argsort(p, kind="stable") if order is None else order)
        L, S = L[lm[L]][:legs], S[sm[S]][:legs]
        if not len(L) and not len(S):
            continue
        v = 0.0
        if len(L):
            v += 0.5 * r[L].mean()
        if len(S):
            v += 0.5 * -r[S].mean()
        out.append(v)
    return np.array(out)


def arms(days: list, names: list, shipped: list, draws: int = 20) -> list:
    """(label, list-of-eligible-sets). Sub-universes are drawn repeatedly."""
    rs = np.random.default_rng(99)
    out = [("21 shipped", [set(n for n in shipped if n in names)]),
           ("all (%d)" % len(names), [set(names)])]
    for size in (21, 50, 100):
        if size >= len(names):
            continue
        out.append((f"{size} random",
                    [set(rs.choice(names, size, replace=False)) for _ in range(draws)]))
    return out


def run(days: list, names: list, shipped: list, nulls: int, label: str,
        min_sessions: int = 20) -> None:
    print(f"\n=== {label} ===")
    add_self_relative(days)
    grid, cells = [], {}
    for aname, sets in arms(days, names, shipped):
        for sel in SELECTORS:
            vals = [book(days, s, sel) for s in sets]
            vals = [v for v in vals if len(v) >= min_sessions]
            if not vals:
                continue
            m = float(np.mean([v.mean() for v in vals]))
            allv = np.concatenate(vals)
            sd = allv.std(ddof=1)
            t = allv.mean() / (sd / np.sqrt(len(vals[0]))) if sd else 0.0
            grid.append({"pool": aname, "selector": sel, "mean": m, "t": t,
                         "sessions": len(vals[0]), "draws": len(vals)})
            cells[(aname, sel)] = sets
    df = pd.DataFrame(grid)
    if df.empty:
        print("  no arm had enough scored sessions — sample too thin")
        return
    piv = df.pivot(index="pool", columns="selector", values="mean")
    print("\n  mean book capture per session (%)")
    print(piv.to_string(float_format=lambda v: f"{v:+.4f}"))
    print("\n  full detail")
    print(df.to_string(index=False, float_format=lambda v: f"{v:+.4f}"))

    if not nulls:
        return
    best = []
    for b in range(nulls):
        g = np.random.default_rng(7000 + b)
        m = []
        for (aname, sel), sets in cells.items():
            vals = [book(days, s, sel, rng=g) for s in sets[:3]]
            vals = [v for v in vals if len(v) >= min_sessions]
            if vals:
                m.append(float(np.mean([v.mean() for v in vals])))
        if m:
            best.append(max(m))
    bn = np.array(best)
    obs = df["mean"].max()
    p = float((bn >= obs).mean())
    top = df.loc[df["mean"].idxmax()]
    print(f"\n  best REAL arm : {top['pool']} / {top['selector']} "
          f"at {obs:+.4f}%  (t {top['t']:+.2f})")
    print(f"  placebo best  : median {np.median(bn):+.4f}%, "
          f"90th {np.quantile(bn, 0.9):+.4f}%, max {bn.max():+.4f}%")
    print(f"  p = {p:.3f}  ->  " + ("INSIDE the noise band" if p > 0.05
                                    else "CLEARS the band — run the autopsy"))


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--nulls", type=int, default=60)
    ap.add_argument("--cache", default=SCRATCH)
    ap.add_argument("--only", choices=["5m", "1h"])
    args = ap.parse_args(argv)

    from dashboard import load_config
    shipped = load_config("config.yaml").get("scan", {}).get("universe") or []

    for tag, fname, window, warmup, mins in (("5m", "pool_5m.csv", 30, 30, 15),
                                             ("1h", "pool_1h.csv", 60, 60, 20)):
        if args.only and args.only != tag:
            continue
        path = os.path.join(args.cache, fname)
        if not os.path.exists(path):
            print(f"missing {path} — run build_pool.py first")
            continue
        f = pd.read_csv(path)
        print(f"\n{tag}: {len(f):,} rows / {f['t'].nunique()} names / "
              f"{f['date'].nunique()} sessions")
        cpath = os.path.join(args.cache, f"pool_scored_{tag}.pkl")
        if os.path.exists(cpath):
            days = pd.read_pickle(cpath)
        else:
            days = walk_forward(f, window=window, warmup=warmup)
            pd.to_pickle(days, cpath)
        names = sorted(f["t"].unique())
        run(days, names, shipped, args.nulls,
            f"TSX {tag} — {len(names)} names, {len(days)} test sessions",
            min_sessions=mins)


if __name__ == "__main__":
    main()
