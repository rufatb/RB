#!/usr/bin/env python3
"""Send one frozen multipart report; do not recompute at delivery time.

A crash/timeout after DATA has ambiguous acceptance: persist UNKNOWN and
require provider reconciliation rather than blindly sending a duplicate. A
deterministic Message-ID is a reconciliation key, not a claim of exactly-once
SMTP semantics.

Credentials used to be environment-ONLY, which is why this module had never
sent a single email from a scheduled run: the container is fresh, nothing
exported them, and `morning.sh` silently took its no-credential branch every
morning. `smtp_credential.load_private_smtp` adds the private-file contract the
DeepSeek and OpenRouter keys already use; the environment still wins.
"""
from __future__ import annotations
import argparse
import datetime as dt
from email.message import EmailMessage
from email.utils import format_datetime
import json
import os
import smtplib
import ssl
from pathlib import Path
from zoneinfo import ZoneInfo
import brief
import email_render
import smtp_credential
from prepare_delivery import subject_state, subject, view
from report_store import Store


def message(report, sender, recipient):
    for address in (sender,recipient):
        if '\n' in address or '\r' in address or '@' not in address:
            raise ValueError('invalid email address')
    msg=EmailMessage()
    msg['From']=sender;msg['To']=recipient
    msg['Subject']=subject(report)
    msg['Message-ID']=f"<rb-daily-{report['session']}@rb-report.local>"
    msg['Date']=format_datetime(dt.datetime.fromisoformat(report['generated_at']))
    msg.set_content(email_render.text(report))
    msg.add_alternative(email_render.html(report),subtype='html')
    msg.add_attachment(brief.render_html(report),subtype='html',
                       filename=f"RB-Full-Report-{report['session']}.html")
    return msg


def send(store,session,sender,recipient,*,smtp_factory=smtplib.SMTP_SSL,now=None,clock=None):
    report=store.get(session)
    if not report:
        raise ValueError('no immutable report to send')
    # Re-read the clock at the actual sending boundary. A report built on time
    # but queued for 20 minutes must not look executable in the inbox.
    if now is not None and clock is not None:
        raise ValueError('supply now or clock, not both')
    fixed=now
    clock=clock or ((lambda:fixed) if fixed is not None else
                   (lambda:dt.datetime.now(ZoneInfo('America/New_York'))))
    view(report, clock())  # refuse pre-entry transmission before authentication
    if store.delivery(session):
        return {'status':'ALREADY_ATTEMPTED','delivery':store.delivery(session)}
    # Private files populate the environment; the environment still wins. This
    # runs BEFORE claim_delivery so an absent credential cannot burn the
    # publish-once claim and make the session look already-attempted.
    missing=smtp_credential.load_private_smtp(Path(store.path).parent)
    host=os.environ.get('RB_SMTP_HOST','smtp.gmail.com')
    user=os.environ.get('RB_SMTP_USER');password=os.environ.get('RB_SMTP_PASSWORD')
    if not user or not password:
        raise ValueError(f"SMTP credential missing "
                         f"({', '.join(missing) or 'RB_SMTP_USER / RB_SMTP_PASSWORD'}); "
                         f"no email attempted. {smtp_credential.REMEDY}")
    # Authenticate before claiming. Failures here cannot have sent DATA.
    with smtp_factory(host,465,context=ssl.create_default_context(),timeout=20) as smtp:
        smtp.login(user,password)
        if not store.claim_delivery(session,f'<rb-daily-{session}@rb-report.local>'):
            return {'status':'ALREADY_ATTEMPTED'}
        try:
            # Authentication/state claiming can cross the dispatch minute.
            # Re-render only the delivery annotation, never the computation.
            checked=clock()
            msg=message(view(report,checked),sender,recipient)
            final=clock()
            if final.astimezone(ZoneInfo('America/New_York')).strftime('%Y-%m-%d %H:%M') != checked.astimezone(ZoneInfo('America/New_York')).strftime('%Y-%m-%d %H:%M'):
                msg=message(view(report,final),sender,recipient)
            refused=smtp.send_message(msg)
            if refused:
                raise RuntimeError('recipient refused')
        except Exception as exc:
            store.finish_delivery(session,'unknown',type(exc).__name__)
            raise RuntimeError('SMTP outcome ambiguous; inspect provider using Message-ID before retry') from exc
        store.finish_delivery(session,'sent',msg['Message-ID'])
    return {'status':'SENT','message_id':msg['Message-ID']}


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--state-dir',default=os.getenv('RB_STATE_DIR','.rb-state'))
    p.add_argument('--session',default=dt.datetime.now(ZoneInfo('America/New_York')).date().isoformat())
    # No argparse `default=` from the environment here: the defaults would be
    # evaluated before the credential files are read, so --state-dir would be
    # ignored for exactly the values it is supposed to supply. That is the
    # day-110c defect — a credential that never reaches the thing needing it.
    p.add_argument('--to')
    p.add_argument('--from',dest='sender')
    p.add_argument('--eml',help='render a reviewable email without sending')
    a=p.parse_args(argv)
    try:
        smtp_credential.load_private_smtp(a.state_dir)
    except ValueError as exc:
        print(json.dumps(dict(status='NOT_SENT', reason=str(exc))))
        return 2
    a.to=a.to or os.environ.get('RB_REPORT_TO')          # explicit flag wins,
    a.sender=a.sender or os.environ.get('RB_SMTP_USER')  # then file/env
    if not a.to or not a.sender:
        # Exit 2, not argparse's 2-with-usage-dump: an unconfigured channel is
        # an ordinary reportable state, not a caller error, and the morning
        # needs to tell them apart to print the right remedy.
        print(json.dumps(dict(status='NOT_SENT', reason='NO_SMTP_CREDENTIAL',
                              remedy=smtp_credential.REMEDY)))
        return 2
    store=Store(a.state_dir)
    if a.eml:
        Path(a.eml).write_bytes(message(store.get(a.session),a.sender,a.to).as_bytes())
        return 0
    try:
        print(send(store,a.session,a.sender,a.to))
    except ValueError as exc:
        # A half-configured channel (an address but no password) is still an
        # unconfigured channel, and the morning must not read a traceback as a
        # provider failure — the two need different remedies.
        if 'credential missing' not in str(exc):
            raise
        print(json.dumps(dict(status='NOT_SENT', reason=str(exc))))
        return 2
    return 0

if __name__=='__main__':
    raise SystemExit(main())
