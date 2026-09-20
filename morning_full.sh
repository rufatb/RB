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

# ── ONE BUDGET, SHARED ─────────────────────────────────────────────────────
# The per-step timeouts below are each defensible on their own and they sum to
# SIXTY-THREE MINUTES inside a TWENTY-FIVE minute window (09:05 → 09:30). They
# were written as "a hung provider must not eat the window", but they were
# never reconciled against each other, so a slow cache and a slow biotech
# harvest can legitimately consume the entire window and the two steps the
# owner actually reads — the DeepSeek and Jev rankings — would then find the
# 09:30 cutoff already passed and REFUSE. The refusal would be correct, the
# sections would read UNAVAILABLE, and nothing would say the cause was an
# upstream overrun rather than a provider outage.
#
# So every step is clamped to the time actually left, minus a reserve for the
# steps that still have to run after it. `reserve` numbers come from measured
# runs (day-111b: the DeepSeek payload is ~27.5s over 116 names, Jev ~1.0s),
# with headroom. A step that would get no usable slice is SKIPPED and named,
# rather than started and killed halfway through writing its snapshot.
seconds_left() {
    printf '%s' $(( $(TZ=America/New_York date -d 'today 09:29:30' +%s) \
                    - $(TZ=America/New_York date +%s) ))
}

# $1 = the step's own ceiling, $2 = seconds the downstream steps still need.
# Prints the timeout to use, or FAILS (prints nothing) when too little is left
# to be worth starting. The caller must skip and name it on failure: `timeout 0`
# means NO TIMEOUT in GNU coreutils, so a budget that has run out must never be
# passed through as a number.
slice() {
    local left=$(( $(seconds_left) - $2 ))
    [ "$left" -gt "$1" ] && left=$1
    [ "$left" -lt "$MIN_SLICE" ] && return 1
    printf '%s' "$left"
}
MIN_SLICE=15

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

# THE EMAIL HAS NEVER BEEN SENT, and this is where that becomes visible while
# there is still time to act. `morning.sh` has carried a complete SMTP send
# since day-97; a scheduled container has never had the credential, so the send
# was skipped silently every morning and the owner's inbox stayed empty against
# a healthy, on-time, correctly published run. Say it at the TOP of the log,
# beside the DeepSeek check, for the same reason: the remedy takes a minute and
# only helps before the publication window.
if ! smtp_out="$(python smtp_credential.py --state-dir "$RB_STATE_DIR" 2>&1)"; then
    log "NO EMAIL CREDENTIAL — the report will publish but WILL NOT be emailed."
    printf '%s\n' "$smtp_out" | sed 's/^/    /'
    stage_faults+=("no SMTP credential: the report will not be emailed")
else
    log "email delivery: configured"
fi

if [ "$(minutes_now)" -ge "$STAGE_DEADLINE" ]; then
    log "PAST ${STAGE_DEADLINE} ET — staging skipped; the factor and cache sections"
    log "  will read UNAVAILABLE. This is the guard working, not a fault: staged"
    log "  after the open they would describe the open."
    stage_faults+=("staging skipped: started after ${STAGE_DEADLINE} ET")
