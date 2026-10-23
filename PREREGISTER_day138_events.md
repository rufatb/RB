# Day-138 — before the news, held a few days (owner, 2026-10-22)

Registered BEFORE any return below was computed. Nothing here changes a
pick, a size or a record.

The owner, after the Top 2's losing run: "You think of new ways for the
council algo that is not retrospective bias. And the hold should be few days.
And the price shouldn't already have changed the price to account for the
research that the language models and web searches are doing."

## What the three conditions mean here

1. **No retrospective bias.**
   * No signal is built from the stock's own past price moves: no momentum,
     no reversal, no "it moved yesterday" (day-132, day-135c/d, day-137).
   * Every input is dated before the entry.
   * No model is scored on a period it may remember.
2. **A few days.** Every position is held three or four sessions.
3. **Not already in the price.** A position is taken either BEFORE the
   information is public (a scheduled report), or only where the price has
   measurably not moved on it yet.

## The population (E1–E3)

* **Names and bars.** The 150 names of the TSX list
  (`.rb-state/tsx_universe.json`), on FMP dividend-adjusted daily bars, with
  XIU.TO as the market. Reports from 2012-01-01 to 2026-10-14: the day-135b
  cache, read through `replay_weeks.collect`.
* **A report** is an FMP `earnings` row with `epsActual` present, dated inside
  the calendar.
  * D is its date;
  * P0 is the last session before D;
  * D1 is the first session after D.
* **The window:** enter at P0's close and exit at the close of D1 + 2, three to
  four sessions.
  * It holds the report whether it comes before the open on D or after the
    close (FMP gives no time of day).
  * It also holds most reports FMP dates a day early (day-135b).
* **The return:** y is the stock's return minus XIU's over the window, in %.

## Hypotheses

* **E1, the earnings-announcement premium.** LONG every report.
  * Stocks earn more in the days around a scheduled report, as payment for
    the risk of the news (Frazzini & Lamont 2007; Barber et al. 2013).
  * The position is taken before anything in the report is known.
* **E2, surprises persist.** The side is the sign of the same name's previous
  surprise: that report's `epsActual` against its `epsEstimated`.
  * The previous report must fall 30 to 200 days before D.
  * An in-line report gives no side (Bernard & Thomas 1990).
* **E3, the peers' read-through.** The side is the majority sign of the
  surprises of same-industry names that have already reported.
  * The industry label must have ≥ 3 names on the list.
  * The peers' reports must fall between 30 calendar days before D and 5
    sessions before P0. That way even a report FMP dates early is public by
    the entry.
  * A tie gives no side.
* **E4, a model's read the open has not priced.** It uses the day-122
  replay's cached FULL-arm answers: DeepSeek v4-pro read the whole overnight
  release (420 releases, 2026-07-02 → 10-01), and its probe showed no memory
  of the period.
  * **Kept:** calls the model marked `material`, where the open did not move
    its way. That means the stock's open against its prior close, minus XIU's,
    signed to the call, is ≤ 0.
  * **Entry** at that open: the TSX shows its calculated opening price before
    09:30.
  * **Exit** at the close two sessions later (three sessions).
  * **Bars:** FMP daily open and close, with XIU the same.

## Statistic and the bar (each hypothesis alone)

* **Placebo.** Each event keeps its name and side and moves to a random window
  of the same length within ±250 sessions (E4: ±120). The window never falls
  within 10 sessions of the name's own reports (E4: its releases in the
  archive). There are 2,000 draws.
* **Excess** is the events' mean minus the mean of the placebo draws. That
  nets out how these names drifted over the period; the list is today's 150,
  so they are survivors.
* **t** is the excess over the clustered standard error. Of clustering by name
  and by week (E4: by session and by name), the smaller |t| counts.
* **PASS needs all of:**
  * excess > 0 and t ≥ 3.0;
  * a one-sided placebo p < 0.01: the share of draws at or above the events'
    mean;
  * at least 3 of 4 time blocks positive, and the LAST block positive (where
    survivorship is weakest);
  * an excess above the measured 0.13% round trip, plus borrow for shorts.
* **Otherwise** the verdict is NULL when a planted 0.50% would show at t ≥ 3,
  else UNDERPOWERED. A negative excess at t ≤ −3 is reported as the opposite
  side; it is never traded without its own registration.

## Descriptive only (never a verdict)

* exits at D1 (the reaction alone) and at D1 + 4;
* before 2020 and from 2020; the liquidity terciles; the sectors;
* E2 and E3 by the size of the surprise;
* E4 over all material calls, and over the calls the open had already priced.

## What follows

* **A pass.** The council's job is redesigned around it. The design is
  registered separately before it runs, then run as a forward shadow through
  the earnings season now under way. It is never sized and never in the
  Top 2; the owner decides any money.
* **All fail.** That is said plainly.

Script: `replay_events.py` → `data/replay_day138_events.json`.
