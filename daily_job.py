#!/usr/bin/env python3
"""Bounded daily runner: one model, three artifacts, one email or explicit outage.

Run at 09:46 ET. Data preparation is a separate pre-open job. Read-only market
acquisition uses independent killable section budgets inside brief.compute.
The Gmail automation uses the same artifacts as SMTP.
"""
from __future__ import annotations
import argparse
import datetime as dt
import os
from pathlib import Path
from zoneinfo import ZoneInfo
import brief
import execution
from report_store import Store
from build_biotech import write_atomic


def run(state_dir,output_dir,now=None,*,clock=None):
    """Freeze, render and write the day. `now` is injectable for tests.

    WHY THE CLOCK IS A PARAMETER (day-94). This read the wall clock directly,
    so `test_catastrophic_assembly_failure_emits_one_frozen_outage` could only
    pass on 2026-09-08: it froze the report under the REAL date while the test
    looked it up under its fixed NOW. The outage path itself was correct all
    along -- it does write "DATA OUTAGE - informational only" -- but a test
    that expires the day after it is written cannot guard anything, and this
    one was already failing silently in the suite.

    Production is unchanged: `now=None` reads the live clock exactly as before.
    """
    if now is not None and clock is not None:
        raise ValueError('supply now or clock, not both')
    injected = now is not None or clock is not None
    fixed = now
    clock = clock or ((lambda:fixed) if fixed is not None else
                     (lambda:dt.datetime.now(ZoneInfo('America/New_York'))))
    now = clock()
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError('aware publication clock required')
    now=now.astimezone(ZoneInfo('America/New_York'))
    if now.time() < dt.time(9,46):
        raise ValueError('do not publish before 09:46 ET')
    store=Store(state_dir);report=store.get(now.date().isoformat())
    failure=None
    if report is None:
        try:
            report=brief.compute(publish=True,state_dir=state_dir,**({'now':now} if injected else {}))
        except Exception as exc:
            failure=type(exc).__name__
            # Catastrophic local model/schema failure only. Ordinary provider
            # timeouts are isolated in brief and never trigger this fallback.
            report=brief.compute(no_net=True,now=now,state_dir=state_dir)
            report['report_status']='DATA OUTAGE — informational only'
            report['errors'].append({'layer':'daily_job','error':failure,
                                     'detail':'Local report assembly failed; recorded state retained, live scan unavailable.'})
        # A report whose session disagrees with the publication clock is an
        # assembly error, not an alarm: refuse before anything else (fail
        # closed), on every path including the NOT RECORDED one.
        if report['session'] != now.date().isoformat():
            raise ValueError('assembled report session does not match publication clock')
        # DAY-95b (C2): an eligible trading day that recorded NOTHING must not
        # be frozen as an informational report -- publish-once would then mask
        # the miss forever (that is exactly how 2026-09-09 disappeared from
        # the ledger after being emailed). Alarm instead; the email carries a
        # 'NOT RECORDED — ' subject and the job exits 7. Holidays/CLOSED days
        # stay quiet informational and are frozen as before.
        if failure is None and brief.record_missed(report):
            report={**report,'report_status':'NOT RECORDED — the publication '
                    'window was eligible but no board was recorded; '
                    +report['report_status']}
        else:
            # Also persist diagnostics/closed-session reports; zero picks is a result.
            report=store.publish(now.date().isoformat(),report)
    # Injected clock also governs the delivery-window check, so a test can
    # pin the whole job rather than half of it. Day-95b: the delivery window is
    # the publication window (09:46:00-09:49:59 ET), not a single minute.
    end=clock().astimezone(ZoneInfo('America/New_York'))
    if report['report_status'].startswith('NOT RECORDED'):
        pass  # the alarm status must survive; never relabel it informational
    elif not execution.in_publish_window(end) or end.date().isoformat()!=report['session']:
        report={**report,'report_status':'INFORMATIONAL — outside the 09:46-09:50 delivery window; '+report['report_status']}
    directory=Path(output_dir);directory.mkdir(parents=True,exist_ok=True)
    write_atomic(directory/'report.json',report)
    (directory/'report.txt').write_text(brief.render_text(report))
    (directory/'report.html').write_text(brief.render_html(report))
    return report


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--state-dir',default=os.getenv('RB_STATE_DIR','.rb-state'))
    p.add_argument('--output-dir',default='.rb-state/latest')
    p.add_argument('--send',action='store_true')
    a=p.parse_args(argv);report=run(a.state_dir,a.output_dir)
    not_recorded=report['report_status'].startswith('NOT RECORDED')
    if a.send:
        from deliver_report import send, send_report
        sender=os.environ.get('RB_SMTP_USER');recipient=os.environ.get('RB_REPORT_TO')
        if not sender or not recipient:raise ValueError('email sender/recipient not configured')
        if not_recorded:
            # Deliberately UNFROZEN (day-95b C2): no Store row exists to claim
            # delivery against, and the alarm must still reach the inbox.
            print(send_report(report,sender,recipient))
        else:
            print(send(Store(a.state_dir),report['session'],sender,recipient))
    else:
        print(brief.render_text(report))
    return 7 if not_recorded else 0

if __name__=='__main__':
    raise SystemExit(main())
