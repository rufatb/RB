# Day101 — a broader TSX research universe, not an adopted predictor

Registered September 14, 2026 before implementation or outcome inspection.
The user approved the 150-name research expansion and 30–50-name DeepSeek
shortlist. Preserve the production TSX-21, K=60/M=20, selection, allocation,
six protected modules, every rejection, registration and historical report.
Day40 supersedes day14's claim of a compact-universe edge; its hourly result
does not certify the exact five-minute execution contract. Day34's rejected
trade-diversification rule is not revived by broader research coverage.

## Fixed coverage design

1. Build a dated security master from identified issuer/exchange or provider
   reference receipts. Exact TSX/CAD/security identity, active status, security
   type, issuer identity, sector and industry are separate required facts.
   Common shares and REIT units are eligible; preferreds, warrants, rights,
   ETFs, funds, TSXV listings and duplicate issuer share classes are excluded
   or kept in an explicitly separate directory. Do not infer missing industry.
   A current constituent list cannot certify historical membership.
2. Target at most 150 eligible research names. Screen with the median of
   daily close times volume over the immediately preceding 20 completed TSX
   sessions, at least CAD10m/day. This is a liquidity proxy, not measured
   exchange turnover or an edge threshold. Positive unadjusted OHLC/volume,
   exact interval, session grid and source identity are required. Rank by this
   proxy descending, ticker ascending for ties; never call a partial source
   enumeration a complete-market rank. No retrospective threshold search.
3. Cache previous-session five-minute history separately from baseline files.
   Prefer saved validated inputs, fetch missing history with bounded workers,
   checkpoint partial successes, and stop new requests after provider refusal
   or whole-wave outage. Never bridge missing sessions or use the legacy
   research extractor. A 150-name target is not 150 successful acquisitions.
4. Before news/model work, shortlist at most 50 eligible names with complete
   Python technicals. Traverse sectors alphabetically in repeated rounds;
   within each sector use the same liquidity/ticker ordering. This distributes
   research coverage, not trade weights. Fewer than30 is an explicit coverage
   gap, never a reason to pad names. No fixed long/short/industry trade quota.
5. News source success with no current linked articles is NO_CURRENT_NEWS;
   a failed/unauthenticated request is UNAVAILABLE. Neither is a fabricated
   neutral model result. Only complete validated evidence reaches DeepSeek;
   the saved pool and shortlist retain every exclusion and denominator.
   Existing DeepSeek model, parsing, sentiment threshold0.50 and day99 H1/H2
   remain unchanged. No cross-time fusion of pre-open and later diagnostics.
6. The report consumes local prepared coverage and factors, never performs
   directory discovery, historical backfills or LLM calls at09:46. Any optional
   expanded opening-context input must contain actual completed bars and exact
   timestamped quote evidence. Missing feeds mean UNAVAILABLE, not simulated
   current data. Sector-relative opening movement and time-of-day RVOL are
   descriptive shadow context, not a new adopted selection or win probability.

## Runtime and failure boundary

Source acquisition bounds fixed before the live expanded run: the official
TMX monthly file may prioritize up to500 discovery issuers by its reported
year-to-date traded value, explicitly not ADV20 or a complete-market liquidity
rank. Sector/industry reference facts may be at most62calendar days old to
accommodate monthly publication lag; active-listing verification must be dated
at or after the immediately preceding TSX session close and no later than
preparation. Daily liquidity must still end on that immediately preceding
session. Unspecified security class/industry remains missing even when a
provider says EQUITY. These are source freshness/coverage limits, not fitted
trading thresholds. A reviewed allowlisted master import preserves its raw
reference/history receipts and verifies the same contracts as automatic staging.

Directory/eligibility preparation has a separate 180-second budget; extended
five-minute pool preparation at most240seconds, eight workers and18seconds per
request. Existing bounded DeepSeek budgets remain unchanged. All production
preparation stops before09:30; no same-session retry after a stored attempt,
including failures. An optional explicit diagnostic uses actual current time
in fresh isolated state and can never replace a morning snapshot. A source
outage may retain a clearly labelled existing60-name research fallback while
the expanded universe remains UNAVAILABLE; it must preserve the baseline and
independent sections. No new sender, orders or automatic replacement emails.

