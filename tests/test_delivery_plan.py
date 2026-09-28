"""The delivery ladder always ends in something sendable, chosen by a script."""
import brief
import delivery_plan as D
import picks_only
from report_store import Store
from test_daily_pipeline import NOW, services


def test_a_published_report_is_prepared_and_claimed_once(tmp_path):
    d = brief.compute(now=NOW, services=services())
    Store(tmp_path).publish(d['session'], d)
    first = D.plan(tmp_path, now=NOW, record=False)
    assert first['mode'] == 'REPORT' and first['claimed'] is True
    assert d['session'] in open(first['subject_path']).read()
    again = D.plan(tmp_path, now=NOW, record=False)
    # The second call does not re-claim; it points at the same files and says
    # the inbox decides.
    assert again['mode'] == 'REPORT' and again['claimed'] is False
    assert again['text_path'] == first['text_path'] and 'inbox' in again['note']


def test_no_publication_but_sealed_picks_sends_picks_only(tmp_path, monkeypatch):
    snaps = {'claude': {'status': 'READY', 'longs': [{'ticker': 'QSR.TO', 'confidence': .52}],
                        'shorts': []},
             'opportunities': {'status': 'UNAVAILABLE', 'reason': 'x'},
             'jev': {'status': 'UNAVAILABLE', 'reason': 'x'}}
    monkeypatch.setattr(picks_only, 'load', lambda root, now: snaps)
    monkeypatch.setattr('late_picks.biotech_part', lambda root, now: [])
    out = D.plan(tmp_path, now=NOW, record=False, reason='morning.sh exit 1')
    assert out['mode'] == 'PICKS_ONLY' and 'PICKS ONLY (morning.sh exit 1)' in open(out['subject_path']).read()


def test_nothing_at_all_asks_for_late_picks(tmp_path, monkeypatch):
    down = {'status': 'UNAVAILABLE', 'reason': 'x'}
    monkeypatch.setattr(picks_only, 'load', lambda root, now: {'claude': down, 'opportunities': down, 'jev': down})
    monkeypatch.setattr('late_picks.biotech_part', lambda root, now: [])
    assert D.plan(tmp_path, now=NOW, record=False)['mode'] == 'LATE'
