# Day 90 — daily report architecture and evidence audit

Audited 2026-09-08. Working baseline: `cab243015a1e056d1707443d5156817c8dae83fc`
on `claude/session-rw51c2`. The repository default branch was an older dashboard
branch, so this work targets the current Claude branch without changing the default.
Read `CLAUDE.md`, `STRATEGY.md`, `INVENTORY.md`, `ACCURACY.md`, `DATA_CEILING.md`
and prior registrations before modifying logic. Published `PREREGISTER_day90.md`
in commit `a0b183c7ad745f0f8f6de48f6d0f6134ad785f41` before the new outcome analysis.

## Findings and disposition

| Finding | Evidence / consequence | Change |
|---|---|---|
| Report mixed acquisition, scoring, decisions and rendering | Re-rendering could fetch fresh facts and mutate records; legacy ledger renderer also fetched tide data | `brief.compute` acquires/computes once; text/HTML/JSON consume the same frozen schema-v2 report |
| Duplicate quote/options authentication | Separate cost and screen Yahoo implementations; last-price option fallback | One transport and shared BBO/contract validation in `quotes.py`; no last-price fallback |
| A last-trade timestamp is not a BBO timestamp | Fresh trade can accompany stale bid/ask | Separate validation; mark-only data cannot certify execution cost |
| `p945` was called a 09:46 fill | It is the close of the 09:40–09:45 bar | Separate signal reference, exact entry quote and exit observation; legacy label explicitly says proxy |
| “15:59 close” implied an exact observation | Legacy scoring uses official daily close | Retain original ledger and outcomes; new timestamped BBO record is independent |
| Single-entry spread was described as realised round-trip cost | Exit spread, commissions, slippage and borrow absent | Label historical same-spread proxy; exact scores require actual entry/exit BBO and explicit costs |
| Hit-rate formula claimed expected P&L | Equal-payoff assumption was unstated; median move is not mean conditional payoff | Cost renderer labels the arithmetic; net P&L comes from observed signed returns |
| Legacy tide was called an index | Universe median is not XIU/SPY | Separate independent-index attribution and matched-window long-minus-short diagnostics |
| Re-run/empty-board publication | CSV rows alone cannot distinguish unrun from valid no-pick | SQLite session publication includes zero-pick/outage days; hash checked; one writer across legacy side effects |
| Biotech mixed with short-horizon directional commentary | Existing broad FDA screen did not implement the requested universe or five-bullet objective monitor | Independent `biotech.py`, new staged universe/evidence feed, tri-state crowding and Top-2 ceiling |
| CRL availability assumption was stale | Official FDA transparency database now exists | Correct current `build_catalyst.py` documentation; preserve the original matched EDGAR sample |
| No production scheduling configuration | Neither inspected branch provided deployment workflow | DST-aware systemd preparation/report/exit units, bounded runner, email dedupe, CI and runbook |

## Unreachable code versus rejected research

Unreachable means absent from a specific runtime entrypoint's call graph; it
is not a deletion instruction. Rejected research encodes tested hypotheses,
controls and failure evidence. The earlier inventory identifies 23 standalone
study harnesses; **none is deleted** here. In particular, density, universe,
overnight, and timing/duration studies remain reproducible history.
The word “rejected” does not mean the file cannot execute.

Removed duplication is the old `brief.build` orchestration and the extra Yahoo
transport implementations. Compatibility formatting lives in `legacy_brief.py`;
legacy `report.py`, `screen.py`, advice and catalyst tools retain their separate
CLI/research uses. They are not the daily engine. Static imports through
`brief.__getattr__` must not be mistaken for daily execution. No study is revived
because a helper is still imported by a test. No baseline features, qualifier,
universe, selection tie-break or risk-allocation parameters were tuned.

## What the data actually supports

Reproduction: `python validate_execution.py --as-of 2026-09-08`.
Input hash and full outputs: `data/day90_results.json`.

