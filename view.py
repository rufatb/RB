#!/usr/bin/env python3
"""
view.py — the short page. One screen, ordered by what you have to decide.

WHY. The full brief is 461 lines and 77% of them are one section. A page that
long is not read every morning, it is skimmed once and then trusted, which is
the worst of both: all the caveats are present and none of them are seen. This
draws the same run in about 30 lines, ordered by decision rather than by topic:

    BOOK        what you hold and what it is worth, one line
    DO TODAY    the only section that asks for an action
    COMING UP   dated catalysts, nearest first
    WATCH       anything that changed, broke, or contradicts itself
    RECORD      the live hit rate, printed next to the advice, always

IT RECOMPUTES NOTHING. `brief.build()` fills a digest as it goes and this draws
from it, so the short page cannot disagree with the long one. A summary built
from a second pass is a second opinion, and a top line that contradicts the
detail underneath it is worse than no top line at all.

WHAT IT REFUSES TO DO. It does not rank, score or shorten the CAVEATS attached
to a number — a fair value that is flagged unreliable in the long page is
flagged here too. Concision is allowed to drop detail; it is not allowed to
drop doubt. Where the short page cannot carry the reasoning it says which
command does.

COLOUR is used for one thing only: the sign of a number and the severity of a
flag. It is disabled automatically when the output is not a terminal, so piping
to a file gives clean text.
"""

from __future__ import annotations

import datetime as dt
import os
import sys

W = 66
# Below this many spread-priced legs the net figure is noise and is labelled
# as such. spread_bps only began recording on day-82, so it starts tiny and
# grows; printing it to three decimals before then invites the wrong read.
NET_MIN_LEGS = 20


def _tty() -> bool:
    return sys.stdout.isatty() and os.environ.get("NO_COLOR") is None


class C:
    """ANSI, resolved once at import against the real output stream."""
    on = False
    RESET = GREEN = RED = YELLOW = DIM = BOLD = CYAN = ""

    @classmethod
    def setup(cls, force: bool = None):
        cls.on = _tty() if force is None else force
        if cls.on:
            cls.RESET, cls.BOLD, cls.DIM = "\033[0m", "\033[1m", "\033[2m"
            cls.GREEN, cls.RED = "\033[32m", "\033[31m"
            cls.YELLOW, cls.CYAN = "\033[33m", "\033[36m"
        else:
            cls.RESET = cls.GREEN = cls.RED = cls.YELLOW = ""
            cls.DIM = cls.BOLD = cls.CYAN = ""


C.setup()


def money(x) -> str:
    if x is None:
        return "—"
    c = C.GREEN if x > 0 else (C.RED if x < 0 else "")
    return f"{c}{x:+,.0f}{C.RESET}"


def pct(x, w: int = 0) -> str:
    if x is None:
        return f"{'stale':>{w}}" if w else "stale"
    c = C.GREEN if x > 0 else (C.RED if x < 0 else "")
    return f"{c}{x:+.2f}%{C.RESET}".rjust(w + len(c) + len(C.RESET)) if w \
        else f"{c}{x:+.2f}%{C.RESET}"


def bar(x, lo: float = -25.0, hi: float = 25.0, n: int = 20) -> str:
    """A P&L bar centred on zero. Visual, not precise — the number is beside it.

    Deliberately clamped and labelled: a bar that silently saturates would make
    +30% and +300% look identical.
    """
    if x is None:
        return " " * n
    mid = n // 2
    frac = max(-1.0, min(1.0, x / hi if x >= 0 else x / abs(lo)))
    fill = int(round(abs(frac) * mid))
    cells = [" "] * n
    if x >= 0:
        for i in range(mid, min(n, mid + fill)):
            cells[i] = "█"
        col = C.GREEN
    else:
        for i in range(max(0, mid - fill), mid):
            cells[i] = "█"
        col = C.RED
    cells[mid] = "│" if cells[mid] == " " else cells[mid]
    clip = "▸" if abs(frac) >= 1.0 else ""
    return f"{col}{''.join(cells)}{C.RESET}{clip}"


