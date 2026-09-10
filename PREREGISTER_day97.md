# Day97 — EODHD qualification and opening-path research

Registered before new market outcomes are computed. This adds data qualification
and research infrastructure, not an adopted predictor or allocation change.
Earlier registrations and all rejected research remain unchanged.

## Operational contract

EODHD is an optional historical research/reference provider. Its delayed or
daily responses never enter the live quote layer, pre-open Yahoo cache, or
09:46 selection. Authenticate exact Canadian ticker/currency via the exchange
catalogue. Validate timestamps, interval, completed sessions, OHLCV and coverage;
HTTP 200, a marketing page or a successful US demo is insufficient.
Keep the API token outside git. Redact credentials, account details and raw
provider errors. Use a finite request/credit budget, no retries after denial or
rate limiting, and no redirects carrying credentials. Keep transport failure
distinct from provider entitlement denial. Preserve prior successful inputs.

## H1 — opening-path information, five-minute proxy, shadow only

The primary question remains day93's paired [r0,gap,vp] vs [r0,gap] comparison.
The extension here adds exactly two opening-path features to [r0,gap,vp]:
third-bar return minus first-bar return, and net opening return divided by the
sum of absolute within-bar returns (zero denominator maps to zero).
These describe the path within the first 15 minutes, not an alternative entry
time, target, exit or a relabelled residual-feature experiment. No threshold
sweep, inverse-signal adoption, overnight trade or automatic promotion.

Use the fixed parity k-NN only, 120 initial training sessions, five chronological
folds, at least 60 distinct OOS sessions, and 20 prior-session volume warm-up.
Both comparisons use identical finite rows and folds. Exclude today's outcomes.
The 145-session figure is only a runnable floor: 20 warm-up + 120 training +
five OOS sessions. It fails the existing 20-cluster inference floor. This new
study requires at least 200 clean raw sessions and may require more after gaps.

Report paired AUC changes, session counts, 20-session moving-block bootstrap
uncertainty (2,000 draws, seed 97), MDE80 = (3.5 + 0.8416212336) * bootstrap SE,
and four chronological OOS block estimates. The discovery threshold is 3.5 SE
for each of the two declared comparisons; no new arms may be added after seeing
results. A constant 0.02 influence shift tests statistical sensitivity only;
it is not a planted feature mechanism or proof that the learner detects alpha.
Session-block sign-flips, 2,000 draws, report the maximum across the two arms
with finite-draw (1+k)/(1+B) probabilities. No valid inference under 60 sessions.

Labels are the last completed opening bar close to the final regular-session
bar close, explicitly a trade-price proxy, not 09:46/15:59 fills. The complete
session's high/low/volume must not enter opening features. Missing bars are not
forward-filled. Five-minute OHLCV does not supply BBO, fees, slippage or borrow.
No AUC result alone satisfies a net-P&L adoption criterion: matched execution,
cost and index evidence plus a separately untouched confirmation period remain
required. Minimum net-return MDE is unavailable until those data exist.

## Contributor audit

Preserve main's e55e776 pairs placebo correction. Review Kimi's day95b work
sequentially. Accept only independently tested finite-feature/density robustness
ideas; do not widen the publication window or remove frozen outage publications.
Its vp normalization comparison loses warm-up rows on one side, so it cannot
isolate normalization from sample composition without paired rows. Its residual
features are a separate registered study, not evidence this extension is novel
or successful. Do not import an unverified result or call a shadow score a win
probability.
