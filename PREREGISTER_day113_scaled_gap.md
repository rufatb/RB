# Pre-registration — day-113: does a volatility-scaled gap carry same-session information?

Committed BEFORE the study is run. The bar below does not move afterwards.

## Why this question, and why now

Day-113 began sending both models `gap_atr` — the last session's gap measured
in units of the name's normal daily move — with a prompt telling them that
"a +2% gap on a name with a 5% ATR is smaller than +0.8% on one with 2%". That
is a statement about SCALE, and it is true arithmetic. Whether a large scaled
gap says anything about the direction of the SAME session is a separate, empirical
claim that nobody has tested here. If it carries nothing, the models should be
told it is context, not a signal. If it carries something, it is a candidate
mechanical third opinion beside DeepSeek and Jev.

## What has already been rejected, and why this is not a re-run

- Day-17/20: gap-BUCKET rules on the k-NN board ("don't short a big gap-down",
  "don't take stretched legs") — rejected on the four-quarter rule. Those
  conditioned the ENGINE'S picks on raw gap size; this conditions nothing on the
  engine and scales the gap by the name's own volatility.
- Per-name volatility normalisation of the k-NN feature space — rejected. That
  changed which neighbours were "familiar"; this is a one-variable direct test.

If this study fails it is recorded as a rejection in STRATEGY.md and the
prompt's language stays "context, not a signal".

## Data

`data/tsx_daily.csv` (committed): TSX daily bars, columns open, close,
prev_close, overnight (%), intraday (%). No high/low, so the scale is the
**20-session standard deviation of close-to-close returns, lagged one session**
(`sd20`) rather than a true ATR. Stated here because it is a deviation from the
live field's definition.

- Signal: `g = overnight / sd20_prev` — the gap in units of normal daily move,
  known at the open.
- Outcome: `intraday` — open to close, a PROXY for the 09:46→15:59 contract (it
  includes 09:30–09:46 and ends at 16:00). Same caveat as the ledger's legacy
  proxy.
- Qualifying rows: `|g| >= 1.0` (one normal day's move, set now, not tuned).
- Statistic: `s = sign(g) × intraday`. Positive = continuation, negative = fade.

## Inference

- **Session-clustered.** The daily mean of `s` across qualifying names is ONE
  observation; the t-statistic is over sessions, never over rows (day-91's
  lesson: same-session rows are not independent).
- **Four chronological quarters of the sample** (equal session counts).
- **Placebo:** 2,000 draws in which each qualifying row's sign is replaced by a
  random sign, recomputing the clustered mean. Report where the real value sits.
- **Positive control (house rules 4 and 10):** plant a continuation of
  `+0.10 × sd20_prev` into `intraday` for qualifying rows only and confirm the
  identical harness detects it at the bar below. The control measures
  `edge / sd`, never `(mean + edge) / sd`. If the control is NOT detected, the
  study is UNDERPOWERED and no null may be reported.

## The bar (all must hold; either direction counts, decided by the data)

1. `|t| >= 3.0` session-clustered on the full sample;
2. the same sign in **all four** quarters;
3. the real mean beyond the 99.5th percentile of the placebo (two-sided p < 0.01);
4. `|mean s|` exceeds a 10 bp round-trip cost;
5. the positive control is detected at `|t| >= 3.0`.

## What passing would and would not mean

Passing licenses ONE thing: a shadow, unsized, labelled mechanical line in the
report, scored forward in `data/model_picks.csv` like the two models. It does not
change the engine's selection, sizing, threshold or board, and it is not
described as a prediction. Failing changes nothing but the prompt's wording
and adds a line to STRATEGY.md.
