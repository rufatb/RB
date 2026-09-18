#!/usr/bin/env bash
# morning_full.sh — stage the pre-open inputs, then publish. ONE session.
#
# WHY THIS EXISTS. Two hard clocks sit 41 minutes apart and neither can move:
#
#   * prepare_deepseek.py and bar_cache.py REFUSE at or after 09:30 ET. They
#     describe the pre-open state; staging them after the bell would fold the
#     market's reaction to the open into evidence about the open.
#   * wait_for_publication.py REFUSES to wait more than 120 seconds
#     ("start publication preparation at or after 09:44 ET"), so morning.sh
#     cannot be started early and left to idle into the window.
#
# A single `morning.sh` invocation therefore cannot do both. Running it at
# 09:05 raises on the 120-second guard and exits 1; that is exactly what
# happened on 2026-09-17 — the scheduled run fired at 09:05, staged its inputs,
# died at 09:12 with nothing published, and the DeepSeek snapshot went with the
# container. The factor section then read UNAVAILABLE for the sixth day.
#
# The two clocks are both right. What was missing is the thing that sits
# between them: stage early, hold the session, then publish in the window.
#
# STATE IS NOT PORTABLE BETWEEN CONTAINERS. The staged snapshot lives in
# $RB_STATE_DIR and dies with the machine, so the staging and the publication
# must happen in the SAME process tree. That is the whole reason this is one
# script and not two scheduled jobs.
#
# Nothing here places, sizes or cancels an order.

set -uo pipefail
cd "$(dirname "$0")" || exit 1

: "${RB_STATE_DIR:=.rb-state}"
export RB_STATE_DIR

# STAGE THE CACHE AND THEN POINT AT IT. `bar_cache.py` writes into
# $RB_STATE_DIR/intraday_cache below, but `morning.sh` looks for the directory
# in RB_INTRADAY_CACHE_DIR and nothing ever set it — so every morning staged a
# cache and then ignored it, and the board reported "cache DEGRADED: 21 names
# acquired live (no cache directory configured)" while the cache sat beside it.
# That cost latency, never the board (day-103), but it was a silent no-op.
: "${RB_INTRADAY_CACHE_DIR:=$RB_STATE_DIR/intraday_cache}"
export RB_INTRADAY_CACHE_DIR

log() { printf '[%s] %s\n' "$(TZ=America/New_York date '+%F %H:%M:%S ET')" "$*"; }
minutes_now() { TZ=America/New_York date '+%H%M'; }

STAGE_DEADLINE=0930   # prepare_deepseek / bar_cache refuse at or after this
PUBLISH_AT=0944       # morning.sh's own guard allows a wait from here

# ── 1. STAGE, while it is still permitted ──────────────────────────────────
# Every staging step is OPTIONAL to the board. A failure here costs that
# section and is reported; it never stops the publication (house rule 1 says
# count and report, not swallow — and never that a shadow input may veto the
# morning). Each is bounded so a hung provider cannot eat the window.
stage_faults=()

# THE CREDENTIAL DOES NOT SURVIVE A CONTAINER. `.rb-state/` is gitignored
# (.gitignore:32), so a fresh clone has no key and no model file, and both
# DeepSeek sections would read UNAVAILABLE against a healthy account. Say so
# HERE, at the top of the log, rather than fifteen minutes later inside a
# provider error — the remedy takes ten seconds and only before the open.
if [ -z "${DEEPSEEK_API_KEY:-}" ] && [ ! -f "$RB_STATE_DIR/secrets/deepseek_api_key" ]; then
    log "NO DEEPSEEK CREDENTIAL — both model sections will read UNAVAILABLE."
    log "  Remedy: export DEEPSEEK_API_KEY, or write it to"
    log "  \$RB_STATE_DIR/secrets/deepseek_api_key (mode 0600), before staging."
    stage_faults+=("no DeepSeek credential staged")
fi

