#!/usr/bin/env python3
"""
ledger.py — the permanent learning record ("learn every single day").

Every pick the 9:45 engine publishes is APPENDED at publish time (date,
ticker, side, sided P, confidence tag, 9:45 price); after the close,
`python ledger.py --score` fills each row's outcome and prints the CUMULATIVE
report — overall hit rate, longs vs shorts, and the hit rate BY CONFIDENCE
TAG (the pre-registered density hypothesis: dense > mid/sparse, to be judged
on ~20 live days before it may become a gate).

WHY a file and not memory: learning must be auditable and survive sessions.
Rows are written before outcomes are knowable (no hindsight), never edited
except to fill outcomes, and committed to the repo as the track record.
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import os

LEDGER = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ledger.csv")
# `role` (day-9): "pair" = a leg of THE PAIR (the picks actually executed under
# the one-long-one-short workflow), "board" = qualified-but-not-traded context
# kept for instrumentation. Pre-day-9 rows have role "" (whole-board era).
# `weight` (day-23): the leg's share of the BOOK CAPACITY at publish time.
# WHY: since day-22 the two pair legs are sized by equal-RISK, not equal
# dollars, so the equal-weighted "avg move captured" no longer equals what the
# book earned — day-23 closed at -0.156% equal-weighted while the book made
# +$94, because the calm winning leg held 65% of the money. Without this column
# the ledger silently misreports the executed record from day-22 onward. Blank
# on every pre-day-23 row and on board rows: the weights were computed at
# publish time but not persisted, and rows are never back-edited (day-18).
FIELDS = ["date", "ticker", "side", "p_sided", "confidence", "p945", "role",
          "weight", "r1", "hit"]


def load(path: str = LEDGER) -> list:
    if not os.path.exists(path):
        return []
    with open(path) as f:
        return list(csv.DictReader(f))


def save(rows: list, path: str = LEDGER) -> None:
    # restval="" so rows written before a column existed survive untouched
    # rather than raising — the ledger is append-and-fill, never rewritten.
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS, restval="")
        w.writeheader()
        w.writerows(rows)


def append_picks(picks: list, date: str, path: str = LEDGER) -> int:
    """Append publish-time rows; (date,ticker) is unique — re-runs don't dupe."""
    rows = load(path)
    seen = {(r["date"], r["ticker"]) for r in rows}
    added = 0
    for p in picks:
        key = (date, p["ticker"])
        if key in seen:
            continue
        w = p.get("weight")
        rows.append({"date": date, "ticker": p["ticker"], "side": p["side"],
                     "p_sided": f"{p['p_sided']:.3f}", "confidence": p.get("confidence", "n/a"),
                     "p945": f"{p['p945']:.4f}", "role": p.get("role", "board"),
                     "weight": f"{w:.4f}" if w is not None else "",
                     "r1": "", "hit": ""})
        added += 1
    save(rows, path)
    return added


def session_is_final(date_str: str, now: dt.datetime, close_time: dt.time) -> bool:
    """Has that session's regular close already happened? Pure + testable."""
    d = dt.date.fromisoformat(date_str)
    if d != now.date():
        return d < now.date()
    return now.time() >= close_time


def score_rows(rows: list, close_fn, now: dt.datetime | None = None,
               close_time: dt.time = dt.time(16, 0)) -> tuple:
    """Fill outcomes for unscored rows using close_fn(ticker, date)->close.

    TWO separate day-24 bugs are guarded here; both wrote wrong numbers into
    the permanent record with no complaint, and the ledger is the arbiter of
    every claim this repo makes:

    1. SCORING AN OPEN SESSION. `--score` at 15:05 stamped LIVE mid-session
       prices as outcomes (ENB read -1.136% with 55 minutes left to trade).
       Guarded by `session_is_final` — rows stay blank and are retried later.
    2. SCORING THE WRONG DAY'S PRICE. `close_fn` took only a ticker and
       returned the LATEST quote, so scoring yesterday's rows the next morning
       recorded TODAY's live price as yesterday's close — BCE.TO went in at
       +0.049% when its actual 2026-07-29 close was +1.618%. Guarded by making
       the date part of the lookup contract: close_fn MUST be given the row's
       own date and must return that session's close or None.

    Lesson class (day-24): every guard in this repo protected ENTRY. Nothing
    protected MEASUREMENT, and a system that grades its own homework needs the
    grader checked hardest. Pure-ish + testable."""
    now = now or dt.datetime.now()
    scored, held = 0, 0
    for r in rows:
        if r["r1"] != "":
            continue
        if not session_is_final(r["date"], now, close_time):
            held += 1
            continue
        c = close_fn(r["ticker"], r["date"])
        if c is None:
            continue
        r1 = (c / float(r["p945"]) - 1) * 100
        win = (r1 > 0) if r["side"] == "LONG" else (r1 < 0)
        r["r1"] = f"{r1:.3f}"
        r["hit"] = "1" if win else "0"
        scored += 1
    return rows, scored, held


