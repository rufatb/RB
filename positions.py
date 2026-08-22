#!/usr/bin/env python3
"""
positions.py — what you are actually holding, carried across days.

WHY THIS DID NOT EXIST. Everything in this repo so far is STATELESS: the 9:46
engine publishes a pair, the ledger scores it after the close, and tomorrow
starts from nothing. That is coherent for a flat-by-3:55 book and useless for
anything held longer — a catalyst position waiting on a PDUFA date three weeks
out has no representation anywhere. The morning report could not tell you what
you own, only what it would buy today.

WHAT A POSITION KNOWS THAT A PICK DOES NOT
  * its ENTRY, so P&L is measured from what you paid rather than from a
    hypothetical 9:45 print;
  * how long it has been held, which is the number that decides whether a
    thesis is working or just slow;
  * its EXIT CONDITION, stated when the position is opened and never invented
    afterwards. A position without a written exit is how a day trade becomes an
    investment;
  * the EVENT it is waiting for, if any, so the brief can warn BEFORE a binary
    window opens rather than explaining afterwards.

DELIBERATELY NOT A BROKER. Nothing here places, sizes, or cancels an order. It
records what the user says they did and marks it to market. Same read-only
property as the rest of the repo, and the same reason: the tool's job is to be
honest about state, not to act.

FAIL-CLOSED ON MARKS. If a price cannot be fetched the position is shown with a
stale marker and excluded from book totals rather than carried at its entry
price. A position silently marked at cost reads as flat when it may be halved —
the same class of error as day-42's stale ledger, where absence of data was
read as absence of movement.
"""

from __future__ import annotations

import csv
import datetime as dt
import os

POSITIONS = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                         "positions.csv")
# `upside`/`downside` are the two branches of a BINARY thesis, recorded at
# entry. They exist so the brief can show the probability the market is paying
# TODAY versus the one assumed when the position was opened — the ZYME thesis
# was written at $25 implying 29%, and by $28.67 the market implied 53%. The
# gap you are betting on shrinks as the price runs, and that has to be visible
# before the event, not reconstructed after it. Blank for non-binary positions.
FIELDS = ["id", "ticker", "side", "shares", "entry_px", "entry_date",
          "source", "thesis", "exit_condition", "event_date", "event_kind",
          "upside", "downside", "status", "exit_px", "exit_date"]
OPEN, CLOSED = "OPEN", "CLOSED"


def load(path: str = POSITIONS) -> list:
    if not os.path.exists(path):
        return []
    with open(path) as f:
        return list(csv.DictReader(f))


def save(rows: list, path: str = POSITIONS) -> None:
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS, restval="")
        w.writeheader()
        w.writerows(rows)


def next_id(rows: list) -> str:
    n = max((int(r["id"]) for r in rows if str(r.get("id", "")).isdigit()),
            default=0)
    return str(n + 1)


def open_position(rows: list, ticker: str, side: str, shares: float,
                  entry_px: float, entry_date: str, source: str,
                  exit_condition: str, thesis: str = "",
                  event_date: str = "", event_kind: str = "",
                  upside: float | None = None,
                  downside: float | None = None) -> list:
    """Append a new OPEN position.

    `exit_condition` is REQUIRED and free text — "flat by 3:55", "close on
    PDUFA outcome", "stop at 21.50". It is written at entry precisely because
    that is the only moment it can be chosen without knowing the answer.
    """
    if side not in ("LONG", "SHORT"):
        raise ValueError("side must be LONG or SHORT")
    if shares <= 0 or entry_px <= 0:
        raise ValueError("shares and entry_px must be positive")
    if not exit_condition.strip():
        raise ValueError("exit_condition is required — a position without a "
                         "written exit is how a day trade becomes an investment")
    rows = list(rows)
    rows.append({"id": next_id(rows), "ticker": ticker.upper(), "side": side,
                 "shares": f"{shares:g}", "entry_px": f"{entry_px:.4f}",
                 "entry_date": entry_date, "source": source, "thesis": thesis,
                 "exit_condition": exit_condition, "event_date": event_date,
                 "event_kind": event_kind,
                 "upside": f"{upside:.4f}" if upside else "",
                 "downside": f"{downside:.4f}" if downside else "",
                 "status": OPEN, "exit_px": "", "exit_date": ""})
    return rows


