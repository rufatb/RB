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
from report_store import Store
from build_biotech import write_atomic


def run(state_dir,output_dir):
    now=dt.datetime.now(ZoneInfo('America/New_York'))
    store=Store(state_dir);report=store.get(now.date().isoformat())
    failure=None
    if report is None:
        try:
            report=brief.compute(publish=True,state_dir=state_dir)
        except Exception as exc:
            failure=type(exc).__name__
            # Catastrophic local model/schema failure only. Ordinary provider
            # timeouts are isolated in brief and never trigger this fallback.
            report=brief.compute(no_net=True,now=now,state_dir=state_dir)
            report['report_status']='DATA OUTAGE — informational only'
            report['errors'].append({'layer':'daily_job','error':failure,
                                     'detail':'Local report assembly failed; recorded state retained, live scan unavailable.'})
        # Also persist diagnostics/closed-session reports; zero picks is a result.
        report=store.publish(now.date().isoformat(),report)
    end=dt.datetime.now(ZoneInfo('America/New_York'))
    if end.strftime('%H:%M')!='09:46' or end.date().isoformat()!=report['session']:
        report={**report,'report_status':'INFORMATIONAL — outside 09:46 delivery minute; '+report['report_status']}
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
    if a.send:
        from deliver_report import send
        sender=os.environ.get('RB_SMTP_USER');recipient=os.environ.get('RB_REPORT_TO')
        if not sender or not recipient:raise ValueError('email sender/recipient not configured')
        print(send(Store(a.state_dir),report['session'],sender,recipient))
    else:
        print(brief.render_text(report))
    return 0

if __name__=='__main__':
    raise SystemExit(main())
