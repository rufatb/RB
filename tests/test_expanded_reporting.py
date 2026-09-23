"""Expanded counts are local evidence, independent of provider/model availability."""
import copy
import hashlib
import json
import sys
from types import SimpleNamespace

import pytest

import brief
import daily_render
import deepseek_factors
import email_render
import preflight
import research_coverage as R
from bar_cache import key
from prepare_factor_pool import _cached
from report_store import encode
from test_daily_pipeline import services
from test_deepseek_render import report
from test_factor_inputs import CFG, NOW, history, save_cache


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, allow_nan=False))


def master():
    return {'status':'PARTIAL', 'session':NOW.date().isoformat(), 'target':150,
        'candidates':[{'ticker':'ABC.TO','sector':'Industrials','industry':'Airlines',
                       'issuer_id':'issuer-abc','median_dollar_volume_20':20_000_000}],
        'source_coverage':{'complete':False},
        'exclusions':[{'ticker':'PREF.TO','reason':'PREFERRED_SECURITY'}],
        'gaps':['PARTIAL_SOURCE_ENUMERATION']}


def stage(root):
    save_cache(root, history())
    row, _ = _cached('ABC.TO', root/'intraday_cache', CFG, NOW)
    universe = {**master(), 'mode':'EXPANDED_TSX_RESEARCH'}
    payload = {'as_of':NOW.replace(hour=8,minute=10).isoformat(),
        'candidates':[row], 'research_universe':universe}
    path = root/'deepseek_candidates.json'
    write(path, payload)
    write(root/'factor_pool_history'/NOW.date().isoformat()/'candidates.json', payload)
    status = {'status':'READY','session':NOW.date().isoformat(),
        'started_at':NOW.replace(hour=8,minute=10).isoformat(),
        'completed_at':NOW.replace(hour=8,minute=11).isoformat(),
        'requested':1,'verified':1,'complete_technicals':1,'reused_baseline':1,
        'errors':{},'candidates_sha256':hashlib.sha256(path.read_bytes()).hexdigest()}
    write(root/'factor_pool_status.json', status)
    write(root/'tsx_universe.json', master())
    return row


def fake_master(monkeypatch, value=None):
    value = value or master()
    monkeypatch.setitem(sys.modules, 'tsx_universe', SimpleNamespace(
        load_prepared=lambda *a, **k:copy.deepcopy(value)))


def forbidden(*args, **kwargs):
    pytest.fail('Research coverage fetched data, called a model or rewrote state')


def test_preflight_validates_actual_completed_history_and_keeps_hashes(tmp_path, monkeypatch):
    stage(tmp_path)
    monkeypatch.setattr('urllib.request.urlopen', forbidden)
    before = {str(p.relative_to(tmp_path)):p.read_bytes() for p in tmp_path.rglob('*') if p.is_file()}
    checked = R.inspect_pool(tmp_path, CFG, NOW, verify_history=True)
    assert checked['status'] == 'READY'
    assert (checked['requested'],checked['verified'],checked['complete_technicals']) == (1,1,1)
    assert checked['technical_tickers'] == ['ABC.TO']
    assert checked['validation'] == 'completed_history'
    assert before == {str(p.relative_to(tmp_path)):p.read_bytes() for p in tmp_path.rglob('*') if p.is_file()}


def test_saved_ready_claim_cannot_hide_missing_cache_file(tmp_path):
    stage(tmp_path)
    (tmp_path/'intraday_cache'/key('ABC.TO')).unlink()
    result = R.inspect_pool(tmp_path, CFG, NOW, verify_history=True)
    assert result['status'] == 'UNAVAILABLE'
    assert result['requested'] == 1 and result['complete_technicals'] == 0
    assert result['errors']['ABC.TO'] == 'FileNotFoundError'


def test_manifest_alone_does_not_certify_expanded_pool(tmp_path):
    write(tmp_path/'factor_pool_status.json', {'session':NOW.date().isoformat(),
        'status':'READY','requested':150,'verified':150,'complete_technicals':150,
        'reused_baseline':21,'started_at':NOW.replace(hour=8).isoformat()})
    result = R.inspect_pool(tmp_path, CFG, NOW, verify_history=True)
    assert result['status'] == 'UNAVAILABLE' and result['complete_technicals'] == 0


def test_changed_candidate_receipt_is_not_accepted(tmp_path):
    stage(tmp_path)
    path = tmp_path/'deepseek_candidates.json'
    obj = json.loads(path.read_text());obj['candidates'][0]['technicals']['rsi']=90
    write(path,obj)
    result = R.inspect_pool(tmp_path,CFG,NOW)
    assert result['status'] == 'UNAVAILABLE'
    assert result['reason'] == 'PREPARED_POOL_MISSING_OR_CHANGED'


