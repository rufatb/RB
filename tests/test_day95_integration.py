"""Regressions found in the September 9 email and contributor integration."""
import copy
import datetime as dt
import json
from zoneinfo import ZoneInfo
import pytest
import brief
import daily_job
import daily_render
import prepare_delivery as P
import risk_evidence as R
import build_social as S
import validate_crossmarket as V
from report_store import Store
from test_daily_pipeline import NOW, services
from test_social import snapshot, sessions, stream


def test_rendering_does_not_reread_configuration_or_compute_risk(monkeypatch):
    d = brief.compute(now=NOW, services=services())
    import dashboard
    monkeypatch.setattr(dashboard, 'load_config', lambda *a:pytest.fail('render-time config'))
    monkeypatch.setattr(R, 'assess', lambda *a:pytest.fail('render-time risk'))
    assert 'How reliable is the record?' in brief.render_text(d)
    assert 'How reliable is the record?' in brief.render_html(d)


def test_dispatch_clock_updates_both_bodies_without_rewriting_publication(tmp_path):
    d = brief.compute(now=NOW, services=services())
    original = copy.deepcopy(d)
    store = Store(tmp_path/'state');store.publish(d['session'], d)
    payload = P.artifacts(store.get(d['session']), tmp_path/'out', NOW.replace(minute=48))
    assert 'INFORMATIONAL' in payload['subject']
    for key in ('text','html'):
        assert 'INFORMATIONAL' in payload[key]
        assert 'no fresh morning entry claim' in payload[key]
    assert store.get(d['session']) == original
    assert json.loads((tmp_path/'out'/'gmail_payload.json').read_text()) == payload


def test_before_0946_cannot_prepare_delivery_or_publish(tmp_path):
    d = brief.compute(now=NOW, services=services())
    with pytest.raises(ValueError, match='before 09:46'):
        P.view(d, NOW.replace(minute=45))
    with pytest.raises(ValueError, match='before 09:46'):
        daily_job.run(tmp_path/'state', tmp_path/'out',clock=lambda:NOW.replace(minute=45))
    assert not (tmp_path/'state'/'reports.sqlite3').exists()


def test_mismatched_assembly_date_never_published(tmp_path, monkeypatch):
    d = brief.compute(now=NOW, services=services())
    d['session'] = '2026-09-07'
    monkeypatch.setattr(daily_job.brief, 'compute',lambda **kw:d)
    with pytest.raises(ValueError,match='session does not match'):
        daily_job.run(tmp_path/'state',tmp_path/'out',clock=lambda:NOW)
    assert Store(tmp_path/'state').get('2026-09-08') is None


def test_perfectly_correlated_legs_do_not_narrow_session_uncertainty():
    rows=[dict(date=f'2026-08-{i:02d}',hit=str(i%2)) for i in range(1,21)]
    once=R.clustered_rate(rows)
    repeated=R.clustered_rate(rows*4)
    assert repeated['n'] == 4*once['n']
    assert repeated['ci95'] == pytest.approx(once['ci95'])
    assert repeated['mde80_pp'] == pytest.approx(once['mde80_pp'])


def test_empirical_shape_excludes_partial_sessions_and_shows_common_exposure():
    rows=[dict(date=f'2026-08-0{day}',ticker=t,hit=str(hit),p_sided='.57')
          for day,hit in ((3,1),(4,0)) for t in ('TRP.TO','ENB.TO')]
    rows += [dict(date='2026-08-05',ticker='TRP.TO',hit='1',p_sided='.57')]
    legs=[dict(ticker=t,side='LONG',baseline_alloc=100) for t in ('TRP.TO','ENB.TO')]
    r=R.assess(rows,legs,[],{'risk_groups':{'pipelines':['TRP.TO','ENB.TO']}})
    assert r['day_shape']['counts_by_hits']==[1,0,1]
    assert r['day_shape']['excluded_sessions']==1
    assert r['concentration'][0]['gross_share']==1


