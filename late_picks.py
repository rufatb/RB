#!/usr/bin/env python3
"""Late picks: when the 09:46 report did not publish, still deliver the three desks — labelled LATE.

WHY THIS EXISTS. 2026-09-24: the scheduled report session ended its turn at
08:54 with `morning_full.sh` in the background, its container was reclaimed,
and nothing published. The bridge's only move was to wait until 10:30 and send
"NOT PUBLISHED". The owner got no picks at all on a day every provider was
healthy. A missing report is a delivery failure; it must not also be a missing
morning.

WHAT THIS IS NOT. It is not the report. The report's picks are asked BEFORE the
open and sealed; these are asked AFTER it, in the isolated diagnostic context,
with the same code and the same question. Every line says so. Nothing here is
sized, recorded in the ledger, or scored on the scoreboard — a ranking asked at
10:05 knows the first half hour, and scoring it beside pre-open picks would
flatter it. Read-only research: nothing places an order.

    python late_picks.py --state-dir DIR --stage          pool, news, DeepSeek, Jev; writes the Claude brief
    python late_picks.py --state-dir DIR --check ANSWER   what the compose step would drop, without composing
    python late_picks.py --state-dir DIR --seal ANSWER    Claude's answer + the other two -> DIR/late/{subject,report}.*

The session running it IS the Claude desk: it reads DIR/claude_brief.txt and
answers it exactly as the morning session would.
"""
from __future__ import annotations

import argparse
import datetime as dt
import html
import json
import os
import shutil
import sys
from pathlib import Path
from zoneinfo import ZoneInfo

import yaml

import claude_opportunities as C
import deepseek_opportunities as O

ET = ZoneInfo('America/New_York')
ROOT = Path(__file__).resolve().parent
ARTIFACT_URL = 'https://claude.ai/artifact/28ZfvwVZG1A2yagxJ4Hyt9'
BRIEF_JSON = 'late_claude_brief.json'
RANKED_SHOWN = 3


def _now(now=None):
    return (now or dt.datetime.now(ET)).astimezone(ET)


def _cfg():
    return yaml.safe_load((ROOT/'config.yaml').read_text())


def stage(state_dir, *, now=None, secrets_from=ROOT/'.rb-state'/'secrets', log=print):
    """Stage every desk's input in an isolated diagnostic context. Each step's
    failure costs that step only and is logged by name (house rule 1)."""
    import diagnostic_context
    root = Path(state_dir)
    if not root.exists():
        diagnostic_context.create_context(root)
        (root/'secrets').mkdir(mode=0o700)
        for name in ('deepseek_api_key', 'openrouter_api_key'):
            src = Path(secrets_from)/name
            if src.exists():
                shutil.copy(src, root/'secrets'/name)
                os.chmod(root/'secrets'/name, 0o600)
        (root/'deepseek_model.txt').write_text('deepseek-flash\n')
    cfg = _cfg()
    steps = []
    def step(name, fn):
        try:
            fn()
            steps.append((name, 'OK'))
        except Exception as exc:  # recorded, never swallowed
            steps.append((name, 'FAILED %s: %s' % (type(exc).__name__, str(exc)[:160])))
        log('[%s] %s' % (name, steps[-1][1]))
    import prepare_factor_pool
    import prepare_deepseek
    import jev_opportunities as J
    step('pool', lambda: prepare_factor_pool.prepare_diagnostic(root, cfg))
    step('news', lambda: (prepare_deepseek.load_private_key(root),
                          prepare_deepseek.prepare_diagnostic(root, cfg, refresh=True)))
    step('claude_brief', lambda: write_brief(root, cfg, _now(now)))
    step('deepseek', lambda: O.stage(root, diagnostic=True))
    step('jev', lambda: J.stage(root, diagnostic=True))
    (root/'late_steps.json').write_text(json.dumps(steps))
    return steps


