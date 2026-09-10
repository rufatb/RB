# EODHD: qualification first, historical research only

This is an optional provider; `r945` still uses the unchanged configured source,
selection, training window and allocation. `quotes.py` remains the only live
equity/options validation path. Daily or delayed EODHD data must not be inserted
there as a live BBO or treated as an exact 09:46 execution price.

## Private configuration

Set `RB_EODHD_API_KEY` in the host secret environment, or point
`RB_EODHD_API_KEY_FILE` at a mode-0600 file. The default file location, when
`RB_STATE_DIR` is set, is `$RB_STATE_DIR/secrets/eodhd_api_key`. Never commit
the key, account profile, raw authenticated request URL or private runtime state.
Do not put a key in scheduled task text or public CI output. The report only
reads a small sanitized prepared status object and never loads credentials.

A separately supplied private input overlay can be imported using
`python import_eodhd_inputs.py --archive /private/input.zip --state-dir "$RB_STATE_DIR"`.
This requires an already restored publication database, rejects all files outside
the three explicit EODHD input paths, retains newer diagnostics and refuses to
overwrite a different existing key. Persist the resulting operational archive
with its version guard. The overlay can never bootstrap an empty report history.

Before the market opens:

```bash
python prepare_eodhd.py --state-dir "$RB_STATE_DIR"
```

The probe checks the account limit, exact Canadian exchange identities, one
prior-session TRP.TO five-minute sample, and dated daily references for TRP.TO,
ENB.TO, BCE.TO, SLF.TO and XIU.TO. These five symbols are a capability sample,
not today's selection. It does not certify the full 21-name intraday universe.
The budget is at most 15 API credits and eight requests, with a 40-second
acquisition deadline and five-second request timeouts. No retries are automatic.
One attempted session is reused, even if it failed; `--retry` requires an
operator to resolve the blocker first. Purchased extra credits are not used.

An intraday HTTP 403 does not erase independently accessible daily references.
A transport failure is NOT an entitlement result. Authentication failures and
rate limits open the global circuit; intraday denial opens only that endpoint
family. Provider response bodies and account names/emails are not persisted.
On failure, retain `eodhd_reference_closes.json` from the prior successful run,
but freshness checks must reject it as a current reference on a later session.
`eodhd_status.json` and dated diagnostics preserve the unsuccessful attempt.

The free plan's published contract is 20 API calls/day and one year of EOD
history plus exchange symbol lists. Intraday normally requires the EOD+Intraday
plan; the actual endpoint response, not that expectation, determines access.
No subscription or upgrade is performed by these scripts.

## Research

```bash
python study_opening_path.py --cache-dir "$RB_INTRADAY_CACHE_DIR" --output "$RB_STATE_DIR/diagnostics/day97-opening-path.json"
```

This reads the existing same-session prepared Yahoo cache without changing it.
The EODHD parser is available for a future separately staged longer panel;
the current research CLI does not silently substitute providers or accept an
EODHD panel under a Yahoo cache manifest. Verify full native symbol/session
coverage before extending acquisition. Published US demo examples do not prove
TSX coverage. Point-in-time membership, timestamps, splits and volume coverage
need their own review; OHLCV alone cannot reproduce spread or borrow costs.

Day97 requires 120 training sessions plus 60 OOS sessions after 20-session
volume warm-up. 145 raw sessions leave about five OOS sessions, not a powered
test. Missing-data exclusions can increase the requirement. AUC MDE is not a
net-return MDE. No study result changes production automatically.

## Official sources checked September 10, 2026

- https://eodhd.com/financial-apis/quick-start-with-our-financial-data-apis
- https://eodhd.com/financial-apis/intraday-historical-data-api
- https://eodhd.com/financial-apis/user-api
- https://eodhd.com/financial-apis/our-data-sources-and-data-partners
- https://eodhd.com/financial-apis/commercial-vs-personal-license-use

These document API semantics, not a live entitlement test of this deployment.

## Free-tier entitlement, measured 2026-09-10

Probed with a live free key, 8 requests. `dailyRateLimit` is **20 requests/day**,
which is itself a binding constraint on any research use.

| capability | free tier | what it would have fixed |
|---|---|---|
| EOD daily OHLC + adjusted close | **YES** | redundancy against Yahoo — reliability, not accuracy |
| Delisted symbol roster (896 TSX commons) | **YES** | names only; see below |
| Delisted price history | **NO** — 0 rows | the actual survivorship fix |
| 5-minute intraday | **NO** — HTTP 403 | day-93's `vp` blocker (needs ~145 sessions) |
| Bid / ask (BBO) | **NO** — field absent | the four ABSTAINs on 2026-09-10 |

**It does not improve the picks, and it was not wired into the daily path.**
The two constraints that actually bind are sub-hourly history depth and a
timestamped BBO, and the free tier addresses neither. `real-time/` returns
OHLCV + `previousClose` with a *trade* timestamp and **no bid/ask at all** —
the same shape as Yahoo, and the same reason `validate_equity` fails closed.

What it did buy is one measurement: 50.6% of TSX common stocks in this
provider's roster are already delisted. See `DATA_CEILING.md`.

**Before paying, verify these two by trial, not by pricing page:**
1. does the paid tier return **price history for delisted names** (not just the
   roster — tested twice, 0 rows on free); and
2. does it return a **bid/ask with its own quote timestamp**, not a last-trade
   timestamp. The BBO gate needs the quote's time, not the print's.

Neither is answerable from the free tier, and both are the whole reason to buy.
