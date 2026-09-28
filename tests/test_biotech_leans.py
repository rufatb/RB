"""Part 2's calls: one forced LONG/SHORT per reviewed event, sealed, recorded, scored."""
import datetime as dt
import json
import types
from zoneinfo import ZoneInfo

import pandas as pd
import pytest

import biotech_leans as B

ET = ZoneInfo('America/New_York')
NOW = dt.datetime(2026, 9, 28, 9, 40, tzinfo=ET)


def event(ticker='ABC', **over):
    return {'event_id': ticker + '-TOPLINE', 'ticker': ticker, 'kind': 'topline',
            'window_start': '2026-10-01', 'window_end': '2026-12-31', 'asset': 'ABC-1',
            'indication': 'X', 'stage': 'Phase 2', 'known_data': 'none', 'new_information': 'soon',
            **over}


def security(ticker='ABC', n=60, start=10.0):
    bars = [{'date': (dt.date(2026, 6, 1) + dt.timedelta(days=i)).isoformat(),
             'adjusted_close': start + i*0.1, 'volume': 1000.0} for i in range(n)]
    return {'ticker': ticker, 'daily_bars': bars, 'market_cap': 5e8, 'short_float': 0.2}


class Client:
    def __init__(self, reply, finish='stop'):
        self.reply, self.finish, self.sent = reply, finish, []
        self.chat = types.SimpleNamespace(completions=self)

    def create(self, **kw):
        self.sent.append(kw)
        msg = types.SimpleNamespace(content=json.dumps(self.reply))
        return types.SimpleNamespace(model='deepseek-flash', choices=[
            types.SimpleNamespace(finish_reason=self.finish, message=msg)])


def test_price_context_is_computed_from_completed_bars():
    ctx = B.price_context(security())
    assert ctx['last_close'] == pytest.approx(15.9) and ctx['range_6mo_pos'] == 1.0
    assert ctx['ret_20d_pct'] > 0 and ctx['short_float'] == 0.2
    assert B.price_context(security(n=10)) is None


def test_a_name_without_certified_history_gets_no_call_and_says_why():
    rows, gaps = B.build_request([event('ABC'), event('ZZZ')], [security('ABC')])
    assert [r['ticker'] for r in rows] == ['ABC'] and 'ZZZ' in gaps[0]


@pytest.mark.parametrize('calls,why', [
    ([], 'not every event'),
    ([{'event_id': 'ABC-TOPLINE', 'side': 'NONE', 'confidence': .5, 'reason': 'x'}], 'side'),
    ([{'event_id': 'ABC-TOPLINE', 'side': 'LONG', 'confidence': 1.5, 'reason': 'x'}], 'confidence'),
    ([{'event_id': 'OTHER', 'side': 'LONG', 'confidence': .5, 'reason': 'x'}], 'not supplied'),
    ([{'event_id': 'ABC-TOPLINE', 'side': 'LONG', 'confidence': .5, 'reason': 'x'}] * 2, 'twice'),
])
def test_every_event_is_called_exactly_once_with_a_side_or_the_reply_is_refused(calls, why):
    rows, _ = B.build_request([event()], [security()])
    with pytest.raises(ValueError, match=why):
        B.parse({'calls': calls}, rows)


def test_stage_seals_records_and_reads_back(tmp_path, monkeypatch):
    monkeypatch.setattr(B, 'load_inputs', lambda now, e, s: ([event()], [security()]))
    client = Client({'calls': [{'event_id': 'ABC-TOPLINE', 'side': 'SHORT', 'confidence': .56,
                                'reason': 'Run-up into a binary readout.'}]})
    calls = tmp_path/'calls.csv'
    snap = B.stage(tmp_path, now=NOW, client=client, calls_path=calls)
    assert snap['status'] == 'READY' and snap['calls'][0]['side'] == 'SHORT'
    assert client.sent[0]['extra_body'] == {'thinking': {'type': 'disabled'}}
    back = B.load_prepared(tmp_path, NOW)
    assert back['calls'][0]['reason'] == 'Run-up into a binary readout.'
    assert [r['side'] for r in B.read(calls)] == ['SHORT']
    # A second stage the same day cannot rewrite the recorded call.
    B.stage(tmp_path, now=NOW, client=Client({'calls': [{'event_id': 'ABC-TOPLINE',
            'side': 'LONG', 'confidence': .6, 'reason': 'x'}]}), calls_path=calls)
    assert [r['side'] for r in B.read(calls)] == ['SHORT']


