"""Acquisition budgets cannot alter healthy baseline inputs or manufacture bars."""
import datetime as dt
import json
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest
import requests

import adapters
import bounded
import r945


def response():
    return SimpleNamespace(raise_for_status=lambda: None,
                           json=lambda: {'chart': {'result': [{'timestamp': [1]}]}})


def test_reachable_chart_slower_than_two_seconds_is_accepted(monkeypatch):
    clock = [0.]
    monkeypatch.setattr(adapters.time, 'monotonic', lambda: clock[0])
    adapter = adapters.YahooDirectAdapter(timeout=8)
    adapter.chart_budget_seconds = 8
    def get(*args, **kwargs):
        assert kwargs['timeout'] == 8
        clock[0] += 7.2
        return response()
    adapter._requests = SimpleNamespace(get=get)
    assert adapter._chart('ENB.TO', '5m', '1d') == {'timestamp': [1]}


def test_hosts_share_budget_and_response_after_deadline_is_refused(monkeypatch):
    clock = [0.]
    monkeypatch.setattr(adapters.time, 'monotonic', lambda: clock[0])
    adapter = adapters.YahooDirectAdapter(timeout=8)
    adapter.chart_budget_seconds = 8
    seen = []
    def get(*args, **kwargs):
        seen.append(kwargs['timeout'])
        clock[0] += 3 if len(seen) == 1 else 6
        if len(seen) == 1:
            raise requests.ConnectionError('https://private.test/?token=PRIVATE_TOKEN')
        return response()
    adapter._requests = SimpleNamespace(get=get)
    with pytest.raises(adapters.ChartTimeoutError) as caught:
        adapter._chart('ENB.TO', '5m', '1d')
    assert seen == [8, 5]
    assert 'PRIVATE_TOKEN' not in str(caught.value)


def test_expired_global_deadline_does_not_start_queued_symbol(monkeypatch):
    monkeypatch.setattr(adapters.time, 'monotonic', lambda: 18.)
    adapter = adapters.YahooDirectAdapter(timeout=8)
    adapter.chart_budget_seconds = 8
    adapter.chart_deadline = 18
    adapter._requests = SimpleNamespace(get=lambda *a, **kw: pytest.fail('late request'))
    with pytest.raises(adapters.ChartTimeoutError):
        adapter._chart('ENB.TO', '5m', '1d')


@pytest.mark.parametrize('status,kind', [(429, adapters.ChartRateLimitError),
    (401, adapters.ChartAuthenticationError), (403, adapters.ChartAuthenticationError)])
def test_rate_limit_and_auth_failure_are_not_retried(status, kind, caplog):
    calls = []
    def get(*args, **kwargs):
        calls.append(1)
        raise requests.HTTPError('PRIVATE_TOKEN', response=SimpleNamespace(status_code=status))
    adapter = adapters.YahooDirectAdapter()
    adapter._requests = SimpleNamespace(get=get)
    with pytest.raises(kind) as caught:
        adapter._chart('ENB.TO', '5m', '1d')
    assert len(calls) == 1
    assert 'PRIVATE_TOKEN' not in str(caught.value) + caplog.text


def test_worker_refuses_uncontrolled_exception_metadata():
    def work():
        exc = RuntimeError('PRIVATE_TOKEN')
        exc.acquisition_reason_code = ['PRIVATE_TOKEN']
        exc.acquisition_http_status = 'PRIVATE_TOKEN'
        raise exc
    out = bounded.acquire({'quotes': (work, 1)})['quotes']
    assert out['error'] == 'RuntimeError'
    assert 'reason_code' not in out and 'http_status' not in out
    assert 'PRIVATE_TOKEN' not in json.dumps(out)


def test_complete_inputs_same_board_for_serial_and_default_cached_workers(monkeypatch, tmp_path):
    from dashboard import load_config
    from intraday_history import session_schedule
    from test_training_history import NOW, ET
    import bar_cache
    cfg = load_config('config.yaml')
    dates = session_schedule('2026-07-20', '2026-09-10').index[-30:]
    rng = np.random.default_rng(100)
    frames = {}
    for number, ticker in enumerate(cfg['scan']['universe']):
        days = []
        price = 100. + number
        for date in [*dates, pd.Timestamp(NOW.date())]:
            price *= 1 + rng.normal(0, .002)
            c = price * (1 + np.cumsum(rng.normal(0, .0005, 78)))
            ix = pd.date_range(str(date.date())+' 09:30', periods=78, freq='5min', tz=ET)
            days.append(pd.DataFrame(dict(Open=c, High=c*1.001, Low=c*.999,
                                           Close=c, Volume=rng.integers(500, 1500, 78)), index=ix))
            price = c[-1]
        days[-1] = days[-1].iloc[:4]
        frames[ticker] = pd.concat(days)
    class Clock(dt.datetime):
        @classmethod
        def now(cls, tz=None): return NOW.astimezone(tz)
    monkeypatch.setattr(r945.dt, 'datetime', Clock)
    monkeypatch.setenv('RB_INTRADAY_CACHE_DIR', str(tmp_path))
    monkeypatch.setattr(bar_cache, 'get_bars', lambda adapter, ticker, now, **kw: frames[ticker].copy())
    serial = r945.run(cfg, workers=1)
    concurrent = r945.run(cfg)
    assert serial['n_names'] >= 17 and serial.get('pair')
    assert json.dumps(serial, sort_keys=True) == json.dumps(concurrent, sort_keys=True)
