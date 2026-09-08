"""Durable, atomic publish-once snapshots, separate from legacy CSV evidence.

SQLite unique keys cover zero-pick sessions as well as populated boards.
A report is immutable after publication; outcome and delivery states are separate.
"""
from __future__ import annotations
import hashlib
import json
import sqlite3
from pathlib import Path


def encode(value):
    def default(obj):
        if hasattr(obj, 'isoformat'):
            return obj.isoformat()
        if hasattr(obj, 'item'):
            return obj.item()
        raise TypeError(type(obj).__name__)
    return json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False, default=default)


class Store:
    def __init__(self, directory):
        Path(directory).mkdir(parents=True, exist_ok=True)
        self.path = Path(directory) / 'reports.sqlite3'
        with self.connect() as db:
            db.executescript('''
                CREATE TABLE IF NOT EXISTS reports (
                    session TEXT PRIMARY KEY, body TEXT NOT NULL, sha256 TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS deliveries (
                    session TEXT PRIMARY KEY, state TEXT NOT NULL, message_id TEXT,
                    detail TEXT, FOREIGN KEY(session) REFERENCES reports(session));
                CREATE TABLE IF NOT EXISTS outcomes (
                    session TEXT NOT NULL, ticker TEXT NOT NULL, exit_time TEXT NOT NULL,
                    body TEXT NOT NULL, PRIMARY KEY(session,ticker,exit_time));
            ''')

    def connect(self):
        db = sqlite3.connect(self.path, timeout=15)
        db.execute('PRAGMA busy_timeout=15000')
        db.execute('PRAGMA foreign_keys=ON')
        return db

    def get(self, session):
        with self.connect() as db:
            row = db.execute('SELECT body,sha256 FROM reports WHERE session=?', (session,)).fetchone()
        if not row:
            return None
        if hashlib.sha256(row[0].encode()).hexdigest() != row[1]:
            raise ValueError('published report integrity failure')
        return json.loads(row[0])

    def publish(self, session, report):
        body = encode(report)
        with self.connect() as db:
            db.execute('INSERT OR IGNORE INTO reports VALUES (?,?,?)',
                       (session, body, hashlib.sha256(body.encode()).hexdigest()))
        return self.get(session)

    def delivery(self, session):
        with self.connect() as db:
            row = db.execute('SELECT state,message_id,detail FROM deliveries WHERE session=?', (session,)).fetchone()
        return dict(zip(('state','message_id','detail'), row)) if row else None

    def claim_delivery(self, session, message_id):
        """Only a never-attempted delivery may send; ambiguous SMTP is not retried."""
        with self.connect() as db:
            return db.execute('INSERT OR IGNORE INTO deliveries VALUES (?,\'sending\',?,NULL)',
                              (session,message_id)).rowcount == 1

    def finish_delivery(self, session, state, detail=''):
        if state not in {'sent', 'unknown', 'failed_before_send'}:
            raise ValueError('invalid delivery state')
        with self.connect() as db:
            db.execute('UPDATE deliveries SET state=?,detail=? WHERE session=?', (state,detail,session))

    def reports(self):
        with self.connect() as db:
            dates = [r[0] for r in db.execute('SELECT session FROM reports ORDER BY session')]
        return [self.get(d) for d in dates]


def read_observations(directory):
    """Read-only access for previews; never creates a database or schema."""
    path=Path(directory)/'reports.sqlite3'
    if not path.exists():return [],[]
    with sqlite3.connect(path.resolve().as_uri()+'?mode=ro',uri=True) as db:
        reports=[]
        for body,digest in db.execute('SELECT body,sha256 FROM reports ORDER BY session'):
            if hashlib.sha256(body.encode()).hexdigest()!=digest:
                raise ValueError('published report integrity failure')
            reports.append(json.loads(body))
        outcomes=[]
        for session,body in db.execute('SELECT session,body FROM outcomes'):
            outcomes.append({**json.loads(body),'session':session})
    return reports,outcomes