else
    log "staging pre-open inputs"

    if budget="$(slice 600 660)"; then
        if timeout "$budget" python bar_cache.py --directory "$RB_STATE_DIR/intraday_cache"; then
            log "  intraday cache: staged"
        else
            log "  intraday cache: FAILED (exit $?) — acquisition falls back to live"
            stage_faults+=("intraday cache not staged")
        fi
    else
        log "  intraday cache: SKIPPED — too little left before 09:30 to start it."
        log "    Acquisition falls back to live; that costs latency, never the board."
        stage_faults+=("intraday cache skipped: staging budget exhausted")
    fi

    # Exits 2 on an incomplete universe, which is a real partial, not a crash.
    if budget="$(slice 900 540)"; then
        timeout "$budget" python build_biotech.py --output data/biotech_snapshot.json
        case $? in
            0) log "  biotech universe: complete" ;;
            2) log "  biotech universe: PARTIAL (provider limit) — monitor stays uncertified"
               stage_faults+=("biotech universe partial") ;;
            *) log "  biotech universe: FAILED — Part 2 will be unavailable"
               stage_faults+=("biotech universe failed") ;;
        esac
    else
        log "  biotech universe: SKIPPED — an upstream step overran. Part 2 will be"
        log "    unavailable and the pool loses its US biotech names."
        stage_faults+=("biotech universe skipped: staging budget exhausted")
    fi

    # THE RESEARCH POOL. This writes `deepseek_candidates.json`, the 130-name
    # pool with prepared technicals, and NOTHING ELSE WRITES IT. It was never
    # in this script, so no scheduled run has ever staged it: on 2026-09-18 the
    # opportunities section read "The candidate pool has not been staged
    # (FileNotFoundError)" on a healthy account, and the factor layer has been
    # quietly working off the 21-name CONFIGURED universe rather than the pool
    # it is documented to use. It must precede the news refresh, so headlines
    # are fetched for the pool's names and not just the baseline twenty-one.
    # Its own budget is already clamped to the time remaining before 09:30.
    if budget="$(slice 900 360)"; then
        timeout "$budget" python prepare_factor_pool.py --state-dir "$RB_STATE_DIR"
        case $? in
            0) log "  factor pool: staged" ;;
            3) log "  factor pool: REFUSED (past the pre-open cutoff) — correct, not a crash"
               stage_faults+=("factor pool refused: past the cutoff") ;;
            *) log "  factor pool: FAILED or PARTIAL — the opportunity ranking falls back"
               log "    to the configured universe, or reads UNAVAILABLE"
               stage_faults+=("factor research pool not staged") ;;
        esac
    else
        log "  factor pool: SKIPPED — an upstream step overran. Both model sections"
        log "    fall back to the 21-name configured universe or read UNAVAILABLE."
        stage_faults+=("factor pool skipped: staging budget exhausted")
    fi

    # Exits 2 when some names lack complete inputs. That is the ordinary
    # result, not an error: coverage is gated by contiguous session warm-up.
    if budget="$(slice 900 120)"; then
        timeout "$budget" python prepare_deepseek.py --state-dir "$RB_STATE_DIR" --refresh-public-inputs
        case $? in
            0) log "  DeepSeek factors: staged, full coverage" ;;
            2) log "  DeepSeek factors: staged, PARTIAL coverage" ;;
            *) log "  DeepSeek factors: FAILED — the factor section will read UNAVAILABLE"
               stage_faults+=("DeepSeek snapshot not staged") ;;
        esac
    else
        log "  DeepSeek factors: SKIPPED — an upstream step overran. The factor"
        log "    section will read UNAVAILABLE and the rankings lose their headlines."
        stage_faults+=("DeepSeek snapshot skipped: staging budget exhausted")
    fi

    # The model's OWN top-2 per side. A separate question from the factor
    # layer's "is there sentiment here", and a separate section. It is a
    # reasoning model: measured at ~54s over 39 names, which is why it is
    # staged here and can never sit inside the 09:46 publication window.
    if budget="$(slice 300 20)"; then
        timeout "$budget" python deepseek_opportunities.py --state-dir "$RB_STATE_DIR"
        case $? in
            0) log "  DeepSeek opportunities: staged" ;;
            3) log "  DeepSeek opportunities: REFUSED (past the pre-open cutoff)"
               stage_faults+=("DeepSeek ranking refused: past the cutoff") ;;
            *) log "  DeepSeek opportunities: FAILED — that section will read UNAVAILABLE"
               stage_faults+=("DeepSeek opportunity ranking not staged") ;;
        esac
    else
        log "  DeepSeek opportunities: SKIPPED — an upstream step ate the window."
        log "    This is one of the two sections the owner reads; say so in the summary."
        stage_faults+=("DeepSeek ranking skipped: staging budget exhausted")
    fi

    # The SECOND opinion. Jev is a decisions model on OpenRouter, reached at
    # /api/alpha/decisions — NOT /chat/completions, which rejects it outright.
    # It answers both sides in one request in well under a second, so unlike
    # the DeepSeek call it is cheap; it is staged here anyway because the same
    # pre-open contract applies to any opinion formed from these inputs.
    if budget="$(slice 180 5)"; then
        timeout "$budget" python jev_opportunities.py --state-dir "$RB_STATE_DIR"
        case $? in
            0) log "  Jev opportunities: staged" ;;
            3) log "  Jev opportunities: REFUSED (past the pre-open cutoff)"
               stage_faults+=("Jev ranking refused: past the cutoff") ;;
            *) log "  Jev opportunities: FAILED — that section will read UNAVAILABLE"
               stage_faults+=("Jev ranking not staged") ;;
        esac
    else
        log "  Jev opportunities: SKIPPED — an upstream step ate the window."
        log "    Measured at ~1.0s over 116 names, so this only happens when the"
        log "    budget was already gone before it was reached."
        stage_faults+=("Jev ranking skipped: staging budget exhausted")
    fi
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
