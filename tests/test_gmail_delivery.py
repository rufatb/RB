"""The connector path must not get weaker guarantees than the socket path.

MEASURED 2026-09-20: a Claude Code container cannot reach smtp.gmail.com on 25,
465 or 587 — the agent proxy tunnels HTTPS only. So the Gmail connector is not
an alternative delivery on this host, it is the ONLY one, and everything
`deliver_report.send` wraps around the SMTP socket has to exist here too:
refuse before 09:46, claim before sending, record the outcome, never send the
same session twice. An agent calling a tool has no socket to hang those off.
"""
import datetime as dt
import json
from zoneinfo import ZoneInfo

import pytest

import brief
import gmail_delivery as G
from report_store import Store
from test_daily_pipeline import NOW, services

ET = ZoneInfo('America/New_York')
SESSION = NOW.date().isoformat()


@pytest.fixture
def state(tmp_path):
    store = Store(tmp_path)
    store.publish(SESSION, brief.compute(now=NOW, services=services()))
    return str(tmp_path), SESSION


def test_prepare_claims_the_delivery_and_names_the_payload(state):
    directory, session = state
    out = G.prepare(directory, session, directory + '/dispatch')
    assert out['status'] == 'CLAIMED'
    assert out['subject'] and out['text_path'] and out['html_path']
    assert Store(directory).delivery(session), 'the claim was not persisted'


def test_the_same_session_is_never_prepared_twice(state):
    """THE POINT. An agent re-running the step must not send the morning's
    report a second time — there is no socket-level claim to stop it."""
    directory, session = state
    G.prepare(directory, session, directory + '/dispatch')
    again = G.prepare(directory, session, directory + '/dispatch')
    assert again['status'] == 'ALREADY_ATTEMPTED'


def test_the_cli_exit_code_tells_an_agent_not_to_send(state):
    directory, session = state
    assert G.main(['--prepare', '--state-dir', directory, '--session', session]) == 0
    assert G.main(['--prepare', '--state-dir', directory, '--session', session]) == 4


def test_the_attachment_is_written_base64_ready_for_the_tool(state):
    directory, session = state
    out = G.prepare(directory, session, directory + '/dispatch')
    import base64
    import pathlib
    att = out['attachments'][0]
    raw = base64.b64decode(pathlib.Path(att['base64_path']).read_text())
    assert raw.lstrip().lower().startswith(b'<!doctype html'), 'attachment did not round-trip'
    assert att['filename'].endswith('.html')


def test_it_refuses_to_prepare_before_the_publication_minute(state):
    """`view()` owns this guard and the connector path must not be the one that
    quietly skips it — a report delivered at 09:20 shows prices the board does
    not, whatever the body says."""
    directory, session = state
    early = dt.datetime.fromisoformat(session).replace(hour=9, minute=20, tzinfo=ET)
    with pytest.raises(ValueError, match='09:46'):
        G.prepare(directory, session, directory + '/dispatch', now=early)


def test_a_failed_send_is_recorded_as_unknown_not_left_absent(state):
    """A missing row and a failed send are different facts (day-97)."""
    directory, session = state
    G.prepare(directory, session, directory + '/dispatch')
    G.record(directory, session, failed=True)
    assert Store(directory).delivery(session)['state'] == 'unknown'


def test_a_successful_send_records_the_provider_id_beside_the_shared_key(state):
    """`message_id` is OUR reconciliation key, set at claim time and shared
    with the SMTP path; `detail` is the provider's own id. Keeping them apart
    is what lets one session be reconciled across both paths."""
    directory, session = state
    G.prepare(directory, session, directory + '/dispatch')
    G.record(directory, session, message_id='1a0c02142e9d7581')
    row = Store(directory).delivery(session)
    assert row['state'] == 'sent'
    assert row['detail'] == '1a0c02142e9d7581', 'the Gmail id was not recorded'
    assert row['message_id'] == G.message_key(session)


def test_both_paths_share_one_reconciliation_key(state):
    """One session delivered once by each path must not read as two reports.
    The first cut of this test ended in `or True`, which asserts nothing."""
    import deliver_report
    directory, session = state
    built = deliver_report.message(Store(directory).get(session),
                                   'a@b.com', 'c@d.com')['Message-ID']
    assert G.message_key(session) == built


def test_preparing_an_unpublished_session_refuses(tmp_path):
    with pytest.raises(ValueError, match='no immutable publication'):
        G.prepare(str(tmp_path), '2026-09-18', str(tmp_path/'dispatch'))
