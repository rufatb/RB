"""Economic/temporal controls for the isolated day91 simulation."""
import numpy as np
import pandas as pd
import pandas_market_calendars as mcal
import pytest
import json

import research_sweep as rs


def fixture_panel(n=100):
    schedule=mcal.get_calendar('NYSE').schedule('2025-01-01','2025-12-31').iloc[:n]
    idx=schedule.index
    frames={t:pd.DataFrame({'o':100.,'c':100.,'h':101.,'l':99.,'v':1000.},index=idx) for t in rs.ALL_TICKERS}
    signal=pd.DataFrame({t:float(j) for j,t in enumerate(rs.ALL_TICKERS)},index=idx)
    return dict(schedule=schedule,frames=frames,dividends=pd.DataFrame(0.,index=idx,columns=rs.ALL_TICKERS),
                signals={look:signal.copy() for look in rs.LOOKBACKS},
                vol=pd.DataFrame(.01,index=idx,columns=rs.ALL_TICKERS),joint=pd.Series(True,index=idx))


def test_fixed_family_and_four_leg_capacity():
    assert len(rs.arm_specs())==48
    assert len({a['id'] for a in rs.arm_specs()})==48
    p=fixture_panel()
    for spec in rs.arm_specs():
        legs=rs.choose_legs(p['signals'][1].iloc[0],p['vol'].iloc[0],spec['direction'],spec['sizing'])
        assert len({t for t,s,w in legs})==4
        assert sum(w for t,s,w in legs if s==1)==pytest.approx(.5)
        assert sum(w for t,s,w in legs if s==-1)==pytest.approx(.5)


def test_dividend_entitlement_and_short_liability():
    p=fixture_panel(); t=rs.TICKERS[0]
    p['frames'][t].iloc[1,p['frames'][t].columns.get_loc('o')]=99.
    p['frames'][t].iloc[1,p['frames'][t].columns.get_loc('c')]=99.
    p['dividends'].iloc[1,p['dividends'].columns.get_loc(t)]=1.
    assert rs.window_return(p,t,0,1,'overnight')==pytest.approx(0.)
    assert rs.window_return(p,t,1,1,'intraday')==pytest.approx(0.)
    p['frames'][t].iloc[1,p['frames'][t].columns.get_loc('o')]=100.
    assert -rs.window_return(p,t,0,1,'overnight')==pytest.approx(-.01)


def test_costs_can_make_every_flat_trade_a_loss():
    p=fixture_panel(); a=rs.arm_specs()[0]
    rows,_=rs.simulate(p,a,[np.arange(61,70)])
    assert rows and all(r['gross']==0 for r in rows)
    assert all(r['net_10']<-.001 for r in rows)  # fee plus intraday short borrow
    assert all(r['hit_10']==0 for r in rows)
    assert all(r['net_25']<r['net_10']<r['net_5'] for r in rows)


def test_weekly_nonoverlap_and_boundary_exclusion():
    p=fixture_panel()
    a=next(s for s in rs.arm_specs() if s['horizon']=='weekly')
    rows,missing=rs.simulate(p,a,[np.arange(61,73),np.arange(73,84)])
    assert len(rows)==4 and missing==2
    assert all(r['exit_date']<n['date'] for r,n in zip(rows,rows[1:]))
    assert all(r['occupied_sessions']==5 for r in rows)


def test_missing_intermediate_weekly_session_is_not_bridged():
    p=fixture_panel(); p['joint'].iloc[63]=False
    a=next(s for s in rs.arm_specs() if s['horizon']=='weekly')
    rows,missing=rs.simulate(p,a,[np.arange(61,71)])
    assert len(rows)==1 and missing==1
    assert rows[0]['date']==p['schedule'].index[66].date().isoformat()


def test_future_mutation_cannot_change_earlier_selection_or_outcome():
    p=fixture_panel(); a=rs.arm_specs()[0]
    before,_=rs.simulate(p,a,[np.arange(61,70)])
    for t in rs.ALL_TICKERS:
        p['frames'][t].iloc[75:]=99999
    for n in rs.LOOKBACKS:
        p['signals'][n].iloc[75:]=-99999
    after,_=rs.simulate(p,a,[np.arange(61,70)])
    assert before==after


