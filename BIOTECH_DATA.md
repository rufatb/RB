# Biotech data contract

The daily monitor is factual event research, not a long/short recommendation.
It does not forecast approval, clinical success, a share-price target or an option
return. “Monitor” means a source-verified catalyst passes the stated expectations
screen. It does not establish that a security is undervalued.

## Universe and daily preparation

`build_biotech.py` paginates **all** provider US-region Biotechnology equities,
including OTC microcaps, with no market-cap prefilter. US means US-traded common
equities/ADRs, not a US-domicile restriction. Sector Healthcare is insufficient:
industry must be Biotechnology. Each record needs current USD market cap and
actual trailing daily share volume. Rank the whole verified population by ADV20,
then intersect ranks 1–100 with **market cap strictly below $500,000,000**.
A $500m company is excluded; there is no minimum market cap.

ADV20 uses exactly the last 20 completed exchange sessions. Today’s partial
volume is excluded. Daily history must have unique ordered dates, split-adjusted
positive prices and valid volume; the builder checks the exchange-session list.
Current snapshot and market-cap capture must be at most 36 hours old. Current
membership is suitable for today's scan, never a survivorship-free historical
universe. A partial fetch, duplicate symbol or missing metadata blocks the rank,
rather than silently promoting an incompletely ranked Top 2.

```bash
python build_biotech.py --output /var/lib/rb-report/biotech_snapshot.json
python discover_biotech_events.py --snapshot /var/lib/rb-report/biotech_snapshot.json --output /var/lib/rb-report/biotech_candidates.json
```

Set `RB_SEC_USER_AGENT` to the actual application name and contact email. The SEC
discovery client caps itself at five requests/second with finite timeouts and
records errors. It creates a **review queue** of SEC filing links, not catalyst
dates. Supplement with issuer investor-relations releases, FDA notices and
conference programs. A trial's administrative primary-completion date is not a
readout announcement. SEC recent-filings coverage alone is not a complete calendar.

## Reviewed events

Supply a JSON object with an `events` array. Every record requires:

| Field | Meaning |
|---|---|
| `event_id`, `ticker` | Stable event identity and exact universe symbol; reconcile revisions before import |
| `kind` | `topline`, `interim`, `conference`, `PDUFA`, `AdCom`, `CRL`, or `financing` |
| `status`, `review_status` | `scheduled`, `verified` after evidence review |
| `window_start`, `window_end` | ISO dates, ordered, within the next six calendar months |
| `announced_at`, `verified_at` | Aware ISO timestamps; no future evidence; reverify at least every seven days |
| `date_basis` | `issuer_guidance`, `FDA`, `conference_program`, or `financing_terms` |
| `source_type`, `source_url` | Issuer, SEC, FDA or conference primary evidence; HTTPS link, correct authority domain |
| `asset`, `indication`, `stage` | Specific asset/context; use factual financing context where appropriate |
| `new_information`, `known_data` | What remains to be learned versus already disclosed evidence |
| `read_throughs` | Objective implications over 3–6 months, including conditional outcomes and information limits |
| `crl_issued_on` | Required only for CRL follow-up; the letter must already be disclosed, never predicted |

Use source quotations/filing sections in review notes if helpful, keeping the
five final bullets concise. Do not silently shift issuer guidance into a precise
date. A delayed/past event is reverified or quarantined; a duplicate identity is
not resolved by whichever row happened to appear last.

```bash
python discover_biotech_events.py --import-reviewed /path/to/reviewed.json --output /var/lib/rb-report/biotech_events.json
```

The importer validates **all** records before atomic replacement. The checked-in
empty feed means no reviewed feed is available, not that no catalysts exist.

## Expectations screen (fixed mechanical thresholds)

These are design choices for an objective screen, not optimised alpha thresholds.

| One vote per category | Positive flag | Missing evidence |
|---|---|---|
| Event options | ATM IV midrank percentile >=80% among >=20 distinct issuers in the same <=30 /31–90 /91–190 DTE cohort | Unknown if quotes/cohort fail validation |
| Positioning | Short interest >=20% of float (<=35 days old), OR holding borrow APR >=20% (<=24h old) | False only when both are observed below threshold; either positive is one vote |
| Repricing with rising RV | Absolute 21-session return >=30% OR 63-session return >=60%, AND latest20/prior40 realised-volatility ratio >=1.5 | Unknown with inadequate valid daily history |

Two or more positive categories go to **Crowded / High-Expectations**, never the
Top 2. Unknown is not false: if positives plus unknowns could reach two, the
entry remains **Insufficient evidence**. Two observed false categories can safely
pass with the third unknown, which remains printed. No-options does not imply
cheap options or automatically exclude a nonoptionable microcap.

Rank eligible Monitor events deterministically by fewer positive flags, earlier
window end, higher ADV20 and ticker; retain at most one per issuer and at most
two issuers. Return fewer than two if evidence does not support two. Each Monitor
has exactly five bullets: Event & Date Window; Asset/Indication/Stage; New
Information vs. Known Data; 3–6 Month Read-throughs; Objective Expectation Indicators.

## Quote and options input

`RB_QUOTES_JSON` selects a timestamped external publisher's local snapshot.
Without it, the common Yahoo client is used, with the **same** validation gates.
No credential is embedded in this repository. Snapshot envelope:

```json
{
  "quotes": {"SYMBOL": {"symbol": "SYMBOL", "currency": "USD", "bid": 0,
    "ask": 0, "bidAskTimestamp": "aware ISO timestamp", "regularMarketPrice": 0,
    "regularMarketTime": "aware ISO timestamp"}},
  "chains": {"SYMBOL": {"initial": {"quote": {}, "expirationDates": []},
    "expiries": {"expiration epoch": {"options": []}}}}
}
```

The zeros are schema placeholders and **will fail validation**. Supply actual
positive, finite, uncrossed quotes. `quoteTime` is accepted as an alternative BBO
timestamp; `regularMarketTime` is never used as a substitute. Quotes expire after
120 seconds. Currency and identity must match. Call/put strike, expiry, currency,
positive open interest and BBO clocks must match and be valid; no lastPrice
fallback. Require expiration **after** the full event date window to cover an
after-close release. The call/put/underlying gap <=3% is a conservative consistency
screen, not an exact American-option parity model. Snapshot age uses the oldest
underlying/contract observation; refresh time cannot make a stale quote fresh.

Refresh options near publication, using the same feed:

```bash
python build_biotech.py --refresh-options --output /var/lib/rb-report/biotech_snapshot.json --events /var/lib/rb-report/biotech_events.json
```

Set `RB_BIOTECH_SNAPSHOT_JSON` and `RB_BIOTECH_EVENTS_JSON` to these persistent
paths for `brief.py`. The morning critical path consumes staged data; it does
not perform hundreds of requests inside a renderer.

Official source references: [yfinance screener API](https://ranaroussi.github.io/yfinance/reference/api/yfinance.screen.html),
[SEC data access](https://www.sec.gov/search-filings/edgar-search-assistance/accessing-edgar-data),
[FDA CRL transparency](https://open.fda.gov/apis/transparency/completeresponseletters/).
