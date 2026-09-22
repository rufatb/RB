#!/usr/bin/env python3
"""Claude's desk: the same long/short question, answered by Claude.

WHY THIS EXISTS. The owner asked for three parallel sections every morning —
Claude's picks, DeepSeek's and Jev's — each coming from its own model, so they
can be compared side by side. DeepSeek and Jev were already asked. Claude never
was: the report was assembled by Claude and contained no opinion of Claude's.

THE SAME QUESTION, THE SAME EVIDENCE. The brief is built by
`deepseek_opportunities.build_request` — one implementation of the rows, the
macro block and the evidence gaps — and carries DeepSeek's system prompt
verbatim: same rules, same two-per-side ceiling, same `invalid_at` claim, same
JSON schema. The answer is validated by DeepSeek's `_clean` against the brief's
own universe, so an invented ticker is refused exactly as it is there. A
comparison between two models is only a comparison if neither was shown
something the other was not.

TWO ROUTES TO ONE SNAPSHOT.
  session  The scheduled Routine IS a Claude session. `morning_full.sh` writes
           the brief and waits; the session reads it, writes its answer and runs
           `--seal`. No API key is needed, and none exists on this account.
  api      If `$RB_STATE_DIR/secrets/anthropic_api_key` is staged, `--api`
           asks the Messages API directly. Only that file is read — never the
           environment, which inside Claude Code carries the SESSION's own
           endpoint, not a credential for this job.
Either route produces the same sealed snapshot and the same reader.

INDEPENDENCE IS ORDERED, NOT PROMISED. `morning_full.sh` does not ask DeepSeek
or Jev until Claude's answer is sealed or its deadline passes, so the other two
answers do not exist on disk while Claude is answering. The seal records which
other rankings were already present, and the section prints it.

THE DEADLINE IS 09:24 ET, not 09:30, so a slow answer can never take the
DeepSeek ranking's slot — DeepSeek is still the owner's headline.

NOTHING HERE IS ADOPTED BY THE ENGINE. The desk's picks are sized on the report
exactly as DeepSeek's and Jev's are (`primary_board.build`), recorded in
`data/model_picks.csv` and scored on the same yardstick. The confidence is
Claude's own number: not calibrated, and never averaged with another model's.
Nothing here places, modifies or cancels an order.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import re
import sys
import time
from pathlib import Path
from zoneinfo import ZoneInfo

import deepseek_opportunities as O
from diagnostics import safe_detail

ET = ZoneInfo('America/New_York')
REGISTRATION = 'CLAUDE.md#day114'
SCHEMA_VERSION = 'day114-claude-v1'
PROMPT_VERSION = O.PROMPT_VERSION          # the same prompt, by construction
SYSTEM_PROMPT = O.SYSTEM_PROMPT
SNAPSHOT_NAME = 'claude_opportunities.json'
BRIEF_NAME = 'claude_brief.json'
BRIEF_TEXT = 'claude_brief.txt'
ANSWER_NAME = 'claude_answer.json'
CUTOFF = dt.time(9, 24)
SESSION_LABEL = 'Claude (scheduled Claude Code session)'
API_MODEL = 'claude-opus-5-5'
API_TIMEOUT = 150.0
MAX_BRIEF_BYTES = 4_000_000
MAX_ANSWER_BYTES = 50_000
OTHERS = (('DeepSeek', O.SNAPSHOT_NAME), ('Jev', 'jev_opportunities.json'))

CONFIDENCE_LABEL = ("Claude's own stated confidence. NOT a calibrated win probability: its "
                    "track record is the scored line beside it, and it is never averaged "
                    "with another model's number.")


def unavailable(reason):
    return {**O.unavailable(reason), 'registration': REGISTRATION,
            'confidence_label': CONFIDENCE_LABEL}


def _now(now):
    now = now or dt.datetime.now(ET)
    if now.tzinfo is None:
        raise ValueError('AWARE_CLOCK_REQUIRED')
    return now.astimezone(ET)


def _write(path, obj):
    from build_biotech import write_atomic
    write_atomic(path, obj)


# ── the brief ────────────────────────────────────────────────────────────────

def brief_text(brief):
    """The brief as a person — or a Claude session — reads it.

    One candidate per line, its headlines on their own lines, so no line is long
    enough to be truncated by a file reader. The JSON file is the sealed record;
    this is the same content, laid out to be read in full."""
    payload = brief['payload']
    out = [SYSTEM_PROMPT, '', '=' * 72,
           f"SESSION {payload['session']} · entry {payload['entry']} · exit {payload['exit']}",
           f"{brief['considered']} candidates. Answer by writing ONE JSON object to "
           f"{brief['answer_path']} and running:", f"  {brief['seal_command']}",
           f"The seal refuses at or after {CUTOFF:%H:%M} ET. Use ONLY this file: do not open "
           'any other snapshot, report, web page or price feed before sealing.', '']
    if payload.get('macro'):
        out += ['MACRO ' + json.dumps(payload['macro'], sort_keys=True), '']
    for row in payload['candidates']:
        news = row.get('headlines') or []
        out.append(json.dumps({k: v for k, v in row.items() if k != 'headlines'}, sort_keys=True))
        for item in news:
            out.append('    headline ' + json.dumps(item, sort_keys=True))
    return '\n'.join(out) + '\n'


def stage_brief(state_dir, *, now=None):
    """Write the question and the evidence. Pre-cutoff only; never calls a model."""
    now = _now(now)
    if now.time() >= CUTOFF:
        raise ValueError('CLAUDE_PREOPEN_ONLY')
    root = Path(state_dir)
    try:
        import yaml
        from factor_inputs import build_from_state
        cfg = yaml.safe_load(Path(__file__).with_name('config.yaml').read_text())
        staged = build_from_state(root, cfg, now)
        request = O.build_request(staged['candidates'], staged.get('macro'), now)
    except (OSError, UnicodeError, ValueError, TypeError, KeyError, ImportError) as exc:
        _write(root/SNAPSHOT_NAME, _seal_snapshot(
            unavailable('The candidate pool has not been staged (%s).' % type(exc).__name__), now))
        return None
    if request is None:
        _write(root/SNAPSHOT_NAME, _seal_snapshot(
            unavailable('No candidate carried complete prepared technicals.'), now))
        return None
    gaps = request['evidence_gaps'] + ['Input gap: ' + safe_detail(str(g), 120)
                                       for g in (staged.get('gaps') or [])[:3]]
    brief = O._seal({'schema_version': SCHEMA_VERSION, 'prompt_version': PROMPT_VERSION,
                     'session': now.date().isoformat(), 'prepared_at': now.isoformat(),
                     'system_prompt': SYSTEM_PROMPT, 'payload': request['payload'],
                     'universe': sorted(request['allowed']), 'considered': request['considered'],
                     'evidence': request['evidence'], 'gaps': gaps,
                     'answer_path': str(root/ANSWER_NAME),
                     'seal_command': (f'python claude_opportunities.py --state-dir {root} '
                                      f'--seal {root/ANSWER_NAME}')})
    _write(root/BRIEF_NAME, brief)
    (root/BRIEF_TEXT).write_text(brief_text(brief))
    return brief


def read_brief(state_dir, now):
    path = Path(state_dir)/BRIEF_NAME
    if not path.is_file():
        raise ValueError('CLAUDE_BRIEF_NOT_STAGED')
    if path.stat().st_size > MAX_BRIEF_BYTES:
        raise ValueError('CLAUDE_BRIEF_OVERSIZED')
    brief = json.loads(path.read_text())
    if not isinstance(brief, dict) or O._seal(brief)['snapshot_sha256'] != brief.get('snapshot_sha256'):
        raise ValueError('CLAUDE_BRIEF_INTEGRITY')
    if brief.get('schema_version') != SCHEMA_VERSION or brief.get('session') != now.date().isoformat():
        raise ValueError('CLAUDE_BRIEF_NOT_TODAY')
    return brief


# ── the answer ───────────────────────────────────────────────────────────────

def _seal_snapshot(result, now, **extra):
    return O._seal({**result, **extra, 'schema_version': SCHEMA_VERSION,
                    'prompt_version': PROMPT_VERSION, 'session': now.date().isoformat(),
                    'prepared_at': now.isoformat()})


def independence(state_dir, now):
    """Which other rankings for TODAY were already on disk at the seal."""
    present = []
    for name, file in OTHERS:
        try:
            obj = json.loads((Path(state_dir)/file).read_text())
            if isinstance(obj, dict) and obj.get('session') == now.date().isoformat():
                present.append(name)
        except (OSError, ValueError):
            continue
    stamp = now.strftime('%H:%M:%S ET')
    if not present:
        return f'sealed at {stamp}, before DeepSeek or Jev had been asked'
    return (f"sealed at {stamp}; {' and '.join(present)}'s ranking was already on disk — "
            'not independent by construction')


def parse_answer(text):
    """One JSON object. A fenced block is unwrapped; anything else is refused."""
    text = text.strip()
    fenced = re.fullmatch(r'```(?:json)?\s*(.*?)\s*```', text, re.S)
    if fenced:
        text = fenced.group(1)
    body = json.loads(text)
    if not isinstance(body, dict):
        raise ValueError('CLAUDE_ANSWER_NOT_AN_OBJECT')
    return body


def seal(state_dir, answer, *, now=None, model=SESSION_LABEL, route='session'):
    """Validate Claude's answer against the brief and seal it. Publish-once."""
    now = _now(now)
    if now.time() >= CUTOFF:
        raise ValueError('CLAUDE_PREOPEN_ONLY')
    root = Path(state_dir)
    if (root/SNAPSHOT_NAME).exists():
        try:
            if json.loads((root/SNAPSHOT_NAME).read_text()).get('session') == now.date().isoformat():
                raise ValueError('CLAUDE_ALREADY_SEALED')
        except (OSError, json.JSONDecodeError):
            pass
    brief = read_brief(root, now)
    allowed = set(brief['universe'])
    longs, long_gaps = O._clean(answer.get('longs'), allowed, 'long')
    shorts, short_gaps = O._clean(answer.get('shorts'), allowed, 'short')
    result = {'status': 'READY' if (longs or shorts) else 'NO_OPPORTUNITY',
              'model': safe_detail(str(model), 60), 'considered': brief['considered'],
              'universe': sorted(allowed), 'evidence': brief['evidence'],
              'longs': longs, 'shorts': shorts,
              'gaps': long_gaps + short_gaps + list(brief.get('gaps') or []),
              'asked_at': brief['prepared_at'], 'adopted': False,
              'registration': REGISTRATION, 'confidence_label': CONFIDENCE_LABEL}
    snapshot = _seal_snapshot(result, now, route=route, independence=independence(root, now))
    _write(root/SNAPSHOT_NAME, snapshot)
    return snapshot


