#!/usr/bin/env python3
"""
catledger.py — the scored record for catalyst trades. The thing that was missing.

WHY THIS IS THE MOST IMPORTANT FILE IN THE CATALYST STACK. Everything else
built for catalysts — the calendar, the opportunity screen, the implied-move
read, the balance-sheet check — is APPARATUS. None of it has been scored
against an outcome even once. The intraday engine's whole credibility comes
from the opposite: 356 legs recorded before the answer was knowable, which is
the only reason it can say "no edge" as a measurement rather than a mood.

Building screens for a strategy with no track record is the exact error the
9:45 engine avoided from its first day, and it is easy to make because the
apparatus FEELS like progress. In six months without this file there would be
opinions about whether catalyst trading works, and nothing else.

WHAT IS RECORDED, AND WHEN. At the moment a catalyst is IDENTIFIED — not when
it is traded — the tool writes down what was knowable then:

    the event and its date, the price, the market-implied move, the skew,
    the cash per share, the runway, the AdCom vote if one has happened,
    and the STANCE the screen assigned.

After the event it records what happened. Nothing is ever back-edited except
the outcome fields, exactly as `ledger.py` works, because a record that can be
revised after the fact is not a record.

THE POINT IS THE COUNTERFACTUAL. Recording only the trades taken would measure
the trader, not the screen. Every catalyst the screen surfaces is logged whether
or not a position follows, so two different questions can be answered later:
does the SCREEN identify moves, and does the SELECTION beat the screen? Day-45's
attribution split taught the same lesson for the intraday book — the tape and
the picks had to be separated before either could be judged.

NO PROBABILITY IS STORED, because none is produced (day-56). What is stored is
what the MARKET implied, which is falsifiable: if outcomes systematically beat
the implied move, that is an edge and this file will show it. If they do not,
this file will say so, and that is worth just as much.
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

CATLEDGER = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                         "catalyst_ledger.csv")
FIELDS = ["logged", "ticker", "event_kind", "event_date", "px_at_log",
          "implied_move", "skew", "cash_per_share", "runway_q", "adcom",
          "stance", "traded", "px_after", "outcome", "move_actual", "note"]


def load(path: str = CATLEDGER) -> list:
    if not os.path.exists(path):
        return []
    with open(path) as f:
        return list(csv.DictReader(f))


def save(rows: list, path: str = CATLEDGER) -> None:
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS, restval="")
        w.writeheader()
        w.writerows(rows)


def log_screen(rows: list, screened: list, today: dt.date,
               traded: set | None = None) -> tuple:
    """Record every catalyst the screen surfaced today. Log-once per event.

    Keyed on (ticker, event_date) rather than the log date: a PDUFA appears in
    the screen every morning for months, and re-logging it daily would turn one
    event into ninety rows and make any later hit rate meaningless.
    """
    traded = traded or set()
    seen = {(r["ticker"], r["event_date"]) for r in rows}
    out, added = list(rows), 0
    for s in screened:
        key = (s.get("ticker", ""), s.get("date", ""))
        if not key[0] or not key[1] or key in seen:
            continue
        f = s.get("fund") or {}
        out.append({
            "logged": today.isoformat(), "ticker": key[0],
            "event_kind": s.get("kind", "PDUFA"), "event_date": key[1],
            "px_at_log": f"{s['spot']:.4f}" if s.get("spot") else "",
            "implied_move": f"{s['move']:.4f}" if s.get("move") is not None else "",
            "skew": f"{s['skew']:.4f}" if s.get("skew") is not None else "",
            "cash_per_share": (f"{f['cash_per_share']:.4f}"
                               if f.get("cash_per_share") else ""),
            "runway_q": f"{f['runway_q']:.2f}" if f.get("runway_q") else "",
            "adcom": s.get("adcom", ""), "stance": s.get("stance", ""),
            "traded": "1" if key[0] in traded else "0",
            "px_after": "", "outcome": "", "move_actual": "", "note": ""})
        seen.add(key)
        added += 1
    return out, added


def score(rows: list, price_fn, today: dt.date, settle_days: int = 3) -> tuple:
    """Fill the outcome for events whose date has passed. Never back-edits.

    `settle_days` because a decision announced on the date is often disclosed
    after the close, and the reaction can straddle the boundary — the same
    filing-date ambiguity `validate_catalyst.window_returns` handles.
    """
    rows = [dict(r) for r in rows]
    n = 0
    for r in rows:
        if r.get("move_actual") or not r.get("event_date") or not r.get("px_at_log"):
            continue
        try:
            ev = dt.date.fromisoformat(r["event_date"])
        except ValueError:
            continue
        if (today - ev).days < settle_days:
            continue
        px = price_fn(r["ticker"])
        if px is None:
            continue
        before = float(r["px_at_log"])
        r["px_after"] = f"{px:.4f}"
        r["move_actual"] = f"{(px / before - 1) * 100:.3f}"
        n += 1
    return rows, n


def report(rows: list) -> str:
    """What the record can and cannot yet say. Refuses to imply significance."""
    scored = [r for r in rows if r.get("move_actual")]
    L = ["=" * 62,
         f"CATALYST RECORD — {len(rows)} events logged, {len(scored)} scored",
         "=" * 62]
    if not scored:
        L.append("  No event has resolved yet. This file exists so that in six")
        L.append("  months there is evidence rather than opinion — the intraday")
        L.append("  engine can say 'no edge' only because it has 356 scored legs.")
        return "\n".join(L)

    def blk(label, sub):
        if not sub:
            return f"  {label:<22} n=0"
        mv = [abs(float(r["move_actual"])) for r in sub]
        beat = [r for r in sub if r.get("implied_move")
                and abs(float(r["move_actual"])) > float(r["implied_move"]) * 100]
        return (f"  {label:<22} n={len(sub):<4} median |move| "
                f"{sorted(mv)[len(mv)//2]:>6.1f}%   exceeded implied "
                f"{len(beat)}/{len(sub)}")

    L.append(blk("ALL", scored))
    L.append(blk("traded", [r for r in scored if r.get("traded") == "1"]))
    L.append(blk("screened only", [r for r in scored if r.get("traded") != "1"]))
    for st in sorted({r.get("stance", "") for r in scored if r.get("stance")}):
        L.append(blk(f"[{st}]", [r for r in scored if r.get("stance") == st]))
    if len(scored) < 30:
        L.append(f"  ⚠ {len(scored)} scored events is far too few to conclude "
                 "anything.\n    Reported so the record accrues in public, not "
                 "so it can be quoted.")
    return "\n".join(L)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--score", action="store_true")
    a = ap.parse_args(argv)
    rows = load()
    if a.score:
        from adapters import YahooDirectAdapter
        ad = YahooDirectAdapter(exchange_tz="America/New_York")

        def px(t):
            try:
                q = ad.get_quote(t)
                return float(q.last) if q.last is not None else None
            except Exception:
                return None
        rows, n = score(rows, px, dt.date.today())
        save(rows)
        print(f"scored {n} newly-resolved events")
    print(report(rows))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
