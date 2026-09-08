"""SMTP acceptance ambiguity, dedupe and late-report labeling."""
import datetime as dt
import pytest
import brief
import deliver_report as D
from report_store import Store
from test_daily_pipeline import NOW,services


class SMTP:
    sent=[]
    fail=False
    def __init__(self,*a,**k):pass
    def __enter__(self):return self
    def __exit__(self,*a):pass
    def login(self,*a):pass
    def send_message(self,msg):
        self.sent.append(msg)
        if self.fail:raise TimeoutError('ambiguous')
        return {}


def fixture(tmp_path,monkeypatch):
    store=Store(tmp_path)
    store.publish(NOW.date().isoformat(),brief.compute(now=NOW,services=services()))
    monkeypatch.setenv('RB_SMTP_USER','sender@example.org')
    monkeypatch.setenv('RB_SMTP_PASSWORD','test-only')
    SMTP.sent=[];SMTP.fail=False
    return store


def test_one_message_for_repeated_delivery(tmp_path,monkeypatch):
    store=fixture(tmp_path,monkeypatch)
    for _ in range(2):D.send(store,'2026-09-08','sender@example.org','recipient@example.org',smtp_factory=SMTP,now=NOW)
    assert len(SMTP.sent)==1 and store.delivery('2026-09-08')['state']=='sent'
    msg=SMTP.sent[0]
    assert len(msg.get_payload())==2
    assert 'Part 1' in msg.get_body(preferencelist=('plain',)).get_content()
    assert 'Part 2' in msg.get_body(preferencelist=('html',)).get_content()


def test_ambiguous_send_is_not_blindly_retried(tmp_path,monkeypatch):
    store=fixture(tmp_path,monkeypatch);SMTP.fail=True
    with pytest.raises(RuntimeError,match='ambiguous'):
        D.send(store,'2026-09-08','s@e.org','r@e.org',smtp_factory=SMTP,now=NOW)
    SMTP.fail=False
    D.send(store,'2026-09-08','s@e.org','r@e.org',smtp_factory=SMTP,now=NOW)
    assert len(SMTP.sent)==1 and store.delivery('2026-09-08')['state']=='unknown'


def test_late_delivery_is_informational_without_mutating_frozen_report(tmp_path,monkeypatch):
    store=fixture(tmp_path,monkeypatch)
    original=store.get('2026-09-08')
    D.send(store,'2026-09-08','s@e.org','r@e.org',smtp_factory=SMTP,now=NOW+dt.timedelta(minutes=30))
    assert 'INFORMATIONAL' in str(SMTP.sent[0]['Subject'])
    assert store.get('2026-09-08')==original


def test_missing_credentials_does_not_claim_a_delivery(tmp_path,monkeypatch):
    store=fixture(tmp_path,monkeypatch);monkeypatch.delenv('RB_SMTP_PASSWORD')
    with pytest.raises(ValueError,match='missing'):
        D.send(store,'2026-09-08','s@e.org','r@e.org',smtp_factory=SMTP,now=NOW)
    assert store.delivery('2026-09-08') is None
