# RB second-pass research audit — September 8, 2026

Audience: portfolio managers and repository reviewers. Scope: research correctness,
new simulated intraday/overnight/weekly expressions, and accuracy-claim integrity.

## Decision

No new strategy is ready for adoption. The second pass found and corrected
material backtest defects, but the new 48-arm sector ETF study did not establish
an improved prediction or P&L result. At the registered 10-basis-point round-trip
cost assumption plus 3% annual short borrow, **none of the 48 strategies was
profitable in both development and confirmation**. This is a short-history
feasibility result, not proof that all strategies or new information must fail.
The daily TSX baseline, biotech rules and published delivery history are unchanged.

## What the second pass corrected

| Finding | Correction | Interpretation |
|---|---|---|
| The ceiling harness labelled a different k-NN formula as shipped | Match live sample SD, normalized vote, fixed 0.5 prior, rounding and clamp; preserve the former scorer as `legacy_knn_scores` | Arithmetic parity, not full feature/window/execution parity |
| Its AUC uncertainty treated same-session rows as independent | Session-cluster influence estimates, paired learner comparisons, multiplicity adjustment and AUC-unit MDE | Serial dependence and historical reuse remain limitations |
| Entry-time research normalized volume using a full-panel median | Shifted, past-only expanding median with 20 prior observations | Removes future-volume leakage; does not rewrite old outcomes |
| Daily acquisition ignored the requested `--years` argument | Propagate it to request dates; reject invalid values | Fetches the period the CLI actually requests |
| Some research fetches hid failures or exposed request text | Count safe error classes and HTTP statuses, including recovered retries | Missing data remains visible; remaining legacy adapters are listed below |
| A legacy function called clipped signed effects net returns | Preserve historical formula, explicitly label its effect-magnitude proxy | The new simulator subtracts costs without clipping losses |
| Legacy report text still described 52–56% leans as measured edges | Replace active claims with diagnostic language; qualify historical notes | Confidence is not invented from similarity scores |

Source files: [ceiling harness](validate_ceiling.py), [entry research](validate_entry.py),
[daily acquisition](build_us.py), [legacy cost proxy](validate_us.py),
[live report wording](r945.py). The current evidence does not establish reliable
baseline skill. The prior statement that the three features can *never* improve
accuracy was too categorical: the 122,234-row AUC=0.5022 study was an hourly proxy
that omitted volume pace, with the comparator/inference limitations above.
Original study numbers and all rejected research remain preserved.

## New study: fixed family, frozen selection