def head(text: str) -> str:
    return f"{C.BOLD}{text}{C.RESET}"


def rule(ch: str = "─") -> str:
    return C.DIM + ch * W + C.RESET


def _days(d: dt.date, today: dt.date) -> int:
    return (d - today).days


def render(d: dict) -> str:
    """The short page, from the digest `brief.build` filled in."""
    today = d.get("today") or dt.date.today()
    now = d.get("now")
    book = d.get("book") or {"legs": [], "net_pct": None, "net_usd": None,
                             "gross": 0, "stale": 0}
    legs = book.get("legs") or []
    L = [rule("═"),
         head(f"  MORNING BRIEF  ·  {now:%a %d %b %Y  %H:%M %Z}" if now
              else "  MORNING BRIEF"),
         rule("═"), ""]

    # ── BOOK ────────────────────────────────────────────────────────────
    if not legs:
        L.append(f"  {head('BOOK')}   {C.DIM}flat — nothing to manage{C.RESET}")
    else:
        if not book.get("gross"):
            # EVERY LEG UNMARKED. `mark_book` totals only what it could price,
            # so a book with no usable marks returns +0.00% on $0 — which at a
            # glance reads as a flat, fully-priced book. It is the opposite:
            # nothing is known. Seen live on 2026-09-02 when one transient
            # quote failure blanked a single-position book. Absence of a mark
            # is not absence of movement (rule 2), and it is not zero.
            L.append(f"  {head('BOOK')}   {C.YELLOW}UNPRICED{C.RESET}   "
                     f"{C.DIM}{len(legs)} position(s), none markable — the "
                     f"total is unknown,{C.RESET}")
            L.append(f"           {C.DIM}not zero. Price by hand before "
                     f"acting.{C.RESET}")
        else:
            L.append(f"  {head('BOOK')}   {pct(book.get('net_pct'))}   "
                     f"{money(book.get('net_usd'))} on "
                     f"${book.get('gross', 0):,.0f}   "
                     f"{C.DIM}{len(legs)} position(s){C.RESET}")
        # The rows render either way. Splitting the header into two branches
        # once left them inside only one, so an unpriced book listed no
        # positions at all -- the failure hid the thing it was reporting.
        L.append("")
        for l in legs:
            settled = (d.get("settled") or {}).get(l["ticker"])
            tag = ""
            if settled and settled.get("outcome") in ("APPROVED", "REJECTED"):
                col = C.GREEN if settled["outcome"] == "APPROVED" else C.RED
                tag = f"  {col}{settled['outcome']}{C.RESET}"
            elif l.get("event_date"):
                n = _days(dt.date.fromisoformat(l["event_date"]), today)
                tag = (f"  {C.DIM}{l.get('event_kind') or 'event'} "
                       f"{'in ' + str(n) + 'd' if n > 0 else 'passed'}{C.RESET}")
            mark = f"{l['mark']:>8.2f}" if l.get("mark") is not None else \
                f"{'stale':>8}"
            L.append(f"    {l['ticker']:<6}{l['side']:<6}{l['entry_px']:>8.2f} "
                     f"→{mark}  {pct(l.get('pnl_pct'))}  "
                     f"{bar(l.get('pnl_pct'))}{tag}")
        if book.get("stale") and book.get("gross"):
            L.append(f"    {C.YELLOW}⚠ {book['stale']} leg(s) unmarked and "
                     f"EXCLUDED from the total — price by hand{C.RESET}")
    L.append("")

    # ── DO TODAY ────────────────────────────────────────────────────────
    L.append(f"  {head('DO TODAY')}")
    acted = False
    for l in d.get("closing") or []:
        settled = (d.get("settled") or {}).get(l["ticker"])
        why = l.get("exit_condition") or "exit rule reached"
        L.append(f"    {C.YELLOW}▸ EXIT {l['ticker']:<6}{C.RESET} "
                 f"{pct(l.get('pnl_pct'))}  {money(l.get('pnl_usd'))}"
                 f"   {C.DIM}{l['event_kind']} {l['event_date']}{C.RESET}")
        if settled and settled.get("outcome") in ("APPROVED", "REJECTED"):
            L.append(f"      the binary is SETTLED ({settled['outcome']}) — "
                     "the catalyst thesis is spent.")
            L.append("      What you hold is now an ordinary equity position. "
                     "Re-underwrite")
            L.append("      it on that basis or close it; there is no event "
                     "left to wait for.")
        else:
            L += _wrap(f"exit rule written at entry: {why}", 6)
        acted = True
    for l, n in d.get("upcoming") or []:
        L.append(f"    {C.YELLOW}▸ DECIDE {l['ticker']:<4}{C.RESET} enters its "
                 f"{l['event_kind']} window in {n}d ({l['event_date']}).")
        L.append("      Hold through the binary or exit before it — a decision "
                 "taken")
        L.append("      during the gap is not a decision.")
        acted = True
    note = (d.get("pair_note") or "").strip()
    if "nothing" not in note.lower():
        L += _pair_lines(d, note)
        acted = True
    else:
        # The note already begins "nothing —"; prefixing it again read
        # "nothing — nothing — engine not ready".
        L.append(f"    {C.DIM}· open    {note}{C.RESET}")
    if not acted:
        L.append(f"    {C.DIM}· nothing due. A position review and no new "
                 f"risk is a normal morning.{C.RESET}")
    L.append("")

    # ── ALSO QUALIFIED ──────────────────────────────────────────────────
    # What the engine saw and the book did not take. Shown so the reader can
    # see the whole shortlist; unsized so it cannot be mistaken for an order.
    L += _board_lines(d)

    # ── OPPORTUNITIES ───────────────────────────────────────────────────
    L += _opportunities(d)

    # ── COMING UP ───────────────────────────────────────────────────────
    cal = d.get("cal") or []
    if cal and not (d.get("ranked") or {}).get("buckets"):
        L.append(f"  {head('COMING UP')}   {C.DIM}FDA decisions "
                 f"(company-disclosed dates, no probability implied){C.RESET}")
        held = {l["ticker"] for l in legs}
        shown = 0
        for c in sorted(cal, key=lambda r: r.get("date") or "9999"):
            if not c.get("date"):
                continue
            n = _days(dt.date.fromisoformat(c["date"]), today)
            if n < 0 or shown >= 5:
                continue
            tkr = (c.get("ticker") or "").strip()
            r = (d.get("priced") or {}).get(tkr) or {}
            fv, price = r.get("fv"), r.get("put_pct")
            if not tkr:
                # A scheduled decision with no resolvable ticker cannot be
                # priced at all. Show the filer, never a blank column.
                tail = f"  {C.YELLOW}no ticker resolved{C.RESET}"
                label = (c.get("company") or "?")[:22]
            elif fv and price is not None:
                import fairvalue as F
                lab, ratio = F.verdict(price * 100, fv)
                col = (C.GREEN if lab.startswith("CHEAP") else
                       C.RED if lab.startswith("RICH") else C.DIM)
                # `~` means the long page flagged this fair value unreliable.
                # Concision may drop detail; it may not drop doubt.
                shaky = "~" if ((fv.get("cross") or {}).get("faults")) else " "
                tail = f" {col}{shaky}put {ratio:.2f}x fair{C.RESET}"
                label = tkr
            elif r.get("error"):
                tail = f"  {C.DIM}unpriced ({r['error'][:22]}){C.RESET}"
                label = tkr
            else:
                tail = f"  {C.DIM}unpriced{C.RESET}"
                label = tkr
            star = f"{C.CYAN}●{C.RESET}" if tkr and tkr in held else " "
            L.append(f"    {star} {n:>4}d  {c['date']}  {label:<7}{tail}")
            shown += 1
        if any(((d.get('priced') or {}).get((c.get('ticker') or '').strip())
                or {}).get("fv", {}) and
               (((d.get('priced') or {}).get((c.get('ticker') or '').strip())
                 or {}).get("fv") or {}).get("cross", {}).get("faults")
               for c in cal):
            L.append(f"      {C.DIM}~ fair value is indicative only — one or "
                     f"both estimators compromised{C.RESET}")
        L.append("")

    # ── WATCH ───────────────────────────────────────────────────────────
    watch = _watch(d)
    if watch:
        L.append(f"  {head('WATCH')}")
        L += watch
        L.append("")

    # ── RECORD ──────────────────────────────────────────────────────────
    L.append(f"  {head('RECORD')}   {C.DIM}printed beside the advice, "
             f"always{C.RESET}")
    L += _record(d)
    L.append("")
    L.append(rule())
    L.append(f"  {C.DIM}detail: brief.py --full   ·   after close: "
             f"ledger.py --score{C.RESET}")
    return "\n".join(L)