def test_deep_history_check_rejects_invalid_grid_even_if_receipts_resealed(tmp_path):
    stage(tmp_path)
    cache = tmp_path/'intraday_cache'/key('ABC.TO')
    item = json.loads(cache.read_text());frame = json.loads(item['frame'])
    frame['index'].pop(-1);frame['data'].pop(-1);item['frame']=json.dumps(frame)
    write(cache,item)
    path = tmp_path/'deepseek_candidates.json';payload=json.loads(path.read_text())
    payload['candidates'][0]['technical_provenance']['input_sha256'] = hashlib.sha256(cache.read_bytes()).hexdigest()
    write(path,payload);write(tmp_path/'factor_pool_history'/NOW.date().isoformat()/'candidates.json',payload)
    status=json.loads((tmp_path/'factor_pool_status.json').read_text())
    status['candidates_sha256']=hashlib.sha256(path.read_bytes()).hexdigest()
    write(tmp_path/'factor_pool_status.json',status)
    result = R.inspect_pool(tmp_path,CFG,NOW,verify_history=True)
    assert result['status'] == 'UNAVAILABLE'
    assert result['complete_technicals'] == 0
    assert 'CACHE_PRIOR_SESSION' in result['errors']['ABC.TO']


def test_pool_industries_survive_unavailable_deepseek(tmp_path, monkeypatch):
    stage(tmp_path);fake_master(monkeypatch)
    result=R.load_prepared(tmp_path,CFG,NOW,{'status':'UNAVAILABLE','covered':0})
    assert result['master_eligible']==result['pool_requested']==result['technical_complete']==1
    assert result['shortlisted'] is None and result['assessed']==0
    assert result['sectors'][0]['name']=='Industrials'
    assert result['industries'][0]['name']=='Airlines'
    assert 'PARTIAL_SOURCE_ENUMERATION' in result['gaps']


def test_sector_counts_are_research_coverage_without_forced_trade_quotas(tmp_path, monkeypatch):
    stage(tmp_path);fake_master(monkeypatch)
    factors={'status':'PARTIAL','covered':1,'assessments':[{'ticker':'ABC.TO'}],
        'research_shortlist':{'tickers':['ABC.TO'],'selected_count':1,'exclusions':[],'gaps':['SHORTLIST_BELOW_30']},
        'research_watchlist':{'evaluated':1},'news_status':{'ABC.TO':{'status':'NO_CURRENT_NEWS'}}}
    result=R.load_prepared(tmp_path,CFG,NOW,factors)
    assert result['sectors']==[{'name':'Industrials','pool':1,'technical_complete':1,'shortlisted':1,'assessed':1}]
    assert result['shortlisted']==result['usable']==1 and not result['adopted']
    assert result['news_status']['ABC.TO']['status']=='NO_CURRENT_NEWS'


def test_unavailable_master_cannot_certify_fallback_industries(tmp_path, monkeypatch):
    stage(tmp_path)
    payload=json.loads((tmp_path/'deepseek_candidates.json').read_text())
    payload['research_universe']['mode']='LEGACY_RESEARCH_FALLBACK'
    payload['research_universe']['fallback_reason']='Directory provider timeout'
    write(tmp_path/'deepseek_candidates.json',payload)
    write(tmp_path/'factor_pool_history'/NOW.date().isoformat()/'candidates.json',payload)
    status=json.loads((tmp_path/'factor_pool_status.json').read_text())
    status['candidates_sha256']=hashlib.sha256((tmp_path/'deepseek_candidates.json').read_bytes()).hexdigest()
    write(tmp_path/'factor_pool_status.json',status)
    fake_master(monkeypatch, {'status':'UNAVAILABLE','target':150,'candidates':[]})
    result=R.load_prepared(tmp_path,CFG,NOW,{'covered':0})
    assert result['master_eligible']==0 and result['technical_complete']==1
    assert result['status']=='UNAVAILABLE' and result['pool_status']=='READY'
    assert result['sectors'][0]['name']=='Unverified classification'
    assert 'Legacy research fallback' in daily_render._expanded_summary({'research_coverage':result})


def test_digest_retains_coverage_when_factor_loader_raises(tmp_path, monkeypatch):
    stage(tmp_path);fake_master(monkeypatch)
    monkeypatch.setattr('deepseek_factors.load_prepared', lambda *a,**k:(_ for _ in ()).throw(ValueError('failed snapshot')))
    monkeypatch.setattr('urllib.request.urlopen',forbidden)
    d=brief.build(now=NOW,no_net=True,state_dir=tmp_path,services=services())
    assert d['intraday']['deepseek']['status']=='UNAVAILABLE'
    coverage=d['intraday']['research_coverage']
    assert coverage['pool_requested']==1
    assert coverage['master_eligible']==1
    assert not (tmp_path/'reports.sqlite3').exists()


