"""Day-149c — the event desk (PREREGISTER_day149_event_desk.md)."""
import datetime as dt
import json
import re
from pathlib import Path

import pytest

import event_desk as E

ET = E.ET
ROOT = Path(__file__).resolve().parent.parent
NOW = dt.datetime(2026, 11, 10, 15, 14, tzinfo=ET)                 # a Tuesday
D = dt.date.fromisoformat
WEEKDAYS = lambda d: d.weekday() < 5                                   # noqa: E731
LIST = {'AAA.TO': 'Trucking', 'BBB.TO': 'Trucking', 'CCC.TO': 'Trucking', 'DDD.TO': 'Trucking',
        'ZZZ.TO': 'Gold'}


def past(*surprises, est=1.0):
    """FMP earnings rows, newest first, one a quarter back from August."""
    rows, day = [], D('2026-08-05')
    for s in surprises:
        rows.append({'date': day.isoformat(), 'epsActual': est * (1 + s / 100), 'epsEstimated': est})
        day -= dt.timedelta(days=91)
    return rows


def coming(day='2026-11-11', eps=1.2, revenue=9.5e8):
    return {'date': day, 'epsActual': None, 'epsEstimated': eps, 'revenueEstimated': revenue}


def peer(day, surprise):
    return [{'date': day, 'epsActual': 1 + surprise / 100, 'epsEstimated': 1.0}]


UP = [coming()] + past(8, 7, 9, 6, 12, 5, 8, 10)
MIXED = [coming()] + past(3, -2, 4, -1, 2, -5, 1, -3)
GRADES_UP = [{'date': '2026-11-03', 'gradingCompany': 'Broker A', 'action': 'upgrade',
              'previousGrade': 'Hold', 'newGrade': 'Buy'}]


def test_the_prompt_is_the_registered_one_verbatim():
    doc = (ROOT/'PREREGISTER_day149_event_desk.md').read_text()
    assert re.search(r'```\n(.*?)\n```', doc, re.S).group(1) == E.SYSTEM_PROMPT
    assert E.PROMPT_VERSION == 'day149-event-v1' and E.MODEL == 'deepseek-v4-pro'
    assert 'ticker' not in E.SYSTEM_PROMPT and 'share price is supplied' in E.SYSTEM_PROMPT


def test_a_surprise_is_measured_against_the_size_of_the_consensus():
    assert E.surprise_pct({'epsActual': 1.1, 'epsEstimated': 1.0}) == 10.0
    assert E.surprise_pct({'epsActual': -0.4, 'epsEstimated': -0.5}) == 20.0
    assert E.surprise_pct({'epsActual': 0.1, 'epsEstimated': 0.001}) is None
    assert E.surprise_pct({'epsActual': None, 'epsEstimated': 1.0}) is None


def test_the_facts_hold_no_price_and_the_item_no_name():
    f = E.facts('AAA.TO', D('2026-11-11'), D('2026-11-10'), earnings=UP, grades=GRADES_UP,
                consensus=[{'buy': 6, 'hold': 2, 'sell': 0}], industry='Trucking',
                peer_rows={'AAA.TO': UP, 'BBB.TO': peer('2026-11-04', 6), 'CCC.TO': peer('2026-10-30', -2),
                           'DDD.TO': peer('2026-08-01', 9)})          # August is not this season
    assert f['consensus'] == {'eps': 1.2, 'revenue': 9.5e8} and f['beats'] == '8 of 8'
    assert [p['ticker'] for p in f['peers']] == ['BBB.TO', 'CCC.TO']
    assert f['surprise_history'][0] == {'date': '2026-08-05', 'eps_surprise_pct': 8.0}
    assert f['analyst_30d'][0].startswith('2026-11-03 Broker A upgrade')
    it = E.item('R01', f)
    text = json.dumps(it)
    assert 'AAA' not in text and 'BBB' not in text and 'ticker' not in text
    assert it['peers'] == [{'date': '2026-11-04', 'eps_surprise_pct': 6.0},
                           {'date': '2026-10-30', 'eps_surprise_pct': -2.0}]
    assert not any(k in text for k in ('close', 'price_', 'return', 'typical'))


