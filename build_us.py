#!/usr/bin/env python3
"""
build_us.py — day-85. The US panel and the earnings feed the repo never had.

Pre-registered in PREREGISTER_day85.md. This module ACQUIRES data; it computes
no outcome.

TWO ARTEFACTS.

  data/us_daily.csv     10y of DAILY bars for a liquid US universe, with the
                        overnight and intraday legs split out per row.
  data/us_earnings.csv  8-K Item 2.02 announcements with acceptance timestamps.

WHY ITEM 2.02 AND NOT A CALENDAR. `earnings.py` has carried this since day-53:
Yahoo returns fiscal quarter-END dates, not announcement dates, so there was no
free point-in-time earnings feed and therefore no way to measure anything about
earnings. SEC 8-K **Item 2.02 — Results of Operations and Financial Condition**
IS the announcement, `filingDate` is the day it became public and
`acceptanceDateTime` is the minute. That separates the three cases that behave
completely differently:

    BEFORE_OPEN   accepted before 09:30 ET      moves today's open
    IN_SESSION    accepted 09:30-16:00 ET       moves the rest of today
    AFTER_CLOSE   accepted after 16:00 ET       moves tomorrow's open

Lumping them is how an event study measures its own look-ahead. The engine's
own window (open -> close) can only be moved by the first two.

GRANULARITY IS ASSERTED, NOT ASSUMED (day-72, rule 9). Yahoo answers a daily
request with weekly, monthly or quarterly bars and returns no error. Every
series is checked and rejects are counted.

SURVIVORSHIP, which cannot be fixed here. The universe is TODAY's listing. Names
that fell and delisted are absent, which inflates loser-side results. Stated in
the pre-registration per-hypothesis because the direction differs by arm.
"""

from __future__ import annotations

import argparse
import io
import json
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor

import numpy as np
import pandas as pd
import requests

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "data")
UA = {"User-Agent": "RB Research rufat.baghirov97@gmail.com"}
YH = {"User-Agent": "Mozilla/5.0"}

SEC_TICKERS = "https://www.sec.gov/files/company_tickers.json"
SEC_SUBS = "https://data.sec.gov/submissions/CIK{cik:010d}.json"
EARNINGS_ITEM = "2.02"

MIN_SESSIONS = 500          # a name needs real history to enter the panel
MAX_DAY_GAP = 6             # day-81: real daily bars top out near a 4-day gap


def sec_tickers(n_top: int = 1200) -> list:
    """Ticker -> CIK for US filers, in SEC's own order (roughly by size)."""
    r = requests.get(SEC_TICKERS, headers=UA, timeout=45)
    r.raise_for_status()
    rows = list(json.loads(r.text).values())
    out, seen = [], set()
    for row in rows:
        t = (row.get("ticker") or "").strip().upper()
        if not t or "-" in t or "." in t or t in seen:
            continue
        seen.add(t)
        out.append({"ticker": t, "cik": int(row["cik_str"]),
                    "name": row.get("title", "")})
        if len(out) >= n_top:
            break
    return out


# ── daily bars ─────────────────────────────────────────────────────────────

def fetch_daily(ticker: str, years: int = 10, tries: int = 3):
    now = int(time.time())
    for host in ("query1", "query2"):
        for attempt in range(tries):
            try:
                r = requests.get(
                    f"https://{host}.finance.yahoo.com/v8/finance/chart/{ticker}",
                    params={"interval": "1d", "period1": now - years * 366 * 86400,
                            "period2": now}, headers=YH, timeout=45)
                res = (r.json().get("chart") or {}).get("result")
                if res:
                    return res[0]
            except Exception:
                time.sleep(1.0 * (attempt + 1))
    return None


def is_daily(idx) -> bool:
    """Rule 9: verify the granularity you GOT. Weekly bars answer a daily ask."""
    if len(idx) < 50:
        return False
    d = np.diff(idx.values).astype("timedelta64[D]").astype(int)
    return float(np.median(d)) <= MAX_DAY_GAP


def daily_rows(ticker: str, res: dict) -> list:
    q = (res.get("indicators", {}).get("quote") or [{}])[0]
    ts = res.get("timestamp") or []
    if not ts:
        return []
    idx = pd.to_datetime(ts, unit="s", utc=True).tz_convert("America/New_York")
    df = pd.DataFrame({"o": q.get("open"), "h": q.get("high"), "l": q.get("low"),
                       "c": q.get("close"), "v": q.get("volume")}, index=idx)
    df = df.dropna(subset=["o", "c"])
    if len(df) < MIN_SESSIONS or not is_daily(df.index):
        return []
    pc = df["c"].shift(1)
    out = pd.DataFrame({
        "t": ticker,
        "date": [str(d.date()) for d in df.index],
        "open": df["o"].to_numpy(), "close": df["c"].to_numpy(),
        "prev_close": pc.to_numpy(), "volume": df["v"].to_numpy(),
        # the two legs, kept separate from the start (H1)
        "overnight": (df["o"] / pc - 1).to_numpy() * 100,
        "intraday": (df["c"] / df["o"] - 1).to_numpy() * 100,
        "daily": (df["c"] / pc - 1).to_numpy() * 100,
    }).dropna(subset=["overnight"])
    return out.to_dict("records")


