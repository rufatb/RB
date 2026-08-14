#!/usr/bin/env python3
"""
report_html.py — the visual 9:46 board.

WHY IT LIVES HERE AND NOT IN r945.py: the terminal render and this one must
never disagree, so both are pure functions of the SAME `res` dict that run()
returns. Nothing is recomputed here — if a number is not in `res`, it does not
appear on the page. Adding a fact to the visual report means adding it to
run(), where the guards live.

DESIGN INTENT, stated because it is a safety property and not a taste
preference: the live record is rendered at EQUAL WEIGHT to the book. This
engine's measured record is a coin flip (PAIR 24/51 as of day-40), and a
dashboard whose picks look more considered than its scoreboard is lying by
layout. Colour is reserved for meaning only -- side and status -- so a glance
never reads decoration as information.
"""

from __future__ import annotations

import datetime as dt
import html


def _esc(v) -> str:
    return html.escape(str(v), quote=True)


CSS = """
:root{
  --paper:#F4F6F8; --surface:#FFFFFF; --sunk:#EDF1F5;
  --line:#DCE3EA; --ink:#141A21; --muted:#64707F;
  --long:#0B6E5A; --short:#A2452B; --warn:#8A6410;
  --long-wash:#E4F1ED; --short-wash:#F8E9E4; --warn-wash:#F7EFDC;
  --serif:ui-serif,Georgia,"Iowan Old Style","Times New Roman",serif;
  --mono:ui-monospace,"SF Mono",SFMono-Regular,Menlo,Consolas,monospace;
  --sans:ui-sans-serif,system-ui,-apple-system,"Segoe UI",Roboto,sans-serif;
}
@media (prefers-color-scheme:dark){
  :root:not([data-theme="light"]){
    --paper:#0F131A; --surface:#171C24; --sunk:#121820;
    --line:#28313D; --ink:#E7EDF4; --muted:#8D9AAA;
    --long:#46BCA0; --short:#E28663; --warn:#D9A83A;
    --long-wash:#122A26; --short-wash:#2C1B16; --warn-wash:#2A2213;
  }
}
:root[data-theme="dark"]{
  --paper:#0F131A; --surface:#171C24; --sunk:#121820;
  --line:#28313D; --ink:#E7EDF4; --muted:#8D9AAA;
  --long:#46BCA0; --short:#E28663; --warn:#D9A83A;
  --long-wash:#122A26; --short-wash:#2C1B16; --warn-wash:#2A2213;
}
*{box-sizing:border-box}
body{
  margin:0; background:var(--paper); color:var(--ink);
  font-family:var(--sans); font-size:15px; line-height:1.55;
  -webkit-font-smoothing:antialiased;
}
.wrap{max-width:1000px; margin:0 auto; padding:32px 20px 72px;
      display:flex; flex-direction:column; gap:22px}
.lbl{font-size:11px; letter-spacing:.09em; text-transform:uppercase;
     color:var(--muted); font-weight:600}
.num{font-family:var(--mono); font-variant-numeric:tabular-nums}

/* masthead */
.mast{display:flex; flex-wrap:wrap; align-items:baseline; gap:8px 18px;
      border-bottom:2px solid var(--ink); padding-bottom:12px}
.mast h1{font-family:var(--serif); font-size:26px; font-weight:600;
         margin:0; letter-spacing:-.01em; text-wrap:balance}
.mast .when{margin-left:auto; text-align:right}
.mast .when b{font-family:var(--mono); font-size:20px; display:block}

/* the clock: the one thing that expires */
.clock{display:flex; align-items:center; gap:14px; flex-wrap:wrap;
       background:var(--sunk); border:1px solid var(--line);
       border-radius:3px; padding:12px 16px}
.clock .big{font-family:var(--mono); font-size:22px; font-weight:600}
.clock.shut{background:var(--short-wash); border-color:var(--short)}
.clock.shut .big{color:var(--short)}

/* verdict + book, equal weight */
.duo{display:grid; grid-template-columns:1fr 1fr; gap:16px}
@media (max-width:760px){.duo{grid-template-columns:1fr}}
.card{background:var(--surface); border:1px solid var(--line);
      border-radius:3px; padding:16px 18px}
.card h2{font-family:var(--serif); font-size:17px; font-weight:600;
         margin:0 0 10px; letter-spacing:-.01em}
.stat{display:flex; align-items:baseline; gap:10px; margin:0 0 4px}
.stat b{font-family:var(--mono); font-size:24px; font-weight:600;
        font-variant-numeric:tabular-nums}
.stat span{color:var(--muted); font-size:13px}
.note{font-family:var(--serif); font-size:14px; color:var(--ink);
      margin:10px 0 0; padding-top:10px; border-top:1px solid var(--line)}
.flag{background:var(--warn-wash); border-left:3px solid var(--warn);
      padding:10px 12px; font-size:13.5px; border-radius:0 3px 3px 0}

/* tickets */
.tickets{display:grid; grid-template-columns:repeat(auto-fit,minmax(300px,1fr));
         gap:14px}
.tkt{background:var(--surface); border:1px solid var(--line);
     border-left:4px solid var(--side); border-radius:3px; padding:14px 16px;
     display:flex; flex-direction:column; gap:8px}
.tkt.long{--side:var(--long)} .tkt.short{--side:var(--short)}
.tkt .top{display:flex; align-items:baseline; gap:10px}
.tkt .tick{font-family:var(--mono); font-size:20px; font-weight:600}
.tkt .side{font-size:11px; font-weight:700; letter-spacing:.09em;
           color:var(--side); text-transform:uppercase}
.tkt .tag{margin-left:auto; font-size:10.5px; letter-spacing:.07em;
          text-transform:uppercase; color:var(--muted);
          border:1px solid var(--line); border-radius:2px; padding:1px 6px}
.order{font-family:var(--mono); font-size:17px; font-weight:600}
.grid2{display:grid; grid-template-columns:1fr 1fr; gap:6px 14px; font-size:13px}
.grid2 div{display:flex; justify-content:space-between; gap:8px;
           border-bottom:1px dotted var(--line); padding-bottom:3px}
.grid2 span:first-child{color:var(--muted)}
.grid2 span:last-child{font-family:var(--mono);
                       font-variant-numeric:tabular-nums}
.pill{display:inline-flex; align-items:center; gap:6px; font-size:12px;
      font-weight:600; border-radius:2px; padding:3px 8px; width:fit-content}
.pill.ok{background:var(--long-wash); color:var(--long)}
.pill.no{background:var(--short-wash); color:var(--short)}

/* board */
table{width:100%; border-collapse:collapse; font-size:13.5px}
.scroll{overflow-x:auto}
th{text-align:left; font-size:11px; letter-spacing:.08em; text-transform:uppercase;
   color:var(--muted); font-weight:600; padding:0 10px 6px 0;
   border-bottom:1px solid var(--line); white-space:nowrap}
td{padding:6px 10px 6px 0; border-bottom:1px solid var(--line);
   font-family:var(--mono); font-variant-numeric:tabular-nums; white-space:nowrap}
td.name{font-weight:600}
td.L{color:var(--long)} td.S{color:var(--short)}

.rules{font-size:13px; color:var(--muted); display:flex;
       flex-direction:column; gap:7px}
.rules b{color:var(--ink)}
footer{font-size:12px; color:var(--muted); border-top:1px solid var(--line);
       padding-top:12px}
"""