def test_full_and_concise_views_consume_one_digest_without_files_or_network(tmp_path, monkeypatch):
    stage(tmp_path);fake_master(monkeypatch)
    coverage=R.load_prepared(tmp_path,CFG,NOW,{'status':'UNAVAILABLE','covered':0})
    d=report();d['intraday']['research_coverage']=coverage
    d['intraday']['deepseek']=deepseek_factors.unavailable('Evidence source timed out',requested=1)
    before=encode(d)
    monkeypatch.setattr('builtins.open',forbidden)
    monkeypatch.setattr('urllib.request.urlopen',forbidden)
    monkeypatch.setattr(R,'load_prepared',forbidden)
    full=brief.render_text(d);html=brief.render_html(d);mail=email_render.text(d)
    assert encode(d)==before
    for body in (full,html):
        assert 'target 150' in body and 'Industrials 0/1' in body
        assert 'prepared technicals 1' in body and 'shortlisted unknown' in body
    assert 'target 150' not in mail   # day-114b: coverage counts live in the full report
    assert 'Airlines' in full and 'PREFERRED_SECURITY' in full
    assert len(daily_render.deepseek_summary(d['intraday']))<=6


def test_legacy_report_has_no_added_universe_or_opening_sections():
    d=report();before=copy.deepcopy(d)
    full=brief.render_text(d);mail=email_render.text(d)
    assert d==before
    assert 'TSX industry research coverage' not in full
    assert 'TSX research: target' not in mail
    assert 'Expanded opening context' not in full


def test_optional_preflight_failure_preserves_independent_sections(tmp_path,monkeypatch):
    stage(tmp_path)
    monkeypatch.setattr('bar_cache.inspect_cache',lambda *a:{'status':'READY','verified':21,'expected':21})
    monkeypatch.setattr('eodhd.load_prepared',lambda *a:{'status':'UNAVAILABLE'})
    monkeypatch.setattr('deepseek_factors.load_prepared',lambda *a:{'status':'UNAVAILABLE'})
    monkeypatch.setattr(R,'load_prepared',lambda *a,**k:(_ for _ in ()).throw(ValueError('invalid master')))
    result=preflight.check(tmp_path,NOW)
    assert result['checks']['intraday_history'].startswith('READY')
    assert result['optional_expanded_research']['status']=='UNAVAILABLE'
    assert 'quote_authentication' in result


def test_baseline_identity_resolves_actual_research_cache_by_input_hash(tmp_path):
    stage(tmp_path)
    old = tmp_path/'intraday_cache'
    directory = tmp_path/'factor_pool_cache';directory.mkdir()
    raw = (old/key('ABC.TO')).read_bytes()
    (directory/key('ABC.TO')).write_bytes(raw)
    (directory/'manifest.json').write_bytes((old/'manifest.json').read_bytes())
    write(directory/(key('ABC.TO')+'.receipt'), {
        'input_sha256':hashlib.sha256(raw).hexdigest(),
        'retrieved_at':NOW.replace(hour=8,minute=6).isoformat(),
        'response':{'meta':{'symbol':'ABC.TO','currency':'CAD','exchangeName':'TOR','instrumentType':'EQUITY'}}})
    (old/key('ABC.TO')).unlink()
    checked = R.inspect_pool(tmp_path,CFG,NOW,verify_history=True)
    assert checked['complete_technicals']==checked['verified']==1
    assert checked['cache_sources']['ABC.TO']=='factor_pool_cache/'+key('ABC.TO')
    assert not (old/key('ABC.TO')).exists()


@pytest.mark.parametrize('verify_history',[False,True])
def test_baseline_identity_cannot_bypass_research_receipt_identity_validation(tmp_path,verify_history):
    stage(tmp_path)
    old=tmp_path/'intraday_cache';directory=tmp_path/'factor_pool_cache';directory.mkdir()
    raw=(old/key('ABC.TO')).read_bytes()
    (directory/key('ABC.TO')).write_bytes(raw)
    (directory/'manifest.json').write_bytes((old/'manifest.json').read_bytes())
    write(directory/(key('ABC.TO')+'.receipt'), {
        'input_sha256':hashlib.sha256(raw).hexdigest(),
        'retrieved_at':NOW.replace(hour=8,minute=6).isoformat(),
        'response':{'meta':{'symbol':'ABC.TO','currency':'USD','exchangeName':'TOR','instrumentType':'EQUITY'}}})
    (old/key('ABC.TO')).unlink()
    checked=R.inspect_pool(tmp_path,CFG,NOW,verify_history=verify_history)
    assert checked['complete_technicals']==checked['verified']==0
    assert checked['errors']['ABC.TO']=='RESEARCH_CACHE_RECEIPT_MISMATCH'
