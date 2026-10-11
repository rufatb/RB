"""The council with memory (day-130 step 3): a shadow on the live council's
table. Registered in PREREGISTER_day130_memory.md."""
import datetime as dt
import json
import types

import pytest

import council as K
import council_memory as M

ET = K.ET
NOW = dt.datetime(2026, 10, 13, 9, 5, tzinfo=ET)


def pick(t, c=0.6, reason='r', inv=None):
    return {'ticker': t, 'confidence': c, 'reason': reason, 'invalid_at': inv}


def desk(longs=(), shorts=(), **kw):
    return {'status': 'READY', 'longs': list(longs), 'shorts': list(shorts), **kw}


def b(*stances, top=()):
    out = []
    for i, s in enumerate(stances, 1):
        st, conv = (s, None) if s == 'ABSTAIN' else (s.split()[0], float(s.split()[1]))
        out.append({'id': 'P%d' % i, 'stance': st, 'conviction': conv, 'argument': 'because'})
    return {'ballots': out, 'top_two': list(top)}


class FakeDeepSeek:
    def __init__(self, replies):
        self.replies, self.seen = list(replies), []
        self.chat = types.SimpleNamespace(completions=self)

    def create(self, **kw):
        self.seen.append(kw)
        msg = types.SimpleNamespace(content=json.dumps(self.replies.pop(0)))
        return types.SimpleNamespace(choices=[types.SimpleNamespace(finish_reason='stop', message=msg)])


class FakeGemini:
    def __init__(self, replies):
        self.replies, self.seen = list(replies), []

    def ask(self, system, user):
        self.seen.append((system, json.loads(user)))
        return self.replies.pop(0), 'gemini-3.8-flash'


def jev_poster(probs):
    def post(body, key, timeout):
        post.body = body
        return {'answers': {'best': {'probabilities': probs}}}
    return post


def claude_post(reply):
    def post(body):
        post.body = body
        return {'choices': [{'message': {'content': json.dumps(reply)}}]}
    return post


LEDGER = [
    # session, side, ticker, r_pct, invalidated
    *[{'session': s, 'model': 'top2', 'kind': 'pick', 'side': side, 'ticker': t, 'r_pct': r,
       'invalidated': inv}
      for s, side, t, r, inv in (('2026-10-01', 'SHORT', 'ELD.TO', '1.2368', ''),
                                 ('2026-10-05', 'SHORT', 'CVE.TO', '-2.1848', ''),
                                 ('2026-10-06', 'SHORT', 'CVE.TO', '-0.169', '0'),
                                 ('2026-10-07', 'LONG', 'CCO.TO', '-1.3282', '1'),
                                 ('2026-10-08', 'SHORT', 'TD.TO', '-0.4149', '0'),
                                 ('2026-10-09', 'LONG', 'TD.TO', '1.3709', '0'),
                                 ('2026-10-13', 'LONG', 'AC.TO', '', ''))],
    {'session': '2026-10-09', 'model': 'deepseek', 'kind': 'selected', 'side': 'LONG',
     'ticker': 'SU.TO', 'r_pct': '-3.0'},
]
LAB = [{'session': '2026-10-07', 'model': 'top2', 'kind': 'pick', 'side': 'LONG', 'ticker': 'CCO.TO',
        'etf': 'XEG.TO', 'r_vs_etf': '-2.4301'}]


def test_the_memory_box_is_the_last_five_recorded_sessions_before_today():
    table = [{'id': 'P1', 'ticker': 'CVE.TO', 'side': 'SHORT'}, {'id': 'P2', 'ticker': 'ZZZ.TO', 'side': 'LONG'}]
    sectors = {'CVE.TO': {'sector': 'Energy', 'industry': 'Oil & Gas Integrated'}}
    m = M.memory('2026-10-13', table, picks=LEDGER, lab=LAB, sectors=sectors)
    assert [x['session'] for x in m['recent']] == ['2026-10-05', '2026-10-06', '2026-10-07',
                                                    '2026-10-08', '2026-10-09']
    cco = m['recent'][2]
    assert cco == {'session': '2026-10-07', 'position': 'LONG CCO.TO', 'r_pct': -1.33, 'result': 'wrong',
                   'wrong_if_hit': True, 'sector_etf': 'XEG.TO', 'sector_part_pct': 1.1,
                   'own_part_pct': -2.43}
    assert 'wrong_if_hit' not in m['recent'][0]           # not recorded: not claimed
    assert m['summary'].startswith('Last 5 recorded sessions: 1 of 5 picks right, mean -0.55%')
    assert m['exposure'][0]['moves_with'] == 'XEG.TO' and m['exposure'][0]['in_effect_a_bet_on'] == 'crude oil'
    assert m['exposure'][1] == {'id': 'P2', 'position': 'LONG ZZZ.TO', 'sector': None, 'moves_with': 'XIU.TO'}
    # a desk pick is not the council's record; today's row is not history
    assert all('SU.TO' not in x['position'] and 'AC.TO' not in x['position'] for x in m['recent'])
    assert M.memory('2026-10-01', table, picks=LEDGER, lab=LAB, sectors={})['summary'] == \
        'No scored Top 2 on the last recorded sessions.'


