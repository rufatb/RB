# AUDIT day-155 — the faded gap, Claude's short thesis: UNDERPOWERED (rejection #70)

Council lab item 17, registered 2026-11-24 (`PREREGISTER_day155_faded_gap.md`,
with amendment 1), run once on 2026-11-25 by `python faded_gap.py` (64bbf9d,
committed before it ran). Summary: `data/faded_gap_day155.json`. The bars come
from day-143's cache, downloaded again that morning by `python report_day.py
--fetch` (amendment 1). The live record's prior sessions are FMP daily bars
fetched at the run. No model was asked.

## The question

On 11-24 both of Claude's shorts rested on one setup: a name that gapped a
normal day or more at the open, then closed back against its gap (HUT.TO
"+19.4% gap faded … below vwap"; CLS.TO "+13.8% gap reversed"). The brief shows
the setup to every model as `gap_atr` with the prior open and close.

Does following the fade earn anything the next session, from 09:45 to the close
against XIU? Following means SHORT after a faded up-gap and LONG after a faded
down-gap.

* **The setup, on the prior session d−1** (the brief's arithmetic,
  `daily_technicals.context`, on dividend-adjusted daily bars):
  * ATR is the mean of the 14 true ranges ending at d−1, each against its own
    prior close;
  * `gap_atr = (open(d−1) − close(d−2)) / ATR`;
  * a faded up-gap is gap_atr ≥ 1 with close(d−1) < open(d−1), so SHORT; a
    faded down-gap is the mirror, so LONG;
  * the name's 15 bars ending at d−1 must be the market's consecutive sessions.
* **The code is the registration's.** The setup in `faded_gap.py` is the
  counting code run at registration (before any return), moved over unchanged.
  `tests/test_faded_gap.py` checks it against that code verbatim on random
  series with holes.
* **The outcome on d:** side × (the name's 09:45 → close − XIU's), in %. Each
  (name, session) is one event and one pick.

## The data

| | Now | Registered |
|---|---:|---:|
| Primary events (150 names, 15-minute bars, 2024-01-02 → 2026-10-29) | **1,209** | 1,209 |
| — SHORT / LONG | 510 / 699 | 512 / 697 |
| — sessions | 359 of 709 | 357 of 707 |
| — names | 150 | 150 |
| — from a gap of 2 ATR or more | 160 | 159 |
| (a) Ten-year daily panel, same names, 2016-01-04 → | 4,211 | 4,218 |
| — sessions / SHORT | 1,597 / 1,970 | 1,599 / 1,972 |
| (b) Point-in-time S&P 500, daily, 2016-01-04 → | 14,302 | 14,303 |
| — sessions / SHORT / names | 2,361 / 6,800 / 662 | 2,360 / 6,805 / 661 |

* **The download** (amendment 1): 151 Toronto files with no failed and no
  capped calls. There were 717 S&P 500 files, 13 of them without daily bars,
  and no failed call. The membership rebuild met 59 glitches in FMP's change
  history (35 additions and 24 removals that disagree with the record), as
  day-143's did, and none were guessed.
* **The counts moved slightly,** as amendment 1 allowed. FMP now serves two
  more 15-minute sessions in the window (709, against 707) and has revised some
  daily bars, so a few events changed side or session. The total is unchanged
  at 1,209.
* Every secondary event counted was scored: none lacked its bar on d.

## Result: UNDERPOWERED

| Leg | Bar | Value | Met |
|---|---|---:|---|
| Mean, session-clustered | > 0 with t ≥ 3 (FOLLOWS) or < 0 with t ≤ −3 (REVERSES) | **−0.060%** an event, t = **−0.52** (se 0.115) | no |
| Four blocks, equal events in date order | all one sign | +0.04%, −0.10%, +0.16%, −0.34% | no |
| Placebo (2,000 draws, seed 155, the same name ≥ 5 sessions away) | p < 0.01 | 0.91 toward FOLLOWS, 0.09 toward REVERSES | no |
| Above the 0.13% round trip (FOLLOWS) | mean − 0.13 > 0 | −0.19% | no |
| (a) Ten-year daily panel, open → close against XIU | the same sign | +0.031% (t = 0.38) | no |
| (b) Point-in-time S&P 500, open → close against SPY | the same sign | −0.007% (t = −0.22) | no |
| **Control: a planted 0.30% an event** | t ≥ 3 | **t = 2.61** (0.30 / se) | **no** |

* **The smallest effect detectable at 80% power is 0.32% an event,** just above
  the 0.30% the registration chose as the smallest edge that would matter. The
  events are the list's wildest name-days, so they are noisy. The draws'
  standard deviation is 0.05%, but the clustered se is 0.11%.
* **So the verdict is UNDERPOWERED,** whatever the sign. The estimate is
  slightly negative, the blocks disagree, and the two secondary panels disagree
  with each other. It is **rejection #70.**

## Beside the verdict (descriptive, never a verdict)

| Split, 09:45 → close against XIU | Events | Mean | t | Right |
|---|---:|---:|---:|---:|
| SHORT after a faded up-gap | 510 | −0.04% | −0.29 | 48% |
| LONG after a faded down-gap | 699 | −0.08% | −0.44 | 49% |
| Gaps of 2 ATR or more | 160 | −0.28% | −1.16 | 46% |
| A full reversal (d−1 closed back beyond d−2's close) | 177 | −0.17% | −0.83 | 49% |
| Not a full reversal | 1,032 | −0.04% | −0.32 | 49% |
| The held gap, followed (LONG after a held up-gap, SHORT after a held down-gap) | 959 | −0.05% | −0.37 | 51% |
| — LONG after a held up-gap | 458 | +0.04% | 0.23 | 52% |
| — SHORT after a held down-gap | 501 | −0.14% | −0.96 | 50% |

* **The other windows on d, faded events, for the side:**
  * open → 09:45, before the entry: −0.06% (t = −1.05), 47% right;
  * 09:45 → noon: −0.07% (t = −0.77).
* **By year:** 2024 +0.06% (330 events), 2025 −0.05% (516), 2026 −0.19% (363).
  None is near a bar.
* **The secondary panels' legs:**
  * ten years on the 150 names: SHORT +0.17% (t = 1.80, 1,970 events), LONG
    −0.09% (t = −0.80, 2,241);
  * the point-in-time S&P 500: SHORT +0.05% (t = 1.06, 6,800), LONG −0.06%
    (t = −1.58, 7,502).

  On open → close daily bars the short leg leans the fade's way, and the long
  leg leans against it. In the tradable window from 09:45 on the primary panel,
  both legs are slightly negative. The ten-year panel's years swing between
  −0.39% (2020) and +0.50% (2021).
* **The live record** (Claude's scored council nominations 10-14 → 11-24,
  112 over 49 names; every prior session was read):
  * 3 followed a faded gap, and all 3 were right, +2.38% on average:
    * LONG SHOP.TO on 11-04, +3.42%;
    * SHORT CLS.TO on 11-24, +3.49%;
    * SHORT HUT.TO on 11-24, +0.23%;
  * the other 109 were 64 right, +0.18%;
  * none went against a faded gap.

  Three picks are an anecdote, far too few to judge.

## What it changes

* **Nothing live.** No tie-break by the setup, and no pass-over of a Claude pick
  that follows one.
* **The prompts are not re-worded** against this result.
* **The setup stays in the brief** as context (`gap_atr` with the prior open and
  close), as it always was.

## Not blind, said plainly

* Day-132 (#47), day-152 (#67) and day-117's field scan were known at
  registration, and the live record's totals were known.
* No split of the faded gap against a next-session return had been computed
  on any panel before this run.

## Cost

None beyond the FMP plan:
* the cache's re-download (about 5,700 Toronto and 2,200 S&P 500 calls);
* 50 daily calls for the live record.

No model was asked and nothing was spent on OpenRouter.
