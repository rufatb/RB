# Day101 — broader research coverage with explicit data denominators

September14,2026. User-authorized implementation; preregistered before source
staging or outcome evaluation in `PREREGISTER_day101_tsx_expansion.md`.

## What changes

* `tsx_universe.py` and `prepare_tsx_universe.py` add a dated TSX/CAD security
  directory, identity/type/industry validation, raw receipts and the exact
  prior20-session CAD10m median daily close-times-volume liquidity screen.
  Target150 is a capacity, not a claim that150 securities were verified.
* `prepare_factor_pool.py` consumes valid directory candidates, retaining
  separate baseline and research history files and all missing-data rows.
  Directory failure or a validated subset no larger than the existing60-name
  roster keeps that explicit fallback; partial coverage cannot shrink the
  research pool into a small REIT-only subset.
* `research_shortlist.py` fixes a maximum50-name pre-news shortlist by sector
  rounds and liquidity order. News failures do not trigger replacement names.
  DeepSeek only receives complete validated public inputs for that roster.
* `research_coverage.py`, preflight and the existing single-Digest renderers
  show directory, technical, shortlist, submitted and assessed denominators,
  sector/industry coverage, and exclusions. Preparation validates actual cache
  contents; the report checks local receipts without new acquisition.
* `research_opening.py` supports optional local, descriptive opening-range,
  VWAP-proxy, time-of-day RVOL and sector-relative context. It does not fetch
  live bars, turn daily prices into quotes, or change any selected position.
* `research_evaluation.py` defines the forward matched-session net-cost study.
  Missing observations remain missing; abstentions are cash. It never adopts
  a strategy or rewrites historical outcomes.

The six protected modules, production TSX-21, K=60/M=20, features, selection,
allocation, existing DeepSeek model/prompt and0.50 research threshold remain
unchanged. Industry research coverage is not a trade-diversification quota.
No claim of a compact-universe edge survives merely because the baseline was
retained: STRATEGY day40 superseded the earlier day14 interpretation. Preserve
both experiments and the rejected day34 diversification result.

## Source observations and limits

The official TMX directory and [monthly issuer workbook](https://www.tsx.com/en/resource/571)
were read on September14. The workbook's internal date is July31,2026; its
later publication date is not the date of the underlying facts. The observed
file contains2,264 TSX issuers, including ineligible instruments, and leaves
the main industry/subsector field blank for most rows. Explicit specialty
classification columns may supply a real fact; the issuer name cannot supply
an invented industry or share class. YTD traded value is discovery priority,
not completed20-session liquidity. The current directory must establish exact
active instruments separately from an issuer root symbol.

The reviewed-master route is a controlled import, not independent verification
of an assertion. Its preparer must retain the actual primary/provider evidence;
setting `reviewed:true` does not establish source accuracy. Hashes establish
receipt integrity and chronology within this workflow, not authenticity by
themselves. A current directory cannot backfill historical membership.

Unauthenticated Yahoo company-profile probes for RY.TO and REI-UN.TO returned
HTTP401 on September14. A subsequent proper authentication check succeeded
in16.825 seconds, and one RY.TO profile request succeeded in6.2 seconds at
13:47:38 ET. It returned Financial Services / Banks - Diversified with exact
RY.TO/TOR identity. Its EQUITY flag still does not establish common-share type.
Thus industry access was demonstrated for one authenticated sample; broad
coverage and exact security types remain unverified. No unavailable reference
was fabricated to fill150 slots. Connected Massive US data does not provide
Canadian listing/quote certification for this expansion.

The actual bounded directory diagnostic at13:43:14–13:43:43 ET on September14
used revision45b9ed897ef0c591e90a11daa70c6fa690c89d24. All27 directory queries
completed; the source sample contained500 discovery issuers. That revision
recorded711 instrument exclusions for missing security type/industry and31
unmatched issuer roots. Review of the raw receipts exposed a join defect:
monthly REIT roots such as REI omit the .UN suffix present in the current
directory. The final code fixes that exact unit mapping and tests the observed
source shape. The earlier zero count is not proof all31 roots lack source data.
The same-source offline replay after that fix identifies19 REIT unit metadata
records. None is certified active/liquid without the missing status-feed and
20-session price receipts. It also fixes a blanket Income Trust exclusion that
would have incorrectly removed eligible REITs. No new network/model requests
or changes to the original diagnostic snapshot were made for this replay.
No daily liquidity requests or model requests were made. This is UNAVAILABLE
coverage, not a successful scan finding zero market opportunities. The final
release additionally checks current suspended/delisted lists; those later fixes
were unit-tested, not established by this earlier live diagnostic. No retry was
made merely to obtain a better coverage result.

[TMX's current Security Master](https://www.tmxwebstore.com/products/tsx-security-master-daily)
documents a suitable detailed reference source, including security type and
nature of business. Its public sample is historical and was not loaded as
current membership. Current subscription/export access remains unestablished.
This release supplies a reviewed import route; it does not purchase a feed.

No new historical or live prediction results were evaluated in this release.
The prior current-time11-assessment integration diagnostic remains separate
from the September14 morning snapshot. Tests using simulated provider responses
validate engineering contracts, not real feed coverage or financial efficacy.

## Operational release checks

The initial full suite passed2,068 tests; final source/shortlist/coverage
follow-up tests passed89. The reviewed release's GitHub CI supplies the final
whole-suite gate after remaining integration checks. Retain the bounded source
diagnostic, reviewed main revision and both existing job pins in the release
record. Preserve the existing report
database, daily delivery/replacement history and all earlier private receipts.
Do not send another email solely because this research release was deployed.
