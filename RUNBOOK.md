# Run and deliver the daily report

`brief.py` is the sole daily computation layer. Preview and publication are
explicitly different commands. Read `CLAUDE.md` and the latest `STRATEGY.md`
addendum first. No command submits a brokerage order.

## Local verification

```bash
python -m pip install -r requirements.txt
python -m pytest -q
python brief.py --offline --format json --output /tmp/rb-preview.json
python brief.py --offline --format html --output /tmp/rb-preview.html
python validate_execution.py --as-of 2026-09-08 --output /tmp/day90-check.json
```

Offline computation does not write ledgers, publish, score or fetch. Live preview
fetches with independent section deadlines, but does not publish or score.
Explicit `--output` writes only the requested artifact. The old `build()` API
is a preview facade. Legacy CLI reports remain available separately, but they
are not the daily two-engine report. Do not concurrently schedule legacy
`r945.py --book` or `report.py` as a second daily publication.

## Morning lifecycle

Before the report window, verify the exact interpreter and checkout:
`/absolute/checkout/.venv/bin/python /absolute/checkout/runtime_check.py`.
Create/install that checkout's environment early if the interpreter is missing
or fails imports. Use the verified absolute interpreter and run commands with
the checkout as working directory throughout; a venv copied from another
temporary directory can contain broken symlinks. `brief.compute()` resolves
its default configuration relative to its own source file.

With a prepared intraday cache, each Yahoo host attempt has a two-second
socket timeout instead of twenty seconds. The independent 22-second process
deadline still bounds fetch, feature construction and calibration together;
socket timeouts do not establish a delivery SLA. Fixed stage/ticker/count
diagnostics survive termination without exposing provider URLs or credentials.
If current bars cannot be acquired, cached history is not today's signal.

An explicit recipient request can authorize a separate informational
replacement through `replacement_report.Replacements`. It preserves the
original report/delivery and records a new immutable body and atomic claim.
Save that claim durably before Gmail; record its actual returned message ID
after success. Unknown outcomes require Sent reconciliation. Scheduled jobs
must never invoke this exception automatically or reset an original claim.

| ET clock | Action | Failure handling |
|---|---|---|
| 08:10 | Stage complete biotech universe; review primary-source event evidence and warm intraday history | Partial coverage blocks only its dependent section |
| 09:20 | `rb-social.timer`: day-94 shadow attention snapshot into `data/social/` (`build_social.py`; feeds nothing in the report). **PRE-OPEN BY DESIGN** — a snapshot after 09:46 holds the market's reaction to the open and is marked `decision_usable: false`; never move this into `morning.sh` | Failed fetches are recorded per name in the snapshot, never counted as zero attention. A missing snapshot is a permanently missing session — forward collection has no history endpoint, and `morning.sh` says so at 09:46 |
| 09:39 | `provenance.py`: is main everything, and is this checkout main? | WARNS, never blocks — a day's record outweighs a tidy branch list. `morning.sh` exits 6: published, but not on the whole of main |
| 09:40 | Prepare report environment and source review; inspect stored state and any delivery status | Signal is not final yet; never publish a hindsight-labelled 09:46 entry |
| 09:45 | Refresh verified options snapshots | Stale or missing expectations remain unknown |
| 09:46 | `daily_job.py --send` computes once, freezes, renders and sends | Intraday acquisition capped at 22s; equity acquisition at 10s, concurrently; completed siblings survive |
| 15:30,15:45,15:59 | `collect_execution.py --exit HH:MM` captures prospective exit/index quotes | Wrong minute, missing quote or unspecified execution costs remain incomplete |

The 09:45 completed five-minute bar only becomes available after it closes.
Therefore a 09:40 report cannot honestly contain final 09:46 entries. The design
prepares early and publishes during 09:46. Later completions are informational,
with no executable entry claim. Holidays and short sessions cannot satisfy the
09:46–15:59 intraday contract; biotech is evaluated independently.

## Always-on Linux deployment

The supplied systemd units are a concrete deployment configuration, **not an
assertion that a host is installed**. Use one designated writer with reliable
network/clock synchronisation, persistent disk and an operator receiving service
failure alerts. Install the reviewed code into `/opt/RB`, create its `.venv`,
create service account `rb-report`, and grant that account ownership of its
runtime/cache directories plus the legacy ledger/print files. No credentials
belong in git. Review the deployment branch before promoting it to your host.