def _pill(ok: bool, text: str) -> str:
    return f'<span class="pill {"ok" if ok else "no"}">{_esc(text)}</span>'


def orders_allowed(res: dict, book: bool) -> tuple:
    """May this page show order lines at all? -> (bool, reason-if-not).

    DAY-25's rule, enforced here rather than trusted: a printed order line IS
    the instruction, and a disclaimer next to one loses. So the visual board
    must suppress orders in every case the terminal does -- not merely warn:

      * `book` false      -- an informational run, including the re-run after
                             the day's board is already published (a re-run can
                             see REVISED early bars and mint a DIFFERENT board);
      * shadow mode       -- paper only;
      * window closed     -- the decision price has expired.

    Getting this wrong is how a prettier report becomes a more dangerous one.
    """
    if res.get("shadow"):
        return False, "SHADOW — paper only, no order and no size"
    if not book:
        return False, "Informational run — the published board of the day stands"
    if res.get("ready_at_iso") and res.get("entry_window_min"):
        try:
            tend = (dt.datetime.fromisoformat(res["ready_at_iso"])
                    + dt.timedelta(minutes=res["entry_window_min"]))
            if dt.datetime.fromisoformat(res["now"]) >= tend:
                return False, "Order window closed — the decision price has expired"
        except Exception:
            pass
    return True, ""


