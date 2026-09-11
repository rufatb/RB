import datetime as dt
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
import pytest

import intraday_history as H
import r945

ET = ZoneInfo('America/New_York')
NOW = dt.datetime(2026, 9, 11, 9, 46, tzinfo=ET)


def day(date, price=100, periods=78):
    ix = pd.date_range(date+' 09:30', periods=periods, freq='5min', tz=ET)
    c = price+np.linspace(0, 1, periods)
    return pd.DataFrame(dict(Open=c, High=c+.1, Low=c-.1, Close=c, Volume=1000), index=ix)


def test_clean_history_matches_legacy_arithmetic_and_current_day_never_trains():
    f = pd.concat([day('2026-09-08'), day('2026-09-09', 102), day('2026-09-10', 103)])
    expected = r945.session_rows(f, 'X.TO')
    actual = H.completed_history(pd.concat([f, day('2026-09-11', 999)]), 'X.TO', NOW)
    assert actual['rows'] == expected
    assert actual['prior_close'] == 104
    assert actual['diagnostics']['accepted_sessions'] == 3
    assert actual['diagnostics']['missing_previous_closes'] == 1


@pytest.mark.parametrize('corrupt', ['missing_open', 'missing_middle', 'truncated', 'duplicate', 'wrong_grid'])
def test_historical_bar_defects_never_become_labels(corrupt):
    good = day('2026-09-09'); bad = day('2026-09-10')
    if corrupt == 'missing_open': bad = bad.iloc[1:]
    elif corrupt == 'missing_middle': bad = bad.drop(bad.index[40])
    elif corrupt == 'truncated': bad = bad.iloc[:10]
    elif corrupt == 'duplicate': bad = pd.concat([bad, bad.iloc[-1:]])
    else: bad.index = bad.index+pd.Timedelta(minutes=1)
    if corrupt == 'duplicate':
        with pytest.raises(ValueError, match='duplicate'):
            H.completed_history(pd.concat([good, bad]), 'X.TO', NOW)
        return
    result = H.completed_history(pd.concat([good, bad]), 'X.TO', NOW)
    assert len(result['rows']) == 1
    assert result['prior_close'] is None
    assert result['diagnostics']['rejected_sessions'] == 1


@pytest.mark.parametrize(('field','value'), [('Open',0), ('Close',np.inf), ('Volume',np.nan),
                                           ('Volume',-1), ('High',99), ('Low',105)])
def test_corrupt_history_and_live_signal_are_both_refused(field, value):
    bad = day('2026-09-10');bad.loc[bad.index[1], field] = value
    assert H.completed_history(bad, 'X.TO', NOW)['rows'] == []
    live = day('2026-09-11');live.loc[live.index[1], field] = value
    assert not r945.validate_signal_bars(live, dt.time(9,30), str(ET), NOW)[0]


def test_missing_exchange_session_breaks_gap_but_holiday_does_not():
    missing = H.completed_history(pd.concat([day('2026-09-08'),day('2026-09-10')]), 'X.TO', NOW)
    assert missing['rows'][-1]['gap'] is None
    assert any(e['reason']=='MISSING_SESSION' for e in missing['diagnostics']['exclusions'])
    holiday = H.completed_history(pd.concat([day('2026-09-04'),day('2026-09-08')]), 'X.TO',
                                 dt.datetime(2026,9,9,9,46,tzinfo=ET))
    assert holiday['rows'][-1]['gap'] == pytest.approx((100/101-1)*100)


def test_close_marker_after_hours_and_future_cannot_change_training():
    regular = day('2026-09-10')
    junk = regular.iloc[-1:].copy();junk.index += pd.Timedelta(minutes=5)
    junk.loc[:,'Close'] = 900
    f = pd.concat([regular,junk,day('2026-09-11',999),day('2026-09-14',999)])
    result = H.completed_history(f, 'X.TO', NOW)
    assert result['rows'] == H.completed_history(regular, 'X.TO', NOW)['rows']
    assert result['prior_close'] == 101
    assert result['diagnostics']['outside_session_bars'] == 1


def test_short_session_close_can_anchor_next_session_but_is_not_a_full_label():
    now = dt.datetime(2025,12,30,9,46,tzinfo=ET)
    schedule = H.session_schedule('2025-12-24','2025-12-24')
    n = int((schedule.iloc[0]['market_close']-schedule.iloc[0]['market_open']).total_seconds()/300)
    assert n != 78
    result = H.completed_history(pd.concat([day('2025-12-24',periods=n),day('2025-12-29')]), 'X.TO', now)
    assert len(result['rows']) == 1
    assert result['rows'][0]['gap'] == pytest.approx((100/101-1)*100)


def test_naive_and_unsorted_timestamps_are_not_silently_repaired():
    f = day('2026-09-10');f.index=f.index.tz_localize(None)
    with pytest.raises(ValueError,match='aware'):
        H.completed_history(f,'X.TO',NOW)
    with pytest.raises(ValueError,match='unsorted'):
        H.completed_history(day('2026-09-10').iloc[::-1],'X.TO',NOW)


def test_live_run_uses_validated_history_and_preserves_exclusion_diagnostics(monkeypatch):
    import bar_cache
    from adapters import YahooDirectAdapter
    from dashboard import load_config
    cfg=load_config('config.yaml');cfg['scan']['universe']=['X.TO']
    historical=pd.concat([day('2026-09-08'), day('2026-09-09',periods=10), day('2026-09-10')])
    frame=pd.concat([historical, day('2026-09-11',periods=4)])
    monkeypatch.setattr(r945,'build_adapter',lambda *a,**kw:YahooDirectAdapter())
    monkeypatch.setattr(bar_cache,'get_bars',lambda *a:frame)
    class Clock(dt.datetime):
        @classmethod
        def now(cls,tz=None): return NOW.astimezone(tz)
    monkeypatch.setattr(r945.dt,'datetime',Clock)
    monkeypatch.setattr(r945,'density_cutoffs',lambda train:(0,1))
    seen=[]
    def score(train, current):
        seen.extend(train.to_dict('records'))
        return None,len(train),None
    monkeypatch.setattr(r945,'knn_probability',score)
    result=r945.run(cfg)
    assert result['training_history'][0]['rejected_sessions']==1
    assert seen and all(r['date']!='2026-09-09' for r in seen)
    assert all(pd.isna(r['gap']) for r in seen)
    assert result['coverage_fail'] and result['n_names']==0


def test_side_concentration_is_computed_then_rendered_next_to_legs():
    import copy
    import brief
    import email_render
    import risk_evidence
    from test_daily_pipeline import services,NOW as TEST_NOW
    report=brief.compute(now=TEST_NOW,services=services())
    legs=[dict(ticker='TRP.TO',side='LONG',baseline_alloc=10),
          dict(ticker='ENB.TO',side='LONG',baseline_alloc=15),
          dict(ticker='BCE.TO',side='SHORT',baseline_alloc=25)]
    risk=risk_evidence.assess([],legs,[],{})
    assert risk['concentration'][0]['side_share']==1
    assert risk['concentration'][0]['gross_share']==.5
    report['intraday']['risk_evidence']=risk
    before=copy.deepcopy(report)
    body=email_render.text(report)
    assert body.index('Common exposure: TRP.TO, ENB.TO')<body.index('## Positions')
    assert '100% of the LONG side' in body
    assert report==before
