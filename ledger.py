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


PRINTS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "universe_prints.csv")
PRINT_FIELDS = ["date", "ticker", "p945"]


def append_universe_prints(rows: list, date: str, path: str = PRINTS) -> int:
    """Store the 9:45 print for EVERY evaluated universe name (day-28).

    The pair is market-neutral, so the tide cancels between the legs and a
    leg's real contribution is its move RELATIVE to the universe. The ledger's
    `hit` column is absolute, so it credits a short for a falling tape and
    penalises a long for the same — measuring the market as much as the
    selection. Reconstructing the tide afterwards needs every name's 9:45
    price, and the QUALIFIED picks alone are a selected sample that would give
    a biased tide. Publish-once, like the ledger itself."""
    existing = []
    if os.path.exists(path):
        with open(path) as f:
            existing = list(csv.DictReader(f))
    if any(r["date"] == date for r in existing):
        return 0
    for r in rows:
        existing.append({"date": date, "ticker": r["ticker"], "p945": f"{r['p945']:.4f}"})
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=PRINT_FIELDS, restval="")
        w.writeheader()
        w.writerows(existing)
    return len(rows)


def tide_by_date(prints: list, close_fn) -> dict:
    """date -> median 9:45->close move across the whole universe. Pure-ish."""
    by = {}
    for r in prints:
        c = close_fn(r["ticker"], r["date"])
        if c is None:
            continue
        by.setdefault(r["date"], []).append((c / float(r["p945"]) - 1) * 100)
    return {d: float(sorted(v)[len(v) // 2]) for d, v in by.items() if len(v) >= 10}


def relative_line(pair_rows: list, tides: dict) -> str:
    """Pair-leg capture measured against the tide — selection skill with the
    tape removed. Absolute capture stays reported alongside it; neither alone
    is the whole picture, and only this one answers 'are the PICKS good?'."""
    usable = [r for r in pair_rows if r["date"] in tides and r["r1"] != ""]
    if len(usable) < 4:
        return ("  relative capture     : (needs universe prints — recording "
                "started day-28)")
    rel = [(float(r["r1"]) - tides[r["date"]]) * (1 if r["side"] == "LONG" else -1)
           for r in usable]
    wins = sum(1 for x in rel if x > 0)
    return (f"  relative capture     : {sum(rel)/len(rel):+.3f}%/leg vs the tide "
            f"over {len(usable)} legs  ({wins}/{len(usable)} beat it)")


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


def missing_sessions(rows: list, today: dt.date, is_trading_day_fn,
                     lookback: int = 10) -> list:
    """Trading days between the ledger's last entry and today that it has NO
    rows for. Pure + testable (the calendar is injected).

    DAY-42, and this one bit a live report rather than a backtest. Two sessions
    were working the same repo; this clone was eight commits stale, so
    `ledger.csv` was missing an entire scored session (2026-08-13, 0/4 on the
    pair). The 9:46 board itself was unaffected — it is computed from market
    data and never reads the ledger — but the RECORD printed underneath it was
    wrong in the flattering direction: PAIR 24/47 (51%) when the truth was
    24/51 (47%), and the report stated there had been no session the previous
    day. Both claims came from absence of data being read as absence of events.

    Deliberately a WARNING and not a fail-closed refusal, unlike the coverage
    and extrapolation guards. Those protect the BET, and a partial universe
    silently changes it. This protects the RECORD, and the honest response to a
    possibly-incomplete record is to say so, not to withhold a board that does
    not depend on it. A legitimate no-run day (nobody asked) trips this too —
    that is the correct behaviour, because from the ledger's side the two are
    indistinguishable and only the reader can tell them apart."""
    dates = {r["date"] for r in rows if r.get("date")}
    if not dates:
        return []
    last = dt.date.fromisoformat(max(dates))
    gaps, d = [], last + dt.timedelta(days=1)
    while d < today and len(gaps) <= lookback:
        if is_trading_day_fn(d) and d.isoformat() not in dates:
            gaps.append(d.isoformat())
        d += dt.timedelta(days=1)
    return gaps


def gap_line(gaps: list) -> str:
    """One-line caveat for the report header; empty string when there is none."""
    if not gaps:
        return ""
    shown = ", ".join(gaps[:5]) + ("…" if len(gaps) > 5 else "")
    return ("  ⚠ RECORD MAY BE INCOMPLETE: no rows for trading day(s) "
            f"{shown}. Either no board was published then, or this copy of the\n"
            "    ledger is stale (day-42). Percentages below are computed only "
            "on what is here.")


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


def wilson(hits: int, n: int, z: float = 1.96) -> tuple:
    """Wilson score interval for a hit rate. WHY (day-25, external audit): a
    bare '44%' invites a decision; '44% (30-59%)' shows it is indistinguishable
    from a coin flip at n=43 and forbids one. Normal-approximation intervals
    are wrong at these sample sizes and near the boundaries. Pure+testable."""
    if n <= 0:
        return (0.0, 1.0)
    p = hits / n
    d = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / d
    half = z * ((p * (1 - p) / n + z * z / (4 * n * n)) ** 0.5) / d
    return (max(0.0, centre - half), min(1.0, centre + half))


def live_summary(rows: list, last_n: int = 20) -> dict | None:
    """Compact live-record numbers for the morning report header (day-13:
    'so far it's not working' must be visible IN the tool, every day, not
    discovered later). Pure; None when nothing is scored yet."""
    done = [r for r in rows if r["hit"] != ""]
    if not done:
        return None
    pair = [r for r in done if r.get("role") == "pair"]
    recent = done[-last_n:]
    # Day-25: per-SIDE, because the aggregate hid it. Shorts ran 44% while the
    # header printed a reassuring 50% overall. Reported WITH a Wilson interval
    # so it cannot be read as "shorts are broken" at these sample sizes.
    longs = [r for r in done if r["side"] == "LONG"]
    shorts = [r for r in done if r["side"] == "SHORT"]
    return {"all_n": len(done), "all_hits": sum(int(r["hit"]) for r in done),
            "pair_n": len(pair), "pair_hits": sum(int(r["hit"]) for r in pair),
            "recent_n": len(recent), "recent_hits": sum(int(r["hit"]) for r in recent),
            "long_n": len(longs), "long_hits": sum(int(r["hit"]) for r in longs),
            "short_n": len(shorts), "short_hits": sum(int(r["hit"]) for r in shorts)}


def decisive_line(pair_rows: list, threshold: float = 0.10) -> str:
    """Hit rate EXCLUDING economic scratches (day-35).

    The `hit` column is a pure sign test, so a leg that finishes +0.015%% counts
    exactly as much as one that finishes +1.5%%. Measured on the live record:
    11%% of pair legs end with |capture| < 0.10%%, and 4 of those 5 landed on the
    winning side of zero — inflating the headline hit rate by ~3pp (51%% -> 48%%).

    A coin landing on its edge is not a win. This line reports the hit rate over
    legs that actually moved, and it is deliberately the LESS flattering number:
    it exists to remove an artifact, not to add one. Pure + testable."""
    scored = [r for r in pair_rows if r.get("r1") not in (None, "")]
    if len(scored) < 10:
        return "  decisive legs       : (needs more scored legs)"
    capt = [float(r["r1"]) * (1 if r["side"] == "LONG" else -1) for r in scored]
    big = [c for c in capt if abs(c) >= threshold]
    if not big:
        return "  decisive legs       : none cleared the threshold"
    h = sum(1 for c in big if c > 0)
    n_scr = len(capt) - len(big)
    return (f"  decisive legs       : {h}/{len(big)} ({h/len(big)*100:.0f}%) with "
            f"|capture| >= {threshold:.2f}%  ({n_scr} scratches excluded)")


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


def attribution(pair_rows: list, tides: dict) -> tuple:
    """Split the book's return into TIDE exposure and SELECTION. Pure + testable.

    DAY-45. Every post-mortem here has had to argue verbally about whether a
    losing day was "the market" or "the picks", and the two existing lines each
    answer half of it: `book_return_line` gives the total, `relative_line` gives
    per-leg skill but is equal-weighted and so does not reconcile to the book.
    This reconciles exactly.

    A leg's capture is `(tide + rel) * sign`, so the weighted book return splits
    cleanly and without residual:

        sum(w*cap) = tide * sum(w*sign)      <- TIDE component
                   + sum(w*sign*rel)          <- SELECTION component

    `sum(w*sign)` is the book's residual directional exposure. The long/short
    construction is supposed to hold it near zero, and this is the first thing
    that measures whether it actually does rather than assuming it. Measured
    over the first 14 sessions: TIDE +0.009%/session (t=+0.78) and SELECTION
    -0.136%/session (t=-1.10) — i.e. the hedge does its job and every bit of the
    loss is the picks, which is exactly what day-43's ceiling result predicts a
    signal-free selector would produce.

    Returns (tide_component, selection_component, n_sessions), each a per-session
    mean in percent."""
    usable = [r for r in pair_rows
              if r.get("weight") not in (None, "") and r.get("r1") not in (None, "")
              and r.get("date") in tides]
    if not usable:
        return (None, None, 0)
    by_day: dict = {}
    for r in usable:
        sign = 1 if r["side"] == "LONG" else -1
        w, mv, td = float(r["weight"]), float(r["r1"]), tides[r["date"]]
        t_c, s_c = by_day.setdefault(r["date"], [0.0, 0.0])
        by_day[r["date"]] = [t_c + w * sign * td, s_c + w * sign * (mv - td)]
    n = len(by_day)
    return (sum(v[0] for v in by_day.values()) / n,
            sum(v[1] for v in by_day.values()) / n, n)


def attribution_line(pair_rows: list, tides: dict) -> str:
    """Two-line report block for the attribution split; empty when unavailable."""
    t_c, s_c, n = attribution(pair_rows, tides)
    if not n:
        return "  attribution          : (needs universe prints + weights)"
    return (f"  attribution          : TIDE {t_c:+.3f}%/session (market exposure, "
            f"target ~0) · SELECTION {s_c:+.3f}%/session (the picks)\n"
            f"                         over {n} sessions — these sum to the "
            f"book-weighted return above")


def _tides_for_report() -> dict:
    """Best-effort tide-by-date for the CLI report; {} when prints/net absent.

    Computed ONCE and shared by the relative and attribution lines — otherwise
    each rebuilds it, meaning two full passes of daily-bar downloads for
    identical numbers."""
    try:
        if not os.path.exists(PRINTS):
            return {}
        with open(PRINTS) as f:
            prints = list(csv.DictReader(f))
        from adapters import YahooDirectAdapter
        a = YahooDirectAdapter(exchange_tz="America/Toronto")
        cache: dict = {}

        def close_fn(t, date):
            if t not in cache:
                try:
                    b = a.get_daily_bars(t, 120)
                    cache[t] = {str(i.date()): float(c) for i, c in b["Close"].items()}
                except Exception:
                    cache[t] = {}
            return cache[t].get(date)
        return tide_by_date(prints, close_fn)
    except Exception:
        return {}


def report(rows: list) -> str:
    done = [r for r in rows if r["hit"] != ""]
    if not done:
        return "ledger: no scored rows yet"
    out = ["=" * 60, f"LEDGER REPORT — {len(done)} scored picks (live, no hindsight)", "=" * 60]
    try:
        import dashboard
        g = gap_line(missing_sessions(rows, dt.date.today(), dashboard.is_trading_day))
        if g:
            out.append(g)
    except Exception as e:                       # calendar unavailable, never fatal
        out.append(f"  (session-gap check unavailable: {type(e).__name__})")

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
        out.append(decisive_line(pair_sub))
        tides = _tides_for_report()
        out.append(relative_line(pair_sub, tides))
        out.append(attribution_line(pair_sub, tides))
    out.append("  — density hypothesis (pre-registered: dense > mid/sparse) —")
    for tag in ("dense", "mid", "sparse", "n/a"):
        sub = [r for r in done if r["confidence"] == tag]
        if sub:
            out.append(line(f"[{tag}]", sub))
    n_tagged = len([r for r in done if r["confidence"] in ("dense", "mid", "sparse")])
    # DAY-47: the pre-registered gate is now DECIDED, and against the
    # hypothesis. On 40,801 qualified picks over 719 walk-forward sessions
    # (validate_density.py) the three tags hit 49.5% / 49.7% / 49.6% — flat to
    # a tenth of a point — and sparse beat dense on capture in only 2 of 4
    # quarters, against a 4-of-4 bar. The tag is real and measures something
    # (corr(nd, vol20) = +0.17; dense names move 0.73% vs sparse 1.29%) but it
    # sorts by VOLATILITY, not by edge. Whatever spread the small live sample
    # shows below is noise: n=91 against n=13,601 per bucket in the deep test.
    out.append(f"  (tagged so far: {n_tagged} — GATE DECIDED day-47: NO gate. "
               "Tags sort by volatility,\n   not by edge; the live spread here "
               "is noise against 40,801 deep-panel picks.)")
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