def fact(history=None, peers=None, analyst=None, nowcast=None):
    f = {}
    if history is not None:
        f['surprise_history'] = [{'date': 'd', 'eps_surprise_pct': x} for x in history]
    if peers is not None:
        f['peers'] = [{'ticker': 'P', 'date': 'd', 'eps_surprise_pct': x} for x in peers]
    if analyst:
        f['analyst_30d'] = ['2026-11-0%d Broker %s Hold→X' % (k + 1, a) for k, a in enumerate(analyst)]
    if nowcast is not None:
        f['nowcast'] = nowcast
    return f


def test_each_facts_direction_is_computed_here():
    assert E.points(fact(history=[1, 2, 3, 4, 5, 6, -1, -2])) == {'surprise_history': 'up'}      # 6 of 8
    assert E.points(fact(history=[1, 2, 3, 4, 5, -1, -2, -3])) == {'surprise_history': 'mixed'}  # 5 of 8
    assert E.points(fact(history=[1, 2, -3, -4, -5, -6, -1, -2])) == {'surprise_history': 'down'}
    assert E.points(fact(history=[1, 2, 3])) == {}                       # fewer than four reports
    assert E.points(fact(peers=[5, 6, 7, -1])) == {'peers': 'up'} and E.points(fact(peers=[5])) == {}
    assert E.points(fact(analyst=['upgrade', 'upgrade', 'downgrade'])) == {'analyst': 'up'}
    assert E.points(fact(analyst=['upgrade', 'downgrade'])) == {'analyst': 'mixed'}
    assert E.points({'analyst_consensus': 'buy 9 / hold 1 / sell 0'}) == {}       # standing ratings point nowhere
    assert E.points(fact(nowcast={'gap_pct': 4.0})) == {'nowcast': 'up'}
    assert E.points(fact(nowcast={'gap_pct': -3.0})) == {'nowcast': 'down'}
    assert E.points(fact(nowcast={'gap_pct': 2.9})) == {'nowcast': 'mixed'}
    assert E.points(fact(nowcast={'gap_pct': 9.0, 'structural': True})) == {}
    assert E.points(fact(nowcast={'gap_pct': 9.0, 'consensus_checked': False})) == {}


def test_a_side_needs_two_facts_one_way_and_none_against():
    up8, dn8 = [1] * 8, [-1] * 8
    assert E.gate(fact(history=up8, peers=[1, 2])) == 'LONG'
    assert E.gate(fact(history=dn8, analyst=['downgrade'])) == 'SHORT'
    assert E.gate(fact(history=up8)) is None                                  # one fact is not enough
    assert E.gate(fact(history=up8, peers=[1, 2], analyst=['downgrade'])) is None     # one points against
    assert E.gate(fact(history=up8, peers=[1, -2, 3, -4])) is None            # mixed is not agreement
    assert E.gate(fact(history=up8, peers=[1, -2, 3, -4], nowcast={'gap_pct': 5.0})) == 'LONG'
    assert E.gate({}) is None and (E.NEEDED, E.MOSTLY, E.MIN_HISTORY, E.MIN_PEERS) == (2, 0.75, 4, 2)


def call(ident, result='BEAT', side='LONG', basis='surprise_history', confidence=0.7, reason='r'):
    return {'id': ident, 'result': result, 'side': side, 'confidence': confidence, 'basis': basis, 'reason': reason}


