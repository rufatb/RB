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
import email_render
from report_store import Store

ET = ZoneInfo('America/New_York')


DISPATCH_GRACE_END = dt.time(10, 0)


def view(report, now=None):
    now = now or dt.datetime.now(ET)
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError('aware dispatch clock required')
    now = now.astimezone(ET)
    diagnostic = ((report.get('provenance', {}).get('factor_diagnostic') or {}).get('kind')
                  == 'CURRENT_TIME_DIAGNOSTIC' and report.get('offline') is True)
    if not diagnostic and now.date().isoformat() == report['session'] and now.time() < dt.time(9, 46):
        raise ValueError('do not deliver before 09:46 ET')
    out = copy.deepcopy(report)
    # DISPATCH GRACE (day-114b). The rule used to be "the 09:46 MINUTE or it is
    # INFORMATIONAL", written when the email was meant to leave inside that
    # minute. It never does — the send runs 09:47-09:55 — so every email was
    # stamped INFORMATIONAL and "no fresh morning entry claim", and PARTIAL
    # DATA was added every day because two readiness gaps are permanent. A
    # label on every email is no label. Now: sent before 10:00 the body states
    # plainly that prices are the 09:46 snapshot and when it was sent; after
    # 10:00, or for a board published late or offline, it is INFORMATIONAL as
    # before. Each section states its own gaps; the header no longer does.
    same_day = now.date().isoformat() == report['session']
    on_time = same_day and dt.time(9, 46) <= now.time() < DISPATCH_GRACE_END
    published_late = out.get('offline') or not str(out['report_status']).startswith('ON_TIME')
    status = 'ON_TIME' if on_time and not published_late else 'INFORMATIONAL'
    note = ('Prices are the 09:46 ET snapshot; sent %s ET.' % now.strftime('%H:%M')
            if status == 'ON_TIME' else
            'Sent %s ET, after the morning window: the 09:46 prices are stale and this is '
            'informational, not a fresh entry claim.' % now.strftime('%H:%M'))
    out['publication_status'] = report.get('publication_status', report['report_status'])
    out['report_status'] = status
    if diagnostic:
        out['report_status'] = 'CURRENT-TIME DEEPSEEK DIAGNOSTIC / INFORMATIONAL — NOT A MORNING SIGNAL'
        note = 'Explicit current-time diagnostic; no morning publication, entry or predictive-accuracy claim.'
        status = 'INFORMATIONAL'
    out['delivery'] = dict(checked_at=now.isoformat(), status=status, note=note)
    return out


def subject_state(report):
    """Expose the most severe computed execution status in the inbox subject.

    Missing acquisition, recorded selections and a fully evaluated empty board
    are distinct states. None establishes a fresh validated entry. This pure
    summary does not infer the cause of a user's trading outcome.
    """
    intraday = report.get('intraday') or {}
    # The subject describes PART 1'S HEADLINE: the three desks' legs when any
    # desk has one, otherwise the engine's, exactly as before. A subject computed
    # from the demoted board could say DO NOT TRADE over a sized desk, or stay
    # neutral over abstained ones.
    from primary_board import headline_legs
    legs = headline_legs(intraday)
    status = str(report.get('report_status') or '')
    if 'DATA OUTAGE' in status:
        return '⛔ DATA OUTAGE — DO NOT TRADE — '
    if not legs:
        if any(r.get('role') == 'pair' for r in intraday.get('recorded_today', [])):
            return 'RECORDED BOARD — no fresh entry validation — '
        if (intraday.get('res') or {}).get('coverage_fail') or report.get('offline'):
            return '⛔ SCAN UNAVAILABLE — no verified entries — '
        return '⛔ NO LEGS SELECTED — nothing to act on — '
    abstained = [l for l in legs if str(l.get('status')).upper() == 'ABSTAIN']
    if len(abstained) == len(legs):
        return f'⛔ DO NOT TRADE — all {len(legs)} legs ABSTAINED — '
    if abstained:
        return f'⚠ {len(abstained)}/{len(legs)} legs ABSTAINED — '
    if status != 'ON_TIME':
        return 'INFORMATIONAL — '
    return ''


def subject(report):
    if (report.get('provenance', {}).get('factor_diagnostic') or {}).get('kind') == 'CURRENT_TIME_DIAGNOSTIC':
        return f"RB Daily Report — {report['session']} — CURRENT-TIME DEEPSEEK DIAGNOSTIC / INFORMATIONAL"
    prefix=subject_state(report).strip(' —')
    pieces=[f"RB Daily Report — {report['session']}"]
    if not str(report['report_status']).startswith('ON_TIME'):pieces.append('INFORMATIONAL')
    if prefix and prefix!='INFORMATIONAL':pieces.append(prefix)
    elif not prefix:pieces.append('Intraday + Biotech')
    return ' — '.join(pieces)


def artifacts(report, directory, now=None):
    out = view(report, now)
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    # Same guard as the SMTP path (deliver_report imports this function), so
    # the Gmail automation cannot ship a neutral-looking subject for a board
    # nobody should act on.
    title=subject(out)
    full_html=brief.render_html(out)
    payload = dict(subject=title, text=email_render.text(out), html=email_render.html(out),
                   attachments=[dict(filename=f"RB-Full-Report-{out['session']}.html",mime_type='text/html',content=full_html)],
                   session=out['session'], checked_at=out['delivery']['checked_at'])
    (directory/'report.json').write_text(json.dumps(out, indent=2, allow_nan=False))
    (directory/'report.txt').write_text(payload['text'])
    (directory/'report.html').write_text(payload['html'])
    (directory/'full_report.html').write_text(full_html)
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
