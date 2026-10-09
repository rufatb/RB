"""The council (day-124): the four models deliberate on the Top 2. The rule,
the ballots and the two rounds are registered in PREREGISTER_day124_council.md."""
import datetime as dt
import json
import types

import pytest

import council as K

ET = K.ET
NOW = dt.datetime(2026, 10, 5, 9, 25, tzinfo=ET)


def pick(t, c=0.6, reason='r', inv=None):
    return {'ticker': t, 'confidence': c, 'reason': reason, 'invalid_at': inv}


def desk(longs=(), shorts=(), **kw):
    return {'status': 'READY', 'longs': list(longs), 'shorts': list(shorts), **kw}


def test_registered_prompt_is_the_frozen_text():
    reg = open('PREREGISTER_day124_council.md').read()
    text = K.prompt('{member}', '{round_note}')
    for para in text.split('\n\n'):
        assert para in reg
    assert K.ROUND_1 in reg.replace('\n', ' ')
    assert 'Return JSON only: {"ballots"' in K.prompt('Gemini', K.ROUND_1)


def test_positions_are_every_selection_plus_jevs_forced_picks():
    table = K.positions(desk([pick('AC.TO', 0.7, 'claude says', 10.0)]),
                        desk([pick('AC.TO', 0.6, 'deepseek says')], [pick('SU.TO')]),
                        {'status': 'UNAVAILABLE'},
                        desk(forced_long={'ticker': 'AC.TO', 'probability': 0.4},
                             forced_short={'ticker': 'CNQ.TO', 'probability': 0.5}))
    got = [(p['id'], p['side'], p['ticker'], [x['model'] for x in p['proposers']]) for p in table]
    assert got == [('P1', 'LONG', 'AC.TO', ['claude', 'deepseek', 'jev']),
                   ('P2', 'SHORT', 'CNQ.TO', ['jev']),
                   ('P3', 'SHORT', 'SU.TO', ['deepseek'])]
    assert table[0]['lead'] == 'Claude' and table[0]['reason'] == 'claude says'
    assert table[0]['invalid_at'] == 10.0
    assert table[0]['proposers'][2]['how'] == 'forced'


def b(*stances, top=()):
    """A ballot reply over P1.. in order."""
    out = []
    for i, s in enumerate(stances, 1):
        st, conv = (s, None) if s == 'ABSTAIN' else (s.split()[0], float(s.split()[1]))
        out.append({'id': 'P%d' % i, 'stance': st, 'conviction': conv, 'argument': 'because'})
    return {'ballots': out, 'top_two': list(top)}


def test_a_ballot_must_vote_on_every_position():
    assert K.parse_ballot(b('ENDORSE 0.7', 'ABSTAIN', top=['P1']), ['P1', 'P2'])['top_two'] == ['P1']
    with pytest.raises(ValueError, match='P2'):
        K.parse_ballot(b('ENDORSE 0.7'), ['P1', 'P2'])
    with pytest.raises(ValueError):    # conviction outside 0.5–1 is no vote
        K.parse_ballot(b('ENDORSE 0.3'), ['P1'])
    out = K.parse_ballot({'ballots': [{'id': 'P1', 'stance': 'oppose', 'conviction': 0.9,
                                       'argument': 'x' * 500}], 'top_two': ['P1', 'P1', 'P9', 'P2']},
                         ['P1'])
    assert out['votes']['P1']['stance'] == 'OPPOSE' and len(out['votes']['P1']['argument']) == 200
    assert out['top_two'] == ['P1']


def table_of(*specs):
    return [{'id': 'P%d' % i, 'ticker': t, 'side': s} for i, (t, s) in enumerate(specs, 1)]


def ballot(**votes):
    top = votes.pop('top', [])
    return {'votes': {k: ({'stance': v.split()[0], 'conviction': float(v.split()[1])}
                          if ' ' in v else {'stance': v, 'conviction': None})
                      for k, v in votes.items()}, 'top_two': top}


