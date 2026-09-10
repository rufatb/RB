#!/usr/bin/env bash
# morning.sh — the unattended 09:46 run.
#
# WHY THIS EXISTS AND NOT JUST `python brief.py`. The report WRITES the day's
# permanent record: ledger rows, universe prints, the advice row. Running it
# without pushing leaves that record on one machine only — which is exactly the
# failure that stranded 2026-09-08 on a single branch and would have lost the
# session had it not been caught. An automated run that does not push is an
# automated way to fork the record.
#
# ORDER MATTERS: pull, run, push. Pulling first means the run sees every other
# machine's record; pushing last means this machine's record reaches them.
#
# EXIT CODES, so cron can tell "nothing to do" from "broken":
#   0  ran and published (or correctly re-read an already-published board)
#   3  not a trading day / market shut — expected, not an error
#   4  the engine REFUSED on an integrity guard (clock, feed, coverage)
#   5  ran but MISSED THE PUBLICATION WINDOW — no board recorded
#   6  PUBLISHED, but provenance was not clean — the record is safe and the
#      run used code that is not the whole of main. Investigate same day.
#   1  something actually failed
#
# --publish IS REQUIRED. `brief.py` alone is a preview and writes nothing; a
# wrapper that omitted the flag would run cleanly every morning, exit 0, and
# record nothing at all. That is the silent failure this file exists to avoid.
#
# THE WINDOW IS 60 SECONDS: execution.clock_status marks a run LATE at 09:47:00
# and the check happens AFTER acquisition, not at process start. So the job
# must be scheduled early enough that fetching 21 names FINISHES inside the
# 09:46 minute. Starting at 09:46:00 is already too late on a slow feed.
#
# Nothing here places, sizes or cancels an order. It runs a read-only report
# and commits the record of what that report said.

set -uo pipefail
cd "$(dirname "$0")" || exit 1

log() { printf '[%s] %s\n' "$(TZ=America/Toronto date '+%F %H:%M:%S %Z')" "$*"; }

# ── 1. SYNC FIRST (house rule 6) ───────────────────────────────────────────
log "pulling"
if ! git pull --ff-only 2>&1 | tail -2; then
    log "PULL FAILED — refusing to run on a possibly stale record."
    log "  A board published from a stale clone can duplicate or contradict"
    log "  rows another machine already wrote. Resolve by hand, then re-run."
    exit 1
fi

# ── 1b. AM I RUNNING EVERYTHING THAT EXISTS? ───────────────────────────────
# The pull above proves this clone matches origin/main. It says NOTHING about
# whether main is the whole of the work: `clock_vs_data` sat finished on
# another branch for five weeks and every morning ran without it, and
# build_social.py -- a FORWARD collector, whose lost days cannot be back-filled
# -- sat unmerged for two. Both looked perfect to `git status` and to the test
# suite, which passes fine on an incomplete main.
#
# This DOES NOT BLOCK the report. A day's record is worth more than a tidy
# branch list, and refusing to publish over an unmerged research branch would
# trade a real loss for a bookkeeping one. It warns, and it colours the exit
# code so the cron mail cannot be mistaken for an ordinary morning.
provenance_clean=1
if prov="$(python provenance.py 2>&1)"; then
    log "provenance: clean — main is everything, and this is main"
else
    provenance_clean=0
    log "PROVENANCE NOT CLEAN — the run below is not everything that exists:"
    printf '%s\n' "$prov" | sed 's/^/    /'
fi

# ── 2. TRADING DAY? ────────────────────────────────────────────────────────
# NOTE: capture the status DIRECTLY. Writing `if ! python -c ...; then rc=$?`
# captures the status of the NEGATION -- always 1 -- so the script's own
# exit 3 never survives and every holiday reports as a hard failure. Found by
# running it, not by reading it.
python -c "
import datetime as dt, sys
import dashboard as D
sys.exit(0 if D.is_trading_day(dt.date.today()) else 3)
" 2>/dev/null
rc=$?
if [ "$rc" -eq 3 ]; then
    log "not a trading day — nothing to run. This is not an error."
    exit 3
