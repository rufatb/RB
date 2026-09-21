"""Jev: a decisions model, and the gate that has no tunable constant.

What is different from the DeepSeek path, and therefore what these tests are
about: the answer is TYPED. The option set is the universe, so the provider
constrains the reply; the ranking comes out of the returned distribution rather
than a second question; and the abstention gate is "more likely than NONE",
which is registered and has nothing in it to loosen after a losing day.
"""
import datetime as dt
import json
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

import jev_opportunities as J
from test_deepseek_opportunities import PREOPEN, headline, pool_row, tech

ET = ZoneInfo('America/New_York')


def answer(probabilities, confidence=0.7):
    return {'type': 'choice', 'choice': max(probabilities, key=probabilities.get),
            'probabilities': probabilities, 'confidence': confidence}


def poster(long_probs=None, short_probs=None, model='typesafe/jev-1.13-20260917', seen=None):
    def post(body, key, timeout):
        if seen is not None:
            seen.append(body)
        return {'model': model,
                'answers': {'long': answer(long_probs or {J.ABSTAIN: 1.0}),
                            'short': answer(short_probs or {J.ABSTAIN: 1.0})}}
    return post


def stage_dir(tmp_path, candidates):
    (tmp_path/'deepseek_candidates.json').write_text(json.dumps(
        {'as_of': PREOPEN.isoformat(), 'candidates': [pool_row(c) for c in candidates]}))
    return tmp_path


# ── the abstention gate ──────────────────────────────────────────────────────

def test_a_name_less_likely_than_doing_nothing_is_not_reported():
    """THE GATE. The owner's complaint was four names every morning, mostly
    wrong. A name appears only when the model rates it above its own NONE."""
    out = J.rank([tech('AC.TO'), tech('TD.TO')], now=PREOPEN,
                 poster=poster(long_probs={'AC.TO': 0.2, 'TD.TO': 0.1, J.ABSTAIN: 0.7}))
    assert out['longs'] == []
    assert out['status'] == 'NO_OPPORTUNITY'


def test_a_name_more_likely_than_doing_nothing_is_reported():
    out = J.rank([tech('AC.TO'), tech('TD.TO')], now=PREOPEN,
                 poster=poster(long_probs={'AC.TO': 0.6, 'TD.TO': 0.1, J.ABSTAIN: 0.3}))
    assert [r['ticker'] for r in out['longs']] == ['AC.TO']
    assert out['longs'][0]['abstain_probability'] == 0.3


def test_the_gate_carries_no_tunable_constant():
    """A threshold that can be nudged after a losing day is a threshold that
    will be. The comparison is against the model's own abstain probability."""
    import inspect
    src = inspect.getsource(J._side)
    assert 'floor = probabilities.get(ABSTAIN)' in src
    assert not [n for n in ('0.5', '0.55', '0.6', '0.65') if n in src]


def test_ranking_comes_from_the_returned_distribution():
    out = J.rank([tech(t) for t in ('A.TO', 'B.TO', 'C.TO')], now=PREOPEN,
                 poster=poster(long_probs={'A.TO': 0.2, 'B.TO': 0.5, 'C.TO': 0.25, J.ABSTAIN: 0.05}))
    assert [r['ticker'] for r in out['longs']] == ['B.TO', 'C.TO'], 'ranked by probability'
    assert len(out['longs']) <= J.MAX_PER_SIDE


def test_a_tie_breaks_deterministically():
    out = J.rank([tech('B.TO'), tech('A.TO')], now=PREOPEN,
                 poster=poster(long_probs={'B.TO': 0.4, 'A.TO': 0.4, J.ABSTAIN: 0.2}))
    assert [r['ticker'] for r in out['longs']] == ['A.TO', 'B.TO']


# ── the universe boundary ────────────────────────────────────────────────────

def test_the_option_set_sent_is_exactly_the_universe_plus_abstain():
    """The provider constrains the answer to these options, which is why an
    invented ticker cannot occur here rather than being caught afterwards."""
    seen = []
    J.rank([tech('AC.TO'), tech('TD.TO')], now=PREOPEN, poster=poster(seen=seen))
    criteria = seen[0]['questions']['long']['criteria']
    assert set(criteria) == {'AC.TO', 'TD.TO', J.ABSTAIN}