def test_consensus_needs_most_of_the_room_and_at_most_one_objection():
    t = table_of(('AC.TO', 'LONG'), ('SU.TO', 'SHORT'), ('CNQ.TO', 'LONG'))
    finals = {'Claude': ballot(P1='ENDORSE 0.7', P2='ENDORSE 0.6', P3='ENDORSE 0.9', top=['P1']),
              'DeepSeek': ballot(P1='ENDORSE 0.8', P2='OPPOSE 0.7', P3='OPPOSE 0.6', top=['P1']),
              'Gemini': ballot(P1='ABSTAIN', P2='ENDORSE 0.55', P3='OPPOSE 0.8'),
              'Jev': None}
    out = K.tally(t, finals)
    by = {r['ticker']: r for r in out['rows']}
    assert out['members'] == ['Claude', 'DeepSeek', 'Gemini'] and out['absent'] == ['Jev']
    # 2 of 3 endorse, 0 object → consensus; 2 of 3 endorse, 1 objects → consensus
    assert by['AC.TO']['consensus'] and by['SU.TO']['consensus']
    # 1 endorse, 2 object → no
    assert not by['CNQ.TO']['consensus']
    # ranked by seats first
    assert [r['ticker'] for r in out['rows']][:2] == ['AC.TO', 'SU.TO']
    assert by['SU.TO']['weakest'] == 0.55          # the weakest supporter, never an average


def test_two_of_four_is_not_most_of_the_room():
    t = table_of(('AC.TO', 'LONG'))
    finals = {m: ballot(P1='ENDORSE 0.7' if m in ('Claude', 'Gemini') else 'ABSTAIN')
              for m in K.MEMBERS}
    assert not K.tally(t, finals)['rows'][0]['consensus']
    finals['Jev'] = ballot(P1='ENDORSE 0.6')
    assert K.tally(t, finals)['rows'][0]['consensus']
    finals['DeepSeek'] = ballot(P1='OPPOSE 0.9')     # 3 endorse, 1 object of 4 → still yes
    assert K.tally(t, finals)['rows'][0]['consensus']


def test_a_lone_member_is_no_council():
    t = table_of(('AC.TO', 'LONG'))
    assert not K.tally(t, {'Claude': ballot(P1='ENDORSE 0.9')})['rows'][0]['consensus']


def test_both_sides_agreed_takes_neither():
    t = table_of(('AC.TO', 'LONG'), ('AC.TO', 'SHORT'))
    finals = {m: ballot(P1='ENDORSE 0.7', P2='ENDORSE 0.7') for m in ('Claude', 'DeepSeek', 'Gemini')}
    rows = K.tally(t, finals)['rows']
    assert not any(r['consensus'] for r in rows) and all(r.get('split') for r in rows)


def test_ranking_tie_break_is_the_weakest_endorser_not_the_mean():
    t = table_of(('AAA.TO', 'LONG'), ('BBB.TO', 'LONG'))
    # AAA: 0.95 and 0.55 (mean 0.75); BBB: 0.7 and 0.7 (mean 0.70). Weakest wins → BBB first.
    finals = {'Claude': ballot(P1='ENDORSE 0.95', P2='ENDORSE 0.7'),
              'DeepSeek': ballot(P1='ENDORSE 0.55', P2='ENDORSE 0.7')}
    assert [r['ticker'] for r in K.tally(t, finals)['rows']] == ['BBB.TO', 'AAA.TO']


# ── the staged rounds, with fake members ────────────────────────────────────

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
        r = self.replies.pop(0)
        if isinstance(r, Exception):
            raise r
        return r, 'gemini-3.8-flash'


def jev_poster(probs):
    def post(body, key, timeout):
        post.body = body
        return {'answers': {'best': {'probabilities': probs}}}
    return post


@pytest.fixture
def staged(tmp_path, monkeypatch):
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
    return tmp_path


