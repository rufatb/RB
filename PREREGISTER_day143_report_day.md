# Day-143 — a name on its report day: a size rule (council lab item 4)

**Registered 2026-10-30, before any return in this test was computed.**
Nothing here changes a live pick, size, prompt or rule. A PASS goes to the
owner as a proposal for a remove-only switch under its own registration.

## Why

* **Two size rules already thin the Top 2.** Both are remove-only:
  * the last session's big movers (day-135c/d, `SKIP_MOVERS`);
  * the morning's widest-swinging names (day-137, `SKIP_WILD`).
* **Neither sees a scheduled event.** A name whose results came out between
  the prior close and the open trades its reaction day today.
  * 10-29's table held two: CP.TO and GFL.TO reported after the 10-28 close.
  * Their −1.07 and −1.33 ATR falls on 10-28 came before the releases, and
    the members read them as "post-earnings".
* **Direction on a report day is settled.**
  * An earnings reaction day's first half hour does not predict
    10:00 → close (#46, t = 0.50).
  * The open prices a release (day-118, day-122, day-125).
* **Size is untested.** If a report day swings wider after 09:45, skipping it
  is a size rule, as day-137's was.

## The question

Does a name swing wider from 09:45 to the close in its report window than on
its other days? The comparison counts only name-days the two live rules
would not already pass over, and the window must not lean either way.

## The data

* **Names.** The 150 in `.rb-state/tsx_universe.json` as staged on
  2026-10-30 (08:53), pinned in `data/report_day143_names.json` and
  committed with this file. Today's list is survivor history (day-138), so
  the point-in-time check below is part of the bar.
* **Primary.** FMP 15-minute bars, 2024-01-02 → 2026-10-29.
  * y is the 09:45 → 16:00 return: day-137's measure, built with
    `council_history.panel`.
  * It is taken raw, and against XIU.TO for the lean.
* **Secondary.** FMP dividend-adjusted daily bars, 2016-01-04 → 2026-10-29,
  measuring open → close (`risk_rules.Daily`).
* **Report dates.** FMP `earnings` per name (limit 400), fetched as
  `replay_weeks` fetches them.
  * Each report date maps to D0, the first XIU session on or after it, and
    D1, the next session.
  * The **report window** is D0 and D1. FMP gives no reliable time of day for
    TSX reports, so the reaction falls on D0 (a release before the open) or
    on D1 (one after the close).
  * FMP's date is early for about a third of reports (day-135b). That puts
    some reactions after D1, which only dilutes the window toward the rest:
    the test is conservative.
  * Reports with no session in range or no bar are dropped and counted.
* **What the live rules already remove.** A name-day enters the comparison
  only if neither rule would pass it over that morning:
  * its prior session's move is under 1 ATR (`|move_atr| < 1`, day-135c);
  * its ATR % is under that session's 90th percentile across the names
    (day-137).

## The bar

PASS needs all four.

1. **Size.** The report window's raw sd of 09:45 → close is at least 1.15×
   the rest's, both within the comparison set. 1.15 is the house's variance
   bar (day-120b, day-135c R2, day-137 H3).
2. **No lean.** On the window, both of these show a date-clustered |t| < 2:
   * 09:45 → close against XIU, signed by the session's opening gap
     (continuation positive);
   * the same, long.

   A lean would make the rule change a bet, not a size.
3. **A placebo.** The same construction with every report date moved 20
   sessions earlier (a window with no report) gives a ratio below 1.15.
   Otherwise the ratio belongs to the filter, not the report.
4. **Point in time** (day-138's rule for an event rule).
   * The universe is the S&P 500 as it stood on each date
     (`replay_events.sp500_membership`), 2016-01-04 → 2026-10-29, on daily
     open → close against SPY.
   * Names since removed are included where FMP serves them.
   * The same two filters apply, and the ratio must also reach 1.15.

* **FAIL** is anything short of all four. It is rejection #59.
* **The planted control** (house rule 10). A random pseudo-window of the
  same size (seed 143) is drawn from the rest.
  * Unscaled, its ratio must stay below 1.15.
  * Scaled by 1.25, it must reach 1.15.
* **The uncertainty.** The 95% interval of the primary ratio comes from a
  session bootstrap (2,000 draws, seed 143), and the smallest ratio the test
  can tell from 1.00 is stated.
* **One look.**

## Beside the verdict (descriptive, never a verdict)

* D0 and D1 separately.
* The window without the live-rule filter.
* The ratio by year (daily), and the within-name median ratio.
* The share of name-days moving more than 3%.
* The volume-confirmed subset (day-135b's `volume_peak`). It is flagged:
  selecting on the volume spike inflates the ratio.
* How many of the record's council positions (`top2/pick` and the
  passed-over shadows, 10-05 → 10-29) sat in a report window.

## What follows

* **PASS:** adoption #6 goes to the owner as a remove-only switch (off until
  they say yes), under its own registration.
  * A live rule needs a reaction-day test that does not rest on FMP's date
    alone: the wire archive's results releases between the prior close and
    the open, beside the brief's `last_report`.
  * Nothing is built before the owner's yes.
* **FAIL:** rejection #59. The two live rules stand as they are.
* **Files:** the script is `report_day.py`. The summary is
  `data/report_day143.json`, and the cache is `.rb-state/report_day_cache/`.
* **Cost:** FMP calls only (the 150 names, 15-minute and daily, plus the
  point-in-time S&P 500 daily set). No OpenRouter, no DeepSeek.