Copy `deploy/rb-report.env.example` to `/etc/rb-report.env`, mode 0600, readable by
the service account. Configure verified sender/recipient, SMTP application
credential and the timestamped data publisher. Gmail app authentication in
ChatGPT is distinct from an SMTP application credential; this code does not
extract or reuse connector tokens.

```bash
sudo cp deploy/*.service deploy/*.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now rb-biotech.timer rb-options.timer rb-report.timer
sudo systemctl enable --now rb-exit@15:30.timer rb-exit@15:45.timer rb-exit@15:59.timer
systemctl list-timers 'rb-*'
journalctl -u rb-report.service
```

Before enabling, verify installation paths and file permissions. Systemd uses
`America/New_York` explicitly (DST aware), one-second timer accuracy and no
random delay. `Persistent=false` avoids presenting a missed morning run as a
new on-time report after reboot. Capture/report steps use exchange calendars.
Snapshot output and state belong in `/var/lib/rb-report`; they must survive
restarts. Back up `reports.sqlite3` using SQLite's online backup API, plus the
legacy CSVs and reviewed event feed. Do not copy a live SQLite WAL database as a
single ordinary file and assume that is a complete backup.

The SEC discovery queue is an optional review aid, not automatic promotion of
filing dates. A recurring researcher must review issuer guidance, FDA notices,
conference programs and financing disclosures before importing events. See
`BIOTECH_DATA.md` for schema and objective thresholds.

## Recovery contract (September 8)

Do not call an unevaluated scan a zero-opportunity result. Already published
baseline legs and the full recorded board must remain visible during outages,
labelled recorded, never re-entered or re-sized. These are hypothetical baseline
selections, not confirmed holdings. The holdings ledger is independently shown
with shares, entry, holding age and overdue-event reconciliation warnings.
Validated prior-session closes may be displayed as dated reference P&L, never
inserted into live marks, execution quotes or aggregate live book P&L.

Before the open, restore persistent operational state and run:

```bash
python sync_runtime.py --state-dir "$RB_STATE_DIR"
python sync_runtime.py --state-dir "$RB_STATE_DIR" --source-ref origin/main
python bar_cache.py --directory "$RB_STATE_DIR/intraday_cache"
python preflight.py --state-dir "$RB_STATE_DIR" --output "$RB_STATE_DIR/preflight.json"
```

Fetch the source ref first. `sync_runtime` only imports append-only CSV records;
conflicting published values stop the import. It does not merge code or change
strategies. Persist runtime_deltas.json alongside the database and staged inputs.
Preserve new locally published rows by exporting deltas before discarding a
temporary checkout. Use one operational-state writer with version-guarded saves.

Set `RB_INTRADAY_CACHE_DIR` to the cache directory: pre-open 60-day five-minute
history is combined with today's fresh five-minute bars using the same selection
logic. Wrong-session/source or incomplete caches fail closed. Never run cache
preparation after 09:30 and present it as pre-open evidence. No paid feed is
declared usable until its exact endpoint and required market/timestamps pass.

Set `RB_REFERENCE_CLOSES_JSON` to reviewed reference_closes.json. Each record
requires ticker, currency, the immediately preceding exchange session, positive
close, aware retrieved_at, and HTTPS source_url. Massive daily bars worked in the
September 8 probe; tested NBBO and stock snapshot endpoints were NOT_ENTITLED.
That does not establish unavailability of every Massive endpoint. US reference
data does not solve the TSX intraday feed requirement.

The daily report also carries an explicitly unranked source-reviewed calendar,
reviewed daily and used for Monday week-ahead planning. It remains visible when
strict universe/crowding certification fails; it never substitutes for Monitor
or silently relaxes the $500m/top100/2-of-3 contract. Fewer than two eligible
Monitor names is legitimate; failing to perform the research is a coverage gap.

## Delivery and duplicate handling

`daily_job.py` produces `report.json`, `report.txt` and `report.html` from one
frozen model. `deliver_report.py` sends text/HTML alternatives with a stable
Message-ID. `reports.sqlite3` has one session record including zero-pick days.
A second run retrieves it before calling providers. An atomic delivery claim
prevents duplicate concurrent sends.

