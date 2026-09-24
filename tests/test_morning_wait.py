"""The morning session waits by command, not by remembering to look (2026-09-24)."""
import os
import time

import morning_wait as W


def test_no_log_is_not_started(tmp_path):
    assert W.status(tmp_path / 'morning_full.log', 60) == ('NOT_STARTED', '')


def test_running_job_reports_its_last_line(tmp_path):
    log = tmp_path / 'morning_full.log'
    log.write_text('[09:01] staging\n[09:02] factor pool: complete\n')
    assert W.status(log, 60) == ('RUNNING', '[09:02] factor pool: complete')


def test_the_jobs_own_exit_code_is_reported_never_swallowed(tmp_path):
    log = tmp_path / 'morning_full.log'
    log.write_text('[09:44] handing over to morning.sh\n[09:46] morning.sh exit 4\n')
    assert W.status(log, 60) == ('DONE', '4')
    assert W.main(['--log', str(log), '--timeout', '0']) == 0


def test_a_silent_log_is_stalled_not_running(tmp_path):
    log = tmp_path / 'morning_full.log'
    log.write_text('[09:01] staging\n')
    old = time.time() - 3600
    os.utime(log, (old, old))
    state, age = W.status(log, 1500)
    assert state == 'STALLED' and int(age) >= 3600


def test_wait_is_bounded_and_returns_running_when_time_runs_out(tmp_path):
    log = tmp_path / 'morning_full.log'
    log.write_text('[09:01] staging\n')
    t = {'now': 0.0}
    def clock(): return t['now']
    def sleep(s): t['now'] += s
    assert W.wait(log, 30, 1500, clock=clock, sleep=sleep)[0] == 'RUNNING'
    assert t['now'] >= 30


def test_wait_returns_as_soon_as_the_job_exits(tmp_path):
    log = tmp_path / 'morning_full.log'
    log.write_text('[09:01] staging\n')
    t = {'now': 0.0}
    def clock(): return t['now']
    def sleep(s):
        t['now'] += s
        log.write_text(log.read_text() + '[09:46] morning.sh exit 0\n')
    assert W.wait(log, 540, 1500, clock=clock, sleep=sleep) == ('DONE', '0')
    assert t['now'] < 540
