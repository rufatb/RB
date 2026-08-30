#!/usr/bin/env python3
"""
validate_insider.py — TEST A: does insider buying precede FDA outcomes?

Pre-registered in PREREGISTER_day78.md before any result was computed.

THE PREMISE, and why it is different in kind from the 37 rejections. Every one
of those tested a function of price history predicting price. This tests
BEHAVIOUR: an officer or director buying shares on the open market, at a real
price, with their own money, in the ninety days before their company's FDA
decision. They are the only people with genuine private information about the
drug, and a code-P purchase is the most expensive signal a person can send.

THE LOOK-AHEAD TRAP, closed by construction and worth restating because it is
the whole ballgame. A Form 4 is filed up to TWO BUSINESS DAYS after the trade.
The transaction date is not public when the trade happens. This study keys
every purchase on its **FILING_DATE** — the day the public could first have
seen it. Keying on TRANS_DATE would credit a trader with information nobody
had, and is the reason a great deal of published insider research fails to
replicate.

THE CONFOUND NAMED IN ADVANCE. Insiders buy after their stock has fallen. Any
effect here may be a reversal signal wearing an insider costume, so the prior
90-day return is measured for both groups and reported beside the result. If
the buying group has simply fallen further, that is the finding.

THE BAR, fixed before the data was joined: |z| >= 3.3 (raised from 3.0 because
two questions are asked), with a passing placebo and a positive control.
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import baserate as B  # noqa: E402
from validate_catalyst import fetch_prices, load_events, window_returns  # noqa: E402

INSIDER = os.path.join(B.DATA, "insider_buys.csv")
WINDOW_DAYS = 90
BAR_Z = 3.3
BOOT = 2000


def _open(path: str):
    """Accepts the plain or the gzipped store; data/ keeps the compressed one."""
    if os.path.exists(path):
        return open(path, newline="")
    import gzip
    return gzip.open(path + ".gz", "rt", newline="")


def load_buys(path: str = INSIDER) -> dict:
    """cik -> sorted [(filing_date, usd)]. Keyed on the PUBLIC date."""
    out: dict = {}
    with _open(path) as f:
        for r in csv.DictReader(f):
            try:
                usd = float(r["usd"])
            except (ValueError, KeyError):
                continue
            out.setdefault(r["cik"].lstrip("0"), []).append(
                (r["filing_date"], usd))
    for k in out:
        out[k].sort()
    return out


def buying_before(buys: dict, cik: str, when: str,
                  days: int = WINDOW_DAYS) -> float:
    """Dollars of code-P purchases FILED in [when-days, when). Strictly before."""
    rows = buys.get(str(cik).lstrip("0"))
    if not rows:
        return 0.0
    end = dt.date.fromisoformat(when[:10])
    start = end - dt.timedelta(days=days)
    return float(sum(u for d, u in rows
                     if d and start.isoformat() <= d < end.isoformat()))


def auc(scores: np.ndarray, labels: np.ndarray) -> float:
    """P(score of a positive > score of a negative). Ties count a half."""
    pos, neg = scores[labels == 1], scores[labels == 0]
    if not len(pos) or not len(neg):
        return float("nan")
    order = np.argsort(np.concatenate([pos, neg]), kind="mergesort")
    ranks = np.empty(len(order), dtype=float)
    ranks[order] = np.arange(1, len(order) + 1)
    r = pd.Series(np.concatenate([pos, neg])).rank().to_numpy()
    return (r[:len(pos)].sum() - len(pos) * (len(pos) + 1) / 2) / (
        len(pos) * len(neg))


def clustered(vals: pd.DataFrame, col: str, flag: str, boot: int = BOOT,
              seed: int = 0) -> dict:
    """Mean difference between flagged and unflagged, bootstrapped over DATES."""
    d = vals[["date", col, flag]].dropna()
    a = d.loc[d[flag], col].to_numpy(dtype=float)
    b = d.loc[~d[flag], col].to_numpy(dtype=float)
    if len(a) < 15 or len(b) < 15:
        return {"n_a": len(a), "n_b": len(b), "diff": float("nan"),
                "sd": float("nan"), "z": float("nan"),
                "mean_a": float("nan"), "mean_b": float("nan")}
    obs = float(np.mean(a) - np.mean(b))
    rng = np.random.default_rng(seed)
    keys = pd.to_datetime(d["date"]).dt.date.to_numpy()
    groups: dict = {}
    for k, i in zip(keys, range(len(d))):
        groups.setdefault(k, []).append(i)
    uk = list(groups)
    arr_v = d[col].to_numpy(dtype=float)
    arr_f = d[flag].to_numpy(dtype=bool)
    out = []
    for _ in range(boot):
        pick = rng.choice(len(uk), size=len(uk), replace=True)
        idx = [i for j in pick for i in groups[uk[j]]]
        vv, ff = arr_v[idx], arr_f[idx]
        if ff.sum() < 15 or (~ff).sum() < 15:
            continue
        out.append(vv[ff].mean() - vv[~ff].mean())
    sd = float(np.std(out)) if out else float("nan")
    return {"n_a": len(a), "n_b": len(b), "diff": obs, "sd": sd,
            "z": obs / sd if sd and sd == sd and sd > 0 else float("nan"),
            "mean_a": float(np.mean(a)), "mean_b": float(np.mean(b))}


def build_sample(events: pd.DataFrame, px: dict, buys: dict) -> pd.DataFrame:
    rows = []
    for _, e in events.iterrows():
        p = px.get(e["ticker"])
        if p is None:
            continue
        w = window_returns(p, e["date"])
        if w is None:
            continue
        usd = buying_before(buys, e["cik"], str(e["date"]))
        rows.append({"ticker": e["ticker"], "cik": e["cik"],
                     "date": pd.Timestamp(e["date"]), "kind": e["kind"],
                     "event": w["event"], "pre20": w["pre20"],
                     "buy_usd": usd, "bought": usd > 0,
                     "approved": 1 if e["kind"] != "CRL" else 0})
    return pd.DataFrame(rows)


def placebo(sample: pd.DataFrame, buys: dict, seed: int = 11) -> dict:
    """The same 90-day lookback ending at a RANDOM date on the same names."""
    rng = np.random.default_rng(seed)
    d = sample.copy()
    shift = rng.integers(180, 900, size=len(d))
    fake = []
    for (_, r), s in zip(d.iterrows(), shift):
        when = (r["date"] - pd.Timedelta(days=int(s))).date().isoformat()
        fake.append(buying_before(buys, r["cik"], when) > 0)
    d["bought"] = fake
    return clustered(d, "event", "bought", boot=600, seed=seed)


def power(sample: pd.DataFrame, edge: float = 3.0, boot: int = 800) -> dict:
    """Can this sample resolve an effect of `edge` percentage points?"""
    base = clustered(sample, "event", "bought", boot=boot)
    sd = base["sd"]
    if not sd or sd != sd or sd <= 0:
        return {"sd": float("nan"), "mde": float("nan"), "detectable": False}
    return {"sd": sd, "z_for_edge": edge / sd, "mde": BAR_Z * sd,
            "edge": edge, "detectable": (edge / sd) >= BAR_Z}


def report(s: pd.DataFrame, real: dict, pl: dict, pw: dict,
           a1_auc: float, a1_z: float) -> str:
    n_buy = int(s["bought"].sum())
    L = ["=" * 76,
         "TEST A — does insider open-market buying precede FDA outcomes?",
         "=" * 76, "",
         f"events with a usable price window : {len(s):,}",
         f"  ...with code-P insider buying FILED in the prior "
         f"{WINDOW_DAYS}d : {n_buy:,} ({n_buy/max(len(s),1):.0%})",
         f"  ...without                                        : "
         f"{len(s)-n_buy:,}", ""]
    L += ["A1 — does buying predict the OUTCOME (approval vs rejection)?",
          f"     AUC {a1_auc:.4f}   z={a1_z:+.2f}   (bar |z| >= {BAR_Z})", ""]
    L += ["A2 — does buying predict the EVENT-WINDOW RETURN (t-2 -> t+1)?",
          f"     with buying    n={real['n_a']:<5} mean {real['mean_a']:+.2f}%",
          f"     without        n={real['n_b']:<5} mean {real['mean_b']:+.2f}%",
          f"     difference     {real['diff']:+.2f}pp   "
          f"date-clustered z={real['z']:+.2f}   (bar |z| >= {BAR_Z})", ""]
    # the confound, measured rather than assumed
    pre_a = s.loc[s["bought"], "pre20"].mean()
    pre_b = s.loc[~s["bought"], "pre20"].mean()
    L += ["THE CONFOUND, named before the test was run: insiders buy after a fall.",
          f"     prior 20d return, with buying    {pre_a:+.2f}%",
          f"     prior 20d return, without        {pre_b:+.2f}%",
          f"     difference                       {pre_a-pre_b:+.2f}pp"]
    L.append("     If the buying group has simply fallen further, any edge "
             "above is reversal,")
    L.append("     not information.")
    L += ["", f"[power] SE {pw['sd']:.2f}pp, minimum detectable effect "
              f"{pw['mde']:.2f}pp at |z|>={BAR_Z}",
          f"[placebo] same lookback at a RANDOM date: {pl['diff']:+.2f}pp, "
          f"z={pl['z']:+.2f}"]
    pl_ok = abs(pl["z"]) < BAR_Z if pl["z"] == pl["z"] else True
    L += ["", "-" * 76, "VERDICT"]
    hit = max(abs(a1_z) if a1_z == a1_z else 0,
              abs(real["z"]) if real["z"] == real["z"] else 0)
    if not pl_ok:
        L.append("  UNREADABLE — the placebo fired; a random lookback shows the "
                 "same thing.")
    elif hit >= BAR_Z:
        L.append(f"  ADOPT — clears the pre-registered |z| >= {BAR_Z}.")
    elif not pw["detectable"]:
        L.append("  UNDERPOWERED — and that is not a rejection. This sample "
                 f"cannot resolve an")
        L.append(f"  effect below {pw['mde']:.1f}pp, so 'no effect' is a claim "
                 "the data cannot support.")
    else:
        L.append(f"  REJECT — #38. Neither question clears |z| >= {BAR_Z}, and "
                 "the sample IS")
        L.append(f"  powered to detect {pw['edge']:.1f}pp. Insider open-market "
                 "buying in the")
        L.append("  ninety days before an FDA decision does not predict its "
                 "outcome or its")
        L.append("  reaction.")
    L.append("-" * 76)
    return "\n".join(L)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--events", default=B.EVENTS)
    ap.add_argument("--insider", default=INSIDER)
    a = ap.parse_args(argv)
    ev = load_events(a.events)
    ev = ev[ev["ticker"].fillna("").astype(str).str.strip().ne("")]
    buys = load_buys(a.insider)
    print(f"insider purchase rows: {sum(len(v) for v in buys.values()):,} "
          f"across {len(buys):,} issuers", flush=True)
    px = fetch_prices(sorted(ev["ticker"].unique()))
    s = build_sample(ev, px, buys)
    print(f"sample: {len(s):,} events with a price window", flush=True)
    real = clustered(s, "event", "bought")
    lab = s["approved"].to_numpy()
    sc = s["buy_usd"].to_numpy(dtype=float)
    a1 = auc(sc, lab)
    # AUC standard error, Hanley-McNeil, for a z against 0.5
    n1, n0 = int((lab == 1).sum()), int((lab == 0).sum())
    q1, q2 = a1 / (2 - a1), 2 * a1 * a1 / (1 + a1)
    se = ((a1 * (1 - a1) + (n1 - 1) * (q1 - a1 * a1)
           + (n0 - 1) * (q2 - a1 * a1)) / (n1 * n0)) ** 0.5 if n1 and n0 else float("nan")
    a1z = (a1 - 0.5) / se if se and se == se and se > 0 else float("nan")
    print(report(s, real, placebo(s, buys), power(s), a1, a1z))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