def test_the_gate_overrules_the_model_and_a_bad_entry_loses_only_itself():
    open_long = E.item('R01', fact(history=[1] * 8, peers=[1, 2]))
    shut = E.item('R02', fact(history=[1] * 8))
    other = E.item('R03', fact(history=[-1] * 8, peers=[-1, -2]))
    reply = {'calls': [call('R01', basis='analyst'), call('R02'), call('R03', side='LONG'),
                       call('R04'), {'id': 'R01x'}]}
    calls, problems = E.parse(reply, [open_long, shut, other])
    assert calls['R01']['side'] == 'LONG' and calls['R01']['basis'] == 'surprise_history'   # its fact replaced
    assert calls['R02']['side'] == 'ABSTAIN' and calls['R02']['result'] == 'BEAT'
    assert calls['R03']['side'] == 'ABSTAIN'                    # the gate was open for SHORT only
    assert problems == {'basis did not point the side\'s way, replaced': 1,
                        'side outside the gate, recorded as ABSTAIN': 2, 'unknown id': 2}
    bad = {'calls': [call('R01', confidence=0.4), call('R02', result='UP'), call('R03'), call('R03')]}
    calls, problems = E.parse(bad, [open_long, shut, other])
    assert calls == {} and problems == {'confidence outside 0.5-1': 1, 'invalid result, side or basis': 1,
                                        'id answered twice': 2}
    assert E.parse({}, [shut]) == ({}, {'no calls list': 1})


# ── the afternoon read ──────────────────────────────────────────────────────

class FMP:
    def __init__(self, calendar=None, earnings=None, grades=None, prices=None):
        self.calendar, self.earnings, self.grades = calendar or [], earnings or {}, grades or {}
        self.prices, self.failures, self.asked = prices or {}, {}, []

    def __call__(self, path, **p):
        self.asked.append((path, p.get('symbol')))
        if path == 'earnings-calendar':
            return self.calendar
        if path == 'earnings':
            return self.earnings.get(p['symbol'], [])
        if path == 'grades':
            return self.grades.get(p['symbol'], [])
        if path == 'grades-consensus':
            return []
        if path == 'historical-price-eod/dividend-adjusted':
            return self.prices.get(p['symbol'], [])
        raise AssertionError(path)


class Client:
    """Takes every side the gate leaves open; abstains elsewhere."""
    def __init__(self, decline=False):
        self.seen, self.decline = [], decline
        self.chat = self
        self.completions = self

    def create(self, **kw):
        items = json.loads(kw['messages'][1]['content'])['items']
        self.seen.append(items)
        assert kw['messages'][0]['content'] == E.SYSTEM_PROMPT
        assert kw['extra_body'] == {'thinking': {'type': 'disabled'}}
        calls = []
        for i in items:
            side = 'ABSTAIN' if self.decline or i['allowed_side'] == 'none' else i['allowed_side']
            calls.append(call(i['id'], 'BEAT' if side != 'SHORT' else 'MISS', side,
                              'none' if side == 'ABSTAIN' else 'surprise_history'))
        content = json.dumps({'calls': calls})

        class R:
            model = 'deepseek-v4-pro'
            choices = [type('C', (), {'finish_reason': 'stop', 'message': type('M', (), {'content': content})})]
        return R


def feed():
    cal = [{'symbol': 'AAA.TO', 'date': '2026-11-11', 'epsActual': None},
           {'symbol': 'CCC.TO', 'date': '2026-11-11', 'epsActual': None},
           {'symbol': 'ZZZ.TO', 'date': '2026-11-12', 'epsActual': None},          # the session after next
           {'symbol': 'QQQ.TO', 'date': '2026-11-11', 'epsActual': None}]          # not on the list
    return FMP(calendar=cal, earnings={'AAA.TO': UP, 'CCC.TO': MIXED, 'BBB.TO': peer('2026-11-04', 6),
                                       'DDD.TO': peer('2026-11-05', 3)})


def build(tmp_path, read=None, client=None, now=NOW):
    ledger = tmp_path/'calls.csv'
    out = E.build(tmp_path/'state', now, read=read or feed(), client=client or Client(), industries=LIST,
                  twins={}, path=ledger, is_trading=WEEKDAYS, typical={'AAA.TO': 4.8})
    return out, ledger


