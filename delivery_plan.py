#!/usr/bin/env python3
"""What to email this morning, decided by ONE command, never by prose.

OWNER, 2026-09-28: "make sure this 100% sends every morning before 10am".

The morning had one good outcome and two silent ones: the report published and
was emailed, or the report session died and nothing arrived until a late
fallback ran after 10:00 (2026-09-24, 09-28). The ladder below always ends in
something sendable, and a script chooses the rung so an agent cannot talk
itself onto the wrong one:

  REPORT      today's immutable publication exists → the real email, prepared
              and claimed by `gmail_delivery.prepare` (the publish-once record)
  PICKS_ONLY  no publication, but the desks' pre-open picks were sealed →
              `picks_only.compose`, under a second, no network
  LATE        nothing sealed at all → the caller runs `late_picks.py`

It prints one JSON object: `mode`, and for REPORT / PICKS_ONLY the exact
`subject_path`, `text_path` and `html_path` to send VERBATIM. It never sends:
the Gmail tool belongs to the agent, which checks the inbox first.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from pathlib import Path
from zoneinfo import ZoneInfo

ET = ZoneInfo('America/New_York')


def plan(state_dir, *, now=None, reason=None, record=True):
    now = (now or dt.datetime.now(ET)).astimezone(ET)
    root = Path(state_dir)
    session = now.date().isoformat()
    try:
        from report_store import Store
        published = Store(root).get(session) is not None
    except Exception:
        published = False
    if published:
        import gmail_delivery
        out = gmail_delivery.prepare(root, session, str(root/'dispatch'), now=now)
        if out['status'] == 'CLAIMED':
            return {'mode': 'REPORT', **{k: out[k] for k in ('subject_path', 'text_path', 'html_path')},
                    'claimed': True}
        # Already claimed by an earlier attempt: the files are on disk. The
        # agent's inbox check decides whether that attempt actually arrived.
        paths = {k: str(root/'dispatch'/f) for k, f in (('subject_path', 'subject.txt'),
                 ('text_path', 'report.txt'), ('html_path', 'report.html'))}
        if all(Path(p).exists() for p in paths.values()) and \
                session in Path(paths['subject_path']).read_text():
            return {'mode': 'REPORT', **paths, 'claimed': False,
                    'note': 'delivery was already claimed; send only if the inbox has no report for today'}
    import picks_only
    why = reason or ('the report published but its email could not be prepared' if published
                     else 'the full report did not publish')
    out = picks_only.compose(root, now=now, reason=why)
    if out['has_picks']:
        if record:
            picks_only.record(out['snaps'], session)
        return {'mode': 'PICKS_ONLY', **{k: out[k] for k in ('subject_path', 'text_path', 'html_path')}}
    return {'mode': 'LATE', 'why': 'nothing was sealed before the open; run late_picks.py'}


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    p.add_argument('--state-dir', default='.rb-state')
    p.add_argument('--reason', help='why the full report is missing, for the PICKS ONLY subject')
    p.add_argument('--no-record', action='store_true')
    a = p.parse_args(argv)
    out = plan(a.state_dir, reason=a.reason, record=not a.no_record)
    print(json.dumps(out, indent=1))
    return 0


if __name__ == '__main__':
    sys.exit(main())
