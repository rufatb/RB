# Day98: EODHD free-tier live entitlement check (external runtime)

AUDIT, not adoption. Performed 2026-09-10 ~09:05-09:25 ET from an external
runtime with outbound EODHD access, closing the gap AUDIT_day97 recorded:
"Outbound EODHD access in this interactive runtime was blocked before a
provider entitlement response." The credential is not reproduced here.

## Verified facts (endpoint responses, not documentation)

| Endpoint family | Request | Result |
|---|---|---|
| EOD daily (`/api/eod/{T}.TO`) | TRP, ENB, BCE, SLF, TD, RY, CNQ, SU, MFC, XIU | HTTP 200, all ten. Exactly 251 sessions, 2025-09-10 to 2026-09-09. `adjusted_close` present. |
| Intraday 5m (`/api/intraday/{T}.TO`) | TRP.TO | HTTP denial, body: "Only EOD data allowed for free users." |
| Exchange catalogue (`/api/exchange-symbol-list/TO`) | TO | HTTP 200, 3,026 symbols. |

## Consequences

1. The free plan's published contract (20 calls/day, 1y EOD, symbol lists,
   no intraday) is now a MEASURED entitlement, not an expectation.
2. The day97 opening-path study's binding constraint is unchanged: it needs
   >=200 clean 5-minute sessions. Free EODHD cannot supply them. The cheapest
   qualifying feed remains the ~7-month 5-minute history identified in
   DATA_CEILING.md (EOD+Intraday plan or equivalent).
3. EODHD free EOD is a valid SECOND SOURCE for the daily reference closes
   already probed by `prepare_eodhd.py`; it adds no alpha-bearing field that
   the existing free daily path lacks (see LAB_day98_kimi.md, section 2 -
   daily-context features were screened and rejected on point-in-time data).
4. The 20-credit/day budget makes full-universe daily refresh + catalogue
   polling tight but feasible if batched and cached; it is NOT feasible for
   per-session multi-symbol intraday work even if upgraded one tier without
   checking that tier's credit math.

No production, selection, or publication path changes follow from
this audit. `quotes.py` remains the only live validation path.
