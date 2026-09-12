# Day99 — staged DeepSeek factors and cost-aware abstention

Registered 2026-09-12 before implementation, API interrogation or strategy
evaluation. Development baseline: main 72e92e8. No historical score, side,
published report or brokerage position may be rewritten. Prior rejected
research and the day90/day94–98 registrations remain preserved.

## Architecture and fixed boundaries

DeepSeek receives only validated, timestamped public candidate evidence and
Python-computed indicators. It assesses sentiment/catalysts/macro alignment;
it does not calculate indicators, fabricate quotes, size orders or estimate
win probabilities. Its four-field JSON output is strictly validated against
the requested symbols. Missing/malformed/late responses remain unavailable,
distinct from a successful NO_EDGE assessment. No LLM call runs in renderers
or on the 09:46 report critical path.

Preparation accepts at most 500 supplied candidates. It never invents names
to satisfy that count or silently expands the production TSX-21 selector.
Local staged evidence can use a smaller actual pool with its count visible.
Missing news, timestamps, complete bars or macro components are explicit.
Preparation uses bounded batches and preserves success/failure coverage.
The model identifier, request/evidence hashes, prompt version and preparation
clock are retained. Keys stay in private host/state secrets, never git/logs.

`brief.build` returns the single Digest; compute remains its compatibility
entry. Terminal/HTML/concise email consume that same object. Existing frozen
publications return before acquisition. Section failures do not erase valid
independent sections. The canonical human entry remains
`TZ=America/Toronto python brief.py`; operational wrappers do not own another
selection pass. No live brokerage execution capability is added.

## Two fixed research arms, no adoption

H1 combines the production directional analog score q with the staged
sentiment s as p = clamp_probability(0.8*q + 0.2*(0.5+0.15*s)). These are DESIGN
weights, not a calibrated probability model or measured alpha. Values always
pass dashboard.clamp_probability, bounded to [0.35,0.65]. Reuse the existing
report.min_sided_p threshold (currently 0.55); require aligned BULL/BEAR
sentiment and valid complete factor evidence. Otherwise NO EDGE - WAIT.
Unknown quantitative values, malformed provider values and stale evidence
remain UNAVAILABLE; a clamped value cannot repair them.

H2 ranks H1's eligible pool by ascending observed entry spread in bps, then
descending sided score and ticker for deterministic ties. It requires an
authenticated, exact-session 09:46 BBO through the existing quote validator.
Missing costs and CORROBORATED prices do not qualify as exact BBO. Future exit
spread is unknown: the entry spread is a cost proxy, not realized round-trip
cost or an expected-return estimate. Each side has AT MOST two names and may
have none. Baseline order, selection, allocation and ledgers are unchanged.

These arms are additive SHADOW views until separate promotion is justified.
Do not reinterpret retrospective LLM knowledge of already-completed events as
point-in-time sentiment. Retain original dated forward inputs and model output.

## Evaluation and stopping rules

Compare on matched forward session populations with the same entry/exit/index
and measured spread/slippage contract. Abstentions are cash (zero return),
not rows dropped from the comparison. Missing execution observations are
coverage gaps, not zero-cost fills. Minimum 120 complete forward sessions,
first 60 development and subsequent 60 untouched confirmation; the existing
four-quarter robustness requirement still applies before promotion. Partial
data or failure of a planted positive control means UNDERPOWERED/BLOCKED.

Primary outcome: paired net return versus unchanged baseline. Also report
participation, gross/net hit rates, payoff ratio, drawdown and shared exposure.
Five-session block bootstrap, 2,000 draws, seed 99; MDE80=(3.5+0.8416212336)*SE.
Keep both registered arms in multiplicity accounting. Fewer than the required
sessions, absent exact costs, or zero observed SE means inference unavailable.
No threshold search, repeated holdout peeking or automatically adopted gain.

## Protected-file conflict

The request both forbids editing constants.py and asks for new thresholds
there. The explicit protection takes precedence: ledger.py, catledger.py,
advice.py, sanity.py, constants.py and resolved.py remain byte-identical.
New DESIGN bounds are separately declared in deepseek_policy.py and this
registration; the probability band and report threshold reuse existing sources.
No runtime mutation of constants.REGISTRY or bypass of protected checks.