def write_brief(root, cfg, now):
    from factor_inputs import build_from_state
    staged = build_from_state(root, cfg, now, diagnostic=True)
    request = O.build_request(staged['candidates'], staged.get('macro'), now)
    if request is None:
        raise ValueError('NO_COMPLETE_CANDIDATES')
    answer = root/C.ANSWER_NAME
    brief = {'session': now.date().isoformat(), 'prepared_at': now.isoformat(),
             'payload': request['payload'], 'universe': sorted(request['allowed']),
             'considered': request['considered'], 'evidence': request['evidence'],
             'answer_path': str(answer),
             'seal_command': f'python late_picks.py --state-dir {root} --seal {answer}'}
    (root/BRIEF_JSON).write_text(json.dumps(brief))
    text = C.brief_text(brief).replace(
        f'The seal refuses at or after {C.CUTOFF:%H:%M} ET.',
        f'LATE: asked at {now:%H:%M} ET, after the open; the morning report did not publish.')
    (root/C.BRIEF_TEXT).write_text(text)
    return brief


def _brief(root):
    return json.loads((Path(root)/BRIEF_JSON).read_text())


def claude_picks(root, answer):
    brief = _brief(root)
    allowed = set(brief['universe'])
    rows = brief['payload']['candidates']
    out, problems = {}, []
    for side, key in (('LONG', 'longs'), ('SHORT', 'shorts')):
        picks, gaps = O._clean(answer.get(key), allowed, side.lower())
        gaps += O.check_levels(picks, side, rows)
        out[key] = picks
        problems += gaps
    return out, problems, brief


def check(root, answer):
    return claude_picks(root, answer)[1]


def _pick_line(side, p):
    wrong = (' Wrong if %s %s.' % ('below' if side == 'LONG' else 'above', p['invalid_at'])
             if p.get('invalid_at') is not None else '')
    conf = p.get('confidence')
    conf = ' (own confidence %.2f)' % conf if isinstance(conf, (int, float)) else ''
    return '- %s %s%s — %s%s' % (side, p['ticker'], conf, p.get('reason') or '', wrong)


def _desk(title, result, picks=None):
    lines = ['', title]
    if picks is None and not isinstance(result, dict):
        return lines + ['Unavailable.']
    picks = picks if picks is not None else result
    if result is not None and isinstance(result, dict) and result.get('status') == 'UNAVAILABLE':
        return lines + ['Unavailable — %s' % (result.get('reason') or 'no reason given')]
    rows = ([_pick_line('LONG', p) for p in picks.get('longs') or []]
            + [_pick_line('SHORT', p) for p in picks.get('shorts') or []])
    return lines + (rows or ['No pick: nothing cleared its own bar today.'])


def _jev(result):
    lines = ['', '3 · Jev']
    if not isinstance(result, dict) or result.get('status') == 'UNAVAILABLE':
        return lines + ['Unavailable — %s' % ((result or {}).get('reason') or 'not staged')]
    for side, key in (('LONG', 'longs'), ('SHORT', 'shorts')):
        for p in result.get(key) or []:
            lines.append('- SELECTED %s %s — probability %.2f vs its own "none" %.2f'
                         % (side, p['ticker'], p.get('probability', 0), p.get('abstain_probability', 0)))
    if not (result.get('longs') or result.get('shorts')):
        lines.append('Selected nothing: no name beat its own "none of these" option (the registered gate).')
    for side, key in (('LONG', 'long_ranked'), ('SHORT', 'short_ranked')):
        ranked = (result.get(key) or [])[:RANKED_SHOWN]
        if ranked:
            lines.append('Ranked %s (a ranking, NOT a selection): ' % side + ', '.join(
                '%s %.2f%s' % (r['ticker'], r.get('probability', 0),
                               '' if r.get('cleared_gate') else ' (below its own "none")') for r in ranked))
    for side, key in (('LONG', 'forced_long'), ('SHORT', 'forced_short')):
        f = result.get(key)
        if isinstance(f, dict) and f.get('ticker'):
            tail = ('' if f.get('cleared_gated_abstain')
                    else ' — below its own abstain: Jev would rather have done nothing')
            lines.append('Forced %s (best of the set, never a selection): %s %.2f vs abstain %.2f%s'
                         % (side, f['ticker'], f.get('probability', 0),
                            f.get('gated_abstain_probability', 0), tail))
    return lines


