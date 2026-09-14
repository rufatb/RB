# Day 100: diagnose the September 14 acquisition failures

Reviewed base: `4a4559598470ad3c92272c02a9d24424ca661f65`.
Date: September 14, 2026. All observation times below are America/New_York.

## Observed failure, not a rendering defect

The interactive preview computed at 09:52:56 retained a file-validated,
complete 21-name history cache prepared before the open. Its intraday worker
completed in 13.425 seconds, but 20 current-session chart requests failed.
NTR.TO returned 4,686 combined bars; no names ultimately cleared evaluation.
Thus it is incorrect to say every fetch failed, or that an empty cache is
the established cause. The current-day acquisition and incomplete evaluation
prevented a usable board. That is not evidence of zero market opportunities.

The prepared-cache path limited each Yahoo host request to two seconds.
Separate diagnostic requests using the host's existing configured transport
returned HTTP 200 for the exact ENB.TO chart, CAD currency and five-minute
granularity:

| Request started | Range | Elapsed | Returned bars |
| --- | --- | ---: | ---: |
| 09:56:32.650109 | 1d | 7.187 seconds | 7 |
| 09:56:39.837556 | 60d | 5.453 seconds | 4,609 |

These observations establish reachable chart data with latency above the old
cutoff. They do not certify the whole universe, executable BBO, or the cause
of every previous outage. The 60-day request was a diagnostic, not a new
purported pre-open cache. Neither diagnostic changed training inputs or reports.

The separate equity-quote worker exhausted its ten-second budget. Its direct
client call could perform cookie, crumb and data requests at eight seconds
each; it bypassed the aggregate-budget helper. Missing results subsequently
appeared as SYMBOL_MISMATCH instead of retaining the transport failure.

## Acquisition-only correction

- Cached Yahoo acquisition uses one bounded wave (at most 24 default workers),
  preserving configured universe ordering through executor.map. Explicit worker arguments remain
  authoritative. Ordinary adapter timeouts and uncached default concurrency
  remain unchanged.
- Each chart has one sixteen-second budget shared by primary host and failover,
  with a fourteen-second socket timeout,
  plus a shared eighteen-second chart deadline. The report's existing
  twenty-two-second killable process remains the hard limit, including model
  computation. Socket timeouts alone are not a timing guarantee.
- No queued request starts after the shared deadline; responses returned after
  their budget are refused. HTTP 429/401/403 do not trigger a second-host retry.
  Controlled timeout, rate-limit and authentication classes survive diagnostics.
- Equity acquisition now uses a raw-row helper with an eight-second aggregate
  budget inside the existing ten-second worker. Cookie, crumb and data stages
  remain visible if killed. Only the expected cookie HTTP 404 is tolerated.
- The validated quote API remains compatible. Raw rows are validated once;
  failed sections produce typed empty placeholders, retaining successful sibling
  sections and recorded facts. A batch outage appears once in the diagnostic
  summary; every affected quote still retains its own cause. No missing quote
  becomes an executable price.
- Coverage failures retain already-computed exclusion explanations while still
  refusing selection below the existing coverage floor.

## Scope and verification

This changes neither the features, K=60/M=20, probability clamp, coverage floor,
selection, allocation, six protected modules nor any preregistered experiment.
DeepSeek remains shadow and its morning attempt is not retried after the open.
Biotech certification and quote freshness remain separate requirements.
No predictive-accuracy or P&L improvement is claimed. No historical report,
delivery claim or private runtime record belongs in this code change.

New regression checks cover slow successful charts, shared host/global budgets,
late-response rejection, no retry on entitlement/rate-limit failures, safe
exception metadata, quote-stage survival and unchanged complete-data boards
between serial and concurrent acquisition. Full verification: 1,744 tests
passed in 196.26 seconds, with six pandas deprecation warnings in the synthetic
parity fixture. Passing tests alone do not certify feeds.

## Recovery observations

The first recovery at 10:09:01, revision `c9a552a`, evaluated nine names versus
zero in the original preview. It still failed the unchanged 80% coverage floor.
All twelve first-wave chart requests exhausted their eight-second budgets;
the queued nine returned approximately 1.3 seconds after starting. Intraday
completed in 11.574 seconds. Quote cookie acquisition took about 7.5 seconds,
then the crumb stage exhausted the eight-second aggregate budget. The quote
placeholder now correctly reports TRANSPORT_TIMEOUT instead of SYMBOL_MISMATCH.

This evidence prompted the bounded single-wave arrangement documented above,
within the unchanged eighteen-second chart and twenty-two-second worker limits.
It changes request scheduling, not outcome-based selection. Quote authentication
remains an independent unresolved availability risk; longer chart tolerance
does not establish executable quotes or repair provider entitlements.

The second recovery, computed at 10:12:25 on `d78590b`, fetched and evaluated
all 21 names independently in 12.295 seconds, using 1,251 validated historical
rows. It did not reuse nine partial successes from the first recovery. The
unchanged baseline returned CP.TO and BCE.TO long, BMO.TO and SLF.TO short.
These are hypothetical research selections, not confirmed holdings or fresh
entry calls: all four were ABSTAIN because the actual clock was late and the
quote worker again timed out, this time at the cookie stage (8.104 seconds).

Both original and recovery computations are retained as audit artifacts;
none was published or sent. This single successful chart scan is not a
minute-level SLA or evidence of predictive improvement. Scheduled jobs still
need reviewed deployment of the fix; this branch does not repin them itself.
