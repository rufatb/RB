# The council lab: one registered improvement step a weekday

The owner, 2026-10-24: "Continue creative improvements for council picks
logic every morning."

## The slot

* **When.** Weekdays at 10:10 ET, after the morning's email is out, a
  scheduled task in this session ("RB council lab") runs one step of this
  file.
* **Until when.** The step ends by 11:40 ET, so the noon check (11:58) never
  waits behind it.
* **What a step is:** one of
  * write and commit a registration;
  * run a registered test on history;
  * write up a result.

  An idea that needs more than one slot carries on the next weekday.
* **If the morning's delivery is not done** when the slot fires, the slot does
  nothing until it is.

## The rules (the house rules, restated for the slot)

1. **Register first** (`PREREGISTER_*.md`, committed before any return is
   computed). The bar never moves: t ≥ 3 by session plus a placebo, a planted
   control, the smallest detectable effect stated, net of the 0.13% round
   trip.
2. **History before forward.** Test on what is already held:
   * the day-117 replay pools;
   * the day-122 release archive;
   * FMP 5- and 15-minute bars from 2024;
   * ten years of daily bars.

   A forward shadow is only for an idea that passes, or one history cannot
   test.
3. **Never judge a long-only or event rule on today's list** (day-138). Use the
   point-in-time check.
4. **Nothing live changes from the slot.**
   * A passing idea goes to the owner as a proposal.
   * Only a remove-only rule the owner approves goes live, under its own
     registration, as on day-135d and day-137.
   * Prompts are never re-worded against a replay.
5. **No OpenRouter spend without the owner's yes.** That means Claude, the web
   scout and other models. The credit is nearly gone and the mornings need
   it. DeepSeek, FMP and the cached data are fine to use.
6. **Every result is written to:**
   * STRATEGY.md (numbered as a rejection or an adoption);
   * an `AUDIT_` file;
   * CLAUDE.md's top section;
   * the table below.

   Then main is pushed, the session branch mirrors it, and the owner gets a
   five-line note.

## The backlog

Ordered by what a result could change, then by cost.

| # | Idea | Why it might help | What is already known | Test | Cost | Status |
|---|---|---|---|---|---|---|
| 1 | **A stop within reach, on the replay** | Day-140 arm A's question on hundreds of picks instead of ~60 | The forward test can detect only ~1.5–1.9% a pick | Day-117 replay picks: own `invalid_at` within 1 ATR of the 09:45 entry vs not; 09:45 → close | None | Next |
| 2 | **Ask the news desk about the open** | The prompt asks 09:45 → close; day-139 scores open → close | The day-122 reads from the open: +0.09%, t = 0.71 | One registered re-worded prompt, one look, on the 419-release archive (cached bodies; the probe found no memory of prices) | DeepSeek, ~40 calls | Queued |
| 3 | **Skip a pick the open already paid** | The owner's day-138 rule: "the price shouldn't already have changed" | Continuation after a further gap was null (day-132); never tried as a remove-only gate | Replay picks whose open gap ran ≥ 1 ATR their way, vs the rest | None | Queued |
| 4 | **A report-day size rule** | A name reporting before the open swings wider; skipping it is a size rule, like day-137's | Report-day direction was null (#46); size untested | Ten years of daily bars, volume-confirmed report dates (day-135b): next-session sd on report days vs others | None | Queued |
| 5 | **One pick a day** | Half the cost, and no same-side stacking | One position per side failed as a size rule (#51); the top pick alone vs two is untested | Counted Top 2 replay (day-121b): rank 1 vs rank 2, net | None | Queued |
| 6 | **Round 1 against the discussion, on history** | Arm B forward needs 40 sessions where both arms pick | The 14 councils before the test (day-140 backfill) show how often the arms differ | A council replay of Round 1 alone on the day-117 sessions. The backfill: the arms differed on 5 of 12 sessions | DeepSeek and Gemini calls | Queued |
| 7 | **Weight the desks by their record** | The review's point 5 | No desk's record is beyond \|t\| = 1.1 | — | — | Not before a desk clears a bar |

## Done

| Date | Step | Result |
|---|---|---|
| 2026-10-24 | Day-140 registered and fixed (`PREREGISTER_day140_fixpack.md`) | Forward from 10-26; no result yet |
| 2026-10-24 | Day-140 backfill: the 23 live picks before the test (descriptive) | Stop in reach: 7 picks +0.47%, the 16 without −0.80% (t = 1.8, with 10-15 among them). The discussion changed the picks on 5 of 12 sessions: its own 0.00%, Round 1's −0.52% |
