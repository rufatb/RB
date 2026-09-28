"""A failed publication still sends the sealed pre-open picks, in seconds."""
import datetime as dt
from zoneinfo import ZoneInfo

import model_picks
import picks_only as PO

NOW = dt.datetime(2026, 9, 28, 9, 49, tzinfo=ZoneInfo('America/New_York'))
SNAPS = {
    'claude': {'status': 'READY', 'longs': [{'ticker': 'QSR.TO', 'confidence': 0.52,
               'invalid_at': 100.78, 'reason': 'held vwap'}], 'shorts': []},
    'opportunities': {'status': 'UNAVAILABLE', 'reason': 'cut off (length)'},
    'jev': {'status': 'NO_OPPORTUNITY', 'longs': [], 'shorts': [],
            'long_ranked': [{'ticker': 'RANKED.TO', 'probability': 0.1}],
            'forced_short': {'ticker': 'AC.TO', 'probability': 0.25,
                             'gated_abstain_probability': 0.42, 'cleared_gated_abstain': False}},
}


def test_the_email_is_built_from_the_sealed_snapshots(tmp_path, monkeypatch):
    monkeypatch.setattr(PO, 'load', lambda root, now: SNAPS)
    monkeypatch.setattr('late_picks.biotech_part', lambda root, now: ['', '## Part 2', 'x'])
    out = PO.compose(tmp_path, now=NOW, reason='morning.sh exit 4')
    text = open(out['text_path']).read()
    assert out['subject'] == 'RB Daily Report — 2026-09-28 — PICKS ONLY (morning.sh exit 4)'
    assert '| LONG QSR.TO | 0.52 | below 100.78 | held vwap |' in text
    assert 'Unavailable — cut off (length)' in text
    assert '| SHORT AC.TO | 0.25 | 0.42 |' in text and 'RANKED.TO' not in text
    assert 'sealed BEFORE the open' in text and 'shares' not in text.lower()
    assert '<table' in open(out['html_path']).read() and out['has_picks']


def test_the_picks_are_recorded_as_the_report_would_have(tmp_path):
    ledger = tmp_path/'picks.csv'
    PO.record(SNAPS, '2026-09-28', ledger)
    rows = {(r['model'], r['kind'], r['ticker']) for r in model_picks.read(ledger)}
    assert rows == {('claude', 'selected', 'QSR.TO'), ('jev', 'forced', 'AC.TO')}
    assert {r['source'] for r in model_picks.read(ledger)} == {'picks_only'}


def test_nothing_staged_exits_two_so_the_caller_runs_late_picks(tmp_path, monkeypatch):
    down = {'status': 'UNAVAILABLE', 'reason': 'not staged'}
    monkeypatch.setattr(PO, 'load', lambda root, now: {'claude': down, 'opportunities': down, 'jev': down})
    monkeypatch.setattr('late_picks.biotech_part', lambda root, now: [])
    assert PO.main(['--state-dir', str(tmp_path), '--no-record']) == 2
