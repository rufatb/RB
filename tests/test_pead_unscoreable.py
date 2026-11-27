"""Day-156g: Part 4's LONG TC.TO read "still holding" from 11-09 to 11-27.

Its entry session had five-minute bars, the first at 10:10: no trade came in the
09:40 bar, the registered entry, so `score_one` returned None every evening and
`score` swallowed whatever else went wrong. Such a position is now marked
unscoreable once its session is over, and a failure is counted by name."""
import datetime as dt

import pandas as pd

import pead as P

ET = P.ET


def bars(day, times, px=10.0):
    return pd.DataFrame([{'Open': px, 'Close': px}] * len(times),
                        index=[pd.Timestamp(f'{day} {t}', tz=ET) for t in times])


def daily(n=12, end=dt.date(2026, 11, 27)):
    days = pd.bdate_range(end=end, periods=n)
    return pd.DataFrame({'Close': 10.0}, index=[pd.Timestamp(d, tz=ET) for d in days])


def ledger(tmp_path, *rows):
    path = tmp_path / 'pead.csv'
    P._write([{'entry_session': s, 'ticker': t, 'side': 'LONG', 'title': 'Results'} for s, t in rows], path)
    return path


EVENING = dt.datetime(2026, 11, 27, 16, 25, tzinfo=ET)


def test_no_trade_in_the_entry_bar_is_unscoreable_once_the_session_is_over(tmp_path):
    path = ledger(tmp_path, ('2026-11-09', 'TC.TO'))
    thin = bars('2026-11-09', ['10:10', '10:15', '15:55'])
    report = {}
    assert P.score(path, now=EVENING, bars_for=lambda t: thin, daily=lambda t: daily(), report=report) == 0
    assert report == {'scored': 0, 'unscoreable': 1, 'failed': {}}
    (row,) = P.read(path)
    assert row['unscoreable'] == 'NO_0940_BAR (first bar 10:10)' and not row['scored_at']
    # Marked once: never asked again, and never rewritten.
    asked = []
    P.score(path, now=EVENING, bars_for=lambda t: asked.append(t) or thin, daily=lambda t: daily())
    assert asked == [] and P.read(path)[0]['unscoreable'] == 'NO_0940_BAR (first bar 10:10)'


def test_during_the_entry_session_nothing_is_marked(tmp_path):
    path = ledger(tmp_path, ('2026-11-27', 'TC.TO'))
    morning = dt.datetime(2026, 11, 27, 10, 20, tzinfo=ET)
    report = {}
    P.score(path, now=morning, bars_for=lambda t: bars('2026-11-27', ['10:10', '10:15']),
            daily=lambda t: daily(), report=report)
    assert report['unscoreable'] == 0 and not P.read(path)[0]['unscoreable']
    # Bars only up to 09:35: the entry bar is not due yet, so it is simply not measured.
    assert P.score_one({'entry_session': '2026-11-27', 'side': 'LONG'},
                       bars('2026-11-27', ['09:30', '09:35']), daily()) is None


def test_a_failure_is_counted_by_name_and_asked_again(tmp_path):
    path = ledger(tmp_path, ('2026-11-09', 'TC.TO'))
    def broken(t):
        raise TimeoutError('slow')
    report = {}
    P.score(path, now=EVENING, bars_for=broken, daily=lambda t: daily(), report=report)
    assert report == {'scored': 0, 'unscoreable': 0, 'failed': {'TimeoutError': 1}}
    assert not P.read(path)[0]['unscoreable']


def test_part_4_says_not_scoreable_instead_of_still_holding(tmp_path):
    path = ledger(tmp_path, ('2026-11-09', 'TC.TO'), ('2026-11-26', 'RY.TO'))
    P.score(path, now=EVENING, bars_for=lambda t: bars('2026-11-09', ['10:10']) if t == 'TC.TO'
            else bars('2026-11-26', ['09:30', '09:40', '15:55']), daily=lambda t: daily())
    sec = P.section(tmp_path, EVENING, path=path)
    assert [h['ticker'] for h in sec['held']] == ['RY.TO']
    assert [h['ticker'] for h in sec['unscoreable']] == ['TC.TO']
    full = '\n'.join(P.lines(sec))
    assert 'Still holding: LONG RY.TO (since 2026-11-26).' in full
    assert 'Not scoreable: LONG TC.TO (entry session 2026-11-09; its first trade that day came at 10:10)' in full
    assert 'TC.TO' not in full.split('Not scoreable')[0]
    # The email shows what is held; the full report and the page keep the record.
    email = '\n'.join(P.lines(sec, concise=True))
    assert 'Still holding: LONG RY.TO (since 2026-11-26).' in email and 'TC.TO' not in email


def test_a_section_from_before_renders_as_it_did():
    old = {'status': 'READY', 'new': [], 'events_checked': 3,
           'held': [{'side': 'LONG', 'ticker': 'TC.TO', 'entry_session': '2026-11-09'}]}
    text = P.lines(old, concise=True)
    assert text[-1] == 'Still holding: LONG TC.TO (since 2026-11-09).'
    assert not any('Not scoreable' in line for line in text)


def test_an_old_ledger_without_the_column_reads_and_writes(tmp_path):
    path = tmp_path / 'old.csv'
    path.write_text('entry_session,ticker,side,react_pct,g,reaction_session,release_at,release_url,title,'
                    'entry,exit_session,exit,r_pct,scored_at\n'
                    '2026-11-09,TC.TO,LONG,7.4,1.0,2026-11-06,,,Results,,,,,\n')
    P.score(path, now=EVENING, bars_for=lambda t: bars('2026-11-09', ['10:10']), daily=lambda t: daily())
    header = path.read_text().splitlines()[0].split(',')
    assert header == list(P.FIELDS) and header[-1] == 'unscoreable'
    (row,) = P.read(path)
    assert row['react_pct'] == '7.4' and row['unscoreable'].startswith('NO_0940_BAR')


def test_the_record_line_counts_what_could_not_be_scored(tmp_path):
    path = ledger(tmp_path, ('2026-11-09', 'TC.TO'))
    rows = P.read(path) + [{'entry_session': '2026-10-01', 'ticker': 'RY.TO', 'side': 'LONG',
                            'r_pct': '1.0', 'scored_at': '2026-10-08T16:20:00-04:00'}]
    rows[0]['unscoreable'] = 'NO_0940_BAR (first bar 10:10)'
    P._write(rows, path)
    assert P.record_line(path).endswith(
        'Live: 1/1 right, +1.00% per 5-day hold. 1 more could not be scored (no trade in the entry bar).')
