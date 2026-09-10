import datetime as dt
from concurrent.futures import ThreadPoolExecutor
import pytest
import brief
from report_store import Store, encode
from replacement_report import Replacements
from test_daily_pipeline import NOW, services


def test_replacement_preserves_original_and_claims_once(tmp_path):
    store = Store(tmp_path)
    original = store.publish('2026-09-08',brief.compute(now=NOW,services=services()))
    store.claim_delivery('2026-09-08','original-gmail-id')
    store.finish_delivery('2026-09-08','sent')
    delivery = store.delivery('2026-09-08')
    r = Replacements(tmp_path)
    def claim(_):
        return r.claim('2026-09-08','requested-1',authorization='recipient requested resend',
                       notes=['Transport unavailable.'],review_url='https://github.com/rufatb/RB/pull/1')
    with ThreadPoolExecutor(4) as ex:
        assert sum(ex.map(claim,range(8))) == 1
    payload = r.render('2026-09-08','requested-1',tmp_path/'dispatch',NOW+dt.timedelta(hours=1))
    assert 'REPLACEMENT / INFORMATIONAL' in payload['subject']
    for field in ('text','html'):
        assert 'Transport unavailable.' in payload[field]
        assert 'no recovered or fresh entry signal is claimed' in payload[field]
    r.finish('2026-09-08','requested-1','sent',message_id='replacement-gmail-id')
    assert r.get('2026-09-08','requested-1')['message_id'] == 'replacement-gmail-id'
    assert encode(store.get('2026-09-08')) == encode(original)
    assert store.delivery('2026-09-08') == delivery
    with pytest.raises(ValueError,match='reconcile Sent'):
        r.render('2026-09-08','requested-1',tmp_path/'again',NOW)


def test_replacement_never_bootstraps_blank_history(tmp_path):
    with pytest.raises(ValueError,match='history required'):
        Replacements(tmp_path)
    assert not (tmp_path/'reports.sqlite3').exists()
