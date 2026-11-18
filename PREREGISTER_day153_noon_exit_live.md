# PREREGISTER day-153: the noon exit on the live record (council lab item 15)

Registered 2026-11-18 in the council-lab slot, before any return in it was
computed. The script, `noon_exit_live.py`, is committed in its own commit
before it runs, next weekday, and it gets one look. It reads the committed
execution lab (`data/reviews/execution_lab.csv`) only: no network, no model,
no cost.

## Why

* **What the emails say.** Every Top 2 section prints day-130's note
  (`execution_lab.NOON_NOTE`): "on 379 replay picks, closing at 12:00 ET was
  no worse than holding to the close and swung 15% less; the afternoon added
  nothing."
* **Where that came from.** H3 of `PREREGISTER_day130_learning.md`, on the
  day-117 replay's picks. It has never been checked on the live picks, and
  the owner trades the live picks.
* **What it could change.** A confirmation would let the note cite the live
  record. A failure would mean the note overstates what is known. Either
  wording change goes to the owner as a proposal: nothing live changes from
  this slot.
* **The backlog.** Items 1–14 are done, parked (6), waiting for a desk to
  clear a bar (7) or waiting for the owner's yes and budget (10). This is the
  next free question.

## The population (pinned)

* **The file.** `data/reviews/execution_lab.csv` as committed at
  registration (sessions 2026-09-17 → 2026-11-17, 500 rows, all with both
  `r` and `r_noon`; 250 of them in the rows below).
* **The rows.** The pooled card's kinds (`selected`, `forced`, `pick`,
  `final`) from the live sources: Claude, DeepSeek, Gemini, Jev, the Top 2
  and the debate's finals.
  * Left out: the engine (`engine/board`), every shadow (`top2council`,
    `top2count`, `top2floor`, `top2memory`, `top2mover`, `top2run`,
    `top2runner`, `top2wild`) and late picks.
* **Once each.** Each (session, ticker, side) counts once, as the pooled
  card does: 179 positions over 37 sessions (counted at registration, no
  return read).
* **The cut.** Sessions through 2026-11-17 only. Rows the evening job adds
  later are not read, so the population stays the one counted here.
* **The windows,** both from the 09:45 entry, as the lab measured them:
  * `r`: to the close (the record's yardstick);
  * `r_noon`: to the 12:00 ET bar.

  Both pay the same entry, and the same exit cost, so the 0.13% round trip
  cancels in their difference. It is stated, not subtracted.

## The measures

* **The cost of leaving at noon:** d = r_noon − r per position, in %. The
  mean of d is session-clustered (day-137's `clustered`, as the lab's tests
  use).
* **The swing:** the ratio sd(r) / sd(r_noon) over positions. Above 1 means
  the noon exit swings less.

## The bar (seed 153)

**CONFIRMED** needs all of:
* **The mean.** Mean d ≥ −0.05% (day-130 H3's own bar) and its t > −2, so
  the noon exit is not shown to cost money.
* **The swing.** The ratio ≥ 1.15 (day-135c's bar for a size rule), with the
  5th percentile of a session-block bootstrap (2,000 draws, seed 153) above
  1.0.
* **Both halves.** In session order, equal numbers of sessions: each half
  shows a ratio above 1.0 and a mean d ≥ −0.05%.
* **The control.** A planted cost of 0.20% a position must show at t ≥ 3,
  computed as 0.20 / se and never as (mean − 0.20) / se. Otherwise the
  verdict is UNDERPOWERED. The smallest effect detectable at 80% power
  (2.8 × se) is printed beside it.

**Anything else.**
* **Not confirmed:** anything but CONFIRMED is rejection #68. The note's
  wording is then proposed to the owner for correction.
* **WORSE:** the noon exit is shown to cost money (mean d < −0.05% with
  t ≤ −2), or it swings more (ratio below 1.0). This is named as such
  within #68.

## Beside the verdict (descriptive, never a verdict)

* The Top 2's own picks (`top2/pick`) alone.
* LONG and SHORT apart.
* The afternoon alone: the mean of r − r_noon, signed to the pick.
* The share of positions where the noon exit did better.
* The lab's other exits on the same positions, as recorded: the pick's own
  "wrong if" stop, the 0.5 and 1 ATR stops, and the sector-fund hedge.
* By month.

## What a result changes

* **Nothing live.** No pick, size, record or rule changes.
* **The wording.** The note under the picks is the one thing a result can
  touch, and only as a proposal to the owner:
  * on CONFIRMED, a line citing the live record beside the replay;
  * on a failure, a correction.

## Not blind, said plainly

* The evening review has printed the execution lab's running comparison
  every evening since 10-11, the noon exit among its rules. Those numbers
  have been on screen.
* I did not read them before writing this, and the bar above is day-130's
  bar with stricter legs added, fixed before this look.

## Cost

None: the committed lab file, no API call, no model.