# The screen's verdicts are written to be read in a paragraph. In a ranked
# column they truncated mid-word ("DOWNSIDE IS THE CHEAPER SI"), so each gets a
# short tag here and keeps its full sentence in `--full`. Anything unmapped
# falls through to its own text rather than being silently blanked.
_VERDICT_TAG = {
    "DOWNSIDE IS THE CHEAPER SIDE": "downside cheaper",
    "STAND ASIDE INTO THE PRINT": "stand aside",
    "PROTECTION IS DEAR — STAND ASIDE": "protection dear",
    "NO PRICED EXPRESSION": "no expression",
    "NOT AN EVENT TRADE": "immaterial",
    "PRICING UNRELIABLE — VERIFY THE QUOTE": "quote unreliable",
    "VERDICT UNAVAILABLE": "no verdict",
}


def _opportunities(d: dict) -> list:
    """The research output, ranked by decision value rather than by date.

    WHY THIS REPLACED THE CALENDAR HERE. The short page listed the five nearest
    FDA dates, which is the order the FDA's diary has. PRAX — the cheapest name
    on the board at 0.44x quoted-to-fair — sits 118 days out and was the sixth
    row, so it never appeared at all. A page that shows the diary instead of the
    ranking hides the one thing the screen exists to produce.

    Ranked by QUOTED / MEASURED FAIR VALUE, from each name's own returns. Below
    1.0x the market is charging less than the name's own history says the
    protection is worth. That comparison is measured; whether TRADING the gap
    pays is not backtested and cannot be with free data.
    """
    rk = d.get("ranked") or {}
    buckets = rk.get("buckets") or {}
    rows = [r for hz in ("WEEK", "MONTH", "QUARTER") for r in buckets.get(hz, [])]
    if not rows:
        return []
    rows.sort(key=lambda r: r["fv_ratio"])
    shown_shaky: list = []
    d["_shown_shaky"] = shown_shaky
    out = [f"  {head('OPPORTUNITIES')}   {C.DIM}ranked by quoted ÷ measured "
           f"fair value, not by date{C.RESET}"]
    shaky = False
    for r in rows[:5]:
        fv = r["fv"]
        mark = " "
        if (fv.get("cross") or {}).get("faults"):
            mark, shaky = "~", True
        ratio = r["fv_ratio"]
        col = C.GREEN if ratio < 0.80 else (C.RED if ratio > 1.25 else C.DIM)
        raw = (r.get("verdict") or {}).get("call", "")
        call = _VERDICT_TAG.get(raw, raw.lower())
        out.append(f"    {col}{ratio:.2f}x{C.RESET} {mark}{r['ticker']:<6}"
                   f"{r['days']:>4}d {C.DIM}put{r['put_pct']*100:5.1f}%/"
                   f"fair{fv['fair']:5.1f}%{C.RESET} {call[:26]}")
        # remembered so WATCH can point at a name the reader can actually see
        shown_shaky.append(r["ticker"]) if mark == "~" else None
    # THE FOOTNOTES MUST NOT OUTGROW THE CONTENT. Four rows of ranking had
    # five rows of caveat under them, which is how a page teaches its reader to
    # skip the caveats. Everything below is one line each, and each one is
    # load-bearing: what the ratio means, why a ~ is not a price, why no long.
    tail = "<1.0x = cheaper than this name's own history says; measured, " \
           "but trading the gap is NOT backtested"
    if shaky:
        tail = "~ = estimators disagree, not a price to act on. " + tail
    out += _wrap(tail, 6, dim=True)
    try:
        import catalyst as _cat
        out += _wrap(f"no long ranked: approval edge "
                     f"+{_cat.APPROVAL_VS_RANDOM_PP:.1f}pp "
                     f"(t={_cat.APPROVAL_T:+.2f}, n={_cat.APPROVAL_N}) is under "
                     f"the pre-registered |t|>={_cat.ADOPT_T:.0f} bar", 6,
                     dim=True)
    except Exception:
        pass
    sk = rk.get("skipped") or []
    if sk:
        names = ", ".join(sorted({t for t, _ in sk}))
        out += _wrap(f"excluded, quote failed its checks: {names}", 6, dim=True)
    out.append("")
    return out


