#!/usr/bin/env python3
"""Run the existing morning on a persistent Linux host, without a chat session.

This is an opt-in replacement for the Claude morning Routine and rb-report.timer.
It preserves research ordering, cutoffs and the report's existing delivery claim.
"""
from __future__ import annotations

import argparse
import datetime as dt
from email.message import EmailMessage
import hashlib
from html import escape
import json
import os
from pathlib import Path
import re
import signal
import smtplib
import ssl
import subprocess
import sys
import time
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent
ET = ZoneInfo('America/New_York')


def now():
    return dt.datetime.now(ET)


def configuration(root):
    from smtp_credential import readiness
    mail = readiness(root)
    fields = {'DEEPSEEK_API_KEY': 'deepseek_api_key', 'OPENROUTER_API_KEY': 'openrouter_api_key',
              'GEMINI_API_KEY': 'gemini_api_key', 'FMP_API_KEY': 'fmp_api_key'}
    missing = []
    for name, filename in fields.items():
        path = Path(root)/'secrets'/filename
        if not os.getenv(name) and (not path.is_file() or not 0 < path.stat().st_size <= 400):
            missing.append(name)
    if not os.getenv('DEEPSEEK_MODEL') and not (Path(root)/'deepseek_model.txt').is_file():
        missing.append('DEEPSEEK_MODEL')
    missing.extend(mail['missing'])
    return {'ready': not missing and mail['ready'], 'missing': missing,
            'email_transport': 'SMTP on the designated host', 'email_error': mail['error']}


def first_claim(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with path.open('x', encoding='utf-8') as out:
            json.dump(value, out)
            out.flush()
            os.fsync(out.fileno())
        return True
    except FileExistsError:
        return False


def atomic(path, value):
    import tempfile
    handle, temporary = tempfile.mkstemp(dir=path.parent, prefix='.status-')
    try:
        with os.fdopen(handle, 'w', encoding='utf-8') as out:
            json.dump(value, out)
            out.flush()
            os.fsync(out.fileno())
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)


def smtp_send(message):
    with smtplib.SMTP_SSL(os.getenv('RB_SMTP_HOST', 'smtp.gmail.com'),
                         int(os.getenv('RB_SMTP_PORT', '465')), timeout=20,
                         context=ssl.create_default_context()) as smtp:
        smtp.login(os.environ['RB_SMTP_USER'], os.environ['RB_SMTP_PASSWORD'])
        refused = smtp.send_message(message)
        if refused:
            raise RuntimeError('SMTP_RECIPIENT_REFUSED')


def send_once(root, kind, subject, text, html, *, at=None, sender=None):
    """Claim before SMTP. An uncertain send is never automatically repeated."""
    if kind not in {'decision', 'open_check', 'not_ready'}:
        raise ValueError('UNKNOWN_DELIVERY_KIND')
    from smtp_credential import readiness
    mail = readiness(root)
    if not mail['ready']:
        raise ValueError('MAIL_TRANSPORT_NOT_CONFIGURED')
    at = (at or now()).astimezone(ET)
    path = Path(root)/'autonomous'/at.date().isoformat()/(kind+'.json')
    message_id = '<rb-%s-%s@%s>' % (at.date().isoformat(), kind, mail['sender'].split('@', 1)[1])
    record = {'kind': kind, 'status': 'sending', 'started_at': at.isoformat(), 'message_id': message_id,
              'payload_sha256': hashlib.sha256((subject+'\n'+text+'\n'+html).encode()).hexdigest()}
    if not first_claim(path, record):
        previous = json.loads(path.read_text(encoding='utf-8'))
        return previous if previous['status'] == 'sent' else {**previous, 'status': 'unknown_reconcile_sent'}
    try:
        message = EmailMessage()
        message['From'], message['To'] = mail['sender'], mail['recipient']
        message['Subject'], message['Message-ID'] = subject.strip(), message_id
        message.set_content(text)
        message.add_alternative(html, subtype='html')
        (sender or smtp_send)(message)
        record.update(status='sent', completed_at=now().isoformat())
        atomic(path, record)
        return record
    except Exception as exc:
        atomic(path, {**record, 'status': 'unknown_reconcile_sent', 'error_type': type(exc).__name__})
        raise RuntimeError('MAIL_OUTCOME_UNKNOWN_RECONCILE_SENT') from None