def test_known_control_and_degenerate_missing_inference():
    rng=np.random.default_rng(8)
    noise=rng.normal(0,.0003,500)
    noise-=noise.mean()
    control=rs.bootstrap_summary(noise+.0005)
    assert control['mean']==pytest.approx(5.)
    assert control['positive_control_5bps_z']==pytest.approx(5/control['se'])
    assert control['target_5bps_detectable']
    assert rs.bootstrap_summary([])['mde80'] is None
    assert rs.bootstrap_summary([.1])['mde80'] is None
    assert rs.bootstrap_summary([.1]*50)['z'] is None
    assert rs.bootstrap_summary(noise[:30])['status']=='UNDERPOWERED'


def test_holm_corrects_entire_predeclared_family():
    arms=[{'primary':{'p':.0005 if i==0 else .02}} for i in range(48)]
    rs.holm_adjust(arms)
    assert arms[0]['holm_p']==pytest.approx(.024)
    assert all(a['holm_p']>=a['primary']['p'] for a in arms)


def write_inputs(tmp_path):
    p=fixture_panel(180)
    folder=tmp_path/'development'; folder.mkdir()
    (tmp_path/'confirmation').mkdir()
    for j,t in enumerate(rs.ALL_TICKERS):
        d=p['frames'][t].copy()
        d['c']=100+np.arange(len(d))*(j+1)*.01
        d['o']=d.c-.01; d['h']=d.c+1; d['l']=d.o-1
        d['t']=(d.index.tz_localize('America/New_York').tz_convert('UTC').asi8//10**6)
        d.to_csv(folder/f'{t}.csv',index=False)
    pd.DataFrame(columns=['id','ticker','currency','ex_dividend_date','split_adjusted_cash_amount']).to_csv(folder/'dividends.csv',index=False)
    request=dict(start='2025-01-01',end='2025-12-31',tickers=list(rs.ALL_TICKERS),pagination_exhausted=True,
                 adjustment_basis='current_share_split_adjusted',sha256=rs.file_hash(folder/'dividends.csv'))
    m=dict(mode='SHORT_HISTORY_FEASIBILITY',distribution_requests={'development':request})
    (tmp_path/'manifest.json').write_text(json.dumps(m))
    return m


def test_loader_features_are_prior_only_and_do_not_bridge_gaps(tmp_path):
    write_inputs(tmp_path)
    before=rs.load_panel(tmp_path,'development')
    path=tmp_path/'development'/f'{rs.TICKERS[0]}.csv'
    d=pd.read_csv(path)
    d.loc[100:,['o','h','l','c']]*=2
    d.to_csv(path,index=False)
    after=rs.load_panel(tmp_path,'development')
    for n in rs.LOOKBACKS:
        pd.testing.assert_frame_equal(before['signals'][n].iloc[:101],after['signals'][n].iloc[:101])
    d=d.drop(index=75); d.to_csv(path,index=False)
    gap=rs.load_panel(tmp_path,'development')
    assert pd.isna(gap['signals'][5].iloc[77][rs.TICKERS[0]])


def test_partial_dividend_request_is_never_complete(tmp_path):
    m=write_inputs(tmp_path)
    m['distribution_requests']['development']['pagination_exhausted']=False
    (tmp_path/'manifest.json').write_text(json.dumps(m))
    assert not rs.load_panel(tmp_path,'development')['dividends_available']


def test_confirmation_cannot_open_before_freeze_validation(monkeypatch,tmp_path):
    def forbidden(*args):
        pytest.fail('confirmation inputs opened before registration check')
    monkeypatch.setattr(rs,'load_panel',forbidden)
    with pytest.raises(ValueError,match='frozen development'):
        rs.run(tmp_path,'confirmation',tmp_path/'out.json')


def test_constant_samples_have_no_zero_mde():
    out=rs.bootstrap_summary([.02]*100)
    assert out['mde80'] is None and out['ci95'] is None
    assert out['status']=='DEGENERATE_INFERENCE'
