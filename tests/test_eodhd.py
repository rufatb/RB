"""Network-free EODHD contracts; fixtures do not assert real entitlements."""
import copy
import datetime as dt
import json

import numpy as np
import pandas as pd
import pytest
import requests

import eodhd as E
import prepare_eodhd as P
import study_opening_path as S

NOW=dt.datetime(2026,9,10,8,15,tzinfo=E.ET)
TOKEN='test-token-never-output'


class Response:
    def __init__(self,value=None,status=200):
        self.value=value
        self.status_code=status
    def json(self):
        return self.value


def catalog():
    return [{'Code':t[:-3],'Name':t,'Country':'Canada','Exchange':'TO',
             'Currency':'CAD','Type':'ETF' if t=='XIU.TO' else 'Common Stock'} for t in P.TICKERS]


def rows(date='2026-09-09'):
    sch=E.schedule(date,date).iloc[0]
    stamps=pd.date_range(sch['market_open'],sch['market_close'],freq='5min',inclusive='left')
    return [{'timestamp':int(s.timestamp()),'datetime':s.strftime('%Y-%m-%d %H:%M:%S'),
             'open':100.,'high':102.,'low':98.,'close':101.,'volume':1000} for s in stamps]


def test_token_never_leaks_in_error_and_transport_opens_circuit():
    calls=[]
    def bad(*a,**kw):
        calls.append(kw)
        raise requests.Timeout('https://eodhd.com/?api_token='+TOKEN)
    client=E.Client(TOKEN,transport=bad)
    with pytest.raises(E.DataGap) as err:client.get('user')
    assert TOKEN not in str(err.value)
    assert 'entitlement not tested' in str(err.value)
    with pytest.raises(E.DataGap,match='CIRCUIT_OPEN'):client.get('user')
    assert len(calls)==1 and calls[0]['allow_redirects'] is False


@pytest.mark.parametrize('status,reason',[(401,'AUTH_REJECTED'),(403,'NOT_ENTITLED'),(429,'RATE_LIMITED'),(302,'HTTP_ERROR'),(500,'HTTP_ERROR')])
def test_http_errors_are_sanitized(status,reason):
    client=E.Client(TOKEN,transport=lambda *a,**k:Response({'error':TOKEN},status))
    with pytest.raises(E.DataGap,match=reason) as err:client.get('intraday/TRP.TO',cost=5)
    assert TOKEN not in str(err.value)


def test_denied_intraday_does_not_disable_daily():
    client=E.Client(TOKEN,transport=lambda url,**kw:Response([],403 if 'intraday' in url else 200))
    with pytest.raises(E.DataGap):client.get('intraday/TRP.TO',cost=5)
    with pytest.raises(E.DataGap,match='CIRCUIT_OPEN'):client.get('intraday/ENB.TO',cost=5)
    assert client.get('eod/TRP.TO')==[]


def test_credit_costs_and_requests_are_bounded():
    client=E.Client(TOKEN,transport=lambda *a,**k:Response([]),max_credits=5)
    client.get('intraday/TRP.TO',cost=5)
    with pytest.raises(E.DataGap,match='BUDGET'):client.get('user')
    assert client.requests==1


def test_account_limits_do_not_expose_profile_or_use_extra_credits():
    payload={'name':'Private','email':'private@example.com','api_token':TOKEN,
             'dailyRateLimit':20,'apiRequests':19,'extraLimit':500,'apiRequestsDate':'2026-09-10'}
    client=E.Client(TOKEN,transport=lambda *a,**k:Response(payload))
    limits=client.limits(NOW)
    assert 'name' not in limits and 'email' not in limits and TOKEN not in json.dumps(limits)
    with pytest.raises(E.DataGap,match='PROVIDER_CREDIT_BUDGET'):client.get('intraday/TRP.TO',cost=5)


@pytest.mark.parametrize('field,value',[('Currency','USD'),('Country','United States'),('Exchange','US'),('Type','CFD')])
def test_canadian_identity_cannot_be_us_twin(field,value):
    cat=catalog();cat[0][field]=value
    with pytest.raises(E.DataGap):E.identity(cat,'TRP.TO')


def test_duplicate_catalog_identity_is_rejected():
    cat=catalog();cat.append(cat[0])
    with pytest.raises(E.DataGap):E.identity(cat,'TRP.TO')


@pytest.mark.parametrize('mutation',[
    lambda r:r.pop(), lambda r:r.append(r[-1]), lambda r:r.reverse(),
    lambda r:r[0].update(timestamp=r[0]['timestamp']+60),
    lambda r:r[0].update(datetime='2026-09-09 00:00:00'),
    lambda r:r[0].update(close=float('nan')),
    lambda r:r[0].update(volume=None), lambda r:r[0].update(volume=-1),
    lambda r:r[0].update(low=200), lambda r:r[0].update(volume=.5)])
def test_intraday_rejects_bad_granularity_coverage_or_values(mutation):
    data=rows();mutation(data)
    with pytest.raises(E.DataGap):E.five_minute_history(data,E.identity(catalog(),'TRP.TO'),NOW,dt.date(2026,9,9),dt.date(2026,9,9))


