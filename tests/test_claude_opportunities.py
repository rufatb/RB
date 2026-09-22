"""Claude's desk: same question, same evidence, same validator, own snapshot."""
import datetime as dt
import json
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest

import claude_opportunities as C
import deepseek_opportunities as O
from test_deepseek_opportunities import PREOPEN, pick, stage_dir, tech

ET = ZoneInfo('America/New_York')
LATER = PREOPEN.replace(hour=9, minute=15)


def briefed(tmp_path, names=('AC.TO', 'CNQ.TO')):
    root = stage_dir(tmp_path, [tech(t) for t in names])
    assert C.stage_brief(root, now=PREOPEN) is not None
    return root


def test_the_brief_is_the_deepseek_question_verbatim(tmp_path):
    """A comparison is only a comparison if neither model saw something the
    other did not: same prompt, same rows, same evidence counts."""
    root = briefed(tmp_path)
    brief = C.read_brief(root, PREOPEN)
    assert brief['system_prompt'] == O.SYSTEM_PROMPT and C.PROMPT_VERSION == O.PROMPT_VERSION
    from factor_inputs import build_from_state
    import yaml
    cfg = yaml.safe_load(open('config.yaml'))
    staged = build_from_state(root, cfg, PREOPEN)
    same = O.build_request(staged['candidates'], staged.get('macro'), PREOPEN)
    assert brief['payload'] == same['payload'] and brief['universe'] == sorted(same['allowed'])
    text = (root/C.BRIEF_TEXT).read_text()
    assert text.startswith(O.SYSTEM_PROMPT) and 'AC.TO' in text
    assert max(len(line) for line in text.splitlines()) < 2000


def test_an_answer_seals_and_reads_back_with_its_independence(tmp_path):
    root = briefed(tmp_path)
    C.seal(root, {'longs': [pick('AC.TO', 0.62)], 'shorts': [pick('CNQ.TO', 0.55)]}, now=LATER)
    out = C.load_prepared(root, LATER + dt.timedelta(minutes=40))
    assert out['status'] == 'READY' and out['longs'][0]['ticker'] == 'AC.TO'
    assert out['model'] == C.SESSION_LABEL and out['route'] == 'session'
    assert 'before DeepSeek or Jev had been asked' in out['independence']
    assert 'NOT a calibrated' in out['confidence_label']


def test_an_invented_ticker_is_refused_exactly_as_for_deepseek(tmp_path):
    root = briefed(tmp_path)
    snap = C.seal(root, {'longs': [pick('ZZZZ.TO')], 'shorts': []}, now=LATER)
    assert snap['longs'] == [] and snap['status'] == 'NO_OPPORTUNITY'
    assert any('outside the supplied universe' in g for g in snap['gaps'])


def test_the_seal_refuses_at_the_deadline_so_deepseek_keeps_its_slot(tmp_path):
    root = briefed(tmp_path)
    with pytest.raises(ValueError, match='PREOPEN_ONLY'):
        C.seal(root, {'longs': [], 'shorts': []}, now=PREOPEN.replace(hour=9, minute=24))
    assert not (root/C.SNAPSHOT_NAME).exists()


def test_the_first_answer_stands(tmp_path):
    root = briefed(tmp_path)
    C.seal(root, {'longs': [pick('AC.TO')], 'shorts': []}, now=LATER)
    with pytest.raises(ValueError, match='ALREADY_SEALED'):
        C.seal(root, {'longs': [], 'shorts': [pick('AC.TO')]}, now=LATER)


def test_a_ranking_already_on_disk_is_disclosed(tmp_path):
    root = briefed(tmp_path)
    (root/O.SNAPSHOT_NAME).write_text(json.dumps({'session': PREOPEN.date().isoformat()}))
    snap = C.seal(root, {'longs': [], 'shorts': []}, now=LATER)
    assert 'DeepSeek' in snap['independence'] and 'not independent' in snap['independence']


def test_an_edited_snapshot_is_refused(tmp_path):
    root = briefed(tmp_path)
    C.seal(root, {'longs': [pick('AC.TO', 0.6)], 'shorts': []}, now=LATER)
    obj = json.loads((root/C.SNAPSHOT_NAME).read_text())
    obj['longs'][0]['confidence'] = 0.99
    (root/C.SNAPSHOT_NAME).write_text(json.dumps(obj))
    assert C.load_prepared(root, LATER)['status'] == 'UNAVAILABLE'


def test_no_pool_seals_an_unavailable_reason_instead_of_a_brief(tmp_path):
    assert C.stage_brief(tmp_path, now=PREOPEN) is None
    out = C.load_prepared(tmp_path, LATER)
    assert out['status'] == 'UNAVAILABLE' and out['reason']
    assert C.wait_for_brief(tmp_path, 0, now_fn=lambda: LATER) == 4


def test_waiting_reports_ready_and_past_cutoff(tmp_path):
    root = briefed(tmp_path)
    assert C.wait_for_brief(root, 0, now_fn=lambda: LATER) == 0
    assert C.wait_for_brief(root, 0, now_fn=lambda: PREOPEN.replace(minute=24)) == 3
    assert C.wait_for_brief(tmp_path/'nothing', 0, now_fn=lambda: LATER) == 2


def test_a_fenced_answer_is_unwrapped_and_prose_is_refused():
    assert C.parse_answer('```json\n{"longs": [], "shorts": []}\n```') == {'longs': [], 'shorts': []}
    with pytest.raises(ValueError):
        C.parse_answer('I would buy AC.TO')


def test_the_api_route_uses_the_same_seal_and_never_the_session_endpoint(tmp_path):
    root = briefed(tmp_path)

    class Messages:
        def create(self, **kw):
            self.kw = kw
            body = json.dumps({'longs': [pick('CNQ.TO', 0.58)], 'shorts': []})
            return SimpleNamespace(stop_reason='end_turn', model='claude-test',
                                   content=[SimpleNamespace(text=body)])
    client = SimpleNamespace(messages=Messages())
    snap = C.ask_api(root, now=LATER, client=client)
    assert snap['route'] == 'api' and snap['model'] == 'claude-test'
    assert client.messages.kw['system'] == O.SYSTEM_PROMPT
    assert json.loads(client.messages.kw['messages'][0]['content']) == C.read_brief(root, LATER)['payload']
    import inspect
    assert "base_url='https://api.anthropic.com'" in inspect.getsource(C.ask_api)


def test_a_cut_off_api_reply_is_refused(tmp_path):
    root = briefed(tmp_path)
    client = SimpleNamespace(messages=SimpleNamespace(create=lambda **kw: SimpleNamespace(
        stop_reason='max_tokens', model='m', content=[])))
    with pytest.raises(ValueError, match='CUT_OFF'):
        C.ask_api(root, now=LATER, client=client)
    assert not (root/C.SNAPSHOT_NAME).exists()


def test_the_credential_is_read_from_the_private_file_only(tmp_path, monkeypatch):
    monkeypatch.setenv('ANTHROPIC_API_KEY', 'sk-env-should-be-ignored')
    assert C.load_api_key(tmp_path) is None
    (tmp_path/'secrets').mkdir()
    (tmp_path/'secrets'/'anthropic_api_key').write_text('sk-ant-x\n')
    assert C.load_api_key(tmp_path) == 'sk-ant-x'
