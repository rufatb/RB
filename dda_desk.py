#!/usr/bin/env python3
"""Canonical DDA research publication and automatic bounded GitHub hooks.

Existing scheduled commands invoke this module. No brokerage actions or sends.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
from pathlib import Path
import subprocess
import sys
import tempfile
import time

from dda_protocol import (ET, VERSION, RESEARCH_PROMPT, CHALLENGE_PROMPT, assemble, digest,
                          freeze, public_url, research_payload, stamp, validate_research,
                          validate_challenge, words)

ROOT = Path(__file__).resolve().parent


def enabled():
    return os.getenv('RB_DDA_ENABLED', '1') == '1'


def read(path):
    if not path.is_file():
        return None
    if path.stat().st_size > 4_000_000:
        raise ValueError('DDA_ARTIFACT_TOO_LARGE')
    value = json.loads(path.read_text(encoding='utf-8'))
    return value if isinstance(value, dict) else None


def first_write(path, data):
    """Publish complete bytes before making the first-write link visible."""
    encoded = json.dumps(data, sort_keys=True, ensure_ascii=False, allow_nan=False, indent=1)
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, temporary = tempfile.mkstemp(prefix='.dda-', suffix='.tmp', dir=path.parent)
    try:
        with os.fdopen(handle, 'w', encoding='utf-8') as out:
            out.write(encoded)
            out.flush()
            os.fsync(out.fileno())
        try:
            os.link(temporary, path)
            return True
        except FileExistsError:
            return False
    finally:
        Path(temporary).unlink(missing_ok=True)


def capture(root, now):
    import yaml
    from factor_inputs import build_from_state
    import factor_pool_policy
    staged = build_from_state(root, yaml.safe_load((ROOT/'config.yaml').read_text()), now)
    fmp_receipt = read(root/'fmp_context.json') or {}
    fmp_clock = stamp(fmp_receipt.get('prepared_at'))
    if not fmp_clock or fmp_clock > now or fmp_clock.date() != now.date():
        for candidate in staged.get('candidates', []):
            candidate.pop('fmp', None)
        staged.pop('fmp_events', None)
    else:
        for candidate in staged.get('candidates', []):
            context = candidate.get('fmp') or {}
            if context.get('last_report') == now.date().isoformat():
                context.pop('eps_surprise_pct', None)  # Unknown intraday disclosure time.
    # Use the complete staged pool, not the <=16-name council table. Preserve
    # available issuer summaries which the original desk headline strips out.
    import newswire
    import press_feed
    archived = newswire.read() + press_feed.read()
    by_ticker = {c['ticker']: c for c in staged.get('candidates', [])}
    from factor_news import classify_headline
    for row in archived:
        at = stamp(row.get('published_at'))
        if not at or at > now or now-at > dt.timedelta(hours=72):
            continue
        for ticker in row.get('tickers') or []:
            if ticker not in by_ticker:
                continue
            url = public_url(row.get('url'))
            title = words(row.get('title'), 500)
            if not url or not title:
                continue
            heads = by_ticker[ticker].setdefault('headlines', [])
            metadata = classify_headline(title, url, ticker)
            summary = words(row.get('summary') or row.get('lead'), 1600)
            item = {'title': title, 'source_url': url, 'published_at': at.isoformat(),
                    'evidence_metadata': metadata, 'summary': summary}
            existing = next((h for h in heads if h.get('source_url') == url), None)
            if existing is not None:
                existing['summary'] = summary
            else:
                heads.append(item)
    from dda_source_text import enrich
    source_text = enrich(staged, root, now)
    # A provider response received later cannot be backdated to request start.
    now = dt.datetime.now(ET)
    # The actual prepared universe may be broader than the legacy roster. An
    # incomplete roster remains explicit rather than shrinking the denominator.
    status = read(root/'factor_pool_status.json') or {}
    declaration = staged.get('research_universe') or status.get('research_universe') or {}
    master = read(root/'tsx_universe.json') or {}
    requested = [c.get('ticker') for c in master.get('candidates', []) if isinstance(c, dict)]
    if not requested:
        requested = list(factor_pool_policy.TICKERS)
    requested = sorted({t for t in requested if isinstance(t, str) and t.endswith('.TO')} | set(by_ticker))
    snapshot = freeze(staged, now, requested=requested)
    snapshot['source_text'] = source_text
    unmatched = sum(r['status'] != 'EXPANDED' for r in source_text['receipts'])
    if unmatched:
        snapshot['gaps'].append(f'Longer issuer text not obtained for {unmatched} source checks; archived excerpts retained.')
    snapshot['upstream_coverage'] = {k: status.get(k) for k in ('requested', 'eligible', 'status')}
    snapshot['universe_mode'] = words(declaration.get('mode'), 80)
    snapshot['evidence_digest'] = digest({k: v for k, v in snapshot.items() if k != 'evidence_digest'})
    return snapshot


def routes(root, seconds):
    from prepare_deepseek import load_private_key, load_private_model
    import council
    import jev_opportunities as J
    load_private_key(root)
    load_private_model(root)
    J.load_private_key(root)  # Same OpenRouter key; never include it in payloads.
    def deepseek(prompt, payload, budget):
        from openai import OpenAI
        client = OpenAI(api_key=os.environ.get('DEEPSEEK_API_KEY', ''), base_url='https://api.deepseek.com',
                        timeout=min(85, budget), max_retries=0)
        result = client.chat.completions.create(model=os.getenv('DEEPSEEK_MODEL', 'deepseek-v4-pro'),
            messages=[{'role': 'system', 'content': prompt}, {'role': 'user', 'content': json.dumps(payload, ensure_ascii=False)}],
            response_format={'type': 'json_object'}, max_tokens=20000,
            extra_body={'thinking': {'type': 'enabled'}, 'reasoning_effort': 'high'})
        if result.choices[0].finish_reason != 'stop':
            raise ValueError('DDA_RESEARCH_TRUNCATED')
        deepseek.last = {'actual_model': result.model, 'reasoning': 'high', 'output_budget': 20000,
                         'usage': result.usage.model_dump() if result.usage else {}}
        return json.loads(result.choices[0].message.content)
    def claude(prompt, payload, budget):
        import research
        key = os.environ.get('OPENROUTER_API_KEY', '')
        if not key:
            raise ValueError('DDA_NO_OPENROUTER_CREDENTIAL')
        post = research.http_post('https://openrouter.ai/api/v1/chat/completions',
                                  {'Authorization': 'Bearer ' + key}, min(75, budget))
        result = post({'model': council.OPENROUTER_CLAUDE, 'max_tokens': 14000,
            'reasoning': {'effort': 'high', 'exclude': True},
            'provider': {'require_parameters': True}, 'response_format': {'type': 'json_object'},
            'messages': [{'role': 'system', 'content': prompt},
                         {'role': 'user', 'content': json.dumps(payload, ensure_ascii=False)}]})
        if result['choices'][0].get('finish_reason') != 'stop':
            raise ValueError('DDA_CHALLENGE_TRUNCATED')
        claude.last = {'actual_model': result.get('model'), 'reasoning': 'high', 'output_budget': 14000,
                       'usage': result.get('usage') or {}}
        return research._json_from(result['choices'][0]['message']['content'])
    return [(os.getenv('DEEPSEEK_MODEL', 'deepseek-v4-pro'), deepseek), (council.OPENROUTER_CLAUDE, claude)]


def stage(root, *, now=None, clock=None, capture_fn=None, askers=None, verify_fn=None, budget=180):
    root = Path(root)
    clock = clock or (lambda: dt.datetime.now(ET))
    now = stamp(now or clock())
    if not now or now.time().replace(tzinfo=None) >= dt.time(9, 28):
        raise ValueError('DDA_INSUFFICIENT_PREOPEN_WINDOW')
    final_path = ROOT/'data'/'reviews'/'dda'/(now.date().isoformat()+'.decision.json')
    previous = read(final_path)
    if previous:
        return previous
    runtime = root/'dda'/now.date().isoformat()
    if not first_write(runtime/'research.claim.json', {'started_at': now.isoformat(), 'policy': VERSION}):
        raise ValueError('DDA_RESEARCH_ALREADY_STARTED')
    deadline = time.monotonic() + min(budget, (now.replace(hour=9, minute=29, second=0)-now).total_seconds())
    snapshot = (capture_fn or capture)(root, now)
    first_write(runtime/'input.json', snapshot)
    askers = askers or routes(root, budget)
    route_log, errors, verification = [], [], []
    baseline = None
    remaining = lambda: max(0, deadline-time.monotonic())
    research = {'assessments': [], 'cases': []}
    challenge = {'reviews': [], 'ranked_choices': [], 'comparisons': []}
    try:
        if remaining() < 10:
            raise ValueError('DDA_RESEARCH_BUDGET_EXHAUSTED')
        name, ask = askers[0]
        started = stamp(clock())
        result = ask(RESEARCH_PROMPT, research_payload(snapshot), remaining())
        research = validate_research(result, snapshot)
        route_log.append({'pass': 'Full-universe research', 'model': name, 'started_at': started.isoformat(),
                          'completed_at': stamp(clock()).isoformat(), 'status': 'complete', 'assessed': len(research['assessments']),
                          **getattr(ask, 'last', {})})
        if research['cases']:
            from dda_verification import verify
            started = stamp(clock())
            verification = (verify_fn or verify)(research['cases'], root, started, seconds=min(18, max(0, remaining()-50)))
            route_log.append({'pass': 'FMP earnings verification', 'model': 'Financial Modeling Prep',
                              'started_at': started.isoformat(), 'completed_at': stamp(clock()).isoformat(),
                              'status': 'complete' if all(v['status'] != 'UNAVAILABLE' for v in verification) else 'partial'})
            # The original council is a labelled comparison, never a privileged
            # winner or a fact. It may not have completed when DDA is challenged.
            try:
                snap = council_snapshot(root, stamp(clock()))
                baseline = snap
            except Exception:
                baseline = None
            if remaining() < 10:
                raise ValueError('DDA_CHALLENGE_BUDGET_EXHAUSTED')
            name, ask = askers[-1]
            started = stamp(clock())
            raw = ask(CHALLENGE_PROMPT, {'cases': research['cases'], 'facts': snapshot['facts'],
                      'verification_context': verification, 'original_council': baseline,
                      'execution_context': snapshot['execution_context'],
                      'all_assessments': research['assessments'],
                      'session': snapshot['session'], 'captured_at': snapshot['captured_at']}, remaining())
            challenge = validate_challenge(raw, research, snapshot)
            route_log.append({'pass': 'Challenge and alternatives comparison', 'model': name,
                              'started_at': started.isoformat(), 'completed_at': stamp(clock()).isoformat(), 'status': 'complete',
                              **getattr(ask, 'last', {})})
    except Exception as exc:
        errors.append({'pass': 'research' if not research['assessments'] else 'challenge', 'error': type(exc).__name__,
                       'model': name if 'name' in locals() else None,
                       'code': str(exc)[:100] if isinstance(exc, ValueError) and str(exc).startswith('DDA_') else 'PROVIDER_OR_VALIDATION_FAILURE'})
    decision = assemble(snapshot, research, challenge, clock(), route_log, errors=errors)
    decision['verification_context'] = verification
    decision['source_text'] = snapshot.get('source_text')
    decision['original_council'] = baseline
    decision['comparison_note'] = 'Original council was not yet available at the challenge cutoff.' if baseline is None else 'Original council supplied as a comparison, not a vote weight.'
    decision['source_revision'] = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
    decision['id'] = digest({k: v for k, v in decision.items() if k != 'id'})[:24]
    first_write(final_path, decision)
    first_write(runtime/'decision.json', decision)
    return read(final_path)


def council_snapshot(root, now):
    import council
    snap = council.load(root, now)
    if not snap or snap.get('session') != now.date().isoformat() or snap.get('status') not in {'READY', 'NO_CONSENSUS', 'NO_POSITIONS'}:
        return None
    original = council.top_two(snap)
    return {'rule_version': original.get('rule_version'), 'reason': words(original.get('reason')),
            'picks': [{k: p.get(k) for k in ('ticker', 'side', 'reason', 'invalid_at', 'confidence', 'agreement')}
                      for p in original.get('picks', [])]}


def load(root, now):
    data = read(Path(root)/'dda'/now.date().isoformat()/'decision.json')
    if not data or data.get('session') != now.date().isoformat() or data.get('policy') != VERSION:
        return None
    ended = stamp(data.get('completed_at'))
    return data if ended and ended <= now else None


def publish(path, *, runner=subprocess.run, budget=8):
    lock = ROOT/'.rb-state'/'dda-publication.lock'
    lock.parent.mkdir(parents=True, exist_ok=True)
    try:
        lock.mkdir()
    except FileExistsError:
        return {'status': 'NOT_PUBLISHED', 'reason': 'PUBLICATION_BUSY'}
    try:
        return _publish(path, runner=runner, budget=budget)
    finally:
        lock.rmdir()


def _publish(path, *, runner, budget):
    """Only a new dated record, never code, a force-push or a shared-index sweep."""
    relative = Path(path).resolve().relative_to(ROOT.resolve()).as_posix()
    if not re.fullmatch(r'data/reviews/dda/\d{4}-\d{2}-\d{2}\.(decision|opening|open-check|report)\.json', relative) or not Path(path).is_file():
        raise ValueError('DDA_PUBLICATION_PATH_REJECTED')
    until = time.monotonic() + budget
    def git(*args):
        left = until-time.monotonic()
        if left <= .1:
            raise TimeoutError('DDA_PUBLICATION_BUDGET')
        return runner(['git', *args], cwd=ROOT, capture_output=True, text=True, timeout=left, check=False)
    try:
        # Never push unreviewed code or unrelated local commits.
        ahead = git('diff', '--name-only', 'origin/main...HEAD')
        if ahead.returncode or any(not re.fullmatch(r'data/reviews/dda/\d{4}-\d{2}-\d{2}\.(decision|opening|open-check|report)\.json', p)
                                   for p in ahead.stdout.splitlines() if p.strip()):
            return {'status': 'NOT_PUBLISHED', 'reason': 'NON_DDA_COMMITS_AHEAD'}
        # --only commits exactly this new presentation record while preserving
        # unrelated staged work. No automatic merge into a running morning.
        committed = git('cat-file', '-e', 'HEAD:'+relative).returncode == 0
        if not committed:
            if git('add', '--', relative).returncode:
                return {'status': 'NOT_PUBLISHED', 'reason': 'GIT_STAGE_FAILED'}
            if git('commit', '--only', '-m', 'record: DDA presentation '+Path(path).name, '--', relative).returncode:
                return {'status': 'NOT_PUBLISHED', 'reason': 'GIT_COMMIT_FAILED'}
        result = git('push', 'origin', 'HEAD:main')
        return {'status': 'PUBLISHED' if result.returncode == 0 else 'NOT_PUBLISHED',
                'reason': None if result.returncode == 0 else 'GIT_PUSH_FAILED_NO_FORCE'}
    except (subprocess.TimeoutExpired, TimeoutError):
        return {'status': 'NOT_PUBLISHED', 'reason': 'GIT_BUDGET_EXHAUSTED'}


def bridge(root, stage_name, now=None):
    """Automatically capture the existing runtime stages for the platform."""
    now = stamp(now or dt.datetime.now(ET))
    if stage_name == 'opening' and now.time().replace(tzinfo=None) >= dt.time(9, 30):
        raise ValueError('DDA_OPENING_EXPORT_TOO_LATE')
    data = {'schema_version': 1, 'session': now.date().isoformat(), 'exported_at': now.isoformat()}
    if stage_name == 'opening':
        import council
        snap = council.load(root, now)
        if snap.get('session') == data['session'] and snap.get('status') in {'READY', 'NO_CONSENSUS', 'NO_POSITIONS'}:
            original = council.top_two(snap)
            data['opening'] = {'decided_at': snap.get('finished_at') or snap.get('asked_at'), 'section': {
                'rule_version': original.get('rule_version'), 'reason': original.get('reason'),
                'picks': [{k: p.get(k) for k in ('ticker', 'side', 'reason', 'invalid_at', 'confidence', 'agreement', 'council_vote')}
                          for p in original.get('picks', [])]}}
    elif stage_name == 'open-check':
        plan = read(Path(root)/'flash'/'open_plan.json') or {}
        at = stamp(plan.get('prepared_at'))
        if not at or at > now or plan.get('session') != data['session'] or at.time().replace(tzinfo=None) < dt.time(9, 31):
            raise ValueError('DDA_OPEN_CHECK_CLOCK_REQUIRED')
        fields = ('ticker', 'side', 'verdict', 'price', 'at', 'atr_pct', 'reach', 'open_days', 'decision', 'decision_why')
        data['open_check'] = {'session': plan['session'], 'prepared_at': at.isoformat(),
                              'rows': [{k: row.get(k) for k in fields} for row in plan.get('rows', [])[:20]]}
    elif stage_name == 'report':
        report = read(Path(root)/'latest'/'report.json') or {}
        if report.get('session') != data['session'] or now.time().replace(tzinfo=None) < dt.time(9, 46):
            raise ValueError('DDA_REPORT_CLOCK_REQUIRED')
        data['report'] = {k: report.get(k) for k in ('session', 'generated_at')}
        original = ((report.get('intraday') or {}).get('top_two') or {})
        data['report']['intraday'] = {'top_two': {'rule_version': original.get('rule_version'),
            'reason': words(original.get('reason')), 'picks': [{k: p.get(k) for k in ('ticker', 'side', 'reason', 'invalid_at', 'confidence', 'agreement')}
                for p in original.get('picks', [])]}}
    expected = {'opening': 'opening', 'open-check': 'open_check', 'report': 'report'}[stage_name]
    if not data.get(expected):
        raise ValueError('DDA_STAGE_NOT_AVAILABLE')
    path = ROOT/'data'/'reviews'/'dda'/(data['session']+'.'+stage_name+'.json')
    first_write(path, data)
    return path


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--state-dir', type=Path, default=Path(os.getenv('RB_STATE_DIR', '.rb-state')))
    parser.add_argument('--stage', action='store_true')
    parser.add_argument('--export', choices=('opening', 'open-check', 'report'))
    parser.add_argument('--publish', action='store_true')
    parser.add_argument('--budget', type=int, default=180)
    args = parser.parse_args(argv)
    if not enabled():
        return 0
    try:
        if args.export:
            path = bridge(args.state_dir, args.export)
        else:
            result = stage(args.state_dir, budget=min(max(args.budget, 15), 180))
            path = ROOT/'data'/'reviews'/'dda'/(result['session']+'.decision.json')
        result = publish(path) if args.publish else {'status': 'RECORDED', 'path': str(path.relative_to(ROOT))}
        print(json.dumps(result))
        return 0 if result['status'] in {'RECORDED', 'PUBLISHED'} else 2
    except Exception as exc:
        print(json.dumps({'status': 'UNAVAILABLE', 'error': type(exc).__name__,
                          'code': str(exc)[:100] if isinstance(exc, ValueError) and str(exc).startswith('DDA_') else 'DDA_STAGE_FAILED'}))
        return 2


if __name__ == '__main__':
    sys.exit(main())
