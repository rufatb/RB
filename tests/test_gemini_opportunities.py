"""The Gemini desk (owner, 2026-10-03): DeepSeek's question, rows, prompt and
validator, answered by gemini-3.8-flash and sealed like every other desk."""
import datetime as dt
import json
from pathlib import Path

import pytest

import deepseek_opportunities as O
import gemini_opportunities as G
import top_picks

ET = G.ET
NOW = dt.datetime(2026, 10, 5, 9, 10, tzinfo=ET)


class Resp:
    def __init__(self, status, data):
        self.status_code, self._data = status, data

    def json(self):
        return self._data


class Session:
    """Answers like generateContent; records what it was sent."""
    def __init__(self, reply=None, *, status=200, finish='STOP', thought=True):
        self.reply, self.status, self.finish, self.thought = reply, status, finish, thought
        self.sent = []

    def post(self, url, headers=None, json=None, timeout=None):
        self.sent.append({'url': url, 'headers': headers, 'json': json})
        parts = ([{'text': 'scratch', 'thought': True}] if self.thought else []) + \
            [{'text': __import__('json').dumps(self.reply)}]
        return Resp(self.status, {'candidates': [{'finishReason': self.finish,
                                                  'content': {'parts': parts}}],
                                  'modelVersion': 'gemini-3.8-flash'})


def client(reply, **kw):
    s = Session(reply, **kw)
    return G.GeminiClient('k', session=s), s


def test_it_asks_deepseeks_exact_question_in_json_mode_with_low_thinking():
    c, s = client({'longs': [{'ticker': O.CONTROL_LONG, 'confidence': 0.7, 'reason': 'r0 2.9',
                              'basis': 'technical'}], 'shorts': []})
    out = G.rank(O.control_universe(), client=c, now=NOW)
    sent = s.sent[0]
    assert sent['url'].endswith('/models/gemini-3.8-flash:generateContent')
    assert sent['headers'] == {'x-goog-api-key': 'k'}
    body = sent['json']
    assert body['systemInstruction']['parts'][0]['text'] == O.SYSTEM_PROMPT == G.SYSTEM_PROMPT
    assert json.loads(body['contents'][0]['parts'][0]['text']) == \
        O.build_request(O.control_universe(), None, NOW)['payload']
    assert body['generationConfig']['responseMimeType'] == 'application/json'
    assert body['generationConfig']['thinkingConfig'] == {'thinkingLevel': 'low'}
    assert out['status'] == 'READY' and out['longs'][0]['ticker'] == O.CONTROL_LONG
    assert out['model'] == 'gemini-3.8-flash' and G.PROMPT_VERSION == O.PROMPT_VERSION


def test_thought_parts_are_never_parsed_as_the_answer():
    c, _ = client({'longs': [], 'shorts': []}, thought=True)
    assert G.rank(O.control_universe(), client=c, now=NOW)['status'] == 'NO_OPPORTUNITY'


def test_the_same_validator_refuses_an_invented_ticker():
    c, _ = client({'longs': [{'ticker': 'FAKE.TO', 'confidence': 0.9, 'reason': 'x',
                              'basis': 'technical'}], 'shorts': []})
    out = G.rank(O.control_universe(), client=c, now=NOW)
    assert out['longs'] == [] and any('FAKE.TO' in g for g in out['gaps'])


@pytest.mark.parametrize('kw,why', [({'status': 429}, 'HTTP_429'),
                                    ({'finish': 'MAX_TOKENS'}, 'CUT_OFF_MAX_TOKENS')])
def test_a_provider_failure_is_named_never_echoed(kw, why):
    c, _ = client({'longs': []}, **kw)
    out = G.rank(O.control_universe(), client=c, now=NOW)
    assert out['status'] == 'UNAVAILABLE' and why in out['reason']


def test_no_credential_is_unavailable_and_says_so(monkeypatch):
    monkeypatch.delenv('GEMINI_API_KEY', raising=False)
    out = G.rank(O.control_universe(), now=NOW)
    assert out['status'] == 'UNAVAILABLE' and 'Gemini credential' in out['reason']


