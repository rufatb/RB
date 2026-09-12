# DeepSeek factor evidence — day99

The canonical daily command remains `TZ=America/Toronto python brief.py`.
`brief.build()` returns one Digest; text, HTML and concise email consume it.
DeepSeek is a separately staged, unadopted factor experiment. It cannot place
orders, recompute indicators, overwrite selections, supply a win probability
or rewrite published results. See `PREREGISTER_day99_deepseek.md`.

## Configuration and live verification

Install `requirements.txt` in the report checkout's own virtual environment.
`openai` is the compatible SDK. `httpx[socks]` supports the configured headless
host proxy; its absence was found and repaired during the live check.

The adapter reads `DEEPSEEK_API_KEY` from the environment. Pre-open preparation
may populate it from private `RB_STATE_DIR/secrets/deepseek_api_key`, mode 0600.
There is no committed development credential or runtime literal fallback.
`DEEPSEEK_MODEL` overrides the private `deepseek_model.txt`; the code default is
`deepseek-chat`. There is no automatic model fallback.

On 2026-09-12, the authenticated `/models` response listed `deepseek-flash` and
`deepseek-v4-pro`, not `deepseek-chat`. The operational model is explicitly
configured as `deepseek-flash`. A live, clearly labelled synthetic schema probe
returned validated NO_EDGE / 0.0. This verifies credentials, model access and
JSON handling only: it is no evidence of market-data coverage or accuracy.
Provider model changes require a documented setting change and new receipt.
Official references: [JSON mode](https://api-docs.deepseek.com/guides/json_mode/),
[model list](https://api-docs.deepseek.com/api/list-models/).

## Preparation contract

After restoring the CURRENT operational archive and staging the unchanged
baseline's history, run before 09:30 ET:

```bash
python prepare_deepseek.py --state-dir "$RB_STATE_DIR" --refresh-public-inputs
python preflight.py --state-dir "$RB_STATE_DIR" --output "$RB_STATE_DIR/preflight.json"
```

The optional public refresh uses one bounded 25-second pass for dated WTI,
CAD/USD, TSX and VIX references and exact-ticker-linked headlines. It stops
subsequent news batches after a provider failure. Missing structured SEC tags
are explicit; headlines are not invented 8-K filings. Prior successful inputs
are retained and revalidated, never relabelled fresh. Endpoint access is
independent of DeepSeek access.

A supplied `deepseek_candidates.json` can contain up to 500 validated names.
Without it, Python builds candidates from the actual configured TSX universe
and file-validated history. No padding, inferred membership, or 500-name claim.
`factor_inputs.validate_payload` defines the exact input contract. Candidates
need timestamped Python technicals with computation/input-hash provenance,
linked headlines/catalyst tags and aware evidence timestamps. Metadata declaring
an upstream Python calculation is not proof of an independently verified one.
Local-cache technicals are calculated here. Prior-session VWAP/ORB are labelled
prior-session; they are not the current morning's opening range.

`deepseek_news.json` maps ticker to headlines and catalyst tags; each evidence
item carries source_url and published_at. `deepseek_macro.json` maps wti,
cadusd, tsx and vix to dated values and source URLs. Missing fields stay missing.
The model sees only allowlisted public fields, never keys, private ledgers,
account identities, holdings or order sizes. News text is untrusted data.

Preparation is bounded to 120 seconds, batches of at most 25, 12 seconds per
request, no SDK retries. This is a deadline, not a promise that 500 names fit.
The session attempt is recorded before requests. Completed attempts, failures
and interrupted/ambiguous attempts cannot silently be rerun the same day.
Inputs, hashes, model metadata, diagnostics and original response assessments
are retained in `deepseek_history/YYYY-MM-DD` and `deepseek_snapshot.json`.
All files must be packed into the same operational archive, preserving SQLite
publication, delivery and replacement state. No LLM response belongs in old
historical rows or a retrospectively reconstructed sentiment backtest.

## Daily computation and reporting

`brief` reads only the local snapshot. It validates timestamps/session/input
hash, candidate linkage and strict model fields. One unavailable optional
section cannot erase successful baseline/holdings/calendar sections.
A saved old publication is returned before any data or model acquisition.

The 09:46 quantitative pool comes from the one existing `r945.run` pass.
`scan.deepseek_shadow` combines that score with staged sentiment, always through
`dashboard.clamp_probability` in [0.35,0.65]. These are uncalibrated design
scores. H1 applies the registered agreement/threshold gate. H2 orders eligible
names by validated exact-09:46 entry spread. Each arm may have zero names;
it never forces two on either side and never replaces baseline allocation.
Unpriced or incomplete data means UNAVAILABLE, not an evaluated no-opportunity
claim. An evaluated threshold failure is NO EDGE - WAIT.

Concise email contains coverage and clearly labelled shadow context. The full
attachment retains source links, per-name reasons and uncertainty/MDE limits.
A strict BBO requirement is intentional: prior daily closes, un-timestamped
BBO and CORROBORATED trade bars do not become executable 09:46 quotes.
No prediction gain has been measured. The fixed forward study and untouched
confirmation are required before considering any adoption.

## Private overlay recovery

`import_deepseek_inputs.py --archive /path/RB-DeepSeek-private-inputs.zip
--state-dir "$RB_STATE_DIR"` imports only the allowlisted credential, explicit
model setting and capability/schema-probe receipts after the canonical state
has been restored. It requires existing valid reports.sqlite3 and never
initializes a replacement database. Different credentials/settings or receipt
conflicts remain visible; newer receipts are retained. Do not print secrets or
put them in GitHub, email, task prompts or authenticated URLs.