def test_a_ticker_outside_the_universe_is_still_rejected():
    """Belt and braces: the provider should make this unreachable."""
    out = J.rank([tech('AC.TO')], now=PREOPEN,
                 poster=poster(long_probs={'LGVN': 0.9, J.ABSTAIN: 0.1}))
    assert out['longs'] == []
    assert any('outside the supplied universe' in g for g in out['gaps'])


def test_every_question_goes_in_one_request():
    """Still ONE request — that is the robustness claim, measured at ~1s and
    $0.00002. It now carries four questions: the two GATED ones that may
    decline, and the two FORCED ones that may not."""
    seen = []
    J.rank([tech('AC.TO')], now=PREOPEN, poster=poster(seen=seen))
    assert len(seen) == 1
    assert set(seen[0]['questions']) == {'long', 'short', 'forced_long', 'forced_short'}
    assert all(q['type'] == 'choice' for q in seen[0]['questions'].values())


def test_only_the_gated_questions_offer_the_abstain_option():
    """The whole separation lives here. If NONE leaks into a forced option set
    the model can decline again and the forced pick stops being forced; if it
    goes missing from a gated set, the registered abstention gate is gone."""
    seen = []
    J.rank([tech('AC.TO')], now=PREOPEN, poster=poster(seen=seen))
    questions = seen[0]['questions']
    for side in ('long', 'short'):
        assert J.ABSTAIN in questions[side]['criteria'], f'{side} lost its abstain option'
        assert J.ABSTAIN not in questions['forced_' + side]['criteria'], \
            f'forced_{side} can decline, so it is not forced'


def test_the_forced_instructions_say_a_low_probability_is_the_honest_answer():
    """Otherwise a model told it MUST pick reads that as pressure to sound
    confident, and a confident number on a coin-flip call is the warning sign
    this whole repo exists to avoid printing."""
    assert 'MUST pick' in J.FORCED_INSTRUCTIONS
    assert 'least bad' in J.FORCED_INSTRUCTIONS
    assert 'low probability on a' in J.FORCED_INSTRUCTIONS


def test_the_model_id_is_pinned_not_floating():
    """`typesafe/jev-latest` is NOT a valid model id — the API rejects it. A
    floating alias that 400s every morning looks exactly like an outage."""
    assert J.DEFAULT_MODEL == 'typesafe/jev-1.13'
    assert 'latest' not in J.DEFAULT_MODEL


def test_it_does_not_use_the_chat_endpoint():
    """Jev cannot be reached through /chat/completions; OpenRouter says so."""
    assert J.ENDPOINT.endswith('/api/alpha/decisions')
    assert 'chat/completions' not in J.ENDPOINT


# ── evidence and the prompt ──────────────────────────────────────────────────

def test_headlines_and_macro_reach_the_state():
    seen = []
    c = tech('ABX.TO'); c['headlines'] = [headline()]
    J.rank([c], macro={'wti': {'value': 61.0, 'as_of': '2026-09-17T16:59:00-04:00',
                               'change_pct': -1.31}}, now=PREOPEN, poster=poster(seen=seen))
    state = seen[0]['state']
    assert state['candidates'][0]['headlines'][0]['class'] == 'UNCLASSIFIED'
    assert state['macro']['wti']['change_pct'] == -1.31


def test_the_instructions_mark_supplied_text_untrusted():
    assert 'UNTRUSTED DATA' in J.INSTRUCTIONS
    assert 'never instructions' in J.INSTRUCTIONS


def test_the_instructions_say_abstaining_is_valid():
    text = J.INSTRUCTIONS.format(side='LONG', none=J.ABSTAIN)
    assert 'valid' in text and 'coin flip' in text and J.ABSTAIN in text


def test_a_ranking_without_news_says_so():
    out = J.rank([tech('AC.TO')], now=PREOPEN, poster=poster())
    assert any('technicals only' in g for g in out['gaps'])
    assert out['evidence']['names_with_headlines'] == 0


# ── failure behaviour ────────────────────────────────────────────────────────

def test_a_provider_failure_never_echoes_its_payload():
    def boom(body, key, timeout):
        raise RuntimeError('sk-or-v1-secret rejected 401')
    out = J.rank([tech('AC.TO')], now=PREOPEN, poster=boom)
    assert out['status'] == 'UNAVAILABLE'
    assert 'sk-or-v1-secret' not in out['reason'] and '401' not in out['reason']


