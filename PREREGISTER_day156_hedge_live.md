# PREREGISTER day-156: the sector-fund hedge on the live record (council lab item 18)

Registered 2026-11-27 in the council-lab slot, before any return in it was
computed for this test. The script, `hedge_live.py`, is committed in its own
commit before it runs, next weekday, and it gets one look. It reads the
committed execution lab (`data/reviews/execution_lab.csv`) only: no network,
no model, no cost.

## Why

* **What the emails say.** Under every one-sided Top 2 (11-27: SHORT FM.TO
  alone) the hedge line (`top_picks.hedge_line`, day-148c) prints two records
  side by side:
  * the live one (`execution_lab.hedge_record`): "On the record so far (181
    picks, the hedge sized by each stock's beta to its fund) the hedged pick
    made 0.23% a pick more than the unhedged one and swung 21% less";
  * the replay's: "On the 379-pick replay it swung 18% less and made 0.11% a
    pick less, which failed its registered test (day-130)."
* **The gap.** The live sentence is a running mean with no t, no placebo, no
  cost for the hedge's own leg and no bar. Day-130 H2 judged the hedge on the
  day-117 replay only. The owner trades the live picks, so the live claim
  needs the same test day-153 gave the noon exit.
* **What it could change.** A confirmation would let the line cite a passed
  test on the live record. A failure would mean the live sentence overstates
  what is known. Either wording change goes to the owner as a proposal:
  nothing live changes from this slot.
* **Not blind.** The line has printed the running gross comparison on every
  one-sided morning since 11-10, and the evening review's lab table shows it.
  On 11-27 it read +0.23% a pick and 21% less swing over these 181 picks.
  Nothing else in this test (net of cost, t, placebo, halves, bootstrap) has
  been computed.
* **The backlog.** No free row was left (day-155c, day-156); this is the next
  free question, proposed and registered in one slot as items 15–17 were.

## The population (pinned)

* **The file.** `data/reviews/execution_lab.csv` as committed at 150a72c (the
  11-26 evening record; sha256 begins `eebb2b8bb207b99d`): 624 rows, sessions
  2026-09-17 → 2026-11-26.
* **The rows.** The hedge line's own population, `execution_lab._model_picks`
  as committed: every source but the engine and the shadows it excludes
  (`top2count`, `top2memory`, `top2mover`, `top2wild`, `top2council`,
  `top2run`, `top2floor`), no forced nominations, one row per name and side
  (`_unique`). That is the population the line quotes, so the test judges the
  printed claim. It includes the runner-up shadow (`top2runner`, 3 rows); the
  day-153 population, which leaves it out, is reported beside the verdict.
* **Measured both ways.** Rows with both `r` and `r_vs_etf`: 181 positions over
  44 sessions, all with a recorded `beta` (counted at registration, no return
  read). By source: Gemini 59, DeepSeek 46, Jev 39, the Top 2 19, Claude 8, the
  debate's finals 7, the runner-up 3. SHORT 100, LONG 81.
* **The cut.** Sessions through 2026-11-26 only. Rows the evening job adds
  later are not read.
* **The windows,** as the lab measured them, both from the 09:45 entry to the
  close and signed to the pick:
  * `r`: the stock alone (the record's yardstick);
  * `r_vs_etf`: the stock less `beta` times its sector fund (`exposure`'s fund,
    XIU.TO where none applies; beta over the 40 prior sessions).

## The measures

* **The hedge's gain, net of its own leg:** d = (r_vs_etf − r) − 0.13% × |beta|
  per position, in %. The fund's own spread is not measured; the stock's
  measured round trip (0.13%, day-132b) is charged on the hedge's notional,
  which overstates the cost of the funds (XIU.TO's spread is about 1 bp). The
  gross difference r_vs_etf − r is printed beside it.
* **The mean of d,** session-clustered (`replay_fmp_analyst.clustered`, as
  day-153).
* **The swing:** the ratio sd(r) / sd(r_vs_etf) over positions. Above 1 means
  the hedged position swings less.

## The bar (seed 156)

**CONFIRMED** needs all of:
* **The mean.** Mean d ≥ −0.05% with its t > −2: net of its own cost, the
  hedge is not shown to cost money.
* **The swing.** The ratio ≥ 1.15 (day-135c's bar for a size rule), with the
  5th percentile of a session-block bootstrap (2,000 draws, seed 156) above
  1.0.
* **Both halves.** In session order, equal numbers of sessions: each half
  shows a ratio above 1.0 and a mean d ≥ −0.05%.
* **The control.** A planted cost of 0.20% a position must show at t ≥ 3,
  computed as 0.20 / se and never as (mean − 0.20) / se. Otherwise the verdict
  is UNDERPOWERED. The smallest effect detectable at 80% power (2.8 × se) is
  printed beside it.

**Anything else.**
* **Not confirmed:** anything but CONFIRMED is rejection #73. The line's live
  sentence is then proposed to the owner for correction.
* **WORSE:** the hedge is shown to cost money net of its leg (mean d < −0.05%
  with t ≤ −2), or it swings more (ratio below 1.0). This is named as such
  within #73.
* **BETTER,** reported and never a verdict: mean d ≥ +0.05% with t ≥ 3.

## Beside the verdict (descriptive, never a verdict)

* The gross difference, r_vs_etf − r, with its clustered t.
* The day-153 population (no runner-up; the debate's finals kept).
* The Top 2's own picks alone, and its picks on mornings with one side only
  (the line's own occasion).
* LONG and SHORT apart; XIU.TO against a sector fund; by fund.
* The share of positions the hedge improved; by month.

## What a result changes

Nothing live, whatever the result. A CONFIRMED result goes to the owner as two
proposals: the line cites this test instead of the replay's failure alone, and
the hedge, as a structure for a one-sided morning, under its own registration
(a size rule, as the five adoptions were). A rejection goes to the owner as a
proposed correction of the line's live sentence. The pick, its size, the
record and the hedge line itself are unchanged until the owner decides.