def _board_lines(d: dict) -> list:
    """Everything that QUALIFIED but is not in the book — shown, never sized.

    These are recorded in the ledger as the untraded control: they are how the
    record answers "does the traded subset beat the pool it is drawn from".
    Day-87 answered that on 34 paired sessions at -0.003%/leg, |t|=0.02 — dead
    zero — so they are printed to show what the engine saw, and deliberately
    without a share count, because a size is an instruction.
    """
    res = d.get("res") or {}
    pair = res.get("pair") or {}
    in_book = set()
    for side in ("long", "short"):
        lg = pair.get(side) or {}
        for r in ([lg.get("pick") or {}] + list(lg.get("extra") or [])):
            if r.get("t"):
                in_book.add(r["t"])
    out, any_row = [], False
    for side, key, col in (("LONG", "longs", C.GREEN),
                           ("SHORT", "shorts", C.RED)):
        rest = [r for r in (res.get(key) or []) if r.get("t") not in in_book]
        if not rest:
            continue
        any_row = True
        bits = []
        for r in rest[:6]:
            p = r.get("p_up")
            sided = (p if side == "LONG" else 1 - p) if p is not None else None
            bits.append(f"{r['t']}" + (f" {sided:.2f}" if sided else ""))
        more = f" +{len(rest) - 6} more" if len(rest) > 6 else ""
        out += _wrap(f"{col}{side:<6}{C.RESET} " + " · ".join(bits) + more, 4)
    if not any_row:
        return []
    return ([f"  {head('ALSO QUALIFIED')}   {C.DIM}recorded, NOT sized — "
             f"these are the control{C.RESET}"] + out
            + [f"    {C.DIM}trading these instead of the book measured "
               f"-0.003%/leg (|t|=0.02){C.RESET}",
               f"    {C.DIM}over 34 paired sessions — no better, and one "
               f"more spread each.{C.RESET}", ""])


