# Day-132c phase 3 — a model asked after the open: no better (owner, 2026-10-14)

Registered first: `PREREGISTER_day132c_after_open.md` (d9d4c05). The harness
was committed with it, and nothing had run. Script: `replay_after_open.py`;
summary: `data/replay_day132c_after_open.json`.

**Verdict: FAIL, and powered.** A model handed each name's first thirty
minutes picks no better from 10:00 to the close than random names from the
same pool. It is also no better than the same model asked before the open.

## What was asked

* **Setup.** 59 replay sessions (2026-07-06 → 2026-09-28), with a median of
  79 names each that had complete bars. DeepSeek v4-pro was asked the
  production nomination question (two longs, two shorts, no abstaining) twice
  per session:
  * Arm A, before the open, on the prior session's rows;
  * Arm B at 10:00, with each name's `open30` added: the gap, the first
    thirty minutes' move, that move against XIU, its relative volume, the
    distance from its 09:30–10:00 VWAP, and where it sits in its range.
* **The model control passed** (5/5 clean in the run, 4/5 in the first check).
  The plant sat only in `open30`, so the model does read the new fields.

## T2 — Arm B, 10:00 → close against XIU

| | Picks | Right | Mean | t |
|---|---:|---:|---:|---:|
| **Arm B, after the open** | 235 | 45.5% | **+0.05%** | **0.44** |
| Random picks, same pool (placebo) | — | — | +0.00% | p = 0.26 |
| Arm A, before the open (09:45 → close) | 231 | 49.4% | −0.04% | −0.30 |
| B − A, paired by session | 58 sessions | | +0.07% | 0.45 |
| Rule: the two strongest first thirty minutes long, the two weakest short | 236 | 50.4% | +0.15% | 1.31 |

A planted 0.5% shows at t = 4.17 (MDE80 0.34%). Arm B misses every bar.

## How it chose

* **It followed the open:** 88% of Arm B's picks went the way the name's
  first thirty minutes had gone.
  * Those 207 picks averaged +0.08%.
  * The 28 that went against it averaged −0.15%.
* **The model did no better than the mechanical rule** of following the first
  thirty minutes (+0.15%, t = 1.31), and that rule is itself no edge (day-130
  H5).
* **Sides.** Its longs averaged +0.33% (t = 2.17) and its shorts −0.22%
  (t = −1.40). The sides disagree, so neither is a signal; neither is a
  registered test.

## What this settles

The outside read's C3 ("reacting to new information beats predicting from old
information") now has its powered test, and it fails. The two live "late"
sessions (DeepSeek 5/8) were two days. By 10:00 the first half hour is priced
like everything else here: overnight releases (day-118/122), analyst changes
(day-125), report days (#46), the gap (#42), first-half-hour momentum (H5) and
yesterday's move (#47).

Nothing changes. A 10:00 desk is not proposed.
