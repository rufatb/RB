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
