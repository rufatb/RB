# Day-137b — the newest DeepSeek on the day-117 replay (owner, 2026-10-21)

Registered BEFORE any call below was made. This is an amendment to
`PREREGISTER_day134_models.md`: one more model under its protocol and bar,
none of it changed.

The owner: "maybe we can use deepseek new model and FMP in a better way that
can make these decisions and picks more informative and better in terms of
accuracy."

## The model

* **Asked:** `deepseek/deepseek-v4.1-flash-1017` on OpenRouter, released
  2026-10-17, the newest DeepSeek listed there ($0.15/M in, $0.60/M out).
* **Why OpenRouter:** the DeepSeek account itself still serves only
  `deepseek-flash` and `deepseek-v4-pro` (`models.list`, 2026-10-21). v4-pro
  has been the production desk since 2026-09-29.
* **Settings:** single-shot, with the model's default reasoning, as day-134b
  ran R1.

## Protocol (day-134b's, unchanged)

1. **Contamination probe.** Five names on three replay dates. CONTAMINATED
   means at least 5 answers, a median absolute error ≤ 5%, and an error under
   half the naive guess's.
   * A model released in October may have seen July–September 2026.
   * If it is contaminated, the replay is VOID and the model can only be
     judged forward.
2. **Positive control.** The desks' planted universe, 5 runs; the bar is 4 of
   5 clean.
3. **Replay.** The 59 day-117 sessions and the production desk question
   (`deepseek_opportunities.rank`: `SYSTEM_PROMPT`, `build_request` rows,
   `_clean`, `check_levels`, `check_basis`), scored by `model_picks.score_one`.

**The bar, day-117's.** Skill needs ALL of:
* a session-clustered mean per pick > 0 with t ≥ 2.0;
* a hit rate beating 2,000 random-pick draws from the same pools (p < 0.05);
* the same sign in both halves.

**Descriptive only:** the paired difference against the day-117 DeepSeek
answers on the same sessions.

## Budget

At most $1.50 of OpenRouter credit. The account has $5.75 left of $20, and the
mornings spend about $0.84 a day. The run stops before the cap, and the
sessions not reached are named.

## What follows

* **PASS:** a forward shadow desk is PROPOSED to the owner, under its own
  registration. It is never sized and never in the Top 2 before 40 live
  sessions.
* **FAIL:** nothing changes.

Script: `replay_or_models.py --model v41flash --summary
data/replay_day137b_deepseek41.json --budget 1.5`.
