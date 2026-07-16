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
import os

LEDGER = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ledger.csv")
# `role` (day-9): "pair" = a leg of THE PAIR (the picks actually executed under
# the one-long-one-short workflow), "board" = qualified-but-not-traded context
# kept for instrumentation. Pre-day-9 rows have role "" (whole-board era).
FIELDS = ["date", "ticker", "side", "p_sided", "confidence", "p945", "role", "r1", "hit"]


def load(path: str = LEDGER) -> list:
    if not os.path.exists(path):
        return []
    with open(path) as f:
        return list(csv.DictReader(f))


def save(rows: list, path: str = LEDGER) -> None:
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
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
        rows.append({"date": date, "ticker": p["ticker"], "side": p["side"],
                     "p_sided": f"{p['p_sided']:.3f}", "confidence": p.get("confidence", "n/a"),
                     "p945": f"{p['p945']:.4f}", "role": p.get("role", "board"),
                     "r1": "", "hit": ""})
        added += 1
    save(rows, path)
    return added


def score_rows(rows: list, close_fn) -> tuple:
    """Fill outcomes for unscored rows using close_fn(ticker)->close. Pure-ish."""
    scored = 0
    for r in rows:
        if r["r1"] != "":
            continue
        c = close_fn(r["ticker"])
        if c is None:
            continue
        r1 = (c / float(r["p945"]) - 1) * 100
        win = (r1 > 0) if r["side"] == "LONG" else (r1 < 0)
        r["r1"] = f"{r1:.3f}"
        r["hit"] = "1" if win else "0"
        scored += 1
    return rows, scored


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
        from adapters import YahooDirectAdapter
        a = YahooDirectAdapter()
        def close_fn(t):
            try:
                q = a.get_quote(t)
                return q.last
            except Exception:
                return None
        rows, n = score_rows(rows, close_fn)
        save(rows)
        print(f"scored {n} new rows")
    print(report(rows))


if __name__ == "__main__":
    main()
