"""Safe operational archive transfer; online SQLite backup, never an empty reset."""
import argparse
from pathlib import Path, PurePosixPath
import sqlite3
import tempfile
import zipfile


def extract(archive,directory):
    root=Path(directory)
    if root.exists() and any(root.iterdir()): raise ValueError('restore into a fresh directory only')
    with zipfile.ZipFile(archive) as z:
        names=set()
        for i in z.infolist():
            p=PurePosixPath(i.filename)
            if (p.is_absolute() or '..' in p.parts or '\\' in i.filename or ':' in i.filename
                or i.filename in names or (i.external_attr>>16)&0o170000==0o120000):
                raise ValueError('unsafe/duplicate archive member')
            names.add(i.filename)
        if 'reports.sqlite3' not in names: raise ValueError('missing publication history')
        z.extractall(root)
    with sqlite3.connect((root/'reports.sqlite3').resolve().as_uri()+'?mode=ro',uri=True) as db:
        if db.execute('PRAGMA integrity_check').fetchone()[0]!='ok': raise ValueError('state integrity failure')


def pack(directory,archive):
    root=Path(directory)
    if not (root/'reports.sqlite3').is_file(): raise ValueError('missing publication history')
    with tempfile.TemporaryDirectory() as tmp:
        backup=Path(tmp)/'reports.sqlite3'
        with sqlite3.connect(root/'reports.sqlite3') as source, sqlite3.connect(backup) as target:
            source.backup(target)
        output=Path(tmp)/'state.zip'
        with zipfile.ZipFile(output,'w',zipfile.ZIP_DEFLATED) as z:
            z.write(backup,'reports.sqlite3')
            for p in sorted(root.rglob('*')):
                if p.is_symlink(): raise ValueError('symlink in operational state')
                if p.is_file() and p.name not in {'reports.sqlite3','reports.sqlite3-shm','reports.sqlite3-wal','publication.lock'}:
                    z.write(p,p.relative_to(root))
        import shutil
        shutil.copyfile(output,archive)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('action',choices=['extract','pack']);p.add_argument('--archive',required=True)
    p.add_argument('--directory',required=True);a=p.parse_args()
    if a.action=='extract': extract(a.archive,a.directory)
    else: pack(a.directory,a.archive)
