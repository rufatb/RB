#!/usr/bin/env python3
"""
validate_entry.py — is 9:46 the right time to run the report? (day-39)

WHY RE-ASK IT: day-21 raced 09:35/09:40/09:45/09:50/10:00/10:30 and kept 9:45,
with a careful paired follow-up. Two things have changed since:

  1. ITS DATASET CANNOT BE REBUILT. That run used a 1-year 5-minute twins set;
     Yahoo caps 5m history at 60 days, so the result is no longer reproducible
     from anything this repo can fetch. Day-22 rebuilt the deep set for exactly
     this reason -- a verdict that cannot be re-run is a verdict on trust.
  2. IT PREDATES THE PLACEBO CALIBRATION. Day-37 showed this grid manufactures
     winners from noise routinely (median best placebo config +0.368%/session).
     Any time-race judged only against a fixed baseline is unprotected against
     exactly that, and day-21 raced six times.

WHAT CHANGES WITH ENTRY TIME (why this is not the same question as day-36's
exit study): moving the entry moves BOTH ends. A later entry gives the model a
longer momentum window in r0 and more volume to judge vp against -- but leaves
less session to capture, and shrinks the training pool's usable range. Those
push in opposite directions, so it genuinely has to be measured.

TWO SAMPLES, opposite trade-offs:
  * TSX 5m, 60 sessions, 21 names -- native and fine-grained (09:35..11:00),
    but thin: ~35 test sessions.
  * US twins 1h, ~490 sessions, 20 names -- 2 years of power, but entries only
    on the hour (10:30 / 11:30 / 12:30 / 13:30).
Agreement between them is the evidence; either alone is not.

RESULTS (2026-08-13) -- 9:46 STANDS, and day-21's verdict is confirmed on
rebuildable data with a calibrated null. REJECTED (#29).

  TSX 5m, 35 test sessions          US twins 1h, ~288 test sessions, 2 years
    09:35  -0.0285%  t -0.25          10:30* -0.0212%  t -0.82
    09:40  +0.0802%  t +1.00          11:30  -0.0316%  t -1.39
    09:45* +0.0730%  t +0.56          12:30  -0.0064%  t -0.35
    09:50  +0.1034%  t +1.00          13:30  -0.0082%  t -0.52
    10:00  +0.0220%  t +0.23
    10:15  -0.0754%  t -0.87        best 12:30 at -0.0064%
    10:30  +0.0510%  t +0.66        placebo best: median +0.0185%
    11:00  +0.0690%  t +1.04        p = 0.940
  best 09:50 at +0.1034%
  placebo best: median +0.1212%    <- the placebo's TYPICAL winner beats the
  p = 0.640                           real one; nothing here is real.

  On two years EVERY entry time is NEGATIVE. The two samples also disagree
  about which time wins (09:50 vs 12:30) -- the instability signature day-21
  named when it refused 09:40.

  TWO THINGS THAT ARE REAL, and neither is an edge:
  * VARIANCE FALLS MONOTONICALLY with a later entry -- TSX std 0.667 -> 0.393,
    twins 0.440 -> 0.268 -- because less session remains. The mean does not
    rise with it. Identical in structure to day-36's exit finding: this
    strategy can buy less risk by shortening exposure, never more return.
  * "POSITIVE SESSIONS" RISES TO 66% at 10:30/11:00 on TSX while the mean
    stays flat. That is the scratch artifact day-35 built `decisive_line` to
    catch: shorter horizons produce smaller moves, so more of them land barely
    on the right side of zero. A win-rate that improves while the mean does
    not is a measurement artifact, not a better entry.

  WHY THIS RE-RUN WAS WORTH DOING even though it agreed with day-21: day-21's
  1-year 5m twins set can no longer be fetched, so its verdict rested on data
  nobody can regenerate. This one rebuilds from scratch with no key.

Usage:
    python validate_entry.py                 # both samples + null
    python validate_entry.py --nulls 200
    python validate_entry.py --rebuild
"""