def live_summary(rows: list, last_n: int = 20) -> dict | None:
    """Compact live-record numbers for the morning report header (day-13:
    'so far it's not working' must be visible IN the tool, every day, not
    discovered later). Pure; None when nothing is scored yet."""
    done = [r for r in rows if r["hit"] != ""]
    if not done:
        return None
    pair = [r for r in done if r.get("role") == "pair"]
    recent = done[-last_n:]
    return {"all_n": len(done), "all_hits": sum(int(r["hit"]) for r in done),
            "pair_n": len(pair), "pair_hits": sum(int(r["hit"]) for r in pair),
            "recent_n": len(recent), "recent_hits": sum(int(r["hit"]) for r in recent)}


def book_return_line(pair_rows: list) -> str:
    """What the BOOK actually earned, per session, on allocated capacity.

    Day-23: `avg move captured` averages the two legs EQUALLY, which stopped
    matching reality on day-22 when equal-RISK sizing made the legs different
    sizes. On day-23 the equal-weighted number was -0.156% while the book made
    +$94, because the calm winning leg carried 65% of the money. This line is
    the honest one for judging the executed strategy; the equal-weighted line
    above stays as the clean measure of the DIRECTION calls. Pure + testable."""
    weighted = [r for r in pair_rows if r.get("weight") not in (None, "")]
    if not weighted:
        return ("  book-weighted return : (recording starts day-23 — earlier "
                "rows predate the weight column)")
    by_day: dict = {}
    for r in weighted:
        capt = float(r["r1"]) * (1 if r["side"] == "LONG" else -1)
        by_day.setdefault(r["date"], []).append(float(r["weight"]) * capt)
    daily = [sum(v) for v in by_day.values()]
    wins = sum(1 for d in daily if d > 0)
    return (f"  book-weighted return : {sum(daily)/len(daily):+.3f}%/session on "
            f"capacity over {len(daily)} sessions  ({wins}/{len(daily)} positive)")


def report(rows: list) -> str:
    done = [r for r in rows if r["hit"] != ""]
    if not done:
        return "ledger: no scored rows yet"
    out = ["=" * 60, f"LEDGER REPORT — {len(done)} scored picks (live, no hindsight)", "=" * 60]

    def line(label, sub):
        if not sub:
            return f"  {label:<18} n=0"
        hits = sum(int(r["hit"]) for r in sub)
        mv = sum(float(r["r1"]) * (1 if r["side"] == "LONG" else -1) for r in sub) / len(sub)
        return (f"  {label:<18} n={len(sub):<4} hit {hits}/{len(sub)} "
                f"({hits/len(sub)*100:.0f}%)  avg move captured {mv:+.2f}%")

    out.append(line("ALL", done))
    out.append(line("longs", [r for r in done if r["side"] == "LONG"]))
    out.append(line("shorts", [r for r in done if r["side"] == "SHORT"]))
    pair_sub = [r for r in done if r.get("role") == "pair"]
    if pair_sub:
        out.append("  — THE PAIR (densest leg per side — the executed record) —")
        out.append(line("PAIR legs", pair_sub))
        out.append(line("board (untraded)", [r for r in done if r.get("role") == "board"]))
        out.append(book_return_line(pair_sub))
    out.append("  — density hypothesis (pre-registered: dense > mid/sparse) —")
    for tag in ("dense", "mid", "sparse", "n/a"):
        sub = [r for r in done if r["confidence"] == tag]
        if sub:
            out.append(line(f"[{tag}]", sub))
    n_tagged = len([r for r in done if r["confidence"] in ("dense", "mid", "sparse")])
    out.append(f"  (gate decision at ~20 tagged days; tagged so far: {n_tagged})")
    return "\n".join(out)


def main(argv=None):
    p = argparse.ArgumentParser(description="Score the pick ledger and print cumulative learning")
    p.add_argument("--score", action="store_true")
    args = p.parse_args(argv)
    rows = load()
    if args.score:
        from zoneinfo import ZoneInfo

        from adapters import YahooDirectAdapter
        from dashboard import load_config, parse_hhmm
        cfg = load_config(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                       "config.yaml"))
        tz = cfg.get("exchange_tz", "America/Toronto")
        close_t = parse_hhmm(cfg.get("market_close", "16:00"))
        a = YahooDirectAdapter(exchange_tz=tz)
        # DATE-SPECIFIC closes from daily bars, cached per ticker. Never
        # get_quote().last — that is the LATEST price and silently scores the
        # wrong session whenever --score runs on a later day (day-24 bug #2).
        _cache: dict = {}
        def close_fn(t, date):
            if t not in _cache:
                try:
                    bars = a.get_daily_bars(t, 90)
                    _cache[t] = {str(i.date()): float(c)
                                 for i, c in bars["Close"].items()}
                except Exception:
                    _cache[t] = {}
            return _cache[t].get(date)
        rows, n, held = score_rows(rows, close_fn,
                                   now=dt.datetime.now(ZoneInfo(tz)),
                                   close_time=close_t)
        save(rows)
        print(f"scored {n} new rows")
        if held:
            print(f"  ⏳ {held} rows HELD BACK — their session has not closed "
                  f"({close_t.strftime('%H:%M')} {tz}). Scoring mid-session would "
                  "write live\n     prices into the permanent record as outcomes. "
                  "Re-run after the close.")
    print(report(rows))


if __name__ == "__main__":
    main()
