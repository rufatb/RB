"""Planted implementation controls, not a retrospective return experiment."""
import copy
import datetime as dt
import io
import json
from pathlib import Path
import subprocess
import time

import pytest

import dda_protocol as P
import dda_desk as D

pytestmark = pytest.mark.dda
NOW = dt.datetime(2026, 11, 11, 9, 10, tzinfo=P.ET)


def staged():
    rows = []
    for ticker in ('AC.TO', 'SU.TO', 'OTHER.TO'):
        rows.append({'ticker': ticker, 'sector': 'Example', 'technicals': {'last': 100, 'prev_low': 95, 'prev_high': 105, 'rsi': 99, 'r0': 20},
                     'headlines': [{'title': ticker+' raises operating guidance', 'published_at': '2026-11-11T07:00:00-05:00',
                                    'source_url': 'https://issuer.test/'+ticker, 'summary': 'Cash-flow guidance increased with signed contracts.',
                                    'evidence_metadata': {'classification': 'ISSUER_RELEASE', 'issuer_role': 'VERIFIED',
                                                          'first_disclosed_at': '2026-11-11T07:00:00-05:00'}}]})
    return {'as_of': NOW.isoformat(), 'candidates': rows, 'macro': {}, 'candidate_gaps': {}}


def snapshot():
    return P.freeze(staged(), NOW, requested=['AC.TO', 'SU.TO', 'OTHER.TO'])


def research(snap, chosen='OTHER.TO'):
    return {'assessments': [{'ticker': r['ticker'], 'status': 'CASE' if r['ticker'] == chosen else 'NO_EDGE',
                             'reason': 'No sufficient incremental evidence' if r['ticker'] != chosen else 'More complete business evidence'}
                            for r in snap['candidates']],
            'cases': [{'ticker': chosen, 'side': 'LONG', 'thesis': 'Contract evidence supports higher cash flow.',
                       'why_now': 'New company update before the bell.', 'not_priced': 'Conditional on an expectation gap confirmed in the source.',
                       'counter_case': 'The market may already price it.', 'confirmation': 'Verify disclosed contract economics and the opening quote.',
                       'invalidation': 'Contract cash flow fails to materialize.',
                       'claims': [{'statement': 'The release describes contracted cash flow.',
                                   'quote': 'Cash-flow guidance increased with signed contracts.',
                                   'evidence_id': next(f['id'] for f in snap['facts'] if f['ticker'] == chosen)}],
                       'evidence_ids': [f['id'] for f in snap['facts'] if f['ticker'] == chosen]}]}


def challenge(clean, verdict='SUPPORTED'):
    identifier = clean['cases'][0]['id']
    return {'reviews': [{'case_id': identifier, 'verdict': verdict, 'reason': 'Verify the supplied business fact.',
                         'verify_next': 'Check expectations and opening price.', 'evidence_ids': clean['cases'][0]['evidence_ids']}],
            'ranked_choices': [identifier] if verdict == 'SUPPORTED' else [],
            'comparisons': [] if verdict == 'SUPPORTED' else [{'case_id': identifier, 'why_not_first': 'Insufficient evidence.'}]}


def test_full_universe_includes_a_stronger_alternative_outside_original_top_two():
    snap = snapshot()
    clean = P.validate_research(research(snap), snap)
    reviewed = P.validate_challenge(challenge(clean), clean, snap)
    out = P.assemble(snap, clean, reviewed, NOW+dt.timedelta(seconds=20), [])
    assert [c['ticker'] for c in out['cases'] if c['chosen']] == ['OTHER.TO']
    assert out['coverage']['assessed'] == 3
    assert 'rsi' not in json.dumps(P.research_payload(snap))
    assert 'r0' not in json.dumps(P.research_payload(snap))
    assert 'Cash-flow guidance' in json.dumps(snap)


def test_exact_full_universe_coverage_is_required_not_a_silent_nomination_slice():
    snap = snapshot()
    reply = research(snap)
    reply['assessments'].pop()
    with pytest.raises(ValueError, match='FULL_UNIVERSE'):
        P.validate_research(reply, snap)


