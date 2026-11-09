# Day-148 — a council veto: do the positions two members object to do worse? (council lab item 11)

**Registered 2026-11-09, before any return split by objections was computed.**
Nothing here changes a live pick, a size, the Top 2, a prompt or the email.

## Why

* Since day-144 the council votes on Claude's picks and cannot replace them.
* On 11-06 three of four members objected to Claude's long ENB.TO, and it
  was printed anyway.
* A remove-only veto would pass over a pick that two or more members object
  to. Before it could be proposed, the record has to show that objections
  sort positions at all.
* **What is already known.**
  * The council's own choice adds nothing over its table (day-137;
    M1 forward, picks minus table −0.44% a session, t = −1.90).
  * Positions every member endorsed did worse than the rest (day-137,
    −1.09% on 6 of 17; M1 forward −0.82% against +0.22%, t = −2.26). That
    leans against the idea that the members' agreement means anything good.

## Not blind (stated before the look)

* Day-137 (`AUDIT_day137_council.md`) reported, for 10-05 → 10-21, the
  positions with **at least one** objection: 51, 26 right, +0.17% raw. The
  two-objection split was not computed.
* The evening reviews print every table position's result each day, without
  its objections.
* 11-06's LONG ENB.TO, with three objections, finished +0.44%.
* The threshold (two objections), the measure and the bar are fixed here,
  before any two-objection split is computed.

## The population (pinned in `data/veto_day148_positions.json`)

* Every council position with a surviving tally, 23 sessions:
  * 10-05 → 10-21 (12 sessions, 108 positions): the frozen tables day-137
    read, kept in `data/council_audit_day137.json`;
  * 10-26 → 11-09 (11 sessions, 131 positions): the frozen reports in
    `.rb-state/reports.sqlite3`.
  * 10-22 and 10-23 were lost in the 10-25 container reset.
* **Vetoed:** two or more objections. 106 positions; every session has both
  groups. 13 positions come from councils that sat with three members.
* The pin holds tallies only (session, ticker, side, objections,
  endorsements, members, whether Claude proposed it, the council's pick, the
  printed Top 2). No return is stored in it.

## The measure

* y = side × (the position's return − XIU.TO's return), in %, from FMP
  five-minute bars: entry the close of the 09:40 bar (the 09:45 price), exit
  the close of the 15:55 bar, both for the stock and for XIU that session.
* A position whose bars are missing is left out and counted, never filled.
* Per session: D = the mean y of the rest − the mean y of the vetoed.

## The bar (day-145's machinery, seed 148)

* **VETO_SORTS** needs all of:
  * the mean of D over the sessions > 0, with t ≥ 3 over the session means;
  * a sign-flip placebo p < 0.01, each session's D flipped as a unit (10,000
    draws, seed 148);
  * both halves of the sessions (in date order) positive;
  * the vetoed positions' own mean of session means below zero after the
    0.13% round trip, so that passing them over would have saved money.
* **OBJECTIONS_BACKWARDS** is the mirror: t ≤ −3, placebo p < 0.01 (lower
  tail), both halves negative.
* **The control.** Every D is centred on zero, then 1.0% is added. It must
  show at t ≥ 3, else the verdict is UNDERPOWERED. The smallest detectable
  effect at 80% power is printed.
* **Anything but VETO_SORTS is rejection #64.**
* **The power, said now.** With about 4.6 vetoed and 5.8 other positions a
  session and 2% a position, D's spread is about 1.25% a session. Over 23
  sessions the smallest detectable effect is near 1% a position.

## Beside the verdict (descriptive, never a verdict)

* At least one objection against none; every member endorsing against the
  rest.
* Longs and shorts apart; the two sources apart.
* Claude's own proposals (73, of which 19 vetoed); the printed Top 2 on the
  frozen sessions (13, of which 4 vetoed).
* Raw returns, not against XIU.

## What follows, decided now

* **VETO_SORTS** goes to the owner as a proposal: a remove-only veto on
  Claude's picks (a pick two or more members object to is passed over, and
  its slot stays empty), run first as a forward shadow under its own
  registration. Nothing live changes from this slot.
* **OBJECTIONS_BACKWARDS** is told to the owner: the council objects to the
  better positions. No rule.
* **Anything else** is rejection #64, and nothing changes.
* **The script** (`council_veto.py`) is committed before it runs, in the next
  slot, and gets one look. It reads the pin and FMP five-minute bars: no
  OpenRouter, no model call.
