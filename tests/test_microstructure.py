import datetime as dt
import json
import csv
import numpy as np
import pandas as pd
import pytest
import study_microstructure as M
from bar_cache import key


def bars(date='2026-09-09'):
    index=pd.date_range(date+' 09:30',periods=78,freq='5min',tz=M.E.ET)
    frame=pd.DataFrame({'Open':100.,'High':101.,'Low':99.,'Close':100.,'Volume':100.},index=index)
    frame.iloc[3]=[100.,103.,99.,102.,100.]
    frame.iloc[4]=[103.,104.,102.,103.,100.]
    frame.iloc[-1]=[105.,106.,104.,105.,100.]
    return frame


def test_confirmation_ignores_future_and_current_entry_bar():
    a=bars();f=M.opening_features(a,[300.]*20,'LONG')
    b=a.copy();b.iloc[4:]=[1000.,1100.,900.,1050.,999999.]
    assert M.opening_features(b,[300.]*20,'LONG')==f
    assert f['confirmed'] and f['feature_available_at']=='09:50 ET'
    assert f['opening_rvol']==1


def test_gap_after_confirmation_is_paid_not_filled_at_trigger():
    r=M.evaluate_leg({'date':'2026-09-09','ticker':'A.TO','side':'LONG'},bars(),[300.]*20)
    assert r['arms']['orb_vwap']['gross_bps']==pytest.approx((105/103-1)*10000)
    assert r['arms']['baseline_proxy']['gross_bps']==pytest.approx(500)
    assert not r['arms']['orb_vwap_rvol']['taken']
    assert r['arms']['orb_vwap_rvol']['gross_bps']==0
    short=M.evaluate_leg({'date':'2026-09-09','ticker':'A.TO','side':'SHORT'},bars(),[300.]*20)
    assert short['arms']['baseline_proxy']['gross_bps']==pytest.approx(-500)
    assert not short['arms']['orb_vwap']['taken']


def test_rvol_uses_same_window_history_not_daily_volume():
    a=bars();a.iloc[:3,a.columns.get_loc('Volume')]=250
    assert M.opening_features(a,[300.]*20,'LONG')['opening_rvol']==2.5
    with pytest.raises(ValueError):M.opening_features(a,[300.]*19,'LONG')
    with pytest.raises(ValueError):M.opening_features(a,[0.]*20,'LONG')


def test_abstentions_keep_capacity_and_statistics_cluster_by_session():
    rows=[]
    rng=np.random.default_rng(4)
    for i in range(50):
        for j in range(4):
            base=float(rng.normal(0,30))
            rows.append({'session':str(i).zfill(3),'arms':{n:{'taken':n!='rvol_2p5','gross_bps':0. if n=='rvol_2p5' else base+(30 if n=='delay_only' else 0)+rng.normal()} for n in M.ARMS}})
    s=M.summarize(rows)
    assert s['arms']['rvol_2p5']['capacity']==200
    assert s['arms']['rvol_2p5']['conditional_gross_hit_rate'] is None
    assert s['arms']['rvol_2p5']['capacity_daily_gross_bps']==0
    doubled=M.summarize(rows+rows)
    assert doubled['arms']['delay_only']['se_bps']==pytest.approx(s['arms']['delay_only']['se_bps'])
    assert s['arms']['delay_only']['paired_delta_bps']>s['arms']['delay_only']['mde80_gross_bps']
    assert s['arms']['baseline_proxy']['proportional_cost_scenarios_bps']['10']==pytest.approx(s['arms']['baseline_proxy']['capacity_daily_gross_bps']-10)


def test_bad_reference_removes_whole_original_board_not_just_losing_leg(tmp_path):
    dates=M.E.schedule(dt.date(2026,7,2),dt.date(2026,8,15)).index[:22]
    cache=tmp_path/'cache';cache.mkdir()
    now=dt.datetime(2026,9,10,8,tzinfo=M.E.ET)
    (cache/'manifest.json').write_text(json.dumps({'complete':True,'source':'yahoo_direct','session':'2026-09-10','prepared_at':now.isoformat()}))
    for ticker in ['A.TO','B.TO']:
        frame=pd.concat([bars(str(d.date())) for d in dates])
        encoded={'columns':list(frame.columns),'index':[i.isoformat() for i in frame.index],'data':frame.to_numpy().tolist()}
        (cache/key(ticker)).write_text(json.dumps({'ticker':ticker,'session':'2026-09-10','frame':json.dumps(encoded)}))
    ledger=tmp_path/'ledger.csv'
    with ledger.open('w') as f:
        w=csv.DictWriter(f,fieldnames=['date','ticker','side','role','p945']);w.writeheader()
        for date in dates[-2:]:
            for t in ['A.TO','B.TO']:
                w.writerow(dict(date=str(date.date()),ticker=t,side='LONG',role='pair',p945=999 if t=='B.TO' and date==dates[-1] else 100))
    matched,p=M.load_inputs(cache,ledger,now)
    assert len(matched)==2
    assert len(p['excluded_boards'])==1 and p['excluded_boards'][0]['original_legs']==2
    assert 'reference differs' in p['excluded_boards'][0]['gaps'][0]['reason']
