# DDA decision protocol v2 — registered 2026-11-10

Owner request: compare all engine-eligible tickers for a concise market-open
decision, add research and challenge passes, connect the platform automatically,
and consolidate morning emails. Today's AC/SU complaint is already known. It is
not a blind test and will not be used to tune numerical thresholds or claim an
accuracy improvement. Historical records and all previous registrations stand.

## Design, fixed before any new outcome analysis

1. Freeze the full staged candidate set, requested universe, per-name coverage,
   dated source facts, macro context, all desk nominations and the council's
   arguments. Never reduce the population to Claude's first long and short.
2. The first research pass reads business/event evidence for every eligible
   candidate, without charts, past returns, model confidence or model identity.
   It returns a coverage row per supplied name and at most six research cases;
   abstaining is allowed. Each case needs a dated source, a directional causal
   mechanism, why repricing may remain, and what would disprove it.
3. A separate-context challenge pass reads each proposed case and the same
   dated evidence. It returns support / thin evidence / contradiction, with
   source references and a concrete failure condition. It cannot introduce a
   ticker, an event, an invented price, a probability or an external fact.
4. The final comparison considers the challenged research cases, alternatives
   and the engine's original selections. It may publish zero, one or two
   research choices, in either direction, with why each beats its alternatives.
   There is no required long/short pair and no first-model priority. Price data
   is introduced only for execution conditions, chasing and invalidation.
5. Existing models, exact configured model names and private credentials are
   reused. Repeated passes through one provider are labelled as separate
   contexts, not statistically independent voters. Provider failures and
   unreviewed names remain explicit coverage gaps.
6. A decision completed at/after 09:30 is informational, not an opening-time
   selection. Only evidence available by the frozen cutoff is allowed. A
   later opening check can retain, invalidate or require reassessment of the
   original case; it cannot claim a fill at an earlier open or rewrite it.
7. Publish immutable, whitelisted DDA artifacts automatically under
   `data/reviews/dda/`, with code revision, evidence digest, capture and answer
   clocks, model routes, source references, pass status and reasons. Bounded
   optional publication cannot delay the original 09:30 or 09:46 deadlines.
8. One daily decision is the primary user surface. Additional desks and the
   original Top 2 remain auditable comparisons. Use one morning email and only
   a material opening-change update in the same thread when the sender supports
   it; keep the full 09:46 report in the platform, with email fallback only if
   the primary decision was not delivered. Never send a live test email.

## Verification harnesses

Offline planted fixtures must cover a stronger sourced alternative outside the
original Top 2, no-edge inputs, fabricated evidence references, a non-nominated
eligible issuer, an incomplete universe, conflicting sources, legal-notice
contamination, already-published results, late model answers, future evidence,
unavailable prices, provider failure, immutable reruns, duplicate publication
and duplicate delivery. They test implementation and provenance, not returns.

## Forward evaluation — no tuning on today's winners

Save every issued choice, alternative and abstention before its eligible
observation window. Evaluate the new policy separately from existing ledgers,
at the first tradable observation after its actual publication/receipt, never
retroactively at 09:30. Report outcomes by rule version and session, include
losses and missing fills, benchmark against XIU and the original choices, and
show user-entered friction separately. No result or bar will be rewritten.
No accuracy or profitability claim is made by deploying this decision workflow.

## Scope amendment — 2026-11-10, before outcome analysis

The owner's subsequent instruction supersedes the email consolidation in item 8:
**keep all existing emails separate and leave the scheduled task running as is.**
This implementation changes only DDA research, presentation, evaluation and
data-only publication hooks. It does not change the original desk prompts,
council selection, email senders or schedule. The original protocol stays above
so this amendment is visible.

The blind screen uses at most two eligible recent articles per issuer, verified
issuer releases first and then newest. Filter future/invalid/notice items BEFORE
applying that input budget. Publish available and supplied counts. Preserve
available release summaries and the staged, time-checked FMP analyst/earnings
context with its limitations. The later review sees price execution context,
but technical patterns alone cannot establish a business case.

Use the existing configured DeepSeek route for the full-universe screen and the
existing OpenRouter Claude route for a separate-context challenge and comparison,
with explicit reasoning/output budgets and recorded actual model/pass failures.
Neither repeats nor provider self-ratings count as independent empirical skill.
Model performance comparisons must separate nomination/selection, rule versions
and trading windows, and compare common sessions where possible. Existing
09:45-to-close bar proxies are gross research returns, not market-open fills or
realized profits. The new DDA policy has no forward results at deployment.

## Input completeness amendment — 2026-11-10, before any DDA forward results

Archive summaries are only opening excerpts. Before the blind screen, use a
separate 15-second read-only FMP budget to retrieve press text for the already
issuer-classified, recent, URL-linked releases in the staged universe. Match
the exact archived source URL, recheck disclosure times, and retain at most
4,000 characters per release and two releases per issuer. Use existing verified
US twin mappings only to find the feed; never treat a US pre-market call as an
intraday signal. Apply no outcome-based issuer priority or price filter.
The evidence cutoff is the completed capture, not the request start. Record
retrieval clocks, supplied excerpt counts and failures; an unmatched, future,
unknown-time or unavailable response cannot invent a source. The screen can
still abstain. The original desk/council inputs and email streams stay unchanged.

## Runtime repair — 2026-11-12, no selection-policy change

The first 150-name live screen consumed 181.906 seconds against a 180-second
whole-workflow budget. Verification therefore received zero seconds and the
required challenge never ran. The original incomplete record remains immutable.
This incident establishes a runtime defect, not evidence about candidate returns.

Allow at most 480 seconds for the detached research workflow, further bounded
by 09:29 ET. Reserve 18 seconds for verification, 180 for challenge/comparison,
and 10 for finalization before allocating up to 240 seconds to the screen.
Terminate each model worker at its actual wall-clock limit; HTTP socket timeouts
alone do not impose that limit. Do not retry or promote an unreviewed replacement.
A window too short to leave the required review time stops before a model call.
Record the per-pass allocation, elapsed time and correct failing route. Existing
evidence, eligibility, prompts, ranking and opening rules remain unchanged.