def test_social_excludes_stale_future_duplicate_and_naive_messages():
    now=dt.datetime.fromisoformat('2026-09-09T09:20:00-04:00')
    rows=[dict(id=1,created_at='2026-09-09T12:00:00Z',entities={'sentiment':{'basic':'Bullish'}}),
          dict(id=2,created_at='2026-09-07T12:00:00Z'),
          dict(id=3,created_at='2026-09-10T12:00:00Z'),
          dict(id=4,created_at='2026-09-09T12:00:00')]
    rows.append(rows[0])
    r=S.parse_stream(stream(messages=rows),'RY',now=now)
    assert (r['msgs_24h'],r['bullish'],r['duplicate_messages'],r['older_messages'],
            r['future_messages'],r['rejected_messages'])==(1,1,1,1,1,1)


def test_social_first_write_survives_rerun(tmp_path):
    a=snapshot('2026-09-08',{'RY.TO':4})
    path=S.write_snapshot(a,str(tmp_path))
    with pytest.raises(FileExistsError):
        S.write_snapshot(snapshot('2026-09-08',{'RY.TO':100}),str(tmp_path))
    assert json.loads(open(path).read())==a


def test_social_gate_cannot_count_duplicate_late_or_non_session_snapshots():
    snaps=[snapshot(d,{'RY.TO':4}) for d in sessions(20)]
    snaps[0]['completed_at']=snaps[0]['date']+'T09:30:01-04:00'
    snaps.append(copy.deepcopy(snaps[1]))
    snaps.append(snapshot('2026-08-08',{'RY.TO':4}))  # Saturday
    r=S.coverage_gate(snaps)
    assert r['sessions_collected']==19 and r['gate']=='COLLECTING'
    assert len(r['rejected_snapshots'])==3
    assert not r['names']['RY.TO']['usable']


def yahoo_payload():
    days=__import__('pandas').bdate_range('2026-08-03',periods=20,tz='UTC')
    return {'chart':{'result':[{'meta':{'symbol':'RY.TO','dataGranularity':'1d'},
        'timestamp':[int(t.timestamp()) for t in days],
        'indicators':{'quote':[dict(open=[100]*20,high=[102]*20,low=[99]*20,close=[101]*20)],
                      'adjclose':[{'adjclose':[101]*20}]}}]}}


def test_daily_parser_never_collapses_intraday_or_duplicate_bars():
    p=yahoo_payload()
    assert len(V.parse_yahoo(p,'RY.TO'))==20
    p['chart']['result'][0]['meta']['dataGranularity']='5m'
    with pytest.raises(V.GranularityError):V.parse_yahoo(p,'RY.TO')
    p=yahoo_payload();p['chart']['result'][0]['timestamp'][1]=p['chart']['result'][0]['timestamp'][0]
    with pytest.raises(V.GranularityError,match='duplicate'):V.parse_yahoo(p,'RY.TO')


def test_missing_daily_rows_are_counted_not_dropped():
    p=yahoo_payload();p['chart']['result'][0]['indicators']['quote'][0]['open'][3]=None
    with pytest.raises(ValueError,match='1 incomplete'):V.parse_yahoo(p,'RY.TO')


def test_fx_start_label_cannot_certify_prior_session_close():
    p=yahoo_payload();p['chart']['result'][0]['meta']['symbol']='USDCAD=X'
    with pytest.raises(ValueError,match='completion times not authenticated'):
        V.parse_yahoo(p,'USDCAD=X')


def test_completed_session_uses_exchange_close_in_et():
    now=dt.datetime(2026,9,10,0,1,tzinfo=dt.timezone.utc)
    assert V.default_last_complete(now)=='2026-09-09'
    assert V.default_last_complete(now.astimezone(ZoneInfo('America/New_York')).replace(hour=15))=='2026-09-08'
