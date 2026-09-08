# Pre-registration — day-93, the ceiling test WITH volume pace

Committed BEFORE any outcome is computed. Bar fixed here and does not move.

## Why this exists: the governing claim was never tested as stated

`CLAUDE.md` calls this "the constraint that governs the intraday engine":

> *`r0`/`gap`/`vp` carry no usable signal. Gradient boosting with ~100x the
> shipped k-NN's capacity reaches AUC 0.5022 on 122,234 out-of-sample rows.*

Day-91's audit found that study **omitted `vp`**. The reason is specific and
measurable, and `validate_ceiling.usable_feats` now states it: Yahoo zeroes the
volume on **~86% of the FIRST hourly bar** of a session, and the hourly pool's
entry IS the first bar. So `v15` was zero on 86% of rows and the feature was
unusable there.

Day-43 therefore measured **two features, not three**, and the claim as written
in CLAUDE.md — the one used to close every accuracy question for fifty days —
overstates what was tested. Day-91 said so plainly ("too categorical") and
corrected the harness. Nobody has yet run the corrected harness on a panel
where `vp` actually exists. That is this study.

**This is not a claim that an edge exists.** It is the observation that the
third feature was never in the test that is cited to rule one out.

## The constraint that shapes the design, stated first

`vp` needs sub-hourly bars. Yahoo caps 5-minute history at ~60 days, so a
vp-inclusive panel is **capped at roughly 40 sessions**, whatever the name
count. Session-clustered inference on ~40 clusters is weak, and this repo has
six separate mirages produced by 60-day windows.

So the honest reach of this study is asymmetric and it is registered as such:

- it **can** show that adding `vp` does not move AUC at a resolvable size
- it **cannot** establish that `vp` helps, on 40 sessions, no matter what the
  point estimate looks like

Any positive result is a candidate for a longer test, never an adoption.

## Hypothesis

**H1.** Out-of-sample AUC of the parity k-NN and of a higher-capacity learner
on `[r0, gap, vp]` versus the same learners on `[r0, gap]`, on an identical
5-minute pool where `vp` is genuinely computable.

The comparison is PAIRED on the same rows and folds, so the only difference is
the feature set.

## Statistics and bars

- **Statistic.** AUC difference, three features minus two, out-of-sample.
- **Bar.** The registered adoption bar is a **paired AUC gain whose
  session-clustered interval excludes zero**, with the gain exceeding the
  reported MDE. Day-43's own bar was AUC-based and this keeps it.
- **Clustering.** AUC influence values aggregated WITHIN session, per day-91's
  correction. Ticker-rows from one session are not independent draws.
- **MDE reported always** (rule 10). On ~40 clusters it will be large, and a
  null must be read as "cannot resolve", not "no effect".
- **Positive control.** The harness's planted-edge control must register, and
  the control size is reported beside the result.
- **Leakage.** `vp` uses a shifted expanding median (day-91's fix). A
  full-panel median would leak the whole sample into every row.
- **Zero-volume check.** The fraction of zero `v15` entry bars is measured and
  printed for the 5m pool. If it exceeds 25% the feature is DROPPED and this
  study reports NOT RUNNABLE rather than pretending to test three features —
  which is exactly the failure being corrected.

## What may be adopted

**Nothing, on this sample.** A positive result licenses one thing: a
pre-registered longer test on paid sub-hourly history. The 40-session ceiling
is not a bar that a good result can argue its way past.

What this study CAN deliver immediately is a correction to CLAUDE.md, which
currently states a categorical claim on the strength of a study that did not
test the feature it names.

## Forbidden

Reporting an AUC gain without its session-clustered interval and MDE. Treating
a 40-session result as an adoption. Quoting this as evidence the engine has an
edge. Dropping the zero-volume check because it is inconvenient.

## Expected outcome, recorded in advance

I expect the AUC difference to be small and the interval to contain zero, and I
expect the MDE to be large enough that the honest verdict is UNDERPOWERED. The
prior is day-43's own result on two features and the live record's 49% on 107
pair legs.

I am running it because the cited justification for closing the accuracy
question does not test what it says it tests, and that should be fixed whether
or not the answer changes.
