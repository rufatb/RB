#!/usr/bin/env python3
"""
validate_catalyst.py — what FDA decisions actually do to a share price, and
whether anything knowable BEFORE the date predicts which one lands.

Runs on the survivorship-free event set from `build_catalyst.py` (SEC EDGAR
full-text search over 2004-2026, biotech SIC only, delisted issuers included
because EDGAR never forgets them).

FOUR QUESTIONS, in the order that can kill the strategy cheapest.

  1  COVERAGE. What fraction of events reach a usable price series? The events
     are survivorship-free; the PRICES may not be, because a company that died
     in 2009 may have no Yahoo history. If dead names drop out here the bias
     walks straight back in at the last step, so this is reported FIRST and
     loudly, and every later number is read in its light.

  2  THE REAL CRL DRAWDOWN. Catalyst theses routinely assume a "cash floor"
     downside — the thesis that prompted this work assumed -18% because the
     company held $322.5M. Cash is not a floor; post-CRL biotechs trade below
     it regularly. This measures the actual distribution instead, and every
     breakeven probability in `catalyst.py` moves with it.

  3  THE CEILING TEST. Does anything observable before the announcement —
     pre-event drift, realised volatility, market cap, the run-up itself —
     separate approvals from CRLs? If not, then no thesis built on public
     price information can beat the market's own probability, and the strategy
     reduces to paying the spread to hold a coin. Same question day-43 asked of
     the intraday engine, and with the same positive control, because a null is
     only trustworthy from a harness that can detect a planted edge.

  4  IS THE RUN-UP ALREADY ARBITRAGED? Much documented biotech catalyst return
     is a pre-event drift that is well known and traded. Measured separately so
     it cannot be mistaken for event skill.

WHAT THIS CANNOT DO. It sees only announcements that HAPPENED. A PDUFA date
that slipped, or an approval nobody 8-K'd, is invisible. It also cannot tell
you a specific drug's approval probability — that is the whole trade and it is
a research question about the molecule, not a calculation.
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import os
import sys
from concurrent.futures import ThreadPoolExecutor

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from adapters import YahooDirectAdapter  # noqa: E402
from validate_ceiling import auc, se_auc  # noqa: E402
from validate_exit import SCRATCH  # noqa: E402


def load_events(path: str, collapse_days: int = 45) -> pd.DataFrame:
    """Events, with retrospective mentions collapsed into their announcement.

    THE DEFECT THIS FIXES, found by inspecting outliers rather than trusting the
    aggregate. A full-text search returns every 8-K that MENTIONS a complete
    response letter, not only the one that ANNOUNCES it. Companies keep
    referring to a CRL for months — in guidance updates, resubmission news,
    financing documents — so the same rejection entered the sample repeatedly,
    at dates when the stock had already recovered. The tell was identical
    returns on duplicated tickers:

        AXSM 2022-06-02  +155.2%   AXSM 2022-06-28  +155.2%
        ALDX 2025-06-17  +171.6%   ALDX 2025-06-26  +171.6%
        AIM  2012-07-11  +185.7%   AIM  2012-08-01  +185.7%

    Axsome's actual CRL was in April 2022; the June filings discuss it after the
    recovery. Uncollapsed, this produced the impossible headline that CRLs had a
    HIGHER median reaction than approvals.

    The first mention within a window is the announcement and later ones are
    discussion, so events for one filer and one kind inside `collapse_days` are
    folded into the earliest. Cheap, and it removes both the double counting and
    the retrospective dates in a single pass.
    """
    with open(path) as f:
        df = pd.DataFrame(list(csv.DictReader(f)))
    df["date"] = pd.to_datetime(df["date"])
    df = df.sort_values(["cik", "kind", "date"])
    keep, last = [], {}
    for i, r in df.iterrows():
        k = (r["cik"], r["kind"])
        prev = last.get(k)
        if prev is None or (r["date"] - prev).days > collapse_days:
            keep.append(i)
            last[k] = r["date"]
    out = df.loc[keep].reset_index(drop=True)
    print(f"  collapsed {len(df):,} mentions -> {len(out):,} distinct events "
          f"({collapse_days}d window per filer)")
    return out


def fetch_prices(tickers: list, workers: int = 12) -> dict:
    """Daily closes per ticker. Delisted names often 404 — counted, not hidden."""
    a = YahooDirectAdapter(exchange_tz="America/New_York")
    out, fail = {}, {}

    def one(t):
        try:
            b = a.get_daily_bars(t, 8000)
            return t, b[["Close"]] if len(b) else None
        except Exception as e:
            return t, type(e).__name__

    with ThreadPoolExecutor(max_workers=workers) as ex:
        for n, (t, r) in enumerate(ex.map(one, tickers), 1):
            if isinstance(r, pd.DataFrame):
                out[t] = r
            else:
                fail[t] = r or "empty"
            if n % 200 == 0:
                print(f"    {n}/{len(tickers)} fetched, {len(out)} usable",
                      flush=True)
    print(f"  price series: {len(out)}/{len(tickers)} tickers usable "
          f"({len(out)/max(len(tickers),1):.0%})")
    return out


def window_returns(px: pd.DataFrame, when: dt.datetime) -> dict | None:
    """Returns around an announcement.

    The 8-K date is the FILING date; a company announcing after the close files
    the next morning, so the reaction can land on t-1 or t. `event` therefore
    spans close(t-2) -> close(t+1), which captures either convention without
    peeking further ahead than a trader could have acted.
    """
    s = px["Close"].dropna()
    if s.empty:
        return None
    idx = s.index
    try:
        i = idx.searchsorted(pd.Timestamp(when).tz_localize(idx.tz)
                             if idx.tz is not None else pd.Timestamp(when))
    except Exception:
        return None
    if i < 25 or i + 2 >= len(s):
        return None
    p = s.to_numpy(dtype=float)
    pre20 = (p[i - 2] / p[i - 22] - 1) * 100        # run-up, ends before the event
    vol20 = float(np.std(np.diff(p[i - 22:i - 1]) / p[i - 22:i - 2]) * 100)
    event = (p[min(i + 1, len(p) - 1)] / p[i - 2] - 1) * 100
    after5 = (p[min(i + 6, len(p) - 1)] / p[min(i + 1, len(p) - 1)] - 1) * 100
    return {"pre20": pre20, "vol20": vol20, "event": event, "after5": after5,
            "px": float(p[i - 2])}


def pct(a: np.ndarray, q: float) -> float:
    return float(np.percentile(a, q)) if len(a) else float("nan")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--events", default=os.path.join(SCRATCH, "catalyst_events.csv"))
    ap.add_argument("--max-tickers", type=int, default=0)
    a = ap.parse_args(argv)

    ev = load_events(a.events)
    print("=" * 76)
    print("FDA CATALYST STUDY — survivorship-free events from SEC EDGAR")
    print("=" * 76)
    n_all = len(ev)
    have_t = ev[ev["ticker"].astype(bool)]
    print(f"events harvested        : {n_all:,} "
          f"({(ev['kind']=='CRL').sum():,} CRL / "
          f"{(ev['kind']=='APPROVAL').sum():,} approval)")
    print(f"with a resolved ticker  : {len(have_t):,} ({len(have_t)/n_all:.0%})")

    tickers = sorted(have_t["ticker"].unique())
    if a.max_tickers:
        tickers = tickers[:a.max_tickers]
    print(f"unique tickers          : {len(tickers):,}\n  fetching prices...")
    px = fetch_prices(tickers)

    rows = []
    for _, r in have_t.iterrows():
        p = px.get(r["ticker"])
        if p is None:
            continue
        w = window_returns(p, r["date"])
        if w is None:
            continue
        w.update({"kind": r["kind"], "ticker": r["ticker"],
                  "date": r["date"], "name": r["name"]})
        rows.append(w)
    d = pd.DataFrame(rows)
    print(f"\n[1] COVERAGE: {len(d):,}/{n_all:,} harvested events reach a usable "
          f"price window ({len(d)/n_all:.0%})")
    if len(d) < 200:
        print("    too few to analyse — stopping rather than reporting noise")
        return 2
    crl = d[d["kind"] == "CRL"]["event"].to_numpy()
    app = d[d["kind"] == "APPROVAL"]["event"].to_numpy()

    print(f"\n[2] EVENT-WINDOW REACTION  (close t-2 -> close t+1)")
    print(f"    {'':<10}{'n':>6}{'mean':>9}{'median':>9}{'p10':>9}{'p25':>9}"
          f"{'p75':>9}{'p90':>9}{'worst':>9}")
    for lab, arr in (("CRL", crl), ("APPROVAL", app)):
        print(f"    {lab:<10}{len(arr):>6}{arr.mean():>+9.2f}{pct(arr,50):>+9.2f}"
              f"{pct(arr,10):>+9.2f}{pct(arr,25):>+9.2f}{pct(arr,75):>+9.2f}"
              f"{pct(arr,90):>+9.2f}{arr.min():>+9.2f}")
    print(f"\n    share of CRLs worse than -18% (the 'cash floor' assumption): "
          f"{(crl < -18).mean():.0%}")
    print(f"    share of CRLs worse than -40%                              : "
          f"{(crl < -40).mean():.0%}")

    print(f"\n[3] CEILING TEST — does pre-event information predict the outcome?")
    d["y"] = (d["kind"] == "APPROVAL").astype(int)
    feats = ["pre20", "vol20", "px"]
    print(f"    base rate P(approval in this sample) = {d['y'].mean():.3f}")
    print(f"    {'feature':<10}{'AUC':>9}{'z':>8}")
    for f in feats:
        s = d[[f, "y"]].dropna()
        A = auc(s["y"].to_numpy(), s[f].to_numpy())
        print(f"    {f:<10}{A:>9.4f}{(A-0.5)/se_auc(s['y'].to_numpy()):>8.2f}")
    rng = np.random.default_rng(0)
    ctrl = rng.normal(size=len(d)) + (2 * d["y"].to_numpy() - 1) * 0.05
    A = auc(d["y"].to_numpy(), ctrl)
    print(f"    {'[control]':<10}{A:>9.4f}{(A-0.5)/se_auc(d['y'].to_numpy()):>8.2f}"
          f"   <- planted edge; if this is small the sample is too thin to trust")

    print(f"\n[4] IS THE RUN-UP ALREADY PRICED?")
    for lab, sub in (("CRL", d[d["kind"] == "CRL"]),
                     ("APPROVAL", d[d["kind"] == "APPROVAL"])):
        print(f"    {lab:<10} pre-event 20d drift {sub['pre20'].mean():+7.2f}%   "
              f"post-event 5d drift {sub['after5'].mean():+7.2f}%")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