@pytest.fixture
def sat(tmp_path, monkeypatch):
    """The live council, staged by council.stage itself, as the morning leaves it."""
    snaps = {'claude': desk([pick('AC.TO', 0.62, 'claude', 9.0)]),
             'deepseek': desk([pick('AC.TO', 0.6)], [pick('SU.TO', 0.58)]),
             'gemini': desk([], [pick('SU.TO', 0.61)]),
             'jev': desk(forced_long={'ticker': 'CNQ.TO', 'probability': 0.3})}
    import claude_opportunities as C
    import deepseek_opportunities as O
    import gemini_opportunities as G
    import jev_opportunities as J
    for k, mod in (('claude', C), ('deepseek', O), ('gemini', G), ('jev', J)):
        monkeypatch.setattr(mod, 'load_prepared', lambda root, now, _k=k, **kw: snaps[_k])
    monkeypatch.setattr(K, 'evidence_rows', lambda root, now, tickers: [
        {'ticker': t, 'r0': 1.0} for t in sorted(tickers)])
    ds = FakeDeepSeek([b('ENDORSE 0.7', 'OPPOSE 0.6', 'ENDORSE 0.6'), b('ENDORSE 0.7', 'OPPOSE 0.6', 'OPPOSE 0.7')])
    gm = FakeGemini([b('ENDORSE 0.6', 'ABSTAIN', 'ENDORSE 0.8'), b('ENDORSE 0.65', 'ABSTAIN', 'ENDORSE 0.75')])
    live = K.stage(tmp_path, now=NOW, clients={'deepseek': ds, 'gemini': gm},
                   jev_poster=jev_poster({'P1': 0.5, 'P2': 0.1, 'P3': 0.2, 'NONE': 0.2}),
                   claude_post=claude_post(b('ENDORSE 0.66', 'OPPOSE 0.8', 'ABSTAIN')),
                   wait=False, clock=lambda: NOW)
    assert live['picks'] == ['P1']
    return tmp_path


def test_the_shadow_sits_on_the_live_table_and_only_adds_memory(sat):
    before = {f: (sat/f).read_bytes() for f in (K.SNAPSHOT, K.BRIEF_JSON, K.BRIEF_TXT, K.CLAUDE_BALLOT)}
    ds = FakeDeepSeek([b('ENDORSE 0.7', 'OPPOSE 0.6', 'ENDORSE 0.7'), b('ENDORSE 0.7', 'OPPOSE 0.6', 'ENDORSE 0.7')])
    gm = FakeGemini([b('ENDORSE 0.6', 'ABSTAIN', 'ENDORSE 0.8'), b('ENDORSE 0.6', 'ABSTAIN', 'ENDORSE 0.8')])
    post = jev_poster({'P1': 0.5, 'P2': 0.1, 'P3': 0.3, 'NONE': 0.2})
    cl = claude_post(b('ENDORSE 0.66', 'OPPOSE 0.8', 'ENDORSE 0.6'))
    out = M.stage(sat, now=NOW, clock=lambda: NOW, clients={'deepseek': ds, 'gemini': gm},
                  jev_poster=post, claude_post=cl, picks=LEDGER, lab=LAB, sectors={})
    # the live council's files are untouched, byte for byte
    assert {f: (sat/f).read_bytes() for f in before} == before
    live = json.loads((sat/K.SNAPSHOT).read_text())
    assert out['positions'] == live['positions'] and out['seats'] == live['seats']
    assert out['live_picks'] == ['P1'] and out['rule_version'] == 'day130-memory'
    # every member read the memory box, under its legend, with the frozen prompt
    for system, payload in gm.seen:
        assert payload['memory']['summary'].startswith('Last 5 recorded sessions')
        assert payload['memory_legend'] == M.MEMORY_LEGEND
        assert system in (K.prompt('Gemini', K.ROUND_1), K.prompt('Gemini', K.ROUND_2))
        assert payload['rows'] == json.loads((sat/K.BRIEF_JSON).read_text())['rows']
    assert all('"memory"' in kw['messages'][1]['content'] for kw in ds.seen)
    assert '"memory"' in cl.body['messages'][1]['content']
    assert post.body['state']['memory']['recent'][0]['session'] == '2026-10-05'
    # AC.TO and SU.TO: 4 of 4 endorse with memory (the live council took AC.TO only)
    assert out['status'] == 'READY' and sorted(out['picks']) == ['P1', 'P3']
    assert json.loads((sat/M.SNAPSHOT).read_text())['picks'] == out['picks']


