# Day100 — DeepSeek availability, research coverage and scheduled source drift

2026-09-14. Foundation: main 4a45595 plus the reviewed day100 acquisition
repairs. No protected module, baseline allocation, ledger or old rejection is
changed. This is not an accuracy claim or a replacement of today's publication.

## Established causes

The September 14 snapshot requested 21 names and covered zero, with no model
batches. News and macro acquisition failed before usable inputs reached
DeepSeek. The private configured model was `deepseek-flash`; the synthetic
capability check was not a market assessment. The scheduled job still pinned
4a45595, so a successful local chart repair did not reach that email.

Measured separately on the actual host, without overwriting the morning
attempt or immutable report:

| Check | Observation | Consequence |
|---|---|---|
| 25 synthetic DeepSeek rows | All 25 strict JSON records, 15.608s, Flash | Old 12s hard worker budget was insufficient; model requests now have 30s |
| Yahoo news/macro with 8s sockets | News timed out at 8.164s; four macro failures | Preparation's host limit also needed correction |
| Same public paths with 16s sockets | News 12.915s; macro 12.888s | Successful transport is distinct from valid evidence |
| Yahoo ticker search | RY.TO returned eight unrelated general stories, even with explicit news query ID | Do not reinterpret these as company catalysts |
| Exact RY.TO RSS feed | Correct ticker channel; current RBC items including a 07:11 ET release | Use checked ticker-specific RSS for TSX evidence |
| Final repaired public path | Four macro references validated in 7.803s; two linked RBC headlines in 10.403s | Actual feed path works for these samples; no claim of 60-name completeness |
| Yahoo cookie/crumb setup | 14.335s | Bootstrap exceeded the report quote budget |
| Quote with prepared auth | 6.775s; current CAD quote returned | Auth reuse fits the existing budget, but BBO timestamp still absent |
| Connected Massive ENB news | Empty response for the tested period | No claim that this route supplied replacement TSX evidence |

The prior chart recovery evaluated 21/21 names in 12.295s with the same baseline
math; its four legs were hypothetical/ABSTAIN and it did not rewrite or resend
the scheduled report. Keep acquisition diagnostics from both attempts.

## Implemented contracts

`prepare_factor_pool.py` stages an independent 60-name configured TSX research
roster, reuses baseline cache read-only, and validates added names' exact
symbol/CAD/Toronto/equity metadata. Current membership or liquidity ranking is
not inferred. Complete technical and staged-history counts are distinct.
Missing data, incomplete sessions and per-name exclusions stay visible.
Nonblocking locks, pre-open deadlines, saved payload hashes and once-session
attempts prevent unbounded waits or retrospective refreshes.

DeepSeek public acquisition uses the actual staged roster, 16s sockets,
12-name news waves, an 18s macro worker and a 120s public budget within 210s
overall. The actual 09:30 cutoff also applies. Up to four model batches run
concurrently, 25 records each, 30s each, no model fallback or SDK retry.
Independent successes survive errors; authentication/rate limits and complete
wave outages stop additional provider work. A 500-name cap is not a promise of
500 verified/evaluated names. Stored evidence is revalidated at assembly time,
without falsely treating observations received after a request began as future
relative to a backdated snapshot. Historical exclusions are advisory only when
the currently required indicators and prior-session evidence are valid.

For explicit Flash requests, the adapter disables default thinking mode for
bounded JSON classification, retaining that setting in request receipts. This
uses the [provider's documented parameter](https://api-docs.deepseek.com/guides/thinking_mode/).
Other explicit models keep their semantics. The synthetic probe stores no
stock forecast and never resets the production attempt.

`prepare_yahoo_auth.py` moves cookie/crumb bootstrap to near 09:40. Private
mode0600 data expires in at most 15 minutes and must match the ET session.
Every report quote is still fetched fresh and validated independently; missing
BBO timestamps cannot be repaired by authentication. The resolved report state
is passed explicitly, including canonical CLI use without RB_STATE_DIR.

The concise pure renderer now shows unpriced H1 candidates and an independent
sentiment watchlist from the complete prepared evidence. Neither requires
inventing a quantitative score for new names. That watchlist is unadopted,
fixed in PREREGISTER_day100_deepseek_reliability.md, and never forces two names
per side. Sources, rationale, model/mode/hash, uncertainty/MDE, exclusions and
shared exposures remain in the full attachment. N/A is not replaced by an
invented opinion. Failure stays UNAVAILABLE; evaluated abstention stays distinct.

## Deployment and verification

Final test totals and reviewed release/pins are recorded in the pull request.
Source changes alone do not install an always-on host or update existing job
pins. Both existing Gmail tasks must point to the reviewed release and retain
all publication/delivery/replacement history. No additional sender, new
automation, same-day replacement or brokerage capability is introduced.

Live input completeness for the next session and executable timestamped BBO
remain unverified until that session's checks. Neither broader coverage,
successful API use nor passing tests demonstrate an edge, higher hit rate,
profitable picks, guaranteed error-free delivery or an inbox-arrival SLA.
