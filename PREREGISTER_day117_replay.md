# PREREGISTER day-117 — do the desks have ANY skill? A replay over every available session

Registered 2026-09-28, before any replay pick was generated or scored.

## Why

The owner: "the accuracy was not good for all LLMs and sections — research why
and let's fix it". The live record cannot answer that. On 2026-09-28 it held
Claude 5/5, DeepSeek 6/12, Jev forced 2/2, engine 7/19, over two to five
sessions. Nineteen model picks cannot tell a 50% picker from a 60% picker (the
Wilson interval on 13/19 runs 46%–83%). "Not good" and "good" are both
unestablished, and tuning a prompt against twelve picks would be the day-98
mistake.

So the question is answered on a sample the models have not seen: a REPLAY.

## The replay (`replay_models.py`)

For every TSX session D covered by Yahoo's ~60-day five-minute history (about
40 sessions), rebuild the candidate pool AS OF D 08:55 ET with the production
code (`prepare_factor_pool._prepare` + `factor_inputs.build_from_state`), fed
history truncated before D — nothing on or after D reaches the rows. Then ask:

  * DeepSeek — `deepseek_opportunities.rank`, the live prompt, unchanged
  * Jev — `jev_opportunities.rank`, gated and forced questions, unchanged

once per session, and score every pick with the production scorer
(`model_picks.score_one`: 09:45 bar close → 15:55 bar close, no costs).

Claude is NOT replayed: the session route has no blind path (this session has
seen the live outcomes of 09-17 → 09-28), and there is no API key. Its live
record is its only evidence.

## Harness controls — run FIRST; nothing is reported if they fail

  * ORACLE: per session, the two best realized longs and shorts from the pool
    must score ≥ 95% hits; ANTI-ORACLE ≤ 5%. Proves direction and scoring are
    wired correctly.
  * LEAKAGE: a unit test proves a pool built for D contains no bar dated ≥ D.

## The bar (per model; DeepSeek selected is PRIMARY, Jev forced SECONDARY)

Skill is claimed ONLY if ALL hold:
  1. session-clustered mean return per pick > 0 with t ≥ 2.0 (each session's
     mean is one observation);
  2. the pick-level hit rate beats a PLACEBO — 2,000 draws of random picks from
     the same session pools with the same long/short counts — at p < 0.05;
  3. the same sign in both halves of the sessions (by date).

Otherwise the result is "no evidence of skill at this sample", stated with its
minimum detectable effect.

## Descriptive only (no inference, no adoption)

Market-adjusted returns (vs XIU.TO over the same bars), long vs short, hit rate
by stated confidence, and two mechanical rules on the same rows —
relative-strength momentum and its reversal — as reference points.

## Limits, stated up front

No headlines (historical RSS is not retrievable; the live feed is almost all
COMMENTARY/UNCLASSIFIED anyway), no macro block, the legacy 117-name pool
rather than the live security master, one model call per session, and each
model's training cutoff is not published — the rows carry dates, so a model
that had memorised these sessions could cheat; a within-session intraday
memory of TSX names is implausible, but it is not excluded.

## What "fix" may mean afterwards

A prompt or parameter changed to fit THIS replay and then scored on it proves
nothing. Any variant chosen after seeing these results is registered separately
and judged only on sessions it was not tuned on (forward, live).
