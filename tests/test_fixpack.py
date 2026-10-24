"""Day-140's fix pack (PREREGISTER_day140_fixpack.md): a stop within reach on
the live Top 2, Round 1 against the deliberated council, and the facts
recorded beside them — on synthetic records, no network."""
import datetime as dt
import json
import sqlite3
from pathlib import Path

import pandas as pd
import pytest

import fixpack as F

ET = F.ET
ROOT = Path(__file__).resolve().parent.parent
SECTORS = {'AAA.TO': {'sector': 'Energy', 'industry': 'Oil & Gas Integrated'},
           'BBB.TO': {'sector': 'Energy', 'industry': 'Oil & Gas Integrated'},
           'CCC.TO': {'sector': 'Financial Services', 'industry': 'Banks - Diversified'}}


def live(session, ticker, side, invalid=None, entry=100.0, r=None):
    return {'session': session, 'model': 'top2', 'kind': 'pick', 'ticker': ticker,
            'side': side, 'invalid_at': '' if invalid is None else str(invalid),
            'entry': '' if entry is None else str(entry), 'r_pct': '' if r is None else str(r)}


def table_row(session, ticker, side, r, model='deepseek', kind='nominated'):
    return {'session': session, 'model': model, 'kind': kind, 'ticker': ticker, 'side': side,
            'invalid_at': '', 'entry': '100', 'r_pct': str(r)}


def ballot(votes, top=()):
    return {'votes': {pid: {'stance': s, 'conviction': c, 'argument': 'a'}
                      for pid, (s, c) in votes.items()}, 'top_two': list(top)}


def council(r1, picks, positions=None):
    positions = positions or [
        {'id': 'P1', 'ticker': 'AAA.TO', 'side': 'LONG', 'invalid_at': 99.0, 'proposers': []},
        {'id': 'P2', 'ticker': 'BBB.TO', 'side': 'SHORT', 'invalid_at': None, 'proposers': []},
        {'id': 'P3', 'ticker': 'CCC.TO', 'side': 'LONG', 'invalid_at': 50.0, 'proposers': []}]
    return {'intraday': {'council': {'positions': positions, 'picks': picks,
                                     'rounds': {'round1': r1, 'round2': {}}}}}


# ── the gate ────────────────────────────────────────────────────────────────

def test_the_gate_is_the_open_checks_reach_rule():
    assert F.gate('LONG', 99.0, 100.0, 2.0) == ('kept', '', 0.5)
    assert F.gate('SHORT', 101.5, 100.0, 2.0) == ('kept', '', 0.75)
    g, why, days = F.gate('LONG', 96.0, 100.0, 2.0)
    assert g == 'dropped' and days == 2.0 and '2.0 normal days away' in why
    assert F.gate('SHORT', None, 100.0, 2.0)[:2] == ('dropped', 'no wrong-if')
    assert F.gate('LONG', 101.0, 100.0, 2.0)[0] == 'dropped'          # already crossed
    assert F.gate('LONG', 99.0, None, 2.0)[:2] == ('', 'not scored yet')
    assert F.gate('LONG', 99.0, 100.0, None)[:2] == ('', 'no ATR for the name')


def test_round1_is_the_frozen_tally_over_the_two_blind_ballots():
    r1 = {'DeepSeek': ballot({'P1': ('ENDORSE', 0.7), 'P2': ('ENDORSE', 0.6), 'P3': ('ABSTAIN', None)}),
          'Gemini': ballot({'P1': ('ENDORSE', 0.6), 'P2': ('OPPOSE', 0.6), 'P3': ('ENDORSE', 0.8)})}
    c = council(r1, ['P3'])['intraday']['council']
    assert [(p['side'], p['ticker']) for p in F.round1_picks(c)] == [('LONG', 'AAA.TO')]
    assert [(p['side'], p['ticker']) for p in F.final_picks(c)] == [('LONG', 'CCC.TO')]
    # one blind ballot is no Round 1: nobody can reach consensus alone
    assert F.round1_picks({**c, 'rounds': {'round1': {'DeepSeek': r1['DeepSeek']}}}) == []


# ── recording ───────────────────────────────────────────────────────────────

S = '2026-10-26'


def wire(tmp_path, ticker):
    root = tmp_path / 'wire'
    root.mkdir()
    (root / f'{S}.jsonl').write_text(json.dumps(
        {'published_at': '2026-10-26T07:00:00-04:00', 'tickers': [ticker], 'title': 'T',
         'source': 'newswire.ca', 'url': 'https://www.newswire.ca/x.html'}) + '\n')
    return root


