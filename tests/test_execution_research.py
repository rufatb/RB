"""Positive/negative controls and execution-cost arithmetic, not fitted outcomes."""
import numpy as np
import pytest
import execution as E
import validate_execution as V
import ledger


def test_tiny_gross_win_is_net_loss_after_two_crossings():
    leg={'side':'LONG','quote':{'status':'OK','bid':99.9,'ask':100.1,'spread_bps':20}}
    exit={'status':'OK','bid':99.95,'ask':100.15,'spread_bps':.2/100.05*10000}
    r=E.score_leg(leg,exit,.03,fees_bps=0,slippage_bps=0)
    assert r['gross_pct']>0 and r['net_pct']<0 and not r['net_hit']
    assert r['selection_net_pct']+r['tide_pct']==pytest.approx(r['net_pct'])


def test_absent_costs_cannot_become_zero():
    leg={'side':'LONG','quote':{'status':'OK'}}
    with pytest.raises(ValueError,match='costs'):
        E.score_leg(leg,{'status':'OK'},0)


def test_historical_nonfinite_and_negative_spreads_are_unpriced():
    rows=[{'side':'LONG','r1':'1','spread_bps':s} for s in ['nan','inf','-1','']]
    a=ledger.accuracy(rows)
    assert a['net_n']==0 and a['net_unpriced']==4
    assert a['net_rate'] is None


def test_net_hit_rate_can_differ_from_gross_without_changing_legacy_hits():
    rows=[{'side':'LONG','r1':'.01','spread_bps':'5'},{'side':'SHORT','r1':'-.4','spread_bps':'5'}]
    a=ledger.accuracy(rows)
    assert a['hits']==2 and a['net_hits']==1 and a['net_rate']==.5


def test_mde_requires_independent_sessions():
    assert V.estimate([5])['mde80_bps'] is None
    assert V.estimate([])['mean_bps'] is None
    assert V.estimate([1,1])['status'].startswith('DEGENERATE')


def test_positive_control_detects_known_edge_and_placebo_does_not():
    noise=np.tile([-2.,2.],300)
    positive=V.estimate(noise+5)
    placebo=V.estimate(noise)
    assert positive['status']=='POWERED' and positive['z']>V.Z
    assert placebo['z']==0
    assert positive['mde80_bps']==pytest.approx(placebo['mde80_bps'])
    assert positive['positive_control_z']==pytest.approx(placebo['positive_control_z'])


def test_noisy_small_sample_is_underpowered_even_with_positive_mean():
    a=V.estimate([-200,205])
    assert a['status']=='UNDERPOWERED' and a['mde80_bps']>5


def test_abstentions_are_zero_on_same_days_not_dropped_sessions():
    assert V.paired_session_rows({'a':10,'b':-10},{'a':10,'b':0})==[0,10]
    with pytest.raises(ValueError,match='missing'):
        V.paired_session_rows({'a':10,'b':-10},{'a':10})


def test_max_placebo_accounts_for_the_whole_grid():
    rng=np.random.default_rng(90)
    noise=rng.normal(size=(100,4))
    assert V.placebo_max(noise)>V.placebo_max(noise[:,:1])


def test_historical_proxy_cannot_pass_native_gate():
    out=V.gate_native([],{'exact_bbo':False})
    assert out['status']=='BLOCKED'
    out=V.gate_native([],{'exact_bbo':True,'point_in_time_universe':True,'all_costs':True})
    assert out['status']=='NO_ADOPTION' and out['adopted']==[]


def native_panel(plant):
    import datetime as dt
    rng=np.random.default_rng(90);rows=[]
    keys=('baseline_net_bps','h1_net_bps','h2_net_bps','exit1530_net_bps','exit1545_net_bps')
    for market in ('TSX','US'):
        import pandas_market_calendars as mcal
        calendar=mcal.get_calendar('TSX' if market=='TSX' else 'NYSE')
        schedule=calendar.schedule(start_date='2026-09-09',end_date='2027-12-31')
        closes=schedule['market_close'].dt.tz_convert('America/New_York')
        dates=[i.date().isoformat() for i,c in closes.items() if c.hour>=16][:252]
        for day in range(252):
            base=float(rng.normal(0,10));edge=float(plant+rng.normal(0,1))
            for name in range(10):
                row={'session':dates[day],
                     'market':market,'ticker':f'FIXTURE{name}','weight':.1,
                     'side':'LONG' if name<5 else 'SHORT',
                     'entry_spread_bps':1.,'trailing_vol_pct':1.}
                for key,scale,value in zip(keys,[1,1,.99,1,1],[base,base,.99*base,base+edge,base+edge]):
                    row.update({key:value,key+'_scale':scale,key+'_index_bps':0.})
                rows.append(row)
    return rows


def test_native_end_to_end_plant_detected_without_promoting_cost_overlays():
    out=V.gate_native(native_panel(6),{'exact_bbo':True,'point_in_time_universe':True,'all_costs':True},as_of='2028-01-01')
    assert out['status']=='CANDIDATE_REQUIRES_REVIEW'
    assert out['adopted']==['H3a_exit_1530','H3b_exit_1545']
    assert not out['production_settings_changed']


def test_native_placebo_and_mislabelled_overlay_cannot_pass():
    panel=native_panel(0);metadata={'exact_bbo':True,'point_in_time_universe':True,'all_costs':True}
    assert V.gate_native(panel,metadata,as_of='2028-01-01')['adopted']==[]
    panel[0]['h1_net_bps']+=5
    with pytest.raises(ValueError,match='overlay'):
        V.gate_native(panel,metadata,as_of='2028-01-01')
