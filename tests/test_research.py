"""Day-126: the research round, the stateless Claude routes and the web scout
(PREREGISTER_day126_research.md)."""
import datetime as dt
import json

import pytest

import research as RS

ET = RS.ET
NOW = dt.datetime(2026, 10, 6, 9, 0, tzinfo=ET)
GRADES = [{'date': '2026-10-06', 'gradingCompany': 'Today', 'action': 'upgrade',
           'previousGrade': 'Hold', 'newGrade': 'Buy'},
          {'date': '2026-09-01', 'gradingCompany': 'RBC', 'action': 'downgrade',
           'previousGrade': 'Buy', 'newGrade': 'Hold'}]


def fake_get(path, **p):
    if path == 'grades':
        return GRADES
    if path == 'historical-price-eod/full':
        return [{'date': '2026-10-05', 'close': 10.0, 'changePercent': 1.0, 'volume': 5},
                {'date': '2026-10-06', 'close': 99.0, 'changePercent': 9.0, 'volume': 5}]
    if path == 'sector-performance-snapshot':
        return [{'sector': 'Energy', 'averageChange': 1.234}] if p['date'] == '2026-10-05' else []
    raise AssertionError(path)


def box(**kw):
    return RS.Toolbox(NOW.date(), {'CVE.TO'}, NOW, get=fake_get, **kw)


def test_tools_never_see_the_session_or_later():
    b = box()
    out = json.loads(b.run('analyst_history', {'ticker': 'CVE.TO'}))
    assert out['actions'] == ['2026-09-01 RBC downgrade Buy→Hold']        # today's is cut
    prices = json.loads(b.run('daily_prices', {'ticker': 'CVE.TO'}))
    assert [s['date'] for s in prices['sessions']] == ['2026-10-05']
    assert json.loads(b.run('sector_performance', {}))['sectors'] == {'Energy': 1.23}


def test_scope_budget_and_replay_tools():
    b = box(max_calls=1)
    assert json.loads(b.run('analyst_history', {'ticker': 'NOPE.TO'}))['error'] == 'TICKER_NOT_IN_LIST'
    b.run('analyst_history', {'ticker': 'CVE.TO'})
    assert json.loads(b.run('analyst_history', {'ticker': 'CVE.TO'}))['error'] == 'BUDGET_SPENT'
    names = {s['function']['name'] for s in box(replay=True).specs()}
    assert not names & set(RS.REPLAY_EXCLUDED) and 'reaction_history' in names
    assert json.loads(box(replay=True).run('news', {'ticker': 'CVE.TO'}))['error'] == 'UNKNOWN_TOOL'


def openai_post(script):
    """Replies in order; records every body it was sent."""
    sent = []

    def post(body):
        sent.append(json.loads(json.dumps(body)))
        return script.pop(0)
    post.sent = sent
    return post


def tool_call(name, args, cid='c1'):
    return {'choices': [{'finish_reason': 'tool_calls', 'message': {'content': None, 'tool_calls': [
        {'id': cid, 'type': 'function', 'function': {'name': name, 'arguments': json.dumps(args)}}]}}]}


def final(obj):
    return {'choices': [{'finish_reason': 'stop', 'message': {'content': json.dumps(obj)}}]}


def test_openai_loop_researches_then_answers_and_logs():
    post = openai_post([tool_call('analyst_history', {'ticker': 'CVE.TO'}),
                        final({'longs': [], 'shorts': [{'ticker': 'CVE.TO'}]})])
    b = box()
    out = RS.openai_loop(post, 'm', 'SYSTEM', 'USER', b)
    assert out['shorts'][0]['ticker'] == 'CVE.TO'
    assert RS.RESEARCH_NOTE.strip()[:20] in post.sent[0]['messages'][0]['content']
    tool_msg = post.sent[1]['messages'][-1]
    assert tool_msg['role'] == 'tool' and 'RBC downgrade' in tool_msg['content']
    assert RS.summary(b)['tools'] == ['analyst_history(CVE.TO)']


def test_a_spent_budget_forces_the_answer_without_tools():
    post = openai_post([tool_call('analyst_history', {'ticker': 'CVE.TO'}), final({'longs': []})])
    RS.openai_loop(post, 'm', 'S', 'U', box(max_calls=1))
    assert post.sent[-1]['tool_choice'] == 'none' and post.sent[-1]['messages'][-1]['content'] == RS.FINAL_ASK


