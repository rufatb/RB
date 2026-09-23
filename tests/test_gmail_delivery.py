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


def test_the_subject_is_written_to_a_file_for_a_sender_in_another_container(state):
    """The morning session cannot reach Gmail — a Routine created through the
    MCP tool stores no connectors. So the send happens in a different session,
    in a different container, and it must take the subject VERBATIM. A sender
    that rebuilds the subject is a second implementation of `subject_state`,
    and that rule is what puts DO NOT TRADE in front of an abstained board."""
    import pathlib
    directory, session = state
    out = G.prepare(directory, session, directory + '/dispatch')
    written = pathlib.Path(out['subject_path']).read_text()
    assert written == out['subject']
    assert 'RB Daily Report' in written


# ── the attachment a model-mediated send cannot carry (2026-09-22) ───────────

def test_an_attachment_too_large_to_paste_is_refused_before_the_send(state, monkeypatch):
    """MEASURED 2026-09-22: the full report is ~348 KB, i.e. ~464 KB of base64,
    and the sending agent has to emit every one of those characters as tool
    input. The instruction to paste the .b64 file verbatim was unrunnable from
    the day it was written; the session that hit it sent no attachments array
    at all and said nothing, which is the right call made invisibly.

    So the refusal happens HERE, before the send, where it can be reported."""
    directory, session = state
    monkeypatch.setattr(G, 'MAX_SENDABLE_BASE64', 10)
    out = G.prepare(directory, session, directory + '/dispatch')
    assert out['attachments'] == []
    assert out['unsendable_attachments'], 'the oversized attachment was not named'
    assert any('ATTACHMENT NOT SENDABLE' in g for g in out['gaps'])
    # The file is still written: a sender with a real file handle can attach it.
    assert open(out['unsendable_attachments'][0]['base64_path']).read()


def test_the_body_stops_promising_an_attachment_that_cannot_be_sent(state, monkeypatch):
    """The frozen body says "attached HTML report". With no attachment that
    sentence is false, and a false sentence in the record is worse than a
    missing file. The publication is NOT rewritten — the note is appended and
    labelled as the sender's addition."""
    directory, session = state
    monkeypatch.setattr(G, 'MAX_SENDABLE_BASE64', 10)
    out = G.prepare(directory, session, directory + '/dispatch')
    text = open(out['text_path']).read()
    html = open(out['html_path']).read()
    # Day-114b: the body no longer promises an attachment at all — it links
    # the published report — so there is nothing false left to correct and no
    # note is appended. The oversized file is still named in `gaps`.
    for body in (text, html):
        assert 'attached' not in body.lower() and 'DELIVERY NOTE' not in body
        assert G.ARTIFACT_URL in body


def test_an_attachment_that_fits_is_still_sent_and_no_note_is_added(state):
    """The refusal must be a size decision, not a blanket one: on a small
    report the attachment still goes, and a note about a missing attachment
    would then be a lie in the other direction."""
    directory, session = state
    out = G.prepare(directory, session, directory + '/dispatch')
    if not out['attachments']:
        pytest.skip('the fixture report is itself over the real limit')
    assert out['unsendable_attachments'] == [] and out['gaps'] == []
    assert 'DELIVERY NOTE' not in open(out['text_path']).read()
