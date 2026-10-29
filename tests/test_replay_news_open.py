"""The day-142 replay: the registered wording, the request, the verdict's mapping."""
import random

import pytest

import news_desk as N
import replay_news_open as X


def test_the_open_wording_is_three_substitutions_and_nothing_else():
    text = X.open_prompt()
    assert '09:45' not in text
    for old, new in X.SUBSTITUTIONS:
        assert text.count(new) == 1
    back = text
    for old, new in reversed(X.SUBSTITUTIONS):
        back = back.replace(new, old)
    assert back == N.SYSTEM_PROMPT
    assert X.PROMPTS == {'open': text, 'day122': N.SYSTEM_PROMPT}
    assert X.PROMPT_VERSION == 'day122-v1+day142-open'


def test_a_wording_that_drifted_refuses():
    with pytest.raises(ValueError, match='SUBSTITUTION_NOT_FOUND_ONCE'):
        X.open_prompt(N.SYSTEM_PROMPT.replace('by 09:45.', 'by then.'))


class _Fake:
    """Captures the one create() call and answers a fixed reply."""
    def __init__(self):
        self.kwargs = None
        self.chat = self
        self.completions = self

    def create(self, **kwargs):
        self.kwargs = kwargs

        class Msg:
            content = '{"calls": []}'

        class Choice:
            finish_reason = 'stop'
            message = Msg()

        class Resp:
            choices = [Choice()]
            model = N.MODEL
        return Resp()


def test_the_request_is_news_desk_ask_with_only_the_prompt_passed_in():
    batch = [{'id': '2026-07-02:AAA.TO', 'ticker': 'AAA.TO', 'releases': []}]
    a, b = _Fake(), _Fake()
    assert N.ask(batch, client=a) == X.ask_with(N.SYSTEM_PROMPT, batch, b)
    assert a.kwargs == b.kwargs
    c = _Fake()
    X.ask_with(X.PROMPTS['open'], batch, c)
    assert c.kwargs['messages'][0]['content'] == X.PROMPTS['open']
    assert {k: v for k, v in c.kwargs.items() if k != 'messages'} == \
        {k: v for k, v in a.kwargs.items() if k != 'messages'}


def _sessions(mean, sd, n_sessions=60, per=6, seed=1):
    rng = random.Random(seed)
    return [(f'2026-07-{k:03d}', [rng.gauss(mean, sd) for _ in range(per)])
            for k in range(n_sessions)]


def _alternating(mean, swing, n_sessions):
    """Session means alternate mean ± swing, two calls each: the mean is exact."""
    return [(f'2026-07-{k:03d}', [mean + (swing if k % 2 else -swing) + e for e in (-1.0, 1.0)])
            for k in range(n_sessions)]


def test_the_verdict_maps_the_bar_as_registered():
    assert X.verdict(_sessions(-0.3, 2.0), draws=200)['status'] == 'FAIL'
    strong = X.verdict(_sessions(1.0, 1.0), draws=200)
    assert strong['status'] == 'PASS' and strong['control']['detected']
    weak = X.verdict(_alternating(0.1, 0.5, 60), draws=200)
    assert weak['mean'] == pytest.approx(0.1) and weak['t'] < 3
    assert weak['status'] == 'NULL' and weak['control']['detected']
    tiny = X.verdict(_alternating(0.05, 9.0, 8), draws=200)
    assert tiny['mean'] == pytest.approx(0.05) and tiny['status'] == 'UNDERPOWERED'
    assert not tiny['control']['detected']


def test_the_control_measures_the_planted_edge_alone():
    big = _sessions(5.0, 1.0)
    small = _sessions(0.0, 1.0)
    assert X.control(big)['t'] == pytest.approx(X.control(small)['t'], rel=0.05)


def test_paired_counts_side_changes_and_differences():
    a = [{'id': 'x', 'session': 's1', 'side': 'LONG', 'w_day': 1.0},
         {'id': 'y', 'session': 's1', 'side': 'SHORT', 'w_day': -0.5},
         {'id': 'z', 'session': 's2', 'side': 'LONG', 'w_day': None}]
    b = [{'id': 'x', 'session': 's1', 'side': 'LONG', 'w_day': 1.0},
         {'id': 'y', 'session': 's1', 'side': 'LONG', 'w_day': 0.5},
         {'id': 'z', 'session': 's2', 'side': 'SHORT', 'w_day': 0.2}]
    got = X.paired(a, b)
    assert got['events'] == 3 and got['side_changed'] == 2
    assert got['mean'] == pytest.approx(-0.5) and got['sessions'] == 1
