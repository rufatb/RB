#!/usr/bin/env python3
"""PICKS ONLY: the desks' sealed pre-open picks, emailed when the full report fails.

OWNER, 2026-09-28: "make sure this 100% sends every morning before 10am".

The picks are made before the open, sealed to disk (Claude by 09:24; DeepSeek
and Jev before 09:30), and the 09:46 report only RENDERS them. When `morning.sh`
fails after staging — an integrity refusal, a crash, a missed window — the
picks still exist, and throwing them away to rebuild a LATE answer after the
open would trade a pre-open opinion for a worse, after-the-fact one. This
composes an email from those snapshots in under a second, with no network
call, so a failed publication still reaches the inbox before 10:00.

It uses the same pure readers as the report (`load_prepared`: seal checked,
session and pre-open clock checked), the same tables as the email, and records
the picks exactly as the report would have (`model_picks.rows_from_report`,
source `picks_only`). Nothing here is sized: without the 09:46 quote check no
share count is honest.

Exit 0: at least one desk had a pick. Exit 2: nothing was staged — the caller
falls back to `late_picks.py`.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from pathlib import Path
from zoneinfo import ZoneInfo

ET = ZoneInfo('America/New_York')
ROOT = Path(__file__).resolve().parent
ARTIFACT_URL = 'https://claude.ai/artifact/28ZfvwVZG1A2yagxJ4Hyt9'


def load(state_dir, now):
    """The three sealed snapshots, each through its own pure reader."""
    import claude_opportunities
    import deepseek_opportunities
    import jev_opportunities
    out = {}
    for key, module in (('claude', claude_opportunities), ('opportunities', deepseek_opportunities),
                        ('jev', jev_opportunities)):
        try:
            out[key] = module.load_prepared(state_dir, now)
        except Exception as exc:
            out[key] = {'status': 'UNAVAILABLE', 'reason': 'unreadable (%s)' % type(exc).__name__}
    return out


def has_picks(snaps):
    return any(s.get(k) for s in snaps.values() if isinstance(s, dict)
               for k in ('longs', 'shorts')) or bool(
        snaps['jev'].get('forced_long') or snaps['jev'].get('forced_short'))


def compose(state_dir, *, now=None, reason='the full report did not publish'):
    import email_render as E
    import late_picks
    from diagnostics import safe_detail
    now = now or dt.datetime.now(ET)
    root = Path(state_dir)
    snaps = dict(load(root, now))
    session = now.date().isoformat()
    subject = 'RB Daily Report — %s — PICKS ONLY (%s)' % (session, safe_detail(reason, 80))

    def desk(title, snap):
        out = ['', '### ' + title]
        if snap.get('status') not in ('READY', 'NO_OPPORTUNITY'):
            return out + ['Unavailable — %s' % safe_detail(snap.get('reason') or 'not staged', 160)]
        return out + (E.pick_table(snap) or ['No pick today: nothing worth a position on either side.'])
    jev = snaps['jev']
    import top_picks
    snaps['top_two'] = top_picks.select(snaps['claude'], snaps['opportunities'], jev)
    body = (['# RB Daily Report — %s — PICKS ONLY' % session,
             'Sent %s ET from the picks sealed before the open.' % now.strftime('%H:%M'),
             'The full 09:46 report did not publish today: %s. These are the desks\' own '
             'picks, sealed BEFORE the open and unchanged; without the 09:46 quote check '
             'nothing is sized. Research only — not orders.' % safe_detail(reason, 160),
             '', *top_picks.table(snaps['top_two']),
             '', '## Part 1 — Picks, sealed before the open']
            + desk('1 · Claude', snaps['claude'])
            + desk('2 · DeepSeek', snaps['opportunities'])
            + ['', '### 3 · Jev']
            + (E.jev_forced_table(jev) if jev.get('status') in ('READY', 'NO_OPPORTUNITY')
               else ['Unavailable — %s' % safe_detail(jev.get('reason') or 'not staged', 160)])
            + late_picks.biotech_part(root, now)
            + ['', '---', 'Confidences are each model\'s own, never averaged. Page: ' + ARTIFACT_URL])
    text = '\n'.join(body) + '\n'
    out = root/'picks_only'
    out.mkdir(parents=True, exist_ok=True)
    (out/'subject.txt').write_text(subject)
    (out/'report.txt').write_text(text)
    (out/'report.html').write_text(E.html_from_text(text))
    return {'subject': subject, 'subject_path': str(out/'subject.txt'),
            'text_path': str(out/'report.txt'), 'html_path': str(out/'report.html'),
            'has_picks': has_picks(snaps), 'snaps': snaps}


def record(snaps, session, path=None):
    """The picks as the report would have recorded them (source picks_only)."""
    import model_picks
    report = {'session': session, 'intraday': {k: v for k, v in snaps.items()}}
    return model_picks.append(model_picks.rows_from_report(report, source='picks_only'),
                              path or model_picks.LEDGER)


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    p.add_argument('--state-dir', default='.rb-state')
    p.add_argument('--reason', default='the full report did not publish')
    p.add_argument('--no-record', action='store_true')
    a = p.parse_args(argv)
    now = dt.datetime.now(ET)
    out = compose(a.state_dir, now=now, reason=a.reason)
    if out['has_picks'] and not a.no_record:
        out['recorded'] = record(out['snaps'], now.date().isoformat())
    out.pop('snaps')
    print(json.dumps(out, indent=1))
    return 0 if out['has_picks'] else 2


if __name__ == '__main__':
    sys.exit(main())
