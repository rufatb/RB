# Day98 — historical-label integrity audit, no strategy search

Recorded before the new audit/replay. Repeated TRP/ENB losses motivate this
review; those observed sessions and the existing cache are development data,
not an untouched confirmation set. Preserve all prior rejected research,
published rows and the day94–97 shadow experiments.

## Fixed correctness question

Does the live training path actually use complete, regular-session five-minute
observations? The current `session_rows` legacy path accepts ten bars, picks
the third row as the opening reference and the final row as the close, and
can carry a previous observed close over a missing exchange session. The live
opening validation does not validate those historical labels.

Add an explicit production history validator: aware sorted unique index,
exchange-calendar grid, full standard sessions, finite positive consistent
OHLC and finite nonnegative volume. Ignore and count out-of-session rows;
reject and count missing/invalid regular-session bars. Only dates strictly
before the decision date can be outcomes. Gaps require the immediately prior
exchange-session close. A missing session cannot be bridged. A verified short
session close may supply the next day's gap, but its outcome is not a
standard 09:45-to-regular-close training example. The legacy extractor remains
available to reproduce historical studies; no rejected result is rewritten.

Healthy complete-data features, k-NN K=60/M=20, normalization, qualification,
density tie-break and allocation must remain numerically identical. This is
data-contract enforcement, not an optimized predictor. Integrate diagnostics
through `brief.compute` and pure renderers; never rewrite a frozen report.

## Fixed descriptive audit

Use the already prepared native TSX cache, retaining its identity and hashes.
Count each exclusion and compare old/new labels on matched ticker-dates.
Retain original published sides. Report old/new signs and gross return-proxy
differences; no hand-selected ticker subsets or parameter searches. No net
P&L improvement without matched cost data. If a before/after return difference
is reported, use complete original boards, equal original-leg capacity,
five-session moving-block bootstrap (2,000 draws, seed 98), and report MDE80
=(3.5+0.8416212336)*SE. Fewer than 20 dates or zero SE means inference unavailable.
This is label correction sensitivity, not a backtest of a new selection rule.

## Subsequent research priorities

Audit contributor parity before trusting headline lab accuracy: production
uses three features and K=60, not two features and K=30. Small exploratory
screens cannot establish a family-wide rejection or positive edge. Retain
the existing opening-path comparison and its >=200 clean-session floor.
Real net expected value, paired chronological confirmation, downside and
common-exposure control are required alongside accuracy; an all-abstain
result is not a profitable opportunity engine. No new fitted strategy is
automatically adopted from this audit.
