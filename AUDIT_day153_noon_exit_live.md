# AUDIT day-153 — the noon exit on the live record: UNDERPOWERED (rejection #68), and it leans worse

Council lab item 15, registered 2026-11-18
(`PREREGISTER_day153_noon_exit_live.md`), run once on 2026-11-19 by
`python noon_exit_live.py` (5cb0c94, committed before it ran). Summary:
`data/noon_exit_live_day153.json`.

## The question

Every Top 2 section prints day-130's note (`execution_lab.NOON_NOTE`): "on 379
replay picks, closing at 12:00 ET was no worse than holding to the close and
swung 15% less; the afternoon added nothing." That came from the day-117
replay (H3). Does it hold on the picks the owner actually gets?

* **The population.** The committed execution lab's live positions: the pooled
  card's kinds (`selected`, `forced`, `pick`, `final`), with no engine, no
  shadows and no late picks. Sessions 2026-09-17 → 11-17, each
  (session, ticker, side) once.
  * 250 rows, 179 positions over 37 sessions, as counted at registration.
  * No position was missing either window.
* **The measures,** both from the 09:45 entry and signed to the pick:
  * d = r_noon − r, the cost of leaving at noon, its mean clustered by session;
  * the swing ratio sd(r) / sd(r_noon). Above 1 means noon swings less.
* **Choices fixed in the code before the run,** where the registration left
  them open:
  * 37 sessions is odd, so "equal halves" are the first 18 and the last 18;
    the middle session (10-20) sits in neither half;
  * the order of labels: CONFIRMED, then UNDERPOWERED (control short of
    t = 3), then WORSE, then NOT_CONFIRMED. The WORSE condition is printed as
    its own flag either way.
* **One look at a few values before the run.** To confirm the lab's sign
  convention, I compared the lab's `r` with `data/model_picks.csv`'s `r_pct`
  on five rows of 09-17 and 09-22; they matched. No mean, sd or difference was
  computed before the run.

## Result: UNDERPOWERED, with the WORSE flag up

| Leg | Bar | Value | Met |
|---|---|---:|---|
| Mean d (noon minus close), clustered | ≥ −0.05% and t > −2 | **−0.230%**, t = **−2.45** | no |
| Swing ratio sd(close) / sd(noon) | ≥ 1.15 | **1.22** | yes |
| Session-block bootstrap, 5th percentile (2,000 draws, seed 153) | > 1.0 | 1.085 (median 1.21, 95th 1.36) | yes |
| First half (18 sessions, 84 positions) | ratio > 1.0 and mean d ≥ −0.05% | ratio 1.25, d −0.14% (t = −1.14) | no |
| Second half (18 sessions, 90 positions) | the same | ratio 1.20, d −0.35% (t = −2.51) | no |
| Planted 0.20% cost: 0.20 / se | t ≥ 3 | **2.13** | no |
| Smallest effect detectable at 80% power (2.8 × se) | printed | 0.26% | |

* **The swing holds.** On the live picks noon swings less, as the replay said:
  sd 1.83% against 2.23% to the close. That is 18% less, and the bootstrap
  keeps the ratio above 1.0.
* **The cost does not.** Leaving at noon gave up 0.23% a position
  (t = −2.45). Both halves point the same way (−0.14% and −0.35%).
* **The control decides the label.** A planted 0.20% cost shows only at
  t = 2.13, below 3. As registered, the verdict is UNDERPOWERED, rejection #68.
* **The WORSE flag is up.** The mean is below −0.05% and its t is at or below
  −2. As registered, that is named within #68: the noon exit is shown to cost
  money at the registered flag's own threshold, though the record cannot see
  0.20% at t = 3.

## Beside it, never judged

| Slice | Positions | Mean d | t | Swing ratio |
|---|---:|---:|---:|---:|
| The Top 2's own picks (`top2/pick`) | 42 | −0.04% | −0.20 | 1.16 |
| LONG | 85 | −0.01% | −0.07 | 1.18 |
| SHORT | 94 | **−0.43%** | −2.32 | 1.23 |
| September | 30 | −0.16% | −0.94 | 1.02 |
| October | 95 | −0.20% | −1.29 | 1.33 |
| November (to 11-17) | 54 | −0.33% | −2.41 | 1.11 |

* **The afternoon is where the money was.** Held to the close the positions
  made +0.13% a position; out at noon −0.10%. The afternoon alone, signed to
  the pick: +0.23%, t = 2.45.
* **Noon did better on 47% of positions.**
* **The cost sits in the shorts:** −0.43% a short, against −0.01% a long. On
  the shorts the morning went against them, and the afternoon came back.
* **The Top 2 alone** (42 positions) shows almost no cost (−0.04%) and 16%
  less swing. That is the population the note is printed under, and it is far
  too small to judge.
* **The lab's other exits on the same positions, against holding to the close:**

  | Exit | Positions | Mean minus close | t | Swing ratio |
  |---|---:|---:|---:|---:|
  | The pick's own "wrong if" stop | 71 | −0.06% | −0.56 | 1.02 |
  | A 0.5 ATR stop | 179 | −0.10% | −1.14 | 1.07 |
  | A 1 ATR stop | 179 | −0.06% | −1.45 | 0.98 |
  | Hedged with its sector fund | 138 | +0.13% | +1.11 | 1.14 |

  None reaches any bar. The hedge line printed under a one-sided Top 2 reads
  the same lab and says the same thing.

## What it says

* On the live picks, leaving at noon swung about 18% less, as the replay said.
* It did **not** come for free: it gave up about 0.23% a position, mostly on
  the shorts. The record cannot pin that at the registered bar, but it points
  the other way from "no worse".
* "The afternoon added nothing" is not what the live record shows. The
  afternoon added +0.23% a position (t = 2.45, short of 3).

## What changes

* **Nothing live.** No pick, size, record or rule changes, and the noon check
  is unchanged.
* **A wording proposal goes to the owner** (the registered consequence of a
  failure). The note under every Top 2 would keep the replay's finding and add
  the live one, for example: "On the live picks (179 positions, 09-17 → 11-17)
  leaving at noon swung 18% less but gave up 0.23% a position (t = −2.45,
  short of the bar), most of it on shorts." The note is not changed until the
  owner says yes.

## Not blind, said plainly

The evening review has printed the lab's running comparison every evening
since 10-11, and the noon exit is among its rules. I did not read those
numbers before writing the registration. The bar is day-130's, with stricter
legs added, fixed before this look.

## Cost

None: the committed lab file, 0.9 s, no API call, no model.

## Not claimed

That any exit makes a pick right more often. Say so plainly when asked.
