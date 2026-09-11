# Day98 — training integrity and repeated-loss review

Base reviewed: 3fb8a22, plus the concurrent 4ad373e losing-days audit, including the day97 microstructure audit and the
disabled-by-default corroborated-BBO option. Registration preceded the audit:
60feacd78fcbf22e632183ce75665fa0920befd9. Account-specific reports and raw
operational state stay private. No brokerage capability is introduced.

## Actual production defect

The live opening bars were validated, but `r945.run` built the historical
training pool with the legacy `session_rows` extractor. It admitted sessions
with only ten bars, used the third observed row as the opening reference,
used the final observed row as the closing label, and bridged missing trading
days when calculating the opening gap. A correctly timestamped current quote
cannot repair mislabeled historical examples.

`intraday_history.completed_history` now validates the exchange-calendar grid,
complete regular sessions, OHLC consistency, finite positive prices, finite
nonnegative volume and strictly preceding outcome dates. Incomplete sessions
are excluded and counted. The next session's gap remains missing unless its
immediate predecessor has a verified close. A verified shortened-session close
may anchor the next gap but does not enter full-horizon training. Outside-hours
rows and terminal markers never define the training close.

The legacy extractor is retained for reproducing past research. Valid, complete
sessions retain the same arithmetic. K=60, M=20, features [r0,gap,vp], score
clamps, qualification, density selection, peer filter and allocation are not
tuned. Refusing invalid training observations can change future fitted scores;
that is an explicit data-contract correction, not an alpha adoption.

Preflight now uses the same validation and cannot certify a file containing
only a last-session closing bar. The diagnostic list survives an unavailable
scan through the frozen report, with counts in the concise email and detail
in the attachment. Both renderers remain pure.

## Measured saved-cache audit

The restored pre-open cache contained 1,260 legacy ticker-session examples.
The validator retained 1,251 complete sessions, excluded nine incomplete
examples, and removed nine subsequent invalid gap values. Twenty-one initial
gap values are naturally unavailable because the cache begins without an
earlier close. Seventeen matched outcome labels differ because the legacy
extractor included a terminal closing marker; these are endpoint-convention
corrections, not realized alpha.

On 111 original published legs across 40 complete matched boards, zero
directional labels changed and the paired mean outcome correction was 0 bps.
The observed difference is degenerate: SE/CI/MDE are unavailable, not evidence
of arbitrarily precise improvement. Net/index MDE also remains unavailable
without matched execution observations. This check does not refit historical
selections or estimate before/after strategy returns. It does not establish
that these data defects caused any particular losing day.

Validation of all 21 cached symbols measured about 1.12 seconds locally;
the full descriptive audit took about 2.16 seconds. This is local CPU time,
not provider reachability or a delivery SLA. Independent acquisition budgets
remain 22/10 seconds, and no research runner is imported by the report.

## Portfolio context and prediction interpretation

Same-sector long legs can act as one common exposure even when the book is
dollar-neutral overall. `risk_evidence.assess` now freezes both group share of
gross notional and group share of its own side. The concise email places this
beside the legs, before the positions section. Its evidence line now includes
mean gross and measured-spread proxy returns alongside hit rates and missing
cost coverage. These presentation changes do not alter weights or turn a
historical analog score into a calibrated probability.

The concurrent `AUDIT_day98_losing_days.md` is preserved. Its concentrated-side
hit-rate comparison does not show that forced diversification improves alpha;
rejection #23 remains binding on adoption. It also does not establish that the
legs are independent: hit rate is not covariance or joint loss magnitude.
Disclosure and the already-registered risk-budget study are appropriate;
an automatic sector gate is not supported by these observations. The new
postmortem's September 11 price figures remain contributor-reported until
their underlying timestamped receipts can be independently checked.

## Contributor audit and next work

Kimi's day98 exploratory note calls [r0,gap] with K=30 production parity.
Current production uses [r0,gap,vp] with K=60/M=20. Its reported 55–58% lab
accuracies and selected 68.8% tail are exploratory, multiply compared and not
a matched production uplift. Likewise a small negative screen cannot close
an entire feature family. Preserve the note as research; do not import its
headline rates as forecasts. Its external EODHD entitlement observations are
distinct from this host's transport block and require their own receipts.

The existing day97 audit already tested ORB/VWAP, RVOL>=2.5 and lunch exits.
The RVOL gate rejected all 103 matched original selections, the ORB/VWAP gate
admitted only six, and the lunch exits reduced gross mean returns. None
demonstrated a profitable replacement. Avoiding all trades in a losing
development sample is not discovering an opportunity engine.

Rerunning the registered opening-path data check found 57 common raw sessions,
36 usable sessions after feature warm-up/gaps and zero eligible OOS sessions.
The registered floor remains 200 clean raw sessions and at least 60 OOS dates.
Seven months/145 sessions was a runnable prototype floor, not adequate
confirmation. No new fitted accuracy result is computed below this floor.

The route forward remains: authenticated native TSX history and timestamped
execution/index data; identical chronological rows and production math for
challengers; paired net expected value, cost sensitivity and downside alongside
accuracy; the preregistered common-exposure experiment versus a fixed exposure
placebo; and a separately untouched confirmation before promotion. These
corrections fix measurement and input integrity. They do not yet demonstrate
higher future hit rate or P&L.