def test_an_afternoon_records_every_report_and_writes_the_email(tmp_path):
    client = Client()
    (status, info), ledger = build(tmp_path, client=client)
    assert status == 'READY' and info == {**info, 'reports': 2, 'sided': 1, 'recorded': 2}
    shown = client.seen[0]
    assert [i['id'] for i in shown] == ['R01', 'R02'] and shown[0]['allowed_side'] == 'LONG'
    assert shown[0]['points'] == {'surprise_history': 'up', 'peers': 'up'} and 'AAA' not in json.dumps(shown)
    a, c = E.read_ledger(ledger)
    assert (a['ticker'], a['side'], a['result'], a['gate'], a['basis']) == \
        ('AAA.TO', 'LONG', 'BEAT', 'LONG', 'surprise_history')
    assert (a['report_date'], a['exit_date'], a['beats'], a['peers']) == \
        ('2026-11-11', '2026-11-12', '8 of 8', '2 of 2 beat')
    assert a['points'] == 'surprise history up; peers up' and float(a['typical_move_pct']) == 4.8
    assert (c['ticker'], c['side'], c['gate']) == ('CCC.TO', 'ABSTAIN', '') and a['w'] == '' == a['scored_at']
    assert a['prompt_version'] == 'day149-event-v1'
    subject = Path(info['subject_path']).read_text()
    assert subject == 'RB Event Desk — 2026-11-10 — for Wed 11-11: LONG AAA.TO · 1 abstained'
    assert 'RB Daily Report — ' not in subject
    text, html = Path(info['text_path']).read_text(), Path(info['html_path']).read_text()
    assert '| LONG AAA.TO (0.70) | BEAT | surprise history | beat 8 of 8; peers 2 of 2 beat | ±4.8% |' in text
    assert '### No side taken' in text and '| ABSTAIN CCC.TO |' in text
    assert 'The exit is the close on Thu 11-12' in text and 'never sized' in text
    assert html.startswith('<!doctype html>') and 'Event research note' in html and '<style' not in html


def test_an_all_abstain_day_still_reports_and_says_so(tmp_path):
    (status, info), ledger = build(tmp_path, client=Client(decline=True))
    assert status == 'READY' and info['sided'] == 0
    assert Path(info['subject_path']).read_text().endswith('for Wed 11-11: no side on 2 report(s)')
    assert 'The desk takes no side today' in Path(info['text_path']).read_text()
    assert {r['side'] for r in E.read_ledger(ledger)} == {'ABSTAIN'}


def test_nothing_without_a_report_and_never_after_the_last_entry(tmp_path):
    (status, info), ledger = build(tmp_path, read=FMP(calendar=[]))
    assert status == 'NOTHING' and '2026-11-11' in info['reason'] and not ledger.exists()
    assert build(tmp_path, now=dt.datetime(2026, 11, 14, 15, 14, tzinfo=ET))[0][0] == 'NOTHING'      # Saturday
    client = Client()
    (status, _), _ = build(tmp_path, client=client, now=dt.datetime(2026, 11, 10, 15, 55, tzinfo=ET))
    assert status == 'TOO_LATE' and client.seen == []
    dead = FMP()
    dead.__class__ = type('Dead', (FMP,), {'__call__': lambda self, path, **p: None})
    dead.failures = {'FMP_HTTP_429': 1}
    assert build(tmp_path, read=dead)[0] == ('FAILED', {'reason': 'FMP_HTTP_429'})


def test_one_call_a_report_and_one_email_a_day(tmp_path):
    (_, _), ledger = build(tmp_path)
    again = Client(decline=True)
    (status, info), _ = build(tmp_path, client=again)
    assert status == 'READY' and again.seen == [] and info['recorded'] == 0
    assert [r['side'] for r in E.read_ledger(ledger)] == ['LONG', 'ABSTAIN']
    E.record(tmp_path/'state', 'abc', NOW)
    assert build(tmp_path)[0] == ('ALREADY_SENT', {})
    # the same report still dated for the next session a day later is not called twice
    later = feed()
    later.calendar = [{'symbol': 'AAA.TO', 'date': '2026-11-12', 'epsActual': None}]
    rows = E.read_ledger(ledger)
    rows[0]['report_date'] = '2026-11-12'
    E.write_ledger(rows, ledger)
    (status, info), _ = build(tmp_path, read=later, now=NOW + dt.timedelta(days=1))
    assert status == 'FAILED' and len(E.read_ledger(ledger)) == 2          # nothing new to ask, nothing kept today


