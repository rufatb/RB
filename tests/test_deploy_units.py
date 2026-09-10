"""The systemd units — where two silent failures actually lived.

Day-97. Emails kept arriving while ledger.csv, universe_prints.csv and
data/advice.csv stopped at 2026-09-08. Two sessions went unrecorded and neither
the engine nor the test suite could have noticed: the defects were in the unit
files, which nothing tested.
"""
import datetime as dt
import os
import re

DEPLOY = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                      "deploy")


def unit(name):
    return open(os.path.join(DEPLOY, name)).read()


def directives(name):
    """The unit with comments stripped.

    Assertions about what a unit DOES must read its directives, not the
    comments explaining why a directive was removed — a test that greps the
    whole file fires on its own explanation. The same trap as morning.sh's
    `code()` helper."""
    return "\n".join(l for l in unit(name).splitlines()
                      if not l.lstrip().startswith("#"))


def test_the_report_timer_starts_before_the_publication_minute():
    """THE BUG. execution.clock_status marks a run LATE at 09:47:00 and checks
    AFTER acquisition. Acquisition budgets are 22s + 10s, and the pull and
    provenance check now run first. A timer firing AT 09:46:00 reaches the
    clock check past the window on a slow feed and publishes nothing while
    looking like an ordinary morning."""
    m = re.search(r"OnCalendar=.*?(\d{2}):(\d{2}):(\d{2})", unit("rb-report.timer"))
    assert m, "no OnCalendar time in the report timer"
    start = dt.time(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    assert start < dt.time(9, 46), \
        f"timer starts at {start}; acquisition must FINISH inside 09:46"
    # ...but not so early that it publishes for the wrong session.
    assert start >= dt.time(9, 40)


def test_the_report_timer_runs_on_weekdays_in_eastern_time():
    t = unit("rb-report.timer")
    assert "Mon..Fri" in t
    assert "America/New_York" in t, "a UTC timer drifts an hour twice a year"


def test_the_timer_does_not_randomise_its_start():
    """RandomizedDelaySec would scatter the start across the very minute the
    run has to finish inside."""
    t = unit("rb-report.timer")
    assert "RandomizedDelaySec=0" in t
    assert "AccuracySec=1s" in t


def test_a_missed_boot_does_not_fire_a_stale_report():
    """Persistent=true would publish a 'morning' board at whatever hour the
    machine came back up."""
    assert "Persistent=false" in unit("rb-report.timer")


def test_the_service_runs_the_wrapper_not_the_job_directly():
    """THE OTHER BUG. The unit called daily_job.py straight, which publishes
    into the state dir and emails -- and never pulls, never checks provenance,
    and NEVER PUSHES THE RECORD. That is why the CSVs stopped while the emails
    continued."""
    s = unit("rb-report.service")
    exec_line = [l for l in s.splitlines() if l.startswith("ExecStart=")][0]
    assert exec_line.endswith("morning.sh"), exec_line
    assert "daily_job.py" not in exec_line


def test_the_service_has_a_timeout_that_covers_the_whole_wrapper():
    s = unit("rb-report.service")
    m = re.search(r"TimeoutStartSec=(\d+)", s)
    assert m and int(m.group(1)) >= 120, \
        "pull + provenance + acquisition + send + push needs more than 65s"


def test_the_service_does_not_run_as_root_and_keeps_umask_private():
    s = unit("rb-report.service")
    assert "User=rb-report" in s and "NoNewPrivileges=true" in s
    assert "UMask=0077" in s


def test_no_unit_file_contains_a_credential():
    """Credentials live in EnvironmentFile, mode 0600, outside git."""
    for name in os.listdir(DEPLOY):
        if name.endswith(".example"):
            continue
        body = unit(name)
        assert "EnvironmentFile" in body or "PASSWORD" not in body
        assert not re.search(r"[0-9a-f]{12,}\.[0-9]{6,}", body), \
            f"{name} looks like it embeds an API key"


def test_the_env_example_carries_no_real_secret():
    e = unit("rb-report.env.example")
    assert "replace-with" in e or "your-account@example.com" in e
    assert not re.search(r"[0-9a-f]{12,}\.[0-9]{6,}", e)


# ── day-97: the 22-second timeout had a scheduling cause ───────────────────

def test_a_unit_actually_stages_the_intraday_history_cache():
    """THE CAUSE OF THE EMPTY 2026-09-10 EMAIL. bar_cache.py could always
    stage the 60-day 5-minute history and preflight.py always CHECKED for it,
    but no unit ever RAN it. So the 09:46 job fetched the whole universe live
    inside a 22s budget and reported TimeoutExpired after exactly 22.0s, with
    "Freshly evaluated names: 0" in the inbox. Staged pre-open it takes 5.8s."""
    s = unit("rb-prepare.service")
    assert "bar_cache.py" in s
    assert "RB_INTRADAY_CACHE_DIR" in s


def test_the_cache_is_staged_before_the_market_opens():
    """bar_cache refuses to run at or after 09:30 -- it stages the PRIOR
    session's bars -- so a timer at 09:4x would raise every single morning."""
    m = re.search(r"OnCalendar=.*?(\d{2}):(\d{2}):(\d{2})", unit("rb-prepare.timer"))
    start = dt.time(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    assert start < dt.time(9, 30), f"bar_cache refuses to run at {start}"


def test_no_two_market_data_jobs_fire_in_the_same_minute():
    """Two jobs hitting the same rate-limited provider at once is how
    "YFRateLimitError: Too Many Requests" happens, and then BOTH fail rather
    than one. rb-options sat on 09:45 when the report moved there."""
    times = {}
    for name in os.listdir(DEPLOY):
        if not name.endswith(".timer"):
            continue
        m = re.search(r"^OnCalendar=.*?(\d{2}):(\d{2}):\d{2}", unit(name), re.M)
        if m:
            times.setdefault(f"{m.group(1)}:{m.group(2)}", []).append(name)
    clashes = {k: v for k, v in times.items() if len(v) > 1}
    assert not clashes, f"timers share a minute: {clashes}"


def test_the_report_still_starts_after_the_cache_job():
    def at(name):
        m = re.search(r"OnCalendar=.*?(\d{2}):(\d{2}):(\d{2})", unit(name))
        return dt.time(*(int(g) for g in m.groups()))
    assert at("rb-prepare.timer") < at("rb-report.timer")


# ── day-97: systemd's "-" prefix is a silent except: pass ──────────────────

def test_no_unit_ignores_the_exit_status_of_work_that_must_succeed():
    """`ExecStart=-...` tells systemd to IGNORE the exit status. rb-biotech
    carried it on BOTH bar_cache (exits 2 on an incomplete universe) and
    build_biotech (exits 2 the same way), so the unit reported success while
    staging nothing. That is house rule 1 -- "never swallow an exception
    silently" -- violated one level below the Python.

    A "-" is allowed only on genuinely advisory steps, and only ExecStopPost
    ones, whose job is to record state after the fact."""
    for name in os.listdir(DEPLOY):
        if not name.endswith(".service"):
            continue
        for line in directives(name).splitlines():
            if line.startswith(("ExecStart=", "ExecStartPre=")):
                assert not line.split("=", 1)[1].lstrip().startswith("-"), \
                    f"{name}: {line} ignores its exit status"


def test_readiness_is_recorded_even_when_the_build_fails():
    """ExecStartPost does not run when ExecStart fails -- and that is exactly
    the run whose readiness you most want written down."""
    s = directives("rb-biotech.service")
    assert "preflight.py" in s
    assert "ExecStopPost" in s
    assert "ExecStartPost=" not in s


def test_the_intraday_cache_has_exactly_one_owner():
    """It was staged inside rb-biotech as an ignored ExecStartPre. The report
    needs it, biotech does not, and a shared owner meant a biotech change could
    silently cost the report its cache."""
    owners = [n for n in os.listdir(DEPLOY)
              if n.endswith(".service") and "bar_cache.py" in directives(n)]
    assert owners == ["rb-prepare.service"], owners


def test_the_cache_is_staged_before_the_unit_that_checks_it():
    """rb-biotech runs preflight, which checks the cache rb-prepare stages.
    Staged afterwards it would report NOT READY every morning."""
    def at(name):
        m = re.search(r"OnCalendar=.*?(\d{2}):(\d{2}):(\d{2})", unit(name))
        return dt.time(*(int(g) for g in m.groups()))
    assert at("rb-prepare.timer") < at("rb-biotech.timer")
    assert "After=" in directives("rb-biotech.service")
    assert "rb-prepare.service" in directives("rb-biotech.service")


# ── day-97: the installer, because a hand-typed cp is how this broke ───────

INSTALL = os.path.join(DEPLOY, "install.sh")


def installer():
    return open(INSTALL).read()


def test_the_installer_is_executable_and_valid_shell():
    import subprocess
    assert os.access(INSTALL, os.X_OK)
    assert subprocess.run(["bash", "-n", INSTALL]).returncode == 0


def test_it_refuses_to_install_where_systemd_is_not_pid_1():
    """A container with the systemd BINARY but a different PID 1 will accept
    `cp` and `daemon-reload` and silently run nothing."""
    s = installer()
    assert "ps -p 1 -o comm=" in s
    i = s.index("ps -p 1 -o comm=")
    assert "exit 1" in s[i:i + 500]


def test_it_verifies_the_LOADED_unit_not_the_repo_copy():
    """THE CASE THAT MATTERS. The repo can be perfect while /etc/systemd
    still holds the old unit that bypasses the wrapper. Verification must read
    systemd, not the file it just copied."""
    s = installer()
    assert "systemctl cat rb-report.service" in s
    assert "LOADED unit still bypasses the wrapper" in s


def test_it_rejects_units_that_ignore_their_exit_status():
    assert "ignores its exit status" in installer()


def test_it_extracts_the_minute_not_the_timezone():
    """`sed 's/.* //'` takes the LAST field of an OnCalendar line, which is
    America/New_York — so every timer 'clashes' and the check is useless.
    Found by running the installer, not by reading it."""
    s = installer()
    assert "[0-9]{2}:[0-9]{2}:[0-9]{2}" in s
    assert "sed 's/.* //;s/:..$//'" not in s


def test_check_mode_changes_nothing():
    """--check must be safe to run on a live host at any hour."""
    s = installer()
    i = s.index('CHECK_ONLY" -eq 0')
    for verb in ("install -m", "daemon-reload", "enable --now"):
        assert s.index(verb) > i, f"{verb} runs outside the install guard"


def test_it_requires_the_env_keys_the_run_actually_reads():
    s = installer()
    for key in ("RB_STATE_DIR", "RB_INTRADAY_CACHE_DIR",
                "RB_SMTP_USER", "RB_REPORT_TO"):
        assert key in s


def test_the_installer_reads_no_credential_values():
    """It checks that keys are PRESENT; it must never echo their values."""
    s = installer()
    assert 'grep -q "^${key}=" "$ENV_FILE"' in s
    assert "PASSWORD" not in s