def test_two_rounds_then_a_tally(staged):
    # P1 LONG AC.TO, P2 LONG CNQ.TO, P3 SHORT SU.TO
    ds = FakeDeepSeek([b('ENDORSE 0.7', 'OPPOSE 0.6', 'ENDORSE 0.6', top=['P1']),
                       b('ENDORSE 0.7', 'OPPOSE 0.6', 'OPPOSE 0.7', top=['P1'])])
    gm = FakeGemini([b('ENDORSE 0.6', 'ABSTAIN', 'ENDORSE 0.8', top=['P3']),
                     b('ENDORSE 0.65', 'ABSTAIN', 'ENDORSE 0.75', top=['P1', 'P3'])])
    post = jev_poster({'P1': 0.5, 'P2': 0.1, 'P3': 0.2, 'NONE': 0.2})
    # Claude's ballot is sealed while staging waits
    calls = []

    def sleep(_):
        calls.append(1)
        K.seal_ballot(staged, b('ENDORSE 0.66', 'OPPOSE 0.8', 'ABSTAIN', top=['P1']), now=NOW)

    out = K.stage(staged, now=NOW, clients={'deepseek': ds, 'gemini': gm}, jev_poster=post,
                  sleep=sleep, clock=lambda: NOW)
    assert calls == [1]
    assert [p['ticker'] for p in out['positions']] == ['AC.TO', 'CNQ.TO', 'SU.TO']
    # round 1 is blind; round 2 reads every member's ballot
    assert 'discussion' not in gm.seen[0][1]
    seat = K.seats('2026-10-05')
    assert [d['seat'] for d in gm.seen[1][1]['discussion']] == sorted(seat.values())
    assert K.ROUND_2 in gm.seen[1][0] and 'You are one of the four members.' in gm.seen[1][0]
    # no member is named to another: not in the prompt, the payload or Jev's options
    for name in ('Claude', 'DeepSeek', 'Gemini', 'Jev'):
        assert name not in gm.seen[1][0] and name not in json.dumps(gm.seen[1][1])
        assert name not in json.dumps(post.body)
    assert 'Claude' not in (staged/K.BRIEF_TXT).read_text().split('=' * 72)[1]
    assert ds.seen[0]['extra_body'] == {'thinking': {'type': 'disabled'}}
    # Jev endorsed P1 only (0.5 > NONE 0.2); P3 at 0.2 is not above NONE
    assert out['rounds']['jev']['votes']['P1']['stance'] == 'ENDORSE'
    assert out['rounds']['jev']['votes']['P3']['stance'] == 'ABSTAIN'
    # AC.TO: 4 of 4 endorse. SU.TO: Gemini endorse, DeepSeek oppose (changed mind) → no.
    assert out['status'] == 'READY' and out['picks'] == ['P1']
    assert out['tally']['members'] == ['Claude', 'DeepSeek', 'Gemini', 'Jev']
    saved = json.loads((staged/K.SNAPSHOT).read_text())
    assert saved['picks'] == ['P1'] and saved['prompt_version'] == K.PROMPT_VERSION


def test_a_failed_member_is_absent_and_named_and_round_two_keeps_round_one(staged):
    ds = FakeDeepSeek([b('ENDORSE 0.7', 'ABSTAIN', 'ENDORSE 0.6'), {'nonsense': 1}])
    gm = FakeGemini([ValueError('HTTP_503'), ValueError('HTTP_503')])
    post = jev_poster({'P1': 0.5, 'P2': 0.1, 'P3': 0.3, 'NONE': 0.2})
    out = K.stage(staged, now=NOW, clients={'deepseek': ds, 'gemini': gm}, jev_poster=post,
                  wait=False, clock=lambda: NOW)
    assert out['errors']['R1 Gemini'] == 'HTTP_503' and out['errors']['Claude'].startswith('no ballot')
    assert out['errors']['R2 DeepSeek'].startswith('kept its round-1 ballot')
    assert out['tally']['members'] == ['DeepSeek', 'Jev']
    # 2 of 2 endorse AC.TO and SU.TO: both reach consensus
    assert out['status'] == 'READY' and len(out['picks']) == 2


def test_no_positions_is_said_and_asks_nobody(tmp_path, monkeypatch):
    import claude_opportunities as C
    import deepseek_opportunities as O
    import gemini_opportunities as G
    import jev_opportunities as J
    for mod in (C, O, G, J):
        monkeypatch.setattr(mod, 'load_prepared', lambda root, now, **kw: desk())
    out = K.stage(tmp_path, now=NOW, clients={'deepseek': None, 'gemini': None}, wait=False)
    assert out['status'] == 'NO_POSITIONS'
    assert K.load(tmp_path, NOW)['status'] == 'NO_POSITIONS'
    assert K.wait_ballot(tmp_path, 0, now_fn=lambda: NOW) == 3