def test_no_edge_is_a_complete_assessment_with_no_forced_long_short_pair():
    snap = snapshot()
    clean = P.validate_research({'assessments': [{'ticker': r['ticker'], 'status': 'NO_EDGE', 'reason': 'Not established from supplied facts.'}
                                               for r in snap['candidates']], 'cases': []}, snap)
    out = P.assemble(snap, clean, {'reviews': [], 'ranked_choices': [], 'comparisons': []}, NOW, [])
    assert out['choice_ids'] == [] and out['coverage']['assessed'] == 3


@pytest.mark.parametrize('alter', ['invented', 'other_issuer', 'no_release'])
def test_invented_or_wrong_issuer_evidence_cannot_support_a_choice(alter):
    snap = snapshot()
    reply = research(snap)
    if alter == 'invented':
        reply['cases'][0]['evidence_ids'] = ['not_supplied']
    elif alter == 'other_issuer':
        reply['cases'][0]['evidence_ids'] = [snap['facts'][0]['id']]
    else:
        for fact in snap['facts']:
            fact['kind'] = 'headline'
    with pytest.raises(ValueError):
        P.validate_research(reply, snap)


def test_reviewer_cannot_promote_a_thin_or_contradicted_case():
    snap = snapshot()
    clean = P.validate_research(research(snap), snap)
    reply = challenge(clean, 'CONTRADICTED')
    reply['ranked_choices'] = [clean['cases'][0]['id']]
    with pytest.raises(ValueError, match='ONLY_SUPPORTED'):
        P.validate_challenge(reply, clean, snap)


def test_late_answer_is_informational_and_cannot_claim_an_opening_entry():
    snap = snapshot()
    clean = P.validate_research(research(snap), snap)
    reviewed = P.validate_challenge(challenge(clean), clean, snap)
    out = P.assemble(snap, clean, reviewed, NOW.replace(hour=9, minute=30), [])
    assert not out['opening_eligible'] and out['status'].startswith('LATE')


def test_future_releases_and_law_firm_notices_are_excluded_and_coverage_gaps_retained():
    data = staged()
    data['candidates'][0]['headlines'][0]['published_at'] = '2026-11-11T11:00:00-05:00'
    data['candidates'][0]['headlines'][0]['evidence_metadata']['first_disclosed_at'] = '2026-11-11T11:00:00-05:00'
    data['candidates'][1]['headlines'][0]['title'] = 'SU.TO Sued for Securities Law Violations, contact the Law Group'
    snap = P.freeze(data, NOW, requested=['MISSING.TO']+[r['ticker'] for r in data['candidates']])
    assert [f['ticker'] for f in snap['facts']] == ['OTHER.TO']
    assert snap['coverage']['missing_tickers'] == ['MISSING.TO']


def test_original_publications_and_zero_choice_results_cannot_be_rewritten(tmp_path):
    path = tmp_path/'record.json'
    assert D.first_write(path, {'choices': []})
    assert not D.first_write(path, {'choices': ['rewritten']})
    assert D.read(path) == {'choices': []}


def test_provider_failure_keeps_diagnostics_without_invented_choices(tmp_path, monkeypatch):
    monkeypatch.setattr(D, 'ROOT', tmp_path)
    monkeypatch.setattr(D.subprocess, 'check_output', lambda *a, **kw: 'a'*40)
    def fail(*a):
        raise RuntimeError('private provider response with a secret')
    out = D.stage(tmp_path/'state', now=NOW, clock=lambda: NOW, capture_fn=lambda *a: snapshot(), askers=[('fixture', fail)])
    assert out['choice_ids'] == [] and out['errors']
    assert 'private provider' not in json.dumps(out)


def test_publish_only_commits_one_presentation_record_and_never_force_pushes(tmp_path, monkeypatch):
    monkeypatch.setattr(D, 'ROOT', tmp_path)
    path = tmp_path/'data/reviews/dda/2026-11-11.decision.json'
    D.first_write(path, {'choices': []})
    calls = []
    def run(command, **kwargs):
        calls.append(command)
        return subprocess.CompletedProcess(command, 1 if 'cat-file' in command else 0, '', '')
    assert D.publish(path, runner=run)['status'] == 'PUBLISHED'
    commit = next(c for c in calls if 'commit' in c)
    assert '--only' in commit and commit[-1] == path.relative_to(tmp_path).as_posix()
    assert not any('--force' in c or '-A' in c for c in calls)
    with pytest.raises(ValueError):
        D.publish(tmp_path/'council.py', runner=run)


