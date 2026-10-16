# Day-135d audit — two Top 2s in a row followed the day before's big move (owner, 2026-10-16)

Registered first: `PREREGISTER_day135d_breadth.md` (75e2ecc). Scripts:
`breadth_reversal.py` (the registered test) and `chase_audit.py`
(descriptive). Summaries: `data/breadth_day135d.json` and
`data/chase_audit_day135d.json`.

## The owner's question

* **The two days.**
  * 10-15: SHORT CLS.TO and SHORT CCO.TO after falls of about 1.5 ATR. Both
    bounced, and the shorts lost 3.6% and 4.2%.
  * 10-16: LONG L.TO and LONG WCN.TO after rises of about 2.5 ATR.
* **What the owner asked:** why does this happen twice in a row, and what can
  raise accuracy? Their reading: big movers turn back the next day, so
  extending yesterday's move is risky.

## Why it happens: the council concentrates a habit the models already have

A pick FOLLOWS when its name moved ≥ 1 ATR in the last session and the pick
takes that direction. A random name and side follows at half the list's
big-mover share (the base).

| Stage, 10-05 → 10-16 | Follow | Base | × chance | Fade |
|---|---:|---:|---:|---:|
| desk selections | 17 of 34 (50%) | 8.5% | 5.9 | 1 |
| nominations (forced, from 10-14) | 22 of 36 (61%) | 15.6% | 3.9 | 2 |
| Jev's forced picks | 7 of 16 (44%) | 8.7% | 5.0 | 1 |
| **the council's Top 2** | **12 of 15 (80%)** | 9.5% | **8.5** | **0** |
| counted rule (shadow) | 5 of 11 (45%) | 8.2% | 5.5 | 0 |
| memory council (shadow) | 8 of 8 | 13.5% | 7.4 | 0 |

* **On 10-16 the council narrowed it step by step:**
  * the table: 4 of 11 positions follow;
  * the agreed positions: 2 of 3;
  * the picks: 2 of 2.

  The reasons say why. They read "follow-through on yesterday's strength" and
  "strong momentum breakout", made from the prior session's rows: move_atr,
  rvol, closing at the high, sector-relative move. Four members agreeing is
  four readers of the same rows finding the same thing striking.
* **Why the two picks shared a side.** Every earlier two-pick day was one long
  and one short. Both same-side days came right after the broadest sessions in
  the sample: 25%, 35% and 34% of the list moved ≥ 1 ATR on 10-14, 10-15 and
  10-16, against 5–19% before. On a broad day the most striking movers move
  together, so the council's two favourites share a direction.
* **Chasing a big mover is not a reversal bet, and not a continuation bet
  either** (day-132, day-135c). The cost is a wider swing. After a move of
  ≥ 1 ATR the next session swings 1.24× wider, and after ≥ 2 ATR (L and WCN
  were 2.5) 1.59× wider.

## The registered test: do movers turn back after a broad day? NULL (rejection #52)

**Setup.** 2017–2026, 150 names. A broad day is the top decile of breadth over
the prior 250 sessions: a median 24% threshold, against 11% on an ordinary
day. That gives 266 broad sessions and 12,020 mover name-days.

| Next session, signed by the move | mean | t (by date) | placebo p | blocks | verdict |
|---|---:|---:|---:|---|---|
| RAW, after broad days | +0.023% | 0.26 | 0.80 | +0.00 +0.03 +0.17 −0.12 | **NULL** |
| against XIU | +0.011% | 0.16 | 0.86 | −0.00 −0.02 +0.06 −0.00 | NULL |
| RAW, after other days | −0.026% | −1.08 | | | |

* **Control** (house rules 4 and 10): a planted −0.30% reversal shows at
  t = −3.41 raw and −4.46 against XIU. The smallest detectable effect is
  0.34% raw and 0.26% against XIU. The null is powered.
* **By the day's direction:**
  * after broad DOWN days, +0.013% (t = 0.10, 143 sessions);
  * after broad UP days, +0.036% (t = 0.32, 123 sessions).
* **The market itself.** After a broad day, XIU signed by that day's direction
  is +0.017% (t = 0.29, MDE 0.22%).
* **So:** after a broad big-move day the movers neither turn back nor carry
  on. The two days the owner lived through are what a coin flip with a wide
  swing looks like.
* **10-16 showed the other side.** From 09:45, 10-15's shorts fell: CLS
  −0.83%, CCO −3.10%, HUT −10.21% at 15:50. The 10-16 longs, under water at
  noon (L +0.03%, WCN −0.72%), finished +0.75% and +0.42% at the last bar
  before the close, while XIU fell 0.58%.

## What changes

* **R2 is switched on** (`council.SKIP_MOVERS = True`) for the 2026-10-19
  morning.
  * **Why.** The owner asked twice for picks that do not carry the last day's
    move into the next ("it's pretty risky for me to long again the next
    day"), and R2 is the tested rule that does it. That makes it the fourth
    adoption, and like the other three, a variance result.
  * **The record** splits at `+day135c-movers`. A council saved before 10-15
    has no `moves`, keeps its old label and is read as it was.
  * **What it would have done.** On 10-15 it would have left nothing to act
    on. On 10-16 it would have picked SHORT CVE.TO alone, which lost 1.73% for
    the short while the two longs gained. It removes the names that swing
    widest; it does not pick winners.
* **No fade rule** (this test) and **no chase rule** (day-132).
* **Unchanged:** the one-direction warning stays a warning. R1 failed its
  registered bar (1.13). On days the market moves ≥ 1%, two names correlate
  0.25, so two same-side picks swing about 29% more than a long/short pair.
  Size them as one bet.

## Accuracy, plainly

* **The tests.** Fifty-two registered tests, and none has raised the hit rate.
* **The record.** Before today, the Top 2 is 7/19 right (37%), −0.63% a pick
  after costs. All model picks together are 37/86 (43%), −0.48%. Every 95%
  range contains 50%.
* **Why.** The inputs are the prior session's prices and indicators, the news,
  analyst changes and earnings. They are priced by 09:45 (day-117, 118, 122,
  125, 132c).
* **What is left to control is how large a loss gets, not how often a pick is
  right:**
  * skip the big movers (now on);
  * do not stack two same-side picks;
  * the noon exit (no worse on the replay, with 15% less swing);
  * size.
