# Day-147 — held for days: do the models' reads come true over one, three or five sessions? (council lab item 8)

**Registered 2026-11-05, before any return in this test was computed.** Nothing
here changes a live pick, a size, the Top 2, a prompt or the email.

## Why

* **The owner, 11-03:** "direction didn't come true." Every pick is scored
  from the 09:45 entry to the same day's close. On that window every source is
  a coin flip: all model picks together are 116/228 (51%), +0.00% gross.
* **A read the open has priced may still come true over days.** If the
  models see a slow drift, a pick held to a later close would be right more
  often than one closed the same day.
* **What is already known points the other way.**
  * Holding overnight was worse on the day-130 replay.
  * Weeks after earnings show no edge since 2012 (day-135b).
  * Day-38's multi-day gains were market drift.

  None of these tested the models' own live reads over 1–5 sessions, which is
  what this does.

## The population (counted 2026-11-05 from the record; no return read)

* **The pooled model picks.** Every scored model pick in
  `data/model_picks.csv`, once per session, ticker and side. These are the
  scoreboard's "All model picks together" (`model_picks.pooled_card`):
  * the kinds are selected, forced, nominated, pick and final;
  * late picks, the engine and every shadow are left out;
  * the first scored row is kept.
* **The window:** sessions 2026-09-17 → 2026-10-29. That is the last session
  whose five-session close (11-05) exists when this runs. The window does not
  move.
* **Counted:** 189 picks over 26 sessions (95 long, 94 short, 67 names). By
  first recorded model: DeepSeek 66, Claude 57, Gemini 36, Jev 21, debate 8,
  Top 2 1. Every one has its recorded 09:45 entry.
* **Claude's own reads** (descriptive): its 48 nominations over 12 sessions
  (10-14 → 10-29), and its first-named long and short, which are the live
  Top 2's rule.
* **Why pooled.** Claude's 48 picks over 12 sessions could see only a very
  large effect. The pooled record is the system's reads, the question the
  owner asked of all of them. Claude's arm is reported beside it, as on
  day-145.

## The measure

* **Entry:** the pick's recorded 09:45 price (`entry`, the scorer's 09:45 bar
  close).
* **Exit:** FMP's daily close H sessions later, by XIU.TO's session calendar
  (H = 1 is the next session's close).
* **Against the market:** XIU.TO over the same window, from its 09:45 price
  that session (FMP 5-minute bars, the 09:40 bar's close) to its close H
  sessions later.
* **y_H** = side × (the pick's return − XIU's return), in %, per pick.
  * Unadjusted closes, the same basis as the entry. A dividend inside the
    hold is a small bias against longs, stated rather than corrected.
  * A pick with a missing close is left out and counted, never filled.
* **H = 3 is the registered verdict.** H = 1 and H = 5 go through the same
  machinery and are reported, not judged.

## The bar (day-145's machinery, seed 147)

* **DRIFT (the reads come true over days)** needs all of:
  * the mean of the session means of y₃ > 0, with t ≥ 3 over the session
    means;
  * a sign-flip placebo p < 0.01, each session's mean flipped as a unit
    (10,000 draws, seed 147);
  * both halves of the sessions positive;
  * the mean net of the 0.13% round trip above zero (gross above 0.13%).
    Borrow on a short held overnight, a few hundredths of a percent on these
    names, is stated, not charged.
* **REVERSAL** is the mirror image: t ≤ −3, placebo p < 0.01 (lower tail),
  and both halves negative.
* **The control.** Every y₃ is centred on zero, then 1.0% is added to every
  pick. It must show at t ≥ 3, else the verdict is UNDERPOWERED. The smallest
  detectable effect at 80% power is printed.
* **Anything but DRIFT is rejection #62.**
* **The power, said now.** A three-session hold swings about 1.7 times a
  single day. With 26 sessions the control may not reach t = 3, and then the
  answer is UNDERPOWERED: the record cannot see 1% yet.

## Beside the verdict (descriptive, never a verdict)

* H = 1 and H = 5.
* The same picks closed the same day: the record's own `r_pct` and y₀.
  * The paired difference y₃ − y₀: does holding beat closing at the close?
* Raw returns, not against XIU.
* Longs and shorts apart.
* By first recorded model.
* Claude's nominations, and its first-named long and short.
* The hit rate at each horizon.

## What follows, decided now

* **DRIFT goes to the owner as a proposal, not a rule.** It would be a hold
  of three sessions on the printed picks. That is a different trade from the
  one the system records, and it would run first as a forward shadow (a
  `hold3` column scored beside each pick) under its own registration. Nothing
  live changes from this slot.
* **Anything else** is written up as rejection #62. Nothing changes.
* **The script** (`holds_history.py`) is committed before it runs, in the next
  slot, and gets one look. It reads `data/model_picks.csv` and FMP daily and
  5-minute bars: no OpenRouter, no model call.

## Amendment 1 — the rejection number only (2026-11-05 evening, before this test runs)

The day-147c market-direction test (`PREREGISTER_day147c_market_direction.md`)
reaches its verdict before this one. If it is a rejection it takes #62, and
this test's "anything but DRIFT" becomes #63. Nothing else here changes.