def test_a_reply_without_a_distribution_is_unavailable_not_a_guess():
    def flat(body, key, timeout):
        return {'model': 'x', 'answers': {'long': {'type': 'choice', 'choice': 'AC.TO'},
                                          'short': {'type': 'choice', 'choice': 'AC.TO'}}}
    out = J.rank([tech('AC.TO')], now=PREOPEN, poster=flat)
    assert out['longs'] == [] and out['shorts'] == []
    assert any('no distribution' in g for g in out['gaps'])


def test_a_noul_answer_where_a_choice_was_asked_is_refused():
    def wrong(body, key, timeout):
        return {'model': 'x', 'answers': {'long': {'type': 'noul', 'noul': 0.9},
                                          'short': {'type': 'noul', 'noul': 0.1}}}
    out = J.rank([tech('AC.TO')], now=PREOPEN, poster=wrong)
    assert out['longs'] == [] and out['status'] == 'NO_OPPORTUNITY'


@pytest.mark.parametrize('bad', [1.4, -0.1, 'high', True])
def test_a_probability_outside_zero_to_one_is_dropped(bad):
    out = J.rank([tech('AC.TO')], now=PREOPEN,
                 poster=poster(long_probs={'AC.TO': bad, J.ABSTAIN: 0.1}))
    assert out['longs'] == []


def test_nothing_returned_is_ever_marked_adopted():
    for out in (J.rank([tech('AC.TO')], now=PREOPEN,
                       poster=poster(long_probs={'AC.TO': 0.9, J.ABSTAIN: 0.1})),
                J.unavailable('x')):
        assert out['adopted'] is False


def test_the_numbers_are_labelled_uncalibrated_everywhere():
    for out in (J.rank([tech('AC.TO')], now=PREOPEN, poster=poster()), J.unavailable('x')):
        label = out['confidence_label'].lower()
        assert 'not calibrated' in label and 'track record' in label


def test_no_credential_asks_nothing():
    out = J.rank([tech('AC.TO')], now=PREOPEN, key='')
    assert out['status'] == 'UNAVAILABLE' and 'OPENROUTER_API_KEY' in out['reason']


# ── staging and the clock ────────────────────────────────────────────────────

def test_staging_refuses_after_the_open(tmp_path):
    root = stage_dir(tmp_path, [tech('AC.TO')])
    with pytest.raises(ValueError, match='PREOPEN_ONLY'):
        J.stage(root, now=dt.datetime(2026, 9, 17, 9, 31, tzinfo=ET), poster=poster())
    assert not (root/J.SNAPSHOT_NAME).exists()


def test_staging_writes_a_sealed_snapshot_that_reads_back(tmp_path, monkeypatch):
    monkeypatch.setenv('OPENROUTER_API_KEY', 'sk-or-test')
    root = stage_dir(tmp_path, [tech('AC.TO')])
    J.stage(root, now=PREOPEN, poster=poster(long_probs={'AC.TO': 0.8, J.ABSTAIN: 0.2}))
    out = J.load_prepared(root, PREOPEN + dt.timedelta(hours=1))
    assert out['status'] == 'READY'
    assert out['longs'][0]['ticker'] == 'AC.TO' and out['longs'][0]['probability'] == 0.8


def test_the_credential_is_loaded_from_state_not_only_the_environment(tmp_path, monkeypatch):
    monkeypatch.delenv('OPENROUTER_API_KEY', raising=False)
    root = stage_dir(tmp_path, [tech('AC.TO')])
    (root/'secrets').mkdir()
    (root/'secrets'/'openrouter_api_key').write_text('sk-or-staged\n')
    J.stage(root, now=PREOPEN, poster=poster())
    assert not any('credential' in g for g in
                   json.loads((root/J.SNAPSHOT_NAME).read_text())['gaps'])


def test_a_staged_credential_never_reaches_the_snapshot(tmp_path, monkeypatch):
    monkeypatch.delenv('OPENROUTER_API_KEY', raising=False)
    root = stage_dir(tmp_path, [tech('AC.TO')])
    (root/'secrets').mkdir()
    (root/'secrets'/'openrouter_api_key').write_text('sk-or-staged-secret\n')
    J.stage(root, now=PREOPEN, poster=poster(long_probs={'AC.TO': 0.8, J.ABSTAIN: 0.2}))
    assert 'sk-or-staged-secret' not in (root/J.SNAPSHOT_NAME).read_text()