@pytest.mark.parametrize('change', ['excerpt', 'number'])
def test_fabricated_magnitude_or_source_excerpt_is_rejected(change):
    snap = snapshot()
    result = research(snap)
    if change == 'excerpt':
        result['cases'][0]['claims'][0]['quote'] = 'The company disclosed a revenue beat that does not exist.'
    else:
        result['cases'][0]['thesis'] = 'Revenue beat consensus by 48.6%.'
    with pytest.raises(ValueError, match='EXCERPT_NOT_IN_SOURCE|UNSOURCED_NUMBER'):
        P.validate_research(result, snap)


def test_fmp_verification_excludes_same_day_and_future_actuals_and_sanitizes_failures():
    from dda_verification import verify
    rows = [{'date': '2026-11-10', 'epsActual': 2, 'epsEstimated': 1},
            {'date': '2026-11-11', 'epsActual': 9000}, {'date': '2026-12-01', 'epsActual': 9999}]
    result = verify([{'ticker': 'TEST.TO'}], Path('.'), NOW, get=lambda *a, **k: rows)
    assert result[0]['earnings'] == [{'date': '2026-11-10', 'epsActual': 2, 'epsEstimated': 1}]
    def fail(*a, **kw):
        raise ValueError('apikey=private')
    assert 'private' not in json.dumps(verify([{'ticker': 'TEST.TO'}], Path('.'), NOW, get=fail))


def test_successful_runtime_uses_all_three_passes_and_does_not_rebill_on_rerun(tmp_path, monkeypatch):
    monkeypatch.setattr(D, 'ROOT', tmp_path)
    monkeypatch.setattr(D.subprocess, 'check_output', lambda *a, **kw: 'a'*40)
    monkeypatch.setattr(D, 'council_snapshot', lambda *a: None)
    requests = []
    def screen(prompt, payload, budget):
        requests.append('screen')
        return research(snapshot())
    def review(prompt, payload, budget):
        requests.append('review')
        assert 'execution_context' in payload and 'verification_context' in payload
        return challenge(P.validate_research(research(snapshot()), snapshot()))
    def verify(*a, **kw):
        requests.append('fmp')
        return [{'ticker': 'OTHER.TO', 'status': 'AVAILABLE'}]
    kwargs = dict(now=NOW, clock=lambda: NOW, capture_fn=lambda *a: snapshot(),
                  askers=[('screen-model', screen), ('challenge-model', review)], verify_fn=verify)
    out = D.stage(tmp_path/'state', **kwargs)
    assert requests == ['screen', 'fmp', 'review'] and len(out['choice_ids']) == 1
    assert [r['model'] for r in out['routes']] == ['screen-model', 'Financial Modeling Prep', 'challenge-model']
    assert D.stage(tmp_path/'state', **kwargs) == out and len(requests) == 3


def test_sidecar_is_detached_data_only_and_has_no_wait_or_email_call(tmp_path):
    import dda_hooks
    calls = []
    assert dda_hooks.start(tmp_path, 'research', popen=lambda *a, **k: calls.append((a, k)))
    args, kwargs = calls[0]
    assert 'dda_desk.py' in args[0][1] and '--publish' in args[0]
    assert kwargs['start_new_session'] and kwargs['stdin'] == subprocess.DEVNULL
    assert 'send' not in ' '.join(args[0])
    assert '--budget' not in args[0]  # Use the canonical default, not the old 180 s override.


def test_publisher_refuses_unreviewed_code_ahead_of_remote(tmp_path, monkeypatch):
    monkeypatch.setattr(D, 'ROOT', tmp_path)
    path = tmp_path/'data/reviews/dda/2026-11-11.decision.json'
    D.first_write(path, {})
    commands = []
    def run(command, **kw):
        commands.append(command)
        return subprocess.CompletedProcess(command, 0, 'council.py\n', '')
    assert D.publish(path, runner=run)['reason'] == 'NON_DDA_COMMITS_AHEAD'
    assert not any('push' in c or 'commit' in c for c in commands)


