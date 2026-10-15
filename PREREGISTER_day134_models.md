# Day-134b — other OpenRouter models on the day-117 replay (owner, 2026-10-14)

Registered BEFORE any call below was made.

The owner asked whether models available on OpenRouter would pick better,
naming "Sonnet 3.5" and "DeepSeek R1" from their own research, and how they
would fit the architecture.

## Models (via OpenRouter, single-shot)

* **The R1 line: `deepseek/deepseek-r1-0528`.** This is R1's May 2025 update,
  priced at $0.50/M in and $2.15/M out. It reasons before it answers, and that
  cannot be switched off.
* **The Sonnet line: `anthropic/claude-sonnet-5.5`** (released 2026-09-28,
  $2/M in and $10/M out). Claude 3.5 Sonnet is no longer on OpenRouter; its
  2026 line is the only one that can be asked. The Claude desk already runs
  Opus 5.5.

No other model is asked under this registration.

## Contamination probe (first, per model)

Each model is asked for the closing price of 5 TSX names on 3 replay dates
(2026-07-15, 2026-08-14, 2026-09-15), with null allowed. Its answers are
compared with FMP's closes, and with a naive guess (each name's close on
2026-01-15).

**CONTAMINATED** means at least 5 answers, a median absolute error ≤ 5%, and
an error under half the naive guess's. A contaminated model's replay is void:
it may know the period. It can be judged forward only.

## Positive control (per model)

The desks' planted universe (`deepseek_opportunities.control_universe`), five
runs. Clean means both planted names on their sides and no noise name.

**Bar: 4 of 5 clean.** Below it, the model's null cannot be read
(UNDERPOWERED as a reader); it is still reported.

## The replay (per model)

* **Sessions.** The 59 day-117 sessions, with their cached pools.
* **The question.** The production desk question:
  * `deepseek_opportunities.SYSTEM_PROMPT` and `build_request` rows;
  * validated by `_clean`, `check_levels` and `check_basis` (`O.rank` with an
    OpenRouter client);
  * at most two names a side, abstaining allowed.
* **Scoring.** `model_picks.score_one`: the 09:45 bar close to the 15:55 bar
  close.

**The bar is day-117's, unchanged.** Skill needs ALL of:
1. a session-clustered mean per pick above 0, with t ≥ 2.0;
2. a hit rate that beats 2,000 random-pick draws from the same pools and sides
   (p < 0.05);
3. the same sign in both halves of the sessions.

**Descriptive only** (no bar, never a rule):
* market-adjusted means;
* long and short splits;
* abstentions;
* the paired difference against the day-117 cached DeepSeek answers on the
  same sessions.

## Budget

At most $5 of OpenRouter credit (the key holds $14.30; the mornings use about
$0.25 a day). The run stops when the running cost would pass it, and the
sessions not reached are named.

## What follows

* **PASS:** a forward shadow desk may be PROPOSED to the owner. It would be
  recorded and scored apart, and never sized or in the Top 2 until 40 live
  sessions, under its own registration.
* **FAIL:** nothing changes. The model is no better than the desks we have,
  on the evidence available.

Script `replay_or_models.py`; summary `data/replay_day134_models.json`.