def test_a_resealed_snapshot_cannot_smuggle_in_an_unassessed_ticker(tmp_path, monkeypatch):
    monkeypatch.setenv('OPENROUTER_API_KEY', 'sk-or-test')
    root = stage_dir(tmp_path, [tech('AC.TO')])
    J.stage(root, now=PREOPEN, poster=poster(long_probs={'AC.TO': 0.8, J.ABSTAIN: 0.2}))
    path = root/J.SNAPSHOT_NAME
    obj = json.loads(path.read_text())
    obj['longs'] = [{'ticker': 'LGVN', 'probability': 0.99, 'confidence': 0.9}]
    path.write_text(json.dumps(J._seal(obj)))
    assert J.load_prepared(root, PREOPEN)['longs'] == []


def test_a_stale_snapshot_is_refused(tmp_path, monkeypatch):
    monkeypatch.setenv('OPENROUTER_API_KEY', 'sk-or-test')
    root = stage_dir(tmp_path, [tech('AC.TO')])
    J.stage(root, now=PREOPEN, poster=poster())
    assert J.load_prepared(root, PREOPEN + dt.timedelta(hours=7))['status'] == 'UNAVAILABLE'


def test_the_reader_makes_no_provider_call(tmp_path, monkeypatch):
    monkeypatch.setenv('OPENROUTER_API_KEY', 'sk-or-test')
    root = stage_dir(tmp_path, [tech('AC.TO')])
    J.stage(root, now=PREOPEN, poster=poster(long_probs={'AC.TO': 0.8, J.ABSTAIN: 0.2}))
    monkeypatch.setattr(J, '_post', lambda *a, **k: pytest.fail('the reader called the provider'))
    assert J.load_prepared(root, PREOPEN)['status'] == 'READY'


def test_a_diagnostic_snapshot_is_not_a_morning_snapshot(tmp_path, monkeypatch):
    monkeypatch.setenv('OPENROUTER_API_KEY', 'sk-or-test')
    from diagnostic_context import create_context
    root = tmp_path/'diag'
    create_context(root, now=PREOPEN)
    stage_dir(root, [tech('AC.TO')])
    J.stage(root, now=PREOPEN, poster=poster(), diagnostic=True)
    assert J.load_prepared(root, PREOPEN)['status'] == 'UNAVAILABLE'
    assert J.load_diagnostic(root, PREOPEN)['status'] in ('READY', 'NO_OPPORTUNITY')


# ── the cross-model comparison ───────────────────────────────────────────────

def test_agreement_between_the_two_models_is_recorded():
    out = J.compare_models({'longs': [], 'shorts': [{'ticker': 'SHOP.TO', 'probability': .48}]},
                           {'longs': [], 'shorts': [{'ticker': 'SHOP.TO', 'confidence': .55}]})
    assert out['rows'][0]['verdict'] == J.AGREE and out['agree'] == 1


def test_a_contradiction_between_the_two_models_is_flagged():
    out = J.compare_models({'longs': [{'ticker': 'CNQ.TO', 'probability': .6}], 'shorts': []},
                           {'longs': [], 'shorts': [{'ticker': 'CNQ.TO', 'confidence': .57}]})
    assert out['rows'][0]['verdict'] == J.OPPOSE and out['oppose'] == 1


def test_the_comparison_produces_no_consensus_pick():
    """Averaging two unmeasured opinions makes a third unmeasured opinion that
    looks better than either."""
    out = J.compare_models({'longs': [{'ticker': 'AC.TO', 'probability': .8}], 'shorts': []},
                           {'longs': [{'ticker': 'AC.TO', 'confidence': .6}], 'shorts': []})
    text = json.dumps(out)
    assert 'consensus' not in text and 'combined' not in text and '0.7' not in text


def test_names_only_the_other_model_picked_are_listed_separately():
    out = J.compare_models({'longs': [], 'shorts': []},
                           {'longs': [{'ticker': 'ABX.TO'}], 'shorts': []})
    assert out['deepseek_only'] == ['ABX.TO'] and out['rows'] == []


# ── the positive control ─────────────────────────────────────────────────────