def test_longer_fmp_text_reaches_the_blind_screen_with_its_real_retrieval_clock():
    from dda_source_text import enrich
    data = staged()
    longer = 'Operating guidance and contract details. '*20+'Revenue actual 130 versus comparable estimate 100.'
    def get(path, **params):
        symbol = params['symbols']
        return [{'url': 'https://issuer.test/'+symbol, 'title': 'Issuer reports guidance',
                 'publishedDate': '2026-11-11 07:00:00', 'text': longer}]
    received = NOW+dt.timedelta(seconds=2)
    receipt = enrich(data, Path('.'), NOW, get=get, clock=lambda: received, twins={})
    assert receipt['excerpts_expanded'] == 3
    snap = P.freeze(data, received)
    assert all('Revenue actual 130' in f['text'] and f['retrieved_at'] == received.isoformat() for f in snap['facts'])
    assert not P.freeze(data, NOW)['facts']  # Later text cannot be used at the request start.


@pytest.mark.parametrize('bad', ['future', 'unknown_time', 'wrong_url'])
def test_fmp_text_cannot_replace_an_excerpt_without_a_matching_dated_source(bad):
    from dda_source_text import enrich
    data = staged()
    original = copy.deepcopy(data)
    def get(path, **params):
        return [{'url': 'https://unrelated.test/release' if bad == 'wrong_url' else 'https://issuer.test/'+params['symbols'],
                 'title': 'Issuer release', 'text': 'untrusted future data '*100,
                 'publishedDate': '2026-11-11 10:00:00' if bad == 'future' else '' if bad == 'unknown_time' else '2026-11-11 07:00:00'}]
    receipt = enrich(data, Path('.'), NOW, get=get, clock=lambda: NOW, twins={})
    assert receipt['excerpts_expanded'] == 0 and data == original


def test_fmp_source_budget_and_failure_keep_the_original_summary_without_key_leaks():
    from dda_source_text import enrich
    data = staged()
    original = copy.deepcopy(data)
    def get(*a, **kw):
        raise ValueError('apikey=private-key-in-url')
    receipt = enrich(data, Path('.'), NOW, get=get, clock=lambda: NOW, twins={})
    assert data == original and 'private-key' not in json.dumps(receipt)
    receipt = enrich(data, Path('.'), NOW, get=lambda *a, **k: pytest.fail('Budget already spent'),
                     clock=lambda: NOW, twins={}, seconds=0)
    assert receipt['excerpts_expanded'] == 0


def test_real_git_publication_commits_an_already_staged_record_without_unrelated_code(tmp_path, monkeypatch):
    repo, bare = tmp_path/'repo', tmp_path/'remote.git'
    repo.mkdir()
    def git(*args, cwd=repo):
        return subprocess.check_output(['git', *args], cwd=cwd, text=True, stderr=subprocess.PIPE).strip()
    git('init', '--bare', str(bare), cwd=tmp_path)
    git('init', '-b', 'main')
    git('config', 'user.email', 'dda-fixture@example.test')
    git('config', 'user.name', 'DDA fixture')
    code = repo/'council.py'
    code.write_text('original fixture code\n')
    git('add', '--', 'council.py')
    git('commit', '-m', 'fixture baseline')
    git('remote', 'add', 'origin', str(bare))
    git('push', '-u', 'origin', 'main')
    monkeypatch.setattr(D, 'ROOT', repo)
    path = repo/'data/reviews/dda/2026-11-11.decision.json'
    D.first_write(path, {'choice_ids': []})
    code.write_text('unrelated staged change\n')
    git('add', '--', 'council.py', path.relative_to(repo).as_posix())
    assert D.publish(path, budget=8)['status'] == 'PUBLISHED'
    assert git('show', 'HEAD:council.py') == 'original fixture code'
    assert git('diff', '--cached', '--name-only') == 'council.py'
    assert json.loads(git('show', 'HEAD:'+path.relative_to(repo).as_posix())) == {'choice_ids': []}
    original_head = git('rev-parse', 'HEAD')
    assert D.publish(path, budget=8)['status'] == 'PUBLISHED'
    assert git('rev-parse', 'HEAD') == original_head