def test_gemini_loop_sends_model_turns_back_whole():
    calls = [{'candidates': [{'finishReason': 'STOP', 'content': {'role': 'model', 'parts': [
                {'functionCall': {'name': 'analyst_history', 'args': {'ticker': 'CVE.TO'}, 'id': 'g1'},
                 'thoughtSignature': 'SIG'}]}}]},
             {'candidates': [{'finishReason': 'STOP', 'content': {'parts': [
                 {'text': 'scratch', 'thought': True}, {'text': '{"longs": [], "shorts": []}'}]}}]}]
    post = openai_post(calls)
    out = RS.gemini_loop(post, 'S', 'U', box())
    assert out == {'longs': [], 'shorts': []}
    second = post.sent[1]['contents']
    assert second[1]['parts'][0]['thoughtSignature'] == 'SIG'
    assert second[2]['parts'][0]['functionResponse']['id'] == 'g1'


def test_a_failed_research_round_falls_back_single_shot(monkeypatch):
    import deepseek_opportunities as O
    monkeypatch.setenv('DEEPSEEK_API_KEY', 'k')
    monkeypatch.setattr(RS, 'openai_loop', lambda *a, **k: (_ for _ in ()).throw(ValueError('HTTP_503')))

    class Client:
        def __init__(self, **kw):
            self.chat = self
            self.completions = self

        def create(self, **kw):
            import types
            msg = types.SimpleNamespace(content=json.dumps({'longs': [], 'shorts': []}))
            return types.SimpleNamespace(model='deepseek-v4-pro',
                                         choices=[types.SimpleNamespace(finish_reason='stop', message=msg)])
    import openai
    monkeypatch.setattr(openai, 'OpenAI', Client)
    out = O.rank(O.control_universe(), now=NOW, research=True, fmp_get=fake_get)
    assert out['status'] == 'NO_OPPORTUNITY'
    assert any('Research round failed (HTTP_503); answered single-shot.' in g for g in out['gaps'])
    assert out['research']['failed'] == 'HTTP_503' and 'prompt_version' not in out


def test_council_facts_carry_no_model_names():
    logs = [[{'model': 'DeepSeek', 'tool': 'daily_prices', 'args': {'ticker': 'CVE.TO'}, 'result': '{"x": 1}'},
             {'model': 'Gemini', 'tool': 'news', 'args': {'ticker': 'CVE.TO'}, 'result': '{"error": "X"}'}]]
    facts = RS.facts_by_ticker(logs, {'CVE.TO'})
    assert facts == {'CVE.TO': 'daily_prices: {"x": 1}'}


def test_scout_keeps_dated_lines_and_sources():
    import scout
    reply = {'choices': [{'message': {'content': '- 2026-10-05 — Deal announced (Reuters) [1]\nnoise line',
                                      'annotations': [{'type': 'url_citation', 'url_citation': {'url': 'https://x'}}]}}],
             'usage': {'cost': 0.01}}
    out, gaps = scout.scout(['CVE.TO'], NOW, post=lambda body: reply, get=lambda p, **k: [{'companyName': 'Cenovus'}])
    assert out['CVE.TO']['facts'] == ['2026-10-05 — Deal announced (Reuters)'] and out['CVE.TO']['sources'] == ['https://x']
    assert scout.row_text(out['CVE.TO']).endswith('[sources: https://x]') and gaps == []


def test_claude_openrouter_ballot_and_wait_ballot_closes(tmp_path):
    import council as K
    reply = {'choices': [{'message': {'content': json.dumps({'ballots': [
        {'id': 'P1', 'stance': 'ENDORSE', 'conviction': 0.6, 'argument': 'seat A is right'}], 'top_two': ['P1']})}}]}
    out = K.ask_claude_openrouter('S', 'U', post=lambda body: reply)
    assert K.parse_ballot(out, ['P1'])['votes']['P1']['stance'] == 'ENDORSE'
    K._write(tmp_path/K.CLAUDE_BALLOT, {'session': '2026-10-06', 'route': 'openrouter', 'reply': out})
    assert K.wait_ballot(tmp_path, 0, now_fn=lambda: NOW) == 3


def test_morning_routes_claude_through_openrouter_before_the_session():
    from pathlib import Path
    body = (Path(__file__).resolve().parent.parent / 'morning_full.sh').read_text()
    assert body.index('--openrouter') < body.index('until python claude_opportunities.py')


def test_deepseek_ships_single_shot_after_its_failed_control():
    """Day-126 amendment 1: the research path failed the planted control."""
    import deepseek_opportunities as O
    assert O.RESEARCH_LIVE is False
