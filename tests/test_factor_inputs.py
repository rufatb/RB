import copy
import datetime as dt
import json
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
import pytest

import factor_inputs as F
from bar_cache import key
from intraday_history import session_schedule
from metrics import macd, rsi

ET = ZoneInfo('America/New_York')
NOW = dt.datetime(2026, 9, 11, 8, 30, tzinfo=ET)
SOURCE = 'https://query1.finance.yahoo.com/v8/finance/chart/ABC.TO?interval=5m&range=60d'
CFG = {'scan': {'universe': ['ABC.TO']}, 'exchange_tz': str(ET),
       'data_sources': {'primary': 'yahoo_direct'}}


def payload():
    return {'as_of': NOW.isoformat(), 'candidates': [{
        'ticker': 'ABC.TO', 'technical_source': 'python',
        'technical_provenance': {'input_sha256': 'a'*64, 'computation': 'upstream.indicators.v1',
            'computed_at': NOW.isoformat(), 'source_url': SOURCE},
        'technicals': {'vwap': 100., 'rsi': 50., 'macd': .1, 'macd_signal': .05,
                       'macd_hist': .05, 'orb_high': 101., 'orb_low': 99., 'rvol': 1.1},
        'technicals_scope': 'previous_completed_session',
        'technicals_as_of': '2026-09-10T16:00:00-04:00', 'source_url': SOURCE,
        'headlines': [{'title': 'Issuer publishes operating update',
            'source_url': 'https://issuer.example/news/update', 'published_at': NOW.isoformat()}],
        'catalyst_tags': []}], 'macro': {name: {'value': 10., 'as_of': NOW.isoformat(),
        'source_url': 'https://provider.example/data/'+name} for name in F.policy.MACRO_KEYS}}


def test_strict_supplied_pool_and_provenance():
    result = F.validate_payload(payload(), NOW)
    assert result['coverage']['complete_tickers'] == ['ABC.TO']
    assert result['candidate_gaps'] == {'ABC.TO': []}
    assert result['candidates'][0]['technical_provenance']['computation'] == 'upstream.indicators.v1'
    p = payload(); p['candidates'][0].pop('technical_source')
    assert 'PYTHON_TECHNICAL_DECLARATION_REQUIRED' in F.validate_payload(p, NOW)['candidate_gaps']['ABC.TO']


@pytest.mark.parametrize('mutate', ['naive', 'future', 'stale', 'wrong_prior_close', 'missing_provenance'])
def test_invalid_technical_timing_does_not_erase_news(mutate):
    p = payload(); c = p['candidates'][0]
    if mutate == 'naive': c['technicals_as_of'] = '2026-09-10T16:00:00'
    elif mutate == 'future': c['technicals_as_of'] = '2026-09-11T16:00:00-04:00'
    elif mutate == 'stale': c['technicals_as_of'] = '2026-09-09T16:00:00-04:00'
    elif mutate == 'wrong_prior_close': c['technicals_as_of'] = '2026-09-10T15:55:00-04:00'
    else: c.pop('technical_provenance')
    result = F.validate_payload(p, NOW)
    assert not result['coverage']['complete']
    assert result['candidates'][0]['technicals'] == {}
    assert result['candidates'][0]['headlines']
    assert result['candidate_gaps']['ABC.TO']


@pytest.mark.parametrize('value', [float('nan'), float('inf'), True, '100'])
def test_nonfinite_and_string_technicals_never_pass(value):
    p = payload(); p['candidates'][0]['technicals']['vwap'] = value
    result = F.validate_payload(p, NOW)
    assert 'NONFINITE_OR_NONNUMERIC_TECHNICAL' in result['candidate_gaps']['ABC.TO']
    assert result['candidates'][0]['technicals'] == {}


@pytest.mark.parametrize('url', ['https://user:secret@issuer.example/data',
    'https://provider.example/data?api_token=secret', 'http://issuer.example/data',
    'https://127.0.0.1/data', 'https://192.168.0.1/data', 'https://issuer.local/data'])
def test_private_or_authenticated_urls_are_rejected_without_echo(url):
    p = payload(); p['candidates'][0]['source_url'] = url
    result = F.validate_payload(p, NOW)
    assert 'INVALID_PUBLIC_SOURCE_URL' in result['candidate_gaps']['ABC.TO']
    assert 'secret' not in json.dumps(result)