def _order_tail(d: dict, res: dict, side: str, p: dict) -> str:
    """Size and fill bound for one leg, or the 9:45 price when unsized.

    Shared by the primary and the extra legs so the two can never drift into
    printing different things about the same book.
    """
    if p.get("shares") and not d.get("shadow"):
        try:
            import r945 as _r
            b = _r.fill_bound(side.upper(), p["p945"],
                              res.get("max_chase_pct", 0.04))
            return (f"{p['shares']:>5} sh  ~${p.get('alloc', 0):,.0f}"
                    f"   {C.DIM}fill "
                    f"{'≤' if side == 'long' else '≥'} {b:.2f}{C.RESET}")
        except Exception:
            return f"{p['shares']:>5} sh"
    return f"  {C.DIM}9:45 ${p.get('p945', 0):.2f}{C.RESET}"


def _pair_lines(d: dict, note: str) -> list:
    """The pair as an ORDER, plus what it costs to express.

    The first version of this view printed `OPEN SU.TO, BMO.TO` — no side, no
    size, no fill bound. The one line that asks for an action has to carry the
    action, or it is a headline pretending to be an instruction.

    And it carries the cost. The engine's directional edge is measured at zero,
    so the spread is not a fee deducted from an expectation — it IS the
    expectation, and a BUY printed without it reads far better than it is.
    """
    res = d.get("res") or {}
    pair = res.get("pair") or {}
    out = []
    st = d.get("publish") or {}
    if st.get("already"):
        # The board is the 9:46 instruction; a later run is reading it back,
        # not issuing a new one. Saying so is the difference between an order
        # and a reminder.
        exact = "exact" in str(st.get("restore_note", ""))
        out.append(f"    {C.DIM}· re-read of the 9:46 board"
                   + ("" if exact else " (sizes re-derived, ±1 sh)")
                   + f"{C.RESET}")
    for side in ("long", "short"):
        lg = pair.get(side) or {}
        p = lg.get("pick") or {}
        if not p.get("t"):
            out.append(f"    {C.DIM}· {side.upper():<5} none qualified — "
                       f"not forced{C.RESET}")
            continue
        verb = "BUY " if side == "long" else "SHORT"
        col = C.GREEN if side == "long" else C.RED
        line = (f"    {col}▸ {verb} {p['t']:<8}{C.RESET}")
        if p.get("shares") is None and st.get("already"):
            # Blank, never a re-computation. A size that differs from the one
            # the ledger scores is worse than no size at all.
            out.append(line + f"  {C.YELLOW}size not restorable from the "
                              f"published board — do not size from here"
                              f"{C.RESET}")
            continue
        out.append(line + _order_tail(d, res, side, p))
        # THE EXTRA LEGS. Day-31 adopted legs_per_side=2 and these are SIZED,
        # PUBLISHED and SCORED exactly like the primary — `r945 --book` has
        # always printed them. This page did not read `extra` at all between
        # day-81 and day-87, so it showed a one-leg-a-side book while the
        # ledger recorded two. Concision may drop detail; it may not drop
        # half the order.
        for x in (lg.get("extra") or []):
            if not x.get("t"):
                continue
            xline = f"    {col}▸ {verb} {x['t']:<8}{C.RESET}"
            out.append(xline + _order_tail(d, res, side, x))
    # The whole expected outcome, in one line.
    rows = d.get("cost") or []
    known = [r for r in rows if (r.get("cost") or {}).get("usd")]
    if known:
        total = sum(r["cost"]["usd"] for r in known)
        stale = False
        try:
            import cost as _ck
            stale = _ck.outside_trading_hours(d.get("now"))
        except Exception:
            stale = False
        if stale:
            # A post-close bid/ask is not a tradeable spread. Say so rather
            # than printing a number four times the morning's.
            out.append(f"      {C.YELLOW}spread not live — outside trading "
                       f"hours{C.RESET}{C.DIM}; the ~${total:,.0f} below is"
                       f"{C.RESET}")
            out.append(f"      {C.DIM}last posted bid/ask, which is far wider "
                       f"than the 9:46 quote.{C.RESET}")
        out.append(f"      {C.YELLOW}starts ~${total:,.0f} behind on spread"
                   f"{C.RESET}{C.DIM} — the edge is zero, so this{C.RESET}")
        out.append(f"      {C.DIM}is not a cost on top of the edge, it IS "
                   f"the expectation.{C.RESET}")
    elif rows:
        out.append(f"      {C.YELLOW}⚠ spread unknown on one or both legs — "
                   f"not zero, unknown{C.RESET}")
    return out