from __future__ import annotations

import argparse
import os
import sys
from concurrent.futures import ThreadPoolExecutor

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from adapters import YahooDirectAdapter  # noqa: E402
from dashboard import load_config  # noqa: E402
from r945 import FEATS, extrapolation_check, knn_probability  # noqa: E402
from validate_exit import SCRATCH  # noqa: E402

# (bar index of the decision close, label). Index i => the (i+1)-th bar.
TSX_TIMES = [(0, "09:35"), (1, "09:40"), (2, "09:45*"), (3, "09:50"),
             (5, "10:00"), (8, "10:15"), (11, "10:30"), (17, "11:00")]
TW_TIMES = [(0, "10:30*"), (1, "11:30"), (2, "12:30"), (3, "13:30")]


def rows_at(bars: pd.DataFrame, ticker: str, i: int, min_bars: int) -> list:
    """Per-session features with the decision point at bar index `i`.

    Mirrors r945.session_rows with the entry bar parameterised. Everything the
    model sees is known at the decision bar's close; the outcome is that bar to
    the session close, so no configuration can peek.
    """
    out, prev_close = [], None
    for d, day in bars.groupby(bars.index.date):
        day = day.sort_index()
        if len(day) < max(min_bars, i + 3):
            if len(day):
                prev_close = day["Close"].iloc[-1]
            continue
        o = float(day["Open"].iloc[0])
        pe = float(day["Close"].iloc[i])
        c = float(day["Close"].iloc[-1])
        gap = (o / prev_close - 1) * 100 if prev_close else None
        prev_close = c
        if not o or not pe:
            continue
        out.append({"t": ticker, "date": str(d), "gap": gap,
                    "r0": (pe / o - 1) * 100,
                    "v15": float(day["Volume"].iloc[:i + 1].sum()),
                    "r1": (c / pe - 1) * 100})
    return out


def fetch_all(universe: list, interval: str, rng: str, tz: str,
              workers: int = 12) -> dict:
    a = YahooDirectAdapter(exchange_tz=tz)

    def one(t):
        try:
            return t, a._bars_df(a._chart(t, interval, rng))
        except Exception:
            return t, pd.DataFrame()

    with ThreadPoolExecutor(max_workers=workers) as ex:
        return dict(ex.map(one, universe))


def scored(feats: pd.DataFrame, min_train: int) -> list:
    """Walk-forward: per-session arrays of p_up / nd / outcome. Past-only."""
    feats = feats.copy()
    feats["vp"] = feats.groupby("t")["v15"].transform(lambda s: s / (s.median() or 1))
    dates = sorted(feats["date"].unique())
    days = []
    for k, d in enumerate(dates):
        if k < min_train:
            continue
        train = feats[feats["date"] < d].dropna(subset=FEATS + ["r1"])
        today = feats[feats["date"] == d]
        if len(train) < 100 or today.empty:
            continue
        P, N, R = [], [], []
        for _, r in today.iterrows():
            if any(pd.isna(r[f]) for f in FEATS) or pd.isna(r["r1"]):
                continue
            rec = {f: r[f] for f in FEATS}
            if not extrapolation_check(train, rec)[0]:
                continue
            res = knn_probability(train, rec)
            if res[0] is None:
                continue
            P.append(res[0]); N.append(res[2]); R.append(r["r1"])
        if len(R) >= 2:
            days.append({"date": d, "p": np.array(P), "nd": np.array(N),
                         "r": np.array(R)})
    return days


