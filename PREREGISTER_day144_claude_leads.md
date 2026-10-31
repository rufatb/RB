# Day-144 — Claude's picks lead the Top 2; the guardrails come off (owner, 2026-10-30)

**Registered 2026-10-31, before the first session it governs (2026-11-02).**
This is the owner's decision, not a test result. Nothing here is claimed to
raise accuracy.

## The decision

* **The owner, 2026-10-30:** "Claude picks are doing much better than council.
  I want council to be led by Claude picks."
* **Asked how, they chose:**
  * "Claude's best long + short": the Top 2 is Claude's first-named long and
    first-named short from its council nominations;
  * on the three guardrails: "Let's get rid of these guardrails rules as they
    may be interfering with our pick accuracies."

## What runs from the morning of 2026-11-02

* **The Top 2** (`council.CLAUDE_LEADS = True`, rule `day144-claude-leads`).
  * The picks are the first long and the first short in Claude's nominations
    (`council.json` `nomination_picks.claude`, best first, day-129). Claude
    names them through OpenRouter, stateless (day-126), before the table is
    built.
  * Each carries Claude's own confidence, reason and "wrong if".
  * The council still sits with its prompt, rounds, members and frozen rule
    unchanged.
    * Its vote on each of Claude's picks is printed beside the pick and cannot
      replace it.
    * A pick the council never voted on says so ("not on the council's
      table").
  * The Top 2 is one long and one short, so it never stacks one side.
  * If Claude named only one side, there is one pick and the section says the
    other slot is empty.
* **The fallbacks.**
  * Claude's nominations are missing (an OpenRouter error, or none): the
    council's own Top 2 stands, labelled "Claude's picks were unavailable
    today (…); the council's own Top 2 stands". The record then carries the
    council's rule.
  * The council did not sit but Claude nominated: Claude's picks, labelled
    "without its vote".
  * Neither: the counted rule, as before.
* **The guardrails are off.** All three switches are kept; each is one line to
  turn back on.
  * `council.SKIP_MOVERS = False`: the last session's big movers (day-135c/d).
  * `council.SKIP_WILD = False`: the morning's widest-swinging names (day-137).
  * `entry_checks.VOID_TOP2 = False`: nothing is voided at 09:46 (day-120
    E1). The 09:31 open check still reports VOID or STILL VALID, and now adds
    that the 09:46 report no longer drops a VOID pick.
  * The big-mover caution line still prints under a pick (display only,
    day-135c).
* **Where it shows:**
  * the council flash and its subject;
  * the 09:31 open check;
  * the report email (Top 2 table, hero, and "CLAUDE'S TOP 2 ONLY" in the
    subject when no desk is sized), the full report and the page;
  * the noon check and the picks-only email.

  The council's own choice prints under the picks: "recorded beside and not a
  pick".
* **Unchanged:**
  * the desks and the nomination prompt;
  * the council's prompt and rule;
  * the memory council, which keeps the council's own rule;
  * the counted shadow, Part 6 and the scorer.

## The record

* **`top2/pick`** from 11-02 is Claude's picks, with `prompt_version`
  `day144-claude-leads` and Claude's own confidence.
* **`top2council/pick`** is new: the council's own decision under its frozen
  rule (now with no pass-over rule and no 09:46 check), carrying its own rule
  version.
  * It is never sized and never pooled (`model_picks.POOLED_EXCLUDED`), and it
    stays out of the execution lab's model pool.
  * The review scores it as "Council's own choice (shadow)", out of the
    lessons.
  * Labelled "not a pick", it has a scoreboard row beside "Top 2 led by
    Claude", from the first scored session. That comparison is the owner's
    question.
* **The other shadows.**
  * `top2mover` and `top2wild` stop accruing, because their rules are off.
  * `top2runner` stops while Claude leads, because no runner-up is shown.
  * `top2count` and `top2memory` continue.
* **"The council's own Top 2" per session** is `model_picks.council_rows`:
  `top2` before 11-02 and on a fallback day, `top2council` after.
  * The memory council's box and its registered comparison (day-130) read it.
  * That test therefore still compares two councils that differ only by
    memory.
* **Day-140 arm A** reads the live Top 2 (`top2/pick`) as registered, "the
  population a live rule would act on".
  * From 11-02 that population is Claude's picks, with no pass-over rule and
    no 09:46 check. The change is recorded here, and its verdict is split by
    `prompt_version`.
  * Arm B (Round 1 against the discussion) reads the council's own picks and
    is unaffected.
* **The scoreboard's "Top 2" row** keeps its label and pools both periods. The
  two rows under it split them.

## The forward comparison (`claude_leads.py`)

* **The question.** Does following Claude's two picks do better, net, than
  following the council's own choice?
* **The unit** is a session whose printed Top 2 was Claude-led and whose picks
  in both arms are all scored.
* **The measure.** Per session, d = Claude-led net − the council's own net.
  * Each arm's net is the mean of (r_pct − 0.13%) over its picks: the record's
    09:45 → close, less the measured round trip.
  * The council counts 0 on a day it chose nothing (no trade, no cost).
* **The harm check at 20 sessions.** t ≤ −2 → HARM, and the owner is told.
* **The decision at 40 sessions** (about 2026-12-29):
  * CLAUDE_BETTER: t ≥ 3, a one-sided sign-flip placebo p < 0.01 (10,000
    draws, seed 144), and both halves positive;
  * COUNCIL_BETTER: t ≤ −2;
  * otherwise NO_DIFFERENCE.

  Each verdict goes to the owner; nothing switches by itself. The smallest
  difference t = 3 can see is printed at the look.
* **The planted control** is in `tests/test_claude_leads.py`:
  * a planted +1.0% a session (sd 0.5) reads CLAUDE_BETTER;
  * a zero-mean series reads NO_DIFFERENCE;
  * −1.0% reads COUNCIL_BETTER;
  * twenty sessions of −1.0% read HARM.
* **Where it shows.** The evening review prints it every day
  (`daily_review.claude_led_section`), and `python claude_leads.py --verdict`
  gives the decision.

## Before the change (descriptive, never part of the test)

* **What the owner saw: the record of 10-14 → 10-30, 13 sessions of
  nominations.**
  * Claude's nominations: 50 picks, 30 right (60%), +0.06% gross, −0.07% net.
  * DeepSeek's: 51 picks, 27 right (53%), +0.20% gross, +0.07% net.
  * Gemini's: 52 picks, 28 right (54%), −0.26% gross.
  * The printed Top 2 (09-29 → 10-28): 25 picks, 10 right (40%), −0.49%
    gross, −0.62% net.
* **The rule replayed on the record, 12 sessions, 10-14 → 10-29.** From
  `python claude_leads.py --before .rb-state/reports.sqlite3`; summary in
  `data/claude_leads_before.json`.
  * Claude's first-named long and short: 24 picks, 14 right (58%), −0.11%
    gross, −0.24% net.
  * The printed Top 2: 10 picks, 4 right, −0.98% gross. It stood aside on 5
    sessions.
  * d: +0.43% a session, t = 1.02.
  * Without 10-15, when the council's two shorts lost 4.2% and 3.6%: +0.13%,
    t = 0.40.
  * Claude's second-named picks: 24 picks, 14 right, +0.05%. Its own ordering
    carried nothing on this record.
  * **Where the nomination order came from:**
    * the frozen report on 5 sessions and that day's review on 8;
    * on the 9 side-sessions where both exist, they agree;
    * 10-30 is left out, because CNQ.TO went unscored.
* **So:**
  * the lead the decision rests on is t ≈ 1, and mostly one day;
  * Claude's first-named picks lost money gross on this record too, just less
    than the council's.

## What the guardrails did (their registered tests)

* **Both size rules were variance results:**
  * after a move of ≥ 1 ATR, the next session swings 1.24× wider (day-135c
    R2);
  * the morning's widest-swinging names swing 2.46× the rest (day-137 H3).

  Neither leaned either way. Removing them should widen the swing and leave
  the expected result alone.
* **E1 at 09:46** showed no accuracy difference on the replay (day-120).
* **With them off,** the Top 2 can hold a big mover or one of the
  widest-swinging names. The caution line names the big movers.

## Dependencies and reverting

* **OpenRouter.** Claude's nominations come through it. On an HTTP 402 (no
  credit, as on 10-29) the council's own Top 2 stands, labelled. Keep the
  credit up.
* **Reverting.** Each switch is the owner's call:
  * `council.CLAUDE_LEADS = False` restores the council's own Top 2;
  * the three guardrail switches restore their rules.
