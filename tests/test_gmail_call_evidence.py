"""Day-156d: a claimed report is retried only on positive evidence that Gmail was
never called. The owner, 2026-11-26: "An empty Sent search alone is insufficient
to retry. Allow a retry once the original sender has stopped and there's
positive evidence Gmail was never called. Otherwise flag the delivery for review." """
import datetime as dt
import json

import delivery_plan
import gmail_delivery as G
from report_store import Store

SESSION = '2026-11-27'
NOW = dt.datetime(2026, 11, 27, 9, 50, tzinfo=G.ET)


def claimed(tmp_path, edition=True):
    store = Store(tmp_path)
    report = {'session': SESSION, 'intraday': {'news_desk': {'edition_version': 'news-desk-edition-v1'}
                                                if edition else {}}}
    store.publish(SESSION, report)
    assert store.claim_delivery(SESSION, G.message_key(SESSION))
    return store


def dispatch(tmp_path):
    d = tmp_path / 'dispatch'
    d.mkdir(exist_ok=True)
    (d / 'subject.txt').write_text(f'RB Daily Report — {SESSION} — Intraday')
    (d / 'report.txt').write_text('# RB Daily Report')
    (d / 'report.html').write_text('<p>RB</p>')


def test_the_marker_is_written_once_and_only_under_an_open_claim(tmp_path, capsys):
    assert G.calling(tmp_path, SESSION)['status'] == 'NOT_CLAIMED'          # nothing claimed yet
    store = claimed(tmp_path)
    first = G.calling(tmp_path, SESSION, now=NOW)
    assert first['status'] == 'CALLING' and first['started_at'] == NOW.isoformat()
    assert json.loads(G.call_marker(tmp_path, SESSION).read_text())['session'] == SESSION
    again = G.calling(tmp_path, SESSION)
    assert again['status'] == 'GMAIL_ALREADY_CALLED' and again['marker']['started_at'] == NOW.isoformat()
    assert G.main(['--state-dir', str(tmp_path), '--session', SESSION, '--calling']) == 4
    G.record(tmp_path, SESSION, message_id='1a2b')
    assert store.delivery(SESSION)['state'] == 'sent'
    assert G.main(['--state-dir', str(tmp_path), '--session', SESSION, '--calling']) == 3   # not open now


def test_the_command_exits_zero_only_when_the_send_may_go(tmp_path):
    claimed(tmp_path)
    assert G.main(['--state-dir', str(tmp_path), '--session', SESSION, '--calling']) == 0


def test_only_the_absence_of_every_sign_counts_as_never_called(tmp_path):
    assert G.gmail_called(tmp_path, SESSION) is False                       # no claim at all
    store = claimed(tmp_path)
    assert G.gmail_called(tmp_path, SESSION) is False                       # claimed, never called
    for state, called in (('sent', True), ('unknown', True), ('failed_before_send', False)):
        store.finish_delivery(SESSION, state)
        assert G.gmail_called(tmp_path, SESSION) is called, state
    store.finish_delivery(SESSION, 'failed_before_send')
    G.call_marker(tmp_path, SESSION).parent.mkdir(parents=True, exist_ok=True)
    G.call_marker(tmp_path, SESSION).write_text('{}')
    assert G.gmail_called(tmp_path, SESSION) is True                        # the marker outranks the state


def test_reconcile_offers_the_files_only_with_positive_evidence(tmp_path):
    claimed(tmp_path)
    dispatch(tmp_path)
    plan = delivery_plan.plan(tmp_path, now=NOW)
    assert plan['mode'] == 'RECONCILE' and plan['gmail_called'] is False
    assert plan['html_path'].endswith('report.html') and 'sender that made the claim has stopped' in plan['note']
    G.calling(tmp_path, SESSION)                                            # the sender started a call
    plan = delivery_plan.plan(tmp_path, now=NOW)
    assert plan['mode'] == 'RECONCILE' and plan['gmail_called'] is True
    assert 'html_path' not in plan and 'flag the delivery for review' in plan['note']


def test_reconcile_without_dispatch_files_is_flagged_not_retried(tmp_path):
    claimed(tmp_path)
    plan = delivery_plan.plan(tmp_path, now=NOW)
    assert plan['mode'] == 'RECONCILE' and plan['gmail_called'] is False
    assert 'html_path' not in plan and 'flag the delivery for review' in plan['note']


def test_a_report_without_an_edition_keeps_its_earlier_path(tmp_path):
    claimed(tmp_path, edition=False)
    dispatch(tmp_path)
    plan = delivery_plan.plan(tmp_path, now=NOW)
    assert plan['mode'] == 'REPORT' and plan['claimed'] is False
