"""The scheduled run's record must reach the repository (2026-09-22: it never had)."""
import json
import shutil
from pathlib import Path

import pytest

import record_import

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def repo(tmp_path):
    for name in ('ledger.csv', 'universe_prints.csv'):
        shutil.copy(ROOT / name, tmp_path / name)
    (tmp_path / 'data').mkdir()
    return tmp_path


def published(tmp_path, repo, ledger_extra='', prints_extra=''):
    src = tmp_path / 'record'
    src.mkdir()
    (src / 'ledger.csv').write_text((repo / 'ledger.csv').read_text() + ledger_extra)
    (src / 'universe_prints.csv').write_text((repo / 'universe_prints.csv').read_text() + prints_extra)
    return src


def test_new_rows_are_appended_and_old_rows_untouched(tmp_path, repo):
    before = (repo / 'ledger.csv').read_text()
    src = published(tmp_path, repo, '2026-09-22,BCE.TO,LONG,0.570,sparse,30.8600,pair,long,,,,,\n',
                    '2026-09-22,BCE.TO,30.8600\n')
    added = record_import.import_dir(src, root=repo)
    assert added['ledger.csv'] == 1 and added['universe_prints.csv'] == 1
    after = (repo / 'ledger.csv').read_text()
    assert after.startswith(before.rstrip('\n')) and '2026-09-22,BCE.TO' in after


def test_importing_twice_adds_nothing(tmp_path, repo):
    src = published(tmp_path, repo, '2026-09-22,BCE.TO,LONG,0.570,sparse,30.8600,pair,long,,,,,\n')
    record_import.import_dir(src, root=repo)
    assert record_import.import_dir(src, root=repo)['ledger.csv'] == 0


def test_a_conflicting_row_fails_the_whole_import_and_writes_nothing(tmp_path, repo):
    """An existing record is immutable. A published file that disagrees with it
    is a fault to surface, never a correction to apply."""
    ledger = (repo / 'ledger.csv').read_text().splitlines()
    first = ledger[1].split(',')
    first[3] = '0.999'                       # same key, different value
    src = tmp_path / 'record'
    src.mkdir()
    (src / 'ledger.csv').write_text('\n'.join([ledger[0], ','.join(first)]) + '\n')
    (src / 'universe_prints.csv').write_text((repo / 'universe_prints.csv').read_text()
                                             + '2026-09-22,NEW.TO,1.0\n')
    prints_before = (repo / 'universe_prints.csv').read_text()
    with pytest.raises(ValueError):
        record_import.import_dir(src, root=repo)
    assert (repo / 'universe_prints.csv').read_text() == prints_before


def test_model_picks_are_recorded_from_the_frozen_report(tmp_path, repo):
    src = published(tmp_path, repo)
    (src / 'report.json').write_text(json.dumps({'session': '2026-09-23', 'intraday': {
        'opportunities': {'status': 'READY', 'longs': [{'ticker': 'A.TO', 'confidence': 0.6}],
                          'shorts': []}}}))
    added = record_import.import_dir(src, root=repo)
    assert added['model_picks'] == 1 and added['session'] == '2026-09-23'
