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

---

## Amendment 1 (2026-10-23, after E1's verdict, before E1-US was run)

* **Why.** E1 passed, but its list is today's 150 most-traded TSX names. They
  are survivors, and the two splits that tried to see past that are both
  muddied by survival:
  * By whole-period return, the best third shows the most premium. That return
    contains the report days themselves.
  * By the return away from reports, the worst third shows the most. A name
    that lost between reports and still made today's list must have gained on
    them.
* **E1-US.** E1's rule runs unchanged on the S&P 500 as it stood on each date.
  * Membership comes from FMP's history of index changes. A name counts from
    the day it joined to the day it left; delisted names are included where
    FMP still serves their bars, and every name that cannot be fetched is
    counted and named.
  * The market is SPY, and the period is 2012-01-01 → 2026-10-14.
  * The window, statistic, placebo and bar are E1's.
* **What it decides.**
  * **E1-US PASS:** E1's premium is credible as something to expect. Its size
    on the TSX is still not known, and the forward record measures it.
  * **E1-US NULL:** E1 is not adopted; it is a survivor artifact until shown
    otherwise.

---

## Results (2026-10-23, after the runs; nothing above was changed)

| Test | Reports | Excess a report | t | Placebo p | Blocks | Verdict |
|---|---:|---:|---:|---:|---|---|
| E1, long every report (TSX list) | 8,203 | +0.37% | +3.78 | 0.000 | +0.46 +0.25 +0.28 +0.49 | PASS as registered |
| E2, the previous surprise | 6,926 | +0.11% | +1.27 | 0.013 | +0.13 +0.19 −0.20 +0.32 | NULL |
| E3, the peers' surprises | 2,208 | +0.33% | +1.68 | 0.007 | +0.57 +0.80 −0.21 +0.16 | UNDERPOWERED |
| E4, the model's unpriced read | 133 | +0.24% | +0.63 | 0.278 | +2.25 −0.51 −0.36 −0.40 | UNDERPOWERED |
| E1-US, long every report (S&P 500 as it stood) | 27,701 | +0.01% | +0.20 | 0.244 | +0.11 +0.06 +0.10 −0.21 | NULL |

* **E1 is not adopted (amendment 1).**
  * On the S&P 500 as it stood on each date (673 names with bars; 46 delisted
    names FMP no longer serves), the same rule earns nothing. A planted 0.50%
    would show at t = 8.07 (smallest detectable effect 0.24%).
  * Split by survival, names still in the index today show +0.15% (t = 2.42)
    and names since removed −0.65% (t = −4.76). Testing on today's names
    manufactures the premium.
  * The TSX list is today's 150 most-traded names, ranked on the last 20
    sessions, and its premium is largest in 2024–2026 (+0.47%, +0.90%, +1.07%
    a report): the years a recent-trading ranking tilts hardest toward recent
    winners.
* **E1's checks after its verdict all held, and survival explains each one:**
  * against the names not reporting in the same window: +0.40%, t = 4.05;
  * on a market model: +0.34%, t = 3.50;
  * trimmed: +0.36%;
  * only when the report fell inside the window: +0.48%, against −0.00% when
    FMP's date put it after the exit.

  A survivor's good reports sit on its report days too.
* **The other three.** E2's and E3's long legs carry E1's survivor premium,
  and their short legs lose. E4 is three months of archive (smallest
  detectable effect 1.47%).

**Nothing passes; rejection #56.** No forward event council is proposed.
