# Day99 — DeepSeek integration and daily report boundary audit

Base: main 72e92e8, including PR #11 and the subsequent abstained-leg display
correction. Read CLAUDE.md and STRATEGY.md before edits. Registration a82b94d
preceded implementation and API interrogation. The six protected modules are
unchanged; no live brokerage execution or strategy promotion is authorized.

## Inventory and exact edit plan

A conservative AST audit found 122 root Python modules, 40 transitively
reachable from brief (including compatibility imports). Static reachability is
not proof of runtime execution. The other 82 include operational entrypoints,
email views and retained research. `legacy_brief` remains reachable through
`brief.__getattr__` and its compatibility tests. No research module qualifies
for deletion merely because today's report does not import it. The older
70-module INVENTORY tables are historical, not current counts.

| Files | Change and reason |
| --- | --- |
| quotes.py, cost.py, screen.py, collect_execution.py | One validated quote boundary, per-symbol isolation, typed failures, bounded transient retry; retain outage observations and prepared provider selection |
| brief.py, daily_job.py, deliver_report.py, diagnostics.py | Digest-returning build, independent local-record failures, safe bounded errors, persistent assembly outage artifact and actual delivery-time rendering |
| adapters.py → adapters/__init__.py | Preserve every existing adapter export while allowing the requested DeepSeek submodule; no competing module/package copies |
| adapters/deepseek_adapter.py, deepseek_policy.py | OpenAI-compatible bounded client, strict four-field model output, evidence-only inputs, DESIGN configuration |
| factor_inputs.py, prepare_deepseek.py, deepseek_factors.py | Deterministic technicals, staged pre-market factor assessment, local-only snapshot consumption and shadow abstention/cost ordering |
| analyst.py, scan.py, r945.py | Explicit provider integration and access to the already-computed candidate pool; no extra selection pass or automatic replacement of baseline |
| daily_render.py, email_render.py, readiness.py | Same Digest, persistent unavailable-section blocks and concise labelled DeepSeek research context |
| tests and operational documentation | Payload, timeout, malformed-input, clamp, replay, no-network-render and protected-file regression coverage |

Unused local calculations/imports in legacy formatters can be proposed for a
later isolated cleanup; no deletion is necessary for this integration. Preserve
all rejection logs and the existing private immutable reports/delivery state.

## Verified failure paths

1. `_compute` validates all equities in one comprehension inside one try. One
   malformed row can erase all successful symbols from the local result.
2. Ledger loading and position marking can raise outside isolation. The
   catastrophic runner then invokes the same assembly again offline and may
   fail identically, producing no artifacts.
3. `brief.build` currently returns text, despite the requested Digest contract;
   its relative default config also depends on headless working directory.
4. The cost path constructs Yahoo directly, ignoring a configured snapshot.
   Execution collection can lose every outage observation on a transport error.
5. Missing-timestamp BBO corroboration also attempts to rescue explicitly stale
   timestamps, beyond its documented purpose, and hides provider exceptions.
6. Some adapter/scan fallbacks swallow exceptions; raw exception text elsewhere
   can carry authenticated URLs into reports.
7. SMTP builds its delivery view before authentication can cross the permitted
   minute. The existing Gmail path already has a separate late-view recheck.

The modern daily_job→brief.compute→render path already used one computation.
Earlier empty email sections followed acquisition failures, not proof that a
successful board was hidden by rendering. The 44/93 figure in the request is
an earlier snapshot; current report counts must come from the unchanged ledger.

## Model boundary and provider documentation

