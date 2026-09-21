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
from pathlib import Path
from zoneinfo import ZoneInfo

import prepare_delivery
from report_store import Store

ET = ZoneInfo('America/New_York')


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
    attachments = []
    for item in payload['attachments']:
        path = Path(output_dir)/(item['filename'] + '.b64')
        path.write_text(base64.b64encode(item['content'].encode()).decode())
        attachments.append({'filename': item['filename'], 'mime_type': item['mime_type'],
                            'base64_path': str(path)})
    return {'status': 'CLAIMED', 'session': session, 'subject': payload['subject'],
            'text_path': str(Path(output_dir)/'report.txt'),
            'html_path': str(Path(output_dir)/'report.html'),
            'attachments': attachments, 'checked_at': payload['checked_at']}


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
