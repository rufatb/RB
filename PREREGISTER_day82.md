# Pre-registration — day-82, cost-aware candidate selection

Committed BEFORE any result is computed, per §4 of the master instruction.
Bars are fixed here and do not move.

## Why this family and not another

The intraday direction call is measured at zero (AUC 0.5022 on 122,234
out-of-sample rows, live 44/93). Further feature engineering on `r0`/`gap`/`vp`
is refuted and is not re-litigated here.

All three changes ever adopted in this repo were **variance or cost** results,
none improved accuracy. A cost claim does not require an edge to exist: **if
direction is uninformative among qualifying candidates, then choosing the
cheapest one to trade is a strictly positive expected saving with no accuracy
claim attached.** That is the hypothesis, and it is the reason this is the
first study rather than another model.

## The natural experiment already in the ledger

`r945.publish` writes every qualifying candidate, not only the traded pair:

- `role="pair"` — the two legs the density rule SELECTED, and traded
- `role="board"` — qualified at the same bar, on the same day, from the same
  universe, and NOT selected

Both are scored against the same 15:59 close. The board rows are therefore the
counterfactual "a qualifying name we did not pick", which makes this an
out-of-sample test of the selection rule itself rather than of the model.

**Sample, counted before any outcome was inspected:** 93 pair legs, 215 board
legs, 38 sessions, 21 unique tickers, 2026-07-08 to 2026-09-01.

## H1 — does density selection beat an arbitrary qualifier?

- **Population.** All scored legs, split `pair` vs `board`.
- **Statistic.** Difference in decisive hit rate (ACCURACY.md §1,
  `|capture| >= ledger.DECISIVE_PCT`), and difference in mean capture per leg.
- **Clustering.** Bootstrap resampling **SESSIONS**, not legs. Legs on one day
  share a market move; treating them as independent understates the interval.
  38 clusters.
- **Bar.** The standing `|t| >= 3`.
- **Expected outcome, stated in advance: UNDERPOWERED.** With 93 vs 215 the
  unclustered SE on a proportion difference is about 5.5pp, so the bar implies
  an MDE near 16pp before clustering and wider after it. A difference that
  large is not plausible. **This is registered as a bound, not as a test I
  expect to pass**, and reporting it as a refutation would violate rule 10.
- **Positive control.** Plant a known lift on the pair legs and confirm the
  harness registers it at the stated size, measured as `edge / sd`.
- **Placebo.** Re-split the same legs at random into groups of 93 and 215 and
  confirm the observed difference is inside the placebo distribution.

**Day-9 context, which makes this worth bounding.** Density selection was
adopted on a walk-forward replay scoring 68.0% discovery / 69.2% confirm
(n=89, p≈0.0007). The live record on the same rule is 47%. H1 asks whether any
of that advantage is visible in the live sample.

## H2 — how much does selection cost in spread?

- **Quantity.** For each session and side, the round-trip spread of the leg
  the density rule chose, minus the round-trip spread of the **cheapest
  qualifying candidate on that side that day**. Positive means density
  selection paid more than it had to.
- **Bar (new, and justified here in advance).** Adopt only if the mean saving
  is **>= 2.0 bps per leg** AND its 95% session-clustered interval excludes
  zero. 2.0 bps is chosen because the measured spread term runs 5-11 bps per
  leg and the directional term is -10 bps; a saving under 2 bps is not worth a
  change to a selection rule that has other properties.
- **THE LIMITATION, STATED BEFORE THE RESULT.** Historical spreads were never
  stored — `ledger.spread_bps` starts today (day-82). H2 therefore **cannot be
  measured on the historical sample**. It will be computed two ways, both
  labelled:
  1. **PROSPECTIVE (the real test).** From today forward, every published leg
     stores its spread. This is the measurement, and it is not available yet.
  2. **SNAPSHOT ESTIMATE (a bound, not a result).** Current spreads for the 21
     traded tickers, applied to the historical selections. This assumes the
     *relative* ordering of spreads among these names is stable over the
     sample. That assumption is not tested here and the figure is reported as
     an estimate with the assumption named — never as a measurement.

## What may be adopted from this

Nothing on H1 alone; an underpowered bound adopts nothing. H2 may change the
selection rule **only** on the prospective measurement, which needs sessions
this study does not have. The snapshot estimate may only be used to decide
whether the prospective study is worth running at all.

## Forbidden in this study

Choosing the 2.0 bps bar after seeing the dispersion. Re-splitting pair/board
on any basis other than what `r945` actually recorded. Reporting H1 as a
refutation of density selection. Using the snapshot estimate as evidence for a
rule change.
