# Intelligent Capital DDA

The DDA v2 layer is a separate research policy. It does not replace the original
desk/council choices, change the email contents, consolidate emails, or edit the
Claude Code scheduled task. See `PREREGISTER_DDA_DECISION_V2.md` and its amendment.

The existing morning script starts `dda_hooks.py STATE research` after the shared
brief is prepared. This starts a detached, bounded process, with no wait in the
original morning. The full staged universe is assessed from business evidence;
up to six sourced cases receive targeted FMP earnings checks and a separate
OpenRouter Claude challenge/comparison. Up to two supported cases are published,
without a required long/short pair. The screen uses the configured DeepSeek model
with thinking enabled/high effort and a 20,000-token output budget; the challenge
uses the existing configured Claude route with high reasoning and 14,000 tokens.
No thinking transcript is published. Actual model routes, failure codes and
clocks are recorded. Truncated/invalid responses cannot become choices.

The primary pass has at most two recent eligible articles per issuer, including
available summary excerpts. This is not full-document diligence.
At capture, a separate 15-second FMP budget expands available release text by
matching existing issuer-classified archive URLs. Each excerpt is capped at
4,000 characters. Future/unknown-time/unmatched responses cannot add facts;
retrieval clocks and coverage are recorded. Missing text retains its summary.
Claims require exact source excerpts; new numerical magnitudes absent from cited texts are
rejected. The FMP check excludes same-day actuals with unknown disclosure times.
Current provider history is not a point-in-time backtest. Broker rating consensus
is not earnings consensus. Missing evidence stays explicit.

The council CLI, opening-check CLI and report CLI independently start data-only
exports. The hooks send no email and make no trading action. Public records:

* `data/reviews/dda/YYYY-MM-DD.decision.json`
* `data/reviews/dda/YYYY-MM-DD.opening.json`
* `data/reviews/dda/YYYY-MM-DD.open-check.json`
* `data/reviews/dda/YYYY-MM-DD.report.json`

First complete file wins, including no-choice and failed-research records. No
opening export can be backfilled after the bell. Late model output is labelled
informational. Runtime input/claim files live under `.rb-state/dda/DATE/` and are
never published. A failed same-day model attempt is not automatically rebilled.
Disable new sidecars only with `RB_DDA_ENABLED=0`; the original run continues.

Publication uses the scheduled run's existing Git identity/credential. A lock
serializes DDA publishers; only the exact new JSON can be committed. An 8-second
shared Git budget, no force/rebase/merge, and an ahead-of-remote code check protect
the original workflow. Failed publication remains in `dda-hook.log` and the
local record; a later stage may flush DDA-only pending commits. If killed while
holding `.rb-state/dda-publication.lock`, remove that empty lock only after
verifying no publisher is running. A schedule pinned to an old code revision
must sync main as its existing startup contract requires.

The platform reads these immutable public artifacts at a pinned GitHub revision.
Refreshing its DDA tab does not buy another model run. Historical model returns
are shown separately by exact rule, selection kind and recorded trading window,
with common-session comparisons. They are gross bar proxies, not fills or proof
of skill; in particular a 09:45 proxy can precede the 09:46 report's availability.
No forward result exists for DDA v2 at launch. Offline tests validate data and
workflow contracts, never prediction accuracy.