def test_the_control_reports_detection_per_side():
    import deepseek_opportunities as D
    out = J.run_control(now=PREOPEN, key='sk-or-test', poster=poster(
        long_probs={D.CONTROL_LONG: 0.8, J.ABSTAIN: 0.2},
        short_probs={J.ABSTAIN: 1.0}))
    assert out['long_detected'] is True and out['short_detected'] is False


# ── the ranking is shown daily; the gate is untouched ────────────────────────
# The owner asked to see Jev's top picks EVERY day, including days it declines
# everything — which are exactly the days the bare picks say least. The answer
# is to show the ranking beside the verdict, never to promote a declined name
# into the selection. `cleared_gate` is what keeps those two apart.

def ranked_answer(probabilities, abstain):
    return {'type': 'choice', 'confidence': 0.5,
            'probabilities': {**probabilities, J.ABSTAIN: abstain}}


def test_the_ranking_is_present_even_when_nothing_clears():
    """THE REQUEST. A day of total abstention used to render nothing at all."""
    picks, ranked, _ = J._side(ranked_answer({'AAA.TO': 0.20, 'BBB.TO': 0.10}, 0.70),
                               {'AAA.TO', 'BBB.TO'})
    assert picks == [], 'the gate must still decline these'
    assert [r['ticker'] for r in ranked] == ['AAA.TO', 'BBB.TO']
    assert all(r['cleared_gate'] is False for r in ranked)


def test_every_ranked_row_says_whether_it_cleared():
    """A table of names under a heading reads as a recommendation unless it
    says otherwise, on every row."""
    _, ranked, _ = J._side(ranked_answer({'AAA.TO': 0.60, 'BBB.TO': 0.10}, 0.30),
                           {'AAA.TO', 'BBB.TO'})
    assert [r['cleared_gate'] for r in ranked] == [True, False]
    assert all('abstain_probability' in r for r in ranked)


def test_the_gate_is_unchanged_by_the_reordering():
    """Picks are now taken from the sorted list and filtered, instead of
    filtered and then sorted. Anything above the floor outranks everything
    below it, so the selection must be identical — this is the same arithmetic
    in a different order, not a loosening."""
    answer = ranked_answer({'AAA.TO': 0.50, 'BBB.TO': 0.40, 'CCC.TO': 0.05}, 0.30)
    picks, _, _ = J._side(answer, {'AAA.TO', 'BBB.TO', 'CCC.TO'})
    assert [p['ticker'] for p in picks] == ['AAA.TO', 'BBB.TO']
    assert len(picks) <= J.MAX_PER_SIDE


def test_a_name_exactly_at_its_own_abstain_does_not_clear():
    """Strictly greater. An equal probability is not a preference."""
    picks, ranked, _ = J._side(ranked_answer({'AAA.TO': 0.30}, 0.30), {'AAA.TO'})
    assert picks == []
    assert ranked[0]['cleared_gate'] is False


def test_the_display_constant_cannot_promote_a_declined_name(monkeypatch):
    """RANKED_PER_SIDE is display only. Turning it up shows more of the
    ranking and must never move a name into the selection — the gate has no
    constant at all, which is the whole point of day-98."""
    monkeypatch.setattr(J, 'RANKED_PER_SIDE', 5)
    picks, ranked, _ = J._side(
        ranked_answer({f'N{i}.TO': 0.05 for i in range(5)}, 0.50),
        {f'N{i}.TO' for i in range(5)})
    assert picks == []
    assert len(ranked) == 5 and all(r['cleared_gate'] is False for r in ranked)


def test_both_renderers_print_the_ranking_and_label_it_as_not_a_pick():
    import daily_render, report_page
    snap = {'status': 'NO_OPPORTUNITY', 'model': 'typesafe/jev-1.13', 'considered': 78,
            'longs': [], 'shorts': [],
            'long_ranked': [{'ticker': 'AAA.TO', 'probability': 0.2,
                             'abstain_probability': 0.7, 'cleared_gate': False}],
            'short_ranked': []}
    text = '\n'.join(daily_render.jev_summary({'jev': snap}))
    assert 'AAA.TO' in text and '0.200' in text
    assert 'NOT a selection' in text and 'NOT selected' in text
    html = report_page._jev_section({'jev': snap})
    assert 'AAA.TO' in html and 'not selected' in html
    assert 'is NOT a pick' in html


