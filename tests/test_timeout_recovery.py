import datetime as dt
import json
import time
from concurrent.futures import ThreadPoolExecutor

import pytest
from bounded import acquire, progress
from test_daily_pipeline import NOW, services


def test_timeout_retains_last_stage_and_completed_tickers():
    def work():
        progress('fetch_started', count=2)
        progress('symbol_received', ticker='TRP.TO', count=3)
        progress('density_started')
        time.sleep(2)
    result = acquire({'intraday': (work, .2)})['intraday']
    assert result['error'] == 'TimeoutExpired'
    assert [x['stage'] for x in result['progress']] == [
        'fetch_started', 'symbol_received', 'density_started']
    assert result['progress'][1]['ticker'] == 'TRP.TO'


def test_concurrent_progress_does_not_corrupt_final_result():
    def work():
        with ThreadPoolExecutor(max_workers=8) as ex:
            list(ex.map(lambda i: progress('symbol_received', count=i), range(21)))
        return {'finished': 21}
    result = acquire({'intraday': (work, 2)})['intraday']
    assert result['value'] == {'finished': 21}
    assert len(result['progress']) == 21


def test_progress_cannot_extend_deadline():
    def work():
        while True:
            progress('fetch_started')
            time.sleep(.005)
    start = time.monotonic()
    result = acquire({'loop': (work, .15)})['loop']
    assert result['error'] == 'TimeoutExpired'
    assert time.monotonic()-start < 1.5


def test_progress_rejects_provider_urls_and_secrets():
    with pytest.raises(ValueError):
        progress('fetch_started', url='https://example.com?token=secret')
    with pytest.raises(ValueError):
        progress('fetch_started', error_class='https://example.com?token=secret')


def test_daily_default_config_is_independent_of_working_directory(tmp_path, monkeypatch):
    import brief
    monkeypatch.chdir(tmp_path)
    result = brief.compute(now=NOW, no_net=True, services=services())
    assert result['session'] == NOW.date().isoformat()
    assert 'Part 1' in brief.render_text(result)


def test_cached_intraday_has_small_socket_budget_without_changing_plain_adapter(tmp_path, monkeypatch):
    import r945
    import bar_cache
    import pandas as pd
    from adapters import YahooDirectAdapter
    from dashboard import load_config
    adapter = YahooDirectAdapter()
    monkeypatch.setenv('RB_INTRADAY_CACHE_DIR', str(tmp_path))
    monkeypatch.setattr(r945, 'build_adapter', lambda *a, **kw: adapter)
    observed = []
    def bars(a, ticker, now):
        observed.append(a.timeout)
        return pd.DataFrame()
    monkeypatch.setattr(bar_cache, 'get_bars', bars)
    class Clock(dt.datetime):
        @classmethod
        def now(cls, tz=None):
            return NOW.astimezone(tz)
    monkeypatch.setattr(r945.dt, 'datetime', Clock)
    cfg = load_config(str(__import__('brief').ROOT/'config.yaml'))
    result = r945.run(cfg)
    assert observed and max(observed) == 2
    assert result['n_names'] == 0
    assert YahooDirectAdapter().timeout == 20