def deliver_files(root, kind, plan, at):
    result = send_once(root, kind,
        Path(plan['subject_path']).read_text(encoding='utf-8'),
        Path(plan['text_path']).read_text(encoding='utf-8'),
        Path(plan['html_path']).read_text(encoding='utf-8'), at=at)
    return result


def cycle(root, at, *, deliver=deliver_files, notice=send_once):
    """Bounded polling; no model question or paid research is created here."""
    import council_flash as flash
    local = at.astimezone(ET)
    outcomes = []
    if local.time() < dt.time(9, 44):
        status, plan = flash.prepare(root, local)
        if status == 'READY':
            result = deliver(root, 'decision', plan, local)
            if result['status'] == 'sent':
                flash.record(root, result['message_id'], now=local)
            outcomes.append(result)
        elif status != 'ALREADY_SENT' and local.time() >= dt.time(9):
            subject = 'RB Morning Decision — %s — RESEARCH NOT READY' % local.date()
            text = ('The scheduled morning research has not produced a sendable decision as of %s ET. '
                    'No completed consensus decision is available. The preparation job may still be running; '
                    'the normal full report window is 09:46 ET. This notice does not claim a crash or a failed future report.'
                    % local.strftime('%H:%M:%S'))
            outcomes.append(notice(root, 'not_ready', subject, text, '<p>'+escape(text)+'</p>', at=local))
        if local.time() >= dt.time(9, 31):
            status, plan = flash.prepare_open(root, local)
            if status == 'READY':
                result = deliver(root, 'open_check', plan, local)
                if result['status'] == 'sent':
                    flash.record(root, result['message_id'], now=local, name=flash.OPEN_SENT)
                outcomes.append(result)
    return outcomes


def record_and_push(root, at, *, runner=subprocess.run):
    """The Routine's existing record step, limited to generated research data."""
    from report_store import Store
    import model_picks
    report = Store(root).get(at.date().isoformat())
    if report:
        model_picks.append(model_picks.rows_from_report(report))
        import gap_signal
        gap_signal.record(report)
    allowed_csv = {'ledger.csv', 'universe_prints.csv', 'data/model_picks.csv', 'data/news_calls.csv',
                   'data/us_preopen_calls.csv', 'data/gap_calls.csv', 'data/pead_calls.csv',
                   'data/reviews/open_checks.csv', 'positions.csv', 'data/advice.csv'}
    def allowed(path):
        return path in allowed_csv or bool(re.fullmatch(
            r'data/(?:newswire/(?:press/)?\d{4}-\d{2}-\d{2}\.jsonl|reviews/dda/\d{4}-\d{2}-\d{2}\.(?:decision|opening|open-check|report)\.json|social/\d{4}-\d{2}-\d{2}\.json)', path))
    def git(*args):
        result = runner(['git', *args], cwd=ROOT, capture_output=True, text=True, timeout=30)
        if result.returncode:
            raise RuntimeError('RECORD_GIT_STEP_FAILED')
        return result.stdout.strip()
    ahead = git('log', '--format=', '--name-only', 'origin/main..HEAD')
    if any(not allowed(path) for path in ahead.splitlines() if path):
        raise ValueError('NON_RECORD_COMMITS_AHEAD')
    candidates = sorted(path for path in allowed_csv if (ROOT/path).is_file())
    for directory in ('data/newswire', 'data/newswire/press'):
        candidates.extend(path.relative_to(ROOT).as_posix() for path in (ROOT/directory).glob('*.jsonl')
                          if allowed(path.relative_to(ROOT).as_posix()))
    if not candidates:
        return
    changed = git('diff', '--name-only', 'HEAD', '--', *candidates).splitlines()
    changed += git('ls-files', '--others', '--exclude-standard', '--', *candidates).splitlines()
    if changed:
        git('add', '--', *sorted(set(changed)))
        git('commit', '--only', '-m', 'record: %s morning host research' % at.date(), '--', *sorted(set(changed)))
    git('push', 'origin', 'HEAD:main')


