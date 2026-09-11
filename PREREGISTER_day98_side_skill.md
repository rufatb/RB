# Pre-registration — day-98: does the LONG side have negative skill?

Committed BEFORE any further data accrues. The bar is fixed here and does not
move. Registered because the question keeps being asked after bad sessions, and
a question re-asked after every loss is not a test — it is a search for
permission.

## Why this exists

The live record, as of 2026-09-11 (`AUDIT_day98_losing_days.md`):

| side | n | hit | own base rate | skill | |
|---|---:|---:|---:|---:|---|
| LONG | 51 | 42.9% | 53.0% | −10.1pp | −1.42 SE |
| SHORT | 58 | 53.4% | 47.0% | +6.4pp | +0.98 SE |

The base rate is the naive coin each side actually bets against — rejection
#16's required control, because a drifting tape makes one side win with no
skill involved and cutting a side would then be a **beta bet**, not an
improvement. The tape drifted UP over these sessions, so the long weakness is
not a drift artifact.

**Neither result is significant, and this family has already been refused
once.** Rejection #16 tested "one side is structurally broken" and found the
deep set and the true five-minute set said OPPOSITE things about which side was
broken — with the true-horizon data pointing at the LONGS, which is the same
direction as today. It failed the four-quarter bar.

So the honest status is: suggestive, underpowered, previously refuted.

## Hypothesis

**H1.** The long side's hit rate, measured against the same-session universe
base rate P(up), is below zero by more than noise.

**H2 (the only one that could license action).** The same is true of the long
side's mean net-of-cost return per leg.

Both are measured on the live `ledger.csv` pair legs only. No backtest
substitute exists: the selector needs intraday features whose free history caps
at ~41 sessions (day-93), so the live record is the only valid sample.

## Statistics and bars

- **Statistic.** Per side: (hit rate − own base rate) in pp, and mean leg
  return in %. Base rate = fraction of the configured universe moving the
  side's direction over the SAME session and the same window.
- **Clustering.** Block bootstrap by SESSION. Legs opened the same morning
  share that day's move and are not independent draws.
- **Bar.** Session-clustered **|t| ≥ 3.0** (`ADOPT_T`), AND the same sign in
  **all four** chronological quarters, AND surviving the base-rate control.
- **MDE printed always** (rule 10).
- **Positive control.** A planted edge must be detected as `edge / sd`, never
  `(mean + edge) / sd`.
- **Placebo.** Side labels shuffled within session; the real statistic must
  beat the 95th percentile of that null.

## When this becomes answerable, computed now

Resolving a 10pp side effect at |t| ≥ 3 needs SE ≤ 3.3pp, i.e. **≈230 legs per
side**. The record has **51 long legs over 40 sessions — 1.27 per session.**

    (230 − 51) / 1.27 ≈ 140 further sessions ≈ 6.7 months

**Before roughly 2027-04, this question cannot be answered at this repo's own
bar.** That is the honest date, and it is registered so nobody — including me —
re-opens it in the meantime because a Tuesday went badly.

## What may be adopted

**Nothing before the bar is met.** And even then, dropping or derating a side
is a beta bet unless the base-rate control clears it, so adoption additionally
requires that the effect survive against each side's own naive rate in all four
quarters. Rejection #16 is the precedent: the raw side records looked decisive
and the control reversed which side looked broken.

## Forbidden

Adopting on the current 51 legs. Re-running this after a losing session and
reporting whichever number now looks larger. Dropping the base-rate control
because the raw gap is bigger. Quoting the −10.1pp figure without its −1.42 SE
and without noting that #16 refused this family. Treating an interim check as
an answer.

## Expected outcome, recorded in advance

I expect this to remain UNRESOLVED at the next interim check, and I expect the
long-side gap to shrink toward zero as n grows, because that is what a −1.42 SE
observation usually is. The prior is 41 rejections, day-43's AUC 0.5022 on
122,234 rows, and rejection #16 specifically.

I am registering it rather than dismissing it because the direction is
consistent with a real cost and the user is entitled to a date on which the
question gets a real answer instead of a shrug.

## The one thing that does NOT need this test

The win/loss ratio is **0.92** against the **1.06** required to break even at a
48.6% hit rate. That is arithmetic, not a hypothesis — a system calling
direction correctly half the time still bleeds at that ratio. It requires no
predictive skill to change and is not gated by this registration.