def recorded(tmp_path, picks_rows, report=None, **kw):
    path = tmp_path / 'fixpack.csv'
    got = F.record_session(S, report, picks_rows=picks_rows, path=path, sectors=SECTORS,
                           brief=kw.pop('brief', {'AAA.TO': {'atr_pct': 2.0, 'days_to_earnings': 3},
                                                  'BBB.TO': {'atr_pct': 2.0}}),
                           archive=kw.pop('archive', None), **kw)
    return got, path


def test_a_session_records_the_gate_the_two_arms_and_the_facts(tmp_path):
    rows = [live(S, 'AAA.TO', 'LONG', invalid=99.0), live(S, 'BBB.TO', 'SHORT', invalid=104.0)]
    r1 = {'DeepSeek': ballot({'P1': ('ENDORSE', 0.7), 'P2': ('ABSTAIN', None), 'P3': ('ABSTAIN', None)}),
          'Gemini': ballot({'P1': ('ENDORSE', 0.6), 'P2': ('ABSTAIN', None), 'P3': ('ABSTAIN', None)})}
    got, path = recorded(tmp_path, rows, council(r1, ['P1', 'P2']), archive=wire(tmp_path, 'BBB.TO'))
    assert got['live'] == 2 and got['round1'] == 1 and got['final'] == 2 and got['council']
    led = {(r['kind'], r['ticker']): r for r in F.read(path)}
    a, b = led[('live', 'AAA.TO')], led[('live', 'BBB.TO')]
    assert a['gate'] == 'kept' and float(a['reach_atr']) == 0.5
    assert b['gate'] == 'dropped' and '2.0 normal days away' in b['reason']
    # the real sector map's entries are dicts; the fund is read from them
    assert a['etf'] == b['etf'] == 'XEG.TO' and a['period'] == 'test'
    assert a['earnings_days'] == '3' and b['earnings_days'] == ''
    assert a['wire_release'] == '0' and b['wire_release'] == '1'
    assert led[('round1', 'AAA.TO')]['rank'] == '1'
    # a rerun adds nothing
    assert F.record_session(S, council(r1, ['P1', 'P2']), picks_rows=rows, path=path,
                            sectors=SECTORS, brief={}, archive=None)['added'] == 0


def test_a_gate_waiting_on_its_entry_is_filled_later_and_never_rewritten(tmp_path):
    early = [live(S, 'AAA.TO', 'LONG', invalid=99.0, entry=None)]
    _, path = recorded(tmp_path, early)
    assert F.read(path)[0]['gate'] == '' and F.read(path)[0]['reason'] == 'not scored yet'
    scored = [live(S, 'AAA.TO', 'LONG', invalid=99.0, entry=100.0)]
    got = F.record_session(S, None, picks_rows=scored, path=path, sectors=SECTORS,
                           brief={'AAA.TO': {'atr_pct': 2.0}}, archive=None)
    assert got['added'] == 0 and got['filled'] >= 1
    r = F.read(path)[0]
    assert r['gate'] == 'kept' and r['reason'] == 'not scored yet'     # the first reason stands
    # a filled cell is never rewritten, whatever a later run computes
    F.record_session(S, None, picks_rows=[live(S, 'AAA.TO', 'LONG', invalid=90.0)], path=path,
                     sectors=SECTORS, brief={'AAA.TO': {'atr_pct': 2.0}}, archive=None)
    assert F.read(path)[0]['gate'] == 'kept' and F.read(path)[0]['invalid_at'] == '99.0'


def test_the_brief_atr_wins_over_the_frozen_copy_and_the_bars():
    rows = [live(S, 'AAA.TO', 'LONG', invalid=98.0)]
    rep = {'intraday': {'council': {'positions': [], 'picks': [],
                                    'moves': {'AAA.TO': {'atr_pct': 1.0}}}}}

    def gate_with(brief, atr):
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            F.record_session(S, rep, picks_rows=rows, path=Path(d) / 'f.csv', sectors=SECTORS,
                             brief=brief, atr=atr, archive=None)
            return F.read(Path(d) / 'f.csv')[0]['gate']
    assert gate_with({'AAA.TO': {'atr_pct': 4.0}}, {'AAA.TO': 1.0}) == 'kept'      # 2% is 0.5 ATR
    assert gate_with({}, {'AAA.TO': 4.0}) == 'dropped'                              # the frozen 1.0
    assert gate_with({}, None) == 'dropped'


def test_the_ledger_is_in_the_folder_the_evening_push_carries():
    import provenance
    assert F.LEDGER == ROOT / 'data' / 'reviews' / 'fixpack.csv'
    assert provenance.run_record('data/reviews/fixpack.csv')
    routine = (ROOT / 'ROUTINE_PROMPT.md').read_text()
    assert 'fixpack' not in (ROOT / 'morning_full.sh').read_text()   # nothing in the morning
    assert 'fixpack' not in routine


# ── the statistics ──────────────────────────────────────────────────────────

