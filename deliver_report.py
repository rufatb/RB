#!/usr/bin/env python3
"""Send one frozen multipart report; do not recompute at delivery time.

SMTP credentials are environment-only. A crash/timeout after DATA has ambiguous
acceptance: persist UNKNOWN and require provider reconciliation rather than
blindly sending a duplicate. A deterministic Message-ID is a reconciliation
key, not a claim of exactly-once SMTP semantics.
"""
from __future__ import annotations
import argparse
import datetime as dt
from email.message import EmailMessage
from email.utils import format_datetime
import os
import smtplib
import ssl
from pathlib import Path
from zoneinfo import ZoneInfo
import brief
import email_render
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


def send(store,session,sender,recipient,*,smtp_factory=smtplib.SMTP_SSL,now=None):
    report=store.get(session)
    if not report:
        raise ValueError('no immutable report to send')
    # Re-read the clock at the actual sending boundary. A report built on time
    # but queued for 20 minutes must not look executable in the inbox.
    now=now or dt.datetime.now(ZoneInfo('America/New_York'))
    report = view(report, now)
    msg=message(report,sender,recipient)
    if store.delivery(session):
        return {'status':'ALREADY_ATTEMPTED','delivery':store.delivery(session)}
    host=os.environ.get('RB_SMTP_HOST','smtp.gmail.com')
    user=os.environ.get('RB_SMTP_USER');password=os.environ.get('RB_SMTP_PASSWORD')
    if not user or not password:
        raise ValueError('RB_SMTP_USER / RB_SMTP_PASSWORD missing; no email attempted')
    # Authenticate before claiming. Failures here cannot have sent DATA.
    with smtp_factory(host,465,context=ssl.create_default_context(),timeout=20) as smtp:
        smtp.login(user,password)
        if not store.claim_delivery(session,msg['Message-ID']):
            return {'status':'ALREADY_ATTEMPTED'}
        try:
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
    p.add_argument('--to',default=os.getenv('RB_REPORT_TO'))
    p.add_argument('--from',dest='sender',default=os.getenv('RB_SMTP_USER'))
    p.add_argument('--eml',help='render a reviewable email without sending')
    a=p.parse_args(argv)
    if not a.to or not a.sender: p.error('recipient and sender required')
    store=Store(a.state_dir)
    if a.eml:
        Path(a.eml).write_bytes(message(store.get(a.session),a.sender,a.to).as_bytes())
    else:
        print(send(store,a.session,a.sender,a.to))
    return 0

if __name__=='__main__':
    raise SystemExit(main())