def test_without_memory_the_payload_is_the_live_councils():
    table = [{'id': 'P1', 'ticker': 'AC.TO', 'side': 'LONG', 'lead': 'Claude', 'reason': 'r',
              'invalid_at': None, 'proposers': [{'model': 'claude', 'how': 'selected',
                                                 'confidence': 0.6, 'reason': 'r', 'seat': 'A'}]}]
    gm = FakeGemini([b('ENDORSE 0.6'), b('ENDORSE 0.6')])
    ds = FakeDeepSeek([b('ENDORSE 0.6'), b('ENDORSE 0.6')])
    post = jev_poster({'P1': 0.5, 'NONE': 0.2})
    M.deliberate(table, [{'ticker': 'AC.TO'}], {'today': 'x'}, {'claude': 'A'},
                 clients={'deepseek': ds, 'gemini': gm}, jev_poster=post, live=False)
    assert set(gm.seen[0][1]) == {'positions', 'rows', 'evidence_legend', 'data_dates'}
    assert set(gm.seen[1][1]) == {'positions', 'rows', 'evidence_legend', 'data_dates', 'discussion'}
    assert set(post.body['state']) == {'positions', 'discussion', 'rows'}


def test_it_says_why_it_did_not_sit(tmp_path):
    late = dt.datetime(2026, 10, 13, 9, 30, tzinfo=ET)
    assert M.stage(tmp_path, now=late, clock=lambda: late)['status'] == 'SKIPPED'
    out = M.stage(tmp_path, now=NOW, clock=lambda: NOW)
    assert out['status'] == 'NO_TABLE' and 'UNAVAILABLE' in out['reason']
    assert json.loads((tmp_path/M.SNAPSHOT).read_text())['status'] == 'NO_TABLE'
    assert M.section(out) is None
    assert M.load(tmp_path, NOW)['status'] == 'NO_TABLE'
    assert M.load(tmp_path, NOW + dt.timedelta(days=1)) is None


def test_its_section_takes_the_same_entry_check_and_is_recorded_apart(sat):
    snap = json.loads((sat/K.SNAPSHOT).read_text())
    snap['picks'] = ['P1', 'P3']
    sec = M.section(snap, prices={'AC.TO': 8.0, 'SU.TO': 30.0})    # AC.TO long, wrong if 9.0 → VOID
    assert [p['ticker'] for p in sec['picks']] == ['SU.TO'] and sec['shadow']
    assert sec['rule_version'].startswith('day130-memory+')
    import model_picks
    rows = model_picks.rows_from_report({'session': '2026-10-13', 'intraday': {'top_two_memory': sec}})
    got = [(r['model'], r['kind'], r['side'], r['ticker'], r['prompt_version']) for r in rows]
    assert got == [('top2memory', 'pick', 'SHORT', 'SU.TO', sec['rule_version'])]


def test_the_paired_readout_and_the_review_section():
    rows = [{'session': '2026-10-13', 'model': 'top2', 'kind': 'pick', 'side': 'LONG', 'ticker': 'AC.TO', 'r_pct': '1.0'},
            {'session': '2026-10-13', 'model': 'top2memory', 'kind': 'pick', 'side': 'SHORT', 'ticker': 'SU.TO', 'r_pct': '-0.5'},
            {'session': '2026-10-14', 'model': 'top2memory', 'kind': 'pick', 'side': 'SHORT', 'ticker': 'SU.TO', 'r_pct': ''},
            {'session': '2026-10-15', 'model': 'top2', 'kind': 'pick', 'side': 'LONG', 'ticker': 'AC.TO', 'r_pct': '0.4'},
            {'session': '2026-10-15', 'model': 'top2memory', 'kind': 'pick', 'side': 'LONG', 'ticker': 'AC.TO', 'r_pct': '0.4'}]
    c = M.comparison(rows)
    assert c['days'] == 2 and c['same_days'] == 1 and c['mean_d'] == -0.75     # 10-14 is not scored yet
    report = {'intraday': {'top_two': {'picks': [{'side': 'LONG', 'ticker': 'AC.TO'}]},
                           'top_two_memory': {'picks': []}}}
    lines = M.review_lines('2026-10-15', report, rows)
    assert lines[2] == 'Today: live LONG AC.TO; with memory no pick.'
    assert 'memory − live -0.75% per session' in lines[3]
    import daily_review
    assert 'unavailable (RuntimeError)' in daily_review.memory_section(
        '2026-10-15', report, lines=lambda s, r: (_ for _ in ()).throw(RuntimeError('x')))


def test_the_control_table_is_the_planted_universe():
    import deepseek_opportunities as O
    table, rows = M.control_table('2026-09-17')
    assert [(p['side'], p['ticker']) for p in table[:2]] == [('LONG', O.CONTROL_LONG), ('SHORT', O.CONTROL_SHORT)]
    assert [r['ticker'] for r in rows] == [p['ticker'] for p in table]
    mem = M.control_memory(table)
    assert mem['summary'].startswith('Last 5 recorded sessions: 0 of 5')
    assert 'CONTROL' not in json.dumps(mem) and 'SYNTHETIC' not in json.dumps(rows).upper()