def test_malformed_timestamp_never_echoes_rejected_values():
    p = payload(); p['candidates'][0]['technicals_as_of'] = 'private-secret-value'
    result = F.validate_payload(p, NOW)
    assert 'private-secret-value' not in json.dumps(result)
    assert 'INVALID_TIMESTAMP' in result['candidate_gaps']['ABC.TO']


def test_duplicate_tickers_rejected_instead_of_first_wins():
    p = payload(); p['candidates'] *= 2
    result = F.validate_payload(p, NOW)
    assert not result['candidates']
    assert result['candidate_gaps']['ABC.TO'] == ['DUPLICATE_CANDIDATE']


def test_500_cap_is_a_cap_not_padding_or_silent_truncation():
    p = payload(); original = p['candidates'][0]
    p['candidates'] = [dict(original, ticker='X'+str(i)) for i in range(501)]
    assert F.validate_payload(p, NOW)['gaps'] == ['CANDIDATE_LIMIT_EXCEEDED']
    p['candidates'] = p['candidates'][:500]
    assert F.validate_payload(p, NOW)['coverage']['accepted'] == 500


def test_missing_current_news_or_macro_is_explicit_and_independent():
    p = payload(); p['macro'].pop('vix'); p['candidates'][0]['headlines'][0]['published_at'] = '2026-09-01T08:00:00-04:00'
    result = F.validate_payload(p, NOW)
    assert result['candidates'][0]['technicals']['vwap'] == 100.
    assert result['candidates'][0]['headlines'] == []
    assert 'INCOMPLETE_MACRO' in result['candidate_gaps']['ABC.TO']
    assert 'NO_CURRENT_CATALYST_EVIDENCE' in result['candidate_gaps']['ABC.TO']
    assert result['gaps'] == ['VIX:MISSING_MACRO']


def test_all_evidence_cut_off_at_snapshot_not_validation_time():
    p = payload(); p['as_of'] = (NOW-dt.timedelta(minutes=5)).isoformat()
    result = F.validate_payload(p, NOW)
    assert 'HEADLINES:FUTURE_EVIDENCE' in result['candidate_gaps']['ABC.TO']
    assert 'WTI:FUTURE_MACRO' in result['gaps']
    assert not result['coverage']['complete']


def test_unknown_fields_and_private_account_fields_never_pass():
    p = payload(); p['account'] = {'secret': 'private'}
    p['candidates'][0]['holdings'] = [1, 2]
    p['candidates'][0]['technicals']['secret_field'] = 1
    result = F.validate_payload(p, NOW)
    assert 'account' not in result and 'holdings' not in result['candidates'][0]
    assert 'secret_field' not in result['candidates'][0]['technicals']
    assert 'UNKNOWN_TECHNICAL_FIELD' in result['candidate_gaps']['ABC.TO']


def day(date, i=0):
    ix = pd.date_range(date+' 09:30', periods=78, freq='5min', tz=ET)
    c = 100+np.sin(i/3)+np.linspace(0, .2, 78)
    return pd.DataFrame({'Open': c, 'High': c+.1, 'Low': c-.1, 'Close': c,
                         'Volume': np.arange(78)+100}, index=ix)


def history():
    schedule = session_schedule('2026-07-01', '2026-09-10')
    return pd.concat([day(str(date.date()), i) for i, date in enumerate(schedule.index)])


def save_cache(root, frame):
    folder = root/'intraday_cache'; folder.mkdir(exist_ok=True)
    (folder/'manifest.json').write_text(json.dumps({'session': NOW.date().isoformat(),
        'prepared_at': '2026-09-11T08:05:00-04:00', 'source': 'yahoo_direct',
        'tickers': ['ABC.TO'], 'complete': True}))
    encoded = {'columns': list(frame.columns), 'index': [i.isoformat() for i in frame.index],
               'data': frame.to_numpy().tolist()}
    (folder/key('ABC.TO')).write_text(json.dumps({'ticker': 'ABC.TO',
        'session': NOW.date().isoformat(), 'frame': json.dumps(encoded)}))
    p = payload()
    (root/'deepseek_news.json').write_text(json.dumps({'ABC.TO': {
        'headlines': p['candidates'][0]['headlines'], 'catalyst_tags': []}}))
    (root/'deepseek_macro.json').write_text(json.dumps(p['macro']))