def test_claudes_ballot_is_checked_sealed_once_and_closed_at_the_hard_stop(tmp_path):
    K._write(tmp_path/K.BRIEF_JSON, {'session': '2026-10-05', 'ids': ['P1']})
    assert K.wait_ballot(tmp_path, 0, now_fn=lambda: NOW) == 0
    assert K.check_ballot(tmp_path, b('ENDORSE 0.2'), now=NOW)
    assert K.check_ballot(tmp_path, b('ENDORSE 0.7'), now=NOW) == []
    assert K.seal_ballot(tmp_path, b('ENDORSE 0.7'), now=NOW)
    with pytest.raises(ValueError, match='ALREADY_SEALED'):
        K.seal_ballot(tmp_path, b('OPPOSE 0.7'), now=NOW)
    assert K.read_claude_ballot(tmp_path, '2026-10-05', ['P1'])['votes']['P1']['stance'] == 'ENDORSE'
    with pytest.raises(ValueError, match='CLOSED'):
        K.seal_ballot(tmp_path, b('ENDORSE 0.7'), now=NOW.replace(hour=9, minute=40))
    assert K.wait_ballot(tmp_path, 0, now_fn=lambda: NOW.replace(minute=27)) == 3


def test_wait_ballot_says_still_waiting_without_a_brief(tmp_path):
    assert K.wait_ballot(tmp_path, 0, now_fn=lambda: NOW, sleep=lambda s: None) == 2


def council_snap():
    t = [{'id': 'P1', 'ticker': 'AC.TO', 'side': 'LONG', 'lead': 'Claude', 'reason': 'r',
          'invalid_at': 30.0, 'proposers': []},
         {'id': 'P2', 'ticker': 'SU.TO', 'side': 'SHORT', 'lead': 'DeepSeek', 'reason': 's',
          'invalid_at': 50.0, 'proposers': []},
         {'id': 'P3', 'ticker': 'CNQ.TO', 'side': 'LONG', 'lead': 'Jev', 'reason': 'q',
          'invalid_at': None, 'proposers': []}]
    finals = {'Claude': ballot(P1='ENDORSE 0.7', P2='ENDORSE 0.6', P3='ENDORSE 0.6', top=['P1']),
              'DeepSeek': ballot(P1='ENDORSE 0.8', P2='ENDORSE 0.7', P3='OPPOSE 0.6'),
              'Gemini': ballot(P1='OPPOSE 0.6', P2='ENDORSE 0.6', P3='OPPOSE 0.6')}
    tal = K.tally(t, finals)
    return {'status': 'READY', 'session': '2026-10-05', 'positions': t, 'tally': tal,
            'picks': [r['id'] for r in tal['rows'] if r['consensus']][:2]}


def test_top_two_carries_the_room_and_the_entry_check_still_applies():
    snap = council_snap()
    sec = K.top_two(snap)
    assert [(p['side'], p['ticker']) for p in sec['picks']] == [('LONG', 'AC.TO'), ('SHORT', 'SU.TO')]
    assert sec['picks'][0]['verdict'] == '2 of 3 endorse, 1 object; named best by 1'
    assert sec['picks'][1]['agreement'] == '3 of 3 endorse'
    assert sec['status'] == 'READY' and sec['rule_version'] == K.RULE_VERSION
    assert sec['near'][0]['ticker'] == 'CNQ.TO'
    # AC.TO already below its 30.0 "wrong if" at 09:46 → dropped and listed
    sec = K.top_two(snap, prices={'AC.TO': 29.0, 'SU.TO': 49.0})
    assert [p['ticker'] for p in sec['picks']] == ['SU.TO'] and sec['void_at_entry'] == ['LONG AC.TO']
    assert sec['status'] == 'PARTIAL' and sec['rule_version'].endswith('+day120-entry')
    lines = K.council_lines(sec)
    assert lines[0].startswith('Council on SHORT SU.TO: Claude endorse 0.60')


def test_no_consensus_lists_the_near_misses():
    snap = council_snap()
    snap['picks'], snap['status'] = [], 'NO_CONSENSUS'
    sec = K.top_two(snap)
    assert sec['picks'] == [] and sec['status'] == 'NO_AGREEMENT'
    assert 'No consensus today' in sec['reason']


