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
