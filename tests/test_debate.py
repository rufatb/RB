"""Part 5: the debate — proposals, cross-examination, adjudication, never padded."""
import datetime as dt
import json
from types import SimpleNamespace

import debate as D

ET = D.ET
NOW = dt.datetime(2026, 9, 29, 9, 30, tzinfo=ET)
DS = {'status': 'READY', 'longs': [{'ticker': 'AC.TO', 'confidence': .58, 'reason': 'broke out'}],
      'shorts': [{'ticker': 'SU.TO', 'confidence': .56, 'reason': 'oil down'}]}
JEV = {'status': 'NO_OPPORTUNITY', 'longs': [], 'shorts': [],
       'forced_long': {'ticker': 'AC.TO', 'probability': .4},
       'forced_short': {'ticker': 'K.TO', 'probability': .3}}
CL = {'status': 'READY', 'longs': [{'ticker': 'AC.TO', 'confidence': .6, 'reason': 'held vwap'}], 'shorts': []}


def fake_client(verdicts, finish='stop'):
    msg = SimpleNamespace(content=json.dumps({'verdicts': verdicts}))
    resp = SimpleNamespace(choices=[SimpleNamespace(message=msg, finish_reason=finish)])
    return SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=lambda **k: resp)))


def fake_poster(long_probs, short_probs):
    return lambda body, key, timeout: {'answers': {
        'long': {'type': 'choice', 'probabilities': long_probs},
        'short': {'type': 'choice', 'probabilities': short_probs}}}


def test_proposals_merge_proposers_and_keep_reasons():
    props = {(p['ticker'], p['side']): p for p in D.proposals(CL, DS, JEV)}
    assert set(props) == {('AC.TO', 'LONG'), ('SU.TO', 'SHORT'), ('K.TO', 'SHORT')}
    assert [x['model'] for x in props[('AC.TO', 'LONG')]['proposers']] == ['claude', 'deepseek', 'jev']
    assert 'Claude: held vwap' in props[('AC.TO', 'LONG')]['reasons']


def test_final_needs_a_keep_and_the_judge_above_its_none():
    props = D.proposals(CL, DS, JEV)
    client = fake_client([
        {'ticker': 'AC.TO', 'side': 'LONG', 'verdict': 'KEEP', 'confidence': .6, 'for': 'f', 'against': 'a'},
        {'ticker': 'SU.TO', 'side': 'SHORT', 'verdict': 'KEEP', 'confidence': .55, 'for': 'f', 'against': 'a'},
        {'ticker': 'K.TO', 'side': 'SHORT', 'verdict': 'REJECT', 'confidence': .4, 'for': 'f', 'against': 'a'}])
    rulings = D.cross_examine(props, [], client=client)
    judged = D.adjudicate(props, [], rulings, poster=fake_poster(
        {'AC.TO': .7, 'NONE': .3}, {'SU.TO': .2, 'K.TO': .5, 'NONE': .3}), key='k')
    final = D.finalize(props, rulings, judged)
    assert [(f['side'], f['ticker']) for f in final] == [('LONG', 'AC.TO')]   # SU below NONE, K rejected


def test_a_name_kept_on_both_sides_is_void():
    props = [{'ticker': 'AC.TO', 'side': s, 'proposers': [], 'reasons': []} for s in ('LONG', 'SHORT')]
    rulings = D.cross_examine(props, [], client=fake_client([
        {'ticker': 'AC.TO', 'side': 'LONG', 'verdict': 'KEEP'},
        {'ticker': 'AC.TO', 'side': 'SHORT', 'verdict': 'KEEP'}]))
    assert {v['verdict'] for v in rulings.values()} == {'REJECT'}


def test_run_never_raises_and_never_pads(monkeypatch):
    out = D.run(CL, DS, JEV, [], now=NOW, client=fake_client([], finish='length'))
    assert out['status'] == 'UNAVAILABLE' and out['final'] == [] and 'cross-examination' in out['reason']
    none = D.run({'status': 'UNAVAILABLE'}, {'status': 'UNAVAILABLE'}, {'status': 'UNAVAILABLE'}, [], now=NOW)
    assert none['status'] == 'NO_PROPOSALS' and none['final'] == []
    monkeypatch.setenv('OPENROUTER_API_KEY', 'k')
    empty = D.run(CL, DS, JEV, [], now=NOW, client=fake_client([]),
                  poster=fake_poster({'AC.TO': .1, 'NONE': .9}, {'SU.TO': .1, 'K.TO': .1, 'NONE': .8}))
    assert empty['status'] == 'READY' and empty['final'] == [] and 'finalized nothing' in empty['reason']
    assert 'No final pick today' in '\n'.join(D.lines({**empty, 'record': 'r'}))


def test_the_section_prints_its_replay_record_and_is_recorded():
    import model_picks
    line = D.replay_line()
    assert 'does NOT beat random' in line or 'passes the registered bar' in line
    sec = {'status': 'READY', 'prompt_version': D.PROMPT_VERSION, 'record': line, 'rulings': [],
           'final': [{'ticker': 'AC.TO', 'side': 'LONG', 'proposers': [{'model': 'deepseek'}],
                      'ruling': {'verdict': 'KEEP', 'confidence': .6, 'for': 'f', 'against': 'a'},
                      'jev_probability': .7, 'jev_none': .3}]}
    text = '\n'.join(D.lines(sec))
    assert '## Part 5 — The debate' in text and '| LONG AC.TO | DeepSeek | KEEP 0.60 | 0.70 vs 0.30 |' in text
    rows = model_picks.rows_from_report({'session': '2026-09-29', 'intraday': {'debate': sec}})
    assert [(r['model'], r['kind'], r['ticker']) for r in rows] == [('debate', 'final', 'AC.TO')]


def test_part_5_is_retired_and_an_older_publication_still_prints_it():
    """Owner, 2026-10-14 (day-132c): the debate is retired. A new publication
    carries no Part 5 and no scoreboard row; one published before still renders
    its section, because a frozen publication never changes."""
    import brief
    import email_render
    import primary_board
    import report_page
    from test_daily_pipeline import NOW as N0, services
    d = brief.build(now=N0, services=services())
    assert d['intraday'].get('debate') is None
    assert 'Part 5 — The debate' not in email_render.text(d)
    assert 'Part 5 — The debate' not in brief.render_text(d)
    assert 'Part 5 — The debate' not in report_page.render(d)
    assert 'Debate (final)' not in [r['source'] for r in primary_board.leaderboard({})]
    d['intraday']['debate'] = {'status': 'READY', 'final': [], 'reason': 'nothing survived'}
    assert '## Part 5 — The debate' in email_render.text(d)
    assert 'Part 5 — The debate' in report_page.render(d)


def test_the_morning_no_longer_stages_the_debate():
    from pathlib import Path
    text = Path(__file__).resolve().parents[1].joinpath('morning_full.sh').read_text()
    assert 'debate.py --stage' not in text and 'debate: retired' in text
