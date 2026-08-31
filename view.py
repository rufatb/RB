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
    if legs:
        L.append(f"  {head('BOOK')}   {pct(book.get('net_pct'))}   "
                 f"{money(book.get('net_usd'))} on "
                 f"${book.get('gross', 0):,.0f}   "
                 f"{C.DIM}{len(legs)} position(s){C.RESET}")
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
        if book.get("stale"):
            L.append(f"    {C.YELLOW}⚠ {book['stale']} leg(s) unmarked and "
                     f"EXCLUDED from the total — price by hand{C.RESET}")
    else:
        L.append(f"  {head('BOOK')}   {C.DIM}flat — nothing to manage{C.RESET}")
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

    # ── COMING UP ───────────────────────────────────────────────────────
    cal = d.get("cal") or []
    if cal:
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
    L.append(f"  {C.DIM}full page: python brief.py --full   ·   "
             f"score after close: python ledger.py --score{C.RESET}")
    return "\n".join(L)


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
        out += _wrap("· re-read of the board published at 9:46 — "
                     + str(st.get("restore_note", "restore status unknown")),
                     4, dim=True)
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
        if p.get("shares") and not d.get("shadow"):
            try:
                import r945 as _r
                b = _r.fill_bound(side.upper(), p["p945"],
                                  res.get("max_chase_pct", 0.04))
                line += (f"{p['shares']:>5} sh  ~${p.get('alloc', 0):,.0f}"
                         f"   {C.DIM}fill "
                         f"{'≤' if side == 'long' else '≥'} "
                         f"{b:.2f}{C.RESET}")
            except Exception:
                line += f"{p['shares']:>5} sh"
        else:
            line += f"  {C.DIM}9:45 ${p.get('p945', 0):.2f}{C.RESET}"
        out.append(line)
    # The whole expected outcome, in one line.
    rows = d.get("cost") or []
    known = [r for r in rows if (r.get("cost") or {}).get("usd")]
    if known:
        total = sum(r["cost"]["usd"] for r in known)
        out.append(f"      {C.YELLOW}this pair starts ~${total:,.0f} behind "
                   f"before the market moves{C.RESET} — the engine's edge is")
        out.append("      measured at zero, so the spread is not a cost on top "
                   "of the edge, it IS")
        out.append("      the outcome. Arithmetic, not a forecast.")
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
                   f"decision(s) with NO ticker resolved — cannot be priced "
                   f"at all")
        out.append(f"      {C.DIM}{names}{C.RESET}")
    if unp:
        out.append(f"    {C.YELLOW}⚠{C.RESET} {len(unp)} calendar name(s) "
                   f"unpriced — options quotes failed their checks: "
                   f"{', '.join(unp[:6])}")

    # Fair values the long page flagged unreliable. ONE line, not one per name:
    # five identical warnings push the things that differ off the screen, and a
    # section nobody finishes reading is the failure this view exists to fix.
    shaky = sorted(t for t, r in priced.items()
                   if (((r.get("fv") or {}).get("cross")) or {}).get("faults"))
    if shaky:
        out.append(f"    {C.YELLOW}⚠{C.RESET} fair value indicative only "
                   f"(marked ~ above): {', '.join(shaky)}")
        out.append(f"      {C.DIM}run `python fairvalue.py TKR --days N` for "
                   f"which estimator is compromised and why{C.RESET}")

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
            out.append(f"    {C.YELLOW}⚠{C.RESET} {what}: two published "
                       f"numbers disagree and BOTH reach this page")
            out += _wrap(f"{short}. Do not mix them in one argument — "
                         "`python constants.py` for the reasoning.",
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
        try:
            import ledger
            tides = ledger._tides_for_report()
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
                    out.append(f"    of which  tide {tide.group(1)}%/session"
                               f"  ·  {col}selection {sel.group(1)}%/session"
                               f"{C.RESET}  {C.DIM}(the picks){C.RESET}")
        except Exception as e:
            out.append(f"    {C.DIM}attribution unavailable "
                       f"({type(e).__name__}){C.RESET}")
    else:
        out.append(f"    {C.DIM}no scored pair legs yet{C.RESET}")
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
    import textwrap
    width = width or (W - indent)
    pad = " " * indent
    lines = textwrap.wrap(text, width=width) or [text]
    return [(C.DIM if dim else "") + pad + x + (C.RESET if dim else "")
            for x in lines]