def test_cache_technicals_are_deterministic_prior_session_with_true_15_min_orb(tmp_path):
    frame = history(); save_cache(tmp_path, frame)
    result = F.build_from_state(tmp_path, CFG, NOW)
    c = result['candidates'][0]; t = c['technicals']; latest = frame[frame.index.date == dt.date(2026, 9, 10)]
    assert result['coverage']['accepted'] == result['coverage']['complete'] == 1
    assert result['coverage']['pool_source'] == 'configured_cached_universe'
    assert result['coverage']['target_capacity'] == 500
    assert c['technicals_as_of'] == '2026-09-10T16:00:00-04:00'
    assert c['technicals_scope'].startswith('previous_completed_session')
    assert 'quant_probability' not in t
    assert t['orb_high'] == latest.iloc[:3]['High'].max()
    assert t['orb_high'] != latest.iloc[:15]['High'].max()
    expected_vwap = (((latest.High+latest.Low+latest.Close)/3)*latest.Volume).sum()/latest.Volume.sum()
    assert t['vwap'] == pytest.approx(expected_vwap)
    daily = frame.groupby(frame.index.date).Close.last()
    assert t['rsi'] == pytest.approx(rsi(daily))
    assert t['macd'] == pytest.approx(macd(daily)['macd'])
    assert F.build_from_state(tmp_path, CFG, NOW) == result


@pytest.mark.parametrize('corruption', ['one_minute_grid', 'missing_bar', 'naive_index', 'missing_field'])
def test_bad_cache_grid_never_produces_technical_values(tmp_path, corruption):
    frame = history()
    if corruption == 'one_minute_grid':
        prior = frame[frame.index.date < dt.date(2026, 9, 10)]
        bad = day('2026-09-10'); bad.index = pd.date_range('2026-09-10 09:30', periods=78, freq='min', tz=ET)
        frame = pd.concat([prior, bad])
    elif corruption == 'missing_bar': frame = frame.drop(frame.index[-20])
    elif corruption == 'naive_index': frame.index = frame.index.tz_localize(None)
    else: frame = frame.drop(columns=['High'])
    save_cache(tmp_path, frame)
    result = F.build_from_state(tmp_path, CFG, NOW)
    assert result['candidates'][0]['technicals'] == {}
    assert result['candidates'][0]['headlines']
    assert 'CACHE_TICKER_UNAVAILABLE_OR_INVALID' in result['candidate_gaps']['ABC.TO']


def test_future_and_current_cache_rows_cannot_change_indicators(tmp_path):
    frame = history(); save_cache(tmp_path, frame)
    expected = F.build_from_state(tmp_path, CFG, NOW)['candidates'][0]['technicals']
    save_cache(tmp_path, pd.concat([frame, day('2026-09-11', 99), day('2026-09-14', 99)]))
    result = F.build_from_state(tmp_path, CFG, NOW)
    assert result['candidates'][0]['technicals'] == expected
    assert 'CACHE_CURRENT_OR_FUTURE_BARS_IGNORED' in result['candidate_gaps']['ABC.TO']


def test_warmup_gaps_are_null_not_invented_indicators(tmp_path):
    save_cache(tmp_path, pd.concat([day('2026-09-09'), day('2026-09-10')]))
    result = F.build_from_state(tmp_path, CFG, NOW)
    assert result['candidates'][0]['technicals']['macd'] is None
    assert result['candidates'][0]['technicals']['rsi'] is None
    assert 'TECHNICAL_UNAVAILABLE:macd' in result['candidate_gaps']['ABC.TO']
    assert not result['coverage']['complete']


def test_staged_duplicate_json_keys_are_rejected_not_silently_overwritten(tmp_path):
    (tmp_path/'deepseek_candidates.json').write_text('{"as_of":"one","as_of":"two","candidates":[]}')
    result = F.build_from_state(tmp_path, CFG, NOW)
    assert result['gaps'] == ['STAGED_CANDIDATE_FILE_INVALID']


