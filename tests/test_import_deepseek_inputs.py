"""Private model inputs cannot replace or corrupt published operational history."""
import json
import os
from pathlib import Path
import sqlite3
import stat
import zipfile

import pytest

import import_deepseek_inputs as I
from report_store import Store


TOKEN = 'sk-unit-test-private-value'
CHECKED = '2026-09-12T12:00:00+00:00'


@pytest.fixture
def state(tmp_path):
    directory = tmp_path / 'state'
    store = Store(directory)
    store.publish('2026-09-11', {'session': '2026-09-11', 'immutable': True})
    store.claim_delivery('2026-09-11', 'actual-gmail-id')
    store.finish_delivery('2026-09-11', 'unknown', 'Reconcile Sent before retry')
    with store.connect() as conn:
        conn.execute('CREATE TABLE replacements (body TEXT, message_id TEXT, state TEXT)')
        conn.execute('INSERT INTO replacements VALUES (?,?,?)',
                     ('immutable replacement', 'actual-replacement-id', 'sent'))
        conn.execute('INSERT INTO outcomes VALUES (?,?,?,?)',
                     ('2026-09-11', 'TRP.TO', '15:59', '{"verified": false}'))
    (directory / 'runtime_deltas.json').write_text('{"preserve": true}')
    return directory


def archive(tmp_path, rows):
    target = tmp_path / 'overlay.zip'
    with zipfile.ZipFile(target, 'w') as bundle:
        for name, content in rows:
            bundle.writestr(name, content if isinstance(content, (str, bytes)) else json.dumps(content))
    return target


def diagnostic(checked=CHECKED, status='READY'):
    return {'checked_at': checked, 'status': status,
            'provider_endpoint': 'https://api.deepseek.com/models',
            'model': 'deepseek-chat'}


def test_overlay_preserves_all_sqlite_history_and_stages_private_inputs(tmp_path, state):
    before = (state / 'reports.sqlite3').read_bytes()
    zip_path = archive(tmp_path, [
        ('secrets/', ''), ('secrets/deepseek_api_key', TOKEN),
        ('deepseek_model.txt', 'deepseek-chat'),
        ('deepseek_capability.json', diagnostic()),
        ('deepseek_schema_probe.json', diagnostic()),
    ])
    result = I.merge(zip_path, state)
    assert len(result['actions']) == 4
    assert (state / 'reports.sqlite3').read_bytes() == before
    assert Store(state).delivery('2026-09-11')['state'] == 'unknown'
    assert (state / 'runtime_deltas.json').read_text() == '{"preserve": true}'
    assert (state / 'secrets/deepseek_api_key').read_text().strip() == TOKEN
    assert stat.S_IMODE((state / 'secrets/deepseek_api_key').stat().st_mode) == 0o600
    assert TOKEN not in json.dumps(result)


@pytest.mark.parametrize('file,value,reason', [
    ('secrets/deepseek_api_key', 'sk-different-private-value', 'EXISTING_PRIVATE_CREDENTIAL_CONFLICT'),
    ('deepseek_model.txt', 'deepseek-reasoner', 'EXISTING_PRIVATE_MODEL_CONFLICT'),
])
def test_late_conflict_prevents_all_writes(tmp_path, state, file, value, reason):
    path = state / file
    path.parent.mkdir(exist_ok=True)
    existing = TOKEN if file.startswith('secrets') else 'deepseek-chat'
    path.write_text(existing)
    zip_path = archive(tmp_path, [('deepseek_capability.json', diagnostic()), (file, value)])
    with pytest.raises(I.DataGap, match=reason) as error:
        I.merge(zip_path, state)
    assert path.read_text() == existing
    assert not (state / 'deepseek_capability.json').exists()
    assert value not in str(error.value)
    assert existing not in str(error.value)


@pytest.mark.parametrize('name', [
    'reports.sqlite3', '../outside', '/absolute', './deepseek_model.txt',
    'secrets//deepseek_api_key', 'secrets/../deepseek_model.txt',
    'secrets\\deepseek_api_key', 'C:/private', 'unrelated.json',
])
def test_unknown_and_noncanonical_paths_reject_archive_before_any_write(tmp_path, state, name):
    before = (state / 'reports.sqlite3').read_bytes()
    zip_path = archive(tmp_path, [('deepseek_model.txt', 'deepseek-chat'), (name, 'bad')])
    with pytest.raises(I.DataGap):
        I.merge(zip_path, state)
    assert not (state / 'deepseek_model.txt').exists()
    assert (state / 'reports.sqlite3').read_bytes() == before


def test_duplicate_archive_member_and_symlink_rejected(tmp_path, state):
    with pytest.warns(UserWarning):
        zip_path = archive(tmp_path, [('deepseek_model.txt', 'deepseek-chat'),
                                      ('deepseek_model.txt', 'deepseek-chat')])
    with pytest.raises(I.DataGap, match='DUPLICATE'):
        I.merge(zip_path, state)
    info = zipfile.ZipInfo('secrets/deepseek_api_key')
    info.create_system = 3
    info.external_attr = (stat.S_IFLNK | 0o777) << 16
    zip_path = archive(tmp_path, [(info, '/outside')])
    with pytest.raises(I.DataGap, match='SYMLINK'):
        I.merge(zip_path, state)
    assert not (state / 'deepseek_model.txt').exists()


def test_destination_symlink_rejected_without_changing_target(tmp_path, state):
    outside = tmp_path / 'outside'
    outside.mkdir()
    (outside / 'deepseek_api_key').write_text(TOKEN)
    (state / 'secrets').symlink_to(outside, target_is_directory=True)
    zip_path = archive(tmp_path, [('secrets/deepseek_api_key', TOKEN)])
    with pytest.raises(I.DataGap, match='DESTINATION_SYMLINK'):
        I.merge(zip_path, state)
    assert (outside / 'deepseek_api_key').read_text() == TOKEN


