"""Planted implementation controls, not a retrospective return experiment."""
import copy
import datetime as dt
import json
from pathlib import Path
import subprocess

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
        return subprocess.CompletedProcess(command, 1 if 'ls-files' in command else 0, '', '')
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
