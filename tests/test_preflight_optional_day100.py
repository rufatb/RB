import datetime as dt
import json
from zoneinfo import ZoneInfo

import pytest
import preflight


@pytest.mark.parametrize('payload', [None, [], {'session': '2026-09-15', 'status': 'READY'},
    {'session': '2026-09-15', 'status': 'READY', 'requested': True}])
def test_malformed_optional_pool_cannot_abort_independent_preflight(tmp_path, monkeypatch, payload):
    monkeypatch.setattr('bar_cache.inspect_cache', lambda *a: {'status': 'READY', 'verified': 21, 'expected': 21})
    monkeypatch.setattr('eodhd.load_prepared', lambda *a: {'status': 'UNAVAILABLE'})
    monkeypatch.setattr('deepseek_factors.load_prepared', lambda *a: {'status': 'UNAVAILABLE'})
    (tmp_path/'factor_pool_status.json').write_text(json.dumps(payload))
    result = preflight.check(tmp_path, dt.datetime(2026, 9, 15, 8, 30, tzinfo=ZoneInfo('America/New_York')))
    assert result['checks']['intraday_history'].startswith('READY')
    assert result['optional_factor_pool']['status'] == 'UNAVAILABLE'
    assert 'quote_authentication' in result