def test_the_jev_ballot_endorses_only_above_its_own_none():
    t = table_of(('AC.TO', 'LONG'), ('SU.TO', 'SHORT'))
    for p in t:
        p['proposers'] = [{'model': 'deepseek', 'how': 'selected', 'confidence': .6, 'reason': 'r'}]
    post = jev_poster({'P1': 0.45, 'P2': 0.25, 'NONE': 0.3})
    out = K.ask_jev(t, [], [], poster=post)
    assert out['votes']['P1'] == {'stance': 'ENDORSE', 'conviction': 0.45,
                                  'argument': 'rated 0.45 against its "none" 0.30'}
    assert out['votes']['P2']['stance'] == 'ABSTAIN' and out['top_two'] == ['P1']
    assert set(post.body['questions']['best']['criteria']) == {'P1', 'P2', 'NONE'}


# ── the council in the Top 2 everywhere ─────────────────────────────────────

def counted():
    return {'picks': [{'ticker': 'AC.TO', 'side': 'LONG', 'agreement': '2 of 4', 'confidence': .6,
                       'lead': 'Claude', 'reason': 'r', 'backing': ['Claude 0.60', 'DeepSeek 0.60'],
                       'votes': 2, 'split': False}],
            'status': 'PARTIAL', 'answered': ['Claude', 'DeepSeek'], 'rule_version': 'day121-agreement',
            'single': []}


def test_the_council_decides_and_the_counted_rule_is_the_fallback():
    import top_picks
    sec = K.decide(counted(), council_snap())
    assert sec['council'] and [p['ticker'] for p in sec['picks']] == ['AC.TO', 'SU.TO']
    text = '\n'.join(top_picks.table(sec, concise=True))
    assert "the council's decision" in text and 'Sat: Claude, DeepSeek, Gemini; absent: Jev.' in text
    assert '| 1 | LONG AC.TO | 2 of 3 endorse, 1 object; named best by 1 |' in text
    assert 'Council on LONG AC.TO: Claude endorse 0.70' in text
    assert 'Short of consensus: LONG CNQ.TO (1 of 3 endorse).' in text
    fall = K.decide(counted(), {'status': 'UNAVAILABLE', 'reason': 'the council was not staged this morning'})
    assert not fall.get('council') and fall['picks'][0]['ticker'] == 'AC.TO'
    assert 'The council did not sit today (the council was not staged this morning)' in \
        '\n'.join(top_picks.table(fall, concise=True))


def snap_of(finals):
    """council_snap's three positions, sealed from `finals` by the real tally."""
    s = council_snap()
    s['tally'] = K.tally(s['positions'], finals)
    s['picks'] = [r['id'] for r in s['tally']['rows'] if r['consensus']][:2]
    s['status'] = 'READY' if s['picks'] else 'NO_CONSENSUS'
    return s


# Every position drew at least as many objections as endorsements: no runner-up.
TURNED_DOWN = {'Claude': ballot(P1='ENDORSE 0.7', P2='ENDORSE 0.6', P3='ENDORSE 0.6'),
               'DeepSeek': ballot(P1='OPPOSE 0.8', P2='OPPOSE 0.7', P3='OPPOSE 0.6'),
               'Gemini': ballot(P1='OPPOSE 0.6', P2='ABSTAIN', P3='OPPOSE 0.6')}
# LONG AC.TO agreed 3 of 3; SHORT SU.TO one endorsement, no objection; LONG CNQ.TO turned down.
ONE_AND_A_RUNNER_UP = {'Claude': ballot(P1='ENDORSE 0.7', P2='ENDORSE 0.6', P3='ENDORSE 0.6'),
                       'DeepSeek': ballot(P1='ENDORSE 0.8', P2='ABSTAIN', P3='OPPOSE 0.6'),
                       'Gemini': ballot(P1='ENDORSE 0.6', P2='ABSTAIN', P3='OPPOSE 0.6')}


def test_the_hero_names_the_closest_positions_on_a_no_consensus_day():
    import email_render as E
    sec = K.decide(counted(), snap_of(TURNED_DOWN))
    assert sec['picks'] == [] and sec['runner_up'] is None
    html = E._hero({'intraday': {'top_two': sec, 'desks': [{}]}})
    assert 'no council consensus — closest: SHORT SU.TO (1 of 3 endorse) · LONG AC.TO' in html


