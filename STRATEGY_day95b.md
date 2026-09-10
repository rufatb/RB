# Day-95b addendum — record-integrity corrections (the unrecorded-day class)

Read alongside STRATEGY.md and STRATEGY_day95.md, whose public journals are
unchanged. This day's work was pre-registered on the 447c6fd main as
PREREGISTER_day95.md before any outcome was computed; it lands here as
PREREGISTER_day95b.md because PR #4's merge (3935984) already occupied that
filename. The unrecorded-day alarm exit code is 7 everywhere in this branch
(main's 58da082 had already assigned exit 6 to "published, but provenance not
clean"; that meaning is untouched).

**Record-integrity corrections (the unrecorded-day class) + two registered shadow
studies. `PREREGISTER_day95b.md` was committed before any outcome was computed.**

## The defect that forced the day

2026-09-09: the board was emailed, went 1/4, and was NEVER RECORDED — ledger.csv
and universe_prints.csv both ended 2026-09-08. The publication gate was a single
wall-clock minute evaluated AFTER acquisition; a run crossing 09:47:00 never
published, publish-once then froze the miss, and morning.sh logged a normal-looking
"no new record rows". An unrecorded losing day is upward selection bias in the
track record this repo exists to keep honest. The forensic (5-minute bars,
09:46→15:59 ET): TRP.TO −0.41% (LONG, wrong), ENB.TO −0.75% (LONG, wrong),
BCE.TO −0.43% (SHORT, right), SLF.TO +0.11% (SHORT, wrong); book ≈ −0.21% on
capital; tide (XIU.TO) −0.36% with ≈ 0 tide contribution — pure selection, both
sides ~20 bps behind their hedge. At the ledger's 51.2% hit rate, ≥3 of 4 legs
wrong is a ~30% base-rate day. It deserves a record, not a gap. Publish-once
forbids retro-entering it; the corrections make the NEXT one impossible to miss.

## What changed (registered in PREREGISTER_day95b.md, Part 1)

- **C1.** Publication window 09:46:00–09:49:59 ET (`execution.PUBLISH_WINDOW_MINUTES
  = 4`), replacing the one-minute `strftime` gate. 09:47–09:49:59 is eligible and
  explicitly labelled `LATE-WINDOW — publishable, record marked late`; ≥09:50 is
  LATE/informational as before. The frozen report's provenance records
  `publication_delay_sec` so exact-window studies can filter late records. The
  09:46 ENTRY contract is unchanged; publish-once is unchanged — Store keys by
  session, first write wins, a late rerun re-reads the frozen board.
- **C2.** The unrecorded-day class: an eligible trading session that produces no
  record (no ledger rows, no prints, no prior frozen report) is NOT frozen as an
  informational report (that freeze is what masked 2026-09-09). `brief.py
  --publish` prints `RECORD NOT WRITTEN` and exits 7; `daily_job` sends the email
  with subject prefix `NOT RECORDED — ` and a top-of-body warning and exits 7;
  morning.sh maps 7 to a loud block + exit 7 and never again logs "no new record
  rows (already published today)" without first checking today's date exists in
  ledger.csv/universe_prints.csv. Holidays/CLOSED days stay quiet informational.
- **C3.** `ledger.record_gaps` anchors enumeration on TODAY (lookback-capped), so
  interior gaps like 2026-09-09/09-10 stay visible after later sessions publish —
  the old `missing_sessions` anchors on the last ledger date and goes blind exactly
  when the record looks healthy again. The daily report's RECORD section prints
  `RECORD MAY BE INCOMPLETE — missing sessions: …`, distinguishing missed
  publications from zero-pick days.
- **C4.** r945 robustness on degraded data (no selection change on healthy data):
  the density-cutoff sample sizes against the dropna'd frame (it previously sized
  against the full frame and could raise ValueError out of the 9:46 run; fewer
  than 2 complete rows now fails closed with a named coverage reason), and the
  k-NN rejects non-finite features (`math.isfinite`, not just `is None`), dropping
  and counting non-finite train rows.
- **C5.** A zero-pick day still writes its universe prints (no pick rows; ledger
  schema unchanged), so "ran fine, nothing qualified" is distinguishable from
  "never published".

## H1 — vp train/serve skew (shadow only)

The k-NN compares today's trailing-normalized `vp` against a training frame
normalized by the full-window median: distances on the vp axis are systematically
shifted. Free data cannot evaluate the fix (day-93: 21 usable 5-minute sessions;
the hourly pool has no vp). Day-95 ships `shadow_vp.py`: both normalizations are
scored daily with the shipped machinery, the pick divergence is logged publish-once
to `data/shadow_vp.jsonl`, and a shadow failure can never affect the real run.
The deliverable is a measured pick-divergence rate — NOT an accuracy result.

## H2 — tide-residualized features (registered harness)

Precondition check (recorded in PREREGISTER_day95b.md): **CLEAR** — STRATEGY.md
contains rejections of beta-matched LEG PAIRING and of a tide-removed cross-sectional
training TARGET, but no rejection of index/beta-residualized FEATURES for the k-NN.
`validate_residual.py` implements the registered design on the hourly two-feature
pool: r0′ = r0 − β·r0_XIU, gap′ = gap − β·gap_XIU, β point-in-time from the
trailing 60 sessions; paired out-of-sample AUC vs raw, influence aggregated within
session, deterministic block bootstrap (20-session blocks, 2,000 draws, seed 95),
four chronological development blocks, planted +2-AUC-point control in edge/SE
form, sign-flip placebo at its 95th percentile, MDE = (3.5 + 0.8416212336) × SE
printed always. Fixture tests: planted edge DETECTED, zero edge NOT claimed,
bitwise deterministic. The real run is **BLOCKED** in this sandbox (URLError:
urlopen timed out — no network); recorded with error classes in
`data/day95_residual_results.json` for a networked host to re-run. No adoption
from either study: shadow logging only, selection/sizing/entry contract untouched.
