# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## House rules

1. **Never swallow exceptions** — report error CLASS, surface them in the email; use targeted failure handling.
2. **Fail closed** — unknown market calendar/feed/clock state means no board, not a guess.
3. **Registration before outcomes** — hypothesis, bars, MDE, and controls are written BEFORE any outcome is computed. No retro-registered studies.
4. **Publish-once is sacred** — a late report never creates a retrospectively chosen board; missed days stay gaps and are labelled as such.
5. **No hidden state** — every decision input is in the repo or fails loudly; no local-only flags that change behavior.
6. **Sync before run** — a board published from a stale clone can duplicate or contradict the record; pull first, always.

## Commands

- Daily brief (also publishes when eligible): `python brief.py --publish`
- Preview only, no writes: `python brief.py`
- Offline/diagnostic: `python brief.py --offline`
- Legacy engine CLI: `python r945.py --book [--shadow]`
- Tests: `python -m pytest -q`

## Architecture

`brief.py` is the single entry point: acquire → compute → publish (exactly once,
keyed by session) → render (text/HTML/JSON). Renderers are pure functions of the
frozen report. `daily_job.py` wraps it for cron; `morning.sh` wraps that for the
unattended run (pull → provenance → report → push). `deliver_report.py` sends the
frozen report; it never recomputes.

The 09:46 board is k-NN over 60-day 5-minute bars (`r945.py`); legs are sized
equal-risk, capped per side. The ledger (`ledger.py`) is append-only and is the
track record of record. The exact-window execution record lives in the Store
(`report_store.py`) keyed by session, immutable after first write.

## Day 95 integration

Codex day-95 work is merged: the provenance audit (`provenance.py`) runs before
the report and colours the exit code (exit 6 = published, but not the whole of
main); the attention collector (`build_social.py`) is checked, never run, from
the wrapper. The day-95 journal is `STRATEGY_day95.md`; its pre-registration is
`PREREGISTER_day95.md`. Risk-evidence (`risk_evidence.py`) computes clustered
hit-rate intervals and day-shape counts from the ledger for the report.

Unattended research tasks must pin the same reviewed main commit; fetch moving main for CSV record
imports only, never for executing unreviewed code during a scheduled run.

## Day-95b record integrity

`PREREGISTER_day95b.md` was committed before any outcome. The publication window is
now 09:46:00–09:49:59 ET (`execution.PUBLISH_WINDOW_MINUTES`); a late record is
labelled late (`publication_delay_sec`), and publish-once is unchanged — a late
rerun NEVER replaces a recorded board. An eligible session that records NOTHING
is the unrecorded-day class: no masking freeze, `NOT RECORDED — ` email subject,
`brief.py --publish` exits 7, morning.sh alarms (2026-09-09 went 1/4 unrecorded —
that gap is never retro-entered). Exit 6 remains main's provenance signal.
Record gaps are anchored on today and printed in the RECORD section; zero-pick
days write universe prints so they are distinguishable from missed publications.
H1 (vp skew) and H2 (tide-residualized features) are registered SHADOW studies —
no adoption from either. See `STRATEGY_day95b.md`.
