# Day96 pairs research: execution-contract amendment

Recorded during integration on 2026-09-09 ET, before running any pairs
outcomes in this review. PREREGISTER_day96.md is preserved verbatim. This
amendment governs subsequent implementation and evaluation; a result already
computed under the original cost definition would require separate labeling
and cannot be treated as a confirmatory result under this correction.

## Signed trading P&L must include losses created by costs

The existing clamped `net_of_cost` transforms a signed statistical effect.
It is not a trading P&L function. For trading returns, subtract nonnegative
costs from signed gross P&L. A synthetic +3 bps gross trade with 5 bps cost
loses 2 bps; a -3 bps trade with the same cost loses 8 bps. Clipping either
result toward zero overstates strategy performance and corrupts hit rates.
Leave the legacy helper and its prior research interpretation unchanged.

Declare the denominator before running the pairs study. On gross deployed
notional, two equal-notional legs each paying 5 bps round trip cost 5 bps
of the pair's total gross notional, not 10 bps. Relative to one leg's notional,
the same currency cost is 10 bps. Both conventions are possible, but gross
returns, trading costs, hit rates and MDE must use the same denominator.
Borrow, fees and slippage remain separately observed or explicitly assumed;
an assumed spread is a sensitivity analysis, not verified executable net P&L.

## Freeze formation, sizing and timing before evaluating

The original design combines an OLS hedge ratio with dollar-neutral sizing.
These are not generally the same exposure. Preserve its dollar-neutral
execution rule: each leg has half the gross notional; an OLS residual may
define the signal but does not silently set trade weights. A beta-weighted
execution arm needs a separate preregistration and search correction.

Define the exact signal observation time and attainable entry before running.
A signal calculated from both official opening prices cannot assume fills at
those same opening prices. Use the previous completed-session signal for the
daily open-to-close proxy, or preregister a later observable entry supported
by timestamped data. Neither certifies the 09:46-to-15:59 contract.

Every data-dependent pairing choice, formation method and threshold must be
repeated inside each placebo draw. Preserve serial structure with specified
blocks or independent circular shifts; do not shuffle individual dates into
an artificially independent sample. Freeze those choices and the number of
draws before seeing outcomes. Keep chronological holdouts untouched.

Report session-clustered uncertainty and MDE in return units under the same
notional convention. All original rejection, survivorship and prospective
shadow requirements remain. No pairs strategy is deployed by this release.

## Contributor integration check

The release incorporates main through cac0666 after the earlier reviewed
quote and clock corrections. The merged social collector retains both the
fixed-window/censoring fields and strict timestamp, identity, duplicate,
first-write and pre-open coverage checks. Its decision-time annotation uses
collection completion, not merely the start time.

provenance.py is an advisory presence check. Matching filenames, symbol names
and record dates does not prove matching function bodies or same-date record
values. Its clean verdict does not replace a diff review, tests or immutable
runtime import conflict checks. A reviewed detached commit is intentional in
the scheduled path; that path does not execute morning.sh or its git pushes.

## Subsequent source review: 7628cef

Claude published the completed pairs study while integration was underway.
Its actual implementation already subtracts signed costs correctly. Its
`gross = side * (ri - rj)` and 10 bps cost consistently use one leg's
notional; the report now states that denominator explicitly. No cost change
or rerun of the published result is needed for that accounting convention.

The original study and rejection #41 remain intact. They are not proof about
all pairs strategies or an attainable 09:46 entry. The open-derived signal
and same-open fill assumption, full-history survivor selection, conditional
return-reassignment placebo and late-added TOP_K/refit settings limit the
claim that the design was followed exactly. A liquidity concentration is
consistent with survivorship bias, not causal identification of that bias.

The validator had certified replication using the holdout's own best cell.
Future runs must instead pass the development-selected cell, with positive
net return, the same t threshold and the holdout max-placebo threshold. They
must also document disjoint issuer/date observations; unknown provenance
or reused issuer/date samples cannot count as holdout evidence. Separate
issuers can still share market shocks, so disjointness is not independence.

The original 3*SE quantity is a significance threshold, not an 80%-power MDE.
Future summaries show both it and the approximate (3+0.8416)*SE MDE80.
Adding a constant to already realized trade returns checks statistical
sensitivity; it does not prove that feature formation and selection recover a
planted predictive mechanism. These corrections do not turn a rejection into
adoption. Original result JSON and strategy history are not rewritten.

The TSX history builder previously authenticated neither returned symbol,
currency nor declared daily granularity, silently skipped invalid OHLC,
treated missing volume as zero, used host-local date bounds, and wrote a
partial universe after failures. Future acquisition validates those fields,
ET dates and completed exchange sessions, rejects duplicate/unordered dates,
and preserves the previous file when the requested universe is incomplete.
This does not retroactively certify the already published daily panel.
The pairs loader also checks finite, positive price inputs and verifies the
stored percent return against its own open/close prices. The US development
and holdout CSVs were not present in this checkout, so this review cannot
independently reproduce their reported effects or assert that they overlap.
Future runs also retain a zero-return cell ahead of losing cells (zero is not
missing) and use the finite-draw +1 correction for Monte Carlo p-values;
zero exceedances in a finite placebo sample never means a probability of zero.
