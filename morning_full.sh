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

# CLAUDE'S DESK (day-114) sits between the news refresh and the DeepSeek and
# Jev rankings, so every step before it leaves this much of the window free.
# Claude answers the SAME brief DeepSeek will get, and must answer BEFORE the
# other two are asked — that ordering is what makes the three independent.
# The seal refuses at 09:24, so DeepSeek always keeps its own slot after it.
CLAUDE_WINDOW=420
CLAUDE_DEADLINE=0924

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

    if budget="$(slice 600 $((660 + CLAUDE_WINDOW)))"; then
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

    # The evening job certifies the universe and commits it COMPRESSED
    # (data/biotech_snapshot.json is gitignored, so an evening build never
    # used to reach this container). Unpack it; the build below then skips.
    if [ -f data/biotech_snapshot.json.gz ]; then
        if gunzip -c data/biotech_snapshot.json.gz > data/biotech_snapshot.json.tmp 2>/dev/null; then
            mv data/biotech_snapshot.json.tmp data/biotech_snapshot.json
            log "  biotech universe: evening snapshot unpacked"
        else
            rm -f data/biotech_snapshot.json.tmp
            log "  biotech universe: evening snapshot UNREADABLE — rebuilding below"
        fi
    fi

    # Exits 2 on an incomplete universe, which is a real partial, not a crash.
    if budget="$(slice 900 $((540 + CLAUDE_WINDOW)))"; then
        # Built the EVENING BEFORE by the bridge session (1,005 names do not fit
        # a 25-minute window). This only rebuilds when that did not happen.
        timeout "$budget" python build_biotech.py --output data/biotech_snapshot.json \
            --skip-if-certified-within 20
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
    if budget="$(slice 900 $((360 + CLAUDE_WINDOW)))"; then
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

    # THE WIRE (day-118): the issuers' own press releases since the last
    # archived day, from newswire.ca's list. prepare_deepseek then puts each
    # pool name's releases FIRST in its staged headlines, so all three desks see
    # them. ~10-20s. A failure costs the releases, never the headlines or a desk.
    if budget="$(slice 60 $((240 + CLAUDE_WINDOW)))"; then
        timeout "$budget" python newswire.py --collect >>"$RB_STATE_DIR/newswire.log" 2>&1
        case $? in
            0) log "  wire releases: collected" ;;
            3) log "  wire releases: collected, some release pages failed (retried next run)" ;;
            *) log "  wire releases: NOT collected or incomplete — the desks see yesterday's archive"
               stage_faults+=("wire releases not collected") ;;
        esac
    else
        log "  wire releases: SKIPPED — an upstream step overran"
        stage_faults+=("wire releases skipped: staging budget exhausted")
    fi

    # Exits 2 when some names lack complete inputs. That is the ordinary
    # result, not an error: coverage is gated by contiguous session warm-up.
    if budget="$(slice 900 $((120 + CLAUDE_WINDOW)))"; then
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

    # FMP CONTEXT (day-125, PREREGISTER_day125_fmp.md). Analyst rating changes,
    # consensus, last/next earnings for every name in the brief, and today's
    # Canada/US releases — staged BEFORE the brief so all four models get the
    # same rows. ~28s measured over 77 names; a failure costs only these fields.
    if budget="$(slice 60 420)"; then
        if timeout "$budget" python fmp_context.py --stage --state-dir "$RB_STATE_DIR" \
                >>"$RB_STATE_DIR/fmp_context.log" 2>&1; then
            log "  FMP context: staged"
        else
            log "  FMP context: NOT staged — the brief carries no FMP fields (fmp_context.log)"
            stage_faults+=("FMP context not staged")
        fi
    else
        log "  FMP context: SKIPPED — too little left before the brief; no FMP fields today"
        stage_faults+=("FMP context skipped: staging budget exhausted")
    fi

    # CLAUDE'S DESK. Write the brief — the exact question and evidence DeepSeek
    # is about to get — then WAIT for Claude's sealed answer before asking
    # anyone else. The scheduled Routine is itself a Claude session: it reads
    # the brief, answers, and runs `claude_opportunities.py --seal`. If a
    # private Anthropic key is staged, the API answers instead. If nothing
    # answers by 09:24 the desk reads UNAVAILABLE and the morning goes on —
    # the wait can cost Claude's section, never DeepSeek's, Jev's or the board.
    if [ "$(minutes_now)" -lt "$CLAUDE_DEADLINE" ] && budget="$(slice 90 330)"; then
        timeout "$budget" python claude_opportunities.py --state-dir "$RB_STATE_DIR" --brief
        case $? in
            0) log "  Claude brief: written — waiting for Claude's sealed answer until ${CLAUDE_DEADLINE}"
               if [ -f "$RB_STATE_DIR/secrets/anthropic_api_key" ]; then
                   if timeout 150 python claude_opportunities.py --state-dir "$RB_STATE_DIR" --api; then
                       log "  Claude picks: answered through the API"
                   else
                       log "  Claude picks: API route FAILED — waiting for the session's answer"
                   fi
               fi
               until python claude_opportunities.py --state-dir "$RB_STATE_DIR" --sealed \
                     || [ "$(minutes_now)" -ge "$CLAUDE_DEADLINE" ]; do
                   sleep 10
               done
               if python claude_opportunities.py --state-dir "$RB_STATE_DIR" --sealed; then
                   log "  Claude picks: sealed"
               else
                   log "  Claude picks: NOT SEALED by ${CLAUDE_DEADLINE} — that section will read UNAVAILABLE"
                   stage_faults+=("Claude picks not sealed by ${CLAUDE_DEADLINE}")
               fi ;;
            2) log "  Claude brief: nothing to answer (no usable pool) — reason sealed"
               stage_faults+=("Claude brief: no usable candidate pool") ;;
            *) log "  Claude brief: FAILED — that section will read UNAVAILABLE"
               stage_faults+=("Claude brief not written") ;;
        esac
    else
        log "  Claude brief: SKIPPED — past ${CLAUDE_DEADLINE} or the window was eaten upstream."
        stage_faults+=("Claude brief skipped: past its deadline")
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

    # The FOURTH desk (owner, 2026-10-03): Gemini (gemini-3.8-flash), asked the
    # same question from the same rows as DeepSeek. ~2s over 89 names; it runs
    # last so the DeepSeek and Jev budgets are untouched.
    if budget="$(slice 120 0)"; then
        timeout "$budget" python gemini_opportunities.py --state-dir "$RB_STATE_DIR"
        case $? in
            0) log "  Gemini opportunities: staged" ;;
            3) log "  Gemini opportunities: REFUSED (past the pre-open cutoff)"
               stage_faults+=("Gemini ranking refused: past the cutoff") ;;
            *) log "  Gemini opportunities: FAILED — that section will read UNAVAILABLE"
               stage_faults+=("Gemini ranking not staged") ;;
        esac
    else
        log "  Gemini opportunities: SKIPPED — an upstream step ate the window."
        stage_faults+=("Gemini ranking skipped: staging budget exhausted")
    fi