def test_the_next_two_sessions_skip_the_weekend():
    assert E.next_sessions(D('2026-11-13'), WEEKDAYS) == [D('2026-11-16'), D('2026-11-17')]
    assert E.due([{'symbol': 'AAA.TO', 'date': '2026-11-11', 'epsActual': 1.0}], {'AAA.TO'}, D('2026-11-11')) == []


# ── the evening score ───────────────────────────────────────────────────────

def px(**closes):
    return [{'date': d.replace('_', '-'), 'adjClose': c} for d, c in closes.items()]


def scored(tmp_path, earnings, now):
    (_, _), ledger = build(tmp_path)
    read = FMP(earnings=earnings, prices={
        'AAA.TO': px(d2026_11_10=100.0, d2026_11_11=103.0, d2026_11_12=104.0),
        'CCC.TO': px(d2026_11_10=50.0, d2026_11_12=49.0),
        'XIU.TO': px(d2026_11_10=40.0, d2026_11_12=40.4)})
    for rows in read.prices.values():
        for r in rows:
            r['date'] = r['date'][1:]
    return E.score(ledger, now=now, read=read), ledger, read


def test_the_score_waits_for_the_exit_then_fills_prices_and_the_result(tmp_path):
    reported = {'AAA.TO': [{'date': '2026-11-11', 'epsActual': 1.32, 'epsEstimated': 1.2}],
                'CCC.TO': [{'date': '2026-11-11', 'epsActual': 0.9, 'epsEstimated': 1.0}]}
    early, ledger, read = scored(tmp_path, reported, dt.datetime(2026, 11, 11, 16, 30, tzinfo=ET))
    assert early == {'priced': 0, 'confirmed': 0, 'not_confirmed': 0, 'waiting': 0} and read.asked == []
    out = E.score(ledger, now=dt.datetime(2026, 11, 12, 16, 30, tzinfo=ET), read=read)
    assert out == {'priced': 2, 'confirmed': 2, 'not_confirmed': 0, 'waiting': 0}
    a, c = E.read_ledger(ledger)
    assert float(a['move']) == pytest.approx(3.0) and float(a['w']) == pytest.approx(3.0)      # +4% less XIU's +1%
    assert (a['confirmed'], a['result_right'], float(a['surprise_pct'])) == ('true', 'true', 10.0)
    assert float(c['move']) == pytest.approx(-3.0) and c['w'] == ''                           # an abstention has no w
    assert (c['confirmed'], c['result_right']) == ('true', 'false') and a['scored_at'] and c['scored_at']
    before = ledger.read_text()
    assert E.score(ledger, now=dt.datetime(2026, 11, 13, 16, 30, tzinfo=ET), read=read)['priced'] == 0
    assert ledger.read_text() == before


def test_a_report_that_never_arrives_is_not_confirmed(tmp_path):
    slipped = {'AAA.TO': [{'date': '2026-11-13', 'epsActual': 1.3, 'epsEstimated': 1.2}], 'CCC.TO': []}
    out, ledger, read = scored(tmp_path, slipped, dt.datetime(2026, 11, 12, 16, 30, tzinfo=ET))
    assert out == {'priced': 2, 'confirmed': 0, 'not_confirmed': 0, 'waiting': 2}
    assert E.read_ledger(ledger)[0]['scored_at'] == '' and E.read_ledger(ledger)[0]['w'] != ''
    out = E.score(ledger, now=dt.datetime(2026, 11, 17, 16, 30, tzinfo=ET), read=read)
    assert out == {'priced': 0, 'confirmed': 0, 'not_confirmed': 2, 'waiting': 0}
    assert [r['confirmed'] for r in E.read_ledger(ledger)] == ['false', 'false']
    assert E.verdict(ledger) == {'verdict': 'NOT_DUE', 'calls': 0, 'due_at': 60}


# ── the registered decision ─────────────────────────────────────────────────

