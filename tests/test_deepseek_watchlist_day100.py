"""Wider contextual assessments remain distinct from quantitative selection."""
import copy

import pytest

import brief
import daily_render
import deepseek_factors as D
import email_render
from report_store import encode
from test_deepseek_factors import NOW, assessment, rehash, save, snapshot
from test_deepseek_render import report


def test_loader_computes_wider_watchlist_without_baseline_scores_or_quotes(tmp_path):
    names=tuple(f'NAME{i:02}.TO' for i in range(60))
    staged=snapshot(names)
    staged['assessments']=[assessment(name,'BULL' if i%2 else 'BEAR',.7 if i%2 else -.7)
                           for i,name in enumerate(names)]
    save(tmp_path,staged)
    loaded=D.load_prepared(tmp_path,NOW)
    watch=loaded['research_watchlist']
    assert watch['status']=='READY' and watch['assessed']==watch['evaluated']==watch['eligible']==60
    assert [row['ticker'] for row in watch['bulls']]==['NAME01.TO','NAME03.TO']
    assert [row['ticker'] for row in watch['bears']]==['NAME00.TO','NAME02.TO']
    assert watch['adopted'] is False
    for row in watch['bulls']+watch['bears']:
        assert not {'quant_probability','probability','shares','entry','direction'} & row.keys()
    shadow=D.rank_shadow([],loaded,{},NOW,min_sided_p=.55,scan_available=False)
    assert shadow['evaluation_status']=='UNAVAILABLE'
    assert loaded['research_watchlist']==watch


def test_watchlist_ranking_is_deterministic_and_does_not_force_both_sides():
    staged=snapshot(('Z.TO','A.TO','B.TO'))
    staged['assessments']=[assessment('Z.TO','BULL',.8),assessment('A.TO','BULL',.8),
                           assessment('B.TO','BEAR',-.49)]
    before=encode(staged)
    first=D.research_watchlist(staged)
    staged['assessments'].reverse()
    second=D.research_watchlist(staged)
    assert [row['ticker'] for row in first['bulls']]==['A.TO','Z.TO']
    assert first['bulls']==second['bulls'] and not first['bears']
    staged['assessments'].reverse()
    assert encode(staged)==before


@pytest.mark.parametrize(('lean','score'),[('NO_EDGE',.8),('BULL',-.9),('BEAR',.9),('BULL',.499)])
def test_no_edge_sign_contradiction_and_threshold_do_not_create_candidates(lean,score):
    staged=snapshot(('A.TO',))
    staged['assessments']=[assessment('A.TO',lean,score)]
    watch=D.research_watchlist(staged)
    assert watch['decision']=='NO EDGE - WAIT'
    assert watch['evaluated']==1 and watch['eligible']==0 and not watch['bulls'] and not watch['bears']


def test_partial_failure_excludes_only_unusable_name_and_retains_real_assessment():
    staged=snapshot(('A.TO','B.TO'))
    staged['status']='PARTIAL'
    staged['candidate_gaps']['A.TO']=['STALE_NEWS']
    staged['assessments']=[assessment('A.TO','BULL',1),assessment('B.TO','BEAR',-.8)]
    watch=D.research_watchlist(staged)
    assert watch['status']=='PARTIAL' and watch['evaluated']==watch['eligible']==1
    assert not watch['bulls'] and watch['bears'][0]['ticker']=='B.TO'
    assert watch['excluded']==[{'ticker':'A.TO','reason':'STALE_NEWS'}]


def test_all_unassessed_or_incomplete_macro_stays_unavailable():
    for staged in [D.unavailable('Model not called.'),snapshot(('A.TO',))]:
        if staged.get('inputs'):
            staged['inputs']['coverage']['macro_complete']=False
        watch=D.research_watchlist(staged)
        assert watch['status']=='UNAVAILABLE' and 'NO EDGE - WAIT' not in watch['decision']
        assert not watch['bulls'] and not watch['bears']


def test_missing_or_duplicate_public_candidate_cannot_be_ranked():
    staged=snapshot(('A.TO',))
    staged['inputs']['candidates']*=2
    assert D.research_watchlist(staged)['status']=='UNAVAILABLE'
    staged['inputs']['candidates']=[]
    assert D.research_watchlist(staged)['status']=='UNAVAILABLE'


