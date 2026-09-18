# Day-111 pre-registration: a second model, and a gate with no dial on it

Committed before any forward observation is scored. House rule 3: the bar is
set here and is not moved afterwards.

## What this adds

`deepseek_opportunities` (day-110) asks one model for its top longs and shorts.
One model's opinion is one opinion. `jev_opportunities` asks a **second** model
the same question from the **same prepared evidence**, so that agreement and
contradiction between them become observable. Neither is adopted; neither is
claimed to have skill; they are never averaged.

## Jev is not a chat model, and that is the point

`typesafe/jev-1.13` is reachable only at `POST /api/alpha/decisions` on
OpenRouter. `/chat/completions` rejects it outright ("is a decisions model and
cannot be used with the chat/completions endpoint"). `typesafe/jev-latest` is
**not a valid model id** and is never used — a floating alias that 400s every
morning would be indistinguishable from an outage.

The request carries a `state` and typed `questions`. Three answer types exist:
`noul` (a bare 0–1 number), `choice` (an option from a supplied set, returned
with a probability over *every* option and a confidence) and `score` (a point
on a supplied ordinal scale). We use `choice`.

**The typing is the reason to use it.** The single failure that can put an
unassessed ticker in front of the owner is a model inventing a name. Here the
option set *is* the candidate universe, so the provider constrains the answer
and that failure mode cannot occur, rather than being caught by a validator
afterwards. The validator is kept anyway.

## The instrument

- **Input.** The same validated payload DeepSeek receives: at most 60 names
  with Python-computed technicals, headlines carrying their quality labels
  (`class`, `issuer_verified`, `first_disclosed`), and the macro block
  (WTI, CAD/USD, TSX, VIX). All supplied text is marked UNTRUSTED DATA.
- **Questions.** Two `choice` questions in ONE request — best LONG and best
  SHORT — over the tickers plus a `NONE` option.
- **Ranking.** From the returned distribution, not a second question.
- **THE GATE.** A name is reported only if its probability **exceeds the
  probability the model itself assigned to `NONE`**. At most two per side.
  This gate has **no tunable constant** — there is deliberately nothing here to
  nudge after a losing day, which is how the day-98 side-skill family got
  re-litigated repeatedly.
- **Clock.** Staged strictly before 09:30 ET, sealed with SHA-256, readable
  only on the same session within six hours. Measured latency **0.83 s** on 38
  names at **$0.00002** per call — two orders of magnitude cheaper and faster
  than the DeepSeek call, which is a robustness argument, not an accuracy one.

## What the numbers are not

`probability` and `confidence` are Jev's own. They are **not** calibrated win
probabilities, have no track record, have never been scored against an outcome,
and are **never** averaged with DeepSeek's self-reported confidence or the
engine's sided score. Averaging two unmeasured opinions produces a third
unmeasured opinion that looks better than either.

## Positive control (house rule 4)

`run_control()` reuses the day-110 planted universe — one unambiguous long, one
unambiguous short, ten flat noise names, with the planting in the NUMBERS ONLY
and nothing in the payload announcing itself as a test.

Result on 2026-09-18 through the production `rank()` path:

| Arm | Returned | Probability | Model's abstain probability |
|---|---|---|---|
| Planted LONG | `CTLUP.TO` | 0.79 | 0.21 |
| Planted SHORT | `CTLDN.TO` | 0.54 | 0.39 |
| Ten noise names | none | — | below the abstain option |

Both planted sides detected; no noise name cleared the gate. A
`NO_OPPORTUNITY` from this instrument is therefore an abstention, not a dead
harness. Re-run with `python jev_opportunities.py --control` before reporting
any null.

## First live reading, 2026-09-18 (diagnostic, after the open)

38 names offered, 32 carrying headlines, all four macro fields.

- LONG: **nothing** — no name beat its own `NONE`.
- SHORT: **SHOP.TO**, probability 0.480 against 0.360 for doing nothing.

DeepSeek independently shorted SHOP.TO the same session. That is one
cross-model agreement on one day: a recorded observation, not evidence.

## The registered forward question

**H1.** Over 120 sessions, do names both models pick on the same side have a
different gross hit rate from names picked by exactly one?

**Bar.** |t| ≥ 3 on session-clustered standard errors, over four quarters.
Below that it is not reported as a finding. Agreement is rare by construction
(both abstain often), so this is registered as **not answerable before
~2027-06** and is not to be re-opened after a good or bad day.

**H2 (descriptive only, no bar).** How often does each model abstain, and how
often do they contradict each other outright?

## What is NOT claimed

No predictive skill, no accuracy gain, no adoption. This ranking enters no
selection, no size, no threshold, no ledger row and no allocation. It cannot
place an order. A failure to stage it is a reported gap that never blocks
publication.