def test_an_edited_snapshot_or_another_day_is_refused(tmp_path, monkeypatch):
    monkeypatch.setattr(B, 'load_inputs', lambda now, e, s: ([event()], [security()]))
    B.stage(tmp_path, now=NOW, record=False, client=Client({'calls': [
        {'event_id': 'ABC-TOPLINE', 'side': 'LONG', 'confidence': .5, 'reason': 'x'}]}))
    assert B.load_prepared(tmp_path, NOW + dt.timedelta(days=1))['status'] == 'UNAVAILABLE'
    path = tmp_path/B.SNAPSHOT_NAME
    obj = json.loads(path.read_text())
    obj['calls'][0]['side'] = 'SHORT'
    path.write_text(json.dumps(obj))
    assert B.load_prepared(tmp_path, NOW)['status'] == 'UNAVAILABLE'


def test_a_provider_failure_is_unavailable_never_a_crash(tmp_path, monkeypatch):
    monkeypatch.setattr(B, 'load_inputs', lambda now, e, s: ([event()], [security()]))
    snap = B.stage(tmp_path, now=NOW, record=False, client=Client({'calls': []}, finish='length'))
    assert snap['status'] == 'UNAVAILABLE' and 'ValueError' in snap['reason']


def test_scoring_runs_from_the_call_day_close_to_the_first_close_after_the_window(tmp_path):
    calls = tmp_path/'calls.csv'
    B.append([{'session': '2026-09-28', 'model': 'm', 'event_id': 'E1', 'ticker': 'ABC',
               'side': 'SHORT', 'confidence': .55, 'kind': 'PDUFA', 'window_end': '2026-10-30'},
              {'session': '2026-09-29', 'model': 'm', 'event_id': 'E1', 'ticker': 'ABC',
               'side': 'LONG', 'confidence': .55, 'kind': 'PDUFA', 'window_end': '2026-10-30'}],
             calls)
    idx = pd.to_datetime(['2026-09-28', '2026-09-29', '2026-10-30', '2026-11-02']).tz_localize(ET)
    bars = pd.DataFrame({'Close': [10.0, 10.0, 12.0, 8.0]}, index=idx)
    early = dt.datetime(2026, 10, 30, 17, tzinfo=ET)
    assert B.score(calls, now=early, bars_for=lambda t: bars) == 0      # window not over
    assert B.score(calls, now=early + dt.timedelta(days=4), bars_for=lambda t: bars) == 2
    rows = {r['session']: r for r in B.read(calls)}
    assert rows['2026-09-28']['exit'] == '8.0' and rows['2026-09-28']['hit'] == '1'  # short, -20%
    card = B.scorecard(B.read(calls))
    # The event counts ONCE, by its first call (the SHORT), not twice.
    assert card == {'events': 1, 'scored': 1, 'hits': 1, 'mean_r_pct': 20.0}


def test_the_table_prints_every_event_and_a_missing_call_says_why():
    cal = [event('ABC'), event('XYZ')]
    leans = {'status': 'READY', 'calls': [{'ticker': 'ABC', 'window_end': '2026-12-31',
             'kind': 'topline', 'side': 'LONG', 'confidence': .52, 'reason': 'a | b'}]}
    text = '\n'.join(B.table_lines(leans, cal))
    assert '| ABC | topline — ABC-1 | 2026-10-01 → 2026-12-31 | LONG | 0.52 | a / b |' in text
    assert '| XYZ |' in text and 'no call' in text and 'not forecasts' in text
