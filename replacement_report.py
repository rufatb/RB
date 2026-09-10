"""Explicitly authorized follow-up views; never overwrite a daily publication.

This module is not called by scheduled senders. Claim, save durable state, then
render and send through the designated Gmail connector. Ambiguous claims must
be reconciled in Sent; there is no retry/reset operation.
"""
import copy
import hashlib
import json
from pathlib import Path
from report_store import Store, encode
from prepare_delivery import artifacts


class Replacements:
    def __init__(self, directory):
        if not (Path(directory)/'reports.sqlite3').is_file():
            raise ValueError('existing publication history required')
        self.store = Store(directory)
        with self.store.connect() as db:
            db.execute('''CREATE TABLE IF NOT EXISTS replacements (
                session TEXT NOT NULL REFERENCES reports(session),
                replacement_id TEXT NOT NULL, body TEXT NOT NULL,
                sha256 TEXT NOT NULL, authorization TEXT NOT NULL,
                state TEXT NOT NULL, message_id TEXT, detail TEXT,
                PRIMARY KEY(session,replacement_id))''')

    def claim(self, session, replacement_id, *, authorization, notes, review_url):
        if not authorization.strip() or not replacement_id.strip() or not notes:
            raise ValueError('explicit authorization, identity and factual notes required')
        if not review_url.startswith('https://github.com/rufatb/RB/pull/'):
            raise ValueError('repository review link required')
        report = self.store.get(session)
        if report is None:
            raise ValueError('original publication required')
        report = copy.deepcopy(report)
        report['replacement'] = dict(id=replacement_id, notes=list(notes), review_url=review_url)
        report['publication_status'] = report['report_status']
        report['report_status'] = 'INFORMATIONAL / PARTIAL DATA'
        body = encode(report)
        digest = hashlib.sha256(body.encode()).hexdigest()
        with self.store.connect() as db:
            return db.execute('''INSERT OR IGNORE INTO replacements
                VALUES (?,?,?,?,?,'sending',NULL,NULL)''',
                (session,replacement_id,body,digest,authorization)).rowcount == 1

    def get(self, session, replacement_id):
        with self.store.connect() as db:
            row = db.execute('SELECT body,sha256,state,message_id FROM replacements '
                             'WHERE session=? AND replacement_id=?',
                             (session,replacement_id)).fetchone()
        if row is None:
            raise ValueError('no authorized replacement claim')
        if hashlib.sha256(row[0].encode()).hexdigest() != row[1]:
            raise ValueError('replacement integrity failure')
        return dict(report=json.loads(row[0]), state=row[2], message_id=row[3])

    def render(self, session, replacement_id, directory, now=None):
        row = self.get(session,replacement_id)
        if row['state'] != 'sending':
            raise ValueError('replacement already attempted; reconcile Sent')
        payload = artifacts(row['report'],directory,now)
        payload['subject'] = f'RB Daily Report — {session} — REPLACEMENT / INFORMATIONAL / PARTIAL DATA'
        (Path(directory)/'gmail_payload.json').write_text(json.dumps(payload,indent=2))
        return payload

    def finish(self, session, replacement_id, state, *, message_id=None, detail=''):
        if state not in {'sent','unknown'} or (state == 'sent' and not message_id):
            raise ValueError('confirmed sent requires actual Gmail message ID')
        with self.store.connect() as db:
            changed = db.execute('UPDATE replacements SET state=?,message_id=?,detail=? '
                                 "WHERE session=? AND replacement_id=? AND state='sending'",
                                 (state,message_id,detail,session,replacement_id)).rowcount
        if changed != 1:
            raise ValueError('no pending replacement; reconcile Sent')