# ── day-129: the runner-up and the repeat flag ──────────────────────────────

def test_with_one_pick_the_runner_up_is_shown_labelled_and_is_never_a_pick():
    import email_render as E
    import top_picks
    sec = K.decide(counted(), snap_of(ONE_AND_A_RUNNER_UP))
    assert [p['ticker'] for p in sec['picks']] == ['AC.TO'] and sec['status'] == 'PARTIAL'
    ru = sec['runner_up']
    assert (ru['side'], ru['ticker'], ru['label'], ru['runner_up']) == ('SHORT', 'SU.TO', 'no consensus', True)
    assert [x['ticker'] for x in sec['near']] == ['CNQ.TO']        # not listed twice
    line = K.runner_up_line(sec)
    assert line == ('Runner-up — no consensus, not a council pick: SHORT SU.TO (1 of 3 endorse); '
                    'wrong if above 50. DeepSeek: s')
    text = '\n'.join(top_picks.table(sec, concise=True))
    assert line in text and '| 2 |' not in text                     # never a row of the table
    assert 'Top 2 today: LONG AC.TO (3 of 3 endorse) · runner-up, no consensus: SHORT SU.TO ' \
           '(1 of 3 endorse)' in E._hero({'intraday': {'top_two': sec, 'desks': [{}]}})


def test_a_runner_up_needs_more_endorsements_than_objections_and_must_still_stand():
    sec = K.top_two(snap_of(TURNED_DOWN))
    assert sec['runner_up'] is None
    assert sec['runner_up_note'] == ('No runner-up: every other position drew at least as many '
                                     'objections as endorsements.')
    # SU.TO qualifies on the votes, but at 09:46 it is already above its own 50.0
    sec = K.top_two(snap_of(ONE_AND_A_RUNNER_UP), prices={'AC.TO': 31.0, 'SU.TO': 51.0})
    assert [p['ticker'] for p in sec['picks']] == ['AC.TO'] and sec['runner_up'] is None
    assert sec['runner_up_note'] == ('No runner-up: the other positions with more endorsements than '
                                     'objections cannot stand — SHORT SU.TO (past its own "wrong if" '
                                     'at 09:46).')
    # the other side of a picked ticker is never the runner-up
    snap = snap_of(ONE_AND_A_RUNNER_UP)
    snap['positions'][1]['ticker'] = snap['tally']['rows'][1]['ticker'] = 'AC.TO'
    assert K.top_two(snap)['runner_up'] is None


def test_an_agreed_position_below_a_void_pick_is_the_runner_up_and_says_it_agreed():
    import email_render as E
    import top_picks
    finals = {m: ballot(P1='ENDORSE 0.7', P2='ENDORSE 0.6', P3='ENDORSE 0.6', top=['P1', 'P2'])
              for m in ('Claude', 'DeepSeek', 'Gemini')}
    snap = snap_of(finals)                 # all three agreed; the council chose AC.TO and SU.TO
    assert [r['ticker'] for r in snap['tally']['rows'] if r['consensus']] == ['AC.TO', 'SU.TO', 'CNQ.TO']
    sec = K.top_two(snap, prices={'AC.TO': 29.0, 'SU.TO': 49.0, 'CNQ.TO': 20.0})
    assert [p['ticker'] for p in sec['picks']] == ['SU.TO'] and sec['void_at_entry'] == ['LONG AC.TO']
    assert sec['runner_up']['ticker'] == 'CNQ.TO'
    assert sec['runner_up']['label'] == 'agreed, ranked below the picks'
    assert sec['reason'].startswith('One position the council chose was already past its own "wrong if"')
    assert 'Runner-up — agreed, ranked below the picks, not a council pick: LONG CNQ.TO' in \
        '\n'.join(top_picks.table(sec, concise=True))
    # both chosen positions void: the hero never says "no consensus" over an agreed runner-up
    sec = K.top_two(snap, prices={'AC.TO': 29.0, 'SU.TO': 51.0, 'CNQ.TO': 20.0})
    assert sec['picks'] == [] and sec['reason'].startswith("The council's positions were already past")
    html = E._hero({'intraday': {'top_two': sec, 'desks': [{}]}})
    assert 'Top 2 today: no council pick — runner-up, agreed, ranked below the picks: LONG CNQ.TO' in html
    assert 'No council pick survived the 09:46 entry check.' in '\n'.join(top_picks.table(sec, concise=True))