def test_full_grid_is_native_five_minute_but_not_live_quote():
    frame=E.five_minute_history(rows(),E.identity(catalog(),'TRP.TO'),NOW,dt.date(2026,9,9),dt.date(2026,9,9))
    assert len(frame)==78 and frame.index[0].hour==9 and frame.index[0].minute==30
    assert 'bid' not in frame.columns


@pytest.mark.parametrize('date',['2026-09-08','2026-09-10','2026-09-12'])
def test_reference_requires_exact_previous_exchange_session(date):
    row={'date':date,'open':100.,'high':102.,'low':98.,'close':101.,'volume':1000}
    with pytest.raises(E.DataGap):E.daily_reference([row],E.identity(catalog(),'TRP.TO'),NOW)


def test_successful_reference_has_clean_provenance():
    row={'date':'2026-09-09','open':100.,'high':102.,'low':98.,'close':101.,'volume':1000}
    result=E.daily_reference([row],E.identity(catalog(),'TRP.TO'),NOW)
    assert result['currency']=='CAD' and result['session']=='2026-09-09'
    assert result['source_url']=='https://eodhd.com/api/eod/TRP.TO'
    assert 'not live' in result['label']


def test_preparation_checks_entitlement_and_keeps_daily_references(tmp_path):
    def get(url,**kw):
        if url.endswith('/user'):return Response({'dailyRateLimit':20,'apiRequests':1,'apiRequestsDate':'2026-09-10'})
        if 'exchange-symbol-list' in url:return Response(catalog())
        if 'intraday' in url:return Response({'message':TOKEN},403)
        return Response([{'date':'2026-09-09','open':100.,'high':102.,'low':98.,'close':101.,'volume':1000}])
    client=E.Client(TOKEN,transport=get)
    result=P.prepare(tmp_path,now=NOW,client=client)
    assert len(result['references'])==5
    assert result['intraday']['status']=='NOT_ENTITLED HTTP 403'
    assert client.requests==8 and client.credits==12
    assert TOKEN not in json.dumps(result)
    assert E.load_prepared(tmp_path,NOW)['reference_count']==5
    P.prepare(tmp_path,now=NOW,client=client)
    assert client.requests==8


def test_failed_probe_preserves_previous_success(tmp_path):
    path=tmp_path/'eodhd_reference_closes.json';path.write_text('{"preserve": true}')
    client=E.Client(TOKEN,transport=lambda *a,**kw:Response({},401))
    result=P.prepare(tmp_path,now=NOW,client=client)
    assert result['gaps'] and path.read_text()=='{"preserve": true}'


def test_preparation_never_runs_after_open(tmp_path):
    with pytest.raises(E.DataGap,match='PRE_OPEN_ONLY'):P.prepare(tmp_path,now=NOW.replace(hour=9,minute=30))
    assert not list(tmp_path.iterdir())


def test_stale_prepared_evidence_is_not_current(tmp_path):
    path=tmp_path/'eodhd_status.json'
    path.write_text(json.dumps({'checked_at':'2026-09-09T08:00:00-04:00','schema_version':1,'status':'READY','references':{}}))
    assert E.load_prepared(tmp_path,NOW)['status']=='UNAVAILABLE'


def test_145_sessions_is_not_a_powered_study():
    result=S.history_requirement(145)
    assert result['potential_oos_sessions']==5 and result['status'].startswith('BLOCKED')
    assert S.history_requirement(200)['status']=='RUNNABLE'


def test_afternoon_cannot_change_opening_features():
    frame=E.five_minute_history(rows(),E.identity(catalog(),'TRP.TO'),NOW,dt.date(2026,9,9),dt.date(2026,9,9))
    a,_=S.session_features(frame,'TRP.TO',NOW)
    changed=frame.copy();changed.iloc[3:]=[200.,205.,195.,201.,9999]
    b,_=S.session_features(changed,'TRP.TO',NOW)
    for field in ['r0','v15','path_accel','path_efficiency']:assert a[0][field]==b[0][field]
    assert a[0]['r1']!=b[0]['r1']


def test_small_panel_never_fits_model_or_claims_null(monkeypatch):
    import validate_ceiling
    monkeypatch.setattr(validate_ceiling,'knn_scores',lambda *a:pytest.fail('unpowered fit'))
    panel=pd.DataFrame([{'t':'TRP.TO','date':str(d.date()),'r0':.1,'gap':.2,'v15':1000.,
                        'r1':.3,'path_accel':.1,'path_efficiency':.5}
                       for d in pd.bdate_range('2026-06-01',periods=41)])
    result=S.analyze(panel,{'fixture':True})
    assert result['status'].startswith('BLOCKED') and result['oos_sessions']==0
    assert result['mde_auc'] is None and result['adopted'] is False