| Measurement | Result | Interpretation |
|---|---:|---|
| Historical pair legs | 107 | Discovery observations, not new holdout |
| Gross hits | 52 / 107 = 48.60% | No demonstrated directional edge |
| Decisive gross hits | 46 / 99 = 46.46% | Eight scratches excluded under existing definition |
| Gross mean capture | -0.05753% / leg | Unweighted historical close proxy |
| Legs with stored spread | 6 / 107 | 101 cannot support a net-cost claim |
| Complete weighted sessions with stored spread | 2 | 37 incomplete sessions; not a representative performance sample |
| Same-spread proxy mean | +17.84 bps/session | Exploratory, fees/slippage/borrow absent |
| Session-bootstrap 95% interval | -3.03 to +38.71 bps | Two sessions; no adoption evidence |
| Rejection-threshold MDE | 51.68 bps/session | 3.5 × SE |
| 80%-power MDE | 64.10 bps/session | Far above the preregistered 5 bps target |
| Planted 5 bps control | z = 0.339 | UNDERPOWERED, not NULL |
| H1, H2, H3a, H3b exact-window tests | BLOCKED | Missing historical BBO/volatility/index/alternative-exit panel; individual MDE unavailable |

No change has proved a pick-accuracy or P&L improvement. All execution overlays
remain shadow observations. Prospective evaluation starts 2026-09-09, requires
252 sessions on **both** native markets and all registered gates. The current
live intraday universe remains TSX; the US holdout must be supplied separately.
Synthetic positive/negative controls validate the harness, not trading results.
The variance-only gate reports its own claim and never promotes production
settings automatically. Overnight remains unadopted.

## Data availability and source corrections

A live Yahoo universe probe returned `YFRateLimitError` on 2026-09-08. The scanner
records an incomplete universe and refuses to invent the ADV20 top-100 rank.
No reviewed upcoming-event feed was supplied. `data/biotech_events.json` is
explicitly empty; it is not a claim that no catalysts exist. The SEC candidate
queue discovers filings but cannot by itself establish event-calendar completeness.

The shared quote validator requires true bid/ask timestamps; ordinary Yahoo
responses often omit them. A fresh last trade can mark a held position but
cannot certify executable quotes or option expectations. Supply a timestamped
feed through `RB_QUOTES_JSON`; see `BIOTECH_DATA.md`. No live Top 2 or execution
quality claim has been manufactured to disguise these blockers.

FDA now publishes approved and unapproved application CRLs, including redacted
letters, in its [official transparency database](https://open.fda.gov/apis/transparency/completeresponseletters/).
This invalidates the older “FDA never publishes CRLs” assertion. It does **not**
justify replacing the historical EDGAR numerator while keeping a different
approval denominator. Any new base-rate study needs a matched population,
coverage audit and separate preregistration. A CRL is an observed disclosure,
not a predicted upcoming rejection; the monitor may track sourced follow-up windows.

[GitHub schedule documentation](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#schedule)
states that scheduled runs may be delayed or dropped and execute only on the
default branch. GitHub cron is therefore not presented as a minute-level SLA.
The supplied systemd timers require an always-on host and monitored delivery.
A ChatGPT scheduled task is a best-effort preparation/email path, not a guaranteed
09:46 inbox-arrival service. Email transmission and inbox arrival are distinct.

## Verification and limits

The original baseline suite passed 943 tests before implementation. The first
full implementation run passed 1,022 tests. Additional operational boundary
checks cover borrow costs, timestamp windows, oldest option observation time,
SEC candidate quarantine, short-data MDE and deadline fallback. See the PR for
the final full-suite result and exact revision.

No brokerage order is placed. No historical outcome is rewritten. No production
SMTP credentials or always-on host were available in this workspace, so the
systemd units are supplied but not claimed active. Live feed completeness,
real delivery latency and the prospective adoption gates remain operational
acceptance criteria; passing unit tests cannot certify them.