if [ "$(minutes_now)" -ge "$STAGE_DEADLINE" ]; then
    log "PAST ${STAGE_DEADLINE} ET — staging skipped; the factor and cache sections"
    log "  will read UNAVAILABLE. This is the guard working, not a fault: staged"
    log "  after the open they would describe the open."
    stage_faults+=("staging skipped: started after ${STAGE_DEADLINE} ET")
else
    log "staging pre-open inputs"

    if timeout 600 python bar_cache.py --directory "$RB_STATE_DIR/intraday_cache"; then
        log "  intraday cache: staged"
    else
        log "  intraday cache: FAILED (exit $?) — acquisition falls back to live"
        stage_faults+=("intraday cache not staged")
    fi

    # Exits 2 on an incomplete universe, which is a real partial, not a crash.
    timeout 900 python build_biotech.py --output data/biotech_snapshot.json
    case $? in
        0) log "  biotech universe: complete" ;;
        2) log "  biotech universe: PARTIAL (provider limit) — monitor stays uncertified"
           stage_faults+=("biotech universe partial") ;;
        *) log "  biotech universe: FAILED — Part 2 will be unavailable"
           stage_faults+=("biotech universe failed") ;;
    esac

    # THE RESEARCH POOL. This writes `deepseek_candidates.json`, the 130-name
    # pool with prepared technicals, and NOTHING ELSE WRITES IT. It was never
    # in this script, so no scheduled run has ever staged it: on 2026-09-18 the
    # opportunities section read "The candidate pool has not been staged
    # (FileNotFoundError)" on a healthy account, and the factor layer has been
    # quietly working off the 21-name CONFIGURED universe rather than the pool
    # it is documented to use. It must precede the news refresh, so headlines
    # are fetched for the pool's names and not just the baseline twenty-one.
    # Its own budget is already clamped to the time remaining before 09:30.
    timeout 900 python prepare_factor_pool.py --state-dir "$RB_STATE_DIR"
    case $? in
        0) log "  factor pool: staged" ;;
        *) log "  factor pool: FAILED or PARTIAL — the opportunity ranking falls back"
           log "    to the configured universe, or reads UNAVAILABLE"
           stage_faults+=("factor research pool not staged") ;;
    esac

    # Exits 2 when some names lack complete inputs. That is the ordinary
    # result, not an error: coverage is gated by contiguous session warm-up.
    timeout 900 python prepare_deepseek.py --state-dir "$RB_STATE_DIR" --refresh-public-inputs
    case $? in
        0) log "  DeepSeek factors: staged, full coverage" ;;
        2) log "  DeepSeek factors: staged, PARTIAL coverage" ;;
        *) log "  DeepSeek factors: FAILED — the factor section will read UNAVAILABLE"
           stage_faults+=("DeepSeek snapshot not staged") ;;
    esac

    # The model's OWN top-2 per side. A separate question from the factor
    # layer's "is there sentiment here", and a separate section. It is a
    # reasoning model: measured at ~54s over 39 names, which is why it is
    # staged here and can never sit inside the 09:46 publication window.
    timeout 300 python deepseek_opportunities.py --state-dir "$RB_STATE_DIR"
    case $? in
        0) log "  DeepSeek opportunities: staged" ;;
        *) log "  DeepSeek opportunities: FAILED — that section will read UNAVAILABLE"
           stage_faults+=("DeepSeek opportunity ranking not staged") ;;
    esac
fi

# ── 2. HOLD until the publication window opens ─────────────────────────────
# The session must stay alive: the staged snapshot is on this filesystem and
# nowhere else. Poll rather than sleep in one block so the wait is visible in
# the log and a killed job is obvious.
while [ "$(minutes_now)" -lt "$PUBLISH_AT" ]; do
    log "holding for the publication window (now $(minutes_now), publish at ${PUBLISH_AT})"
    sleep 60
done

# ── 3. PUBLISH ─────────────────────────────────────────────────────────────
log "handing over to morning.sh"
TZ=America/Toronto ./morning.sh
rc=$?

if [ ${#stage_faults[@]} -gt 0 ]; then
    log "staging faults this run: ${stage_faults[*]}"
fi
log "morning.sh exit ${rc}"
exit "$rc"