def run(root):
    root = Path(root).resolve()
    at = now()
    from dashboard import is_trading_day
    if not is_trading_day(at.date()):
        print(json.dumps({'status': 'NOT_A_TRADING_DAY'}), flush=True)
        return 0
    ready = configuration(root)
    if not ready['ready']:
        print(json.dumps({'status': 'NOT_CONFIGURED', **ready}), flush=True)
        return 2
    if not dt.time(8, 45) <= at.time() < dt.time(9, 30):
        print(json.dumps({'status': 'MISSED_START_WINDOW', 'at': at.isoformat()}), flush=True)
        return 2
    # One designated writer. Never restart a paid same-day run automatically.
    claim = root/'autonomous'/at.date().isoformat()/'run.json'
    if not first_claim(claim, {'status': 'starting', 'started_at': at.isoformat()}):
        print(json.dumps({'status': 'ALREADY_STARTED_CHECK_RUN_LOG'}), flush=True)
        return 2
    # Existing startup contract: fail rather than run a stale checkout.
    try:
        sync = subprocess.run(['git', 'pull', '--ff-only'], cwd=ROOT, capture_output=True, timeout=45)
    except subprocess.TimeoutExpired:
        atomic(claim, {'status': 'SYNC_FAILED', 'at': now().isoformat()})
        return 2
    if sync.returncode:
        atomic(claim, {'status': 'SYNC_FAILED', 'at': now().isoformat()})
        return 2
    failures = 0
    env = {**os.environ, 'RB_STATE_DIR': str(root),
           'PATH': str(Path(sys.executable).parent)+os.pathsep+os.environ.get('PATH', '')}
    child = None
    try:
        with (root/'morning_full.log').open('ab') as log:
            child = subprocess.Popen(['bash', str(ROOT/'morning_full.sh')], cwd=ROOT, env=env,
                stdin=subprocess.DEVNULL, stdout=log, stderr=log, start_new_session=True)
            while True:
                current = now()
                atomic(claim, {'status': 'running', 'started_at': at.isoformat(), 'heartbeat_at': current.isoformat()})
                try:
                    outcomes = cycle(root, current)
                    for outcome in outcomes:
                        print(json.dumps(outcome), flush=True)
                        if outcome['status'] != 'sent':
                            failures += 1
                except Exception as exc:
                    failures += 1
                    print(json.dumps({'status': 'DELIVERY_FAILED', 'error_type': type(exc).__name__}), flush=True)
                code = child.poll()
                if code is not None:
                    from report_store import Store
                    publication = Store(root)
                    delivery = publication.delivery(current.date().isoformat()) or {}
                    if code != 3 and delivery.get('state') != 'sent':
                        failures += 1
                        print(json.dumps({'status': 'REPORT_EMAIL_NOT_CONFIRMED',
                            'delivery_state': delivery.get('state', 'not_attempted')}), flush=True)
                    try:
                        record_and_push(root, current)
                    except Exception as exc:
                        failures += 1
                        print(json.dumps({'status': 'RECORD_PUBLICATION_FAILED', 'error_type': type(exc).__name__}), flush=True)
                    atomic(claim, {'status': 'complete' if code == 0 and not failures else 'degraded',
                        'exit_code': code, 'delivery_failures': failures, 'completed_at': now().isoformat()})
                    return 0 if code in {0, 3} and not failures else 2
                if current.time() >= dt.time(10):
                    os.killpg(child.pid, signal.SIGTERM)
                    try:
                        child.wait(timeout=10)
                    except subprocess.TimeoutExpired:
                        os.killpg(child.pid, signal.SIGKILL)
                        child.wait(timeout=5)
                    atomic(claim, {'status': 'TIMED_OUT', 'at': now().isoformat()})
                    return 2
                time.sleep(5)
    except Exception as exc:
        atomic(claim, {'status': 'FAILED', 'error_type': type(exc).__name__, 'at': now().isoformat()})
        raise
    finally:
        if child is not None and child.poll() is None:
            os.killpg(child.pid, signal.SIGTERM)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--state-dir', type=Path, default=Path(os.getenv('RB_STATE_DIR', '.rb-state')))
    parser.add_argument('--check', action='store_true', help='Inspect configuration; do not research or send')
    args = parser.parse_args()
    if args.check:
        result = configuration(args.state_dir)
        print(json.dumps(result))
        return 0 if result['ready'] else 2
    if os.name != 'posix':
        raise SystemExit('This opt-in service needs the designated persistent Linux host.')
    return run(args.state_dir)


if __name__ == '__main__':
    sys.exit(main())
