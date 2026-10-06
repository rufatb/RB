#!/usr/bin/env python3
"""GEMINI'S DESK — a fourth model asked the same question (owner, 2026-10-03).

Gemini answers EXACTLY what DeepSeek and Claude answer: the same rows from
`deepseek_opportunities.build_request`, the same system prompt verbatim, the
same validator (`_clean`), the same level and basis checks. A comparison
between models is only a comparison if none was shown something the others
were not. It is asked after Claude's seal, beside DeepSeek and Jev, before
09:30, and the report reads a sealed snapshot — a renderer never reaches it.

    python gemini_opportunities.py --state-dir .rb-state       # stage today's ranking
    python gemini_opportunities.py --control                   # planted-edge positive control

Model: `gemini-3.8-flash` on the Gemini API (generativelanguage v1beta),
listed by models.list on 2026-10-03. JSON mode, thinking level LOW — the other
desks answer non-thinking for the same reason (day-114b: a reasoning budget
that eats the reply). The credential lives at
$RB_STATE_DIR/secrets/gemini_api_key (0600, gitignored), or GEMINI_API_KEY.

Its confidence is its own number, never averaged with another model's.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sys
from pathlib import Path
from zoneinfo import ZoneInfo

import deepseek_opportunities as O
from diagnostics import safe_detail

ET = ZoneInfo('America/New_York')
REGISTRATION = 'CLAUDE.md#day123'
SCHEMA_VERSION = 'day123-gemini-v1'
PROMPT_VERSION = O.PROMPT_VERSION          # the same prompt, by construction
SYSTEM_PROMPT = O.SYSTEM_PROMPT
SNAPSHOT_NAME = 'gemini_opportunities.json'
DEFAULT_MODEL = 'gemini-3.8-flash'
ENDPOINT = 'https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent'
THINKING = {'thinkingLevel': 'low'}
MAX_OUTPUT_TOKENS = 16384
REQUEST_TIMEOUT = 120.0
MODE = 'thinking-low'
CONFIDENCE_LABEL = ("Gemini's own stated confidence. NOT a calibrated win probability: its "
                    'record is the scored line beside its picks, and it is never averaged '
                    "with another model's number.")


def unavailable(reason):
    return {**O.unavailable(reason), 'registration': REGISTRATION,
            'confidence_label': CONFIDENCE_LABEL}


def load_private_key(state_dir):
    """The environment wins; the private file populates it. Same contract as
    the DeepSeek and OpenRouter keys: no whitespace, bounded length."""
    present = os.environ.get('GEMINI_API_KEY', '').strip()
    if present:
        return present
    path = Path(state_dir)/'secrets'/'gemini_api_key'
    if not path.is_file():
        return None
    key = path.read_text().strip()
    if not key or len(key) > 400 or any(c.isspace() for c in key):
        raise ValueError('INVALID_PRIVATE_CREDENTIAL')
    os.environ['GEMINI_API_KEY'] = key
    return key


class GeminiClient:
    """One generateContent call. Returns (reply dict, model version)."""

    def __init__(self, key, *, model=DEFAULT_MODEL, timeout=REQUEST_TIMEOUT, session=None):
        self.key, self.model, self.timeout = key, model, timeout
        self.session = session

    def ask(self, system, user):
        import requests
        body = {'systemInstruction': {'parts': [{'text': system}]},
                'contents': [{'role': 'user', 'parts': [{'text': user}]}],
                'generationConfig': {'responseMimeType': 'application/json',
                                     'maxOutputTokens': MAX_OUTPUT_TOKENS,
                                     'thinkingConfig': THINKING}}
        r = (self.session or requests).post(ENDPOINT.format(model=self.model),
                                            headers={'x-goog-api-key': self.key},
                                            json=body, timeout=self.timeout)
        if r.status_code != 200:
            # The status only: a provider body can echo the request.
            raise ValueError('HTTP_%d' % r.status_code)
        data = r.json()
        cands = data.get('candidates') or []
        if not cands:
            block = (data.get('promptFeedback') or {}).get('blockReason')
            raise ValueError('NO_CANDIDATE' + ('_' + str(block) if block else ''))
        cand = cands[0]
        if cand.get('finishReason') != 'STOP':
            raise ValueError('CUT_OFF_%s' % safe_detail(str(cand.get('finishReason')), 30))
        text = ''.join(p.get('text', '') for p in (cand.get('content') or {}).get('parts') or []
                       if not p.get('thought'))
        reply = json.loads(text)
        if not isinstance(reply, dict):
            raise ValueError('reply is not an object')
        return reply, safe_detail(str(data.get('modelVersion') or self.model), 60)


def rank(candidates, *, macro=None, model=None, client=None, now=None, key=None,
         research=False, fmp_get=None):
    """Ask once, validate hard, at most two per side — DeepSeek's checks exactly."""
    now = now or dt.datetime.now(ET)
    request = O.build_request(candidates, macro, now)
    if request is None:
        return unavailable('No candidate carried complete prepared technicals.')
    allowed, payload = request['allowed'], request['payload']
    model = model or os.environ.get('GEMINI_MODEL') or DEFAULT_MODEL
    if client is None:
        key = key or os.environ.get('GEMINI_API_KEY', '').strip()
        if not key:
            return unavailable('No Gemini credential is staged for this session.')
        client = GeminiClient(key, model=model)
    # DAY-126 RESEARCH ROUND (see deepseek_opportunities.rank): any failure
    # falls through to the single-shot call, and the gaps say so.
    body, served, research_meta, research_gaps = None, None, None, []
    if research and isinstance(client, GeminiClient) and client.session is None:
        import research as RS
        box = None
        try:
            box = RS.Toolbox(now.date(), allowed, now, get=fmp_get, model='Gemini')
            post = RS.http_post(ENDPOINT.format(model=client.model), {'x-goog-api-key': client.key},
                                client.timeout)
            body = RS.gemini_loop(post, SYSTEM_PROMPT, json.dumps(payload, sort_keys=True, allow_nan=False),
                                  box, thinking=THINKING)
            served, research_meta = client.model, RS.summary(box)
        except Exception as exc:
            body = None
            code = str(exc)[:40] if str(exc).isupper() else type(exc).__name__
            research_gaps.append('Research round failed (%s); answered single-shot.' % code)
            if box is not None:
                research_meta = {**RS.summary(box), 'failed': code}
    if body is None:
        try:
            body, served = client.ask(SYSTEM_PROMPT, json.dumps(payload, sort_keys=True,
                                                                allow_nan=False))
        except Exception as exc:
            reason = str(exc) if isinstance(exc, ValueError) and str(exc).isupper() else ''
            return unavailable('The ranking request failed: ' + (safe_detail(reason, 60)
                                                                 or type(exc).__name__))
    longs, long_gaps = O._clean(body.get('longs'), allowed, 'long')
    shorts, short_gaps = O._clean(body.get('shorts'), allowed, 'short')
    long_gaps += O.check_levels(longs, 'LONG', payload['candidates'])
    short_gaps += O.check_levels(shorts, 'SHORT', payload['candidates'])
    long_gaps += O.check_basis(longs, payload['candidates'])
    short_gaps += O.check_basis(shorts, payload['candidates'])
    out = {'status': 'READY' if (longs or shorts) else 'NO_OPPORTUNITY', 'mode': MODE,
           'model': served, 'considered': request['considered'], 'universe': sorted(allowed),
           'evidence': request['evidence'], 'longs': longs, 'shorts': shorts,
           'gaps': long_gaps + short_gaps + request['evidence_gaps'] + research_gaps,
           'asked_at': now.isoformat(), 'adopted': False, 'registration': REGISTRATION,
           'confidence_label': CONFIDENCE_LABEL}
    if research_meta is not None:
        out['research'] = research_meta
        if not research_meta.get('failed'):
            out['prompt_version'] = research_meta['prompt_version']
    return out


