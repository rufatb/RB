"""Day-154 (PREREGISTER_day154_floor_history.md): the population pin, on
synthetic files only. No real record or return is read here."""
import csv
import json
import sqlite3

import floor_history as F


def test_the_floor_is_the_live_rule():
    assert F.floor_kept(0.50, 0) and F.floor_kept(0.62, None)
    assert F.floor_kept(0.35, 2) and F.floor_kept(0.10, 4)
    assert not F.floor_kept(0.49, 1) and not F.floor_kept(None, None)
    assert not F.floor_kept(0.40, None)            # off the table: confidence leg only


def _ledger(tmp_path, rows):
    path = tmp_path / 'picks.csv'
    cols = ['session', 'model', 'kind', 'side', 'ticker', 'confidence', 'r_pct']
    with open(path, 'w', newline='') as fh:
        w = csv.DictWriter(fh, fieldnames=cols)
        w.writeheader()
        for r in rows:
            w.writerow(r)
    return path


def test_the_pin_takes_claudes_nominations_once_and_reads_no_return(tmp_path):
    rows = [
        {'session': '2026-10-14', 'model': 'claude', 'kind': 'nominated', 'side': 'LONG', 'ticker': 'AAA.TO', 'confidence': '0.42', 'r_pct': '9.9'},
        {'session': '2026-10-14', 'model': 'claude', 'kind': 'nominated', 'side': 'LONG', 'ticker': 'AAA.TO', 'confidence': '0.42', 'r_pct': '9.9'},
        {'session': '2026-10-14', 'model': 'deepseek', 'kind': 'nominated', 'side': 'LONG', 'ticker': 'BBB.TO', 'confidence': '0.9', 'r_pct': '1'},
        {'session': '2026-10-14', 'model': 'claude', 'kind': 'selected', 'side': 'LONG', 'ticker': 'CCC.TO', 'confidence': '0.9', 'r_pct': '1'},
        {'session': '2026-11-12', 'model': 'claude', 'kind': 'nominated', 'side': 'SHORT', 'ticker': 'DDD.TO', 'confidence': '0.30', 'r_pct': '-2'},
        {'session': '2026-10-22', 'model': 'claude', 'kind': 'nominated', 'side': 'SHORT', 'ticker': 'EEE.TO', 'confidence': '0.60', 'r_pct': '0'},
        {'session': '2026-11-20', 'model': 'claude', 'kind': 'nominated', 'side': 'SHORT', 'ticker': 'FFF.TO', 'confidence': '0.60', 'r_pct': '0'},
    ]
    ledger = _ledger(tmp_path, rows)
    veto = tmp_path / 'veto.json'
    veto.write_text(json.dumps({'positions': [
        {'session': '2026-10-14', 'ticker': 'AAA.TO', 'side': 'LONG', 'endorse': 2, 'oppose': 1, 'members': 4}]}))
    db = tmp_path / 'reports.sqlite3'
    con = sqlite3.connect(str(db))
    con.execute('create table reports (session text, body text, sha256 text)')
    body = {'intraday': {'council': {'tally': {'rows': [
        {'ticker': 'DDD.TO', 'side': 'SHORT', 'endorse': ['DeepSeek'], 'oppose': ['Gemini', 'Jev'],
         'seats': ['A', 'B', 'C', 'D']}]}}}}
    con.execute('insert into reports values (?, ?, ?)', ('2026-11-12', json.dumps(body), 'x'))
    con.commit()
    con.close()
    out = F.pin(ledger, veto, db)
    ps = out['positions']
    assert [(p['session'], p['ticker']) for p in ps] == [('2026-10-14', 'AAA.TO'), ('2026-11-12', 'DDD.TO')]
    assert ps[0]['kept'] and ps[0]['endorse'] == 2 and ps[0]['source'] == 'day148_pin'
    assert not ps[1]['kept'] and ps[1]['endorse'] == 1 and ps[1]['source'] == 'frozen_report'
    assert out['sessions_without_tally'] == ['2026-10-22']
    assert all('r_pct' not in p for p in ps)        # no outcome travels into the pin


# ── the run code (synthetic only; no real return is read) ───────────────────

import random as _random


def _picks(n_sessions, edge, noise, seed=1):
    rng = _random.Random(seed)
    out = []
    for i in range(n_sessions):
        s = '2026-%02d-%02d' % (1 + i // 28, 1 + i % 28)
        for j in range(4):
            kept = j < 3
            y = rng.gauss(edge if kept else 0.0, noise)
            out.append({'session': s, 'ticker': 'N%d.TO' % j, 'side': 'LONG' if j % 2 else 'SHORT',
                        'confidence': 0.6 if kept else 0.3, 'endorse': 2 if kept else 1,
                        'kept': kept, 'y': y, 'rank': 1 + j % 2})
    return out


def test_a_large_sorting_edge_reads_sorts():
    got = F.verdict(_picks(120, 1.5, 1.0), draws=200)
    assert got['status'] == 'SORTS' and got['control']['detected']
    assert got['mde80'] is not None and got['mde80'] > 0


def test_dropped_beating_kept_reads_removes_winners():
    got = F.verdict(_picks(120, -1.0, 1.0), draws=200)
    assert got['status'] == 'REMOVES_WINNERS' and got['removes_winners']


def test_a_small_noisy_sample_is_underpowered_not_null():
    got = F.verdict(_picks(6, 0.0, 3.0), draws=200)
    assert got['status'] == 'UNDERPOWERED' and not got['control']['detected']


def test_the_control_measures_edge_over_se_not_mean_over_se():
    picks = _picks(120, 5.0, 1.0)               # a huge real mean must not inflate the control
    d, t = F.control(picks)
    assert abs(d - F.PLANT) < 1e-9
    centred = F.control(_picks(120, 0.0, 1.0))
    assert abs(t - centred[1]) < 1e-6


def test_outcomes_take_the_pinned_row_and_its_order(tmp_path):
    rows = [
        {'session': '2026-10-14', 'model': 'claude', 'kind': 'nominated', 'side': 'LONG', 'ticker': 'AAA.TO', 'confidence': '0.4', 'r_pct': '1.5'},
        {'session': '2026-10-14', 'model': 'claude', 'kind': 'nominated', 'side': 'LONG', 'ticker': 'BBB.TO', 'confidence': '0.3', 'r_pct': ''},
        {'session': '2026-10-14', 'model': 'claude', 'kind': 'nominated', 'side': 'LONG', 'ticker': 'AAA.TO', 'confidence': '0.4', 'r_pct': '9'},
        {'session': '2026-10-14', 'model': 'claude', 'kind': 'nominated', 'side': 'SHORT', 'ticker': 'CCC.TO', 'confidence': '0.6', 'r_pct': '-0.5'},
    ]
    outs = F.outcomes(_ledger(tmp_path, rows))
    assert outs[('2026-10-14', 'AAA.TO', 'LONG')] == (1.5, 1)
    assert outs[('2026-10-14', 'BBB.TO', 'LONG')] == (None, 2)
    assert outs[('2026-10-14', 'CCC.TO', 'SHORT')] == (-0.5, 1)
    pos = [{'session': '2026-10-14', 'ticker': t, 'side': s, 'kept': True}
           for t, s in (('AAA.TO', 'LONG'), ('BBB.TO', 'LONG'))]
    scored, unscored = F.join(pos, outs)
    assert [p['ticker'] for p in scored] == ['AAA.TO'] and [p['ticker'] for p in unscored] == ['BBB.TO']
