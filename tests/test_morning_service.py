import datetime as dt
import json
import os
from pathlib import Path
import subprocess
from zoneinfo import ZoneInfo

import pytest

import morning_service as service

NOW = dt.datetime(2026, 11, 11, 9, 1, tzinfo=ZoneInfo('America/New_York'))


@pytest.fixture
def mail(monkeypatch):
    for name, value in {'RB_SMTP_USER': 'sender@example.test', 'RB_SMTP_PASSWORD': 'example-app-password',
                        'RB_REPORT_TO': 'recipient@example.test'}.items():
        monkeypatch.setenv(name, value)


def test_a_missing_server_transport_cannot_be_mistaken_for_the_claude_connector(tmp_path, monkeypatch):
    for name in ('RB_SMTP_USER', 'RB_SMTP_PASSWORD', 'RB_REPORT_TO', 'DEEPSEEK_API_KEY',
                 'OPENROUTER_API_KEY', 'GEMINI_API_KEY', 'FMP_API_KEY'):
        monkeypatch.delenv(name, raising=False)
    result = service.configuration(tmp_path)
    assert not result['ready'] and 'RB_SMTP_PASSWORD' in result['missing']
    assert 'OPENROUTER_API_KEY' in result['missing']


def test_send_claim_survives_restart_and_preserves_the_complete_html(tmp_path, mail):
    messages = []
    first = service.send_once(tmp_path, 'decision', 'Research', 'Plain text', '<table><tr><td>Full HTML</td></tr></table>',
                              at=NOW, sender=messages.append)
    second = service.send_once(tmp_path, 'decision', 'Research', 'Plain text', '<p>changed</p>', at=NOW, sender=messages.append)
    assert first == second and len(messages) == 1
    assert 'Full HTML' in messages[0].get_body(preferencelist=('html',)).get_content()
    assert messages[0]['Message-ID'] == first['message_id']


def test_an_uncertain_network_outcome_is_never_automatically_retried(tmp_path, mail):
    calls = []
    def send(message):
        calls.append(message)
        raise TimeoutError('private credential must not reach persisted status')
    with pytest.raises(RuntimeError, match='UNKNOWN_RECONCILE'):
        service.send_once(tmp_path, 'decision', 'Subject', 'Text', '<p>HTML</p>', at=NOW, sender=send)
    result = service.send_once(tmp_path, 'decision', 'Subject', 'Text', '<p>HTML</p>', at=NOW, sender=send)
    assert result['status'] == 'unknown_reconcile_sent' and len(calls) == 1
    assert 'private credential' not in json.dumps(result)


def test_0900_notice_does_not_claim_a_crash_or_a_failed_future_report(tmp_path, monkeypatch):
    import council_flash
    monkeypatch.setattr(council_flash, 'prepare', lambda *a: ('WAITING', {}))
    notices = []
    def notice(*args, **kwargs):
        notices.append(args)
        return {'status': 'sent'}
    service.cycle(tmp_path, NOW, notice=notice)
    assert len(notices) == 1 and notices[0][1] == 'not_ready'
    assert 'may still be running' in notices[0][3]
    assert 'full report window is 09:46' in notices[0][3]
    assert 'RB Daily Report' not in notices[0][2]


def test_open_check_is_not_requested_before_0931(tmp_path, monkeypatch):
    import council_flash
    monkeypatch.setattr(council_flash, 'prepare', lambda *a: ('ALREADY_SENT', {}))
    monkeypatch.setattr(council_flash, 'prepare_open', lambda *a: pytest.fail('Too early'))
    assert service.cycle(tmp_path, NOW) == []


def test_a_successful_flash_marks_the_existing_marker_only_after_delivery(tmp_path, monkeypatch):
    import council_flash
    monkeypatch.setattr(council_flash, 'prepare', lambda *a: ('READY', {'subject_path': 'fixture'}))
    order = []
    monkeypatch.setattr(council_flash, 'record', lambda *a, **kw: order.append('record'))
    def send(*a):
        order.append('send')
        return {'status': 'sent', 'message_id': 'fixture-id'}
    service.cycle(tmp_path, NOW, deliver=send)
    assert order == ['send', 'record']


def test_record_publication_refuses_an_unrelated_code_commit(tmp_path, monkeypatch):
    from report_store import Store
    monkeypatch.setattr(service, 'ROOT', tmp_path)
    commands = []
    def runner(command, **kwargs):
        commands.append(command)
        return subprocess.CompletedProcess(command, 0, 'council.py\n', '')
    with pytest.raises(ValueError, match='NON_RECORD_COMMITS_AHEAD'):
        service.record_and_push(tmp_path/'state', NOW, runner=runner)
    assert len(commands) == 1


def test_real_record_publication_preserves_unrelated_staged_code(tmp_path, monkeypatch):
    repo, remote = tmp_path/'repo', tmp_path/'remote.git'
    repo.mkdir()
    def git(*args, cwd=repo):
        return subprocess.run(['git', *args], cwd=cwd, check=True, capture_output=True, text=True).stdout.strip()
    git('init', '--bare', str(remote))
    git('init', '-b', 'main')
    git('config', 'user.email', 'fixture@example.test')
    git('config', 'user.name', 'Fixture')
    git('config', 'core.autocrlf', 'false')
    (repo/'ledger.csv').write_text('session,value\n')
    (repo/'example.py').write_text('original = True\n')
    git('add', '--', 'ledger.csv', 'example.py')
    git('commit', '-m', 'Fixture baseline')
    git('remote', 'add', 'origin', str(remote))
    git('push', '-u', 'origin', 'main')
    (repo/'ledger.csv').write_text('session,value\n2026-11-11,1\n')
    (repo/'example.py').write_text('unreviewed = True\n')
    git('add', '--', 'example.py')
    monkeypatch.setattr(service, 'ROOT', repo)
    service.record_and_push(repo/'.rb-state', NOW)
    assert git('show', 'HEAD:example.py') == 'original = True'
    assert git('diff', '--cached', '--name-only') == 'example.py'
    assert '2026-11-11' in git('show', 'main:ledger.csv', cwd=remote)


def test_child_exit_zero_does_not_hide_an_unsent_report(tmp_path, monkeypatch):
    import dashboard
    monkeypatch.setattr(dashboard, 'is_trading_day', lambda *a: True)
    monkeypatch.setattr(service, 'now', lambda: NOW.replace(hour=8, minute=50))
    monkeypatch.setattr(service, 'configuration', lambda *a: {'ready': True})
    monkeypatch.setattr(service.subprocess, 'run', lambda *a, **kw: subprocess.CompletedProcess(a, 0))
    class Finished:
        def __init__(self, *a, **kw):
            pass
        def poll(self):
            return 0
    monkeypatch.setattr(service.subprocess, 'Popen', Finished)
    monkeypatch.setattr(service, 'cycle', lambda *a: [])
    monkeypatch.setattr(service, 'record_and_push', lambda *a: None)
    assert service.run(tmp_path) == 2
    status = json.loads((tmp_path/'autonomous'/'2026-11-11'/'run.json').read_text())
    assert status['status'] == 'degraded' and status['delivery_failures'] == 1


def test_the_opt_in_timer_stages_at_0850_and_does_not_replay_a_missed_start():
    root = Path(service.__file__).parent
    timer = (root/'deploy/rb-morning.timer').read_text()
    unit = (root/'deploy/rb-morning.service').read_text()
    assert '08:50:00 America/New_York' in timer and 'Persistent=false' in timer
    assert 'morning_service.py' in unit and 'KillMode=control-group' in unit
    assert not any('enable' in line for line in unit.splitlines())
