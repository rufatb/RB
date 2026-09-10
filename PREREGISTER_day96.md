# Pre-registration — day-96: intraday relative-value pairs

Committed BEFORE any outcome is computed. Bars fixed here and do not move.

## Why this is not already in the record

Forty rejections, and a full-text search of `STRATEGY.md` for *cointegration,
pairs trading, spread reversion, Ornstein-Uhlenbeck, Kalman, half-life,
stat-arb* returns **nothing**. That is not an oversight, it is a different
mechanism: the shipped engine is a **cross-sectional directional** board — score
21 names, take the top two long and the bottom two short. Rejections #17
("a same-sector pair is a worse structure") and #23 ("diversify the two legs
across sectors") tested the pairing of that board's legs, not a mean-reverting
spread.

Relative-value pairs trading is the other thing entirely: form a spread between
two co-moving names, trade its deviation, and profit from convergence rather
than from direction. It has never been tested here.

## The honest prior, recorded before running

Strongly negative, and specifically so:

- **Gatev, Goetzmann & Rouwenhorst (2006)** established the canonical result —
  up to ~11% annualised, 1962–2002, and they controlled for data snooping.
- **Do & Faff (2010)** found the distance method **largely unprofitable after
  2002 once trading costs are counted**, with performance peaking in the 1970s–80s
  and declining through the 1990s.
- **Krauss (2017)** argues the cointegration method's weak showing is
  compromised by the two-step selection that only tests pairs already close in
  Euclidean distance.

So the strategy this study builds is documented as dead net of costs in the
modern era. It is being tested anyway because it has never been tested *here*,
on *this* execution contract, and because "everyone knows" is not a measurement.

## The cost arithmetic, stated before the backtest

A pair trade is TWO legs, each crossing the spread on entry and on exit:

    round trip = 2 legs x SPREAD_BPS(5.0) = 10 bps = 0.10%
    typical move (cost.TYPICAL_MOVE_PCT)  = 0.69%
    cost as share of a normal day         = 14.5%

Every result is reported NET, using the day-87 clamped `net_of_cost` so that
cost can erase an effect but never reverse its sign (the day-85 bug where
`m - cost*sign(m)` turned +0.016% into −0.034%).

If the observed spread-divergence distribution cannot reach the break-even
threshold this implies, the family is **closed by arithmetic** and no backtest
is required — the same disposal the earnings gate got at 0.108 bps/leg.

## The methodological contribution: placebo-max over the PAIR GRID

This is the part public implementations do not do, and it is the reason their
backtests look good and fail live.

