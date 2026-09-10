#!/usr/bin/env bash
# install.sh — put the RB timers on THIS host, and prove they are right.
#
#   sudo deploy/install.sh --check     inspect only, changes nothing
#   sudo deploy/install.sh             install, enable, then verify
#
# WHY THIS EXISTS. The 2026-09-09 and 09-10 sessions went unrecorded because of
# two defects that lived in the unit files, not in the Python:
#
#   * rb-report.service ran daily_job.py DIRECTLY, so it published into the
#     state dir and emailed, and never pulled, never checked provenance and
#     never pushed a CSV. The record existed only on this host.
#   * rb-report.timer fired at 09:46:00, but the clock check happens AFTER
#     acquisition, so the run reached it past the window and published nothing.
#   * rb-biotech.service carried `ExecStart=-`, which tells systemd to IGNORE
#     the exit status, so bar_cache could fail every morning while the unit
#     went green.
#
# A hand-typed `cp` of six files at 08:00 is how those get half-applied. This
# does the whole thing and then CHECKS ITS OWN WORK, because an installer that
# reports success without verifying is the same class of bug as the `-`.
#
# It installs no credentials and reads none. Nothing here places an order.

set -uo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
UNIT_DIR=/etc/systemd/system
ENV_FILE=/etc/rb-report.env
TIMERS=(rb-prepare rb-biotech rb-social rb-options rb-report)
CHECK_ONLY=0
FAIL=0

for arg in "$@"; do
    case "$arg" in
        --check) CHECK_ONLY=1 ;;
        -h|--help) sed -n '2,20p' "$0"; exit 0 ;;
        *) echo "unknown argument: $arg" >&2; exit 2 ;;
    esac
done

say()  { printf '  %s\n' "$*"; }
ok()   { printf '  \033[32mOK\033[0m   %s\n' "$*"; }
bad()  { printf '  \033[31mFAIL\033[0m %s\n' "$*"; FAIL=1; }
warn() { printf '  \033[33mWARN\033[0m %s\n' "$*"; }

echo "RB deployment — repo $REPO"
echo

# ── preconditions ──────────────────────────────────────────────────────────
echo "PRECONDITIONS"
[ "$(id -u)" -eq 0 ] || { bad "must run as root (sudo)"; exit 1; }

if [ "$(ps -p 1 -o comm= 2>/dev/null)" != "systemd" ]; then
    bad "systemd is not PID 1 on this host — these units cannot run here."
    say "  This is the wrong machine, or a container. Run it on the box that"
    say "  actually sends your 09:46 email."
    exit 1
fi
ok "systemd is PID 1"

[ -f "$REPO/morning.sh" ] || { bad "no morning.sh in $REPO"; exit 1; }
[ -x "$REPO/morning.sh" ] || { bad "morning.sh is not executable"; exit 1; }
ok "morning.sh present and executable"

PY="$REPO/.venv/bin/python"
if [ -x "$PY" ]; then ok "interpreter $PY"
else bad "no interpreter at $PY — create the venv first"; fi

if [ -f "$ENV_FILE" ]; then
    perms="$(stat -c %a "$ENV_FILE")"
    [ "$perms" = 600 ] && ok "$ENV_FILE (mode $perms)" \
                       || warn "$ENV_FILE is mode $perms; should be 600"
    for key in RB_STATE_DIR RB_INTRADAY_CACHE_DIR RB_SMTP_USER RB_REPORT_TO; do
        grep -q "^${key}=" "$ENV_FILE" && ok "  $key set" \
                                       || bad "  $key MISSING from $ENV_FILE"
    done
else
    bad "$ENV_FILE missing — copy deploy/rb-report.env.example and fill it in"
fi

id rb-report >/dev/null 2>&1 && ok "user rb-report exists" \
                             || bad "user rb-report does not exist"
[ "$FAIL" -eq 0 ] || { echo; echo "PRECONDITIONS FAILED — nothing installed."; exit 1; }
echo

