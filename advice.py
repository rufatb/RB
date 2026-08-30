#!/usr/bin/env python3
"""
advice.py — a record of what the SYSTEM said to do, so its advice can be scored.

THE GAP THIS FILLS, and it is the reason "would you rely on this" had no good
answer. Three records already exist and none of them holds a recommendation:

    ledger.py      the intraday PICKS and whether they went the right way
    positions.py   what the PORTFOLIO MANAGER says they did
    catledger.py   catalyst events that were SCREENED

So the engine's picks are scored, and the human's trades are recorded, and the
one thing nobody writes down is the ADVICE. When this system said "exit ZYME"
twice and holding was right, nothing anywhere captured that it had said so.
An adviser whose recommendations are not recorded cannot be evaluated, and
cannot be wrong in a way that shows up later.

WHAT A RECORD HAS TO CONTAIN TO BE FALSIFIABLE. Not a sentiment. Four things:

    ACTION      what to do, from a closed set. "Consider trimming" is not an
                action and cannot be scored.
    BASIS       the measured claim it rests on, named. If the basis is later
                retracted -- and five have been in eleven days -- every piece
                of advice built on it can be found and re-examined.
    HORIZON     when the advice should be judged. Advice with no horizon can
                always be defended by waiting.
    PRICE       the mark at the moment of the advice, so the counterfactual is
                computable rather than argued.

WHAT IT DELIBERATELY DOES NOT DO. It does not grade itself. Scoring compares
the price at the horizon to the price at the advice, and reports it; whether
that was the right call in context is a judgement, and a file that awarded
itself marks would be worth nothing.

Read-only with respect to the market, like everything else here.
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import baserate as B  # noqa: E402

PATH = os.path.join(B.DATA, "advice.csv")
FIELDS = ["issued", "ticker", "action", "basis", "horizon_days", "px_at_advice",
          "px_at_horizon", "move_pct", "judged", "note"]

# A CLOSED SET. Anything not on this list is not advice, it is commentary.
ACTIONS = ("BUY", "SELL", "SHORT", "COVER", "HOLD", "EXIT", "HEDGE",
           "STAND ASIDE", "SIZE DOWN")


def load(path: str = PATH) -> list:
    if not os.path.exists(path):
        return []
    with open(path, newline="") as f:
        return list(csv.DictReader(f))


def save(rows: list, path: str = PATH) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)


def record(rows: list, ticker: str, action: str, basis: str,
           horizon_days: int, px: float | None, today: dt.date,
           note: str = "") -> tuple:
    """Append one piece of advice. Idempotent per (day, ticker, action).

    Re-running the morning report must not multiply the record — the same
    advice repeated on the same day is one recommendation, not two.
    """
    if action not in ACTIONS:
        raise ValueError(f"{action!r} is not in the closed action set")
    key = (today.isoformat(), ticker, action)
    for r in rows:
        if (r["issued"], r["ticker"], r["action"]) == key:
            return rows, 0
    rows = list(rows) + [{
        "issued": today.isoformat(), "ticker": ticker, "action": action,
        "basis": basis, "horizon_days": str(horizon_days),
        "px_at_advice": f"{px:.4f}" if px is not None else "",
        "px_at_horizon": "", "move_pct": "", "judged": "", "note": note}]
    return rows, 1


def due(rows: list, today: dt.date) -> list:
    """Advice whose horizon has passed and which has not been marked."""
    out = []
    for r in rows:
        if r.get("judged") or not r.get("px_at_advice"):
            continue
        try:
            when = dt.date.fromisoformat(r["issued"])
            h = int(r["horizon_days"])
        except (ValueError, KeyError):
            continue
        if (today - when).days >= h:
            out.append(r)
    return out


def mark(rows: list, price_fn, today: dt.date) -> tuple:
    """Fill the outcome for advice whose horizon has passed. Never back-edits.

    The move is recorded RAW and unsigned by intent: whether a -4% move after
    a SELL was good advice depends on the action, and encoding that judgement
    here would let the file flatter itself. `report` applies the sign.
    """
    rows = [dict(r) for r in rows]
    n = 0
    for r in due(rows, today):
        px = price_fn(r["ticker"])
        if px is None:
            continue
        before = float(r["px_at_advice"])
        r["px_at_horizon"] = f"{px:.4f}"
        r["move_pct"] = f"{(px / before - 1) * 100:.3f}"
        r["judged"] = today.isoformat()
        n += 1
    return rows, n


# Which direction makes a piece of advice look right. HOLD and STAND ASIDE are
# deliberately absent: they have no directional claim, so scoring them by price
# would be scoring the market, not the advice.
DIRECTION = {"BUY": +1, "COVER": +1, "SELL": -1, "EXIT": -1, "SHORT": -1,
             "SIZE DOWN": -1, "HEDGE": -1}


def report(rows: list) -> str:
    done = [r for r in rows if r.get("move_pct")]
    L = ["▎ADVICE RECORD — what this system told you to do"]
    if not done:
        pend = len([r for r in rows if not r.get("judged")])
        L.append(f"   {len(rows)} recommendation(s) on file, {pend} still "
                 "inside their horizon,")
        L.append("   0 scored. Nothing here can be judged yet, and saying so is "
                 "the point.")
        return "\n".join(L)
    scored = [(r, DIRECTION[r["action"]] * float(r["move_pct"]))
              for r in done if r["action"] in DIRECTION]
    if not scored:
        L.append(f"   {len(done)} marked, none with a directional claim "
                 "(HOLD/STAND ASIDE are not scored).")
        return "\n".join(L)
    good = sum(1 for _, v in scored if v > 0)
    avg = sum(v for _, v in scored) / len(scored)
    L.append(f"   directional advice scored: {good}/{len(scored)} moved the way "
             f"it implied, mean {avg:+.2f}%")
    for r, v in sorted(scored, key=lambda x: x[0]["issued"])[-8:]:
        L.append(f"     {r['issued']}  {r['action']:<11}{r['ticker']:<7}"
                 f"{v:+7.2f}%   {r['basis'][:44]}")
    L.append("   ── the move is recorded raw; the sign is applied per action. "
             "HOLD and")
    L.append("      STAND ASIDE carry no directional claim and are not scored.")
    return "\n".join(L)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--mark", action="store_true")
    a = ap.parse_args(argv)
    rows = load()
    if a.mark:
        from adapters import YahooDirectAdapter
        ad = YahooDirectAdapter(exchange_tz="America/New_York")

        def px(t):
            try:
                q = ad.get_quote(t)
                return float(q.last) if q.last else None
            except Exception:
                return None
        rows, n = mark(rows, px, dt.date.today())
        save(rows)
        print(f"marked {n}")
    print(report(rows))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