def test_the_two_group_t_clusters_by_session():
    diff, t = F.two_group([('s1', 1.0, True), ('s2', 3.0, True), ('s3', 0.0, False),
                           ('s4', 2.0, False)])
    assert diff == pytest.approx(1.0) and t == pytest.approx(1.0 / (4 / 3) ** 0.5)
    assert F.two_group([('s1', 1.0, True)]) == (None, None)


def planted(n, kept_mean, dropped_mean, *, dropped_every=2):
    out = []
    for i in range(n):
        s = '2026-11-%02d' % (i % 28 + 1) if i < 28 else '2026-12-%02d' % (i - 27)
        wobble = 0.1 * ((i % 5) - 2)
        kept = i % dropped_every != 0
        out.append((s, (kept_mean if kept else dropped_mean) + wobble, kept))
    return out


def test_arm_a_follows_the_registered_bar():
    v = F.arm_a(planted(40, 1.0, -1.0))
    assert v['status'] == 'PASS' and v['placebo_p'] < 0.01 and v['t'] > 3
    assert F.arm_a(planted(40, -0.5, 0.5))['status'] == 'FAIL'
    few = F.arm_a(planted(40, 1.0, -1.0, dropped_every=8))     # 5 dropped picks: too few
    assert few['dropped'] < F.MIN_GROUP and few['status'] == 'UNDERPOWERED'
    # the halves must agree
    flip = planted(20, 1.0, -1.0) + [(s.replace('2026-11', '2027-01'), y, g)
                                     for s, y, g in planted(20, -0.2, 0.2)]
    v = F.arm_a(flip)
    assert v['diff'] > 0 and v['halves'][1] < 0 and v['status'] == 'UNDERPOWERED'


def test_arm_b_is_two_sided():
    up = [0.5 + 0.05 * (i % 3) for i in range(40)]
    assert F.arm_b(up)['status'] == 'ADDS'
    assert F.arm_b([-x for x in up])['status'] == 'SUBTRACTS'
    noise = [0.3 if i % 2 else -0.3 for i in range(40)]
    assert F.arm_b(noise)['status'] == 'UNDERPOWERED'


# ── the verdict on a ledger ─────────────────────────────────────────────────

def ledger_for(tmp_path, n_sessions, kept_mean=1.0, dropped_mean=-1.0, period='test'):
    path = tmp_path / ('fixpack_%s_%d.csv' % (period, n_sessions))
    led, picks = [], []
    day = dt.date(2026, 10, 26)
    for i in range(n_sessions):
        s = (day + dt.timedelta(days=i)).isoformat()
        for j, (t, kept) in enumerate((('AAA.TO', True), ('BBB.TO', False))):
            led.append({'session': s, 'period': period, 'kind': 'live', 'ticker': t,
                        'side': 'LONG', 'gate': 'kept' if kept else 'dropped', 'rank': j + 1})
            picks.append(table_row(s, t, 'LONG', (kept_mean if kept else dropped_mean)
                                   + 0.1 * ((i % 5) - 2), model='top2', kind='pick'))
        for kind, t, y in (('round1', 'CCC.TO', 0.0), ('final', 'AAA.TO', None)):
            led.append({'session': s, 'period': period, 'kind': kind, 'ticker': t, 'side': 'LONG'})
            if y is not None:
                picks.append(table_row(s, t, 'LONG', y))
    F._write(led, path)
    return path, F.outcomes(picks)


def test_the_verdict_waits_for_forty_sessions_and_reads_only_the_test(tmp_path):
    path, outs = ledger_for(tmp_path, 39)
    v = F.verdict(path, outs)
    assert v['A']['status'] == 'NOT_DUE' and v['A']['sessions'] == 39
    assert v['B']['status'] == 'NOT_DUE'
    path, outs = ledger_for(tmp_path, 45)
    v = F.verdict(path, outs)
    assert v['A']['status'] == 'PASS' and v['A']['look'] == 40 and v['A']['sessions'] == 40
    assert v['B']['look'] == 40 and v['B']['status'] == 'ADDS'      # final +1.0 against Round 1's 0
    before, outs = ledger_for(tmp_path, 45, period='before')
    assert F.verdict(before, outs)['A']['status'] == 'NOT_DUE'
    line = F.line(path, outs)
    assert 'decision on the first 40: PASS' in line and 'ADDS' in line


