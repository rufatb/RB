# Pre-registration — day-95b: record-integrity corrections and two registered studies

Committed BEFORE any outcome is computed. Bars fixed here and do not move.


## Naming

Originally drafted as PREREGISTER_day95.md on the 447c6fd main and committed
there before any outcome. PR #4 (merged as 3935984) had independently added
its own PREREGISTER_day95.md on the moved main, so this file lands as
PREREGISTER_day95b.md (repo precedent: day83/day83b). The registration text,
bars and precondition outcome are unchanged; the exit-code it registers for
the unrecorded-day alarm is now 7 (main's 58da082 assigned 6 to
"published, but provenance not clean" first).

## Why this exists

2026-09-09 exposed a defect class independent of prediction quality: the board
was emailed, went 1/4, and was NEVER RECORDED (ledger.csv and
universe_prints.csv both end 2026-09-08). An unrecorded losing day is not a
process footnote — it is upward selection bias in the track record this repo
exists to keep honest. The forensic (run on 5-minute bars, 2026-09-09
09:46→15:59 ET): TRP.TO −0.41% (LONG, wrong), ENB.TO −0.75% (LONG, wrong),
BCE.TO −0.43% (SHORT, right), SLF.TO +0.11% (SHORT, wrong); book ≈ −0.21% on
capital; tide (XIU.TO) −0.36% with the market-neutral book ≈ 0 tide
contribution — the loss was pure selection, both sides ~20 bps behind their
hedge. At the ledger's 51.2% hit rate, ≥3 of 4 legs wrong is a ~30% base-rate
day. It deserves a record, not a gap.

## Part 1 — infrastructure corrections (not alpha claims)

Registered so the diff is reviewable against intent:

- C1. The publication gate was a single wall-clock minute
  (`now.strftime('%H:%M') == '09:46'` evaluated AFTER acquisition). Any run
  crossing 09:47:00 never publishes; publish-once then freezes the miss; the
  email still sends. Correction: publication window 09:46:00–09:49:59, and the
  frozen report records `publication_delay_sec` so exact-window studies can
  filter late records. Entry contract (09:46) unchanged; this is about the
  RECORD, and a late record is explicitly labelled late.
- C2. An eligible session that produces no record must ALARM, not send a
  normal-looking email: distinct exit code, loud subject, and morning.sh stops
  claiming "no new record rows" on coverage-fail days.
- C3. Record gaps must be printed in the daily report's RECORD section
  (gap detection currently exists only on CLI paths and stops enumerating once
  a later session publishes — interior gaps become invisible).
- C4. r945 bug fixes that cannot change selection on healthy data: the
  density-cutoff sample is drawn from the dropna'd frame (currently sizes
  against the full frame and can raise), and k-NN rejects NaN features
  (currently checks only `is None`).
- C5. A zero-pick day must still write its universe prints (day-29's design:
  every evaluated day leaves a trace), so "ran fine, nothing qualified" is
  distinguishable from "never published".

Known defects recorded but NOT changed here (they alter live selection and
require their own registered tests): the `vp` train/serve skew (training frame
normalizes by full-window median; live uses trailing-only) — see H1; the
non-Yahoo data-source fallback (every configured source silently degrades to
yahoo_direct); the stale `max_chase_pct` 0.15 fallback default.

## Part 2 — registered studies (shadow only; no adoption from either)

**H1 — vp train/serve skew.** The k-NN compares today's trailing-normalized
`vp` against a training frame normalized by the full-window median: distances
on the vp axis are systematically shifted. Free data cannot evaluate the fix
(day-93: the 5-minute pool is 21 usable sessions; the hourly pool has no vp).
Registered remedy: a SHADOW A/B — both variants computed daily, picks logged
side by side, no accuracy claim until a paid 5-minute history exists; the
deliverable is a measured pick-divergence rate, nothing more.

**H2 — tide-residualized features.** Replace raw `r0`/`gap` with their
index-residualized counterparts (r0 − β·r0_XIU, gap − β·gap_XIU, β from
trailing 60 sessions) in the parity k-NN, on the hourly two-feature pool (the
set day-43 actually tested). Paired out-of-sample AUC vs raw features,
influence values aggregated within session, deterministic block bootstrap
(20-session blocks, 2,000 draws, seed 95), four chronological development
blocks, planted +2-AUC-point control (edge/SE form), sign-flip placebo at its
95th percentile, MDE = (3.5 + 0.8416212336) × SE printed always. Preconditions
checked BEFORE running: if STRATEGY.md already contains a rejection of
index-residualized or beta-adjusted features, H2 is WITHDRAWN and the citation
is recorded here instead of re-running a decided question. Runnable on the
host (network); sandbox execution is expected to be BLOCKED and would be
recorded as such.

## Forbidden

Retro-entering the 2026-09-09 or 2026-09-10 boards (publish-once; a late report
never creates a retrospectively chosen board). Any change to selection, sizing,
or the 09:46 entry contract under the cover of these corrections. Presenting
the shadow A/B divergence as an accuracy result.

## H2 precondition outcome

CLEAR — no prior registration found. STRATEGY.md was searched
case-insensitively for `residual`, `beta-adjust`, `beta-match`, `tide-adjust`,
`index-adjust` (and, broadly, `residualiz`, `market-adjust`,
`beta … feature`, `hedged feature`, `cross-sectional target`, `y_rel`). The
matches are: (a) "Beta-matched pairing (pick the long/short combo with the
closest betas)" — a rejected LEG-PAIRING rule, not residualized k-NN features
(explicitly out of scope of this precondition); (b) "Tide-removed
(cross-sectional) training target" — a rejected change to the TARGET y
(cross-sectional demeaning of labels), not index-residualized FEATURES;
(c) attribution/accounting uses of "residual" (tide decomposition), not
feature tests. No rejection of index- or beta-residualized r0/gap features
for the k-NN exists in STRATEGY.md, so H2 proceeds as registered.