def test_a_repeat_of_the_previous_sessions_top_two_is_flagged_with_its_result():
    import top_picks
    rows = [{'session': '2026-10-01', 'model': 'top2', 'kind': 'pick', 'side': 'LONG', 'ticker': 'SU.TO',
             'r_pct': '0.5'},
            {'session': '2026-10-02', 'model': 'top2', 'kind': 'pick', 'side': 'SHORT', 'ticker': 'AC.TO',
             'r_pct': '-0.4149'},
            {'session': '2026-10-02', 'model': 'top2runner', 'kind': 'pick', 'side': 'LONG',
             'ticker': 'SU.TO', 'r_pct': ''},
            {'session': '2026-10-05', 'model': 'top2', 'kind': 'pick', 'side': 'LONG', 'ticker': 'SU.TO',
             'r_pct': ''}]
    prev = K.previous_top2('2026-10-05', rows)      # the last session BEFORE today, Top 2 rows only
    assert prev == {'AC.TO': {'session': '2026-10-02', 'side': 'SHORT', 'r_pct': -0.4149, 'hit': None}}
    sec = K.top_two(council_snap(), previous=prev)
    assert sec['picks'][0]['repeat']['session'] == '2026-10-02' and 'repeat' not in sec['picks'][1]
    line = K.repeat_line(sec['picks'][0])
    assert line == ("LONG AC.TO was also the previous session's Top 2 (2026-10-02): SHORT AC.TO, wrong, "
                    "-0.41% from 09:45 to the close.")
    assert line in '\n'.join(top_picks.table(sec, concise=True))
    unscored = {'side': 'LONG', 'ticker': 'TD.TO', 'repeat': {'session': '2026-10-08', 'side': 'SHORT',
                                                               'r_pct': None}}
    assert K.repeat_line(unscored).endswith(': SHORT TD.TO, not scored yet.')
    assert K.repeat_line({'side': 'LONG', 'ticker': 'TD.TO'}) is None


def test_the_repeat_lookup_reads_the_record_and_a_missing_one_flags_nothing(tmp_path, monkeypatch):
    import model_picks as M
    path = tmp_path/'picks.csv'
    M.write([{'session': '2026-10-08', 'model': 'top2', 'kind': 'pick', 'side': 'SHORT',
              'ticker': 'TD.TO', 'r_pct': -0.4149, 'hit': False}], path)
    monkeypatch.setattr(K, 'PREVIOUS_LEDGER', path)
    assert K.previous_top2('2026-10-09')['TD.TO']['r_pct'] == -0.4149
    assert K.previous_top2('2026-10-08') == {}                   # never today's own rows
    monkeypatch.setattr(K, 'PREVIOUS_LEDGER', tmp_path/'missing.csv')
    assert K.previous_top2('2026-10-09') == {}


def test_each_pick_says_who_proposed_it_and_how():
    import top_picks
    snap = snap_of(ONE_AND_A_RUNNER_UP)
    snap['positions'][0]['proposers'] = [{'model': 'gemini', 'how': 'selected'},
                                         {'model': 'claude', 'how': 'nominated'},
                                         {'model': 'jev', 'how': 'forced'}]
    sec = K.top_two(snap)
    line = 'Proposed: LONG AC.TO by Gemini (selected), Claude (nominated), Jev (forced).'
    assert K.proposed_line(sec['picks']) == line
    assert line in '\n'.join(top_picks.table(sec, concise=True))
    assert K.proposed_line([{'side': 'LONG', 'ticker': 'AC.TO'}]) is None     # an older section


def test_an_unreadable_record_costs_the_repeat_flag_only_and_says_so(monkeypatch):
    import top_picks

    def broken(session, rows=None):
        raise RuntimeError('disk')
    monkeypatch.setattr(K, 'previous_top2', broken)
    sec = K.top_two(council_snap())
    assert len(sec['picks']) == 2 and not any('repeat' in p for p in sec['picks'])
    assert 'The repeat check could not read the record (RuntimeError).' in \
        '\n'.join(top_picks.table(sec, concise=True))


