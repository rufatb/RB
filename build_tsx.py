#!/usr/bin/env python3
"""build_tsx.py — daily OHLC for the configured TSX universe, for day-96.

Writes data/tsx_daily.csv in the same schema as data/us_daily.csv so
validate_pairs.py runs on it unchanged.

RULE 9 IS THE WHOLE POINT OF THE ASSERTIONS BELOW. Day-72: Yahoo answers
`interval=1d, range=max` with WEEKLY, MONTHLY or QUARTERLY bars and no error,
so a "3-day event window" was three months on some names and shipped for four
days. This file verifies the granularity it GOT, counts what it rejects, and
refuses to write a panel it cannot vouch for.

Uses /v8/finance/chart, which needs no crumb — the endpoint that kept working
through the 2026-09-09 406 outage.
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import math
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

import yaml
from zoneinfo import ZoneInfo

ET = ZoneInfo("America/New_York")

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "data")
CHART = ("https://query2.finance.yahoo.com/v8/finance/chart/{t}"
         "?interval=1d&period1={p1}&period2={p2}")
UA = {"User-Agent": "Mozilla/5.0", "Accept": "application/json"}

# A daily series' median spacing must be one trading day. Anything above this
# is a weekly/monthly answer wearing a daily label.
MAX_MEDIAN_SPACING_DAYS = 4.0


class GranularityError(ValueError):
    """The bars are not the bars that were asked for. Never downgraded."""


def fetch(ticker: str, start: dt.date, end: dt.date, timeout: float = 30.0):
    url = CHART.format(t=urllib.parse.quote(ticker, safe=""),
                       p1=int(dt.datetime.combine(start, dt.time(), ET).timestamp()),
                       p2=int(dt.datetime.combine(end, dt.time(), ET).timestamp()))
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        payload = json.loads(r.read())
    res = (payload.get("chart") or {}).get("result") or []
    if not res:
        raise ValueError("no chart result")
    r0 = res[0]
    meta = r0.get("meta") or {}
    if meta.get("symbol") != ticker or meta.get("currency") != "CAD":
        raise ValueError(f"unauthenticated symbol/currency for {ticker}")
    if meta.get("dataGranularity") != "1d":
        raise GranularityError("provider did not authenticate daily granularity")
    stamps = r0.get("timestamp") or []
    q = ((r0.get("indicators") or {}).get("quote") or [{}])[0]
    if not stamps:
        raise ValueError("no timestamps")

    days = [dt.datetime.fromtimestamp(s, ET).date() for s in stamps]
    if len(set(days)) != len(days) or days != sorted(days):
        raise ValueError("duplicate or unordered daily sessions")
    if any(not start <= d < end for d in days):
        raise ValueError("bar outside requested session range")
    import pandas_market_calendars as mcal
    schedule = mcal.get_calendar("TSX").schedule(start_date=start, end_date=end)
    closes = {d.date(): r["market_close"].to_pydatetime()
              for d, r in schedule.iterrows()}
    now = dt.datetime.now(dt.timezone.utc)
    if any(d not in closes or closes[d] > now for d in days):
        raise ValueError("non-session or incomplete-session daily bar")
    gaps = sorted((days[i + 1] - days[i]).days for i in range(len(days) - 1))
    median_gap = gaps[len(gaps) // 2] if gaps else 999
    if median_gap > MAX_MEDIAN_SPACING_DAYS:
        raise GranularityError(
            f"median spacing {median_gap}d — asked for daily, got coarser bars")

    rows = []
    for i, d in enumerate(days):
        o, c, v = q.get("open", [])[i], q.get("close", [])[i], q.get("volume", [])[i]
        if (any(x is None or not math.isfinite(float(x)) for x in (o, c, v))
                or float(o) <= 0 or float(c) <= 0 or float(v) < 0):
            raise ValueError(f"invalid OHLC/volume for {ticker} on {d}")
        rows.append({"date": d.isoformat(), "open": float(o), "close": float(c),
                     "volume": float(v)})
    return rows, median_gap


def build(tickers, start, end, out, delay=0.4):
    panel, stats = [], {"ok": 0, "granularity": 0, "error": 0, "rejected_bars": 0}
    for i, t in enumerate(tickers):
        try:
            rows, gap = fetch(t, start, end)
        except GranularityError as exc:
            stats["granularity"] += 1
            print(f"  [{i+1:2d}/{len(tickers)}] {t:9s} GRANULARITY — {exc}")
            continue
        except (urllib.error.URLError, ValueError, KeyError, IndexError) as exc:
            stats["error"] += 1
            print(f"  [{i+1:2d}/{len(tickers)}] {t:9s} ERROR — {type(exc).__name__}: {exc}")
            continue
        prev = None
        kept = 0
        for r in rows:
            if prev is None:
                prev = r["close"]
                continue
            intraday = (r["close"] / r["open"] - 1.0) * 100.0
            overnight = (r["open"] / prev - 1.0) * 100.0
            daily = (r["close"] / prev - 1.0) * 100.0
            panel.append({"t": t, "date": r["date"], "open": r["open"],
                          "close": r["close"], "prev_close": prev,
                          "volume": r["volume"], "overnight": overnight,
                          "intraday": intraday, "daily": daily})
            prev = r["close"]
            kept += 1
        stats["ok"] += 1
        stats["rejected_bars"] += len(rows) - kept - 1
        print(f"  [{i+1:2d}/{len(tickers)}] {t:9s} OK  {kept} sessions "
              f"(median spacing {gap}d)")
        if i + 1 < len(tickers):
            time.sleep(delay)

    if not panel or stats["ok"] != len(tickers):
        raise SystemExit("incomplete TSX universe — preserving any previous panel; "
                         f"{stats['ok']}/{len(tickers)} names passed, "
                         f"{stats['error']} data errors, {stats['granularity']} granularity errors")
    cols = ["t", "date", "open", "close", "prev_close", "volume",
            "overnight", "intraday", "daily"]
    tmp = out + ".tmp"
    with open(tmp, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        w.writerows(panel)
    os.replace(tmp, out)
    print(f"\nwrote {out}: {len(panel)} rows, {stats['ok']} names")
    print(f"  failures — granularity {stats['granularity']}, fetch {stats['error']}, "
          f"bars rejected for missing OHLC {stats['rejected_bars']}")
    return stats


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--config", default=os.path.join(HERE, "config.yaml"))
    ap.add_argument("--out", default=os.path.join(DATA, "tsx_daily.csv"))
    ap.add_argument("--years", type=int, default=10)
    a = ap.parse_args(argv)
    with open(a.config) as f:
        cfg = yaml.safe_load(f)
    tickers = sorted(set(cfg["scan"]["universe"]) | {cfg["ticker"]})
    end = dt.datetime.now(ET).date()
    start = end - dt.timedelta(days=365 * a.years + 10)
    print(f"TSX daily bars, {len(tickers)} names, {start} -> {end}")
    build(tickers, start, end, a.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