A network interruption after SMTP accepts DATA can leave delivery ambiguous.
Such attempts are marked `UNKNOWN`; **do not blindly resend**. Reconcile the
Message-ID in provider Sent mail or SMTP logs, then have the operator record the
resolution. The code favours avoiding duplicate tactical reports over claiming
exactly-once delivery from an SMTP protocol that cannot guarantee it. Failed
credentials before a send claim may be corrected and retried. A late message
labels itself informational; inbox arrival cannot be guaranteed by a timer.

For a reviewable MIME file without sending:

```bash
python deliver_report.py --session YYYY-MM-DD --state-dir /var/lib/rb-report --eml /tmp/rb-review.eml
```

For the designated Gmail connector sender, after the delivery claim has been
durably saved, re-render timing from the frozen publication immediately before
transmission:

```bash
python prepare_delivery.py --state-dir "$RB_STATE_DIR" --session YYYY-MM-DD --output-dir "$RB_STATE_DIR/dispatch"
```

Use `gmail_payload.json`'s exact `subject`, `text`, and `html` in one multipart
message. If the minute changes before calling Gmail, run this command again;
it only annotates delivery time and renders, never reselects or overwrites the
publication. It rejects delivery before 09:46. Do not claim a publication-time
ON_TIME label establishes an on-time transmission. Dispatch is best effort.

The September 9 jobs still pinned September 8 code even after main was fixed.
After an authorized reviewed merge, update BOTH existing job pins to the same
main SHA and their data-only source ref to origin/main. Do not create additional
daily senders or copy private operational state into git. A failed state download
is an operational blocker, never authorization to start with a blank database.

Set sender/recipient environment variables even for MIME rendering. The
ChatGPT Gmail task can send the same rendered artifacts using the Gmail plugin;
it must check Sent for the exact daily subject and preserve durable publication
state before sending. Never run SMTP and Gmail delivery simultaneously as two
independent senders. Keep one designated sender per session.

GitHub Actions is used for tests, not a 09:46 delivery guarantee. GitHub warns
that cron can be delayed/dropped and only runs on the default branch. A ChatGPT
scheduled task is also best effort: task start is not email arrival. For a hard
09:40–09:46 requirement, deploy and monitor the always-on runner with a suitable
live feed and measure end-to-end delivery latency before claiming the SLA.

## Execution-cost evidence and research

Optional EODHD qualification is documented in `EODHD_DATA.md`. Run
`prepare_eodhd.py` only before 09:30 with private credentials and restored state.
Do not run it on the 09:46 critical path. `brief.compute` reads its staged
diagnostics only. Day97 research is offline/shadow and never changes selection.
Preserve private credentials, EODHD diagnostics and successful references in
the operational archive; never copy them into GitHub or task prompt text.

Manual collection accepts verified costs explicitly:

```bash
python collect_execution.py --exit 15:59 --state-dir /var/lib/rb-report --fees-bps VERIFIED_VALUE --slippage-bps VERIFIED_VALUE --borrow-bps VERIFIED_VALUE
python validate_execution.py --panel /path/to/prospective-panel.json --output /tmp/prospective-result.json
```

The placeholders intentionally do not run as numeric values. Never enter zero
unless the cost is actually verified zero. `--borrow-bps` is holding-period
short cost, not annual APR. The timer collector intentionally leaves costs
unspecified until an execution-cost feed is integrated: it records quotes but
will not report false net P&L. Actual broker fills/costs are preferable to BBO
crossing proxies. Do not fill old gaps using current quotes or daily closes.

A native panel is a JSON object with `metadata` and `rows`; see
`validate_execution.gate_native`. Each arm needs its own same-window index and
active exposure. Rows include `entry_spread_bps` and `trailing_vol_pct`; the gate
checks H1/H2 returns and exposure against the fixed formulas, rather than trusting
an arbitrary candidate column. The panel models costs proportional to notional
for H2; fixed-ticket costs require a separately registered extension. Non-session
and early-close dates cannot count toward the holdout. Use fixed original capacity, preserve abstention zeros and
missing-data counts. Both TSX and US native holdouts, point-in-time membership
and complete costs are mandatory. The present TSX-only daily engine cannot
satisfy the US gate by relabelling TSX observations. Results never automatically
change production settings. MDE and controls are reported even for rejected or
underpowered arms; no “improved accuracy” claim without prospective evidence.
