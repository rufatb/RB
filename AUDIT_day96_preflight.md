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