def test_todays_182_second_screen_preserves_verification_and_full_challenge_window(tmp_path, monkeypatch):
    """Replay elapsed time, never today's outcomes or another paid request."""
    monkeypatch.setattr(D, 'ROOT', tmp_path)
    monkeypatch.setattr(D.subprocess, 'check_output', lambda *a, **kw: 'a'*40)
    monkeypatch.setattr(D, 'council_snapshot', lambda *a: None)
    elapsed, calls = [0.], []
    data = staged()
    for i in range(147):
        row = copy.deepcopy(data['candidates'][0])
        row['ticker'] = f'T{i:03}.TO'
        data['candidates'].append(row)
    snap = P.freeze(data, NOW+dt.timedelta(seconds=15))
    clean = P.validate_research(research(snap), snap)
    def capture(*a):
        elapsed[0] += 15
        return snap
    def screen(prompt, payload, budget):
        assert len(payload['candidates']) == 150
        calls.append(('screen', budget))
        elapsed[0] += 182
        return research(snap)
    def verify(*a, seconds):
        calls.append(('verify', seconds))
        elapsed[0] += 18
        return [{'ticker': 'OTHER.TO', 'status': 'AVAILABLE'}]
    def review(prompt, payload, budget):
        calls.append(('challenge', budget))
        elapsed[0] += 170
        return challenge(clean)
    kwargs = dict(now=NOW, clock=lambda: NOW+dt.timedelta(seconds=elapsed[0]),
                  monotonic=lambda: elapsed[0], capture_fn=capture, verify_fn=verify,
                  askers=[('screen-model', screen), ('challenge-model', review)])
    out = D.stage(tmp_path/'state', **kwargs)
    assert calls == [('screen', 240), ('verify', 18), ('challenge', 180)]
    assert out['coverage']['assessed'] == 150 and out['coverage']['challenged'] == 1
    assert out['opening_eligible'] and not out['errors'] and len(out['choice_ids']) == 1
    assert [r['elapsed_seconds'] for r in out['routes']] == [182, 18, 170]
    assert out['runtime_budget']['total_seconds'] == 480
    assert D.stage(tmp_path/'state', **kwargs) == out and len(calls) == 3


@pytest.mark.parametrize('when,budget', [(NOW, 180), (NOW.replace(minute=27), 480)])
def test_short_window_stops_before_billing_instead_of_starving_the_challenge(tmp_path, monkeypatch, when, budget):
    monkeypatch.setattr(D, 'ROOT', tmp_path)
    monkeypatch.setattr(D.subprocess, 'check_output', lambda *a, **kw: 'a'*40)
    def never(*a, **kw):
        pytest.fail('Do not bill a screen without room for the required review')
    out = D.stage(tmp_path/'state', now=when, clock=lambda: when, monotonic=lambda: 0,
                  capture_fn=lambda *a: snapshot(), askers=[('screen-model', never)], budget=budget)
    assert out['status'] == 'RESEARCH INCOMPLETE' and not out['choice_ids']
    assert out['errors'] == [{'pass': 'research', 'model': 'screen-model', 'error': 'ValueError',
                              'code': 'DDA_RESEARCH_BUDGET_EXHAUSTED'}]
    assert out['routes'][0]['status'] == 'failed'
    assert out['runtime_budget']['total_seconds'] <= budget


def test_research_overrun_cannot_promote_unreviewed_cases(tmp_path, monkeypatch):
    monkeypatch.setattr(D, 'ROOT', tmp_path)
    monkeypatch.setattr(D.subprocess, 'check_output', lambda *a, **kw: 'a'*40)
    elapsed = [0.]
    def overrun(prompt, payload, budget):
        elapsed[0] += budget+1
        return research(snapshot())
    out = D.stage(tmp_path/'state', now=NOW, clock=lambda: NOW+dt.timedelta(seconds=elapsed[0]),
                  monotonic=lambda: elapsed[0], capture_fn=lambda *a: snapshot(),
                  askers=[('screen-model', overrun)], verify_fn=lambda *a, **kw: pytest.fail('Screen timed out'))
    assert out['status'] == 'RESEARCH INCOMPLETE' and not out['choice_ids']
    assert out['errors'][0]['code'] == 'DDA_RESEARCH_TIMEOUT'
    assert out['coverage']['assessed'] == 0