def _watch(d: dict) -> list:
    """Only things that changed, broke, or disagree. Never a status recital."""
    out = []
    for t, e in (d.get("mark_errors") or {}).items():
        out.append(f"    {C.YELLOW}⚠{C.RESET} {t} could not be marked ({e})")

    # unpriced calendar names — absence of a quote is not absence of risk
    cal = d.get("cal") or []
    priced = d.get("priced") or {}
    noticker = [c for c in cal if not (c.get("ticker") or "").strip()]
    unp = sorted({(c.get("ticker") or "").strip() for c in cal
                  if (c.get("ticker") or "").strip()
                  and not (priced.get((c["ticker"]).strip()) or {}).get("fv")})
    if noticker:
        names = ", ".join(sorted({(c.get("company") or "?")[:26]
                                  for c in noticker}))
        out.append(f"    {C.YELLOW}⚠{C.RESET} {len(noticker)} scheduled "
                   f"decision(s) with NO ticker — unpriceable:")
        out += _wrap(names, 6, dim=True)
    # IS THIS ABOUT THE NAMES, OR ABOUT THE FEED? Run before the options market
    # opens, every check fails for every name AND for SPY, whose ATM put quotes
    # 0.00/0.00. Printing that as "N names failed their checks" told the PM half
    # the calendar was illiquid when the market was shut. quotes.py prices a
    # control first so the two can be told apart.
    feed_live = next((r.get("feed_live") for r in priced.values()
                      if r.get("feed_live") is not None), None)
    if unp and feed_live is False:
        out.append(f"    {C.YELLOW}⚠ OPTIONS FEED NOT LIVE{C.RESET} — "
                   f"{len(unp)} name(s) unpriced for that reason alone")
        out += _wrap("the control (SPY) has no two-sided quote either, so "
                     "nothing here says a name is illiquid. Re-run in market "
                     "hours.", 6, dim=True)
    elif unp:
        # Group by the TYPED reason. "failed its checks" was one sentence for
        # six distinct causes, and the reader could act on none of them.
        by: dict = {}
        for t in unp:
            r = priced.get(t) or {}
            by.setdefault(r.get("reason_why") or "quote failed its checks",
                          []).append(t)
        out.append(f"    {C.YELLOW}⚠{C.RESET} {len(unp)} calendar name(s) "
                   f"unpriced:")
        for why, names in sorted(by.items()):
            shown, extra = sorted(names)[:6], max(0, len(names) - 6)
            txt = (", ".join(shown) + (f" +{extra} more" if extra else "")
                   + f" — {why}")
            out += _wrap(txt, 6, dim=True)

    # The `~` in OPPORTUNITIES already carries this per name. Repeating the
    # roster here was five lines saying what one mark says, and repetition is
    # what pushed the things that differ off the screen in the first place.
    shaky = sorted(t for t, r in priced.items()
                   if (((r.get("fv") or {}).get("cross")) or {}).get("faults"))
    # Point at a name the reader can SEE marked. Falling back to the full
    # shaky roster printed the hint on a page with no ~ anywhere -- when the
    # feed is down nothing is ranked, so nothing carries the mark it explains.
    seen = d.get("_shown_shaky") or []
    if seen:
        out.append(f"      {C.DIM}why a name is marked ~: "
                   f"`python fairvalue.py {seen[0]} --days 60`{C.RESET}")

    # constants that moved, and contradictions between published numbers
    try:
        import constants as K
        now, snap = K.live(), K.load()
        dr = K.drift(now, snap)
        for k, old, new in dr["changed"]:
            out.append(f"    {C.RED}⚠ MOVED{C.RESET} {k}: {old!r} → {new!r}")
        for k, e in dr["broken"]:
            out.append(f"    {C.RED}⚠ BROKEN{C.RESET} {k}: {e}")
        # A STANDING contradiction, not news. Printed in full every morning it
        # becomes wallpaper and stops being read, which is how the long page
        # lost its caveats. Two lines and a command that prints the reasoning.
        for what, _why, short in K.tensions():
            # WRAPPED. A fixed header assumed a short name; "typical
            # intraday move" pushed it to 81 columns and broke the layout the
            # width test exists to protect.
            out += _wrap(f"⚠ {what}: two published numbers disagree, both "
                         f"reach this page", 4)
            out += _wrap(f"{short}; never mix them (`python constants.py`)",
                         6, dim=True)
    except Exception as e:                       # never silently (rule 1)
        out.append(f"    {C.RED}⚠{C.RESET} constants check failed: "
                   f"{type(e).__name__}: {e}")
    return out