fi

# ── 1b. BIOTECH CALLS (owner, 2026-09-28) ─────────────────────────────────
# A LONG/SHORT per reviewed catalyst event. Its horizon is the event window,
# months away, so it is not bound to the 09:30 cutoff and runs outside the
# staging budget. ~6s measured; a failure costs Part 2's call column only.
if timeout 150 python biotech_leans.py --state-dir "$RB_STATE_DIR" >/dev/null; then
    log "  biotech calls: staged and recorded"
else
    log "  biotech calls: NOT staged — Part 2 prints its events without a call"
    stage_faults+=("biotech calls not staged")
fi

# EXTRA SECTIONS (day-119): the gap signal's normal daily moves and today's
# post-earnings signals. Prior closes only, so staging after 09:30 is fine; a
# failure costs only its own section.
if timeout 120 python gap_signal.py --stage --state-dir "$RB_STATE_DIR" >/dev/null; then
    log "  gap signal: staged"
else
    log "  gap signal: NOT staged — Part 3 reads unavailable"
    stage_faults+=("gap signal not staged")
fi
if timeout 90 python debate.py --stage --state-dir "$RB_STATE_DIR" >/dev/null; then
    log "  debate: staged"
else
    log "  debate: NOT staged — Part 5 reads unavailable"
    stage_faults+=("debate not staged")
fi
if timeout 120 python pead.py --stage --state-dir "$RB_STATE_DIR" >/dev/null; then
    log "  post-earnings drift: staged"
