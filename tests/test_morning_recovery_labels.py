"""Regression for the queued 2026-11-11 morning and premature recovery email."""
import datetime as dt
import json
from zoneinfo import ZoneInfo

import pytest

import council
import dda_desk
import late_picks

ET = ZoneInfo('America/New_York')


def test_no_positions_cannot_be_described_as_a_two_round_consensus():
    result = council.council_top_two({'status': 'NO_POSITIONS', 'session': '2026-11-11',
        'positions': [], 'errors': {'nominations': 'CLAUDE_BRIEF_NOT_TODAY'}}, previous={})
    assert result['picks'] == []
    assert 'no candidate positions' in result['reason']
    assert 'not a completed consensus' in result['reason']
    assert 'after two rounds' not in result['reason']


def test_opening_export_preserves_no_positions_status(tmp_path, monkeypatch):
    now = dt.datetime(2026, 11, 11, 9, 23, tzinfo=ET)
    monkeypatch.setattr(dda_desk, 'ROOT', tmp_path)
    monkeypatch.setattr(council, 'load', lambda *a: {'status': 'NO_POSITIONS', 'session': '2026-11-11',
        'finished_at': now.isoformat(), 'positions': [], 'errors': {'nominations': 'CLAUDE_BRIEF_NOT_TODAY'}})
    result = json.loads(dda_desk.bridge(tmp_path, 'opening', now).read_text())
    assert result['opening']['council_status'] == 'NO_POSITIONS'
    assert not result['opening']['section']['picks']


@pytest.mark.parametrize('hour,minute,asked,expected', [
    (9, 31, '09:29', 'BEFORE the open'), (9, 40, '09:31', 'AFTER the open'),
    (10, 12, '10:05', 'AFTER the open')])
def test_recovery_email_uses_real_clocks_and_does_not_claim_a_future_report_failed(tmp_path, monkeypatch, hour, minute, asked, expected):
    import deepseek_opportunities
    import jev_opportunities
    import gemini_opportunities
    now = dt.datetime(2026, 11, 11, hour, minute, tzinfo=ET)
    at = '2026-11-11T'+asked+':00-05:00'
    (tmp_path/late_picks.BRIEF_JSON).write_text(json.dumps({'session': '2026-11-11', 'prepared_at': at,
        'considered': 1, 'universe': ['AAA.TO'], 'evidence': {},
        'payload': {'candidates': [{'ticker': 'AAA.TO', 'last': 100, 'prev_low': 98, 'prev_high': 102}]}}))
    unavailable = lambda *a: {'status': 'UNAVAILABLE', 'reason': 'not staged', 'longs': [], 'shorts': []}
    for module in (deepseek_opportunities, jev_opportunities, gemini_opportunities):
        monkeypatch.setattr(module, 'load_diagnostic', unavailable)
    monkeypatch.setattr(late_picks, 'biotech_part', lambda *a: [])
    result = late_picks.compose(tmp_path, {'longs': [], 'shorts': []}, now=now)
    text = (tmp_path/'late'/'report.txt').read_text(encoding='utf-8')
    assert expected in text and asked in text
    assert 'session stopped' not in text and 'did not publish today' not in text
    if hour == 9 and minute < 46:
        assert result['subject'].startswith('RB Recovery Research — ')
        assert 'RB Daily Report — ' not in result['subject']
        assert 'full report window is 09:46' in text
    else:
        assert 'LATE PICKS' in result['subject']