elif [ "$rc" -ne 0 ]; then
    log "could not determine whether today is a trading day (exit $rc) —"
    log "  treating as an error rather than assuming the market is open."
    exit 1
fi

# ── 3. THE REPORT ──────────────────────────────────────────────────────────
log "running the report"
out="$(TZ=America/Toronto python brief.py --publish 2>&1)"; rc=$?
printf '%s\n' "$out"

if [ $rc -ne 0 ]; then
    log "brief.py exited $rc"
    exit 1
fi

# An integrity refusal is a SUCCESSFUL run that correctly declined to publish.
# It must not look like a normal morning to whoever reads the cron mail.
if printf '%s' "$out" | grep -qiE "REFUSING TO PUBLISH|CLOCK IS BEHIND|FEED IS STALE|NOTHING PUBLISHED|MARKET CLOSED"; then
    log "the engine REFUSED to publish on an integrity guard — see the output above."
    log "  No orders, no ledger rows. Fix the cause and re-run; do not override."
    exit 4
fi

# MISSED THE WINDOW. A LATE run renders a full page and publishes NOTHING, so
# without this it reads like an ordinary morning while the day goes unrecorded.
if printf '%s' "$out" | grep -qiE "LATE — informational|entry window missed"; then
    log "MISSED THE 09:46 PUBLICATION WINDOW — the page above is informational."
    log "  No board was recorded for today. Schedule the job EARLIER: the clock"
    log "  is checked after acquisition, so the fetch must finish before 09:47."
    exit 5
fi

# ── 4. PUSH THE RECORD ─────────────────────────────────────────────────────
# Only the record. Never code — an unattended job must not publish edits
# nobody has read.
# ── 4b. DID THE 09:20 ATTENTION COLLECTOR ACTUALLY FIRE? ───────────────────
# Checked here, NOT run here. build_social.py is registered to collect at
# 09:20 ET, pre-open, because a snapshot taken after 09:46 contains the
# market's reaction to the open — running it from this wrapper would be
# look-ahead wearing a scheduling convenience as a disguise, and every row so
# collected is marked decision_usable:false for exactly that reason.
#
# Forward collection cannot be back-filled. A missed morning is a permanently
# missing session, so silence is the wrong response to a missing snapshot.
today_snap="data/social/$(TZ=America/Toronto date +%F).json"
if [ -f "$today_snap" ]; then
    if ! grep -q '"decision_usable": true' "$today_snap"; then
        log "attention snapshot exists but was collected AFTER 09:46 — it is"
        log "  marked unusable as a feature. Check the rb-social timer."
    fi
else
    log "NO ATTENTION SNAPSHOT for today ($today_snap) — the 09:20 collector"
    log "  did not run. This session cannot be recovered later; forward"
    log "  collection has no history endpoint. Check rb-social.timer."
fi

git add -- ledger.csv universe_prints.csv positions.csv data/advice.csv 2>/dev/null
# Only TODAY'S snapshot, by exact path — never the directory. A directory
# stage would carry anything that happened to be sitting in it, which is the
# same "publish edits nobody has read" failure this job stages narrowly to
# avoid. The snapshot is a record: forward collection cannot re-derive it.
git add -- "$today_snap" 2>/dev/null
if git diff --cached --quiet; then
    log "no new record rows (already published today) — nothing to push"
    [ "$provenance_clean" -eq 1 ] || exit 6
    exit 0
fi

git commit -q -m "record: $(TZ=America/Toronto date +%F) board (automated 09:46 run)" || {
    log "COMMIT FAILED — the record is on this machine only. Push by hand."; exit 1; }

for attempt in 1 2 3 4; do
    if git push -q origin HEAD 2>&1; then
        log "record pushed"
        [ "$provenance_clean" -eq 1 ] || exit 6
        exit 0
    fi
    log "push failed (attempt $attempt) — retrying"
    sleep $((2 ** attempt))
done

log "PUSH FAILED after 4 attempts. The record is committed LOCALLY but this"
log "  machine is now the only copy. Push by hand before running anywhere else."
exit 1