# ── the units themselves, before anything is copied ────────────────────────
echo "UNIT SANITY (from the repo, before install)"
for line in $(grep -h '^ExecStart' "$REPO"/deploy/*.service | sed 's/ .*//'); do
    case "$line" in
        ExecStart=-*|ExecStartPre=-*)
            bad "a unit ignores its exit status: $line" ;;
    esac
done
[ "$FAIL" -eq 0 ] && ok "no ExecStart/ExecStartPre ignores its exit status"

exec_line="$(grep -h '^ExecStart=' "$REPO/deploy/rb-report.service")"
case "$exec_line" in
    *morning.sh) ok "rb-report runs morning.sh (pull, publish, send, push)" ;;
    *) bad "rb-report ExecStart is not morning.sh: $exec_line" ;;
esac

declare -A MINUTE
for t in "${TIMERS[@]}"; do
    # Extract HH:MM specifically. `sed 's/.* //'` takes the LAST field, which
    # is the TIMEZONE — every timer then "clashes" at America/New_York. Found
    # by running this, not by reading it.
    when="$(grep -h '^OnCalendar=' "$REPO/deploy/$t.timer" \
            | grep -oE '[0-9]{2}:[0-9]{2}:[0-9]{2}' | head -1 | cut -c1-5)"
    if [ -z "$when" ]; then
        warn "$t.timer has no HH:MM:SS OnCalendar — not checked for clashes"
        continue
    fi
    if [ -n "${MINUTE[$when]:-}" ]; then
        bad "$t and ${MINUTE[$when]} both fire at $when — provider rate limits"
    fi
    MINUTE[$when]="$t"
done
[ "$FAIL" -eq 0 ] && ok "no two timers share a minute"
echo

# ── install ────────────────────────────────────────────────────────────────
if [ "$CHECK_ONLY" -eq 0 ]; then
    echo "INSTALLING"
    changed=0
    for f in "$REPO"/deploy/*.service "$REPO"/deploy/*.timer; do
        base="$(basename "$f")"
        if ! cmp -s "$f" "$UNIT_DIR/$base"; then
            install -m 0644 "$f" "$UNIT_DIR/$base" && say "updated $base"
            changed=$((changed + 1))
        fi
    done
    [ "$changed" -eq 0 ] && ok "units already current" \
                         || ok "$changed unit file(s) updated"
    systemctl daemon-reload && ok "daemon-reload"
    for t in "${TIMERS[@]}"; do
        systemctl enable --now "$t.timer" >/dev/null 2>&1 \
            && ok "enabled $t.timer" || bad "could not enable $t.timer"
    done
    echo
fi

# ── verify what is ACTUALLY loaded, not what we think we wrote ─────────────
echo "VERIFICATION (reading systemd, not the repo)"
for t in "${TIMERS[@]}"; do
    if ! systemctl is-enabled "$t.timer" >/dev/null 2>&1; then
        bad "$t.timer is not enabled"; continue
    fi
    if ! systemctl is-active "$t.timer" >/dev/null 2>&1; then
        bad "$t.timer is enabled but not active"; continue
    fi
    next="$(systemctl show -p NextElapseUSecRealtime --value "$t.timer" 2>/dev/null)"
    ok "$t.timer active — next: ${next:-unknown}"
done

loaded="$(systemctl cat rb-report.service 2>/dev/null | grep '^ExecStart=')"
case "$loaded" in
    *morning.sh) ok "loaded rb-report.service runs morning.sh" ;;
    "") bad "rb-report.service is not loaded" ;;
    *) bad "LOADED unit still bypasses the wrapper: $loaded" ;;
esac

echo
if [ "$FAIL" -eq 0 ]; then
    echo "DEPLOYMENT OK."
    echo "Tomorrow: journalctl -u rb-prepare -u rb-report --since 08:00"
    exit 0
fi
echo "DEPLOYMENT NOT CLEAN — see FAIL lines above. Fix before the next open."
exit 1