else
    log "  post-earnings drift: NOT staged — Part 4 reads unavailable"
    stage_faults+=("post-earnings drift not staged")
fi

# ── 1b'. THE COUNCIL (day-124, PREREGISTER_day124_council.md) ────────────
# The four models deliberate on the Top 2: DeepSeek and Gemini ballot every
# proposed position, Claude (this session, from council_brief.txt) and Jev
# answer after reading them, then DeepSeek and Gemini cast final ballots.
# Claude's ballot is waited for until 09:27 at most. It must end by 09:34 so
# Part 6 keeps its window; without it the counted rule decides the Top 2.
council_left=$(( $(TZ=America/New_York date -d 'today 09:34:00' +%s) - $(date +%s) ))
if [ "$council_left" -gt 30 ]; then
    if timeout "$(( council_left < 900 ? council_left : 900 ))" python council.py --stage \
            --state-dir "$RB_STATE_DIR" >>"$RB_STATE_DIR/council.log" 2>&1; then
        log "  council: sat — the Top 2 is its decision (council.log)"
    else
        log "  council: did NOT sit — the counted rule decides the Top 2 (council.log)"
        stage_faults+=("council did not sit")
    fi
else
    log "  council: SKIPPED — too close to the open; the counted rule decides the Top 2"
    stage_faults+=("council skipped: too late")
fi

# ── 1c. PART 6, THE NEWS DESK (day-122) ───────────────────────────────────
# A model reads every liquid TSX name's overnight release. The window runs to
# 09:30, so this waits for it to close, then has until 09:43 — it can never
# delay publication. A failure costs Part 6 only.
while [ "$(minutes_now)" -lt 0931 ]; do
    log "holding for the overnight news window to close (now $(minutes_now))"
    sleep 60
done
news_left=$(( $(TZ=America/New_York date -d 'today 09:43:00' +%s) - $(date +%s) ))
if [ "$news_left" -gt 30 ]; then
    if timeout "$(( news_left < 300 ? news_left : 300 ))" python news_desk.py --stage \
            --state-dir "$RB_STATE_DIR" >>"$RB_STATE_DIR/news_desk.log" 2>&1; then
        log "  news desk: staged and recorded"
    else
        log "  news desk: NOT staged — Part 6 reads unavailable (news_desk.log)"
        stage_faults+=("news desk not staged")
    fi
else
    log "  news desk: SKIPPED — too close to publication"
    stage_faults+=("news desk skipped: too close to publication")
fi

# ── 2. HOLD until the publication window opens ─────────────────────────────
# The session must stay alive: the staged snapshot is on this filesystem and
# nowhere else. Poll rather than sleep in one block so the wait is visible in
# the log and a killed job is obvious.
while [ "$(minutes_now)" -lt "$PUBLISH_AT" ]; do
    log "holding for the publication window (now $(minutes_now), publish at ${PUBLISH_AT})"
    sleep 60
done

# ── 2b. STAGE THE YAHOO LOGIN before the quote window ─────────────────────
# prepare_yahoo_auth.py existed and NOTHING ran it, so every 09:46 quote check
# began cold: cookie bootstrap, crumb fetch, then the quote — three requests
# from a container that had just pulled a 130-name pool, daily bars, news and
# a biotech universe from the same provider. On 2026-09-22 the quote request
# came back 429 and all four legs ABSTAINED on "provider rate limit reached".
# Staged here, 09:46 makes ONE request. Failure is not fatal: the quote path
# still bootstraps on its own, exactly as before.
if auth_out="$(timeout 40 python prepare_yahoo_auth.py --state-dir "$RB_STATE_DIR" 2>&1)"; then
    log "  Yahoo login staged for 09:46"
else
    log "  Yahoo login NOT staged — 09:46 will bootstrap cold: ${auth_out:0:200}"
    stage_faults+=("Yahoo login not staged")
fi

# ── 3. PUBLISH ─────────────────────────────────────────────────────────────
log "handing over to morning.sh"
TZ=America/Toronto ./morning.sh
rc=$?

if [ ${#stage_faults[@]} -gt 0 ]; then
    log "staging faults this run: ${stage_faults[*]}"
fi
log "morning.sh exit ${rc}"
exit "$rc"
