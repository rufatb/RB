"""Preparation and diagnostics submit only complete, validated public inputs."""
import copy
import datetime as dt
import json
import sys
from types import SimpleNamespace

import pytest

import factor_inputs as F
import probe_deepseek as probe
from adapters.deepseek_adapter import CANDIDATE_KEYS
from test_factor_inputs import payload, NOW, CFG
from test_prepare_deepseek import success


def test_shared_eligibility_keeps_healthy_names_and_full_requested_pool():
    raw = payload()
    healthy = raw['candidates'][0]
    missing_news = copy.deepcopy(healthy)
    missing_news.update(ticker='NEWS.TO', headlines=[])
    missing_technical = copy.deepcopy(healthy)
    missing_technical['ticker'] = 'TECH.TO'
    missing_technical['technicals']['macd'] = None
    raw['candidates'].extend([missing_news, missing_technical])
    clean = F.validate_payload(raw, NOW)
    before = copy.deepcopy(clean)
    rows, gaps = F.eligible_public_candidates(clean)
    assert [row['ticker'] for row in rows] == ['ABC.TO']
    assert set(rows[0]) == CANDIDATE_KEYS
    assert set(gaps) == {'NEWS.TO', 'TECH.TO'}
    assert clean == before
    assert clean['coverage']['requested'] == 3
    assert clean['candidate_gaps']['NEWS.TO'] == ['NO_CURRENT_CATALYST_EVIDENCE']
    assert 'TECHNICAL_UNAVAILABLE:macd' in clean['candidate_gaps']['TECH.TO']


def test_missing_macro_is_never_a_usable_model_batch():
    raw = payload()
    raw['macro'].pop('vix')
    clean = F.validate_payload(raw, NOW)
    rows, gaps = F.eligible_public_candidates(clean)
    assert rows == []
    assert 'INCOMPLETE_MACRO' in gaps['ABC.TO']
    assert clean['coverage']['requested'] == 1


@pytest.mark.parametrize('mutate', [
    lambda clean: clean['coverage'].update(complete_tickers=[]),
    lambda clean: clean['coverage'].update(macro_complete=False),
    lambda clean: clean['candidate_gaps'].update({'ABC.TO': ['CACHE_CURRENT_OR_FUTURE_BARS_IGNORED']}),
    lambda clean: clean['candidate_gaps'].update({'ABC.TO': 'INVALID_DIAGNOSTICS'}),
    lambda clean: clean['macro'].update(vix=None),
    lambda clean: clean['candidates'][0]['technicals'].update(macd=None),
    lambda clean: clean['candidates'][0].update(headlines=[]),
    lambda clean: clean['candidates'].append(copy.deepcopy(clean['candidates'][0])),
])
def test_completeness_label_cannot_clear_missing_values_or_hard_gaps(mutate):
    clean = F.validate_payload(payload(), NOW)
    mutate(clean)
    rows, gaps = F.eligible_public_candidates(clean)
    assert rows == []
    assert gaps['ABC.TO']


def test_historical_exclusion_advisory_does_not_block_complete_inputs():
    raw = payload()
    raw['candidate_diagnostics'] = {'ABC.TO': ['HISTORICAL_SESSIONS_EXCLUDED:2']}
    rows, gaps = F.eligible_public_candidates(F.validate_payload(raw, NOW))
    assert [row['ticker'] for row in rows] == ['ABC.TO']
    assert gaps == {}


def test_adapter_rejection_remains_explicit_and_does_not_echo_rejected_text():
    clean = F.validate_payload(payload(), NOW)
    secret = 'sk-synthetic-private-not-a-credential'
    clean['candidates'][0]['headlines'][0]['title'] = secret
    rows, gaps = F.eligible_public_candidates(clean)
    assert rows == []
    assert gaps['ABC.TO'] == ['Candidate failed DeepSeek public payload validation.']
    assert secret not in json.dumps(gaps)


def test_real_probe_calls_shared_eligibility_before_provider(tmp_path, monkeypatch):
    source = tmp_path/'inputs.json'
    source.write_text(json.dumps(payload()))
    original = F.eligible_public_candidates
    called = []
    def checked(clean):
        called.append(clean['coverage']['requested'])
        return original(clean)
    monkeypatch.setattr(F, 'eligible_public_candidates', checked)
    result, _ = probe.probe_real(tmp_path, source, evaluator=success, clock=lambda: NOW)
    assert called == [1]
    assert result['requested'] == result['eligible'] == result['covered'] == 1


@pytest.mark.parametrize('marker', [
    {'kind': 'CURRENT_TIME_DIAGNOSTIC'}, {'morning_snapshot': False},
])
def test_default_state_builder_rejects_diagnostic_pool(tmp_path, marker):
    raw = payload()
    raw.update(marker)
    (tmp_path/'deepseek_candidates.json').write_text(json.dumps(raw))
    clean = F.build_from_state(tmp_path, CFG, NOW)
    assert clean['candidates'] == []
    assert clean['gaps'] == ['DIAGNOSTIC_CANDIDATES_NOT_A_MORNING_POOL']


def test_diagnostic_builder_requires_context_and_preserves_honest_marker(tmp_path, monkeypatch):
    raw = payload()
    raw.update(kind='CURRENT_TIME_DIAGNOSTIC', morning_snapshot=False)
    (tmp_path/'deepseek_candidates.json').write_text(json.dumps(raw))
    checked = []
    monkeypatch.setitem(sys.modules, 'diagnostic_context',
        SimpleNamespace(require_context=lambda root: checked.append(root)))
    later = NOW+dt.timedelta(hours=3)
    clean = F.build_from_state(tmp_path, CFG, later, diagnostic=True)
    assert checked == [tmp_path]
    assert clean['coverage']['complete'] == 1
    assert clean['kind'] == 'CURRENT_TIME_DIAGNOSTIC' and clean['morning_snapshot'] is False
    assert clean['as_of'] == later.isoformat()
    assert clean['coverage']['pool_prepared_at'] == NOW.isoformat()
    assert clean['candidates'][0]['technicals_as_of'] == raw['candidates'][0]['technicals_as_of']
    assert json.loads((tmp_path/'deepseek_candidates.json').read_text()) == raw


def test_diagnostic_builder_cannot_bypass_context_failure(tmp_path, monkeypatch):
    def denied(root):
        raise ValueError('DIAGNOSTIC_CONTEXT_REQUIRED')
    monkeypatch.setitem(sys.modules, 'diagnostic_context', SimpleNamespace(require_context=denied))
    with pytest.raises(ValueError, match='DIAGNOSTIC_CONTEXT_REQUIRED'):
        F.build_from_state(tmp_path, CFG, NOW, diagnostic=True)


def test_diagnostic_marker_never_relaxes_technical_freshness(tmp_path, monkeypatch):
    raw = payload()
    raw.update(kind='CURRENT_TIME_DIAGNOSTIC', morning_snapshot=False)
    raw['candidates'][0]['technicals_as_of'] = '2026-09-09T16:00:00-04:00'
    (tmp_path/'deepseek_candidates.json').write_text(json.dumps(raw))
    monkeypatch.setitem(sys.modules, 'diagnostic_context', SimpleNamespace(require_context=lambda root: None))
    clean = F.build_from_state(tmp_path, CFG, NOW, diagnostic=True)
    assert clean['coverage']['complete'] == 0
    assert 'STALE_OR_WRONG_PREVIOUS_SESSION_TECHNICALS' in clean['candidate_gaps']['ABC.TO']
    assert F.eligible_public_candidates(clean)[0] == []
