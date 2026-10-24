"""Day-140's fix pack (fixpack.py) in shadow: the abstention gate, the
sector cap, the frozen Round-1 ballots scored apart, and the paired
record — all on synthetic council snapshots, no network."""
import datetime as dt
import json

import pandas as pd
import pytest

import council as K
import fixpack as F

ET = F.ET
S = dt.date(2026, 10, 2)                     # a Friday
NOW = dt.datetime(2026, 10, 2, 9, 33, tzinfo=ET)


def pos(pid, ticker, side, invalid=100.0, conf=0.6, how='selected', model='claude'):
    return {'id': pid, 'ticker': ticker, 'side': side, 'invalid_at': invalid,
            'lead': 'Claude', 'reason': 'r',
            'proposers': [{'model': model, 'how': how, 'confidence': conf,
                           'reason': 'r', 'invalid_at': invalid, 'seat': 'A'}]}


def ballot(votes, top=()):
    return {'votes': {pid: {'stance': s, 'conviction': c, 'argument': 'a'}
                      for pid, (s, c) in votes.items()},
            'top_two': list(top)}


# ── the gate ────────────────────────────────────────────────────────────────

def test_the_gate_needs_a_wrong_if_and_a_dated_catalyst():
    assert F.gate(pos('P1', 'AAA.TO', 'LONG'), 3) == (True, '')
    ok, why = F.gate(pos('P1', 'AAA.TO', 'LONG', invalid=None), 3)
    assert not ok and 'wrong-if' in why
    ok, why = F.gate(pos('P1', 'AAA.TO', 'LONG'), 9)
    assert not ok and 'catalyst' in why
    ok, why = F.gate(pos('P1', 'AAA.TO', 'LONG', invalid=None), None)
    assert not ok and 'wrong-if' in why and 'catalyst' in why


def test_ranking_prefers_selected_support_then_confidence():
    a = pos('P1', 'AAA.TO', 'LONG', conf=0.55)
    b = pos('P2', 'BBB.TO', 'LONG', conf=0.9, how='nominated', model='gemini')
    picks, _ = F.select_shadow([b, a], {'AAA.TO': {'days_to_earnings': 2},
                                        'BBB.TO': {'days_to_earnings': 2}}, {})
    assert [p['ticker'] for p in picks] == ['AAA.TO', 'BBB.TO']
    assert picks[0]['rank'] == 1 and picks[1]['rank'] == 2


def test_the_sector_cap_holds_one_per_sector_per_side_but_not_across_sides():
    a = pos('P1', 'AAA.TO', 'LONG')
    b = pos('P2', 'BBB.TO', 'LONG', conf=0.7, model='deepseek')
    c = pos('P3', 'CCC.TO', 'SHORT', conf=0.65, model='gemini')
    rows = {t: {'days_to_earnings': 1, 'sector': 'Energy'} for t in ('AAA.TO', 'BBB.TO', 'CCC.TO')}
    picks, verdicts = F.select_shadow([a, b, c], rows, {})
    assert [(p['ticker'], p['side']) for p in picks] == [('BBB.TO', 'LONG'), ('CCC.TO', 'SHORT')]
    capped = [v for v in verdicts if v['ticker'] == 'AAA.TO'][0]
    assert capped['gate'] == 'pass' and 'sector cap' in capped['reason']


def test_an_abstention_is_a_verdict_not_a_pick():
    a = pos('P1', 'AAA.TO', 'LONG', invalid=None)
    picks, verdicts = F.select_shadow([a], {'AAA.TO': {'days_to_earnings': 1}}, {})
    assert picks == [] and verdicts[0]['gate'] == 'abstain'


# ── Round 1 on its own ──────────────────────────────────────────────────────

def test_round1_top2_uses_the_councils_own_tally_on_the_blind_ballots():
    table = [pos('P1', 'AAA.TO', 'LONG'), pos('P2', 'BBB.TO', 'SHORT')]
    r1 = {'DeepSeek': ballot({'P1': ('ENDORSE', 0.7), 'P2': ('OPPOSE', 0.6)}, top=['P1']),
          'Gemini': ballot({'P1': ('ENDORSE', 0.6), 'P2': ('ABSTAIN', None)}, top=['P1'])}
    got = F.round1_top2(table, r1)
    assert [(p['ticker'], p['side']) for p in got] == [('AAA.TO', 'LONG')]
    assert F.round1_top2(table, {}) == []


# ── staging ─────────────────────────────────────────────────────────────────

def snapshot(table, picks, round1):
    return {'session': S.isoformat(), 'status': 'READY', 'positions': table,
            'picks': picks, 'rounds': {'round1': round1, 'round2': {}},
            'tally': {'members': ['DeepSeek', 'Gemini'], 'rows': []}}


@pytest.fixture
def staged(tmp_path, monkeypatch):
    table = [pos('P1', 'AAA.TO', 'LONG', conf=0.7),
             pos('P2', 'BBB.TO', 'LONG', invalid=None, conf=0.9, model='deepseek'),
             pos('P3', 'CCC.TO', 'SHORT', conf=0.6, model='gemini')]
    r1 = {'DeepSeek': ballot({'P1': ('ENDORSE', 0.7), 'P2': ('ENDORSE', 0.8),
                              'P3': ('ENDORSE', 0.6)}, top=['P2']),
          'Gemini': ballot({'P1': ('ENDORSE', 0.6), 'P2': ('ABSTAIN', None),
                            'P3': ('ENDORSE', 0.7)}, top=['P1', 'P3'])}
    (tmp_path / K.SNAPSHOT).write_text(json.dumps(snapshot(table, ['P2'], r1)))
    monkeypatch.setattr(F, '_evidence', lambda sd, now, tickers: {
        'AAA.TO': {'days_to_earnings': 2, 'sector': 'Energy', 'rel_sector_pct': 1.2},
        'BBB.TO': {'days_to_earnings': 2, 'sector': 'Energy', 'rel_sector_pct': 0.4},
        'CCC.TO': {'days_to_earnings': 1, 'sector': 'Banks', 'rel_sector_pct': 0.9}})
    return tmp_path


