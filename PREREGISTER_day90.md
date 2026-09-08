# PREREGISTER_day90 — execution cost and report integrity
Registered 2026-09-08 before running the new outcome analysis. Baseline:
cab243015a1e056d1707443d5156817c8dae83fc (claude/session-rw51c2).

## Scope and prior knowledge
Days 1–89 are discovery data, not an untouched holdout. Their documented
rejections remain in force, including overnight and entry/hold-time grids.
This registration does NOT modify r0/gap/vp, k-NN, qualification, peer filters,
density selection, universe, or baseline allocation. Infrastructure corrections
are not alpha claims. Biotech is an independent factual monitoring engine.

## Three fixed hypotheses; no parameter search
H1: abstain from a baseline leg when its entry spread exceeds 10% of that
name's trailing entry-to-close standard deviation. Missing/nonfinite/stale
quotes also abstain as a data-integrity rule, never as evidence of an edge.
No replacement leg; unused allocation stays cash.
H2: multiply each original allocation by max(0, 1 - spread_bps /
(100 * trailing_vol_pct)). Never rescale the remaining legs upward.
H3: compare fixed 15:30 and 15:45 exits to 15:59 on the identical baseline
09:46 entries. These alternatives remain research-only. Overnight is retained
as a rejected historical study, not silently reopened or deployed.

## Measurements and eligibility
The published p945 is the close of the 09:40–09:45 bar, NOT a 09:46 fill.
For exact execution studies require timestamped entry/exit bid/ask or actual
fills at the declared times. Bar-only and historical-ledger analyses must say
PROXY, and cannot certify the exact execution contract.
Net midpoint return subtracts half the entry and exit spreads, commissions,
slippage and short borrow where applicable. Missing costs are missing, never
zero or today's quote substituted for yesterday's. Report gross, net hit rate,
decisive net hit rate (absolute net capture >=0.10%), book-weighted net return,
long-minus-short return and benchmark attribution separately. The independent
index is XIU.TO for TSX and SPY for US, measured over the same window; the
universe median is separately labelled and cannot be called the index.

## Adoption gate
Prospective holdout starts 2026-09-09. Require at least 252 distinct sessions
on BOTH native markets, four consecutive chronological blocks, point-in-time
membership, complete costs and matched index observations. Legacy rows and
rolling Yahoo windows are exploratory only; no promotion based on them.
Compare paired session returns on the SAME baseline opportunity days, retaining
abstentions as zero return on original capital. Primary: net selection return.
Require positive paired difference in all four blocks on both markets, pooled
z >=3.5, improvement >=5bps/session on original capacity, and a 95% lower
confidence bound above zero. Reject concentration where any name supplies >20%
of improvement. No worsening of 5% expected shortfall by >1bp/session.
A variance-only adoption must be named as such: >=10% volatility reduction in
all blocks, mean-net noninferiority within 1bp, and no accuracy improvement claim.

## Power and controls
Cluster by SESSION, not ticker. Use deterministic 10,000 session bootstrap
draws (seed 90) of paired differences; uncertainty includes no-trade days.
Report both rejection threshold MDE=3.5*SE and 80%-power
MDE=(3.5+0.8416212336)*SE, in bps and net-hit percentage points as applicable.
Fewer than 2 independent sessions: MDE unavailable, never zero.
A planted +5bps/session must be detectable using edge/SE (not mean+edge/SE);
otherwise label UNDERPOWERED. A session sign-flip placebo of the maximum across
the four arms (H1, H2, H3a, H3b) must be beaten at its 95th percentile.
No inspect-and-retune, no stopping when significance first appears.
Report every arm, missing-data counts, negative results and input hashes.

## Deliverables and expected result
Implement collection, paired evaluation, pure report renderers and fail-closed
data validation. Expect the historical cost comparison to be BLOCKED or
UNDERPOWERED because exact quotes/volatility/index windows were not persisted.
Do not promise an accuracy or P&L improvement. Publish the actual result.