# ── the forced choice: a pick every day, from a DIFFERENT question ───────────
# The owner asked for a Jev pick daily. The answer is not to lower the gate —
# it has no constant to lower — but to ask a second question whose option set
# contains no "none of these", so declining is not a legal answer. That is a
# different instrument, honestly labelled: best-of-set, which on a quiet day is
# least-bad-of-a-bad-set. Verified live 2026-09-21 on a NOISE-ONLY universe:
# the gate declined both sides and the forced question still named NOIS9.TO
# long and NOIS0.TO short.

def test_the_forced_question_has_no_abstain_option():
    """THE MECHANISM. If NONE is in the forced option set the model can decline
    again and the whole change is a no-op."""
    import inspect
    src = inspect.getsource(J.rank)
    assert 'forced_criteria = dict(criteria)' in src
    assert src.index('forced_criteria = dict(criteria)') < src.index('criteria[ABSTAIN]'), \
        'forced_criteria was copied AFTER the abstain option was added to it'


def test_a_forced_pick_is_returned_even_when_every_name_is_hopeless():
    pick, gaps = J._forced(ranked_answer({'AAA.TO': 0.02, 'BBB.TO': 0.01}, 0.0),
                           {'AAA.TO', 'BBB.TO'})
    assert pick is not None and pick['ticker'] == 'AAA.TO'
    assert pick['forced'] is True


def test_an_abstain_smuggled_into_the_forced_answer_is_refused():
    """It was never offered. A name we did not put in the option set must not
    reach the owner — that typing is the reason to use this provider."""
    pick, gaps = J._forced(
        {'type': 'choice', 'probabilities': {'AAA.TO': 0.3, J.ABSTAIN: 0.9}},
        {'AAA.TO'})
    assert pick['ticker'] == 'AAA.TO', 'the abstain won a question it was not on'
    assert any('abstain it was not offered' in g for g in gaps)


def test_a_name_outside_the_universe_never_becomes_the_forced_pick():
    pick, gaps = J._forced(
        {'type': 'choice', 'probabilities': {'GHOST.TO': 0.99, 'AAA.TO': 0.10}},
        {'AAA.TO'})
    assert pick['ticker'] == 'AAA.TO'
    assert any('invalid option' in g for g in gaps)


def test_the_forced_pick_never_enters_the_gated_selection():
    """The two must not merge. `_forced` has no code path into longs/shorts,
    and a forced pick below the abstain floor is exactly the case where
    conflating them would turn 'I would rather do nothing' into a pick."""
    picks, ranked, _ = J._side(ranked_answer({'AAA.TO': 0.10}, 0.80), {'AAA.TO'})
    forced, _ = J._forced(ranked_answer({'AAA.TO': 0.10}, 0.0), {'AAA.TO'})
    assert picks == [], 'the gate must still decline'
    assert forced['ticker'] == 'AAA.TO', 'the forced question must still answer'


def test_an_unavailable_result_still_carries_the_forced_keys():
    """A reader that does `snap['forced_long']` must not KeyError on the one
    day the provider is down."""
    out = J.unavailable('provider down')
    for key in ('forced_long', 'forced_short', 'long_ranked', 'short_ranked'):
        assert key in out


def test_both_renderers_print_the_forced_pick_and_say_it_is_not_the_selection():
    import daily_render, report_page
    snap = {'status': 'NO_OPPORTUNITY', 'model': 'typesafe/jev-1.13', 'considered': 78,
            'longs': [], 'shorts': [], 'long_ranked': [], 'short_ranked': [],
            'forced_label': J.FORCED_LABEL,
            'forced_long': {'ticker': 'AAA.TO', 'probability': 0.31,
                            'gated_abstain_probability': 0.62,
                            'cleared_gated_abstain': False, 'forced': True},
            'forced_short': {'ticker': 'BBB.TO', 'probability': 0.71,
                             'gated_abstain_probability': 0.40,
                             'cleared_gated_abstain': True, 'forced': True}}
    text = '\n'.join(daily_render.jev_summary({'jev': snap}))
    assert 'AAA.TO' in text and 'BBB.TO' in text
    assert 'NOT the selection' in text
    assert 'would rather have done nothing' in text
    html = report_page._jev_section({'jev': snap})
    assert 'AAA.TO' in html and 'Forced choice' in html
    assert 'would rather have done nothing' in html
