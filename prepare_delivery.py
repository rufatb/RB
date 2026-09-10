#!/usr/bin/env python3
"""Render one frozen publication for Gmail at the actual dispatch clock.

No acquisition, selection, state mutation or send. Claim/persist delivery
separately before invoking this immediately ahead of Gmail transmission.
"""
import argparse
import copy
import datetime as dt
import json
from pathlib import Path
from zoneinfo import ZoneInfo
import brief
from report_store import Store

ET = ZoneInfo('America/New_York')


def view(report, now=None):
    now = now or dt.datetime.now(ET)
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError('aware dispatch clock required')
    now = now.astimezone(ET)
    if now.date().isoformat() == report['session'] and now.time() < dt.time(9, 46):
        raise ValueError('do not deliver before 09:46 ET')
    out = copy.deepcopy(report)
    on_time = now.date().isoformat() == report['session'] and now.strftime('%H:%M') == '09:46'
    partial = (out.get('offline') or out.get('readiness', {}).get('status') != 'READY'
               or out['report_status'] != 'ON_TIME')
    status = 'ON_TIME' if on_time and not partial else 'INFORMATIONAL'
    note = ('Within the 09:46 dispatch minute; inbox arrival is not guaranteed.'
            if on_time else 'Outside the publication delivery window; no fresh morning entry claim.')
    if partial:
        note += ' Partial or unavailable data; retain the section-specific gaps.'
    out['publication_status'] = report.get('publication_status', report['report_status'])
    out['report_status'] = status + (' / PARTIAL DATA' if partial else '')
    out['delivery'] = dict(checked_at=now.isoformat(), status=status, note=note)
    return out


def artifacts(report, directory, now=None):
    out = view(report, now)
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    subject = f"RB Daily Report — {out['session']}"
    if out['report_status'] != 'ON_TIME':
        subject += ' — ' + out['report_status']
    payload = dict(subject=subject, text=brief.render_text(out), html=brief.render_html(out),
                   session=out['session'], checked_at=out['delivery']['checked_at'])
    (directory/'report.json').write_text(json.dumps(out, indent=2, allow_nan=False))
    (directory/'report.txt').write_text(payload['text'])
    (directory/'report.html').write_text(payload['html'])
    (directory/'gmail_payload.json').write_text(json.dumps(payload, indent=2, allow_nan=False))
    return payload


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--state-dir', required=True)
    p.add_argument('--session', required=True)
    p.add_argument('--output-dir', required=True)
    a = p.parse_args(argv)
    report = Store(a.state_dir).get(a.session)
    if report is None:
        raise ValueError('no immutable publication; run daily_job.py first')
    payload = artifacts(report, a.output_dir)
    print(json.dumps(dict(subject=payload['subject'], checked_at=payload['checked_at'])))


if __name__ == '__main__':
    main()