def close_position(rows: list, pos_id: str, exit_px: float,
                   exit_date: str) -> list:
    rows = [dict(r) for r in rows]
    for r in rows:
        if r["id"] == str(pos_id) and r["status"] == OPEN:
            r.update({"status": CLOSED, "exit_px": f"{exit_px:.4f}",
                      "exit_date": exit_date})
            return rows
    raise KeyError(f"no OPEN position with id {pos_id}")


def pnl(side: str, entry_px: float, mark: float, shares: float) -> tuple:
    """(percent, dollars) for one leg. Shorts profit when the mark falls."""
    sign = 1.0 if side == "LONG" else -1.0
    pct = (mark / entry_px - 1.0) * 100.0 * sign
    return pct, entry_px * shares * pct / 100.0


def days_held(entry_date: str, today: dt.date) -> int:
    return (today - dt.date.fromisoformat(entry_date)).days


def mark_book(rows: list, marks: dict, today: dt.date) -> dict:
    """Mark every OPEN position. Missing marks are STALE, never carried at cost.

    Returns legs (each with pnl and a `stale` flag), the book totals computed
    from marked legs ONLY, and the count of stale legs so the caller can say so
    out loud rather than quietly reporting a partial book as a whole one.
    """
    legs, net_dollars, gross, stale = [], 0.0, 0.0, 0
    for r in rows:
        if r.get("status") != OPEN:
            continue
        sh, ep = float(r["shares"]), float(r["entry_px"])
        mark = marks.get(r["ticker"])
        leg = {"id": r["id"], "ticker": r["ticker"], "side": r["side"],
               "shares": sh, "entry_px": ep,
               "days": days_held(r["entry_date"], today),
               "exit_condition": r.get("exit_condition", ""),
               "event_date": r.get("event_date", ""),
               "event_kind": r.get("event_kind", ""),
               "source": r.get("source", ""), "thesis": r.get("thesis", ""),
               "upside": r.get("upside", ""), "downside": r.get("downside", ""),
               "stale": mark is None}
        if mark is None:
            stale += 1
            leg.update({"mark": None, "pnl_pct": None, "pnl_usd": None})
        else:
            p, d = pnl(r["side"], ep, float(mark), sh)
            leg.update({"mark": float(mark), "pnl_pct": p, "pnl_usd": d})
            net_dollars += d
            gross += ep * sh
        legs.append(leg)
    return {"legs": legs, "net_usd": net_dollars, "gross": gross,
            "net_pct": (net_dollars / gross * 100.0) if gross else 0.0,
            "stale": stale}


def net_exposure(legs: list) -> float:
    """Signed notional as a fraction of gross. ~0 is hedged; +/-1 is directional.

    Day-47 published a short-only book on a falling tape, made $73, and the
    attribution showed every cent came from being unhedged. The brief needs this
    number where it can be seen BEFORE the day, not reconstructed after it.
    """
    gross = sum(l["entry_px"] * l["shares"] for l in legs)
    if not gross:
        return 0.0
    signed = sum(l["entry_px"] * l["shares"] * (1 if l["side"] == "LONG" else -1)
                 for l in legs)
    return signed / gross


def due_today(legs: list, today: dt.date, warn_days: int = 7) -> tuple:
    """(closing today, entering an event window soon). Pure + testable."""
    closing, upcoming = [], []
    for l in legs:
        ed = l.get("event_date") or ""
        if not ed:
            continue
        try:
            d = (dt.date.fromisoformat(ed) - today).days
        except ValueError:
            continue
        if d <= 0:
            closing.append(l)
        elif d <= warn_days:
            upcoming.append((l, d))
    return closing, upcoming