def test_the_recorded_facts_count_the_sector_cap_and_identical_sessions(tmp_path):
    led = [{'session': S, 'period': 'test', 'kind': 'live', 'ticker': t, 'side': 'SHORT',
            'etf': 'XEG.TO', 'gate': 'kept', 'invalid_at': '1'} for t in ('AAA.TO', 'BBB.TO')]
    led += [{'session': S, 'period': 'test', 'kind': k, 'ticker': 'AAA.TO', 'side': 'SHORT'}
            for k in ('round1', 'final')]
    path = tmp_path / 'f.csv'
    F._write(led, path)
    outs = F.outcomes([table_row(S, 'AAA.TO', 'SHORT', 0.4, model='top2', kind='pick'),
                       table_row(S, 'BBB.TO', 'SHORT', -0.2, model='top2', kind='pick')])
    d = F.describe(path, outs)
    assert d['cap_binds'] == 1 and d['b_sessions'] == 1 and d['b_same'] == 1
    assert d['any_level']['yes'] == 2 and d['gate']['yes'] == 2


# ── the review's block ──────────────────────────────────────────────────────

def test_the_review_block_records_and_prints_and_never_raises(tmp_path):
    rows = [live(S, 'AAA.TO', 'LONG', invalid=99.0, r=0.8)]
    text = F.section(S, council({}, []), path=tmp_path / 'f.csv', state_dir=tmp_path,
                     picks_rows=rows)
    assert 'day-140' in text and 'LONG AAA.TO' in text
    assert 'not judged yet (no ATR for the name)' in text            # no brief in tmp_path
    broken = F.section(S, {'intraday': {'council': {'positions': 'not a list', 'picks': ['P1']}}},
                       path=tmp_path / 'g.csv', state_dir=tmp_path, picks_rows=rows)
    assert 'unavailable' in broken or 'day-140' in broken


def test_the_review_calls_it_with_the_frozen_report(monkeypatch):
    import daily_review as dr
    seen = {}
    import fixpack
    monkeypatch.setattr(fixpack, 'section', lambda session, report: seen.update(
        session=session, report=report) or 'ok')
    assert dr.fixpack_section('2026-10-26', {'session': '2026-10-26'}) == 'ok'
    assert seen == {'session': '2026-10-26', 'report': {'session': '2026-10-26'}}


# ── the councils before the test ────────────────────────────────────────────

def test_the_backfill_records_only_the_councils_before_the_test(tmp_path, monkeypatch):
    db = tmp_path / 'reports.sqlite3'
    con = sqlite3.connect(db)
    con.execute('create table reports (session text, body text)')
    r1 = {'DeepSeek': ballot({'P1': ('ENDORSE', 0.7)}), 'Gemini': ballot({'P1': ('ENDORSE', 0.6)})}
    pos = [{'id': 'P1', 'ticker': 'AAA.TO', 'side': 'LONG', 'invalid_at': 99.0, 'proposers': []}]
    for s in ('2026-10-15', '2026-10-26'):
        body = council(r1, ['P1'], pos)
        body['session'] = s
        con.execute('insert into reports values (?, ?)', (s, json.dumps(body)))
    con.commit()
    import model_picks
    monkeypatch.setattr(model_picks, 'read', lambda path=None: [
        live('2026-10-15', 'AAA.TO', 'LONG', invalid=99.0, r=0.5),
        live('2026-10-26', 'AAA.TO', 'LONG', invalid=99.0, r=0.5)])
    days = pd.bdate_range(end=pd.Timestamp('2026-10-14'), periods=60, tz='America/Toronto')
    frame = pd.DataFrame({'Open': 100.0, 'High': 101.0, 'Low': 99.0, 'Close': 100.0,
                          'Volume': 1e6}, index=days)
    import exposure
    monkeypatch.setattr(exposure, 'load_sectors', lambda path=None: SECTORS)
    done = F.backfill(db, path=tmp_path / 'f.csv', chart=lambda t: ({}, frame))
    assert [d['session'] for d in done] == ['2026-10-15']
    led = F.read(tmp_path / 'f.csv')
    assert {r['period'] for r in led} == {'before'}
    r = [x for x in led if x['kind'] == 'live'][0]
    assert float(r['atr_pct']) == pytest.approx(2.0) and r['gate'] == 'kept'   # bars: TR 2 on 100


# ── the registration ────────────────────────────────────────────────────────

def test_the_constants_are_the_registered_ones():
    doc = (ROOT / 'PREREGISTER_day140_fixpack.md').read_text()
    assert (F.START, F.DECISION, F.FINAL, F.BAR, F.PLACEBO_P, F.DRAWS, F.SEED, F.MIN_GROUP,
            F.COST, F.CATALYST_SESSIONS) == ('2026-10-26', 40, 80, 3.0, 0.01, 2000, 140, 10,
                                             0.13, 5)
    for words in ('REGISTERED 2026-10-24', 'REACH_ATR', 't ≥ 3.0', 'p < 0.01', '2,000 draws, seed 140',
                  'at least 10 picks in each group', 'data/reviews/fixpack.csv',
                  'within 0–5 sessions', '40th qualifying session', 'the 80th'):
        assert words in doc, words
    import council_flash
    assert council_flash.REACH_ATR == 1.0