def load_api_key(state_dir):
    path = Path(state_dir)/'secrets'/'anthropic_api_key'
    if not path.is_file():
        return None
    key = path.read_text().strip()
    if not key or len(key) > 400 or any(c.isspace() for c in key):
        raise ValueError('INVALID_PRIVATE_CREDENTIAL')
    return key


def ask_api(state_dir, *, now=None, client=None, model=API_MODEL):
    """The API route: one Messages call on the brief, then the same seal."""
    injected_clock = now
    now = _now(now)
    brief = read_brief(state_dir, now)
    if client is None:
        key = load_api_key(state_dir)
        if not key:
            raise ValueError('NO_ANTHROPIC_CREDENTIAL')
        import anthropic
        # EXPLICIT base_url: inside Claude Code ANTHROPIC_BASE_URL points at the
        # session's own proxy, and this job's key must never be sent there.
        client = anthropic.Anthropic(api_key=key, base_url='https://api.anthropic.com',
                                     max_retries=0, timeout=API_TIMEOUT)
    response = client.messages.create(
        model=model, max_tokens=4096, system=SYSTEM_PROMPT,
        messages=[{'role': 'user', 'content': json.dumps(brief['payload'], sort_keys=True,
                                                         allow_nan=False)}])
    if getattr(response, 'stop_reason', None) != 'end_turn':
        raise ValueError('CLAUDE_REPLY_CUT_OFF')
    text = ''.join(getattr(b, 'text', '') for b in response.content)
    # Sealed at the time the ANSWER exists, not the time it was asked.
    return seal(state_dir, parse_answer(text), now=None if injected_clock is None else now,
                model=getattr(response, 'model', model), route='api')


