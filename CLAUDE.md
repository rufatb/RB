# Working notes for this repo

## Day111b — the population was never roster-bound; it was warm-up bound

**MEASURED: the eligible set was IDENTICAL day to day.** 09-17 and 09-18 both
produced 38 usable names and overlapped 38 of 38. Both model sections were
choosing from a set that never moved, which is exactly what the owner reported.

The roster was not the cause — 130 names were already requested. RSI/MACD/RVOL
were derived from a FIVE-MINUTE panel (each session's 15:55 bar as its close);
MACD needs 35 CONTIGUOUS sessions and Yahoo serves ~41 of 5-minute history, so
any excluded session truncates the tail. Day-109 saw the same shape from the
other end (60 → 130 moved assessed 23 → 29) and read it as a roster result.

`daily_technicals.py` computes the daily indicators from TRUE DAILY BARS (~250
sessions), and `prepare_factor_pool` runs it as a second pass that fills only
what the warm-up could not produce — `r0`, `vwap` and the opening range are
intraday and stay with the 5m panel, and five-minute values WIN on merge.

    acquired 77/130 → 117/130 · complete technicals 38 → 77 · usable 38 → 116

**Biotech comes from bars already on disk.** `build_biotech.py` stages US
securities with `daily_bars` attached — 109 of 111 compute at zero acquisition
cost. They are US/USD; the baseline engine neither scores nor prices them, so
every row carries `market` and `currency` and the prompt says not to compare
levels across markets. **`validate_payload` STRIPPED that tag** (unknown fields
never pass through) — now passed from a CLOSED set, bogus values rejected.

**`MAX_NAMES` was 60 and cut in ROSTER ORDER**, so AGI, IVN, LUN and PAAS —
names both models had been picking — were complete, present and silently
dropped for being alphabetically late. An alphabetical slice is an unregistered
selection rule. Raised to 250; measured at 116 names the DeepSeek payload is
~5.9k tokens / 27.5s (no worse than at 38) and Jev ~9.2k / 1.0s, so the budget
was never the constraint. If it ever binds again it is DISCLOSED in the gaps.

**Jev abstains more as the population grows.** At 38 names it shorted SHOP.TO;
at 116 it declined both sides, because probability mass spreads across options
and nothing beats its own `NONE`. That is the registered gate working, not a
fault, and the gate has no dial to turn.

### Three self-inflicted defects worth remembering

1. **Both new passes were DEAD CODE when first shipped.** They were gated on
   `fetcher is None`, but `_prepare` does `fetcher = fetcher or fetch_history`
   near the top. The live run returned `daily_filled: 0, biotech_added: 0` and
   the same 38 names while reporting `PARTIAL` and looking healthy. Every test
   passed because none asserted the passes did WORK.
2. **The gate was then wrong a second way.** Several tests inject `acquire_fn`
   and NOT `fetcher`; the daily pass opened real sockets behind their mocks and
   filled the very names they assert were not acquired. Gate on ANY injection.
3. **Two mutants survived the first pass.** A mostly-daily series riddled with
   holes keeps a 1.0-day median, and the 5m/daily merge was never exercised
   because the daily-filled name had failed 5m acquisition entirely and so had
   nothing to overwrite — that needs a PARTIAL fixture.

## Day111 — Jev, a second opinion from a DECISIONS model

Read `PREREGISTER_day111_jev_opportunities.md`. `jev_opportunities.py` asks a
second model the same question as day-110, from the same prepared evidence, and
renders under the DeepSeek section. Neither is adopted and they are NEVER
averaged — averaging two unmeasured opinions makes a third that looks better
than either.

**Jev is not a chat model.** `typesafe/jev-1.13` is reachable only at
`POST https://openrouter.ai/api/alpha/decisions`; `/chat/completions` rejects it
outright. `typesafe/jev-latest` is **NOT a valid model id** — pin the version,
because a floating alias that 400s every morning looks exactly like an outage.
The request is `{model, state, questions}`; answers are typed `noul` (bare 0-1),
`choice` (an option from a supplied set, plus a probability over EVERY option
and a confidence) or `score` (a point on a supplied ordinal scale).

**The typing is the reason to use it.** With `choice`, the option set IS the
universe, so the provider makes the invented-ticker failure unreachable rather
than leaving it to a validator. The validator is kept anyway.

**THE GATE HAS NO DIAL.** A name is reported only when its probability exceeds
the probability the model itself assigned to `NONE`. There is deliberately no
constant to nudge after a losing day — the day-98 side-skill family shows what
happens when there is one.

Measured 2026-09-18: **0.83 s and $0.00002** per call over 38 names, both sides
in ONE request — two orders of magnitude faster and cheaper than the DeepSeek
call. That is a robustness argument, not an accuracy one.

Positive control passes both directions on the day-110 planted universe
(`CTLUP.TO` 0.79 vs abstain 0.21; `CTLDN.TO` 0.54 vs 0.39; no noise name
cleared). Re-run with `python jev_opportunities.py --control`.

First live reading: Jev abstained entirely on the long side and shorted
SHOP.TO; DeepSeek independently shorted SHOP.TO too. One agreement on one day
is a recorded observation, not evidence.

The OpenRouter credential lives at `${RB_STATE_DIR}/secrets/openrouter_api_key`,
mode 0600, gitignored — same contract as the DeepSeek key, and it dies with the
container the same way.

## Day110 — the model was never asked the question the owner was asking

`deepseek_factors` answers "is there directional sentiment in these headlines".
On a commentary feed that is `NO_EDGE` almost every day, and day-109 proved the
abstention is real. But nobody had ever asked DeepSeek **which names it would be
long and short, and how sure it is**. That is an opinion, not a sentiment
reading, so it is a separate module (`deepseek_opportunities.py`), a separate
staged snapshot, and its own report section beside the board. Read
`PREREGISTER_day110_deepseek_opportunities.md`.

**`deepseek-flash` is a REASONING model.** Measured on 46 names it spent
**15,939 tokens thinking** and 349 emitting JSON. `max_tokens=4096` truncated
every reply and the section read UNAVAILABLE against a healthy provider;
`MAX_COMPLETION_TOKENS` is 32,768 and a truncated reply is never parsed. One
request takes ~54s over 39 names — by itself disqualifying for the 09:46 window,
which is why it is staged pre-open by `morning_full.sh` and read by a pure
reader.

The positive control passes **numbers only** (house rule 4, and day-109's
lesson): planted long `CTLUP.TO` returned at 0.74, planted short `CTLDN.TO` at
0.63, none of the ten noise names picked. Re-run with
`python deepseek_opportunities.py --control` before reporting any null.

**A confidence here is the model's own number.** Not calibrated, no track
record, never scored against an outcome, and **never blended** with the engine's
sided probability — averaging a measured quantity with an unmeasured self-report
launders the second into the first.

**`compare()` needs the engine universe or it lies.** The engine scores 21
names; the pool is 130. On 2026-09-17 all four picks (EMA.TO, CAE.TO long;
AGI.TO, CG.TO short) were `UNSEEN` — outside the engine's universe — so the
0-of-4 agreement is a fact about COVERAGE, not disagreement. Without the
universe argument every such row would have read "the engine rejected this",
which is a claim about the engine from evidence containing none.

A ranking asked after 09:30 is a different instrument from one asked before it,
and both renderers label the diagnostic case rather than printing "pre-open".

### Day110d — the 130-name pool has NEVER been staged by a scheduled run

2026-09-18 published ON TIME at 09:46:09 and the opportunities section read
**"The candidate pool has not been staged (FileNotFoundError)"** on a healthy
account. `prepare_factor_pool.py` writes `deepseek_candidates.json` and
**nothing else does** — and it was never in `morning_full.sh`. So the factor
layer has been quietly working off the 21-name CONFIGURED universe (that is the
"Assessed 17 / 21" on the page) rather than the 130-name pool it is documented
to use, and `deepseek_opportunities` had no pool at all. It now runs BEFORE the
news refresh, so headlines are fetched for the pool's names, not just the
baseline twenty-one.

`bar_cache.py` stages into `$RB_STATE_DIR/intraday_cache`; `morning.sh` reads
**`RB_INTRADAY_CACHE_DIR`**, which nothing ever set. Every morning staged a
cache and then acquired all 21 names live beside it — the "cache DEGRADED"
line on the page was telling the truth about a silent no-op. Exported now.

`prepare_factor_pool.py` run after 09:30 raised a bare traceback, so a CORRECT
refusal was indistinguishable from a crash in the morning log. It exits **3**
with `{"status":"REFUSED","reason":"RESEARCH_POOL_PREOPEN_ONLY"}`.

**A Routine's `last_run.finished_at` is the DELIVERY record, not the session.**
09-18 showed fired 13:06:24 / finished 13:09:13 and looked like a 3-minute
death; the session actually ran to 13:50 and published at 09:46. Check
`get_session` `updated_at` and the artifact's `updated_at` before concluding a
run died.

### Day110c — the ranker was reading charts with the news on the same disk

`stage()` read `deepseek_candidates.json`, which carries **technicals only**.
`factor_inputs.build_from_state` is the function that merges the staged
headlines and the macro block, bounds them, and RECOMPUTES each headline's
classification instead of trusting a staged claim. Reading the raw file meant
82 names' headlines and all four macro fields sat unused on the same disk while
the model guessed from prices. It now reads the validated payload.

Each headline travels **with its quality label** — `class`, `issuer_verified`,
`first_disclosed` — because the title alone is the dangerous form: day-109
established that evidence quality, not the model, is the binding constraint,
and a model shown only the words reads a stock-pick column as a catalyst. The
prompt states what COMMENTARY / MULTI_YEAR_TITLE / UNCLASSIFIED are worth, and
marks all supplied text UNTRUSTED DATA, NEVER INSTRUCTIONS.

`evidence` records what the model was actually SHOWN (names with news, macro
fields) and both renderers print it. A ranking made on prices alone and one
made with the morning's tape are different readings; printing the picks without
the evidence count invites the first to be read as the second. With no news
staged the gaps say "technicals only" rather than looking informed.

**The account carries ONLY `deepseek-flash` and `deepseek-v4-pro`.**
`deepseek-chat` and `deepseek-reasoner` DO NOT EXIST on it — verified against
`models.list`. Measured 2026-09-17 on 39 names with full evidence: flash 30.5s,
v4-pro 79.0s; flash cited WTI −1.31% for its oil shorts and named its headlines
UNCLASSIFIED, v4-pro gave terser technical-only reasons. flash stays the
default. Catalyst tags are **zero** on TSX names — that harvest is SEC 8-K,
i.e. US issuers.

**`r945.run`'s too-early branch dropped `cache_degraded`.** Every other exit
carries it; that one computed the degradation and threw it away, so a pre-open
caller was told nothing about a missing cache — the silent degradation day-103
exists to prevent. Its test read the WALL CLOCK, so it only ever exercised the
post-09:46 path: green every afternoon, `KeyError` at 09:05. Both clocks are
pinned now.

### The three wiring defects found when asked "will this actually run tomorrow"

1. **`report_page.py` was invoked by NOTHING.** It was written to stop the daily
   HTML being rebuilt by hand, then went on being rebuilt by hand — the exact
   drift its own docstring warns about. `daily_job.run` now writes
   `report_page.html` beside the three artifacts, inside a try so a page fault
   cannot cost the record.
2. **The credential never reached the ranker.** `rank()` reads `os.environ`,
   right for a pure function and wrong for a job: run from `morning_full.sh` in
   a fresh process nothing had exported the key. `stage()` now calls
   `prepare_deepseek.load_private_key/load_private_model` — one implementation
   of the contract, not a second copy that drifts.
3. **The page had no DOCTYPE and no charset.** Harmless while it was pasted
   somewhere; a mojibake and quirks-mode risk now the job writes a file opened
   from disk.

**`.rb-state/` is gitignored, so a fresh container has NO credential.** Every
session must supply `DEEPSEEK_API_KEY` (env, or
`$RB_STATE_DIR/secrets/deepseek_api_key` mode 0600) before 09:30 or both model
sections read UNAVAILABLE against a healthy account. `morning_full.sh` checks
this FIRST and names the remedy while there is still time to act.

`tests/test_morning_full.code()` used to keep TRAILING comments, so an ordering
assertion matched prose forty lines above the command it described. It now cuts
at an unquoted `#`.

## Day109 — the factor layer's NO_EDGE is a tested abstention

Read `AUDIT_day109_factor_positive_control.md`. A planted-edge control through
the real `evaluate_batch` path returns **BULL +0.30** and **BEAR −0.60** on
unambiguous catalysts, and **raw equals final** on both — so `factor_grounding`
is NOT flattening leans, and the harness detects a planted edge in both
directions. House rule 4 is satisfied: the NO_EDGE sessions are informative
nulls, not a broken harness.

The first control was CONFOUNDED by its own design — it wrote "SYNTHETIC
CONTROL" into the headline text and the model correctly refused to lean on
evidence labelled fake. Do not repeat that: plant realistic wording.

The binding constraint is EVIDENCE QUALITY. `factor_news.classify_headline`
labels every Yahoo RSS item COMMENTARY or UNCLASSIFIED with
`first_disclosed_at: None` and `primary_source_verified: False`, because the
feed carries no disclosure metadata; catalyst tags were zero across all 130
names. Widening the roster 60 → 130 moved assessed 23 → 29 and produced no
extra lean. More names carrying commentary are still commentary.

A lean does not imply a board: `BULL +0.30` on a name whose quant score is
0.504 gives combined 0.512, under the 0.55 threshold. The lean gate and the
score gate are independent and both must pass.

`public_payload` rejects a staged candidate until it is stripped to
`CANDIDATE_KEYS` — the staged rows carry an extra `technical_provenance` key.

## Day105 — the morning run is a Routine, and the email is its summary

`trig_01YZ2smjbMZXJvWKBxU4JfWj` — "RB Daily Report — weekday 09:46 ET", cron
`40 13 * * 1-5` (UTC; 09:40 ET), fresh session per fire, notifications push +
email. It runs `morning.sh`, which waits for the publication minute, publishes,
pushes the record CSVs, then rewrites the owner's page at
`https://claude.ai/artifact/28ZfvwVZG1A2yagxJ4Hyt9` and finishes with a short
summary. **That summary is the email.** It is not `deliver_report.py`: no SMTP
credential and no Gmail connector exists, so the inbox is reached through the
Routine's own notification channel.

**Cron is UTC and does not know about DST.** `trig_01AG5fGuTJtdADMJyse1Sizj`
fires once on 2026-11-01 to shift the cron to `40 14 * * 1-5` when EDT ends,
and is instructed to register the reverse for 2026-03-14. Do not "tidy up"
either Routine without replacing that mechanism.

**09:46 is the earliest honest publication and cannot be moved.** The third
five-minute bar closes at 09:45, `r945.run` refuses before open+16 minutes, and
`exact_spread` requires 09:46 at both the quote and the clock. Firing at 09:40
buys acquisition slack, not an earlier report; the gain over recent mornings is
that it is on time at all rather than at 09:59 or 11:22.

The concise email omits a section that produced nothing rather than printing
UNAVAILABLE lines about it — see day-105 in the render notes below. The full
attached report is unchanged and remains the record.

## Day103 — a missing cache costs latency, never the board

`require_cache` used to RAISE when no cache directory was staged, to protect
the 22s budget after the day-97 timeout. The budget is real; refusing to run
was not the way to protect it. **2026-09-14 and 2026-09-15 both published a
board with ZERO names evaluated and emailed "SCAN UNAVAILABLE" on a healthy
feed** — the whole TSX-21 fetches live in 4.1–5.1s against that 22s budget
with no errors.

`bar_cache.cache_ready(adapter, now)` answers whether the cache can serve THIS
session from THIS source — the 09-15 board was empty *with* the variable
exported, because the manifest was staged for 09-11. `get_bars` falls back to
live acquisition on any miss and reports it through `on_fallback`; `r945.run`
counts them into `cache_degraded` / `cache_fallbacks`, and both renderers print
the degradation. The board is unaffected — caching "changes acquisition only,
not baseline features or rules" — but a fallback means a pre-open job did not
run, and it is never silent (house rule 1).

The tightened socket budget now follows `cache_ready`, not the env var: 14s/16s
is sized for small same-day responses, not a 60-day fetch. A cache holding
today's bars is LEAKAGE and is discarded for a live fetch, reported, not trusted.

**The host has never been installed and cannot be installed from a Claude Code
container** — PID 1 is not systemd, and `install.sh` refuses by design. The
board no longer depends on that install; delivery still does.

## Day100 — a hole in the record must stay visible

Read `AUDIT_day100_day95b_review.md`. `ledger.missing_sessions` anchors on the
ledger's LAST date and walks forward, so an interior gap disappears the moment
a later session publishes — verified on our own ledger: three missing days
become `[]` when one row for 09-11 is added. `ledger.record_gaps` anchors on
TODAY, walks backward, and is print-aware, so it separates *the run never
happened* from *the run happened and picked nothing*. Only the first is a gap.
It prints **beside the hit rate in the email**, because a rate over a holed
record is a rate over what survived. It never blocks: this protects the RECORD,
not the bet.

`kimi/day95-record-integrity` is NOT mergeable — its base predates PRs #5–#12,
so it would resurrect `adapters.py` and delete thirteen CLAUDE.md sections. Its
diagnosis was right and is ported. Its four-minute publication window is
**refused**: it sets `eligible=True` for 09:47–09:50, which licenses a fresh
entry claim at prices the board does not show and contradicts day-99's
`exact_spread`. Do not loosen an execution contract to make a missed run look
on time.

DeepSeek credentials are live and verified: the account carries `deepseek-flash`
and `deepseek-v4-pro` and **not** `deepseek-chat`, so the explicit model setting
is required. A probe verified credentials, model access and JSON handling only —
not coverage, not accuracy.

## Day99 DeepSeek — staged, shadow, and it must never cost the morning

A shadow layer with no adopted output may not block publication. The day-99
merge put `openai`, `socksio`, `adapters.deepseek_adapter` and `factor_inputs`
in `runtime_check.REQUIRED`; `morning.sh` exits 1 on any non-zero there, before
acquisition. On a venv predating the merge that is **no board, no ledger row
and no email at all** — `brief.compute` already degrades to UNAVAILABLE, and
the import gate made that degradation unreachable. Those four are now OPTIONAL:
counted, named, logged as DEGRADED, never blocking.

`rb-deepseek.timer` (09:15 ET) stages the snapshot. Nothing ran
`prepare_deepseek.py` before — `load_prepared` is a pure reader, so the section
would have read "Assessment unavailable" every morning while looking installed.
The window is bounded at both ends: after 08:05 staging, before the 09:30
cut-off the reader enforces, and inside `MAX_SNAPSHOT_AGE_HOURS`.

**The host needs `DEEPSEEK_MODEL=deepseek-flash` explicitly.** The code default
`deepseek-chat` was absent from the 2026-09-12 account listing and there is no
automatic fallback. The credential belongs in
`${RB_STATE_DIR}/secrets/deepseek_api_key`, mode 0600, never in a unit file.

A passing import check is not provider reachability, and no factor output is
adopted, sized or ranked into the baseline board.

## Day98 side skill — registered, and NOT answerable until ~2027-04

`PREREGISTER_day98_side_skill.md` and `AUDIT_day98_losing_days.md`. The long
side shows 42.9% against a 53.0% base rate (−10.1pp, −1.42 SE) on 51 legs; the
short side +6.4pp at +0.98 SE. **Neither is significant and rejection #16
already refused this family**, having found the deep set and the true 5-minute
set said OPPOSITE things about which side was broken.

Resolving a 10pp side effect at |t|>=3 needs ~230 legs per side. At 1.27 long
legs per session that is ~140 further sessions. **Do not re-open this after a
losing day** — the bar and the date are registered precisely so it stops being
re-litigated.

What needs no test: the win/loss ratio is **0.92** against the **1.06** needed
to break even at a 48.6% hit rate. That is arithmetic, and it is what loses
money — not the hit rate, which is the ledger's headline metric.

An ABSTAINED leg renders no share count and no dollar figure. A row carrying a
size is an order ticket whatever the Status column says; the banner alone did
not stop it being acted on twice.

## Day98 training integrity

Read `AUDIT_day98_training_integrity.md` and
`PREREGISTER_day98_training_integrity.md`. Production training and preflight
now validate the actual exchange-session grid and immediate prior close through
`intraday_history.py`. The legacy extractor remains for old-study reproduction.
`audit_training_history.py` is standalone descriptive research, never a live
selector. Preserve missing-data counts, immutable publications and prior work.
These corrections do not establish an accuracy gain. Common exposure by side
is computed once and printed beside the concise email's hypothetical legs.

## Day97 EODHD qualification

Read `EODHD_DATA.md`, `AUDIT_day97.md` and `PREREGISTER_day97.md`. EODHD is
an optional historical/reference provider, not a live source switch. Its free
plan has not been proven to support Canadian intraday data. Private credentials
and diagnostics stay outside git. The new opening-path harness is shadow-only;
145 sessions are a runnable floor, not a statistically adequate test. The
baseline selector and allocation remain unchanged on healthy data.

## "run report" means one computation

```bash
python brief.py                         # preview; does not publish
python daily_job.py --send               # scheduled 09:46 ET, freeze + render + email
python brief.py --publish --format json  # publication without email
python brief.py --offline                # diagnostic; no network or ledger writes
```

`brief.compute` owns acquisition, calculation and publication. Renderers consume
its frozen schema-v2 output and never fetch, select, score, allocate or persist.
The full intraday board and objective Top-2 biotech monitor are separate engines.
Read `RUNBOOK.md`, `BIOTECH_DATA.md` and `AUDIT_day90.md` for operational details.

At 15:30, 15:45 and 15:59, `collect_execution.py` records exact-window quotes;
unknown costs remain unscored. `ledger.py --score` is the **legacy official-close
proxy**, never evidence of exact 09:46/15:59 execution. Preserve both records.

## Before touching anything, read STRATEGY.md

It is the running record of every change tested — **40 rejections, 3
adoptions**. Almost every "obvious improvement" in this space has already been
measured here and refuted. Check before proposing.

The three adopted changes were all VARIANCE results. None improved accuracy.

## The constraint that governs the intraday engine

The current studies have not established usable directional skill. Day43
reported gradient-boosting **AUC 0.5022 on 122,234 out-of-sample rows** in an
hourly proxy that dropped `vp`; the smaller five-minute panel included it.
Day91 found that the historical comparator labelled shipped k-NN used different
math, and the quoted z statistics treated same-session rows as independent.
The original results, including the planted control's reported z=15, remain
historical records, not corrected reruns or proof of a universal feature ceiling.
`validate_ceiling.py` now matches the live scorer's arithmetic and reports
session-clustered comparisons; full live-pipeline parity still requires matching
the data, feature construction, training windows and execution contract.

Do not promise better accuracy from this engine. Do not present its picks as
predictions. The report prints its own record beside every pick for this
reason.

## House rules, learned the hard way

1. **Never swallow an exception silently.** Day-29: a bare `except: pass` hid
   a `NameError` and no universe prints were written at all. Day-55: the same
   pattern hid 2,214 consecutive HTTP 403s. Count failures and report them.
2. **Fail closed on data.** Missing coverage, an unmarkable position, a stale
   print — say so and exclude it. Never carry a position at cost; absence of
   data is not absence of movement (day-42).
3. **Pre-register the bar before running the test**, and do not move it
   afterwards. Four quarters on both markets, or it is a window artifact.
4. **Every null needs a positive control.** A harness that cannot detect a
   planted edge cannot report a null. Day-51 and day-56 were both caught this
   way, and day-46's own bar turned out to be unsatisfiable for this reason.
5. **Placebo anything that looks like a prize.** Day-51's "oracle gap" of
   +2.34%/trade was smaller than pure noise produced (+2.85%).
6. **Sync before working.** The container resets between turns; `git fetch` and
   fast-forward first. A stale clone once put a wrong record in a live report
   (day-42).
7. **A ratio needs both legs from one population.** Day-71: P(CRL) is only
   meaningful because rejections AND approvals come from the same harvest, the
   same classifier and the same window. Mixing an EDGAR numerator with a
   Drugs@FDA denominator would have produced a confident number describing
   nothing. Where a leg might be undercounted, MEASURE the undercount and show
   the correction beside the raw figure rather than folding it in.
8. **A rate over a population is never a forecast for one name.** Print
   UNCONDITIONAL next to it every single time. It is the prior you argue away
   from.
9. **Verify the data you got, not the data you asked for.** Day-72: Yahoo
   answers `interval="1d", range="max"` with WEEKLY, MONTHLY or QUARTERLY bars
   and no error, so day-68's "3-day event window" was three months on some
   names and shipped for four days. Assert granularity, count what you reject.
10. **A control that cannot detect a planted edge means UNDERPOWERED, not
   NULL.** Day-72's run-up study can only resolve a drift above 6.2pp; "no
   effect found" there would be a claim the data cannot support. And build the
   control to measure `edge / sd`, never `(mean + edge) / sd`.

## Read-only, always

Nothing in this repo submits, modifies, or cancels a brokerage order. Hypothetical allocation is a research calculation. `positions.py` records
what the user says they did. Keep it that way.

## Day-90 operating contract

`PREREGISTER_day90.md` was committed before analysis. H1 spread abstention, H2
cost sizing and H3 fixed earlier exits are shadow-only; no baseline tuning or
overnight adoption. Always print missing-data coverage and MDE. Preserve rejected
research even when unreachable from the daily entrypoint. New FDA transparency
sources do not authorise mixing numerator and denominator populations.

## Day-93/94 outcomes

Day-93 (`PREREGISTER_day93.md`): the ceiling test WITH `vp` is UNRUNNABLE on
free data — Yahoo's ~41 sessions of 5-minute history cannot meet the corrected
harness's 125-session floor at any feature count, and the bar was not lowered.
The old two-feature study did not establish usable skill, but its comparator
and uncertainty defects prevent treating it as a universal feature ceiling.
The three-feature question remains OPEN; tested free-history depth was
insufficient for the registered study (see `DATA_CEILING.md`).

Day-94 (`PREREGISTER_day94.md`, shadow research, no adoption): `build_social.py`
forward-collects StockTwits/Trends attention snapshots into `data/social/` —
coverage gate after 20 sessions, no inference before 120. `validate_crossmarket.py`
is the registered test of prior-session US proxy state (SPY/XLF/USO/USDCAD) beyond
`[r0, gap]`, a DAILY-BAR PROXY that cannot certify the 09:46 contract.

## Pairs trading was tested and REJECTED (#41), on our own universe

Day-96. `pairs.py` / `validate_pairs.py` / `build_tsx.py`, pre-registered at
`cac0666`. On the TSX-21 all six cells lose money **gross and net** — best cell
−0.111%/trade, worse than the placebo (p=0.846), negative in all four quarters —
and the planted control DETECTED at t=4.20, so this is a POWERED negative, not
an underpowered shrug.

On US names the apparent +0.0367% edge is **selection luck**, established by
`pairs.reselection_placebo`, which re-runs formation and pair choice on a null
panel where nothing is cointegrated: 124 of 200 null draws BEAT the real result
(p=0.62), and for the selected cell the null returns MORE than the real panel
(+0.0388% vs +0.0367%). Cell by cell, real minus null averages +0.0036%/trade.
The conditional placebos in the original write-up could not see this because
they hold pair selection fixed; that claim was withdrawn. What survives as
description only: the apparent effect sat entirely in the smallest liquidity
quartile and the largest quartile is negative in both panels — pairs trading
buys the underperforming leg, the family `DATA_CEILING.md` calls untestable on
free data.

`pairs.naive_public_recipe` keeps the standard public methodology beside the
honest one: it reports **+0.1177%/trade at t=+3.1 on the TSX-21**, which really
loses 0.188%. Do not re-litigate this family without reading day-96 first.

Nothing from it is wired into selection, sizing, the report or the email.

## Is main everything? Run `provenance.py`

Read AUDIT_day96_preflight.md before implementing PREREGISTER_day96.md.
The clamped statistical-effect helper is not signed net trading P&L; the
amendment fixes the cost denominator and identifies timing/formation choices
that must be frozen before inference. No pairs result is adopted here.

`git status` clean does not mean main is complete. `clock_vs_data` sat finished
on another branch for **five weeks** and every morning ran without it;
`build_social.py`, a forward collector whose missed days cannot be back-filled,
sat unmerged for two. Both were invisible to `git status` and to a fully green
suite, which passes perfectly on an incomplete main.

`provenance.py` asks the three questions that matter, by CONTENT — a branch-only
file, a top-level symbol main has nowhere, or a record date main has never seen.
It does not use commit counts as evidence: a fully-merged branch showed "2
commits ahead" and a rename read as lost work on the first run. `morning.sh`
runs it at 09:39, WARNS without blocking, and exits **6** — published, but not
on the whole of main.

## September 8 recovery

Intraday and equity acquisition have independent process deadlines (22s/10s).
Timeouts preserve recorded boards, position facts and reviewed calendars. Same-day
published ledger rows win over a fresh selection; never replace them on a rerun.
Pre-open history caching changes acquisition only, not baseline features or rules.
`preflight.py` checks staged readiness; `sync_runtime.py` imports new Claude-published
CSV records without merging code or overwriting earlier values. `state_bundle.py`
preserves SQLite history safely. See RUNBOOK for the daily/weekly calendar,
reference-close context, and unresolved live-data/holdings-verification gates.

## Day 95 integration

Read `AUDIT_day95.md`, `STRATEGY_day95.md` and `PREREGISTER_day95.md`. Claude's quote-authentication
fix and Kimi's day94 research are integrated; no new predictor or sizing rule
is adopted. `brief.compute` freezes empirical session risk, clustered hit-rate
uncertainty, analog-score reliability and common exposure. Renderers never
reread config. An analog score is not a calibrated success probability.

For Gmail, run `daily_job.py` WITHOUT `--send`. After the durable delivery claim
is saved, run `prepare_delivery.py` immediately before transmission and use
its exact subject/text/html. Late dispatch labels the body as well as subject;
the original publication stays immutable. The existing preparation and daily
tasks must pin the same reviewed main commit; fetch moving main for CSV record
imports only, never for executing unreviewed code during a scheduled run.

### Day99 DeepSeek integration (unadopted)

`brief.build()` returns the single Digest; renderers are pure views, never
provider/model calls. `adapters` is now a package preserving existing exports.
The bounded DeepSeek JSON client runs only in `prepare_deepseek.py` before the
open; report computation reads the staged snapshot and computes preregistered
shadow arms using the existing quantitative pool. Preserve baseline selections
and allocation. NO EDGE - WAIT denotes a tested abstention; unavailable input
is not proof of zero market opportunities. No accuracy gain is claimed.
Read DEEPSEEK_DATA.md and PREREGISTER_day99_deepseek.md before editing this path.
The six protected files, including constants.py, remain unchanged; DESIGN
bounds live in deepseek_policy.py and do not mutate constants.REGISTRY.