def build_prices(tickers: list, workers: int = 12) -> tuple:
    rows, bad = [], {"fetch": 0, "granularity_or_short": 0}
    def one(t):
        res = fetch_daily(t)
        if res is None:
            return t, None
        return t, daily_rows(t, res)
    with ThreadPoolExecutor(max_workers=workers) as ex:
        for i, (t, got) in enumerate(ex.map(one, tickers), 1):
            if got is None:
                bad["fetch"] += 1
            elif not got:
                bad["granularity_or_short"] += 1
            else:
                rows += got
            if i % 100 == 0:
                print(f"    {i}/{len(tickers)} … {len(rows):,} rows", flush=True)
    return pd.DataFrame(rows), bad


# ── the earnings feed ──────────────────────────────────────────────────────

def classify_time(acceptance: str) -> str:
    """BEFORE_OPEN / IN_SESSION / AFTER_CLOSE. Never lumped (see the header)."""
    try:
        ts = pd.Timestamp(acceptance)
    except Exception:
        return "UNKNOWN"
    if ts.tzinfo is None:                 # SEC stamps these in ET
        ts = ts.tz_localize("America/New_York")
    else:
        ts = ts.tz_convert("America/New_York")
    hm = ts.hour * 60 + ts.minute
    if hm < 9 * 60 + 30:
        return "BEFORE_OPEN"
    if hm < 16 * 60:
        return "IN_SESSION"
    return "AFTER_CLOSE"


def earnings_for(ticker: str, cik: int, tries: int = 3) -> list:
    for attempt in range(tries):
        try:
            r = requests.get(SEC_SUBS.format(cik=cik), headers=UA, timeout=45)
            r.raise_for_status()
            rec = r.json().get("filings", {}).get("recent", {})
            out = []
            for form, items, fdate, acc in zip(
                    rec.get("form", []), rec.get("items", []),
                    rec.get("filingDate", []), rec.get("acceptanceDateTime", [])):
                if form != "8-K" or EARNINGS_ITEM not in (items or ""):
                    continue
                out.append({"t": ticker, "cik": cik, "date": fdate,
                            "acceptance": acc, "when": classify_time(acc)})
            return out
        except Exception:
            time.sleep(1.0 * (attempt + 1))
    raise RuntimeError(f"{ticker}: submissions fetch failed")


def build_earnings(universe: list, workers: int = 6) -> tuple:
    rows, failed = [], []
    def one(u):
        try:
            return earnings_for(u["ticker"], u["cik"])
        except Exception as e:            # noqa: BLE001 — counted, never hidden
            return e
    with ThreadPoolExecutor(max_workers=workers) as ex:
        for i, got in enumerate(ex.map(one, universe), 1):
            if isinstance(got, Exception):
                failed.append(str(got))
            else:
                rows += got
            if i % 100 == 0:
                print(f"    {i}/{len(universe)} … {len(rows):,} announcements",
                      flush=True)
    return pd.DataFrame(rows), failed


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--names", type=int, default=600)
    ap.add_argument("--years", type=int, default=10)
    a = ap.parse_args(argv)
    os.makedirs(DATA, exist_ok=True)

    print(f"universe: SEC company_tickers, first {a.names} usable US filers")
    uni = sec_tickers(a.names)
    print(f"  {len(uni)} names")

    print(f"\ndaily bars ({a.years}y, granularity asserted per name)")
    px, bad = build_prices([u["ticker"] for u in uni])
    if px.empty:
        print("  NO PRICE DATA — refusing to write an empty panel.")
        return 2
    kept = sorted(px["t"].unique())
    print(f"  {len(px):,} ticker-days across {len(kept)} names, "
          f"{px['date'].min()} .. {px['date'].max()}")
    print(f"  dropped {bad['fetch']} on fetch, {bad['granularity_or_short']} "
          f"for short history or non-daily bars (rule 9)")
    px.to_csv(os.path.join(DATA, "us_daily.csv"), index=False)

    print(f"\nearnings: 8-K Item {EARNINGS_ITEM}, timestamped")
    uni_kept = [u for u in uni if u["ticker"] in set(kept)]
    ern, failed = build_earnings(uni_kept)
    if ern.empty:
        print("  NO EARNINGS fetched — the event arms cannot run.")
    else:
        ern = ern.sort_values(["t", "date"]).reset_index(drop=True)
        ern.to_csv(os.path.join(DATA, "us_earnings.csv"), index=False)
        by = ern["when"].value_counts().to_dict()
        print(f"  {len(ern):,} announcements across {ern['t'].nunique()} names, "
              f"{ern['date'].min()} .. {ern['date'].max()}")
        print(f"  timing: " + ", ".join(f"{k} {v:,}" for k, v in sorted(by.items())))
    if failed:
        print(f"  ⚠ {len(failed)} names failed and are ABSENT, not empty")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
