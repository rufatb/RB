# Working notes for this repo

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
