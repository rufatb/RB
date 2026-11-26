"""Part 6 travels in the first report export, before the later CSV push."""
import datetime as dt
import json

import pytest

import dda_desk as desk
from dda_protocol import ET


NOW = dt.datetime(2026, 11, 18, 9, 46, 1, tzinfo=ET)


def report(tmp_path, **news_changes):
    row = {'session': '2026-11-18', 'ticker': 'CNL.TO', 'side': 'LONG', 'arm': 'full',
           'material': True, 'confidence': .75, 'first_at': '2026-11-18T06:30:00-05:00',
           'reason': 'Published release rationale.', 'url': 'https://issuer.test/release',
           'title': 'Issuer release', 'model': 'recorded-model', 'prompt_version': 'recorded-rule',
           'private_key': 'excluded-private-input', 'w945_raw': 99., 'scored_at': NOW.isoformat()}
    news = {'status': 'READY', 'calls': [row], 'headline': {'CNL.TO': 'SHORT'},
            'private_context': 'excluded-private-input', **news_changes}
    data = {'session': '2026-11-18', 'generated_at': NOW.replace(second=0).isoformat(),
            'intraday': {'top_two': {'picks': []}, 'news_desk': news}}
    source = tmp_path / 'state/latest/report.json'
    source.parent.mkdir(parents=True)
    source.write_text(json.dumps(data), encoding='utf-8')
    return source, data


def test_first_report_sidecar_contains_the_same_news_calls_without_private_or_outcome_fields(tmp_path, monkeypatch):
    monkeypatch.setattr(desk, 'ROOT', tmp_path)
    source, original = report(tmp_path)
    before = source.read_bytes()
    path = desk.bridge(tmp_path / 'state', 'report', NOW)
    exported = json.loads(path.read_text(encoding='utf-8'))['report']
    news = exported['intraday']['news_desk']
    assert news['status'] == 'READY' and news['calls'][0]['ticker'] == 'CNL.TO'
    assert news['calls'][0]['reason'] == original['intraday']['news_desk']['calls'][0]['reason']
    assert exported['generated_at'] == original['generated_at']
    assert not {'headline', 'private_context', 'w945_raw', 'scored_at', 'private_key'} & set(news)
    encoded = json.dumps(exported)
    assert 'excluded-private-input' not in encoded and 'w945_raw' not in encoded and 'scored_at' not in encoded
    assert source.read_bytes() == before


def test_report_export_cannot_be_backfilled_before_0946(tmp_path, monkeypatch):
    monkeypatch.setattr(desk, 'ROOT', tmp_path)
    report(tmp_path)
    with pytest.raises(ValueError, match='DDA_REPORT_CLOCK_REQUIRED'):
        desk.bridge(tmp_path / 'state', 'report', NOW.replace(minute=45))
    assert not (tmp_path / 'data').exists()


def test_news_export_retains_first_publication_on_retry(tmp_path, monkeypatch):
    monkeypatch.setattr(desk, 'ROOT', tmp_path)
    source, data = report(tmp_path)
    path = desk.bridge(tmp_path / 'state', 'report', NOW)
    before = path.read_bytes()
    data['intraday']['news_desk']['calls'][0]['side'] = 'SHORT'
    source.write_text(json.dumps(data), encoding='utf-8')
    desk.bridge(tmp_path / 'state', 'report', NOW + dt.timedelta(seconds=5))
    assert path.read_bytes() == before


def test_export_does_not_smuggle_another_session_or_news_arm_into_part_six(tmp_path, monkeypatch):
    monkeypatch.setattr(desk, 'ROOT', tmp_path)
    source, data = report(tmp_path)
    row = data['intraday']['news_desk']['calls'][0]
    data['intraday']['news_desk']['calls'] += [None, {**row, 'arm': 'headline'}, {**row, 'session': '2026-11-17'}]
    source.write_text(json.dumps(data), encoding='utf-8')
    exported = json.loads(desk.bridge(tmp_path / 'state', 'report', NOW).read_text(encoding='utf-8'))
    assert len(exported['report']['intraday']['news_desk']['calls']) == 1


def test_malformed_optional_news_does_not_prevent_top_two_publication(tmp_path, monkeypatch):
    monkeypatch.setattr(desk, 'ROOT', tmp_path)
    report(tmp_path, calls=True)
    data = json.loads(desk.bridge(tmp_path / 'state', 'report', NOW).read_text(encoding='utf-8'))
    assert 'top_two' in data['report']['intraday']
    assert data['report']['intraday']['news_desk']['status'] == 'UNAVAILABLE'


def test_a_blind_news_desk_reaches_the_platform_as_blind(tmp_path, monkeypatch):
    """Day-156: 11-26's export said READY over a wire nobody had read."""
    monkeypatch.setattr(desk, 'ROOT', tmp_path)
    report(tmp_path, status='BLIND', calls=[], wire={'releases_in_window': 0})
    data = json.loads(desk.bridge(tmp_path / 'state', 'report', NOW).read_text(encoding='utf-8'))
    assert data['report']['intraday']['news_desk']['status'] == 'BLIND'
    assert data['report']['intraday']['news_desk']['calls'] == []