def test_missing_cache_and_news_preserve_actual_pool_without_inventing_names(tmp_path):
    result = F.build_from_state(tmp_path, CFG, NOW)
    assert [c['ticker'] for c in result['candidates']] == ['ABC.TO']
    assert result['coverage']['complete'] == 0
    assert 'CACHE_MANIFEST_UNAVAILABLE_OR_INVALID' in result['gaps']


def test_size_limit_precedes_json_parse(tmp_path, monkeypatch):
    monkeypatch.setattr(F.policy, 'MAX_INPUT_BYTES', 10)
    (tmp_path/'deepseek_candidates.json').write_text(json.dumps(payload()))
    assert F.build_from_state(tmp_path, CFG, NOW)['gaps'] == ['STAGED_CANDIDATE_FILE_INVALID']


@pytest.mark.parametrize(('observed', 'valid'), [
    ('2026-09-10T16:00:00-04:00', True),
    ('2026-09-10T15:59:59-04:00', False),
    ('2026-09-09T16:00:00-04:00', False),
    ('2026-09-11T08:11:00-04:00', False),
])
def test_preopen_macro_uses_completed_exchange_close_not_six_hour_age(observed, valid):
    now = NOW.replace(hour=8, minute=10)
    p = {'as_of': now.isoformat(), 'candidates': [], 'macro': {
        key: {'value': 10., 'as_of': observed, 'source_url': 'https://provider.example/reference'}
        for key in F.policy.MACRO_KEYS}}
    result = F.validate_payload(p, now)
    assert result['coverage']['macro_complete'] is valid
    assert bool(result['macro']) is valid
    assert 'Dated references' in result['coverage']['macro_scope']
    if valid:
        assert not result['gaps']
    else:
        reason = 'FUTURE_MACRO' if observed.endswith('08:11:00-04:00') else 'STALE_MACRO'
        assert reason in ' '.join(result['gaps'])


def test_macro_prior_exchange_close_handles_labour_day_without_accepting_older_session():
    now = dt.datetime(2026, 9, 8, 8, 10, tzinfo=ET)
    p = {'as_of': now.isoformat(), 'candidates': [], 'macro': {
        key: {'value': 10., 'as_of': '2026-09-04T16:00:00-04:00',
              'source_url': 'https://provider.example/reference'} for key in F.policy.MACRO_KEYS}}
    assert F.validate_payload(p, now)['coverage']['macro_complete']
    p['macro']['tsx']['as_of'] = '2026-09-03T16:00:00-04:00'
    result = F.validate_payload(p, now)
    assert not result['coverage']['macro_complete'] and 'TSX:STALE_MACRO' in result['gaps']


def test_dated_macro_does_not_relax_six_hour_snapshot_age():
    now = NOW.replace(hour=8, minute=10)
    p = {'as_of': (now-dt.timedelta(hours=7)).isoformat(), 'candidates': [], 'macro': {
        key: {'value': 10., 'as_of': '2026-09-10T16:00:00-04:00',
              'source_url': 'https://provider.example/reference'} for key in F.policy.MACRO_KEYS}}
    assert F.validate_payload(p, now)['gaps'] == ['STALE_SNAPSHOT']


def test_500_candidate_validation_resolves_calendar_once(monkeypatch):
    p = payload(); candidate = p['candidates'][0]
    p['candidates'] = [dict(candidate, ticker='X'+str(i)) for i in range(500)]
    original = F._previous_close
    calls = []
    def counted(now):
        calls.append(now)
        return original(now)
    monkeypatch.setattr(F, '_previous_close', counted)
    result = F.validate_payload(p, NOW)
    assert result['coverage']['complete'] == 500
    assert len(calls) == 1


def test_missing_calendar_is_a_controlled_gap_not_an_exception(monkeypatch):
    def unavailable(now):
        raise RuntimeError('private environment details')
    monkeypatch.setattr(F, '_previous_close', unavailable)
    result = F.validate_payload(payload(), NOW)
    assert 'PRIOR_EXCHANGE_SESSION_UNAVAILABLE' in result['gaps']
    assert not result['coverage']['complete']
    assert result['candidates'][0]['headlines']
    assert 'private environment details' not in json.dumps(result)
