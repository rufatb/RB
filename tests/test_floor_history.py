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