def _biotech(now):
    try:
        import biotech
        snap_path = ROOT/'data'/'biotech_snapshot.json'
        universe = {s['ticker'] for s in biotech.select_universe(json.loads(snap_path.read_text()), now)}
        events = json.loads((ROOT/'data'/'biotech_events.json').read_text())['events']
    except Exception as exc:
        return ['', 'Biotech catalysts', 'Unavailable (%s).' % type(exc).__name__]
    rows = [e for e in events if e['ticker'] in universe]
    lines = ['', 'Biotech catalysts (3–6 months; factual, no directional call)']
    for e in sorted(rows, key=lambda e: e['window_end']):
        when = e['window_start'] if e['window_start'] == e['window_end'] else '%s to %s' % (e['window_start'], e['window_end'])
        lines.append('- %s %s — %s (%s), %s. Source: %s' % (e['ticker'], e['kind'], e['asset'],
                                                          e['indication'], when, e['source_url']))
    return lines + ([] if rows else ['No reviewed event on a monitored name.'])


def compose(root, answer, *, now=None, reason='the scheduled report session stopped before publication'):
    now = _now(now)
    root = Path(root)
    import jev_opportunities as J
    picks, problems, brief = claude_picks(root, answer)
    try:
        deepseek = O.load_diagnostic(root, now)
    except Exception as exc:
        deepseek = O.unavailable('diagnostic snapshot unreadable (%s)' % type(exc).__name__)
    try:
        jev = J.load_diagnostic(root, now)
    except Exception as exc:
        jev = J.unavailable('diagnostic snapshot unreadable (%s)' % type(exc).__name__)
    session = now.date().isoformat()
    subject = 'RB Daily Report — %s — LATE PICKS (the 09:46 report did not publish)' % session
    head = ['RB Daily Report — %s — LATE PICKS' % session,
            'The 09:46 report did not publish today: %s.' % reason,
            'These picks were asked at %s ET, AFTER the open, by the same pipeline in its '
            'diagnostic mode, from %d names. They are not the frozen report: not sized, not '
            'recorded, not scored. Research only — not orders.' % (now.strftime('%H:%M'), brief['considered']),
            'Confidence numbers are each model\'s own, not calibrated win probabilities; the '
            'models are never averaged.']
    body = (head + _desk('1 · Claude', {'status': 'READY'}, picks)
            + (['  (dropped: %s)' % '; '.join(problems)] if problems else [])
            + _desk('2 · DeepSeek', deepseek) + _jev(jev) + _biotech(now)
            + ['', 'Page: ' + ARTIFACT_URL])
    text = '\n'.join(body) + '\n'
    html_body = '<html><body style="font-family:sans-serif">' + ''.join(
        ('<h3>%s</h3>' % html.escape(l)) if l[:2] in ('1 ', '2 ', '3 ') or l.startswith('Biotech')
        else ('<p>%s</p>' % html.escape(l) if l else '') for l in body) + '</body></html>'
    out = root/'late'
    out.mkdir(exist_ok=True)
    (out/'subject.txt').write_text(subject)
    (out/'report.txt').write_text(text)
    (out/'report.html').write_text(html_body)
    return {'subject': subject, 'subject_path': str(out/'subject.txt'),
            'text_path': str(out/'report.txt'), 'html_path': str(out/'report.html'),
            'claude_dropped': problems}


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    p.add_argument('--state-dir', required=True)
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument('--stage', action='store_true')
    g.add_argument('--check', metavar='ANSWER')
    g.add_argument('--seal', metavar='ANSWER', help='compose the late email from this answer')
    p.add_argument('--reason', default='the scheduled report session stopped before publication')
    a = p.parse_args(argv)
    if a.stage:
        steps = stage(a.state_dir)
        print(json.dumps({'steps': steps, 'brief': str(Path(a.state_dir)/C.BRIEF_TEXT)}, indent=1))
        return 0
    answer = C.parse_answer(Path(a.check or a.seal).read_text())
    if a.check:
        problems = check(a.state_dir, answer)
        print(json.dumps({'problems': problems}, indent=1))
        return 0 if not problems else 2
    print(json.dumps(compose(a.state_dir, answer, reason=a.reason), indent=1))
    return 0


if __name__ == '__main__':
    sys.exit(main())