def planted(tmp_path, n, mean, flip=0.0):
    rows, day = [], D('2026-11-10')
    for k in range(n):
        w = mean + (2.0 if k % 2 else -2.0) + (flip if k >= n // 2 else 0)
        rows.append({'session': (day + dt.timedelta(days=k)).isoformat(), 'ticker': 'T%d.TO' % k,
                     'side': 'LONG', 'confirmed': 'true', 'w': w})
    path = tmp_path/'v.csv'
    E.write_ledger(rows, path)
    return path


def test_the_verdict_waits_for_sixty_confirmed_calls_and_reads_the_registered_bar(tmp_path):
    assert E.verdict(planted(tmp_path, 59, 2.0)) == {'verdict': 'NOT_DUE', 'calls': 59, 'due_at': 60}
    good = E.verdict(planted(tmp_path, 60, 1.5))
    assert good['verdict'] == 'PASS' and good['t'] >= 3 and good['calls'] == 60 and good['net_pct'] > 0
    assert E.verdict(planted(tmp_path, 60, -0.1))['verdict'] == 'FAIL'
    assert E.verdict(planted(tmp_path, 60, 0.2))['verdict'] == 'CONTINUE'
    assert E.verdict(planted(tmp_path, 60, 1.5, flip=-3.2))['verdict'] != 'PASS'          # the halves disagree
    final = E.verdict(planted(tmp_path, 120, 0.2))
    assert final['calls'] == 120 and final['verdict'] in ('FAIL', 'UNDERPOWERED')


def test_abstentions_and_unconfirmed_calls_are_not_in_the_verdict(tmp_path):
    path = planted(tmp_path, 60, 1.5)
    rows = E.read_ledger(path)
    rows[0]['side'], rows[1]['confirmed'] = 'ABSTAIN', 'false'
    E.write_ledger(rows, path)
    assert E.verdict(path) == {'verdict': 'NOT_DUE', 'calls': 58, 'due_at': 60}


# ── the control ─────────────────────────────────────────────────────────────

def test_the_control_plants_two_names_the_gate_opens_and_six_it_keeps_shut():
    items, names = E.control_items(seed=3)
    assert sorted(names.values()) == ['CTLDN.TO', 'CTLUP.TO'] + ['NOIS%d.TO' % k for k in range(6)]
    by = {names[i['id']]: i for i in items}
    assert by['CTLUP.TO']['allowed_side'] == 'LONG' and by['CTLDN.TO']['allowed_side'] == 'SHORT'
    assert all(by['NOIS%d.TO' % k]['allowed_side'] == 'none' for k in range(6))
    assert 'CTL' not in json.dumps(items) and 'NOIS' not in json.dumps(items)
    out = E.control(3, client=Client())
    assert out['clean'] == 3 and out['of'] == 3 and out['runs'][0]['up'] == 'BEAT/LONG'
    assert E.control(2, client=Client(decline=True))['clean'] == 0              # a desk that never sides fails it


# ── the Routine and the registration ────────────────────────────────────────

def test_the_routine_prompt_names_real_commands_and_carries_no_key():
    text = (ROOT/'ROUTINE_EVENTDESK.md').read_text()
    for flag in ('--build', '--record', '--message-id', '--state-dir'):
        assert 'event_desk.py' in text and flag in text
    assert 'send_check.py' in text and 'data/event_calls.csv' in text
    assert 'RB Daily Report — ' not in text.replace('never contains "RB Daily Report — "', '')
    for secret in ('sk-', 'apikey=', 'AIza'):
        assert secret not in text
    assert 'Never create, modify, enable, disable or delete any Routine' in text


def test_the_registration_fixes_what_the_code_does():
    doc = (ROOT/'PREREGISTER_day149_event_desk.md').read_text()
    for needle in ('60th', '120th', 'seed 149', '0.13%', 'at least two', 'none points against',
                   'session after the report date', 'three quarters', '5 of 5', 'XIU.TO'):
        assert needle in doc, needle
    assert (E.DECISION, E.FINAL, E.SEED, E.BAR, E.PLACEBO_P, E.COST, E.CONFIRM_DAYS) == \
        (60, 120, 149, 3.0, 0.01, 0.13, 5)
    assert E.LAST_ENTRY == dt.time(15, 55) and E.BENCH == 'XIU.TO'
