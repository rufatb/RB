# Day-145 — best first: does a model's first-named nomination beat its second? (council lab item 5)

**Registered 2026-11-03, before any return in this test was computed.** Nothing
here changes a live pick, a size, the Top 2, a prompt or the email.

## Why

* **Item 5 asked whether one pick a day beats two.** The test it named was
  the counted Top 2 (`top2count`): its first slot against its second.
* **That population cannot answer it.** Sizing on 11-03 read counts only, no
  outcome:
  * the counted Top 2 filled both slots on 6 of its 16 sessions (5 a long
    and a short, 1 on one side);
  * the order of its slots survives only in the frozen reports, and the
    10-25 reset emptied `reports.sqlite3`, so the order is known for one of
    the six (11-02);
  * the printed Top 2 filled both slots on 11 of its 18 sessions.

  Six or eleven pairs could only detect a difference of about 2.5–3% a pick.
  Item 5 as written is closed without a test; it is not a numbered
  rejection.
* **Day-144 makes the question sharper, on a larger population.**
  * The live Top 2 is now Claude's FIRST-named long and short. The rule
    assumes the first-named is the model's best.
  * Every model's nominations are recorded (two per side, best first, forced:
    day-129), so the record holds the first-against-second comparison for
    every model, side and session since 10-14.
  * Each model always put its higher own confidence first: 30 of 30 pairs
    each for Claude, DeepSeek and Gemini, with no ties. So the test is also
    one of each model's own confidence within a side.
* **One pick a day is then arithmetic.** With no measured edge, one pick
  costs 0.13% a session where two cost 0.26%. Under day-144 the two are always
  one long and one short, so same-side stacking cannot happen. Whether the
  pick to keep can be told apart is this test.

## What was already seen (not blind)

* **Claude's arm is not blind.**
  * Day-144's `--before` replay read Claude's first-named picks: 24 picks,
    58% right, −0.11% gross.
  * On 11-02 Claude's second-named picks won (CP.TO, AC.TO) while its
    first-named lost.
* **The scoreboard prints each model's nominations pooled, both positions
  together** (on 11-03):

  | Model | Right | Gross |
  |---|---|---|
  | Claude | 34/56 | +0.11% |
  | DeepSeek | 29/56 | +0.24% |
  | Gemini | 29/56 | −0.27% |

* **The first-against-second split of DeepSeek's and Gemini's nominations has
  not been computed.**
* **So the verdict is on all three models together.** Claude's arm alone is
  reported beside it and is descriptive only.
* **The prior.** Day-132b's T1: on 479 replay picks the top-confidence pick
  did 0.20% worse than the rest (UNDERPOWERED, rank correlation −0.02).

## The population

* **A pair** is (session, model, side) for model ∈ {Claude, DeepSeek, Gemini}
  and side ∈ {LONG, SHORT}, over sessions **2026-10-14 → 2026-11-03**. That is
  the first recorded nominations through the run's last scored session; the
  window does not move.
* **Both nominations are taken from the record.** They come from
  `data/model_picks.csv`, kind `nominated`, and both must be scored
  (`r_pct`).
* **The order** comes from the frozen report when it holds the session
  (`intraday.council.nomination_picks`, `.rb-state/reports.sqlite3`).
  Otherwise it comes from that evening's review (`data/reviews/DATE.json`).
  * The review keeps the nominations it scored in the nomination order, in
    section "Nominated (forced)". There the order is known only when both
    names on that side were scored.
  * These are day-144's sources.
  * Where both exist they agreed on 34 of 34 sides. Two reviews held one name
    only, and six sessions (10-26 → 11-03) have no review copy, or none yet.
* **Left out, and counted:** a pair not scored, or whose order is unknown.
* **Sized today** (counts only):
  * 84 pairs over 14 sessions (10-14 → 11-02), 6 a session: 36 ordered by the
    frozen reports and 48 by the reviews;
  * 11-03 adds 6 once tonight's scoring fills them, for 90 pairs over 15
    sessions.
* **The unit is the pair.** A ticker two models nominated sits in two pairs.
  Everything is clustered by session.

## The measure and the bar

* **y** is the record's `r_pct`: the 09:45 bar's close to the close, signed
  to the side.
  * Both picks in a pair pay the same 0.13% round trip, so the difference is
    the same gross or net.
  * Each arm's net mean is reported.
* **d** = y(first-named) − y(second-named), for each pair.
* **The statistic.**
  * Each session's D is the mean of its pairs' d.
  * t = mean(D) / (sd(D) / √n) over the n sessions.
  * This is day-144's paired t (`claude_leads._t`).
* **FIRST_BETTER** (the order carries information) needs all of:
  * mean(D) > 0 with t ≥ 3.0;
  * a sign-flip placebo p < 0.01:
    * each session's D is flipped as a unit;
    * 10,000 draws, seed 145, one-sided;
    * p is the share of draws with t at or above the real one;
  * both halves of the sessions by date positive (the first ⌊n/2⌋ against the
    rest).
* **SECOND_BETTER** is the mirror image: t ≤ −3.0, the other tail's placebo
  p < 0.01, and both halves negative.
* **Otherwise NULL.**
* **Planted control** (house rule 10, `edge / sd`):
  * every d is centred on zero by subtracting the mean d;
  * 1.0% is added to every first-named pick, and the test is re-run;
  * it must show at t ≥ 3, or the verdict is UNDERPOWERED rather than NULL;
  * the smallest detectable effect (80% power at t = 3) is reported.
* **One look.** This history has no second look.
* **Rejection #60.** Anything but FIRST_BETTER is rejection #60, under its
  label.

## Reported beside the verdict (descriptive, never a verdict)

* **By model** (Claude's not blind) and **by side**.
* **Each arm on its own:** picks, right, gross and net mean.
* **The live rule's arm:** Claude's first-named long and short, each session,
  against its second-named pair, net. This is the day-144 question in its
  narrowest form.
* **Own confidence** as a continuous ranker: pairs by the size of their
  confidence gap.

## What follows

* **FIRST_BETTER** goes to the owner as support for day-144 taking the
  first-named names. Nothing changes.
* **SECOND_BETTER** goes to the owner: the live rule would be taking each
  model's weaker-ranked names. Any change is the owner's decision, under its
  own registration.
* **NULL or UNDERPOWERED** is rejection #60, recorded in `STRATEGY.md`.
  * "Best first" is then not a ranking the record can see.
  * One pick a day would halve the cost and the swing, with nothing to say
    which of the two to keep: a size choice for the owner, not a rule from
    this test.
* **The script** is `best_first.py`, committed before the look. Its summary
  is `data/best_first_day145.json`.
* **It runs in the next lab slot**, after the 11-03 evening scoring, on the
  record alone: no API call of any kind.
