#!/usr/bin/env python3
"""
earnings.py — the event risk the 9:45 engine is structurally blind to.

`r945.py`'s own header has always said the tool has "NO earnings/dividend/news
feed to price it". The dividend half of that gap was measured and dismissed
(day-65: real mechanism, -1.000% mechanical shift in `gap`, but ex-dividend rows
behave no differently at the same gap, largest |t| = 1.55 against a 3.0 bar —
rejection #35). Earnings are the other half, and they are a different animal: a
dividend pays a known amount on a known date, while a report is genuine
information arriving inside the holding period.

WHAT THIS IS, AND WHAT IT IS EXPLICITLY NOT.

It is a WARNING, not a gate. Yahoo serves the NEXT earnings date free, but its
`earningsHistory` returns fiscal QUARTER-END dates rather than announcement
dates — RY's Q3 ends 31 July and it reports four weeks later — so for TSX names
there is still no free source of historical announcement dates.

DAY-88 MEASURED THE GATE ON US DATA AND CLOSED THE QUESTION. That measurement
was impossible when this module was written; SEC 8-K Item 2.02 supplied it —
60,922 announcements timestamped to the minute, against 50,779 qualified legs
over 490 sessions (PREREGISTER_day88.md, validate_earnfilter.py).

The result vindicates warning rather than blocking, and does so by arithmetic
rather than by a null:

    in-window legs are 0.78% of all legs
    their penalty, at the point estimate the statistics do NOT support,
      is -0.138%/leg against clean legs
    removing them moves the book average by +0.108 BPS PER LEG
    one round-trip spread on the live book is ~8 bps

So the whole gate, granted its most flattering reading, is worth 1.3% of a
single spread crossing. The penalty itself is UNDERPOWERED (|t|=1.59, blocks
flip sign) and would need 3.6x the panel to resolve — but resolving it would
not make the gate worth having, because the frequency argument is independent
of the effect size. An exact placebo confirms the harness: excluding
announcements that land AFTER the leg is flat moves nothing (|t|=0.23).

The warning stays for the reason it was written. A name reporting inside the
window hands you the same coin flip with a bigger stake on it, and the reader
is entitled to know that before sizing. What is settled is that BLOCKING on it
buys nothing measurable.

The argument for printing it anyway is the extrapolation guard's argument, not
a prediction one: a name reporting after today's close has a return
distribution the 60-day pool does not represent, and the reader is entitled to
know that before entering. Whether to act on it is the reader's call — which is
why it warns and never blocks.

THE ASYMMETRY WORTH KNOWING. A report landing AFTER today's close cannot move
the 9:45->close leg at all, because the leg is flat by 3:55. It matters only if
the position is held overnight, which this strategy never does. A report landing
BEFORE the open, or during the session, is inside the window and is the case
that actually bites. Both are labelled distinctly rather than lumped into one
scary flag.
"""

from __future__ import annotations

import argparse
import datetime as dt
import http.cookiejar
import json
import os
import sys
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120 Safari/537.36")
H = {"User-Agent": UA, "Accept": "application/json,text/plain,*/*"}


class _Yahoo:
    def __init__(self):
        self.op = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
        self.crumb = None

    def _get(self, u: str) -> bytes:
        return self.op.open(urllib.request.Request(u, headers=H), timeout=40).read()

    def auth(self):
        if self.crumb:
            return
        try:
            self._get("https://fc.yahoo.com")
        except Exception:
            pass
        self.crumb = self._get(
            "https://query2.finance.yahoo.com/v1/test/getcrumb").decode()

    def next_earnings(self, ticker: str) -> list:
        self.auth()
        u = (f"https://query2.finance.yahoo.com/v10/finance/quoteSummary/{ticker}"
             f"?modules=calendarEvents&crumb={self.crumb}")
        r = json.loads(self._get(u))["quoteSummary"]["result"][0]
        raw = r.get("calendarEvents", {}).get("earnings", {}).get("earningsDate", [])
        out = []
        for x in raw:
            v = x.get("raw") if isinstance(x, dict) else None
            if v:
                out.append(dt.datetime.utcfromtimestamp(v).date().isoformat())
        return sorted(set(out))


def classify(ev_date: str, today: dt.date) -> tuple:
    """(days_away, label). Pure + testable.

    The distinction that matters: a report AFTER today's close cannot touch a
    leg that is flat by 3:55. Only a report inside today's session, or one that
    already landed before the open, is in the window.
    """
    d = (dt.date.fromisoformat(ev_date) - today).days
    if d == 0:
        return d, "TODAY — inside the session window"
    if d < 0:
        return d, f"reported {abs(d)}d ago — the pool may not represent this yet"
    if d == 1:
        return d, "TOMORROW — not in today's window, but positioning may be"
    return d, f"in {d}d"


def gather(tickers: list, sleep: float = 0.1) -> dict:
    y, out = _Yahoo(), {}
    for t in tickers:
        try:
            out[t] = {"dates": y.next_earnings(t), "error": None}
        except Exception as e:
            out[t] = {"dates": [], "error": type(e).__name__}
    return out


def render(cal: dict, today: dt.date, picks: set | None = None,
           horizon: int = 7) -> str:
    """Report block. Names in `picks` are surfaced even outside the horizon."""
    picks = picks or set()
    L, unavailable = [], []
    for t in sorted(cal):
        v = cal[t]
        if v["error"]:
            unavailable.append(f"{t} ({v['error']})")
            continue
        for ed in v["dates"]:
            d, label = classify(ed, today)
            if not (-3 <= d <= horizon):
                continue
            if t not in picks and abs(d) > 2:
                continue                       # only crowd the page for picks
            mark = "⚠ " if (t in picks and -1 <= d <= 1) else "  "
            L.append(f"   {mark}{t:<9} {ed}  {label}")
    if not L and not unavailable:
        return ""
    out = ["▎EARNINGS NEARBY — event risk the 9:45 model cannot see"]
    out += L or ["   none within the window for today's picks"]
    if unavailable:
        out.append(f"   ⚠ could not check: {', '.join(unavailable)} — "
                   "unknown, not clear")
    out.append("   ── a WARNING, not a gate, and NOT backtested: no free source")
    out.append("      gives historical TSX announcement dates, so the cost of")
    out.append("      trading through one has never been measured here.")
    return "\n".join(out)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default="config.yaml")
    ap.add_argument("--horizon", type=int, default=7)
    a = ap.parse_args(argv)
    from dashboard import load_config
    uni = load_config(a.config).get("scan", {}).get("universe") or []
    today = dt.date.today()
    cal = gather(uni)
    print(render(cal, today, picks=set(uni), horizon=a.horizon)
          or "no earnings within the window")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