def stage(state_dir, *, now=None, client=None, model=None, diagnostic=False):
    """Ask before the open and seal the answer, from the validated payload."""
    from build_biotech import write_atomic
    now = now or dt.datetime.now(ET)
    if now.tzinfo is None:
        raise ValueError('AWARE_CLOCK_REQUIRED')
    now = now.astimezone(ET)
    root = Path(state_dir)
    if diagnostic:
        from diagnostic_context import require_context
        require_context(root)
    elif now.time() >= O.PREOPEN_CUTOFF:
        raise ValueError('OPPORTUNITIES_PREOPEN_ONLY')
    credential_gaps, key = [], None
    try:
        key = load_private_key(root)
        if not key and client is None:
            credential_gaps.append('No Gemini credential is staged for this session.')
    except (OSError, UnicodeError, ValueError) as exc:
        credential_gaps.append('The staged Gemini credential was rejected (%s).'
                               % type(exc).__name__)
    try:
        import yaml
        from factor_inputs import build_from_state
        cfg = yaml.safe_load((Path(__file__).with_name('config.yaml')).read_text())
        payload = build_from_state(root, cfg, now, diagnostic=diagnostic)
        candidates = payload['candidates']
        if not isinstance(candidates, list):
            raise ValueError('payload carries no candidate list')
    except (OSError, UnicodeError, ValueError, TypeError, KeyError, ImportError) as exc:
        result = unavailable('The candidate pool has not been staged (%s).' % type(exc).__name__)
    else:
        import fmp_context
        result = rank(candidates, macro=fmp_context.with_events(payload), client=client, model=model,
                      now=now, key=key, research=client is None)
        for gap in (payload.get('gaps') or [])[:3]:
            result.setdefault('gaps', []).append('Input gap: ' + safe_detail(str(gap), 120))
    context = ({'kind': 'CURRENT_TIME_DIAGNOSTIC', 'morning_snapshot': False,
                'prediction_evidence': False} if diagnostic else {})
    result = {**result, 'gaps': list(result.get('gaps') or []) + credential_gaps}
    import research as RS
    version = RS.keep_log(root, 'gemini', result, now) or PROMPT_VERSION
    snapshot = O._seal({**result, 'schema_version': SCHEMA_VERSION,
                        'prompt_version': version,
                        'session': now.date().isoformat(), 'prepared_at': now.isoformat(),
                        **context})
    write_atomic(root/SNAPSHOT_NAME, snapshot)
    return snapshot


