import copy
import json
import pytest
from report_store import Store
from quotes import reference_close
from import_massive_reference import import_response
from test_daily_pipeline import NOW


def test_massive_uses_its_actual_bar_not_a_documentation_link(tmp_path):
    store=Store(tmp_path);store.publish('2026-09-08',{'immutable':True})
    # Prior completed session before the September 8 holiday-adjusted report.
    raw='T,c,t\nZYME,27.15,1788552000000\n'
    row=import_response(raw,'ZYME',tmp_path,NOW.isoformat())
    assert row['provider']=='Massive' and row['source_url'].startswith('https://api.massive.com/v2/')
    assert (tmp_path/row['evidence_path']).read_text()==raw
    assert reference_close(row,'ZYME',NOW)['status']=='OK'
    for changes in ({'source_url':row['documentation_url']},{'close':99},{'ticker':'OTHER'},
                    {'source_url':row['source_url']+'?apiKey=private'}):
        assert reference_close({**row,**changes},'ZYME',NOW)['status']=='UNAVAILABLE'
    assert store.get('2026-09-08')=={'immutable':True}
    with pytest.raises(ValueError,match='conflicting'):
        import_response(raw.replace('27.15','28.15'),'ZYME',tmp_path,NOW.isoformat())


def test_reference_host_alone_is_insufficient():
    row=dict(provider='EODHD',ticker='ZYME',currency='USD',close=27.15,session='2026-09-04',retrieved_at=NOW.isoformat())
    for path in ('/docs/rest','/api/eod/OTHER','/api/eod/ZYME?api_token=secret'):
        assert reference_close({**row,'source_url':'https://eodhd.com'+path},'ZYME',NOW)['status']=='UNAVAILABLE'
