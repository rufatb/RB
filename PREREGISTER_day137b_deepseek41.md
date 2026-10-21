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

---

## Results (2026-10-21, after the run; nothing above was changed)

* **Contamination: not contaminated.** All 15 probe answers were null.
* **Control: PASS,** 4 of 5 clean. One run missed the planted short.
* **Replay: FAIL (rejection #55).**
  * All 59 sessions were answered. Four first attempts were cut off in
    transfer (IncompleteRead) and asked once more.
  * 185 picks: 46.5% right, +0.017% a pick, session-clustered t = +0.81,
    placebo p = 0.81. Both halves were positive (+0.111%, +0.066%).
  * Longs: 44 of 99 right, −0.012%. Shorts: 42 of 86 right, +0.051%.
  * Paired against the day-117 DeepSeek answers on the same sessions:
    +0.145% a session, t = 1.15. Not a difference.
* **Spent:** $0.34 of the $1.50 cap, 66 calls.

Nothing changes. The newest DeepSeek reads the same rows no better than the
models already asked.