def sealed_today(state_dir, now=None):
    now = _now(now)
    try:
        obj = json.loads((Path(state_dir)/SNAPSHOT_NAME).read_text())
    except (OSError, ValueError):
        return False
    return isinstance(obj, dict) and obj.get('session') == now.date().isoformat()


def wait_for_brief(state_dir, seconds, *, now_fn=None, sleep=time.sleep):
    """Block until today's brief exists (0), the wait ends (2) or the cutoff passes (3)."""
    now_fn = now_fn or (lambda: dt.datetime.now(ET))
    deadline = time.monotonic() + seconds
    while True:
        now = _now(now_fn())
        if now.time() >= CUTOFF:
            return 3
        try:
            read_brief(state_dir, now)
            return 0
        except (OSError, ValueError):
            pass
        if sealed_today(state_dir, now):
            return 4        # UNAVAILABLE was sealed instead: nothing to answer
        if time.monotonic() >= deadline:
            return 2
        sleep(5)


# ── reading ──────────────────────────────────────────────────────────────────

def load_prepared(state_dir, now):
    """Revalidate the sealed snapshot. Pure: no model call, no state written."""
    return O.load_snapshot(state_dir, now, name=SNAPSHOT_NAME, schema=SCHEMA_VERSION,
                           unavailable=unavailable, cutoff=CUTOFF,
                           extra=('route', 'independence'))


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    p.add_argument('--state-dir', default='.rb-state')
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument('--brief', action='store_true', help='write the brief (pre-09:24 only)')
    g.add_argument('--seal', metavar='ANSWER_JSON', help="seal Claude's answer")
    g.add_argument('--api', action='store_true', help='answer through the Messages API')
    g.add_argument('--wait-brief', type=int, metavar='SECONDS',
                   help='wait for the brief: 0 ready, 2 still waiting, 3 past cutoff, 4 nothing to answer')
    g.add_argument('--sealed', action='store_true', help='exit 0 when today is sealed')
    g.add_argument('--show', action='store_true', help='print the validated snapshot')
    a = p.parse_args(argv)
    root = Path(a.state_dir)
    try:
        if a.brief:
            brief = stage_brief(root)
            print(json.dumps({'status': 'BRIEF_WRITTEN' if brief else 'UNAVAILABLE_SEALED',
                              'read': str(root/BRIEF_TEXT) if brief else None,
                              'considered': brief and brief['considered']}))
            return 0 if brief else 2
        if a.seal:
            path = Path(a.seal)
            if path.stat().st_size > MAX_ANSWER_BYTES:
                raise ValueError('CLAUDE_ANSWER_OVERSIZED')
            snap = seal(root, parse_answer(path.read_text()))
        elif a.api:
            snap = ask_api(root)
        elif a.wait_brief is not None:
            code = wait_for_brief(root, a.wait_brief)
            print(json.dumps({'status': {0: 'READY', 2: 'STILL_WAITING', 3: 'PAST_CUTOFF',
                                         4: 'NOTHING_TO_ANSWER'}[code],
                              'read': str(root/BRIEF_TEXT)}))
            return code
        elif a.sealed:
            return 0 if sealed_today(root) else 1
        else:
            print(json.dumps(load_prepared(root, dt.datetime.now(ET)), indent=1))
            return 0
    except ValueError as exc:
        print(json.dumps({'status': 'REFUSED', 'reason': safe_detail(str(exc), 120)}))
        return 3
    except Exception as exc:
        print(json.dumps({'status': 'FAILED', 'reason': type(exc).__name__}))
        return 1
    print(json.dumps({'status': snap['status'], 'longs': snap['longs'], 'shorts': snap['shorts'],
                      'gaps': snap['gaps'], 'independence': snap.get('independence')}, indent=1))
    return 0


if __name__ == '__main__':
    sys.exit(main())