def load_prepared(state_dir, now, *, diagnostic=False):
    """Revalidate the sealed snapshot. Pure: no model call, no state written."""
    out = O.load_snapshot(state_dir, now, diagnostic=diagnostic, name=SNAPSHOT_NAME,
                          schema=SCHEMA_VERSION, unavailable=unavailable,
                          extra=('prompt_version', 'mode', 'research_summary'))
    if out.get('status') != 'UNAVAILABLE':
        out['registration'], out['confidence_label'] = REGISTRATION, CONFIDENCE_LABEL
    return out


def load_diagnostic(state_dir, now):
    from diagnostic_context import require_context
    require_context(Path(state_dir))
    return load_prepared(state_dir, now, diagnostic=True)


def run_control(*, client=None, model=None, now=None, key=None):
    """House rule 4: the planted universe DeepSeek's control uses, numbers only."""
    result = rank(O.control_universe(), client=client, model=model, now=now, key=key)
    return {**result,
            'long_detected': any(r['ticker'] == O.CONTROL_LONG for r in result.get('longs') or []),
            'short_detected': any(r['ticker'] == O.CONTROL_SHORT for r in result.get('shorts') or [])}


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    p.add_argument('--state-dir', default=os.environ.get('RB_STATE_DIR', '.rb-state'))
    p.add_argument('--diagnostic', action='store_true')
    p.add_argument('--control', action='store_true')
    a = p.parse_args(argv)
    try:
        key = load_private_key(a.state_dir)
    except ValueError as exc:
        print(json.dumps({'status': 'UNAVAILABLE', 'reason': str(exc)}))
        return 2
    if a.control:
        result = run_control(key=key)
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0 if (result['long_detected'] and result['short_detected']) else 2
    try:
        result = stage(a.state_dir, diagnostic=a.diagnostic)
    except ValueError as exc:
        print(json.dumps({'status': 'REFUSED', 'reason': safe_detail(str(exc), 80)}))
        return 3
    print(json.dumps({k: v for k, v in result.items() if k != 'universe'}, indent=2,
                     sort_keys=True))
    return {'READY': 0, 'NO_OPPORTUNITY': 0}.get(result.get('status'), 2)


if __name__ == '__main__':
    sys.exit(main())
