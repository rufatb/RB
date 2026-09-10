# Day95 technical integration audit

This public document covers software changes. Session-specific loss analysis,
account allocations and operational publication/delivery records remain private.
The existing public strategy journal and account configuration are unchanged.

Main already contained Codex day90/91 and Kimi day92. This release integrates
Kimi's day94 research, then Claude's main quote-authentication and clock fixes.
No new predictor, allocation, holding horizon or brokerage capability is adopted.

## Correctness and report changes

- Risk evidence is frozen in brief.compute. Renderers no longer read config,
  fit an independence model or silently suppress errors. Empirical session
  counts, clustered uncertainty, score reliability and common exposure are
  descriptive evidence, not calibrated forecasts.
- Execution-check status leads each row; allocations are hypothetical. Recorded
  boards retain original names, sides and shares without becoming holdings.
- prepare_delivery.py annotates the immutable publication at the actual dispatch
  clock and produces one subject/text/HTML payload. It rejects pre-09:46 sends
  and marks late or partial dispatch informational in both email bodies.
- daily_job supports fixed and advancing test clocks, rejects mismatched dates,
  prevents pre-09:46 publication and preserves freeze-once outage behavior.
- Claude's Yahoo crumb Accept-header correction is retained. A quoted spread
  still needs an authenticated BBO timestamp to support execution evidence.
- The legacy binomial helper states its independence assumption. The daily
  report uses empirical counts. Exposure labels live in risk_evidence.py;
  the existing account configuration is not modified or republished.
- HTML uses email-compatible inline styles and table headings. Intraday,
  objective biotech Monitor, unranked calendar and holdings remain separate.

## Research review

The social collector counts unique valid messages within a stated 24-hour
window, records exclusions, preserves first-write observations and verifies
pre-open ET exchange sessions. Capped streams are observed counts, not total
traffic. Each usable name requires sufficient valid sessions. Unverified
search terms cannot establish issuer sentiment. No inference is adopted.

The cross-market harness rejects unauthenticated granularity, duplicate dates
and incomplete bars; enforces the declared discovery threshold; reports MDE
for confirmation/control; and serializes missing uncertainty as null. A
normal-feature shift is not a guaranteed fitted AUC gain. FX daily labels
without authenticated completion times are blocked to prevent look-ahead.
The corrected acquisition attempt remains BLOCKED, not a statistical null.

PREREGISTER_day95.md registers a future common-exposure risk-budget experiment.
Its exact matched data are absent; no production sizing overlay or accuracy
gain is claimed. Prior rejected studies and shadow arms are retained. See
STRATEGY_day95.md for the separate technical addendum.

## Validation and operation

The integrated suite passed locally, including immutability, duplicate and
ambiguous delivery, rendering purity, quote validation and synthetic research
controls. Focused regressions cover FX timing and correlated-session uncertainty.
Passing tests does not establish prediction accuracy, data access or an SLA.

Both existing morning jobs must pin the same reviewed main revision. Moving
main can supply CSV records only, never unreviewed code during scheduled runs.
Preserve operational history and version-guarded claims; unavailable state must
not be replaced by an empty database. Verified live feeds and a monitored host
remain necessary for a measured minute-level delivery SLA.