def test_challenge_failure_records_the_reviewer_and_preserves_unapproved_screen(tmp_path, monkeypatch):
    monkeypatch.setattr(D, 'ROOT', tmp_path)
    monkeypatch.setattr(D.subprocess, 'check_output', lambda *a, **kw: 'a'*40)
    monkeypatch.setattr(D, 'council_snapshot', lambda *a: None)
    def fail(*a):
        raise ValueError('DDA_CHALLENGE_TIMEOUT')
    out = D.stage(tmp_path/'state', now=NOW, clock=lambda: NOW,
                  capture_fn=lambda *a: snapshot(),
                  askers=[('screen-model', lambda *a: research(snapshot())), ('challenge-model', fail)],
                  verify_fn=lambda *a, **kw: [{'ticker': 'OTHER.TO', 'status': 'AVAILABLE'}])
    assert out['status'] == 'RESEARCH INCOMPLETE' and not out['choice_ids']
    assert out['coverage']['assessed'] == 3 and out['coverage']['challenged'] == 0
    assert out['errors'][0]['pass'] == 'challenge' and out['errors'][0]['model'] == 'challenge-model'
    assert out['routes'][-1]['status'] == 'failed'


@pytest.mark.parametrize('index,code', [(0, 'DDA_RESEARCH_TIMEOUT'), (1, 'DDA_CHALLENGE_TIMEOUT')])
def test_wall_timeout_kills_and_reaps_a_still_active_provider_worker(tmp_path, monkeypatch, index, code):
    """A real hung local process proves this is more than an HTTP idle timeout."""
    worker = tmp_path/'hung_provider.py'
    worker.write_text('import sys,time\nsys.stderr.write("private-provider-secret\\n")\n'
                      'sys.stderr.flush()\ntime.sleep(60)\n', encoding='utf-8')
    monkeypatch.setattr(D, '__file__', str(worker))
    monkeypatch.setattr(D, 'ROOT', tmp_path)
    monkeypatch.setattr(D, '_provider_routes', lambda *a: [('screen', None), ('challenge', None)])
    children, popen = [], subprocess.Popen
    def track(*a, **kw):
        child = popen(*a, **kw)
        children.append(child)
        return child
    monkeypatch.setattr(D.subprocess, 'Popen', track)
    _, ask = D.routes(tmp_path, 480)[index]
    started = time.monotonic()
    with pytest.raises(ValueError, match=code) as error:
        ask('fixture', {'no': 'credentials'}, .3)
    assert time.monotonic()-started < 3
    assert len(children) == 1 and children[0].poll() is not None
    assert 'private-provider-secret' not in str(error.value)


def test_worker_roundtrip_preserves_result_and_actual_model_receipt(tmp_path, monkeypatch):
    worker = tmp_path/'fixture_provider.py'
    worker.write_text('import sys,json\nr=json.load(sys.stdin)\n'
                      'print(json.dumps({"result":r["payload"],"metadata":{"actual_model":"fixture","usage":{"total_tokens":1}}}))\n',
                      encoding='utf-8')
    monkeypatch.setattr(D, '__file__', str(worker))
    monkeypatch.setattr(D, 'ROOT', tmp_path)
    monkeypatch.setattr(D, '_provider_routes', lambda *a: [('fixture', None)])
    _, ask = D.routes(tmp_path, 480)[0]
    assert ask('fixture', {'thesis': 'priced in / déjà vu'}, 3) == {'thesis': 'priced in / déjà vu'}
    assert ask.last == {'actual_model': 'fixture', 'usage': {'total_tokens': 1}}


def test_provider_worker_never_serializes_private_exception_text(tmp_path, monkeypatch, capsys):
    def fail(*a):
        raise ValueError('apikey=private-provider-secret')
    monkeypatch.setattr(D, '_provider_routes', lambda *a: [('fixture', fail)])
    monkeypatch.setattr(D.sys, 'stdin', io.StringIO(json.dumps({'prompt': '', 'payload': {}, 'budget': 1})))
    assert D.main(['--provider-worker', '0', '--state-dir', str(tmp_path)]) == 0
    assert json.loads(capsys.readouterr().out) == {'code': 'DDA_PROVIDER_FAILURE'}


def test_start_at_or_after_preopen_guard_does_not_create_claim_or_call_provider(tmp_path, monkeypatch):
    monkeypatch.setattr(D, 'ROOT', tmp_path)
    with pytest.raises(ValueError, match='DDA_INSUFFICIENT_PREOPEN_WINDOW'):
        D.stage(tmp_path/'state', now=NOW.replace(minute=28), capture_fn=lambda *a: pytest.fail('Too late'))
    assert not (tmp_path/'state').exists()
