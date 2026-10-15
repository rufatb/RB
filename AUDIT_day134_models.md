# Day-134b — other OpenRouter models on the day-117 replay: no better (owner, 2026-10-14)

Registered first: `PREREGISTER_day134_models.md` (ca9648f), harness included,
before any call. Script: `replay_or_models.py`; summary:
`data/replay_day134_models.json`.

**Verdict.** Neither model the owner's research pointed to picks better:
* DeepSeek R1 reads the rows, passing the planted control 5 of 5, and its
  picks are a coin flip on the registered bar;
* Claude Sonnet 5.5 declines to pick at all.

The question was the production desk question: the same prompt and rows, and
the desks' own validation.

## What was asked

* **Claude 3.5 Sonnet** is no longer on OpenRouter. Its line's 2026 model,
  Sonnet 5.5, was asked instead. The Claude desk already runs Opus 5.5.
* **DeepSeek R1** was asked as its May 2025 update, R1-0528. The DeepSeek desk
  already runs v4-pro.
* **Contamination.** Neither model gave a single July–September 2026 closing
  price when asked, so neither remembers the replay period.

## Results

| | Picks | Right | Mean per pick | t | Placebo p | Halves | Verdict |
|---|---:|---:|---:|---:|---:|---|---|
| **DeepSeek R1-0528** | 207 | 48.8% | **−0.02%** | **−0.14** | 0.61 | −0.02 / −0.01 | **FAIL** |
| Claude Sonnet 5.5 | 0 | — | — | — | — | — | abstained 59/59 |
| DeepSeek (day-117 run, same sessions) | 221 | 49.3% | −0.08% | −0.68 | 0.55 | −0.02 / −0.13 | FAIL |

**R1-0528.**
* **Power.** MDE80 is 0.27% per pick, so an edge that size or larger is ruled
  out.
* **Against the market.** −0.03% per pick against XIU.
* **Sides.** Longs 52/107, shorts 49/100.
* **Against DeepSeek.** Paired by session, +0.07% (t = 0.66): no different.
* **Behaviour.** It picked on every session and reasoned 1–9 minutes per call.

**Sonnet 5.5.**
* It answered NO_OPPORTUNITY on every session.
* On the planted control it found the plant once in five runs.
* As a desk it would print "No pick today" every morning, like the stateless
  Claude desk.

## Why

Day-117 found that no field the models see carries information about
09:45 → close in this pool. Every model asked since has landed on the coin flip:
* DeepSeek flash and v4-pro;
* Jev;
* the live Claude and Gemini desks;
* the council;
* now R1.

A stronger reader cannot recover a signal that is not in the inputs.

## What this settles

The model families in the owner's research are no better on the evidence, and
none is added. If a model ever passes this bar, the route is ready:
`replay_or_models.ORClient` runs any OpenRouter model through the production
desk path. A passing model would start as a forward shadow desk (recorded and
scored apart for 40 sessions), not as a council seat or a printed desk.

Spent $4.26 of OpenRouter credit (cap $5). About $10 remains.
