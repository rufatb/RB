#!/usr/bin/env python3
"""
validate_exdiv.py — does the ex-dividend date poison the `gap` feature?

THE SUSPICION, and it is mechanical rather than statistical. `gap` is
open/prev_close - 1. On an ex-dividend morning the open is LOWER by the
dividend for a reason that carries no information about the rest of the day —
the shareholder was paid, nothing was learned. The engine cannot tell that
apart from a 3% gap caused by overnight news, and `r945.py`'s own header admits
the tool has "NO earnings/dividend/news feed".

The sizes are not trivial on this universe. Measured live:

    T.TO   $0.418 quarterly on a $13.61 price = 3.07% of price
    ENB.TO $0.970 quarterly on a $69.54 price = 1.39%
    BCE.TO $0.438 quarterly on a $32.65 price = 1.34%

A fake -3.07% gap is far outside the normal range of the feature, so those rows
land in a corner of the k-NN's space populated by genuinely bad overnight news.

WHAT IS MEASURED, in the order that can kill the idea cheapest:
  1  FREQUENCY   how many ticker-sessions are ex-dividend at all. If it is a
                 fraction of a percent the fix cannot matter however right the
                 mechanism is.
  2  DISTORTION  how far the gap on those days sits from the name's normal gap.
                 This is the size of the lie being told to the model.
  3  OUTCOME     do ex-dividend rows behave DIFFERENTLY from ordinary rows with
                 the same gap? This is the only question that decides anything.
                 If a -3% mechanical gap and a -3% news gap are followed by the
                 same distribution of r1, then the contamination costs nothing
                 and the honest answer is to leave the engine alone.

PRE-REGISTERED BEFORE RUNNING: adopt a change only if ex-dividend rows are
BOTH frequent enough to matter (>1% of rows) AND behave differently at
|t| >= 3 against matched ordinary rows. A mechanism that is real but costless
gets documented, not shipped — this repo has 34 rejections and most of them
were reasonable ideas that measured to nothing.
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


def fetch(ticker: str, rng: str = "2y") -> tuple:
    """(daily bars, {ex_date: amount}) — dividends come from the same payload."""
    a = YahooDirectAdapter(exchange_tz="America/Toronto")
    r = a._chart_events(ticker, "1d", rng) if hasattr(a, "_chart_events") else None
    if r is None:
        import json
        import urllib.request
        h = {"User-Agent": "Mozilla/5.0 (compatible; research/1.0)",
             "Accept": "application/json"}
        u = (f"https://query2.finance.yahoo.com/v8/finance/chart/{ticker}"
             f"?interval=1d&range={rng}&events=div")
        r = json.loads(urllib.request.urlopen(
            urllib.request.Request(u, headers=h), timeout=45).read())["chart"]["result"][0]
    ts = r.get("timestamp") or []
    q = (r.get("indicators", {}).get("quote") or [{}])[0]
    df = pd.DataFrame({"open": q.get("open"), "close": q.get("close")},
                      index=pd.to_datetime(ts, unit="s").date)
    divs = {dt.datetime.utcfromtimestamp(v["date"]).date(): float(v["amount"])
            for v in (r.get("events", {}).get("dividends", {}) or {}).values()}
    return df.dropna(), divs


def rows_for(ticker: str) -> list:
    try:
        df, divs = fetch(ticker)
    except Exception:
        return []
    out, prev = [], None
    for d, r in df.iterrows():
        if prev is not None and prev > 0:
            amt = divs.get(d, 0.0)
            out.append({"t": ticker, "date": str(d),
                        "gap": (r["open"] / prev - 1) * 100,
                        "r1": (r["close"] / r["open"] - 1) * 100,
                        "exdiv": 1 if amt else 0,
                        "div_pct": amt / prev * 100 if amt else 0.0})
        prev = r["close"]
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default="config.yaml")
    a = ap.parse_args(argv)
    uni = load_config(a.config).get("scan", {}).get("universe") or []
    print("=" * 72)
    print("EX-DIVIDEND CONTAMINATION OF THE `gap` FEATURE")
    print("=" * 72)
    print(f"universe: {len(uni)} names, 2 years of daily bars\n")

    rows = []
    with ThreadPoolExecutor(max_workers=10) as ex:
        for r in ex.map(rows_for, uni):
            rows += r
    d = pd.DataFrame(rows)
    if d.empty:
        print("no data")
        return 2

    # 1 FREQUENCY
    n, nx = len(d), int(d["exdiv"].sum())
    print(f"[1] FREQUENCY : {nx} ex-dividend rows of {n:,} ticker-sessions "
          f"({nx/n:.2%})")
    if nx:
        print(f"    dividend size, %% of prior close: median "
              f"{d.loc[d.exdiv == 1, 'div_pct'].median():.2f}%  max "
              f"{d.loc[d.exdiv == 1, 'div_pct'].max():.2f}%")

    # 2 DISTORTION
    ex_gap = d.loc[d.exdiv == 1, "gap"]
    no_gap = d.loc[d.exdiv == 0, "gap"]
    print(f"\n[2] DISTORTION: mean gap on ex-div days {ex_gap.mean():+.3f}% vs "
          f"{no_gap.mean():+.3f}% otherwise")
    print(f"    the dividend alone accounts for a "
          f"{-d.loc[d.exdiv == 1, 'div_pct'].mean():+.3f}% mechanical shift")

    # 3 OUTCOME — matched on gap, which is the only fair comparison
    print(f"\n[3] OUTCOME   : do ex-div rows behave differently at the SAME gap?")
    print(f"    {'gap bucket':<16}{'n(ex)':>7}{'r1(ex)':>9}{'n(norm)':>9}"
          f"{'r1(norm)':>10}{'diff':>9}{'t':>7}")
    edges = [-99, -2, -1, -0.5, 0, 0.5, 1, 99]
    worst_t = 0.0
    for lo, hi in zip(edges[:-1], edges[1:]):
        e = d[(d.exdiv == 1) & (d.gap >= lo) & (d.gap < hi)]["r1"]
        o = d[(d.exdiv == 0) & (d.gap >= lo) & (d.gap < hi)]["r1"]
        if len(e) < 5 or len(o) < 30:
            continue
        se = (e.var() / len(e) + o.var() / len(o)) ** 0.5
        t = (e.mean() - o.mean()) / se if se else 0.0
        worst_t = max(worst_t, abs(t))
        print(f"    [{lo:>5},{hi:>5})  {len(e):>7}{e.mean():>+9.3f}"
              f"{len(o):>9}{o.mean():>+10.3f}{e.mean()-o.mean():>+9.3f}{t:>7.2f}")

    print("\n" + "=" * 72)
    freq_ok, eff_ok = nx / n > 0.01, worst_t >= 3
    print(f"VERDICT: frequency {nx/n:.2%} ({'PASS' if freq_ok else 'below the 1% bar'}) · "
          f"largest |t| {worst_t:.2f} ({'PASS' if eff_ok else 'below the 3.0 bar'})")
    if freq_ok and eff_ok:
        print("-> ADOPT: ex-dividend rows behave differently and are frequent")
        print("   enough to matter. Correct the gap or exclude the row.")
    else:
        print("-> NOT ADOPTED. The mechanism is real — the open genuinely drops")
        print("   by the dividend — but it does not change what follows, so")
        print("   correcting it would be motion, not improvement. Documented in")
        print("   the report as context; the engine is left alone.")
    print("=" * 72)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