The [registration](PREREGISTER_day91.md) was published in
[48651ec](https://github.com/rufatb/RB/commit/48651ec161c691846783025e47c6a4a780216437)
before acquiring this price panel. Nine predeclared sector ETFs (XLB, XLE, XLF,
XLI, XLK, XLP, XLU, XLV, XLY) supply four distinct hypothetical legs: two longs,
two shorts, 100% gross exposure. SPY is a separate benchmark.

The 48 arms combine four trailing-return lookbacks (1/5/20/60 sessions), momentum
or reversal, equal or inverse-volatility sizing, and three horizons:
prior-close signal to next-open/same-close intraday; prior-close signal to the
following close/next-open overnight; and non-overlapping five-session weekly
holds. The overnight signal deliberately does not consume its own entry close.
All horizons are daily-bar proxies, **not exact 09:46 TSX execution**.

Massive returned prices beginning September 9, 2024 despite a September 2015
request. The registered short-history fallback therefore uses 2025, with a
common 61-session warm-up. Confirmation covers January 2–September 4, 2026.
The winning development arm and full-result hash were published in
[d1901cb](https://github.com/rufatb/RB/commit/d1901cb359b2b09342fa8298672f7b691caebc5e)
before acquiring confirmation prices. Its identity was never replaced by a
confirmation winner. Both phases used the identical evaluator hash.

The connected provider supplied 250 complete development and 170 confirmation
NYSE sessions for all ten instruments. Calendar checks found no internal missing
sessions. The data requests include cash distributions: split-adjusted cash is
credited/debited only when the holding crosses the ex-date entitlement boundary.
Massive's adjusted bars account for splits, not cash distributions by themselves.
[Provider aggregate documentation](https://massive.com/docs/rest/stocks/aggregates/custom-bars)

## Results

All returns below are simulated book returns per occupied session. Weekly trade
returns are divided by five for this comparison. Cost scenarios are assumed
round-trip trading frictions per leg, plus the fixed borrow assumption; they are
not measured spread/slippage or guaranteed short availability.

| Measurement | Development | Confirmation |
|---|---:|---:|
| Arms positive at 10 bps cost | 5 / 48 | 4 / 48 |
| Positive arms surviving Holm adjustment | 0 | 0 |
| Frozen winner | `reversal_20_equal_weekly` | Same frozen arm |
| Non-overlapping weekly trades | 36 | 34 |
| Frozen winner net bps/session | +2.32 | -3.80 |
| Net leg hit rate (%) | 48.61 | 50.00 |
| MDE at 80% power (bps/session) | 8.24 | 26.62 |
| Frozen winner at 25 bps cost | -0.68 | -6.80 |

The development winner's four block means were +3.63, −1.07, −0.71 and +7.41
bps/session. It already failed stability and the 25-bps cost stress. In
confirmation it produced approximately −6.56% compounded endpoint return and
−14.43% maximum drawdown measured only at trade endpoints. Intratrade drawdown
can be worse. Its 95% block-bootstrap interval for mean return was −14.65 to
+7.24 bps/session, MDE80 26.62 bps, and the planted 5-bps detectability ratio was
0.82. **UNDERPOWERED**, not a conclusive finding that a small effect is absent.

Every intraday and overnight arm was negative in both periods at primary costs.
The four positive confirmation arms were different from the five positive
development arms. Selecting them now would reuse confirmation as training.
No arm supplied statistically supported positive performance after correction
for the 48 comparisons. Higher hit rate alone would not establish profitability;
the frozen arm's 50% confirmation hit rate accompanied negative returns.

## All 48 arms

D/C = development/confirmation. Returns and MDE are basis points per occupied
session. Hit is confirmation net leg accuracy under 10-bps friction plus borrow.
Every arm is research-only; the table is not a list of current opportunities.

| Arm | D net | C net | C hit % | C MDE80 | C Holm p | C net at 25 bps |
|---|---:|---:|---:|---:|---:|---:|
| `momentum_1_equal_intraday` | -10.47 | -5.99 | 47.4 | 22.21 | 1.000 | -20.99 |
| `momentum_1_equal_overnight` | -8.26 | -17.04 | 41.6 | 15.69 | 0.000 | -32.04 |
| `momentum_1_equal_weekly` | +0.92 | -5.65 | 47.1 | 8.27 | 0.114 | -8.65 |
| `momentum_1_inverse_vol_intraday` | -10.46 | -6.69 | 47.4 | 22.83 | 1.000 | -21.69 |
| `momentum_1_inverse_vol_overnight` | -8.60 | -16.92 | 41.6 | 13.31 | 0.000 | -31.92 |
| `momentum_1_inverse_vol_weekly` | +1.13 | -5.32 | 47.1 | 8.57 | 0.241 | -8.32 |
| `reversal_1_equal_intraday` | -9.75 | -14.24 | 43.7 | 22.21 | 0.194 | -29.24 |
| `reversal_1_equal_overnight` | -12.72 | -3.93 | 44.5 | 15.69 | 1.000 | -18.93 |
| `reversal_1_equal_weekly` | -5.95 | +0.72 | 50.7 | 8.20 | 1.000 | -2.28 |
| `reversal_1_inverse_vol_intraday` | -9.76 | -13.53 | 43.7 | 22.83 | 0.323 | -28.53 |
| `reversal_1_inverse_vol_overnight` | -12.38 | -4.05 | 44.5 | 13.32 | 1.000 | -19.05 |
| `reversal_1_inverse_vol_weekly` | -6.16 | +0.38 | 50.7 | 8.55 | 1.000 | -2.62 |
| `momentum_5_equal_intraday` | -8.51 | -12.11 | 44.3 | 22.29 | 0.531 | -27.11 |
| `momentum_5_equal_overnight` | -8.77 | -9.91 | 45.0 | 15.64 | 0.208 | -24.91 |
| `momentum_5_equal_weekly` | -3.31 | -8.19 | 46.3 | 25.11 | 1.000 | -11.19 |
| `momentum_5_inverse_vol_intraday` | -8.55 | -11.22 | 44.3 | 20.72 | 0.531 | -26.22 |
| `momentum_5_inverse_vol_overnight` | -8.70 | -9.69 | 45.0 | 14.36 | 0.125 | -24.69 |
| `momentum_5_inverse_vol_weekly` | -2.57 | -8.49 | 46.3 | 21.57 | 1.000 | -11.49 |
| `reversal_5_equal_intraday` | -11.71 | -8.11 | 46.0 | 22.29 | 1.000 | -23.11 |
| `reversal_5_equal_overnight` | -12.20 | -11.06 | 41.0 | 15.66 | 0.085 | -26.06 |
| `reversal_5_equal_weekly` | -1.72 | +3.25 | 51.5 | 25.10 | 1.000 | +0.25 |
| `reversal_5_inverse_vol_intraday` | -11.67 | -9.00 | 46.0 | 20.72 | 1.000 | -24.00 |
| `reversal_5_inverse_vol_overnight` | -12.28 | -11.28 | 41.0 | 14.39 | 0.028 | -26.28 |
| `reversal_5_inverse_vol_weekly` | -2.46 | +3.55 | 51.5 | 21.56 | 1.000 | +0.55 |
| `momentum_20_equal_intraday` | -14.93 | -8.15 | 45.3 | 15.12 | 0.531 | -23.15 |
| `momentum_20_equal_overnight` | -7.98 | -5.71 | 45.7 | 16.49 | 1.000 | -20.71 |
| `momentum_20_equal_weekly` | -7.35 | -1.13 | 47.8 | 26.69 | 1.000 | -4.13 |
| `momentum_20_inverse_vol_intraday` | -14.90 | -7.89 | 45.3 | 14.03 | 0.453 | -22.89 |
| `momentum_20_inverse_vol_overnight` | -7.50 | -6.33 | 45.7 | 15.07 | 1.000 | -21.33 |
| `momentum_20_inverse_vol_weekly` | -6.77 | -0.87 | 47.8 | 24.39 | 1.000 | -3.87 |
| `reversal_20_equal_intraday` | -5.29 | -12.07 | 45.3 | 15.12 | 0.023 | -27.07 |
| `reversal_20_equal_overnight` | -13.00 | -15.26 | 40.5 | 16.50 | 0.003 | -30.26 |
| `reversal_20_equal_weekly` | +2.32 | -3.80 | 50.0 | 26.62 | 1.000 | -6.80 |
| `reversal_20_inverse_vol_intraday` | -5.32 | -12.33 | 45.3 | 14.03 | 0.006 | -27.33 |
| `reversal_20_inverse_vol_overnight` | -13.48 | -14.64 | 40.5 | 15.08 | 0.001 | -29.64 |
| `reversal_20_inverse_vol_weekly` | +1.73 | -4.06 | 50.0 | 24.32 | 1.000 | -7.06 |
| `momentum_60_equal_intraday` | -16.82 | -9.81 | 47.1 | 19.28 | 0.627 | -24.81 |
| `momentum_60_equal_overnight` | -8.46 | -12.18 | 42.5 | 17.13 | 0.081 | -27.18 |
| `momentum_60_equal_weekly` | -5.27 | -0.12 | 53.7 | 12.88 | 1.000 | -3.12 |
| `momentum_60_inverse_vol_intraday` | -16.35 | -9.76 | 47.1 | 18.66 | 0.580 | -24.76 |
| `momentum_60_inverse_vol_overnight` | -8.22 | -11.69 | 42.5 | 15.43 | 0.041 | -26.69 |
| `momentum_60_inverse_vol_weekly` | -4.67 | -0.88 | 53.7 | 10.84 | 1.000 | -3.88 |
| `reversal_60_equal_intraday` | -3.41 | -10.42 | 45.0 | 19.28 | 0.531 | -25.42 |
| `reversal_60_equal_overnight` | -12.52 | -8.79 | 42.8 | 17.15 | 0.626 | -23.79 |
| `reversal_60_equal_weekly` | +0.24 | -4.81 | 44.1 | 12.89 | 1.000 | -7.81 |
| `reversal_60_inverse_vol_intraday` | -3.87 | -10.46 | 45.0 | 18.66 | 0.453 | -25.46 |
| `reversal_60_inverse_vol_overnight` | -12.76 | -9.28 | 42.8 | 15.44 | 0.300 | -24.28 |
| `reversal_60_inverse_vol_weekly` | -0.36 | -4.05 | 44.1 | 10.84 | 1.000 | -7.05 |

Full machine-readable outputs: [development](data/day91_development.json),
[frozen selection](data/day91_selection.json),
[confirmation](data/day91_confirmation.json).

## Why the comparison is still limited

- The chosen ETFs survive today. They avoid rebuilding a historical stock
  universe from today's constituents but do not eliminate instrument-selection
  bias; sector definitions also evolve. This is not evidence about TSX stock picks.
- The short history spans only one development year and eight confirmation
  months. It is newly inspected by this run, not globally untouched market
  history or a prospective trial. Weekly inference has only 36/34 trade slots.
- A 20-slot circular block bootstrap and Holm correction are approximate tools.
  Weekly samples contain few independent blocks. Missing calendar observations
  block inference; constant samples cannot claim zero MDE. No optional retuning
  or stopping rule was used. Repeated backtest searches can manufacture winners.
  [Bailey et al., The Probability of Backtest Overfitting](https://www.davidhbailey.com/dhbpapers/backtest-prob.pdf)
- Dollar neutrality is not beta neutrality. Separate SPY-relative long and short
  components are reported; their difference is not certified residual alpha.
- Borrow availability, realized commissions, funding, actual quotes and fills
  are not supplied. Daily OHLC bars cannot certify the intraday execution window.
- Some older research loaders still require unavailable raw panels or suppress
  underlying adapter failure reasons (`build_rich`, `validate_twins`); older SEC
  acquisition uses recent submissions only. These were identified, not claimed
  fixed. Previous raw studies were not recreated from a moving universe.

## What changes now, and what would justify a new strategy

Use the corrected research harness and retain the complete experiment record.
Keep baseline output labelled as research candidates; the daily operational
recovery remains useful, but it does not imply improved prediction quality.
For further R&D, obtain the exact timestamped execution panel for already
registered cost/abstention/exit studies, or preregister an information source the
current tests did not measure (for example, point-in-time news with publication
latency and an explicitly defined surprise). Merely increasing the number of
indicator combinations or holding today's baseline overnight is unsupported.
No new data purchase, order, strategy adoption or delivery-state change was made.

## Reproduction and verification

Install `requirements-research.txt` for optional model comparisons; the ETF
sweep itself uses core requirements. Restore the separate raw research archive.
To reproduce development without exposing confirmation, copy only `development/`
and the acquisition manifest into a fresh data directory with an empty
`confirmation/`. Then run:

```bash
python research_sweep.py --data-dir /path/to/research-data --phase development --output /tmp/development.json
python research_sweep.py --data-dir /path/to/research-data --phase confirmation --frozen-development /tmp/development.json --output /tmp/confirmation.json
```

Restore `confirmation/` only between these two steps. The output path must not
already exist. Frozen inputs, evaluator and manifest hashes are in the results.
Both phases use the same evaluator, with no post-outcome strategy changes.

The full local suite passed **1,094 tests**. The 46 new cases cover live-score
parity, within-session replication, temporal leakage, acquisition errors,
parameter propagation, dividends/short liabilities, non-overlapping holds,
missing data, repeated-testing arithmetic and synthetic controls. Executable
AST comparison confirmed the live k-NN, density and selector math is unchanged.
Tests establish software properties; they do not establish investment skill.

Research stopped after the entire registered 48-arm family, three cost scenarios
and two periods were completed. All outcomes are disclosed. Expanding the family
after seeing these results would require a new registration and new validation
resources, rather than an unreported search until a winner appears.
