#!/usr/bin/env python3
"""
brief.py — the single morning page. One command, four layers, honest labels.

WHY ONE PAGE. Until now "run report" printed a fresh intraday pair and nothing
else: no memory of what you were holding, no view of what was coming, and the
pair presented first as though it were the most important thing on the screen.
It is the least. This composes the four layers in the order a decision actually
needs them —

    1  POSITIONS    what you hold, marked, with the exit written at entry
    2  ACTIONS      what closes today, what enters a binary window soon
    3  CALENDAR     scheduled FDA decisions (facts, from company filings)
    4  INTRADAY     the 9:46 pair, printed WITH its own record

— and each layer states what it may claim, because they are not equal:

    positions   fact. no prediction at all.
    calendar    fact. a date a company disclosed; no probability implied.
    intraday    MEASURED, NO EDGE. 34 rejections; gradient boosting reaches
                AUC 0.5022 on 122,234 rows where the same harness detects a
                planted 52% coin at z=15. It prints its live record next to
                every pick so the number is never out of sight.

THE POINT OF THE REDESIGN is that this page can say "nothing to do today".
The old report could not — it manufactured a pair every session, which trains
a reader to trade a coin flip. Most mornings the honest output is a position
review and no new risk.

WHAT THE INTRADAY SECTION ADDS. Its hit rate cannot be improved; that is
measured and settled. What can improve is how much it tells you about WHY a
name was chosen and WHAT WOULD INVALIDATE it — the runner-up it beat and by
how much, whether its side is crowded into one sector, and its expectation
stated tide-relative rather than absolute. A pick you can interrogate is worth
more than a probability you cannot.

Read-only throughout. Nothing here places, sizes, or cancels an order.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sys
from zoneinfo import ZoneInfo

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import ledger  # noqa: E402
import positions as pos  # noqa: E402
from validate_exit import SCRATCH  # noqa: E402

RULE = "─" * 74


def _fmt_pct(x, w=7):
    return f"{x:+{w}.2f}%" if x is not None else f"{'stale':>{w}} "


# ──────────────────────────────────────────────────────────── 1. POSITIONS
def render_positions(book: dict, today: dt.date,
                     mark_errors: dict | None = None) -> str:
    legs = book["legs"]
    if not legs:
        return ("▎OPEN POSITIONS — none\n"
                "   Flat. Nothing to mark, nothing to manage.")
    x = pos.net_exposure(legs)
    tag = ("hedged" if abs(x) < 0.25 else
           f"DIRECTIONAL {'long' if x > 0 else 'short'}")
    L = [f"▎OPEN POSITIONS ({len(legs)})".ljust(46) +
         f"net exposure {x:+.2f} ({tag})", "   " + RULE,
         f"   {'id':<3}{'ticker':<8}{'side':<6}{'entry':>9}{'mark':>9}"
         f"{'P&L':>9}{'$':>10}{'held':>6}  waiting on"]
    for l in legs:
        ev = (f"{l['event_kind'] or 'event'} {l['event_date']}"
              if l["event_date"] else l["exit_condition"][:26])
        mark = f"{l['mark']:>9.2f}" if l["mark"] is not None else f"{'—':>9}"
        usd = f"{l['pnl_usd']:>+10.0f}" if l["pnl_usd"] is not None else f"{'—':>10}"
        L.append(f"   {l['id']:<3}{l['ticker']:<8}{l['side']:<6}"
                 f"{l['entry_px']:>9.2f}{mark}{_fmt_pct(l['pnl_pct'])}{usd}"
                 f"{l['days']:>5}d  {ev}")
    L.append("   " + RULE)
    L.append(f"   book {book['net_pct']:+.2f}% on ${book['gross']:,.0f} "
             f"deployed  ·  {book['net_usd']:+,.0f}")
    for d, gross, names in pos.event_concentration(legs):
        L.append(f"   ⚠ ${gross:,.0f} resolves on ONE date ({d}): "
                 f"{', '.join(names)}.\n     Binaries settling together are "
                 "perfectly correlated that morning, however\n     balanced the "
                 "book looks by side.")
    if book["stale"]:
        why = (f" ({', '.join(sorted(set(mark_errors.values())))})"
               if mark_errors else "")
        L.append(f"   ⚠ {book['stale']} position(s) could not be marked{why} and "
                 "are EXCLUDED from the total.\n     A stale leg is not a flat "
                 "leg — price it by hand before acting.")
    return "\n".join(L)


def render_catalyst_detail(legs: list, today: dt.date) -> str:
    """For every binary position: what the market is paying NOW, versus what
    was assumed at entry.

    THE FAILURE THIS EXISTS TO PREVENT. A catalyst thesis is written once, at a
    price, with a probability attached. The price then moves — and the implied
    probability moves with it, silently. The ZYME matrix was written at $25
    against a $36/$20.50 bracket, implying the market held 29% while the thesis
    asserted 85%. At $28.67 the market implies 53%. The 56-point disagreement
    that WAS the trade has shrunk to 32 points, and nothing in a static matrix
    would ever tell you that.

    So the number is recomputed every morning from the live mark. If the market
    has come to agree with you, the edge you entered for is gone whether or not
    the position is profitable — and profit makes that easier to miss, not
    harder.
    """
    import catalyst
    out = []
    for l in legs:
        if not (l.get("upside") and l.get("downside") and l["event_date"]):
            continue
        up, dn = float(l["upside"]), float(l["downside"])
        d = (dt.date.fromisoformat(l["event_date"]) - today).days
        out.append(f"   {l['ticker']} — {l['event_kind']} in {d}d "
                   f"({l['event_date']})")
        if l["thesis"]:
            out.append(f"      thesis at entry : {l['thesis']}")
        out.append(f"      bracket         : ${dn:,.2f} (fail) → ${up:,.2f} (pass)")
        p_entry = catalyst.implied_probability(l["entry_px"], up, dn)
        out.append(f"      implied P at your ${l['entry_px']:,.2f} entry: "
                   f"{p_entry:.0%}")
        if l["mark"] is None:
            out.append("      implied P now   : unavailable (mark is stale)")
            continue
        p_now = catalyst.implied_probability(l["mark"], up, dn)
        out.append(f"      implied P NOW at ${l['mark']:,.2f}       : "
                   f"{p_now:.0%}   ({(p_now-p_entry)*100:+.0f} pts since entry)")
        # what is still on the table versus what is at risk
        to_up = (up / l["mark"] - 1) * 100
        to_dn = (dn / l["mark"] - 1) * 100
        out.append(f"      from here       : {to_up:+.1f}% if approved, "
                   f"{to_dn:+.1f}% if not  →  risk/reward "
                   f"{abs(to_up/to_dn):.2f}:1" if to_dn else "")
        if p_now > 0.65:
            out.append("      ⚠ the market has largely come to agree with you. "
                       "Most of the\n        disagreement you entered for is "
                       "priced; the remaining upside is\n        thin against "
                       "an unchanged downside.")
        # Check the floor against the balance sheet rather than repeating the
        # thesis's own assumption back at the reader.
        try:
            import fundamentals as _f
            from build_catalyst import ticker_map
            cik = ticker_map(SCRATCH).get(l["ticker"], "")
            fs = _f.summarise(cik, today) if cik else None
            if fs and fs.get("cash_per_share"):
                out += _f.render(fs, l["mark"])
                if dn > fs["cash_per_share"] * 2:
                    out.append(f"      \u26a0 the ${dn:,.2f} floor is "
                               f"{dn/fs['cash_per_share']:.0f}x cash per share — "
                               "a cash argument does not support it.")
        except Exception:
            pass
        out.append("      NOTE: a CRL floor is an ASSUMPTION, not a bound — "
                   "day-56 could not\n        establish the drawdown "
                   "distribution, and verified CRLs in that\n        sample "
                   "ran to -80%.")
    if not out:
        return ""
    return "▎CATALYST POSITIONS — what the market is paying now\n" + "\n".join(out)


# ────────────────────────────────────────────────────────────── 2. ACTIONS
def render_actions(book: dict, today: dt.date, pair_note: str) -> str:
    closing, upcoming = pos.due_today(book["legs"], today)
    L = ["▎TODAY'S ACTIONS"]
    if closing:
        for l in closing:
            L.append(f"   ⏰ CLOSE-OUT DUE  {l['ticker']} — {l['event_kind']} "
                     f"was {l['event_date']}. Exit rule: {l['exit_condition']}")
    else:
        L.append("   CLOSE   nothing due")
    L.append(f"   OPEN    {pair_note}")
    for l, d in upcoming:
        L.append(f"   ⚠ {l['ticker']} enters its {l['event_kind']} window in "
                 f"{d}d ({l['event_date']}).")
        L.append("     Decide NOW whether to hold through the binary or exit "
                 "before it —\n     a decision taken during the gap is not a "
                 "decision.")
    return "\n".join(L)


# ───────────────────────────────────────────────────────────── 4. INTRADAY
def pair_reasoning(res: dict, side: str, cfg: dict) -> list:
    """Why THIS name and not the runner-up — the part that lets you overrule it.

    The old board printed a probability and a density tag. Neither tells you
    whether the choice was close. A leg picked over a near-identical rival is a
    coin flip inside a coin flip; a leg with a clear margin at least reflects
    the rule the engine claims to follow.
    """
    lg = (res.get("pair") or {}).get(side) or {}
    if lg.get("status") == "NONE" or not lg.get("pick"):
        return []
    pick = lg["pick"]
    pool = res["longs"] if side == "long" else res["shorts"]
    rivals = [r for r in pool if r["t"] != pick["t"]]
    out = []
    if rivals:
        nxt = min(rivals, key=lambda r: r.get("nd", 9e9))
        margin = nxt.get("nd", 0) - pick.get("nd", 0)
        close = abs(margin) < 0.02
        out.append(f"      chosen over {nxt['t']} on density "
                   f"(nd {pick.get('nd', 0):.3f} vs {nxt.get('nd', 0):.3f}"
                   f"{', a near tie — treat as arbitrary' if close else ''})")
    groups = cfg.get("peer_groups") or {}
    sector = next((g for g, names in groups.items() if pick["t"] in names), None)
    if sector:
        same = [r for r in pool if r["t"] in groups.get(sector, [])]
        if len(same) > 1:
            out.append(f"      {len(same)} of this side's candidates are "
                       f"{sector} — the side is concentrated, not diversified")
    out.append(f"      invalidated if: filled worse than the bound, or the "
               f"9:45 print is stale by >20 min")
    return out


def render_intraday(res: dict, cfg: dict, shadow: bool) -> tuple:
    lr = res.get("live_record") or {}
    L = ["▎INTRADAY PAIR — the 9:46 book"]
    if res.get("too_early"):
        return "\n".join(L + [f"   ⏰ too early; ready {res.get('ready_at')}"]), \
               "nothing — engine not ready"
    if res.get("coverage_fail"):
        return "\n".join(L + ["   ⛔ INSUFFICIENT COVERAGE — no board today",
                              f"   {res['coverage_fail']}"]), \
               "nothing — coverage gate failed"
    if lr.get("pair_n"):
        L.append(f"   live record: PAIR {lr['pair_hits']}/{lr['pair_n']} "
                 f"({lr['pair_hits']/lr['pair_n']*100:.0f}%) — a coin flip, "
                 "measured 34 ways")
    pair = res.get("pair") or {}
    opened = []
    for side in ("long", "short"):
        lg = pair.get(side) or {}
        if lg.get("status") == "NONE" or not lg.get("pick"):
            L.append(f"   {side.upper():<6}: ⛔ none qualified — do not force one")
            continue
        p = lg["pick"]
        L.append(f"   {side.upper():<6}: {p['t']:<9} sided-P {lg['sided']:.2f}  "
                 f"[{p.get('confidence','?')}]  9:45 ${p['p945']:.2f}")
        if p.get("shares") and not shadow:
            import r945 as _r
            b = _r.fill_bound(side.upper(), p["p945"],
                              res.get("max_chase_pct", 0.04))
            L.append(f"      ➤ {'BUY' if side == 'long' else 'SELL SHORT'} "
                     f"{p['shares']} sh (~${p.get('alloc', 0):,.0f})  "
                     f"fill bound {'<=' if side == 'long' else '>='} {b:.2f}")
        L += pair_reasoning(res, side, cfg)
        for x in (lg.get("extra") or []):
            sh = (f" — {x['shares']} sh (~${x.get('alloc', 0):,.0f})"
                  if x.get("shares") and not shadow else "")
            L.append(f"      + {x['t']}{sh} (second leg — SPLITS the same half, "
                     "does not add exposure)")
        opened.append(p["t"])
    if shadow:
        L.append("   ⛔ SHADOW — published and scored, NO capital. The record "
                 "keeps accruing at zero cost.")
        return "\n".join(L), "nothing — intraday running in shadow"
    return "\n".join(L), (", ".join(opened) if opened else
                          "nothing — no leg qualified")


# ─────────────────────────────────────────────────────────────── 5. RECORD
def render_record(rows: list) -> str:
    done = [r for r in rows if r.get("hit") not in ("", None)]
    pair = [r for r in done if r.get("role") == "pair"]
    if not pair:
        return "▎RECORD — no scored pair legs yet"
    hits = sum(int(r["hit"]) for r in pair)
    L = ["▎RECORD", f"   pair legs {hits}/{len(pair)} "
                    f"({hits/len(pair)*100:.0f}%)"]
    L.append("   " + ledger.decisive_line(pair).strip())
    tides = ledger._tides_for_report()
    if tides:
        L.append("   " + ledger.relative_line(pair, tides).strip())
        L.append("   " + ledger.attribution_line(pair, tides)
                 .strip().replace("\n", "\n   "))
    return "\n".join(L)


# ───────────────────────────────────────────────────────────────── compose
def build(cfg_path: str, shadow: bool, no_net: bool = False,
          days_back: int = 4) -> str:
    from dashboard import load_config
    cfg = load_config(cfg_path)
    tz = ZoneInfo(cfg.get("exchange_tz", "America/Toronto"))
    now = dt.datetime.now(tz)
    today = now.date()

    parts = [f"═" * 74,
             f"MORNING BRIEF — {now:%a %Y-%m-%d %H:%M} {now.tzname()}",
             "═" * 74]

    # 1 positions
    prows = pos.load()
    marks: dict = {}
    mark_errors: dict = {}
    if not no_net:
        from adapters import YahooDirectAdapter
        a = YahooDirectAdapter(exchange_tz=str(tz))
        for t in {r["ticker"] for r in prows if r.get("status") == pos.OPEN}:
            # `Quote.last`, not `.price` — the field is named for what it is, a
            # last trade. Getting this wrong marked every position STALE, which
            # the fail-closed path reported honestly rather than hiding, but a
            # brief where nothing can be marked is a brief nobody will read.
            try:
                q = a.get_quote(t)
                if q.last is not None:
                    marks[t] = float(q.last)
            except Exception as e:
                mark_errors[t] = type(e).__name__
    book = pos.mark_book(prows, marks, today)
    parts.append(render_positions(book, today, mark_errors))

    # 4 intraday (computed before actions, which cite it)
    pair_note, intraday = "nothing — engine not run", ""
    if not no_net:
        import r945
        res = r945.run(cfg, workers=12)
        try:
            res["live_record"] = ledger.live_summary(ledger.load())
        except Exception:
            res["live_record"] = None
        # PUBLISH before rendering. The brief replaces `r945.py --book` as the
        # morning command, so it inherits the obligation to write the day's
        # permanent record — a board printed but never recorded would stop the
        # ledger accruing on the day this shipped, silently.
        st = r945.publish(res, cfg)
        intraday, pair_note = render_intraday(res, cfg, shadow)
        for e in st["errors"]:
            intraday += f"\n   ⚠ {e}"
        if st["already"]:
            intraday += ("\n   [already published today — this is a re-read; "
                         "the first board of the day stands.\n    Share counts "
                         "shown are from that board, not a re-computation.]")
        elif st["picks"]:
            intraday += (f"\n   [recorded {st['picks']} picks "
                         f"({st['pair']} pair / {st['picks']-st['pair']} board); "
                         "score after close with `python ledger.py --score`]")

    parts.append(render_actions(book, today, pair_note))
    cat_detail = render_catalyst_detail(book['legs'], today)
    if cat_detail:
        parts.append(cat_detail)

    # 3 calendar
    try:
        import pdufa
        cal_path = os.path.join(SCRATCH, "pdufa_calendar.json")
        cal = (json.load(open(cal_path)) if os.path.exists(cal_path)
               else (pdufa.build(6, today, cal_path) if not no_net else []))
        parts.append(pdufa.render(cal, today, 120))
        # The calendar says WHAT is scheduled; the screen says what the market
        # has already paid for it. A date without price context is a diary
        # entry, not an opportunity.
        if not no_net and cal:
            try:
                import screen as _scr
                held = {l["ticker"] for l in book["legs"]}
                rows = [r for r in _scr.screen(cal, today, 130, 12)
                        if r["ticker"] not in held]
                parts.append(_scr.render(rows, today))
                # LOG every surfaced catalyst, traded or not. Recording only
                # the trades taken would measure the trader, not the screen —
                # and without this the catalyst layer would still have zero
                # scored outcomes in six months (day-64).
                try:
                    import catledger as _cl
                    lrows, added = _cl.log_screen(_cl.load(), rows, today,
                                                  {l["ticker"] for l in book["legs"]})
                    if added:
                        _cl.save(lrows)
                        parts[-1] += (f"\n   [logged {added} new event(s) to the "
                                      "catalyst record — score with "
                                      "`python catledger.py --score`]")
                except Exception as e:
                    parts[-1] += (f"\n   \u26a0 catalyst record NOT written "
                                  f"({type(e).__name__}) — the screen ran but "
                                  "nothing was learned from it")
            except Exception as e:
                parts.append(f"▎CATALYST OPPORTUNITIES\n   ⚠ pricing "
                             f"unavailable ({type(e).__name__}) — the calendar "
                             "above stands, the pricing does not")
    except Exception as e:
        parts.append(f"▎FDA DECISION CALENDAR\n   ⚠ unavailable "
                     f"({type(e).__name__}) — the rest of the brief stands")

    # ADVISORY COMMITTEES — the public expert vote, which usually moves the
    # stock more than the decision that follows it.
    if not no_net:
        try:
            import adcom as _ac
            ac_path = os.path.join(SCRATCH, "adcom.json")
            data = (json.load(open(ac_path)) if os.path.exists(ac_path)
                    else _ac.build(5, today, ac_path))
            parts.append(_ac.render(data, today, 120))
        except Exception as e:
            parts.append(f"\u258e ADVISORY COMMITTEES\n   \u26a0 unavailable "
                         f"({type(e).__name__}) — treat as UNKNOWN, not as "
                         "nothing scheduled")

    # WHAT CHANGED — filings since the last brief, for held and watched names.
    # A position waiting weeks on a decision is not static; the company keeps
    # filing, and some of those filings matter more than the decision.
    if not no_net:
        try:
            import newsflow as _nf
            from build_catalyst import ticker_map
            # ticker_map is CIK -> ticker (that is what the SEC file provides);
            # invert it for lookups by symbol. The calendar already carries a
            # CIK per row, so prefer that and fall back to the inverted map.
            by_ticker = {v: k for k, v in ticker_map(SCRATCH).items()}
            watch = {}
            for l in book["legs"]:
                watch[l["ticker"]] = by_ticker.get(l["ticker"], "")
            for c in (cal or []):
                t = c.get("ticker")
                if not t:
                    continue
                if 0 <= (dt.date.fromisoformat(c["date"]) - today).days <= 45:
                    watch[t] = c.get("cik") or by_ticker.get(t, "")
            pairs = sorted(watch.items())
            if pairs:
                since = today - dt.timedelta(days=days_back)
                parts.append(_nf.render(_nf.gather(pairs, since), since, today))
        except Exception as e:
            parts.append(f"\u258e WHAT CHANGED\n   \u26a0 filing check "
                         f"unavailable ({type(e).__name__}) — treat this as "
                         "UNKNOWN, not as quiet")

    if intraday:
        parts.append(intraday)
        # Earnings proximity for the names actually picked. The 9:45 model has
        # no earnings feed (its own header says so), and next week every
        # Canadian bank reports -- a universe that is a third financials.
        if not no_net:
            try:
                import earnings as _e
                uni = (cfg.get("scan") or {}).get("universe") or []
                picks = set()
                for side in ("long", "short"):
                    lg = (res.get("pair") or {}).get(side) or {}
                    if lg.get("pick"):
                        picks.add(lg["pick"]["t"])
                    picks |= {x["t"] for x in (lg.get("extra") or [])}
                blk = _e.render(_e.gather(uni), today, picks)
                if blk:
                    parts.append(blk)
            except Exception as ex:
                parts.append(f"\u258e EARNINGS NEARBY\n   \u26a0 unavailable "
                             f"({type(ex).__name__}) — unknown, not clear")
    parts.append(render_record(ledger.load()))
    parts.append("Read-only. Nothing here placed, sized, or cancelled an order.")
    return "\n\n".join(parts)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default="config.yaml")
    ap.add_argument("--shadow", action="store_true",
                    help="print the pair but claim no capital")
    ap.add_argument("--days-back", type=int, default=4,
                    help="lookback for the WHAT CHANGED filing scan")
    ap.add_argument("--offline", action="store_true",
                    help="positions/record only; no network")
    a = ap.parse_args(argv)
    print(build(a.config, a.shadow, a.offline, a.days_back))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
