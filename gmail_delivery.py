#!/usr/bin/env python3
"""Publish-once bookkeeping for the Gmail-connector delivery path.

WHY THIS EXISTS. `deliver_report.send` does three things around the SMTP
socket: it refuses to transmit before 09:46, it CLAIMS the delivery in the
store before handing over DATA, and it records the outcome. The connector path
has no socket — an agent calls the Gmail tool — so it would otherwise get none
of that, and a re-run would cheerfully send the morning's report twice.

MEASURED 2026-09-20: a Claude Code container cannot reach smtp.gmail.com on 25,
465 or 587; the agent proxy tunnels HTTPS only. So on this host the connector
is not an alternative to the SMTP path, it is the ONLY path, and it needs the
same guarantees rather than weaker ones.

Two calls, in this order:

    python gmail_delivery.py --prepare --session 2026-09-21
        Renders the frozen publication at the actual dispatch clock (the same
        `prepare_delivery.artifacts` the Gmail automation has always used),
        claims the delivery, and prints where the payload is. Exits 4 and sends
        NOTHING if this session was already attempted.

    python gmail_delivery.py --record --session 2026-09-21 --message-id <id>
        Records the outcome after the tool call returns.

If the send fails, record it with `--failed` so the state is `unknown` rather
than silently absent: a missing row and a failed send are different facts, and
day-97's ambiguity rule applies here exactly as it does to SMTP.

Nothing here renders, recomputes or sends anything.
"""
from __future__ import annotations
import argparse
import base64
import datetime as dt
import json
import os
from html import escape
from pathlib import Path
from zoneinfo import ZoneInfo

import prepare_delivery
from report_store import Store

ET = ZoneInfo('America/New_York')


# A MODEL-MEDIATED SEND CANNOT CARRY A LARGE ATTACHMENT, measured 2026-09-22.
# The connector's `attachments[].content` is base64 that the SENDING AGENT has
# to emit as tool input, token by token. The full report is ~348 KB, i.e. ~464 KB
# of base64 — far past any single tool call. The instruction to "paste the exact
# contents of the .b64 file" was unrunnable from the day it was written, and the
# session that hit it silently sent no attachments array at all, which is the
# right call made invisibly. This threshold makes the refusal explicit and
# BEFORE the send, so the body can stop promising an attachment that cannot come.
MAX_SENDABLE_BASE64 = 100_000

# Where the full report actually is when it cannot be attached. It is published
# as a file on the owner's page by the same morning run, so this is not a
# consolation link: it is the same bytes, addressed differently.
ARTIFACT_URL = os.environ.get(
    'RB_ARTIFACT_URL', 'https://claude.ai/artifact/28ZfvwVZG1A2yagxJ4Hyt9')
PUBLISHED_FULL_REPORT = 'delivery/full_report.html'


def _unattachable_note(items):
    """Plain-text note naming what is missing and where it is instead.

    The frozen body says "Full board, sources and diagnostics: attached HTML
    report." With no attachment that sentence is false, and a false sentence in
    the record is worse than a missing file. The frozen text is NOT rewritten —
    it is the publication — so the correction is appended and labelled as an
    addition by the sender."""
    names = ', '.join(sorted(i['filename'] for i in items))
    return ('\n\n' + '-'*70 + '\n'
            'DELIVERY NOTE — added by the sending session, NOT part of the frozen report.\n'
            'The report above says "attached HTML report". THERE IS NO ATTACHMENT ON\n'
            'THIS MESSAGE. %s is too large for this delivery path to carry.\n'
            'The full report is published in full, unchanged, at:\n'
            '  %s\n  (file: %s)\n'
            'Every number above is the frozen publication and is untouched.\n'
            % (names, ARTIFACT_URL, PUBLISHED_FULL_REPORT) + '-'*70 + '\n')


def _unattachable_html(items):
    names = escape(', '.join(sorted(i['filename'] for i in items)))
    return ('<div style="border:2px solid #8a5f19;background:#f7efe0;padding:14px 16px;'
            'margin:18px 0"><p style="margin:0 0 8px;font-weight:700;color:#6b4a14">'
            'DELIVERY NOTE — added by the sending session, not part of the frozen report'
            '</p><p style="margin:0;line-height:1.55">The report says &quot;attached HTML '
            'report&quot;. <strong>There is no attachment on this message.</strong> %s is too '
            'large for this delivery path to carry. The full report is published in full, '
            'unchanged, at <a href="%s">%s</a> (file <code>%s</code>). Every number below is '
            'the frozen publication and is untouched.</p></div>'
            % (names, escape(ARTIFACT_URL), escape(ARTIFACT_URL),
               escape(PUBLISHED_FULL_REPORT)))