def test_the_private_key_contract(tmp_path, monkeypatch):
    monkeypatch.delenv('GEMINI_API_KEY', raising=False)
    assert G.load_private_key(tmp_path) is None
    (tmp_path / 'secrets').mkdir()
    (tmp_path / 'secrets' / 'gemini_api_key').write_text('AQ.abc\n')
    assert G.load_private_key(tmp_path) == 'AQ.abc'
    monkeypatch.delenv('GEMINI_API_KEY', raising=False)
    (tmp_path / 'secrets' / 'gemini_api_key').write_text('two words')
    with pytest.raises(ValueError):
        G.load_private_key(tmp_path)


def test_sealed_snapshot_round_trips_through_the_pure_reader(tmp_path):
    from build_biotech import write_atomic
    c, _ = client({'longs': [], 'shorts': [{'ticker': O.CONTROL_SHORT, 'confidence': 0.66,
                                            'reason': 'r0 -2.7', 'basis': 'technical'}]})
    result = G.rank(O.control_universe(), client=c, now=NOW)
    snap = O._seal({**result, 'schema_version': G.SCHEMA_VERSION, 'prompt_version': G.PROMPT_VERSION,
                    'session': NOW.date().isoformat(), 'prepared_at': NOW.isoformat()})
    write_atomic(tmp_path / G.SNAPSHOT_NAME, snap)
    back = G.load_prepared(tmp_path, NOW.replace(hour=9, minute=46))
    assert back['status'] == 'READY' and back['shorts'][0]['ticker'] == O.CONTROL_SHORT
    assert back['prompt_version'] == G.PROMPT_VERSION
    # an edited file fails its seal
    obj = json.loads((tmp_path / G.SNAPSHOT_NAME).read_text())
    obj['shorts'][0]['confidence'] = 0.99
    (tmp_path / G.SNAPSHOT_NAME).write_text(json.dumps(obj))
    assert G.load_prepared(tmp_path, NOW.replace(hour=9, minute=46))['status'] == 'UNAVAILABLE'


def test_staging_after_the_open_is_refused(tmp_path):
    with pytest.raises(ValueError, match='PREOPEN'):
        G.stage(tmp_path, now=NOW.replace(hour=9, minute=31))


def test_the_positive_control_path_detects_both_planted_sides():
    c, _ = client({'longs': [{'ticker': O.CONTROL_LONG, 'confidence': 0.68, 'reason': 'a',
                              'basis': 'technical'}],
                   'shorts': [{'ticker': O.CONTROL_SHORT, 'confidence': 0.67, 'reason': 'b',
                               'basis': 'technical'}]})
    out = G.run_control(client=c, now=NOW)
    assert out['long_detected'] and out['short_detected']


def snap(longs=(), shorts=()):
    return {'status': 'READY', 'longs': [{'ticker': t, 'confidence': .6} for t in longs],
            'shorts': [{'ticker': t, 'confidence': .6} for t in shorts]}


def test_gemini_counts_toward_the_two_model_agreement():
    """Owner: the algorithm picks on at least two models in agreement — Gemini
    is one of the four that can make the two."""
    none = {'status': 'NO_OPPORTUNITY', 'longs': [], 'shorts': []}
    out = top_picks.select(none, snap(longs=['AC.TO']), none, gemini=snap(longs=['AC.TO']))
    assert [p['ticker'] for p in out['picks']] == ['AC.TO']
    assert out['picks'][0]['agreement'] == '2 of 4'
    assert out['picks'][0]['backing'] == ['DeepSeek 0.60', 'Gemini 0.60']
    alone = top_picks.select(none, none, none, gemini=snap(longs=['AC.TO']))
    assert alone['picks'] == [] and alone['single'][0]['by'] == 'Gemini 0.60'


def test_gemini_is_a_desk_a_scoreboard_row_and_a_recorded_source():
    import model_picks
    import primary_board
    assert ('gemini', 'Gemini', 'gemini') in primary_board.DESKS
    assert ('gemini_selected', 'Gemini') in primary_board.LEADERBOARD
    rows = model_picks.rows_from_report({'session': '2026-10-05', 'intraday': {
        'gemini': {**snap(longs=['AC.TO']), 'prompt_version': G.PROMPT_VERSION}}})
    assert [(r['model'], r['kind'], r['ticker']) for r in rows] == [('gemini', 'selected', 'AC.TO')]


def test_gemini_proposes_in_the_debate():
    import debate
    props = debate.proposals(None, None, None, snap(shorts=['SU.TO']))
    assert props[0]['proposers'][0]['model'] == 'gemini'