September14 coverage-compatibility amendment, before any expanded model pass
or outcome inspection: a partial directory must not shrink the existing60-name
research roster into a small sector-specific subset. Activate expanded pool
staging only when its validated directory contains more than the existing
legacy roster (at least61 with today's60-name roster). Otherwise retain the
explicit legacy fallback while preserving partial directory facts/exclusions.
This boundary is derived from existing coverage, not fitted to returns; do not
pad strict candidates with unverified names or describe fallback as expanded.

## Evaluation protocol

The expanded arm is a new unadopted challenger alongside the unchanged baseline
and existing H1/H2/watchlist arms, counted in multiplicity rather than replacing
an unsuccessful arm. Collect dated membership, receipts, inclusions, exclusions,
model/config hashes, all zero-selection days and exact entry/exit observations.
Do not backfill point-in-time membership, news or LLM decisions after outcomes.

Minimum120 complete forward sessions:60 development then60 untouched
confirmation, plus the existing four-quarter/two-market robustness requirement
before production adoption. Evaluate on the same union of exchange sessions,
abstentions as cash; missing execution prices/costs remain missing, not zero.
Primary endpoint is paired session net-return difference after actual entry
and exit spread, slippage and relevant short financing/availability evidence.
Report gross proxy results separately, turnover, participation, hit rate,
drawdown, sector/common exposure, missingness and placebo/positive-control
diagnostics. Use five-session block bootstrap,2,000 draws, seed101 and
MDE80=(3.5+0.8416212336)*SE. Never treat securities within a session as independent
samples. Insufficient matched history gives UNDERPOWERED/UNAVAILABLE with no
numerical alpha claim. Forward predictive efficacy is unestablished at release.

Schema, source parsing, failure isolation, unchanged-baseline parity and
preparation-to-rendering tests are engineering validation. They cannot certify
feed availability or improved accuracy. No rule is selected by today's returns.

## Day-134 amendment: the 150 names, sourced so the rule can actually run (owner, 2026-10-14)

The owner said "go ahead with the 150". Registered before any expanded pool
was built or any outcome read. The screen, the rank, the 150 target, the
C$10M floor, the bounds and the evaluation protocol above are unchanged; only
sources, evidence and wiring change.

**Why the automatic route never produced a universe.** Measured once tonight in
an isolated diagnostic (22:40 ET, engineering only):
* every TMX source answered: 2,294 issuers (metadata 2026-09-30), both status
  feeds current, 27 of 27 directory queries;
* 450 of the 500 discovery issuers failed the explicit-type test, because the
  directory names an instrument by its issuer ("Royal Bank of Canada") and
  never says "common": RY, TD, ENB, CNQ, SU, BMO and the rest;
* 33 failed the join: the directory files a class-share issuer under its first
  class (BBD.A, TECK.A, RCI.A, GIB.A, CCL.A, QBR.A), not its root, and an
  accent (AtkinsRéalis) broke the name match;
* 2 REITs survived. No morning ever staged it, and every morning logged the
  legacy fallback.

**Changes.**
1. **Common shares by convergent evidence.** An instrument is COMMON_STOCK
   (rule `TMX_OPERATING_ISSUER+FMP_EQUITY`) when ALL hold:
   * the TMX issuer is eligible as before (not ETP, CDR, closed-end fund,
     SPAC or a structured product);
   * the instrument is a current exact TMX directory instrument of that
     issuer, at its root symbol or its root plus one class letter (BBD.B), and
     never .PR/.PF/.DB/.WT/.RT/.U, nor .UN outside the REIT rule;
   * FMP's TSX company screener (a paid provider receipt, one call) lists that
     exact ticker as not an ETF, not a fund, and actively trading.

   An instrument named explicitly as common keeps the old rule; REIT units keep
   the old rule. Income-trust and partnership units (BIP.UN, BEP.UN) stay
   excluded: they are neither common shares nor REIT units. Duplicate classes
   are still cut to one per issuer by liquidity.
2. **The join.** The directory row is found at the root, or at the root plus a
   class letter; names match after accents and punctuation are folded.
3. **Industry.** TMX's when present; else FMP's screener industry and sector
   for that ticker, dated by the receipt. Never inferred from a name.
4. **Liquidity receipts from FMP daily bars** (historical-price-eod), with a
   credential-free URL in the receipt. Same rule: exactly the immediately
   preceding 20 completed sessions, positive OHLC and volume, median
   close × volume ≥ C$10M. The Yahoo receipt path stays valid.
5. **Staging.** `morning_full.sh` runs `prepare_tsx_universe.py` before the
   factor pool, once per session, within the 180 s budget. A failure, or a
   list no larger than the legacy roster, keeps the legacy roster, labelled.
6. **Who reads it.** The desks read every name in the pool that carries their
   fields (`usable_candidates`, unchanged). The factor layer keeps its 30–50
   shortlist, counted over the TSX research rows only: the US biotech rows
   added to the same file on day-111b are not part of the 150.
7. **Sector map.** New names get their sector and industry from the same FMP
   receipt, so sector context, exposure lines and review peers cover them.

**Not claimed.** No accuracy gain: the population changes. Day-117 found no
input field carries signal in this pool; more names are more choices, not
more signal. A dry run tonight is engineering validation only.
