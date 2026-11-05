# Day-146 — three days one way: does a pick that follows a three-day run lose on day four? (owner, 2026-11-04)

Registered on the evening of 2026-11-04, before any return in it was computed.
The script, `runs_history.py`, is committed before it runs, and it gets one
look. It reads cached bars only (`.rb-state/report_day_cache`, day-143's
download), so it costs nothing.

## The owner's words

After 11-04's CLS.TO long lost 5.21%:

> "The stock has already gone that direction in which you're predicting it
> will continue to go … for the past three days let's say it's been decreasing
> if you give it a short the day after it declined for three days there is
> that risk of rebounding and it kept happening and same in the other
> direction where it's been pumping for three days and you still say long
> position. There is a possibility of profit taking by investors which does
> happen and then you lose out on that day, even though the technicalities
> were correct and it's been pumping."

## Not tested here before

* Day-132 (#47), day-135c/d (#51, #52) and day-137 (#53) all asked about
  **one** session's move (≥ 1 ATR, or against the sector).
* Day-130's weekly-reversal sleeve traded five-day losers as its own book.
* Nothing has asked about a **run of days in one direction**, whatever their
  size, as the owner describes it.

## The definitions

* **A run.** A name's last three completed sessions each closed the same way
  against the session before (close to close). Three rises is an up run; three
  falls is a down run. A flat close breaks it. A longer run counts, because its
  last three days are one way.
* **Following a run.** LONG after an up run, SHORT after a down run: betting
  the move carries on. This is what the owner says keeps losing.
* **The measure,** per name-day with a run:
  `y = sign(run) × (the name's 09:45 → close − XIU's 09:45 → close)`, in %.
  The owner's reading predicts y < 0: a rebound, or profit-taking.

## The data (all cached; no API call)

* **Primary.**
  * The 150 names: `data/report_day143_names.json`.
  * FMP 15-minute session prices, 2024-01-02 → 2026-10-29, as day-143 cached
    them (`.rb-state/report_day_cache/tsx`). The window is the record's: the
    09:30 bar's close (09:45) to the session's last close.
  * The run is read from FMP's daily closes (`eod`). The name's prior session
    must be XIU's prior session, or the day is skipped and counted.
* **Secondary, where only the sign is required.**
  * **(a) The same 150 names over ten years:** FMP dividend-adjusted daily bars,
    2016-01-04 → 2026-10-29, open → close against XIU's open → close.
  * **(b) The point-in-time S&P 500:** members on each date only, by day-138's
    membership intervals. Daily open → close against SPY's. This is the
    survivor check (day-138's rule).

## The bar (day-137 H1's machinery, seed 146)

* **REVERSAL (supports the rule)** needs all of:
  * mean y < 0, with a session-clustered t ≤ −3;
  * all four calendar blocks negative;
  * the placebo p < 0.01, two-sided. Each event's run sign is replaced by the
    same name's run sign on a random other run session at least 5 sessions
    away (2,000 draws);
  * both secondary panels' means negative.
* **CONTINUATION (the opposite)** needs mean > 0, t ≥ 3, all four blocks
  positive and placebo p < 0.01.
* **The control.** A planted 0.10% must show at t ≥ 3 (0.10 / se); otherwise
  the verdict is UNDERPOWERED.
* **Everything else is NULL.** Anything but REVERSAL is rejection #61. REVERSAL
  would be the first registered rule shown to make picks right more often.

## Beside the verdict (descriptive, never a verdict)

* Runs of at least 2, 4 and 5 days.
* Up runs (the longs) and down runs (the shorts), apart.
* The three days' total move in normal days (ATR14): under 1, 1–2, 2 or more.
* Raw, not against XIU.
* The open → 09:45 and open → close windows: whether a reversal, if any,
  happens before the entry.
* **The live record.** Every scored model pick 2026-09-17 → 2026-11-04 (once
  per session, name and side; the shadows left out), split into following a
  run and not, with runs from FMP daily closes.

## What follows, decided now

The owner asked for the rule, so it is built whatever the result, behind
`council.SKIP_RUNS`.
* **Claude's picks (the live Top 2).**
  * A nomination that follows a run is passed over.
  * Claude's next nomination on that side that does not follow a run stands in
    its place.
  * If both of Claude's nominations on a side follow runs, that side is empty.
* **The council's own Top 2** (when Claude's picks are missing) is remove-only,
  as the big-mover rule is: nothing is added in a passed-over pick's place.
* **The record.** Passed-over picks are recorded as `top2run/pick`, a shadow:
  never sized, never pooled, out of the scoreboard and the lab. The evening
  review scores them.
* **The forward judgement** comes at 40 sessions with a passed-over pick: the
  passed-over picks against what stood in their place, paired by session and
  side, at t ≥ 3 with a sign-flip placebo p < 0.01 and both halves agreeing.
* **REVERSAL or NULL:** switched ON from the 2026-11-05 morning, at the owner's
  request, labelled with this result. A NULL means the rule is not shown to
  make picks right more often. It changes which picks are made and, on this
  evidence, costs nothing on average.
* **CONTINUATION:** left OFF, and the owner is told before anything goes live.
  Following runs would then be the better side, and the rule would remove the
  better picks.