def test_stage_records_the_shadow_the_live_and_round1(staged, tmp_path):
    ledger, r1ledger = tmp_path / 'shadow.csv', tmp_path / 'round1.csv'
    out = F.stage(staged, now=NOW, path=ledger, r1_path=r1ledger)
    assert out['status'] == 'RECORDED' and out['abstentions'] == 1
    # BBB fails the gate (no wrong-if) even though the live council picked it;
    # AAA passes and CCC passes on the other side of another sector.
    assert out['shadow'] == [('LONG', 'AAA.TO'), ('SHORT', 'CCC.TO')]
    assert out['live'] == [('LONG', 'BBB.TO')]
    rows = F.read(ledger)
    gates = {(r['ticker'], r['side']): r for r in rows if r['kind'] == 'gate'}
    assert gates[('BBB.TO', 'LONG')]['gate'] == 'abstain'
    assert 'wrong-if' in gates[('BBB.TO', 'LONG')]['reason']
    votes = F.read(r1ledger)
    assert len(votes) == 6
    assert {(v['model'], v['ticker']): v['stance'] for v in votes}[('Gemini', 'BBB.TO')] == 'ABSTAIN'
    # a rerun adds nothing
    again = F.stage(staged, now=NOW, path=ledger, r1_path=r1ledger)
    assert again['added'] == 0 and again['ballots_added'] == 0
    assert len(F.read(ledger)) == len(rows)


def test_stage_without_a_council_costs_nothing(staged, tmp_path):
    (tmp_path / K.SNAPSHOT).write_text(json.dumps({'session': '1999-01-01', 'positions': []}))
    out = F.stage(staged, now=NOW, path=tmp_path / 's.csv', r1_path=tmp_path / 'r.csv')
    assert out['status'] == 'NO_COUNCIL' and not (tmp_path / 's.csv').exists()


# ── scoring and the paired record ───────────────────────────────────────────

def daily(n=30, close=10.0, last=S, open_=None, final=None):
    days = pd.bdate_range(end=pd.Timestamp(last), periods=n, tz='America/Toronto')
    f = pd.DataFrame({'Open': close, 'High': close, 'Low': close, 'Close': close,
                      'Volume': 1_000_000}, index=days, dtype=float)
    if open_ is not None:
        f.iloc[-1, f.columns.get_loc('Open')] = open_
    if final is not None:
        f.iloc[-1, f.columns.get_loc('Close')] = final
    return f


def test_score_fills_y_on_the_registered_yardstick(tmp_path):
    ledger = tmp_path / 'shadow.csv'
    F._write([{'session': S.isoformat(), 'kind': 'shadow', 'ticker': 'AAA.TO', 'side': 'LONG'},
              {'session': S.isoformat(), 'kind': 'live', 'ticker': 'BBB.TO', 'side': 'SHORT'}],
             ledger, F.FIELDS)
    frames = {'AAA.TO': daily(open_=10.0, final=11.0), 'BBB.TO': daily(open_=20.0, final=19.0),
              F.MARKET: daily(close=40.0)}
    n = F.score(path=ledger, now=dt.datetime(2026, 10, 2, 17, 0, tzinfo=ET),
                chart=lambda t: ({}, frames[t]))
    assert n == 2
    rows = {(r['kind']): r for r in F.read(ledger)}
    assert float(rows['shadow']['y']) == pytest.approx(10.0 - F.COST)   # +10% vs a flat XIU
    assert float(rows['live']['y']) == pytest.approx(5.0 - F.COST)      # a short into a 5% fall


def test_the_paired_record_counts_a_shadow_that_stood_aside_as_zero(tmp_path):
    ledger = tmp_path / 'shadow.csv'
    F._write([
        {'session': '2026-10-01', 'kind': 'shadow', 'ticker': 'AAA.TO', 'side': 'LONG', 'y': 1.0},
        {'session': '2026-10-01', 'kind': 'live', 'ticker': 'BBB.TO', 'side': 'LONG', 'y': 0.5},
        {'session': '2026-10-01', 'kind': 'round1', 'ticker': 'AAA.TO', 'side': 'LONG', 'y': 0.25},
        {'session': '2026-10-02', 'kind': 'live', 'ticker': 'CCC.TO', 'side': 'SHORT', 'y': -1.0},
        {'session': '2026-10-02', 'kind': 'gate', 'ticker': 'DDD.TO', 'side': 'LONG',
         'gate': 'abstain', 'reason': 'no dated catalyst (earnings within 5 sessions)'},
    ], ledger, F.FIELDS)
    r = F.record(ledger)
    assert r['sessions'] == 2
    assert r['paired_diff'] == pytest.approx((0.5 + 1.0) / 2)     # day 2: 0 - (-1.0)
    assert r['deliberation_delta'] == pytest.approx(0.5 - 0.25)   # only day 1 has a Round-1 pick
    assert r['abstentions'] == 1
    assert '2 paired session(s)' in F.line(ledger)
