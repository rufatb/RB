#!/usr/bin/env python3
"""Import private DeepSeek inputs without replacing publication or delivery state.

Every member and every conflict is checked before any destination is changed.
The four allowlisted inputs are then replaced individually and atomically; the
caller must still save the containing operational archive with its version guard.
No network requests, database creation, or report publication occurs here.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import math
import os
from pathlib import Path, PurePosixPath
import re
import sqlite3
import stat
import tempfile
from urllib.parse import parse_qsl, urlsplit
import zipfile


ALLOWED = frozenset({
    'secrets/deepseek_api_key', 'deepseek_model.txt',
    'deepseek_capability.json', 'deepseek_schema_probe.json',
})
MAX_MEMBER_BYTES = 1_000_000
MAX_ARCHIVE_BYTES = 4_000_000
CREDENTIAL_FIELDS = frozenset({
    'api_key', 'apikey', 'authorization', 'password', 'secret',
    'access_token', 'refresh_token', 'api_token', 'token',
})


class DataGap(ValueError):
    """Credential-free, bounded reason for a refused private overlay."""


def _unique(pairs):
    out = {}
    for key, value in pairs:
        if key in out:
            raise DataGap('DUPLICATE_DIAGNOSTIC_KEY')
        out[key] = value
    return out


def _invalid_constant(_):
    raise DataGap('NONFINITE_DIAGNOSTIC_VALUE')


def _json(content):
    try:
        value = json.loads(content, object_pairs_hook=_unique,
                           parse_constant=_invalid_constant)
    except (UnicodeError, json.JSONDecodeError, RecursionError) as exc:
        raise DataGap('INVALID_DIAGNOSTIC_JSON') from None
    if not isinstance(value, dict):
        raise DataGap('INVALID_DIAGNOSTIC_JSON')
    return value


def _aware(value):
    try:
        if not isinstance(value, str):
            raise ValueError
        observed = dt.datetime.fromisoformat(value.replace('Z', '+00:00'))
        if observed.tzinfo is None or observed.utcoffset() is None:
            raise ValueError
        return observed
    except (ValueError, OverflowError):
        raise DataGap('AWARE_DIAGNOSTIC_CHECKED_AT_REQUIRED') from None


def _credential_free(value, depth=0):
    if depth > 30:
        raise DataGap('DIAGNOSTIC_NESTING_LIMIT')
    if isinstance(value, dict):
        for key, item in value.items():
            if key.lower().replace('-', '_') in CREDENTIAL_FIELDS:
                raise DataGap('CREDENTIAL_IN_DIAGNOSTIC_REJECTED')
            _credential_free(item, depth + 1)
    elif isinstance(value, list):
        for item in value:
            _credential_free(item, depth + 1)
    elif isinstance(value, float) and not math.isfinite(value):
        raise DataGap('NONFINITE_DIAGNOSTIC_VALUE')
    elif isinstance(value, str):
        if re.search(r'\bsk-[A-Za-z0-9_-]+|\bbearer\s+\S+', value, re.I):
            raise DataGap('CREDENTIAL_IN_DIAGNOSTIC_REJECTED')
        # Reject authenticated URLs, including ones embedded in error prose.
        for text in re.findall(r'https?://[^\s<>"\']+', value):
            try:
                url = urlsplit(text)
                if url.username is not None or url.password is not None:
                    raise DataGap('AUTHENTICATED_DIAGNOSTIC_URL_REJECTED')
                if any(key.lower().replace('-', '_') in CREDENTIAL_FIELDS
                       for key, _ in parse_qsl(url.query, keep_blank_values=True)):
                    raise DataGap('AUTHENTICATED_DIAGNOSTIC_URL_REJECTED')
            except ValueError:
                raise DataGap('INVALID_DIAGNOSTIC_URL') from None


def _diagnostic(content):
    value = _json(content)
    observed = _aware(value.get('checked_at'))
    _credential_free(value)
    return value, observed


def _text(content, kind):
    try:
        value = content.decode('utf-8').strip()
    except UnicodeError:
        raise DataGap('INVALID_' + kind) from None
    if kind == 'PRIVATE_CREDENTIAL':
        if (not value or len(value) > 400 or not value.isascii()
                or any(char.isspace() or ord(char) < 33 or ord(char) == 127 for char in value)):
            raise DataGap('INVALID_PRIVATE_CREDENTIAL')
    elif (not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._:-]{0,99}', value)
          or value.startswith('sk-')):
        raise DataGap('INVALID_PRIVATE_MODEL')
    return value


def _no_symlinks(path):
    if any(part.is_symlink() for part in [path, *path.parents]):
        raise DataGap('DESTINATION_SYMLINK_REJECTED')


def _history(state):
    db = state / 'reports.sqlite3'
    _no_symlinks(db)
    if not db.is_file() or db.stat().st_size < 100:
        raise DataGap('EXISTING_PUBLICATION_STATE_REQUIRED')
    try:
        with sqlite3.connect(db.resolve().as_uri() + '?mode=ro', uri=True) as conn:
            if conn.execute('PRAGMA integrity_check').fetchall() != [('ok',)]:
                raise DataGap('PUBLICATION_STATE_INTEGRITY_FAILURE')
            tables = {row[0] for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'")}
            if not {'reports', 'deliveries'}.issubset(tables):
                raise DataGap('EXISTING_PUBLICATION_SCHEMA_REQUIRED')
            for body, digest in conn.execute('SELECT body,sha256 FROM reports'):
                if (not isinstance(body, str) or
                        hashlib.sha256(body.encode()).hexdigest() != digest):
                    raise DataGap('PUBLICATION_STATE_CONTENT_INTEGRITY_FAILURE')
    except sqlite3.Error:
        raise DataGap('PUBLICATION_STATE_INTEGRITY_FAILURE') from None


def merge(archive, state):
    """Validate a private input overlay completely, then atomically stage inputs."""
    state = Path(state).absolute()
    _history(state)
    pending, actions = [], []
    try:
        with zipfile.ZipFile(archive) as bundle:
            seen, total = set(), 0
            for item in bundle.infolist():
                name = item.filename
                path = PurePosixPath(name)
                is_directory = item.is_dir()
                raw_parts = name[:-1].split('/') if is_directory else name.split('/')
                if (item.orig_filename != name or path.is_absolute()
                        or any(part in {'', '.', '..'} for part in raw_parts)
                        or '\\' in name or ':' in name or '\x00' in name or name in seen
                        or path.as_posix() != name.rstrip('/')):
                    raise DataGap('UNSAFE_OR_DUPLICATE_OVERLAY_MEMBER')
                seen.add(name)
                mode = stat.S_IFMT(item.external_attr >> 16)
                if mode == stat.S_IFLNK:
                    raise DataGap('OVERLAY_SYMLINK_REJECTED')
                if mode not in (0, stat.S_IFREG, stat.S_IFDIR) or item.flag_bits & 1:
                    raise DataGap('UNSUPPORTED_OVERLAY_MEMBER')
                if is_directory:
                    if name != 'secrets/' or mode == stat.S_IFREG:
                        raise DataGap('UNEXPECTED_OVERLAY_DIRECTORY')
                    continue
                if name not in ALLOWED or mode == stat.S_IFDIR:
                    raise DataGap('UNEXPECTED_OVERLAY_FILE')
                total += item.file_size
                if item.file_size > MAX_MEMBER_BYTES or total > MAX_ARCHIVE_BYTES:
                    raise DataGap('OVERLAY_SIZE_LIMIT')
                destination = state / name
                _no_symlinks(destination)
                if destination.exists() and not destination.is_file():
                    raise DataGap('DESTINATION_NOT_REGULAR_FILE')
                if destination.exists() and destination.stat().st_size > MAX_MEMBER_BYTES:
                    raise DataGap('EXISTING_INPUT_SIZE_LIMIT')
                content = bundle.read(item)
                if len(content) != item.file_size:
                    raise DataGap('OVERLAY_MEMBER_SIZE_MISMATCH')
                if name in ('secrets/deepseek_api_key', 'deepseek_model.txt'):
                    kind = 'PRIVATE_CREDENTIAL' if name.startswith('secrets/') else 'PRIVATE_MODEL'
                    value = _text(content, kind)
                    if destination.exists():
                        existing = _text(destination.read_bytes(), kind)
                        if existing != value:
                            raise DataGap('EXISTING_' + kind + '_CONFLICT')
                        if kind == 'PRIVATE_MODEL':
                            actions.append({'file': name, 'action': 'SKIPPED_IDENTICAL'})
                            continue
                    # Atomic replacement also ensures the key cannot retain broad
                    # permissions or mutate another file through a hard link.
                    content = (value + '\n').encode()
                else:
                    data, checked = _diagnostic(content)
                    if destination.exists():
                        previous, previous_checked = _diagnostic(destination.read_bytes())
                        if previous_checked > checked:
                            actions.append({'file': name, 'action': 'SKIPPED_NEWER_EXISTS'})
                            continue
                        if previous_checked == checked:
                            if previous != data:
                                raise DataGap('EQUAL_TIME_DIAGNOSTIC_CONFLICT')
                            actions.append({'file': name, 'action': 'SKIPPED_IDENTICAL'})
                            continue
                pending.append((destination, content))
    except (zipfile.BadZipFile, zipfile.LargeZipFile, RuntimeError, NotImplementedError):
        raise DataGap('INVALID_PRIVATE_OVERLAY_ARCHIVE') from None

    # No destination creation occurs until validation of the last archive member.
    staged = []
    try:
        for destination, content in pending:
            destination.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            _no_symlinks(destination)
            fd, temp = tempfile.mkstemp(dir=destination.parent, prefix='.deepseek-')
            staged.append((destination, temp))
            with os.fdopen(fd, 'wb') as stream:
                os.fchmod(stream.fileno(), 0o600)
                stream.write(content)
                stream.flush()
                os.fsync(stream.fileno())
        for destination, temp in staged:
            _no_symlinks(destination)
            os.replace(temp, destination)
            actions.append({'file': str(destination.relative_to(state)), 'action': 'STAGED'})
    except OSError:
        raise DataGap('PRIVATE_OVERLAY_WRITE_FAILED') from None
    finally:
        for _, temp in staged:
            if os.path.exists(temp):
                os.unlink(temp)
    return {'actions': actions, 'publication_history': 'untouched',
            'credential_contents': 'never output'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--archive', required=True)
    parser.add_argument('--state-dir', required=True)
    args = parser.parse_args()
    try:
        result = merge(args.archive, args.state_dir)
    except DataGap as exc:
        print(json.dumps({'status': 'CONFLICT_OR_UNAVAILABLE', 'reason': str(exc)}))
        return 2
    except OSError:
        print(json.dumps({'status': 'CONFLICT_OR_UNAVAILABLE', 'reason': 'PRIVATE_OVERLAY_IO_FAILURE'}))
        return 2
    print(json.dumps(result, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