def _record(d: dict) -> list:
    rows = d.get("ledger_rows") or []
    done = [r for r in rows if r.get("hit") not in ("", None)]
    pair = [r for r in done if r.get("role") == "pair"]
    out = []
    if pair:
        hits = sum(int(r["hit"]) for r in pair)
        rate = hits / len(pair) * 100
        col = C.RED if rate < 50 else C.GREEN
        out.append(f"    intraday pair  {col}{hits}/{len(pair)} "
                   f"({rate:.0f}%){C.RESET}   "
                   f"{C.DIM}a coin flip, and expected to stay one{C.RESET}")
        # Never the hit rate alone (ACCURACY.md §2).
        try:
            import ledger as _lg
            a = _lg.accuracy(pair)
            if a["mean"] is not None:
                # A 4-leg net figure printed to three decimals beside a
                # 105-leg gross one reads as though the book were up. Say how
                # thin it is, in the same breath as the number.
                if a["net_mean"] is None:
                    net = (f"net n/a ({a['net_unpriced']} legs predate the "
                           f"spread column)")
                elif a["net_n"] < NET_MIN_LEGS:
                    net = (f"net {a['net_mean']:+.2f}% on {a['net_n']} legs "
                           f"— too few to read")
                else:
                    net = f"net {a['net_mean']:+.3f}% on {a['net_n']}"
                out.append(f"    {C.DIM}mean {a['mean']:+.3f}%/leg  ·  {net}"
                           f"{C.RESET}")
        except Exception as e:
            out.append(f"    {C.YELLOW}⚠ accuracy unavailable "
                       f"({type(e).__name__}){C.RESET}")
        try:
            import ledger
            # From the digest: computed once by build(), never re-downloaded.
            tides = d.get("tides")
            if tides:
                a = ledger.attribution_line(pair, tides)
                # Pull the two numbers out rather than reprinting the sentence:
                # TIDE is market exposure (target ~0), SELECTION is the picks.
                import re
                tide = re.search(r"TIDE\s*([+-][\d.]+)%", a)
                sel = re.search(r"SELECTION\s*([+-][\d.]+)%", a)
                if tide and sel:
                    s = float(sel.group(1))
                    col = C.RED if s < 0 else C.GREEN
                    out.append(f"    of which  tide {tide.group(1)}%"
                               f"  ·  {col}selection {sel.group(1)}%"
                               f"{C.RESET} {C.DIM}/session (the picks)"
                               f"{C.RESET}")
        except Exception as e:
            out.append(f"    {C.DIM}attribution unavailable "
                       f"({type(e).__name__}){C.RESET}")
    else:
        out.append(f"    {C.DIM}no scored pair legs yet{C.RESET}")
    if d.get("scored_now"):
        out.append(f"    {C.DIM}+{d['scored_now']} leg(s) scored this morning "
                   f"from the previous session{C.RESET}")
    if d.get("held_back"):
        out.append(f"    {C.DIM}{d['held_back']} held back — their session has "
                   f"not closed{C.RESET}")
    if d.get("score_error"):
        out.append(f"    {C.YELLOW}⚠ scoring failed ({d['score_error']}) — the "
                   f"record below is STALE{C.RESET}")
    try:
        import advice as A
        rec = A.report(A.load()).split("\n")
        hit = next((x for x in rec if "directional advice scored" in x), None)
        out.append("    " + (hit.strip() if hit else
                             C.DIM + "advice record: nothing scored yet" +
                             C.RESET))
    except Exception:
        pass
    return out


def _wrap(text: str, indent: int, width: int = None, dim: bool = False) -> list:
    """Wrapped, with CONTINUATION lines indented past the first.

    Every line used the same pad, so a wrapped warning read as two separate
    bullets at the same level:

        ⚠ P(rejection): two published numbers disagree, both reach
        this page

    which is a layout that hides where one item ends and the next begins.
    """
    import textwrap
    width = width or (W - indent)
    pad, cont = " " * indent, " " * (indent + 2)
    lines = textwrap.wrap(text, width=width) or [text]
    out = [pad + lines[0]] + [cont + x for x in lines[1:]]
    return [(C.DIM if dim else "") + x + (C.RESET if dim else "") for x in out]