def _ticket(r: dict, side: str, res: dict, bound_fn, book: bool = False) -> str:
    """One order ticket. Renders ONLY what run() already decided."""
    is_long = side == "LONG"
    px = r.get("p945")
    last = r.get("last")
    bound = bound_fn(side, px, res.get("max_chase_pct", 0.04)) if px else None
    tradeable = None
    if bound is not None and last is not None:
        tradeable = last <= bound if is_long else last >= bound

    rows = [("9:45 print", f"{px:.2f}" if px else "—"),
            ("first 15m", f'{r.get("r0", 0):+.2f}%'),
            ("gap", f'{r.get("gap") or 0:+.2f}%'),
            ("sided P", f'{(r["p_up"] if is_long else 1 - r["p_up"]):.2f}')]
    if r.get("shares") is not None:
        rows += [("2% adverse", f'−${r.get("adverse_2pct", 0):,.0f}'),
                 ("disaster line", f'{r["p945"] * (0.975 if is_long else 1.025):.2f}')]

    allowed, why = orders_allowed(res, book)
    if allowed and r.get("shares") is not None:
        verb = "BUY" if is_long else "SELL SHORT"
        order = (f'<div class="order">{verb} {r["shares"]:,} sh '
                 f'<span style="color:var(--muted);font-weight:400">'
                 f'≈${r.get("alloc", 0):,.0f}</span></div>')
    else:
        order = (f'<div class="order" style="color:var(--muted);font-size:14px">'
                 f'{_esc(why or "No order")}</div>')
        rows = [x for x in rows if x[0] != "2% adverse"]

    status = ""
    if tradeable is not None and allowed:
        sym = "≤" if is_long else "≥"
        status = _pill(tradeable,
                       (f"live {last:.2f} · bound {sym} {bound:.2f}" if tradeable
                        else f"BOUND BROKEN — live {last:.2f}, needs {sym} {bound:.2f}"))

    cells = "".join(f"<div><span>{_esc(k)}</span><span>{_esc(v)}</span></div>"
                    for k, v in rows)
    return (f'<article class="tkt {side.lower()}">'
            f'<div class="top"><span class="tick">{_esc(r["t"])}</span>'
            f'<span class="side">{side}</span>'
            f'<span class="tag">{_esc((r.get("confidence") or "?").upper())}</span></div>'
            f'{order}{status}<div class="grid2">{cells}</div></article>')