def test_joint_placebo_is_finite_and_reproducible():
    rng=np.random.default_rng(17)
    sessions=np.repeat(np.arange(80),10)
    y=rng.integers(0,2,size=len(sessions))
    baseline=rng.normal(size=len(y))
    candidates={'a':baseline+.1*rng.normal(size=len(y)), 'b':baseline+.2*rng.normal(size=len(y))}
    a=S.paired_summary(y,baseline,candidates,sessions)
    b=S.paired_summary(y,baseline,candidates,sessions)
    assert a==b and all(v['max_arm_placebo_p'] >= 1/(S.DRAWS+1) for v in a.values())
    assert all(v['mde80_auc']>0 and not v['adopted'] for v in a.values())


def test_prepared_provider_is_frozen_with_report_not_read_by_renderer(tmp_path,monkeypatch):
    import brief
    from test_daily_pipeline import NOW as REPORT_NOW, services
    before=brief.compute(now=REPORT_NOW,services=services(),state_dir=tmp_path)
    monkeypatch.setattr(E,'load_prepared',lambda *a:{'status':'PARTIAL','reference_count':0,
        'intraday_status':'NOT TESTED','note':'fixture historical evidence'})
    after=brief.compute(now=REPORT_NOW,services=services(),state_dir=tmp_path)
    assert before['intraday']['legs']==after['intraday']['legs']
    monkeypatch.setattr(E,'load_prepared',lambda *a:pytest.fail('render-time lookup'))
    assert 'fixture historical evidence' in brief.render_text(after)
    assert 'fixture historical evidence' in brief.render_html(after)


def test_knn_healthy_input_preserves_arithmetic_and_bad_values_abstain():
    import r945 as R
    rng=np.random.default_rng(1)
    train=pd.DataFrame(rng.normal(size=(260,4)),columns=R.FEATS+['r1'])
    today=dict(zip(R.FEATS,[.1,.2,.3]))
    result=R.knn_probability(train,today)
    mu,sd=train[R.FEATS].mean(),train[R.FEATS].std().replace(0,1)
    distance=((((train[R.FEATS]-mu)/sd).to_numpy()-((pd.Series(today)-mu)/sd).to_numpy())**2).sum(axis=1)
    idx=np.argsort(distance)[:R.K]
    g=np.average((train['r1'].to_numpy()[idx]>0).astype(float),weights=1/(1+np.sqrt(distance[idx])))
    expected=max(R.HARD_FLOOR,min(R.HARD_CAP,round((g*R.K+.5*R.M)/(R.K+R.M),3)))
    assert result[0]==expected
    assert R.knn_probability(train,{**today,'vp':float('inf')})[0] is None
    bad=train.copy();bad.loc[0,'vp']=float('inf')
    with pytest.raises(ValueError,match='nonfinite'):R.knn_probability(bad,today)


def test_density_sample_uses_complete_frame_size():
    import r945 as R
    frame=pd.DataFrame({'r0':range(130),'gap':.1,'vp':np.nan,'r1':.1})
    frame.loc[:9,'vp']=1.
    assert R.density_cutoffs(frame)==(0.0,9e9)


def test_overlay_cannot_replace_history_or_traverse_paths(tmp_path):
    import sqlite3,zipfile
    import import_eodhd_inputs as I
    state=tmp_path/'state';state.mkdir()
    with sqlite3.connect(state/'reports.sqlite3') as db:db.execute('create table evidence(x)')
    before=(state/'reports.sqlite3').read_bytes()
    for name in ['reports.sqlite3','../escape','secrets/../../escape','unrelated.json']:
        archive=tmp_path/'input.zip'
        with zipfile.ZipFile(archive,'w') as z:z.writestr(name,'bad')
        with pytest.raises(E.DataGap):I.merge(archive,state)
        assert (state/'reports.sqlite3').read_bytes()==before


def test_overlay_preserves_newer_status_and_private_key_permissions(tmp_path):
    import sqlite3,zipfile,stat
    import import_eodhd_inputs as I
    state=tmp_path/'state';state.mkdir()
    with sqlite3.connect(state/'reports.sqlite3') as db:db.execute('create table evidence(x)')
    status={'checked_at':'2026-09-10T08:20:00-04:00','status':'PARTIAL'}
    (state/'eodhd_status.json').write_text(json.dumps(status))
    archive=tmp_path/'input.zip'
    with zipfile.ZipFile(archive,'w') as z:
        z.writestr('secrets/eodhd_api_key',TOKEN)
        z.writestr('eodhd_status.json',json.dumps({**status,'checked_at':'2026-09-10T08:00:00-04:00'}))
    result=I.merge(archive,state)
    assert TOKEN not in json.dumps(result)
    assert json.loads((state/'eodhd_status.json').read_text())==status
    assert stat.S_IMODE((state/'secrets/eodhd_api_key').stat().st_mode)==0o600


def test_overlay_requires_existing_database(tmp_path):
    import import_eodhd_inputs as I
    with pytest.raises(E.DataGap,match='EXISTING_PUBLICATION_STATE_REQUIRED'):I.merge(tmp_path/'absent.zip',tmp_path)
