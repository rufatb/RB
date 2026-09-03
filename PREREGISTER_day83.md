# Pre-registration — day-83, the magnitude expression

Committed BEFORE any result is computed. Bars are fixed here and do not move.

## Why this and not another model

The intraday direction call is measured at zero: AUC 0.5022 on 122,234
out-of-sample rows, where the same harness detects a planted 52% coin at z=15;
38 rejections; live 46/97. **Direction is not re-litigated here.**

Day-70 measured two things on the same rows and they went opposite ways:

| | z | day-70 verdict |
|---|---|---|
| direction after a 6-K | +0.72 | REJECTION #36 |
| **magnitude** (\|r1\|) after a 6-K | **+6.35** | adopted, as a RISK WARNING |

The engine can predict *how far*, not *which way*. Expressed in shares, a
predictable magnitude at zero direction edge is **pure added variance**, which
is exactly why it shipped as a reason to size DOWN. The hypothesis here is that
the same measurement, expressed in options, is the payoff rather than the cost.

**This is not a new signal.** It is the one signal already measured, pointed at
an instrument that can monetise it. If it fails it fails on COST, and that is
tested first.

## The instrument, and a constraint found before writing this

`.TO` names carry **no listed options on this feed** — SU.TO, BMO.TO, RY.TO and
CNQ.TO all return zero expiry dates. The US cross-listings do, with real open
interest (SU 16,073 · TD 19,990 · CNQ 11,219 · RY 4,824 · BMO 222 · ENB 800).

So the expression requires moving from the TSX line to the NYSE line. That is a
different instrument, different hours and different liquidity — not a
relabelling — and BMO's 222 contracts of open interest is a warning on its own.

## STAGE 1 — COST. Run first, and it can end the study

**Question.** Does a round-trip at-the-money straddle on these names cost more
than the measured post-filing magnitude is worth?

**Statistic.** Round-trip cost = (call spread + put spread) as a percentage of
spot, where each spread is `(ask − bid) / mid`. Crossed once on entry and once
on exit, so the round trip is the full spread on both legs.

**Bar, fixed now.** The study proceeds to Stage 2 **only if**

    median round-trip straddle cost  <  0.5 x (measured post-filing |r1| lift)

A cost above half the effect leaves too little for the effect to be worth
having after the variance risk premium is paid. If cost exceeds the bar,
**the study stops and is written up as REJECTED ON COST** — no modelling, no
Stage 2, no "but with better execution".

**Why cost first.** The share book died of spread after months of work on
direction. Testing the cheapest, most decisive constraint first is the lesson
from that, and it costs a day rather than a quarter.

**The feed gate is mandatory.** Yahoo zeroes bid/ask outside market hours — SPY's
at-the-money put quotes 0.00/0.00 pre-market. Measuring the cost then returns a
spread of zero, i.e. *trading is free*, the most flattering possible error.
`quotes.feed_is_live` must pass before any cost number is recorded, and the
harness must REFUSE rather than report when it does not.

## STAGE 2 — the effect. Only if Stage 1 passes

**Hypothesis.** A long at-the-money straddle opened at 9:46 on a session
following a 6-K, held to 15:59, outperforms the same structure on random
sessions in the same names.

**Population.** US cross-listings of the intraday universe with listed options
and non-trivial open interest.

**Statistic.** Mean straddle return, and the win rate against the round-trip
cost from Stage 1.

**Clustering.** Bootstrap resampling **SESSIONS**, not legs.

**Bar.** The standing `|t| >= 3`.

**Placebo.** The same structure on random dates in the same names. If the
placebo reproduces a material share of the effect it is a company-type or
regime artefact, not a filing effect.

**Positive control.** Plant a known magnitude lift and confirm the harness
registers it at the stated size, measured as `edge / sd`.

**MDE reported always.** If the observed effect is smaller than `bar x SE`, the
answer is **UNDERPOWERED**, not refuted.

## Known weaknesses, stated in advance

1. **The magnitude result was not pre-registered.** Day-70 wrote it after seeing
   the `|r1|` column and labelled it honestly. It earns a place as a warning on
   mechanism and z=6.35; it has NOT earned the status of a trading signal, which
   is what this study would decide.
2. **It is conditional on a 6-K**, measured on 52,919 rows across 78 names. It
   does not say the engine can pick high-magnitude sessions generally.
3. **This is really a variance-risk-premium claim.** Implied volatility already
   prices expected movement. The question is whether the filing-conditional
   magnitude exceeds what the straddle costs — not whether the stock moves.
4. **No historical option prices exist for free**, so Stage 2's entry cost must
   come from Stage 1's current-spread measurement applied to historical
   sessions. That is an assumption about spread stability, it is not tested
   here, and any Stage 2 result carries it as a stated limitation.

## Forbidden in this study

Proceeding to Stage 2 if Stage 1 fails its bar. Measuring cost while the feed
control fails. Substituting `lastPrice` for a two-sided quote. Re-deriving the
direction call. Reporting an underpowered Stage 2 as a refutation. Moving the
0.5x cost bar after seeing the spreads.