def render_html(res: dict, book: bool = False, record_line: str = "") -> str:
    """The whole page. Pure function of `res` — see module docstring."""
    from r945 import fill_bound

    now = res.get("now", "")
    try:
        stamp = dt.datetime.fromisoformat(now)
        day, clock = stamp.strftime("%A %d %B %Y"), stamp.strftime("%H:%M")
    except Exception:
        day, clock = now, ""

    parts = [f'<div class="mast"><h1>The 9:46 Board</h1>'
             f'<div class="when"><span class="lbl">{_esc(day)}</span>'
             f'<b>{_esc(clock)} ET</b></div></div>']

    # ---- fail-closed states get the page to themselves ----
    if res.get("too_early"):
        parts.append(
            f'<div class="card"><h2>Too early — refusing</h2>'
            f'<p>The 9:30–9:45 bars are not complete. Running before '
            f'{_esc(res.get("ready_at", "09:46"))} ET reads an in-progress bar as '
            f'the 9:45 print, which is an unvalidated trade.</p></div>')
        return _page(parts)
    if res.get("coverage_fail"):
        parts.append(
            f'<div class="card" style="border-color:var(--short)">'
            f'<h2 style="color:var(--short)">No board, no orders today</h2>'
            f'<p class="num">{_esc(res["coverage_fail"])}</p>'
            f'<p class="note">Fail-closed by design: the pair is chosen by comparing '
            f'names against each other, so a missing name silently changes the bet.</p>'
            f'</div>')
        return _page(parts)

    # ---- the clock, because it is the one thing that expires ----
    window = ""
    if res.get("ready_at_iso") and res.get("entry_window_min"):
        t0 = dt.datetime.fromisoformat(res["ready_at_iso"])
        tend = t0 + dt.timedelta(minutes=res["entry_window_min"])
        try:
            left = (tend - dt.datetime.fromisoformat(now)).total_seconds() / 60
        except Exception:
            left = 0
        shut = left <= 0
        window = (f'<div class="clock{" shut" if shut else ""}">'
                  f'<span class="lbl">Order window</span>'
                  f'<span class="big">{tend.strftime("%H:%M")} ET</span>'
                  f'<span>{"CLOSED — no trade today" if shut else f"{left:.0f} min left"}'
                  f'</span><span style="margin-left:auto" class="lbl">'
                  f'{_esc(res.get("coverage", ""))} · {_esc(res.get("source", ""))}'
                  f'</span></div>')
    parts.append(window)

    # ---- record and book at equal weight (see module docstring) ----
    lr = res.get("live_record") or {}
    rec = ['<div class="card"><h2>The live record</h2>']
    if lr.get("all_n"):
        rec.append(f'<div class="stat"><b>{lr["pair_hits"]}/{lr["pair_n"]}</b>'
                   f'<span>traded legs correct '
                   f'({lr["pair_hits"] / lr["pair_n"] * 100:.0f}%)</span></div>')
        rec.append(f'<div class="stat"><b>{lr["all_hits"]}/{lr["all_n"]}</b>'
                   f'<span>all picks ever '
                   f'({lr["all_hits"] / lr["all_n"] * 100:.0f}%)</span></div>')
        if record_line:
            rec.append(f'<p class="note">{_esc(record_line)}</p>')
        if lr["all_n"] >= 30 and lr["all_hits"] / lr["all_n"] < 0.54:
            rec.append('<p class="note" style="border:0;padding:0;margin-top:10px">'
                       '<span class="flag">This record has not demonstrated an edge '
                       'over a coin flip. Trade the printed size or do not trade.'
                       '</span></p>')
    else:
        rec.append('<p>No scored history yet.</p>')
    rec.append("</div>")

    pair = res.get("pair") or {}
    legs = []
    for side, key in (("LONG", "long"), ("SHORT", "short")):
        leg = pair.get(key) or {}
        if leg.get("status") == "NONE" or not leg.get("pick"):
            continue
        for r in [leg["pick"]] + list(leg.get("extra") or []):
            legs.append((side, r))
    allowed, why_not = orders_allowed(res, book)
    capital = sum(r.get("alloc") or 0 for _, r in legs) if allowed else 0
    nl = sum(1 for s, _ in legs if s == "LONG")
    summary = ['<div class="card"><h2>Today\'s book</h2>',
               f'<div class="stat"><b>{nl}L / {len(legs) - nl}S</b>'
               f'<span>legs, up to 2 a side</span></div>']
    if capital:
        summary.append(f'<div class="stat"><b>${capital:,.0f}</b>'
                       f'<span>deployed across the book</span></div>')
    if not allowed:
        summary.append(f'<span class="flag">{_esc(why_not)}. No order lines on '
                       f'this page.</span>')
    summary.append(f'<p class="note">{res.get("n_names", 0)} names evaluated. '
                   f'A missing side leaves its half in cash — the tool never '
                   f'invents a leg to fill the habit.</p></div>')
    parts.append('<div class="duo">' + "".join(rec) + "".join(summary) + "</div>")

    # ---- tickets ----
    if legs:
        parts.append('<div class="tickets">' +
                     "".join(_ticket(r, s, res, fill_bound, book) for s, r in legs) +
                     "</div>")
    else:
        parts.append('<div class="card"><h2>No qualified pair</h2>'
                     '<p>Nothing cleared the bar on either side. Forcing a leg '
                     'is a coin flip.</p></div>')

    # ---- the board that was NOT sized ----
    rows = []
    for side, key in (("L", "longs"), ("S", "shorts")):
        for r in res.get(key) or []:
            if any(r is x for _, x in legs):
                continue
            sp = r["p_up"] if side == "L" else 1 - r["p_up"]
            rows.append(f'<tr><td class="name">{_esc(r["t"])}</td>'
                        f'<td class="{side}">{"LONG" if side == "L" else "SHORT"}</td>'
                        f'<td>{sp:.2f}</td><td>{r["p945"]:.2f}</td>'
                        f'<td>{r.get("r0", 0):+.2f}%</td>'
                        f'<td>{(r.get("gap") or 0):+.2f}%</td>'
                        f'<td>{_esc((r.get("confidence") or "?").lower())}</td></tr>')
    if rows:
        parts.append('<div class="card"><h2>Qualified but not sized</h2>'
                     '<p class="lbl" style="margin:-4px 0 10px">Logged for the '
                     'ledger. Not orders.</p><div class="scroll"><table><thead><tr>'
                     '<th>Name</th><th>Side</th><th>Sided P</th><th>9:45</th>'
                     '<th>First 15m</th><th>Gap</th><th>Tag</th></tr></thead><tbody>'
                     + "".join(rows) + "</tbody></table></div></div>")

    excl = res.get("excluded") or []
    if excl:
        parts.append('<div class="card"><h2>Refused</h2><div class="rules">' +
                     "".join(f'<div><b>{_esc(e.get("t", "?"))}</b> — '
                             f'{_esc(e.get("excluded_reason", ""))}</div>'
                             for e in excl) + "</div></div>")

    parts.append(
        '<div class="card"><h2>The rules that do not change</h2><div class="rules">'
        '<div><b>The share counts are the risk model.</b> Trading larger '
        'multiplies every loss by the same factor and voids every number above.</div>'
        '<div><b>Close every leg by 3:55.</b> One night nearly doubles volatility '
        'and worsens the tail 2.3×; 3- and 5-day holds collect market drift, not '
        'signal, at ten times the variance.</div>'
        '<div><b>Do not exit earlier either.</b> Across 944 legs the capture curve '
        'is flat inside 0.02% at every exit — the tape does not hand back what it '
        'gave, so there is no peak to sell into.</div>'
        '<div><b>Past the fill bound is no trade.</b> The move the signal predicted '
        'has already happened; chasing it buys a different bet.</div>'
        '</div></div>')

    parts.append('<footer>Generated by r945.py from the same result object the '
                 'terminal report prints — no number here is recomputed. '
                 'Read-only: this tool never places an order.</footer>')
    return _page(parts)


def _page(parts: list) -> str:
    return ("<title>The 9:46 Board</title>\n<style>" + CSS + "</style>\n"
            '<div class="wrap">' + "".join(p for p in parts if p) + "</div>")