def test_missing_blank_wrong_schema_and_corrupt_database_never_initialized(tmp_path):
    zip_path = archive(tmp_path, [('deepseek_model.txt', 'deepseek-chat')])
    state = tmp_path / 'state'
    state.mkdir()
    with pytest.raises(I.DataGap, match='EXISTING_PUBLICATION_STATE_REQUIRED'):
        I.merge(zip_path, state)
    db = state / 'reports.sqlite3'
    assert not db.exists()
    db.write_bytes(b'')
    with pytest.raises(I.DataGap, match='EXISTING_PUBLICATION_STATE_REQUIRED'):
        I.merge(zip_path, state)
    assert db.read_bytes() == b''
    with sqlite3.connect(db) as conn:
        conn.execute('CREATE TABLE unrelated (x)')
    with pytest.raises(I.DataGap, match='EXISTING_PUBLICATION_SCHEMA_REQUIRED'):
        I.merge(zip_path, state)
    db.write_bytes(b'not sqlite' * 100)
    with pytest.raises(I.DataGap, match='INTEGRITY_FAILURE'):
        I.merge(zip_path, state)
    assert not (state / 'deepseek_model.txt').exists()


def test_invalid_publication_hash_rejected(tmp_path, state):
    with sqlite3.connect(state / 'reports.sqlite3') as conn:
        conn.execute("UPDATE reports SET body='tampered'")
    zip_path = archive(tmp_path, [('deepseek_model.txt', 'deepseek-chat')])
    with pytest.raises(I.DataGap, match='CONTENT_INTEGRITY_FAILURE'):
        I.merge(zip_path, state)
    assert not (state / 'deepseek_model.txt').exists()


@pytest.mark.parametrize('file', ['deepseek_capability.json', 'deepseek_schema_probe.json'])
def test_newer_diagnostic_is_preserved_equal_identical_skipped_and_equal_conflict_refused(tmp_path, state, file):
    path = state / file
    current = diagnostic()
    path.write_text(json.dumps(current))
    older = diagnostic('2026-09-12T11:00:00Z', 'UNAVAILABLE')
    result = I.merge(archive(tmp_path, [(file, older)]), state)
    assert result['actions'][0]['action'] == 'SKIPPED_NEWER_EXISTS'
    assert json.loads(path.read_text()) == current
    result = I.merge(archive(tmp_path, [(file, current)]), state)
    assert result['actions'][0]['action'] == 'SKIPPED_IDENTICAL'
    with pytest.raises(I.DataGap, match='EQUAL_TIME_DIAGNOSTIC_CONFLICT'):
        I.merge(archive(tmp_path, [(file, diagnostic(status='DIFFERENT'))]), state)
    assert json.loads(path.read_text()) == current
    newer = diagnostic('2026-09-12T13:00:00+00:00', 'UNAVAILABLE')
    I.merge(archive(tmp_path, [(file, newer)]), state)
    assert json.loads(path.read_text()) == newer


@pytest.mark.parametrize('payload', [
    {'checked_at': '2026-09-12T12:00:00'},
    {'checked_at': CHECKED, 'api_key': TOKEN},
    {'checked_at': CHECKED, 'detail': 'Bearer opaque-private-value'},
    {'checked_at': CHECKED, 'detail': TOKEN},
    {'checked_at': CHECKED, 'detail': 'https://api.deepseek.com/models?api_key=private'},
    {'checked_at': CHECKED, 'detail': 'https://user:private@api.deepseek.com/models'},
    '{"checked_at":"2026-09-12T12:00:00Z","checked_at":"2026-09-12T13:00:00Z"}',
    '{"checked_at":"2026-09-12T12:00:00Z","score":NaN}',
    '{"checked_at":"2026-09-12T12:00:00Z","score":1e999}',
])
def test_diagnostics_must_be_aware_and_credential_free(tmp_path, state, payload):
    zip_path = archive(tmp_path, [('deepseek_capability.json', payload)])
    with pytest.raises(I.DataGap) as error:
        I.merge(zip_path, state)
    assert TOKEN not in str(error.value)
    assert not (state / 'deepseek_capability.json').exists()


@pytest.mark.parametrize('model', ['https://elsewhere.example', '../model', 'sk-not-a-model', 'a b', 'x'*101, ''])
def test_private_model_is_a_model_identifier_only(tmp_path, state, model):
    with pytest.raises(I.DataGap, match='INVALID_PRIVATE_MODEL'):
        I.merge(archive(tmp_path, [('deepseek_model.txt', model)]), state)


def test_size_limit_rejects_compressed_large_member(tmp_path, state):
    zip_path = tmp_path / 'overlay.zip'
    with zipfile.ZipFile(zip_path, 'w', compression=zipfile.ZIP_DEFLATED) as bundle:
        bundle.writestr('deepseek_capability.json', b' ' * (I.MAX_MEMBER_BYTES + 1))
    with pytest.raises(I.DataGap, match='SIZE_LIMIT'):
        I.merge(zip_path, state)


def test_equal_key_is_secured_without_mutating_hardlink(tmp_path, state):
    private = state / 'secrets'
    private.mkdir()
    key = private / 'deepseek_api_key'
    key.write_text(TOKEN)
    key.chmod(0o644)
    other = tmp_path / 'hardlink'
    os.link(key, other)
    I.merge(archive(tmp_path, [('secrets/deepseek_api_key', TOKEN)]), state)
    assert stat.S_IMODE(key.stat().st_mode) == 0o600
    assert stat.S_IMODE(other.stat().st_mode) == 0o644
    assert other.read_text() == TOKEN
