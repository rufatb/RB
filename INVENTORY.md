# INVENTORY.md — every file, what it is, and whether it is load-bearing

Generated day-64 (the day the repo got its first full map). Line counts are from
the day-64 snapshot and drift; treat them as size classes, not facts. If a file
here changes PURPOSE, update this file in the same commit.

## The daily path (load-bearing at 09:46)

| file | lines | role |
|---|---:|---|
| `brief.py` | 387 | the entry point. acquire → compute → publish-once → render. Exits 7 (day-95b) when an eligible session recorded nothing. |
| `r945.py` | 1559 | the 9:45→close engine: pooled k-NN, density tag, peer gate, pair selection, sizing, publish path |
| `execution.py` | 196 | clock/calendar gates (fail-closed), the publication window (day-95b: 09:46:00–09:49:59 ET, late records labelled), leg integrity evaluation, exact-window scoring |
| `daily_job.py` | 107 | cron wrapper: freeze, render, write artifacts, exit 7 on the unrecorded-day class |
| `morning.sh` | 207 | unattended run: pull → provenance → report → push. Exit codes documented in its header (7 = day-95b unrecorded-day alarm) |
| `daily_render.py` | 291 | pure text/HTML renderers over the frozen report (incl. day-95b RECORD-gap section) |
| `deliver_report.py` | 120 | send the frozen report; claim/finish delivery; NOT RECORDED alarm path sends unfrozen |
| `report_store.py` | ~200 | the immutable session-keyed Store; publish-once lives here |
| `ledger.py` | 721 | the append-only track record: picks, universe prints, scoring, accuracy lines, record-gap detection |
| `quotes.py` | ~250 | quote validation, staleness, timestamps |
| `adapters.py` | ~300 | market data adapters (Yahoo direct etc.) |
| `dashboard.py` | ~300 | config loading, trading-day calendar, shared helpers |
| `config.yaml` | — | universe, sizing, thresholds. Changing it changes the bet; changes are commits. |

## Research harnesses (shadow only; never read by the daily path)

| file | lines | role |
|---|---:|---|
| `validate_residual.py` | 430 | day-95b H2: tide-residualized features, registered harness (BLOCKED in sandbox; runs on host) |
| `shadow_vp.py` | 131 | day-95b H1 SHADOW: vp train/serve normalization A/B, divergence logger only |
| `validate_ceiling.py` / `validate_exit.py` / `validate_deep.py` / `validate_twins.py` / `validate_density.py` / `validate_crossmarket.py` | — | the registered study harnesses; each is named in STRATEGY.md with its verdict |
| `build_pool.py` / `bar_cache.py` | — | research data acquisition/caching |
| `provenance.py` | — | day-95: is this clone the whole of main? |
| `risk_evidence.py` | — | clustered hit-rate intervals, day-shape counts for the report |
| `build_social.py` | — | day-94 Arm A forward attention collector (09:20 ET; never run from morning.sh) |

## Data

See `data/README.md`. The record files (`ledger.csv`, `universe_prints.csv`,
`positions.csv`, `data/advice.csv`) are pushed by the morning run and pulled
before it. Research artifacts under `data/` are committed on purpose (container
recycles destroy scratch).

## Tests

`tests/` mirrors the above one-to-one where possible. `tests/test_day95.py` is
the day-95b record-integrity suite (window boundaries, unrecorded-day class,
record gaps, r945 robustness, shadow A/B, H2 fixtures). `tests/test_morning.py`
pins the wrapper's contract including both exit-6 (provenance) and exit-7
(unrecorded-day) semantics.