The official [DeepSeek JSON guide](https://api-docs.deepseek.com/guides/json_mode/)
documents json_object output, a JSON prompt/example and the possibility of empty
content. JSON mode is not schema validation; the application rejects unknown
tickers, extra/duplicate fields, nonfinite numbers and truncated responses.
The [API reference](https://api-docs.deepseek.com/api/create-chat-completion/)
uses the OpenAI-compatible https://api.deepseek.com endpoint.

Current [model discovery documentation](https://api-docs.deepseek.com/api/list-models/)
lists deepseek-flash/deepseek-v4-pro examples; the user's requested
deepseek-chat/deepseek-reasoner identifiers must be checked against the actual
account response. An unsupported identifier must not silently switch the model.
The requested default stays configurable. The [error reference](https://api-docs.deepseek.com/quick_start/error_codes/)
distinguishes authentication, balance, parameter, rate-limit and server failures.
A host transport block is not provider denial.

No API output can override Python indicators or supply its own probability.
No LLM-generated old-date sentiment can become a retroactive backtest input.
The two registered arms are unadopted; unknown exact costs or insufficient
forward history leave accuracy uplift and MDE unavailable.

## Verification

Implementation, test results, live probe and release status are recorded below
after execution; passing fixtures will not be described as a successful live feed.

Full regression: **1,723 tests passed** on the integrated worktree (Python 3.12).
The historical request's 651-test count is obsolete. Additional final receipt
integrity/output-cap cases are checked separately and again in PR CI.
The canonical offline JSON command completed; it reports unavailable staged
factors rather than fake zero-edge market findings. Runtime imports passed.
The six protected files and ledger/universe CSVs have no diff from 72e92e8.
No rejected research was deleted, no old outcomes recomputed, and no email sent.

The late-clock review added an assembly-time check after local factor validation
and marks already-computed legs ABSTAIN if the minute elapsed, without running
selection or allocation again. A frozen report also survives malformed current
configuration: lookup precedes config loading. New tests prohibit network/model
work during rendering and frozen rereads; optional factor failures preserve the
same baseline legs, pair and allocation.

Live verification on 2026-09-12: an initial local SDK constructor failed because
socksio was absent on the configured proxy host. Installing httpx[socks] resolved
that dependency. Authenticated GET /models then succeeded and returned exactly
`deepseek-flash` and `deepseek-v4-pro`. Explicitly selected `deepseek-flash` for
private operation; a single synthetic JSON contract probe returned READY with
NO_EDGE and sentiment 0.0. No actual stock picks or accuracy result were tested.
The private receipts retain the real clock and selected model. Availability of
DeepSeek does not establish access to TSX prices, news, 8-K tags or live BBO.

Freshness review found that a six-hour macro limit would mechanically reject
prior TSX closes every pre-market morning. Dated macro references now require
an observation at or after the immediately preceding TSX session close and no
later than the input snapshot. Older and future observations are rejected,
including holiday cases. Snapshot freshness remains six hours. Calendar lookup
runs once per pool; a 500-candidate local validation took 0.1893 seconds, which
is a CPU measurement, not a report delivery SLA.

The current canonical state archive resolved to version 16, but two downloads
failed with HTTP 502. No older local state was uploaded over it. A separate
four-file private overlay was saved and its importer tested against existing
publication history. Preparation imports it only after restoring the current
canonical state. The importer cannot initialize, replace or alter reports.sqlite3;
it rejects credential/model conflicts and retains newer diagnostic receipts.
Operational task updates below use the reviewed release and preserve the one
Gmail sender, delivery claims, replacements, calendars and rejected research.

Measured improvement: **none yet**. H1/H2 are preregistered shadow arms. Existing
44/93 (47%) in the request is historical, not a current measurement or forecast.
Unknown exact costs, missing data and insufficient forward paired sessions block
an accuracy/MDE claim. No hindsight sentiment backtest or strategy promotion was
performed. Cost ordering uses observed entry spread, not known future exit cost.

Final hardening: the loader requires a checksum over the entire saved receipt,
including assessments; changed sentiments with otherwise valid JSON cannot be
replayed as the original output. Completion output is capped at 8,192 tokens.
**220 affected tests passed** after these changes. Provider request/response
model and response IDs are retained separately when returned; missing IDs are
not fabricated. The full preregistration was published as a separate ancestor
commit before implementation (`7d0817e` remote; original local `a82b94d`).
