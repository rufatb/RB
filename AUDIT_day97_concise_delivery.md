# Day 97: concise delivery and preparation evidence

Date: 2026-09-10. Reviewed base: `0096cf1d25e1bd3373a8d981a5d8da1c0250768a`.

## What the operational evidence establishes

- The preserved September 10 cache was complete, 21/21 names, prepared at
  08:13:40 ET. The saved 09:46:23 preflight also said READY. Reading every file
  now confirms those identities and prior-session contents. An absent cache
  is not an established cause of this email's 22-second intraday timeout.
  Its old acquisition worker did not retain the stage at which it stalled.
- An offline computational replay of the archived September 9 bars, truncated
  before 09:46 that day, evaluated 21 names in 2.782 seconds with profiling.
  No provider was called, signal published or strategy changed. This directs
  investigation toward acquisition but proves neither live runtime nor
  predictive accuracy. Main's per-host deadlines and stage diagnostics remain.
- Massive is an actual connected provider. A freshly returned
  `/v2/aggs/ticker/ZYME/prev` response contains a September 9 close of 27.15 USD,
  matching the stored reference. No evidence shows a fixture supplied that
  price. The former documentation URL did not establish observation provenance.
  The repair retains the returned bar, timestamp, provider and data endpoint.
  [Official endpoint documentation](https://massive.com/docs/rest/stocks/aggregates/previous-day-bar).
- A 09:43 options observation is too old for the existing 120-second maximum
  age at 09:46. Standalone report preparation now starts at 09:44 and waits
  until 09:46; options refresh starts at 09:45. The actual Gmail task starts
  preparation at 09:40 and uses the same publication wait. No second sender
  should be activated alongside it.

## Changes

The email becomes a compact view of the same immutable computation. It leads
with selected or recorded legs, shares and validation, then ledger positions,
reviewed events and short evidence/gap context. The complete HTML report is
attached to the same message. The full universe board, sources, empirical
outcomes, cost/index evidence, uncertainty and research details remain available.
Recently recorded closures are computed in `brief.py`, without reopening them
or treating ledger records as brokerage confirmation.

Preflight reads actual history files instead of accepting a manifest alone.
Published acquisition requires a configured prepared-cache path, preventing an
unset environment from silently triggering a 60-day fetch at publication.
Biotech discovery and security acquisition have independent killable deadlines;
completed batches are saved, and a rate limit or timeout stops further batches.
Partial coverage remains uncertified. This does not cure provider rate limits
or manufacture the missing universe.

Reference provenance validates the declared provider, exact ticker endpoint,
credential-free source URL and returned Massive bar identity/date/price. The
importer keeps the raw response and refuses conflicting or newer references.
It never changes holdings or frozen reports. US daily bars are dated context,
not live TSX quotes.

## Scope and verification

Baseline selection, allocation, quote checks, rejected research and
day94/day95/day96/day97 registrations remain unchanged. H1/H2, alternative
exits, pairs and opening-path research remain shadow/unadopted. There is no
new predictive-performance claim or reason to rerun selection.

Regression checks cover compact/full-view parity, informational dispatch,
one multipart message with one full attachment, immutable publications,
cached-file integrity, bounded partial biotech work, options freshness and
observed-price provenance. Live provider reachability is a separate gate;
tests and offline timing do not establish it. Tomorrow's report must keep
remaining acquisition gaps visible, rather than promise names.

The systemd files describe an optional standalone deployment. Editing them
does not install services on an inaccessible host. The existing Gmail tasks
must be updated to reviewed merged code and preserve durable claims and the
explicit 09:46 wait.