def test_concise_and_full_views_use_saved_watchlist_when_scan_and_costs_fail(monkeypatch):
    d=report()
    staged=snapshot(('EXPANDED.TO',))
    staged['assessments']=[assessment('EXPANDED.TO','BULL',.8)]
    staged['research_watchlist']=D.research_watchlist(staged)
    staged['shadow']=D.rank_shadow([],staged,{},NOW,min_sided_p=.55,scan_available=False)
    d['intraday']['deepseek']=staged
    d['intraday']['res'].update(n_names=0,coverage_fail='SCAN UNAVAILABLE')
    before=encode(d)
    def forbidden(*args,**kwargs):
        pytest.fail('Renderer attempted selection or acquisition')
    monkeypatch.setattr(D,'research_watchlist',forbidden)
    monkeypatch.setattr(D,'rank_shadow',forbidden)
    monkeypatch.setattr(D,'load_prepared',forbidden)
    concise=email_render.text(d)
    full=brief.render_html(d)
    assert 'SHADOW sentiment watchlist: BULL EXPANDED.TO' in concise
    assert 'entries unverified' in concise and 'not calibrated probabilities' in concise
    assert 'no quantitative probability' in full and 'PREREGISTER_day100' in full
    assert len(daily_render.deepseek_summary(d['intraday']))<=6
    assert encode(d)==before


def test_full_view_keeps_model_and_receipt_hashes():
    d=report()
    d['intraday']['deepseek'].update(input_sha256='a'*64,snapshot_sha256='b'*64,
        batches=[{'status':'READY','model':'deepseek-flash','response_model':'deepseek-flash','inference_mode':'thinking_disabled',
                  'input_sha256':'c'*64}])
    body=brief.render_text(d)
    assert all(digest*64 in body for digest in 'abc')
    assert 'response deepseek-flash' in body
    assert 'inference mode thinking_disabled' in body


@pytest.mark.parametrize('mode',['thinking_disabled','model_default'])
def test_loader_preserves_strict_inference_mode(tmp_path,mode):
    obj=snapshot(('A.TO',))
    obj['batches'][0]['inference_mode']=mode
    save(tmp_path,obj)
    loaded=D.load_prepared(tmp_path,NOW)
    assert loaded['status']=='READY'
    assert loaded['batches'][0]['inference_mode']==mode


@pytest.mark.parametrize('mode',['unknown','sk-fixture-secret',None,False,1,[],{}])
def test_loader_rejects_unsupported_inference_mode_without_echo(tmp_path,mode):
    obj=snapshot(('A.TO',))
    obj['batches'][0]['inference_mode']=mode
    save(tmp_path,obj)
    loaded=D.load_prepared(tmp_path,NOW)
    assert loaded['status']=='UNAVAILABLE'
    assert 'sk-fixture-secret' not in encode(loaded)


def test_historical_exclusions_are_visible_advisories_not_new_factor_failures(tmp_path):
    obj=snapshot(('A.TO',))
    obj['inputs']['candidate_diagnostics']={'A.TO':['HISTORICAL_SESSIONS_EXCLUDED:2']}
    obj['candidate_gaps']['A.TO']=['HISTORICAL_SESSIONS_EXCLUDED:3']
    rehash(obj)
    save(tmp_path,obj)
    loaded=D.load_prepared(tmp_path,NOW)
    assert loaded['candidate_diagnostics']['A.TO']==['HISTORICAL_SESSIONS_EXCLUDED:2','HISTORICAL_SESSIONS_EXCLUDED:3']
    assert not loaded['candidate_gaps'].get('A.TO')
    assert loaded['research_watchlist']['eligible']==1
    d=report();d['intraday']['deepseek']=loaded
    full=brief.render_text(d)
    assert 'HISTORICAL_SESSIONS_EXCLUDED:2' in full and 'HISTORICAL_SESSIONS_EXCLUDED:3' in full
    assert 'advisory; current evidence validated separately' in full


def test_advisory_does_not_fill_missing_current_technical_fields(tmp_path):
    obj=snapshot(('A.TO',))
    obj['inputs']['candidates'][0]['technicals']['rsi']=None
    obj['inputs']['candidate_diagnostics']={'A.TO':['HISTORICAL_SESSIONS_EXCLUDED:2']}
    rehash(obj);save(tmp_path,obj)
    loaded=D.load_prepared(tmp_path,NOW)
    assert 'TECHNICAL_UNAVAILABLE:rsi' in loaded['candidate_gaps']['A.TO']
    assert loaded['research_watchlist']['status']=='UNAVAILABLE'
