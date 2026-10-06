"""The council flash (owner, 2026-10-06): the council's decision by email the
moment it is sealed, ahead of the 09:46 report."""
import datetime as dt
import json

import council_flash as F

ET = F.ET
AT = dt.datetime(2026, 10, 6, 9, 0, tzinfo=ET)


def council(status='READY', picks=('P1',)):
    votes = {m: {'stance': 'ENDORSE', 'conviction': 0.6, 'argument': 'rows say so'}
             for m in ('Claude', 'DeepSeek', 'Gemini')}
    return {'session': '2026-10-06', 'status': status, 'picks': list(picks),
            'asked_at': '2026-10-06T08:57:55-04:00', 'finished_at': '2026-10-06T08:58:23-04:00',
            'positions': [{'id': 'P1', 'ticker': 'CVE.TO', 'side': 'SHORT', 'lead': 'Gemini',
                           'reason': 'dilution selling', 'invalid_at': 45.81}],
            'tally': {'members': ['Claude', 'DeepSeek', 'Gemini'], 'absent': [],
                      'rows': [{'id': 'P1', 'side': 'SHORT', 'ticker': 'CVE.TO',
                                'consensus': status == 'READY', 'endorse': list(votes),
                                'oppose': [], 'seats': list(votes), 'votes': votes, 'weakest': 0.6}]}}


def write(tmp_path, obj):
    (tmp_path/'council.json').write_text(json.dumps(obj))


def test_flash_carries_the_decision_and_its_wrong_if(tmp_path):
    write(tmp_path, council())
    code, info = F.wait(tmp_path, 0, now_fn=lambda: AT)
    assert code == 0 and info['subject'] == 'RB Council Flash — 2026-10-06 — SHORT CVE.TO (3 of 3 endorse)'
    text = (tmp_path/'flash'/'report.txt').read_text()
    assert 'above 45.81' in text and 'decided at 08:58 ET (before the open)' in text
    assert 'not yet checked against the open' in text
    assert (tmp_path/'flash'/'report.html').read_text().startswith('<!doctype html>')


def test_the_subject_never_blocks_the_report():
    """Every sender skips the report when it finds "RB Daily Report — <today>"."""
    for c in (council(), council('NO_CONSENSUS', ())):
        import council as K
        assert 'RB Daily Report' not in F.subject('2026-10-06', K.top_two(c))


def test_no_consensus_still_flashes_and_says_so(tmp_path):
    write(tmp_path, council('NO_CONSENSUS', ()))
    code, info = F.wait(tmp_path, 0, now_fn=lambda: AT)
    assert code == 0 and info['subject'].endswith('no consensus — nothing to act on')


def test_waits_for_the_council_then_stops_at_0944(tmp_path):
    assert F.wait(tmp_path, 0, now_fn=lambda: AT)[0] == 2
    late = AT.replace(hour=9, minute=44)
    assert F.wait(tmp_path, 0, now_fn=lambda: late)[1]['status'] == 'TOO_LATE'
    write(tmp_path, {**council(), 'session': '2026-10-05'})          # yesterday's is not today's
    assert F.wait(tmp_path, 0, now_fn=lambda: AT)[0] == 2


def test_a_council_that_did_not_sit_sends_nothing(tmp_path):
    write(tmp_path, {**council(), 'status': 'UNAVAILABLE', 'reason': 'fewer than two members'})
    code, info = F.wait(tmp_path, 0, now_fn=lambda: AT)
    assert code == 3 and info['status'] == 'NOTHING'


def test_sent_once(tmp_path):
    write(tmp_path, council())
    F.record(tmp_path, 'abc', now=AT)
    assert F.wait(tmp_path, 0, now_fn=lambda: AT)[0] == 4


def test_morning_prompt_sends_the_flash_before_the_wait():
    from pathlib import Path
    body = (Path(__file__).resolve().parent.parent/'ROUTINE_PROMPT.md').read_text()
    assert body.index('council_flash.py') < body.index('python morning_wait.py')