def message_key(session):
    """The same reconciliation key the SMTP path uses, so one session cannot be
    delivered once by each path and look like two different reports."""
    return f'<rb-daily-{session}@rb-report.local>'


def prepare(state_dir, session, output_dir, *, now=None):
    store = Store(state_dir)
    report = store.get(session)
    if report is None:
        raise ValueError('no immutable publication; run daily_job.py first')
    existing = store.delivery(session)
    if existing:
        return {'status': 'ALREADY_ATTEMPTED', 'delivery': existing}
    # Renders through `view()`, which REFUSES before 09:46 ET on the session's
    # own date and labels a late dispatch informational. The connector path
    # must not be the one that quietly skips that guard.
    payload = prepare_delivery.artifacts(report, output_dir, now)
    if not store.claim_delivery(session, message_key(session)):
        return {'status': 'ALREADY_ATTEMPTED', 'delivery': store.delivery(session)}
    # THE PAYLOAD HAS TO OUTLIVE THIS CONTAINER. The morning runs in a fresh
    # scheduled session that CANNOT reach the Gmail connector — a Routine
    # created through the MCP tool stores no connectors, and the server says so
    # outright. So the send happens elsewhere, and everything it needs must be
    # publishable as files beside the report page. Writing the subject to its
    # own file is the point: whoever sends must never RECOMPUTE it. It carries
    # the board state (DO NOT TRADE / legs ABSTAINED / INFORMATIONAL) that
    # `subject_state` derives from the frozen report, and a sender that builds
    # its own subject is a second, drifting implementation of that rule.
    (Path(output_dir)/'subject.txt').write_text(payload['subject'])
    attachments, unsendable = [], []
    for item in payload['attachments']:
        path = Path(output_dir)/(item['filename'] + '.b64')
        encoded = base64.b64encode(item['content'].encode()).decode()
        path.write_text(encoded)
        row = {'filename': item['filename'], 'mime_type': item['mime_type'],
               'base64_path': str(path), 'base64_chars': len(encoded),
               'sendable': len(encoded) <= MAX_SENDABLE_BASE64}
        (attachments if row['sendable'] else unsendable).append(row)
    # The file is still written either way. A later path with a real file handle
    # — a host SMTP run, a script — can attach it; only the model-mediated send
    # cannot, and that is a property of the SENDER, not of the report.
    text_path, html_path = Path(output_dir)/'report.txt', Path(output_dir)/'report.html'
    gaps = []
    if unsendable:
        gaps.append('ATTACHMENT NOT SENDABLE: %s (%s base64 chars, limit %s). The body now '
                    'says so and points at %s.'
                    % (', '.join(i['filename'] for i in unsendable),
                       max(i['base64_chars'] for i in unsendable),
                       MAX_SENDABLE_BASE64, ARTIFACT_URL))
        text_path.write_text(text_path.read_text() + _unattachable_note(unsendable))
        html = html_path.read_text()
        marker = '<body'
        cut = html.find('>', html.find(marker)) + 1 if marker in html else 0
        html_path.write_text(html[:cut] + _unattachable_html(unsendable) + html[cut:])
    return {'status': 'CLAIMED', 'session': session, 'subject': payload['subject'],
            'subject_path': str(Path(output_dir)/'subject.txt'),
            'text_path': str(text_path), 'html_path': str(html_path),
            'attachments': attachments, 'unsendable_attachments': unsendable,
            'gaps': gaps, 'checked_at': payload['checked_at']}


def record(state_dir, session, *, message_id=None, failed=False):
    store = Store(state_dir)
    if failed:
        store.finish_delivery(session, 'unknown', message_id or 'gmail-connector-failed')
        return {'status': 'RECORDED_UNKNOWN'}
    store.finish_delivery(session, 'sent', message_id or message_key(session))
    return {'status': 'RECORDED_SENT', 'message_id': message_id or message_key(session)}


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--state-dir', default=os.getenv('RB_STATE_DIR', '.rb-state'))
    p.add_argument('--session', default=dt.datetime.now(ET).date().isoformat())
    p.add_argument('--output-dir')
    p.add_argument('--prepare', action='store_true')
    p.add_argument('--record', action='store_true')
    p.add_argument('--message-id')
    p.add_argument('--failed', action='store_true')
    a = p.parse_args(argv)
    if a.prepare == a.record:
        p.error('choose exactly one of --prepare or --record')
    if a.prepare:
        out = prepare(a.state_dir, a.session,
                      a.output_dir or str(Path(a.state_dir)/'dispatch'))
        print(json.dumps(out, indent=2))
        return 4 if out['status'] == 'ALREADY_ATTEMPTED' else 0
    print(json.dumps(record(a.state_dir, a.session, message_id=a.message_id,
                            failed=a.failed), indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
