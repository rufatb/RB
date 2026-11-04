# Day-145 — best first: a model's first-named nomination does no better than its second (rejection #60)

Council lab item 5, run 2026-11-04 in one look. Registered 2026-11-03
(`PREREGISTER_day145_best_first.md`, 79eef1d), before any return was
computed. The script (`best_first.py`, 857ff4d) was committed before the run.
Summary: `data/best_first_day145.json`. Cost: none, because it reads the
record only.

## The question

Every model names two longs and two shorts for the council, best first.
Day-144's Top 2 takes Claude's first-named long and short, which assumes the
first-named is the model's best. Does a model's first-named nomination beat
its second-named one, per model and side?

## The data

* **90 pairs over 15 sessions,** 2026-10-14 → 2026-11-03: Claude, DeepSeek and
  Gemini, long and short, six pairs a session.
  * No pair was left out: every one was scored and had a known order.
* **Where the order came from.** 42 pairs from the frozen reports and 48 from
  the evening reviews. Where both sources existed, they agreed on 40 of 40.
* **Each model always put its higher own confidence first** (90 of 90 pairs;
  median gap 0.035). So this is also a test of each model's own confidence
  within a side.

## The verdict: NULL

| Bar | Registered | Result | |
|---|---|---|---|
| Size and sign | mean first − second > 0, t ≥ 3 | **+0.20% a pick, t = 0.94** | not met |
| Placebo | sign-flip p < 0.01 (seed 145) | p = 0.18 | not met |
| Halves | both positive | +0.25%, +0.15% | met |
| Control | a planted 1.0% at t ≥ 3 | t = 4.75 | detected |

* **The smallest detectable effect is 0.81% a pick.** A real ordering effect
  smaller than that could not be seen here.
* **Anything but FIRST_BETTER is rejection #60.** The mirror outcome,
  SECOND_BETTER, was not met either (t ≤ −3 would be needed).

## Beside the verdict (descriptive, never a verdict)

| | First-named | Second-named |
|---|---|---|
| All three models | 52/90 right, +0.13% gross, −0.00% net | 47/90, −0.07% gross, −0.20% net |
| Claude (not blind) | 17/30, −0.14% gross | 19/30, +0.31% gross |
| DeepSeek | 19/30, +0.95% gross | 13/30, −0.41% gross |
| Gemini | 16/30, −0.43% gross | 15/30, −0.11% gross |

* **First minus second, by model** (per session, paired):
  * Claude −0.45%, t = −1.68;
  * DeepSeek +1.36%, t = 2.40;
  * Gemini −0.32%, t = −0.70.
* **By side:** long −0.16% (t = −0.51), short +0.55% (t = 1.33).
* **Own confidence as a ranker:** pairs with a wide confidence gap read +0.24%,
  and narrow ones +0.16%. That is no gradient.
* **The live rule's arm.** Claude's first-named long and short, which is
  today's Top 2, did 0.45% a session worse than its second-named pair
  (t = −1.68). That is short of any bar, and it points the opposite way from
  the rule's premise.
* **DeepSeek's first-named picks read best** (+0.95% gross over 30 picks).
  * That is one of six splits, with no bar of its own.
  * Its paired t of 2.40 is below 3.
  * Read it as a number to watch, not a finding.

## So

* **Rejection #60.** "Best first" is not a ranking the record can see. Pooled,
  a model's first-named nomination is +0.20% a pick over its second, t = 0.94.
  A 0.81% difference could have been seen.
* **For day-144's rule:** nothing on the record says Claude's first-named pick
  is its best. Its second-named picks did slightly better, but not
  significantly. The rule is the owner's decision and stays as it is; this is
  information for them.
* **For "one pick a day":** with no ordering signal, keeping one of the two
  halves the cost and the swing, and changes nothing in expectation. Which one
  to keep would be arbitrary. That is a size choice for the owner, not a rule
  from this test.
* **Next lab item:** 8, Claude's reads over longer holds (free, on the
  record).