def book(days: list, bar: float = 0.55, legs: int = 2, rng=None) -> np.ndarray:
    """The shipped book shape: 2 densest legs a side, half the book per side."""
    out = []
    for day in days:
        p, nd, r = day["p"], day["nd"], day["r"]
        n = len(r)
        lm, sm = p >= bar, (1 - p) >= bar
        if rng is not None:
            perm = rng.permutation(n)
            nl, ns = int(lm.sum()), int(sm.sum())
            lm = np.zeros(n, bool); sm = np.zeros(n, bool)
            lm[perm[:nl]] = True
            sm[perm[nl:nl + ns]] = True
        order = np.argsort(nd, kind="stable")
        L = order[lm[order]][:legs]
        S = order[sm[order]][:legs]
        if not len(L) and not len(S):
            continue
        v = 0.0
        if len(L):
            v += 0.5 * r[L].mean()
        if len(S):
            v += 0.5 * -r[S].mean()
        out.append(v)
    return np.array(out)


def race(fetched: dict, times: list, min_bars: int, min_train: int,
         nulls: int, label: str) -> pd.DataFrame:
    print(f"\n=== {label} ===")
    rows, day_sets = [], {}
    for i, name in times:
        feats = []
        for t, bars in fetched.items():
            if not bars.empty:
                feats += rows_at(bars, t, i, min_bars)
        f = pd.DataFrame(feats)
        if f.empty:
            continue
        days = scored(f, min_train)
        day_sets[name] = days
        v = book(days)
        if len(v) < 20:
            continue
        sd = v.std(ddof=1)
        rows.append({"entry": name, "sessions": len(v), "mean": v.mean(),
                     "t": v.mean() / (sd / np.sqrt(len(v))) if sd else 0.0,
                     "std": sd, "pos": float((v > 0).mean()),
                     "legs_per_sess": np.mean([len(d["r"]) for d in days])})
        print(f"  {name:>8}  n={len(v):>3}  mean {v.mean():+.4f}%  "
              f"t {rows[-1]['t']:+.2f}  std {sd:.3f}  pos {rows[-1]['pos']:.0%}",
              flush=True)

    df = pd.DataFrame(rows)
    if df.empty or not nulls:
        return df

    # Placebo: the SAME race, with each entry time's directional calls
    # randomised. The statistic is the best entry time in the race, so the null
    # absorbs the fact that racing 8 times guarantees a winner.
    best_null = []
    for b in range(nulls):
        g = np.random.default_rng(5000 + b)
        m = [book(days, rng=g).mean() for days in day_sets.values()]
        best_null.append(max(m))
    bn = np.array(best_null)
    obs = df["mean"].max()
    p = float((bn >= obs).mean())
    win = df.loc[df["mean"].idxmax(), "entry"]
    print(f"\n  best entry on this sample : {win} at {obs:+.4f}%")
    print(f"  placebo best              : median {np.median(bn):+.4f}%, "
          f"90th {np.quantile(bn, 0.9):+.4f}%, max {bn.max():+.4f}%")
    print(f"  p = {p:.3f}  ->  " + ("INSIDE the noise band" if p > 0.05
                                    else "clears the band"))
    return df


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--nulls", type=int, default=100)
    ap.add_argument("--cache", default=SCRATCH)
    ap.add_argument("--rebuild", action="store_true")
    args = ap.parse_args(argv)

    cfg = load_config("config.yaml")
    uni = cfg.get("scan", {}).get("universe") or []
    print(f"fetching 5m TSX bars for {len(uni)} names...", flush=True)
    tsx = fetch_all(uni, "5m", "60d", "America/Toronto")
    a = race(tsx, TSX_TIMES, min_bars=20, min_train=25, nulls=args.nulls,
             label="TSX 5m — 60 sessions, native, fine-grained (thin)")

    import validate_twins as vt
    print("\nfetching 1h twin bars (~2 years)...", flush=True)
    tw = {}
    for tsx_t, us in vt.TWINS.items():
        res = vt.fetch_hourly(us)
        if res:
            tw[tsx_t] = vt.bars_df(res)
    b = race(tw, TW_TIMES, min_bars=5, min_train=200, nulls=args.nulls,
             label="US twins 1h — ~490 sessions, 2 years (coarse)")
    return a, b


if __name__ == "__main__":
    main()
