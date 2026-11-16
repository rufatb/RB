# PREREGISTER day-152: a name's own intraday habit (council lab item 12)

Registered 2026-11-16 in the council-lab slot, before any return in it was
computed. The script, `intraday_habit.py`, is committed in its own commit
before it runs, next weekday, and it gets one look. It reads cached bars only
(`.rb-state/report_day_cache`, day-143's download), so it costs nothing.

## The question

* **The idea.** Lou, Polk & Skouras (2019), "A tug of war", on US stocks:
  * a stock's past intraday returns persist intraday;
  * its past overnight returns reverse intraday.
* **Why it could matter here.** The habit is known before the open. If it
  holds on the 150 TSX names, it could break ties among Claude's nominations
  (a proposal to the owner, never a live change from this slot).
* **What the record says so far.**
  * Day-117's field scan had no such field.
  * The level split (overnight against intraday) was rejected on cost
    (day-87).
  * Every one-session signal tested since day-117 has been null (#47, #52,
    #53, #61, #62).
  * On large caps, expect a few hundredths of a percent a day at best.

## The definitions

* **The habit.** For each name and session d, the mean over the prior 20
  sessions (d−20 … d−1, never d) of `h = the name's 09:45 → close − XIU's
  09:45 → close`, in %.
  * A name needs h on at least 15 of those 20 sessions, or it is left out of
    session d.
  * The 09:45 price is the close of the 09:30 fifteen-minute bar; the close is
    the session's last bar (the record's window).
* **The sort.**
  * On each session, the names with a habit and with session d's bars are
    ranked by habit.
  * The top fifth and the bottom fifth are taken (rounded down, at least 5
    names each). A session with fewer than 25 such names is skipped and
    counted.
* **The measure,** per session:
  `y = mean(top fifth's h on d) − mean(bottom fifth's h on d)`, in %.
  Persistence predicts y > 0.
* **The per-pick edge** is y / 2: a long in the top fifth and a short in the
  bottom fifth, each against XIU.

## The data (all cached; no API call)

* **Primary.**
  * The 150 names: `data/report_day143_names.json`.
  * FMP 15-minute session prices, 2024-01-02 → 2026-10-29, as day-143 cached
    them (`.rb-state/report_day_cache/tsx`): open, 09:45, noon, close per
    session.
  * XIU.TO's bars, from the same cache.
  * The first sessions, before any name has 15 of 20 prior values, are
    warm-up.
* **Secondary, signs only.**
  * **(a) The same 150 names over ten years:** FMP dividend-adjusted daily
    bars, 2016-01-04 → 2026-10-29. The habit is the prior 20 sessions'
    open → close against XIU's; the outcome is open → close against XIU.
  * **(b) The point-in-time S&P 500** (the survivor check, day-138's rule):
    members on each date only, by day-138's membership intervals. Daily
    open → close against SPY's, with the same sort and measure.

## The bar (seed 152)

* **PERSISTENCE (supports a tie-break by habit)** needs all of:
  * mean y > 0, with t ≥ 3 on the session series;
  * all four calendar blocks positive (equal numbers of sessions, in date
    order);
  * a placebo p < 0.01, one-sided. Within each session the habits are
    shuffled across that session's names, and the mean y is recomputed
    (2,000 draws);
  * the per-pick edge above the measured cost: y / 2 > 0.13%;
  * both secondary panels' means positive.
* **REVERSAL (the opposite)** needs mean y < 0, t ≤ −3, all four blocks
  negative and the placebo p < 0.01 the other way. It is reported as a
  finding; any rule from it needs its own registration.
* **The control.** A planted 0.10% a session must show at t ≥ 3, computed as
  0.10 / se and never as (mean + 0.10) / se. Otherwise the verdict is
  UNDERPOWERED. The smallest effect detectable at 80% power (2.8 × se) is
  printed beside it.
* **Everything else is NULL.** Anything but PERSISTENCE is rejection #67.

## Beside the verdict (descriptive, never a verdict)

* **The overnight version** (Lou, Polk & Skouras's cross effect): the habit is
  the prior 20 sessions' mean prior close → open against XIU, and the outcome
  stays 09:45 → close. Their reading predicts reversal (y < 0).
* **The two legs apart:** the top fifth's mean h, and the bottom fifth's
  negated.
* **Fifths 1 to 5,** to see whether any sort is monotonic.
* **A 60-session habit** in place of 20.
* **The open → 09:45 window:** whether any persistence happens before the
  entry.
* **By year:** 2024, 2025, 2026.
* **The live record.** Claude's council nominations since 2026-10-14
  (`data/model_picks.csv`, kind `nominated`): within a session and side,
  whether the nomination with the stronger habit (in the pick's direction)
  did better. A count only; far too few to judge.

## What a result changes

* **Nothing live.** A PERSISTENCE goes to the owner as a proposed tie-break
  among Claude's nominations. It goes live only with the owner's yes, under
  its own registration and a forward shadow.
* A NULL, REVERSAL or UNDERPOWERED is rejection #67. Nothing is built from
  it.

## Not blind, said plainly

* Day-137 H1 (#53) tested following a name's one-session move against its
  sector, on the same bars: −0.044% a name-day, t = −2.75, a lean toward
  reversal.
* That is a one-day signal against the sector; this is a 20-day habit against
  XIU, sorted across names. They are related, and the earlier lean is known.
  No sort of the 20-day habit has been computed.

## Cost

* None: cached bars, no API call, no model.
