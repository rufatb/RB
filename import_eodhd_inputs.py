"""Merge a private EODHD input overlay without replacing operational history."""
import argparse
import json
import os
from pathlib import Path, PurePosixPath
import sqlite3
import tempfile
import zipfile

from eodhd import DataGap, aware

ALLOWED = {'secrets/eodhd_api_key','eodhd_status.json','diagnostics/day97-opening-path.json'}


def merge(archive, state):
    state = Path(state)
    db = state/'reports.sqlite3'
    # An overlay is not a replacement for the durable publication database.
    if not db.is_file() or db.is_symlink():
        raise DataGap('EXISTING_PUBLICATION_STATE_REQUIRED')
    with sqlite3.connect(db.resolve().as_uri()+'?mode=ro',uri=True) as conn:
        if conn.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
            raise DataGap('PUBLICATION_STATE_INTEGRITY_FAILURE')
    pending, actions = [], []
    with zipfile.ZipFile(archive) as bundle:
        seen = set()
        for item in bundle.infolist():
            name = item.filename
            p = PurePosixPath(name)
            if p.is_absolute() or '..' in p.parts or '\\' in name or ':' in name or name in seen:
                raise DataGap('UNSAFE_OR_DUPLICATE_OVERLAY_MEMBER')
            seen.add(name)
            if (item.external_attr>>16)&0o170000 == 0o120000:
                raise DataGap('OVERLAY_SYMLINK_REJECTED')
            if item.is_dir():
                if name not in ('secrets/','diagnostics/'):
                    raise DataGap('UNEXPECTED_OVERLAY_DIRECTORY')
                continue
            if name not in ALLOWED or item.file_size > 1_000_000:
                raise DataGap('UNEXPECTED_OVERLAY_FILE')
            destination = state/name
            if any(part.is_symlink() for part in [destination,*destination.parents] if part != state.parent):
                raise DataGap('DESTINATION_SYMLINK_REJECTED')
            content = bundle.read(item)
            if name == 'secrets/eodhd_api_key':
                token = content.decode().strip()
                if not token or any(c.isspace() for c in token) or len(token)>256:
                    raise DataGap('INVALID_CREDENTIAL_FILE')
                if destination.exists() and destination.read_text().strip() != token:
                    raise DataGap('EXISTING_CREDENTIAL_CONFLICT — retain original; operator review required')
            else:
                data = json.loads(content)
                if not isinstance(data,dict):
                    raise DataGap('INVALID_OVERLAY_JSON')
                if name == 'eodhd_status.json':
                    checked = aware(data['checked_at'])
                    if destination.exists() and aware(json.loads(destination.read_text())['checked_at']) >= checked:
                        actions.append({'file':name,'action':'preserved newer/equal prepared status'})
                        continue
                elif destination.exists():
                    actions.append({'file':name,'action':'preserved existing diagnostic'})
                    continue
            pending.append((destination,content))
    # Validate the whole archive before any write. Writes are idempotent and
    # individually atomic; the caller must durably save the containing archive.
    for path, content in pending:
        path.parent.mkdir(parents=True,exist_ok=True)
        fd,temp = tempfile.mkstemp(dir=path.parent,prefix='.eodhd-')
        try:
            with os.fdopen(fd,'wb') as stream:
                stream.write(content)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temp,path)
        finally:
            if os.path.exists(temp):os.unlink(temp)
        actions.append({'file':str(path.relative_to(state)),'action':'staged'})
    return {'actions':actions,'publication_history':'untouched','credential_contents':'never output'}


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--archive',required=True);p.add_argument('--state-dir',required=True)
    a=p.parse_args();print(json.dumps(merge(a.archive,a.state_dir),indent=2))
