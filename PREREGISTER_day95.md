# Day 95 — integration audit and risk evidence

Registered September 9, 2026 ET, before running corrected day94 market-data
inference or any new risk experiment. Existing outcomes and rejected studies
remain historical records. This registration does not alter the baseline.

## Audit, not a prediction experiment

Reconcile the September 9 email's four hypothetical legs against their actual
timestamped price sources. Report bar proxies separately from fills and from
close-to-close returns. No fill, borrow fee, spread, index quote or actual
holding may be inferred from the email. Today is an explanation set, never a
holdout for choosing a fix. Compute empirical complete-session bad-day counts
and diagnostic-score calibration from prior published records only. These are
descriptive audits; no alpha MDE applies to formatting or data-integrity fixes.

## Correct the day94 implementation before evaluating its three fixed arms

Keep its dates, features, seed, 20-session blocks, 2,000 draws and Holm family.
Reject non-daily and duplicate daily bars instead of silently collapsing them.
Report missing fields, invalid rows and unavailable uncertainty explicitly.
Use z >= 3.5 for its development discovery threshold, consistent with its
registered MDE. Print the four development blocks; they are diagnostics, not
a retrospectively chosen pass criterion. A confirmation cannot establish live
intraday skill because its target is open-to-close and its universe is current.

The existing add_control(edge=.02) shifts a normal feature by +/-0.05 on true
labels. Its standalone population AUC is Phi(sqrt(2)*.05), about 0.5282; its
effect after fitting k-NN is NOT guaranteed to be +2 AUC points. Keep the
control unchanged, disclose this distinction, and measure its paired learned
effect and MDE. An undetected control stays UNDERPOWERED. No source/coverage
failure is a statistical null. No parameter search or automatic adoption.

Arm A collection clarification, before prospective data: count unique, valid,
aware-timestamped StockTwits messages in the preceding 24 hours, ending at
collection. Older, future, duplicate and malformed messages get separate
rejection counts. A capped endpoint measures observed stream coverage, not
total daily traffic. Only first-write, pre-open TSX session snapshots count
toward the 20-session coverage gate. Each usable name needs 20 valid sessions;
failed observations stay missing. Trends terms are unverified search terms,
not authenticated issuer sentiment. No inference before 120 sessions.

## One new prospective shadow hypothesis: common-exposure risk budget

Question: can reducing common exposure lower downside without concealing poor
directional accuracy? Keep the selected names, sides and baseline relative
weights. Estimate covariance from the preceding 60 complete, matched 09:46 to
15:59 net-return observations; all training observations precede the decision.
Compute portfolio variance with and without off-diagonal covariances. Apply
one whole-book multiplier min(1, sqrt(diagonal_variance/full_variance)); if
full_variance <= 0 use 1. Missing data means no research result, never a
replacement trade. This can reduce gross exposure, not manufacture new alpha.

Evaluate prospectively after 60 additional complete sessions, on original
capacity including cash. Primary endpoint: paired daily squared downside
reduction versus baseline, accompanied by mean-net-return noninferiority
margin 5 bps/day, turnover, gross exposure and original per-leg hit rate.
Use a paired 20-session circular block bootstrap, 2,000 draws, seed 95; report
95% intervals and MDE80=(3.5+0.8416212336)*SE for paired mean net return. Report
the same endpoint against a fixed 0.75 exposure placebo and a planted paired
+5 bps/day control. Four sequential 15-session blocks must agree on downside
reduction. No significance or adoption claim before this sample; no tuning
the multiplier after September 9. Exact matched data are currently missing,
so implementation/inference waits for a verified prospective dataset.

Operational changes now: freeze diagnostics in brief.compute, make email
status reflect the actual dispatch clock, distinguish hypothetical allocations
from execution-verified observations, and align both existing scheduled jobs
with the reviewed main commit. None of these demonstrates higher prediction
accuracy. A finite failed study does not prove a universal feature ceiling.
