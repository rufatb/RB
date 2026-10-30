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
| 1 | **A stop within reach, on the record** | Day-140 arm A's question on 172 picks instead of ~60 | The forward test can detect only ~1.5–1.9% a pick | The record's desk picks (Claude, DeepSeek, Gemini; selected and nominated; 09-17 → 10-23, 10-15 left out): own level within 1 ATR of the 09:45 entry vs not | None | Done: FAIL, rejection #57 (`AUDIT_day141_reach_history.md`) |
| 2 | **Ask the news desk about the open** | The prompt asks 09:45 → close; day-139 scores open → close | The day-122 reads from the open: +0.09%, t = 0.71 | One registered re-worded prompt, one look, on the 419-release archive (the bodies are refetched from the wire; the probe found no memory of prices) | DeepSeek, ~130 calls (one per session and wording) | Done: NULL, rejection #58 (`AUDIT_day142_newsdesk_open_prompt.md`) |
| 3 | **Skip a pick the open already paid** | The owner's day-138 rule: "the price shouldn't already have changed" | Continuation after a further gap was null (day-132); never tried as a remove-only gate | The record's desk picks whose open gap ran ≥ 1 ATR their way, vs the rest | None | Closed without a test: the record cannot judge it (1 of 189 positions opened ≥ 1 ATR its way), and history (#42) leans against it |
| 4 | **A report-day size rule** | A name reporting before the open swings wider; skipping it is a size rule, like day-137's | Report-day direction was null (#46); size untested | Ten years of daily bars, volume-confirmed report dates (day-135b): next-session sd on report days vs others | None | Registered (`PREREGISTER_day143_report_day.md`): 09:45 → close on FMP 15-minute bars, beyond the two live rules, with a point-in-time S&P 500 check; runs next slot |
| 5 | **One pick a day** | Half the cost, and no same-side stacking | One position per side failed as a size rule (#51); the top pick alone vs two is untested | The record's counted Top 2 (`top2count`, from the frozen reports): the first slot vs the second, net | None | Queued |
| 6 | **Round 1 against the discussion, on history** | Arm B forward needs 40 sessions where both arms pick | The 14 councils before the test (day-140 backfill) show how often the arms differ | A council replay of Round 1 alone, once the day-117 pools are rebuilt (their cache is gone). The backfill: the arms differed on 5 of 12 sessions | DeepSeek and Gemini calls | Queued |
| 7 | **Weight the desks by their record** | The review's point 5 | No desk's record is beyond \|t\| = 1.1 | — | — | Not before a desk clears a bar |

**2026-10-26: the replay caches are gone.** The container reset wiped
`.rb-state`, including the day-117 replay cache and the FMP caches. The
backlog now uses the committed record, or refetches.

## Done

| Date | Step | Result |
|---|---|---|
| 2026-10-24 | Day-140 registered and fixed (`PREREGISTER_day140_fixpack.md`) | Forward from 10-26; no result yet |
| 2026-10-24 | Day-140 backfill: the 23 live picks before the test (descriptive) | Stop in reach: 7 picks +0.47%, the 16 without −0.80% (t = 1.8, with 10-15 among them). The discussion changed the picks on 5 of 12 sessions: its own 0.00%, Round 1's −0.52% |
| 2026-10-26 | Item 1 registered on the record (`PREREGISTER_day141_reach_history.md`), since the replay cache was wiped | Runs next slot |
| 2026-10-27 | Item 1 run (`reach_history.py`, `data/reach_day141.json`) | FAIL, powered (rejection #57): kept 39 picks −0.05%, dropped 119 +0.12%, t = −0.72; a planted 1% shows at t = 4.17. With 10-15 put back: +0.12%, t = 0.32 |
| 2026-10-28 | Item 2 registered (`PREREGISTER_day142_newsdesk_open_prompt.md`): day-122's prompt with its window moved to the open, on the day-122 releases, judged by day-139's bar (seed 142) | Runs next slot |
| 2026-10-29 | Item 2 run (`replay_news_open.py`, `data/replay_day142_open_prompt.json`; 133 DeepSeek calls) | NULL, powered (rejection #58): 418 calls +0.11% open → close against XIU, t = 0.99, placebo p = 0.19; a planted 0.5% shows at t = 4.41. Day-122's prompt re-asked: +0.05%; paired difference +0.06%, t = 0.46 |
| 2026-10-30 | Item 3 sized before any test (gaps and ATR only; no outcome read): of the record's 189 positions (09-17 → 10-29, each name, side and day once), the open ran ≥ 1 ATR the pick's way once, ≥ 0.5 ATR 15 times (8 sessions), ≥ 0.25 ATR 43 times | Closed without a test. A gate at 1 ATR cannot be judged on the record. On history a ≥ 1 ATR gap continues slightly from the open (#42, t = 2.63), the opposite of the premise. Not a numbered rejection |
| 2026-10-30 | Item 4 registered (`PREREGISTER_day143_report_day.md`; names pinned in `data/report_day143_names.json`) | Runs next slot |
