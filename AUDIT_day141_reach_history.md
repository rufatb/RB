# Day-141 — a stop within reach, tested on the record: FAIL (rejection #57)

**Registered** 2026-10-26 in `PREREGISTER_day141_reach_history.md` (cd011b6),
before any return was computed. **Run** 2026-10-27 in the council lab's slot
by `reach_history.py`; summary `data/reach_day141.json`. Nothing live changes.

## The question

Day-140 arm A keeps a Top 2 pick whose own "wrong if" is within one normal
day (ATR) of its 09:45 entry, and drops the rest. Forward, it can see only a
difference of about 1.5–1.9% a pick by its 40th session. This test asks the
same question of the record's desk picks, which are about three times as many.

## The population

* **The picks.** 172 scored picks of Claude, DeepSeek and Gemini (selected and
  nominated), over 21 sessions from 2026-09-17 to 10-23. 85 carry a level.
  This matches the registration.
* **The ATR.** Computed by `daily_technicals.from_series` on Yahoo daily bars
  cut before each session. No pick was excluded for want of one.
* **The primary test** has 158 picks over 20 sessions; 10-15 is left out, as
  registered.
* **Dropped, by reason:** 80 with no "wrong if", 32 out of reach, and 7
  already crossed at the entry.

## The verdict: FAIL

| Group | Picks | Right | Mean, 09:45 → close |
|---|---:|---:|---:|
| Kept: a stop within one normal day | 39 | 18 (46%) | −0.05% |
| Dropped | 119 | 62 (52%) | +0.12% |

* **The test:**
  * the difference is −0.17% a pick, t = −0.72;
  * the label-shuffle placebo p is 0.67 (2,000 draws, seed 141);
  * the halves disagree, +0.30% and −0.35%.

  A difference ≤ 0 is a FAIL as registered.
* **Net of the 0.13% round trip,** the kept picks average −0.18%.
* **The planted control.** With each group centred and 1.0% added to every
  kept pick, t = 4.17, so it is detected. The smallest detectable effect at
  80% power is 0.92% a pick.
* **So this is a powered FAIL.** The gate would have shown a gap of about
  0.9% or more, and the record shows none. Its point estimate is on the wrong
  side.

## Beside the verdict (descriptive, never a verdict)

* **With 10-15 put back:** +0.12%, t = 0.32.
  * All 14 of that day's picks were dropped: 8 with no level and 6 out of
    reach.
  * They averaged −2.61%, with 4 right. That one day turns the sign, which is
    why the registration held it out.
* **Unique positions** (a position is kept when any proposer's level is in
  reach): 35 kept −0.01%, 83 dropped +0.01%, t = −0.10. Every proposer of a
  position had the same recorded outcome.
* **Any level against none:** 78 picks −0.07% (42 right) against 80 picks
  +0.22% (38 right), t = −0.63. Having a level at all says nothing either.
* **By model** (kept minus dropped):

  | Model | Difference | t | Kept picks |
  |---|---:|---:|---:|
  | Claude | −0.13% | −0.52 | 10 |
  | DeepSeek | +0.32% | +0.51 | 9 |
  | Gemini | −0.36% | −0.77 | 20 |

* **By kind:** selected −0.16% (t = −0.42), nominated −0.13% (t = −0.34).
* No split is near a bar, and the models disagree on the sign.

## What it means

* **The reach gate does not sort desk picks.** Picks whose stop an ordinary
  day can reach did no better than picks with a far stop or none.
* **The day-140 backfill's split came from one day.** On 23 live picks it was
  +0.47% against −0.80% (t = 1.8), and that gap was 10-15's losing shorts.
* **The open check's "OUT OF REACH" label (day-135) stays.** It describes the
  stop truthfully and was never claimed to sort picks.
* **Day-140 arm A runs on unchanged,** forward and on the Top 2 only, as both
  registrations say. This result says not to expect it to pass.
* **No rule is proposed.** This is rejection #57.

## Not claimed

* That a stop is useless as risk control. This measures the pick's
  09:45 → close result, the record's yardstick, not a stop-loss order's fill.
* Anything about any single day's picks.

## Files

* `reach_history.py`: the test. It reuses `fixpack.gate`, `fixpack.two_group`
  and `fixpack.arm_a` (seed 141).
* `tests/test_reach_history.py`: 5 tests covering the population, the gate's
  labels and exclusions, the planted control and the verdict's mapping.
* `data/reach_day141.json`: the summary.