def test_the_runner_up_is_recorded_as_its_own_shadow_never_as_top2_or_on_the_board():
    import model_picks
    import primary_board
    sec = K.decide(counted(), snap_of(ONE_AND_A_RUNNER_UP))
    rows = model_picks.rows_from_report({'session': '2026-10-05', 'intraday': {'top_two': sec}})
    got = sorted((r['model'], r['side'], r['ticker'], r['agreement']) for r in rows)
    assert got == [('top2', 'LONG', 'AC.TO', '3 of 3 endorse'),
                   ('top2runner', 'SHORT', 'SU.TO', '1 of 3 endorse')]
    assert 'top2runner_pick' not in dict(primary_board.LEADERBOARD)


def test_the_page_prints_the_runner_up_and_the_repeat_as_the_email_does():
    import report_page
    prev = {'AC.TO': {'session': '2026-10-02', 'side': 'SHORT', 'r_pct': -0.4149, 'hit': None}}
    sec = K.top_two(snap_of(ONE_AND_A_RUNNER_UP), previous=prev)
    html = report_page._top_two_section({'top_two': sec})
    assert 'Runner-up — no consensus, not a council pick: SHORT SU.TO' in html
    assert 'LONG AC.TO was also the previous session' in html
    assert html.count('<tr class="reason">') == 1                  # one pick row, never two


def test_the_evening_review_scores_the_runner_up_apart_from_the_top_two():
    import daily_review
    sec = K.decide(counted(), snap_of(ONE_AND_A_RUNNER_UP))
    got = [(x['section'], x['ticker']) for x in daily_review.picks_of({'intraday': {'top_two': sec}})]
    assert ('Top 2', 'AC.TO') in got and ('Runner-up (not a pick)', 'SU.TO') in got


def test_the_counted_rule_is_recorded_as_a_shadow_and_the_council_as_top2():
    import model_picks
    sec = K.decide(counted(), council_snap())
    rows = model_picks.rows_from_report({'session': '2026-10-05', 'intraday': {
        'top_two': sec, 'top_two_counted': counted()}})
    got = sorted((r['model'], r['ticker'], r['prompt_version']) for r in rows)
    assert got == [('top2', 'AC.TO', 'day124-council+day129-nominations'),
                   ('top2', 'SU.TO', 'day124-council+day129-nominations'),
                   ('top2count', 'AC.TO', 'day121-agreement')]


def test_a_council_only_day_does_not_say_nothing_to_act_on():
    import email_render as E
    import prepare_delivery
    report = {'intraday': {'desks': [{'id': 'claude', 'legs': []}],
                           'top_two': K.decide(counted(), council_snap())}}
    assert prepare_delivery.subject_state(report).startswith('COUNCIL TOP 2 ONLY — 2 positions')
    assert 'the council agreed on the Top 2' in E._hero(report)
    assert K._clip('one two three', 9) == 'one two…'


def test_no_model_leads_seats_and_the_lead_rotate_by_day():
    days = ['2026-10-%02d' % d for d in range(5, 31)]
    firsts = {K.lead_order(d)[0] for d in days}
    assert firsts == {'claude', 'deepseek', 'gemini'}          # each leads on some day
    assert all(K.lead_order(d)[-1] == 'jev' for d in days)      # no reasons, no levels
    assert K.seats('2026-10-05') == K.seats('2026-10-05')       # reproducible
    assert sorted(K.seats('2026-10-05').values()) == ['A', 'B', 'C', 'D']
    assert K.lead_order(None) == K.LEAD_ORDER                    # old publications unchanged


def test_the_counted_top_two_lead_rotates_too():
    import top_picks
    a = desk([pick('AC.TO', 0.6, 'claude reason', 10.0)])
    b_ = desk([pick('AC.TO', 0.6, 'deepseek reason', 11.0)])
    g = desk([pick('AC.TO', 0.6, 'gemini reason', 12.0)])
    leads = {top_picks.select(a, b_, {'status': 'UNAVAILABLE'}, gemini=g,
                              session='2026-10-%02d' % d)['picks'][0]['lead'] for d in range(5, 31)}
    assert leads == {'Claude', 'DeepSeek', 'Gemini'}
