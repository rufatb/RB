# DeepSeek preparation-to-email boundary correction

September 14, 2026. Based on reviewed main `1b39eaca`. The earlier 14-name
current-time API probe verified a request and strict response, not the entire
scheduled preparation-to-report path. The user's pasted report retained the
actual failed pre-open snapshot: 0/21 assessed, missing macros and headlines.
That historical failure is preserved. A later successful model call cannot be
backdated to repair it.

## Confirmed defects

1. Production preparation checked whether a candidate had headlines and passed
   the SDK's public-field schema. That schema allows explicit nulls. It did not
   apply the complete-input gate used by the real-input probe. Missing RSI or
   macro data could therefore be sent, counted as model-assessed, and rejected
   by the report's real input validator. An existing test explicitly permitted
   the missing-macro submission. Production and probe now share one complete-
   eligibility helper; unavailable names retain their reasons and denominator.
2. The watchlist returned early on UNAVAILABLE with 0 assessed and 0 evaluated;
   its full view printed 0/0 beside the report's 0/21. The view now distinguishes
   requested, complete inputs, assessed, usable and threshold-passing counts.
   An unrun gate says NOT EVALUATED. Zero qualifying market opportunities is
   not inferred from a provider or input failure.
3. Existing pipeline tests substituted the prepared loader with fixture dicts.
   New integration tests exercise production preparation, SDK response parsing,
   snapshot sealing, the real loader, one Digest and actual email renderers.
   Only provider I/O uses deterministic fixtures. Timeout and malformed-response
   cases retain successful independent sections and explicit failure counts.
4. A preparation completing after 09:30 could initially say READY, although
   the reader correctly refused it. Preparation now marks the late result
   unavailable and retains returned assessments strictly as audit evidence.

New receipts retain source-requested, accepted, eligible, submitted and assessed
counts plus batch ticker identities. The reader checks new coverage receipts;
legacy snapshots still recompute observed assessments instead of trusting their
old counters. No original snapshot, publication, replacement, delivery or CSV
is rewritten.

## Current-time integration diagnostic: criteria fixed before running

`diagnose_deepseek_pipeline.py` takes existing canonical state and a new,
separate output directory. It reuses baseline historical files read-only and
exercises the same separate 60-name pool preparation, public evidence refresh,
complete-input gate, bounded model batches and sealed-snapshot validator as
production. It uses actual clocks. No model, size, threshold, roster, indicator
or baseline selection rule is changed to obtain a successful test.

The diagnostic requires an explicit isolated context without a publication
database or operations file. Its artifacts carry CURRENT_TIME_DIAGNOSTIC and
morning_snapshot=false. Production refuses these artifacts, including when
their timestamps happen to precede 09:30. An explicit offline, unpublished
Digest view accepts them through the same data validator. It cannot publish,
acquire quotes, select a new baseline or send email. Normal report commands
still consume only genuine same-session pre-open snapshots.

Integration PASS requires at least one actual assessment, all returned rows
remaining usable through the loader and Digest, unchanged assessment contents,
all model rows in the full HTML attachment, intact diagnostic labels and zero
forbidden network/model/publication calls during loading/rendering. Counts,
timestamps, errors, model identifiers and receipts remain available. Partial
source coverage is reported independently of integration PASS. A complete API
response on a subset never establishes full-universe readiness.

The runner records failures and refuses to reuse an output directory. Repeating
a diagnostic after a concrete code repair requires a new labelled audit, never
deletion of its attempt or reinterpretation as a morning result. A diagnostic
does not authorize another email or replacement. The preserved daily jobs
remain the single production sender.

## Scope and limits

The baseline remains TSX-21, K=60/M=20 and the same allocation. The 60-name
roster is research-only; the 0.50 contextual display threshold and all H1/H2
thresholds remain unchanged. All six protected modules and rejected studies
remain intact. No historical outcomes were inspected to choose a rule. Passing
integration tests, authentic API responses and fuller evidence coverage do not
establish increased hit rate, P&L, a calibrated probability or tomorrow's feed
availability. MDE and predictive validation remain governed by the unchanged
forward registrations.

Actual live diagnostic, full-suite and deployment results are recorded with
their exact revision and clocks in the pull request and private operational
receipts. The [JSON mode](https://api-docs.deepseek.com/guides/json_mode/)
and [thinking-mode](https://api-docs.deepseek.com/guides/thinking_mode/) API
settings were checked against the official provider documentation.
