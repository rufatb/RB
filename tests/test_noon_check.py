"""The noon check (day-130): where the council's picks stand at 12:00 ET."""
import datetime as dt
import json

import pandas as pd

import noon_check as N

ET = N.ET
DAY = dt.date(2026, 10, 13)
NOON = dt.datetime(2026, 10, 13, 12, 1, tzinfo=ET)


def bars(prices, low=None, high=None):
    """5-minute bars from 09:30 to 11:55 with closes walking through `prices`."""
    t = dt.datetime.combine(DAY, dt.time(9, 30), tzinfo=ET)
    idx, rows = [], []
    for i in range(30):
        c = prices[min(i, len(prices) - 1)]
        idx.append(t + dt.timedelta(minutes=5 * i))
        rows.append({'Open': c, 'High': high if (high and i == 10) else c,
                     'Low': low if (low and i == 10) else c, 'Close': c})
    return pd.DataFrame(rows, index=pd.DatetimeIndex(idx))


def report(tmp_path, picks, runner=None, session='2026-10-13'):
    (tmp_path/'latest').mkdir(exist_ok=True)
    sec = {'council': True, 'picks': picks, 'runner_up': runner}
    (tmp_path/'latest'/'report.json').write_text(json.dumps({'session': session, 'intraday': {'top_two': sec}}))


PICK = {'side': 'LONG', 'ticker': 'TD.TO', 'invalid_at': 99.0, 'agreement': '3 of 4 endorse'}


def feed(table):
    def f(t):
        return table[t]
    return f


def test_waits_for_noon_then_reports_since_the_0945_entry(tmp_path):
    report(tmp_path, [PICK])
    fb = feed({'TD.TO': bars([100, 100, 100, 101]), 'XFN.TO': bars([50, 50, 50, 50.5])})
    assert N.prepare(tmp_path, NOON.replace(hour=11, minute=30), bars_for=fb)[0] == 'WAITING'
    status, info = N.prepare(tmp_path, NOON, bars_for=fb)
    assert status == 'READY' and info['subject'] == 'RB Noon Check — 2026-10-13 — LONG TD.TO +1.00%'
    text = (tmp_path/'noon'/'report.txt').read_text()
    assert '| LONG TD.TO | +1.00% (101 at 12:00) | below 99 | no | XFN.TO +1.00% |' in text
    assert 'Exit note (day-130 test)' in text and 'nothing here changes it' in text


def test_a_crossed_wrong_if_is_said_in_the_subject(tmp_path):
    report(tmp_path, [PICK])
    fb = feed({'TD.TO': bars([100, 100, 100, 99.5], low=98.0), 'XFN.TO': bars([50])})
    assert N.prepare(tmp_path, NOON, bars_for=fb)[1]['subject'].endswith('LONG TD.TO -0.50% (wrong if crossed)')


def test_the_runner_up_is_labelled_and_a_failed_name_is_not_checked(tmp_path):
    runner = {'side': 'SHORT', 'ticker': 'CVE.TO', 'invalid_at': 45.8, 'runner_up': True}
    report(tmp_path, [PICK], runner)

    def fb(t):
        if t == 'CVE.TO':
            raise RuntimeError('429')
        return bars([100, 100, 100, 100.5])
    status, info = N.prepare(tmp_path, NOON, bars_for=fb)
    assert 'runner-up SHORT CVE.TO NOT CHECKED' in info['subject']
    assert '| SHORT CVE.TO (runner-up, not a pick) | NOT CHECKED (RuntimeError)' in \
        (tmp_path/'noon'/'report.txt').read_text()


def test_nothing_without_a_pick_once_a_day_and_never_late(tmp_path):
    report(tmp_path, [])
    assert N.prepare(tmp_path, NOON)[0] == 'NOTHING'
    report(tmp_path, [PICK], session='2026-10-09')          # yesterday's report is not today's
    assert N.prepare(tmp_path, NOON)[0] == 'NOTHING'
    report(tmp_path, [PICK])
    assert N.prepare(tmp_path, NOON.replace(hour=13, minute=31))[0] == 'TOO_LATE'
    N.record(tmp_path, 'abc', now=NOON)
    assert N.wait(tmp_path, 0, now_fn=lambda: NOON)[0] == 4