With N names there are N(N−1)/2 candidate pairs — for 500 names, 125,000. At
p<0.01 with no multiple-testing correction, roughly **1,250 pairs test as
cointegrated on pure noise**. The standard public recipe (see
`fraserjohnstone/pairs-trading-backtest-system`, which "examines all possible
pair combinations for signs of cointegration and runs a trading algorithm over
each cointegrated pair") selects the best pairs and backtests them on the same
data. That is selection on the outcome. The literature's fixes are White's
Reality Check, Hansen's SPA, and the Deflated Sharpe Ratio; the field-note
framing of "testing all combinations is computationally heavy" treats a
**statistical** problem as a **compute** problem.

This repo already owns the right machinery — house rule 5, the placebo-max
rule. It is applied here to the pair grid:

> The statistic is the **best REAL pair's** net return measured against the
> distribution of the **best PLACEBO pair's** net return, at the 95th
> percentile. Never against zero.

The placebo destroys the pairing while preserving each name's own marginal
return distribution, so the placebo's best cell absorbs exactly the advantage
that comes from getting to choose a winner out of thousands of candidates.

## Design

**Universe.** `data/us_daily.csv` — 578 names, 2,517 sessions, 2016-08-30 to
2026-09-03 (development). `data/us_daily_holdout.csv` — 1,279 names, for
replication. A TSX-21 arm is reported separately for the live contract.

**Formation is POINT-IN-TIME and trailing only.** The hedge ratio and the
spread's mean and sd are estimated on a trailing window ending strictly BEFORE
the session traded. A full-sample hedge ratio leaks the whole panel into every
row and is the most common defect in public backtests. Formation window: 252
sessions. Minimum overlap: 200.

**Exactly two formation methods, no search.**
- D: normalised-price distance (Gatev).
- C: Engle–Granger — OLS hedge ratio, ADF on the residual.

**Exactly three entry thresholds, no search.** |z| >= 1.5, 2.0, 2.5. Six cells
total; the placebo-max is taken over all six.

**Entry/exit.** Enter at the session open, exit at that session's close —
`intraday` in the panel. Single session, no overnight carry. This matches the
shipped contract's shape (day-24, rejection #24: no exit beats the close) and
directly addresses Do & Faff's cost critique, since it is one round trip.

**Direction.** Long the leg that is cheap relative to the spread's trailing
mean, short the rich one, dollar-neutral.

**DAILY-BAR PROXY, stated first.** Entry is the OPEN, not 09:46. The panel's
`intraday` return is open→close and therefore contains 09:30–09:46 — sixteen
minutes the live engine does not see. No result here certifies the
09:46→15:59 contract, whatever the point estimate says.

**Survivorship, and why it bites HERE specifically.** `DATA_CEILING.md` holds
that on free data "any cross-sectional strategy that buys losers is untestable
— not underpowered, untestable, because the bias points the same way as the
hypothesis." **Pairs trading buys the underperforming leg.** That is a direct
hit, and it is the single most likely way this study produces a false positive.
Mitigations, all reported: the size test below at the day-86 ratio criterion,
the 1,279-name holdout comparison that measured the bias quadrupling on day-86,
and a large-cap-only arm where delisting is rare. If the effect concentrates in
the smallest liquidity quartile, it is survivorship and is reported as such.

## Statistics and bars

- **Statistic.** Mean net-of-cost return per pair-trade, and hit rate.
- **Clustering.** Block bootstrap, blocks = session, 2,000 draws, seed 96. Legs
  within one session share that session's move and are not independent draws.
- **MDE reported always** (rule 10), so a null is separable from UNDERPOWERED.
- **Positive control.** A planted edge must be detected, measured as
  `edge / sd` and never `(mean + edge) / sd`.
- **Size robustness.** Liquidity quartiles; `SIZE_RATIO_MAX = 2.0`, the
  ratio-based day-87 criterion, not the sign-based test that let a 25x
  concentration through for 54 days.

**The adoption bar — all five, any failure is a rejection:**

1. Best real cell **exceeds the 95th percentile of the placebo best-cell
   distribution**;
2. mean net-of-cost > 0 with session-clustered **|t| >= 3.0** (`ADOPT_T`);
3. **same sign in all four** chronological quarters (`BLOCKS = 4`);
4. **replicates on the 1,279-name holdout**;
5. **size ratio <= 2.0**.

## What may be adopted, and what reaches the 09:46 email

**Nothing reaches the email on this study alone.** A result clearing all five
bars licenses a SHADOW engine — computed, printed beside the board, and scored
prospectively — exactly as day-90's H1/H2/H3 were handled. Promotion from
shadow to a live pick requires the shadow's own prospective record, not this
backtest. A daily-bar proxy cannot certify a 09:46 entry, and no amount of
in-sample strength changes that.

## Forbidden

Reporting a best pair's return without its placebo-max comparison. Full-sample
hedge ratios or spread statistics. Adding a fourth threshold or a third
formation method after seeing results. Presenting the daily-bar proxy as
evidence about the 09:46 contract. Quoting any of this as proof the engine has
an edge. Wiring anything into the published report or the email that has not
cleared all five bars AND accrued its own shadow record.

## Expected outcome, recorded in advance

**Rejection #41.** I expect the raw best pair to look strong, the placebo's
best cell to absorb most or all of it, and the residual to die on the 10bp
round trip. If anything survives that, I expect it to concentrate in the
smallest liquidity quartile and fail the size ratio — which would be
survivorship, not an edge.

I am running it because it has never been run here, because the placebo-max
over a pair grid is a genuinely stronger test than the public implementations
apply, and because a bounded null on a family this popular is worth owning.
