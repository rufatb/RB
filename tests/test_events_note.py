"""Day-148c: the evening note (owner, 2026-11-09: "Yes").

The next three sessions' scheduled releases, and each reporting name's typical
move on a report day. Sizes and timing, never direction; no pick, no size, no
ledger. Every test here feeds it a fake FMP: no network.
"""
import datetime as dt
import json

import pytest

import events_note as N

ET = N.ET
MON = dt.datetime(2026, 11, 9, 16, 30, tzinfo=ET)        # a Monday evening
WEEKDAYS = lambda d: d.weekday() < 5                      # noqa: E731


def daily(start, n, step=0.0, jumps=None, volume=1000.0):
    """n weekday bars from `start`; `jumps` {date: (pct, volume)} moves the close that day."""
    out, day, close = [], dt.date.fromisoformat(start), 100.0
    while len(out) < n:
        if day.weekday() < 5:
            pct, vol = (jumps or {}).get(day.isoformat(), (step, volume))
            opened = close
            close = close * (1 + pct / 100)
            out.append({'date': day.isoformat(), 'open': opened, 'close': close, 'volume': vol})
        day += dt.timedelta(days=1)
    return out


class FakeFMP:
    def __init__(self, events=(), calendar=(), earnings=None, bars=None, fail=()):
        self.events, self.calendar = list(events), list(calendar)
        self.earnings, self.bars, self.fail, self.calls, self.failures = earnings or {}, bars or {}, set(fail), [], {}

    def __call__(self, path, **p):
        self.calls.append((path, p.get('symbol')))
        if path in self.fail or (path, p.get('symbol')) in self.fail:
            self.failures['FMP_HTTP_429'] = self.failures.get('FMP_HTTP_429', 0) + 1
            return None
        if path == 'economic-calendar':
            return self.events
        if path == 'earnings-calendar':
            return self.calendar
        if path == 'earnings':
            return self.earnings.get(p['symbol'], [])
        if path == 'historical-price-eod/full':
            return self.bars.get(p['symbol'], [])
        raise AssertionError(path)


def state(tmp_path, names=('AAA.TO', 'BBB.TO')):
    (tmp_path/'tsx_universe.json').write_text(json.dumps(
        {'candidates': [{'ticker': t, 'industry': 'Gold'} for t in names]}))
    return tmp_path


def ev(when_utc, name, impact='High', country='US', est=None, prev=None):
    return {'date': when_utc, 'event': name, 'impact': impact, 'country': country,
            'estimate': est, 'previous': prev}


def test_the_note_belongs_to_the_evening_before_a_session():
    fri, sun = dt.date(2026, 11, 13), dt.date(2026, 11, 15)
    assert N.sessions(fri, is_trading=WEEKDAYS) == []                       # Saturday is next
    assert N.sessions(sun, is_trading=WEEKDAYS) == [dt.date(2026, 11, 16), dt.date(2026, 11, 17),
                                                    dt.date(2026, 11, 18)]
    thu = dt.date(2026, 11, 12)                                              # the weekend is skipped
    assert N.sessions(thu, is_trading=WEEKDAYS) == [dt.date(2026, 11, 13), dt.date(2026, 11, 16),
                                                    dt.date(2026, 11, 17)]
    holiday = lambda d: d.weekday() < 5 and d != dt.date(2026, 11, 10)      # noqa: E731
    assert N.sessions(dt.date(2026, 11, 9), is_trading=holiday) == []       # tomorrow is a holiday
    assert N.sessions(dt.date(2026, 11, 10), is_trading=holiday)[0] == dt.date(2026, 11, 11)


def test_the_real_calendar_knows_the_tsx_trades_on_remembrance_day():
    assert N.sessions(dt.date(2026, 11, 9)) == [dt.date(2026, 11, 10), dt.date(2026, 11, 11),
                                                dt.date(2026, 11, 12)]


def test_the_calendar_is_in_eastern_time_by_impact_with_the_speakers_on_one_line():
    days = [dt.date(2026, 11, 10), dt.date(2026, 11, 11)]
    rows = [ev('2026-11-10 13:30:00', 'Inflation Rate MoM (Oct)', est=0.3, prev=0.6),
            ev('2026-11-10 13:30:00', 'Inflation Rate MoM (Oct)', est=0.3, prev=0.6),     # a duplicate
            ev('2026-11-10 13:30:00', 'CPI s.a (Oct)', est=337, prev=336.3),              # the index level
            ev('2026-11-10 13:30:00', 'Inflation Rate (Oct)', est=337.02, prev=336.94),
            ev('2026-11-10 09:00:00', 'Fed Waller Speech', impact='Medium'),
            ev('2026-11-10 18:30:00', 'Fed Bowman Speech', impact='Medium'),
            ev('2026-11-10 21:30:00', 'API Crude Oil Stock Change (Nov/06)', impact='Medium', prev=-5.267),
            ev('2026-11-11 03:00:00', 'Late Tuesday Print', country='CA'),              # 22:00 ET Tuesday
            ev('2026-11-10 13:30:00', 'A Low One', impact='Low'),
            ev('2026-11-10 13:30:00', 'A German One', country='DE'),
            ev('2026-11-13 13:30:00', 'Outside The Window'),
            {'date': 'not a time', 'event': 'Broken', 'impact': 'High', 'country': 'US'}]
    got = N.macro(rows, days)
    tue = got[dt.date(2026, 11, 10)]
    assert tue['high'] == ['08:30 US Inflation Rate MoM (Oct) — consensus 0.3 — previous 0.6',
                           '22:00 CA Late Tuesday Print']
    assert tue['medium'] == ['16:30 US API Crude Oil Stock Change (Nov/06) — previous -5.267']
    assert tue['speakers'] == ['04:00 Waller', '13:30 Bowman'] and tue['cpi'] == '08:30'
    assert got[dt.date(2026, 11, 11)] == {'high': [], 'medium': [], 'speakers': [], 'cpi': None}


def test_a_typical_move_is_the_median_against_the_benchmark_on_the_busier_day():
    # the report is dated 2026-08-04 but the reaction, on volume, is the next session
    jumps = {'2026-08-05': (6.0, 9000.0), '2026-05-05': (-4.0, 9000.0)}
    bars = N._bars(daily('2025-11-03', 280, jumps=jumps))
    bench = N._bars(daily('2025-11-03', 280, jumps={'2026-08-05': (1.0, 1000.0)}))
    reports = [{'date': '2026-08-04', 'epsActual': 1.0}, {'date': '2026-05-05', 'epsActual': 0.5},
               {'date': '2026-11-12', 'epsActual': None},            # not out yet
               {'date': '2026-11-09', 'epsActual': 2.0}]             # today: not a past report
    moves = N.reactions(reports, bars, bench, '2026-11-09')
    assert [round(x, 2) for x in moves] == [-4.0, 5.0]               # oldest first; 6% less XIU's 1%
    assert N.typical(moves) == (None, moves, 2)                      # too few reports for a typical move
    seven = [1.0, -2.0, 3.0, -4.0, 5.0, -6.0, 7.0]
    assert N.typical(seven) == (4.0, [-4.0, 5.0, -6.0, 7.0], 7)
    assert N.typical(list(range(1, 40)))[2] == N.REPORTS             # only the last REPORTS count


def test_reporters_are_the_lists_names_dated_in_the_window_or_due_tonight():
    today, days = dt.date(2026, 11, 9), [dt.date(2026, 11, 10), dt.date(2026, 11, 11)]
    cal = [{'symbol': 'AAA.TO', 'date': '2026-11-09', 'epsActual': None},      # tonight, not out yet
           {'symbol': 'BBB.TO', 'date': '2026-11-09', 'epsActual': 1.2},       # out this morning
           {'symbol': 'CCC.TO', 'date': '2026-11-11', 'epsActual': None},
           {'symbol': 'ZZZ.TO', 'date': '2026-11-10', 'epsActual': None},      # not on the list
           {'symbol': 'AAA.TO', 'date': '2026-11-13', 'epsActual': None}]      # after the window
    assert N.reporters(cal, {'AAA.TO', 'BBB.TO', 'CCC.TO'}, today, days) == [
        ('2026-11-09', 'AAA.TO'), ('2026-11-11', 'CCC.TO')]


def note(tmp_path, **kw):
    jumps = {'2026-08-05': (6.0, 9000.0), '2026-05-06': (-4.0, 9000.0), '2026-02-04': (3.0, 9000.0),
             '2025-11-05': (-2.0, 9000.0), '2025-08-06': (5.0, 9000.0), '2025-05-07': (1.0, 9000.0)}
    fmp = FakeFMP(
        events=[ev('2026-11-10 13:30:00', 'Inflation Rate MoM (Oct)', est=0.3, prev=0.6),
                ev('2026-11-12 13:30:00', 'Initial Jobless Claims (Nov/07)', est=195, prev=189)],
        calendar=[{'symbol': 'AAA.TO', 'date': '2026-11-10', 'epsActual': None},
                  {'symbol': 'BBB.TO', 'date': '2026-11-12', 'epsActual': None}],
        earnings={'AAA.TO': [{'date': d, 'epsActual': 1.0} for d in jumps]},
        bars={'AAA.TO': daily('2025-03-03', 480, jumps=jumps), 'BBB.TO': daily('2025-03-03', 480),
              'XIU.TO': daily('2025-03-03', 480)}, **kw)
    return fmp, N.build(state(tmp_path), MON, read=fmp, is_trading=WEEKDAYS)


def test_the_note_names_the_events_and_each_reporters_typical_move(tmp_path):
    fmp, (status, info) = note(tmp_path)
    assert status == 'READY' and info['sessions'] == ['2026-11-10', '2026-11-11', '2026-11-12']
    assert info['subject'] == ('RB Evening Note — 2026-11-09 — for Tue 11-10: US inflation 08:30 · '
                               '1 report on the list by then')
    text = (tmp_path/'evening_note'/'report.txt').read_text()
    assert text.splitlines()[0] == '# RB Evening Note — 2026-11-09'
    assert '- 08:30 US Inflation Rate MoM (Oct) — consensus 0.3 — previous 0.6' in text
    assert '### Wed 11-11\n- Nothing of High or Medium impact on the calendar.' in text
    assert '| AAA.TO | Tue 11-10 | 3.5% | +3.0%, -4.0%, +6.0% | Gold |' not in text       # four, not three
    assert '| AAA.TO | Tue 11-10 | 3.5% | -2.0%, +3.0%, -4.0%, +6.0% | Gold |' in text
    assert '| BBB.TO | Thu 11-12 | — | — | Gold |' in text                # no past report: no number invented
    assert '| Hotter | 48 |' in text                                      # an inflation print is in the window
    assert 'A typical move is a size, not a direction.' in text
    assert 'every source on its record is still a coin flip' in text
    # one benchmark call, and two calls a reporter
    assert sorted(c for c in fmp.calls if c[0] == 'earnings') == [('earnings', 'AAA.TO'), ('earnings', 'BBB.TO')]
    assert fmp.calls.count(('historical-price-eod/full', 'XIU.TO')) == 1


def test_the_email_is_inline_styled_and_never_reads_as_the_daily_report(tmp_path):
    _, (status, info) = note(tmp_path)
    html = (tmp_path/'evening_note'/'report.html').read_text()
    assert 'RB Daily Report — ' not in info['subject']          # the morning senders skip on that phrase
    assert 'Evening research note · not an order' in html and 'Morning research note' not in html
    assert '<style' not in html and 'class=' not in html
    assert 'US inflation 08:30' in html and '<table role="table"' in html
    assert 'apikey' not in html.lower() and 'financialmodelingprep' not in html


def test_no_inflation_print_no_inflation_table(tmp_path):
    fmp = FakeFMP(events=[ev('2026-11-10 13:30:00', 'Initial Jobless Claims (Nov/07)', est=195)])
    status, info = N.build(state(tmp_path), MON, read=fmp, is_trading=WEEKDAYS)
    text = (tmp_path/'evening_note'/'report.txt').read_text()
    assert status == 'READY' and '| Hotter |' not in text
    assert "FMP dates no report on the list for these sessions." in text
    assert info['subject'].endswith('for Tue 11-10: 08:30 US Initial Jobless Claims (Nov/07)')


def test_one_side_failing_is_said_and_both_failing_sends_nothing(tmp_path):
    fmp, (status, _) = note(tmp_path, fail={'earnings-calendar'})
    text = (tmp_path/'evening_note'/'report.txt').read_text()
    assert status == 'READY' and 'Unavailable today: the earnings calendar could not be read.' in text
    assert 'Not read from FMP: FMP_HTTP_429 ×1.' in text
    other = tmp_path/'b'
    other.mkdir()
    fmp, (status, info) = note(other, fail={'earnings-calendar', 'economic-calendar'})
    assert status == 'FAILED' and info['reason'] == 'FMP_HTTP_429'
    assert not (other/'evening_note').exists()


def test_a_reporter_whose_history_fails_is_listed_without_a_number(tmp_path):
    fmp, (status, _) = note(tmp_path, fail={('earnings', 'AAA.TO')})
    text = (tmp_path/'evening_note'/'report.txt').read_text()
    assert status == 'READY' and '| AAA.TO | Tue 11-10 | — | — | Gold |' in text
    assert 'Not read from FMP: FMP_HTTP_429 ×1.' in text


def test_no_list_staged_still_sends_the_calendar_and_says_so(tmp_path):
    fmp = FakeFMP(events=[ev('2026-11-10 13:30:00', 'Inflation Rate MoM (Oct)', est=0.3, prev=0.6)])
    status, _ = N.build(tmp_path, MON, read=fmp, is_trading=WEEKDAYS)
    text = (tmp_path/'evening_note'/'report.txt').read_text()
    assert status == 'READY' and 'the earnings calendar could not be read' in text
    assert 'Not read from FMP: NO_LIST_STAGED ×1.' in text
    assert ('earnings-calendar', None) not in fmp.calls


def test_one_note_an_evening_and_none_before_a_day_off(tmp_path):
    _, (status, _) = note(tmp_path)
    assert status == 'READY'
    N.record(tmp_path, 'abc123', MON)
    assert json.loads((tmp_path/'evening_note'/'sent.json').read_text())['message_id'] == 'abc123'
    assert N.build(tmp_path, MON, read=FakeFMP(), is_trading=WEEKDAYS)[0] == 'ALREADY_SENT'
    tue = MON + dt.timedelta(days=1)                       # the next evening it is due again
    assert N.build(tmp_path, tue, read=FakeFMP(events=[ev('2026-11-11 13:30:00', 'X')]),
                   is_trading=WEEKDAYS)[0] == 'READY'
    fri = dt.datetime(2026, 11, 13, 16, 30, tzinfo=ET)
    assert N.build(tmp_path/'c', fri, read=FakeFMP(), is_trading=WEEKDAYS) == (
        'NOTHING', {'reason': 'tomorrow is not a trading day'})


def test_a_failure_is_a_code_never_the_url():
    def get(path, **p):
        raise ValueError('https://financialmodelingprep.com/stable/x?apikey=SECRET went wrong')
    r = N.Reader(get=get, per_second=1000)
    assert r('economic-calendar') is None and r.failures == {'ValueError': 1}

    def coded(path, **p):
        raise ValueError('FMP_HTTP_402')
    r = N.Reader(get=coded, per_second=1000)
    assert r('earnings', symbol='AAA.TO') is None and r.failures == {'FMP_HTTP_402': 1}


def test_the_cli_reports_a_crash_as_failed_and_never_raises(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(N, 'build', lambda *a, **k: 1 / 0)
    assert N.main(['--state-dir', str(tmp_path), '--build']) == 1
    assert json.loads(capsys.readouterr().out) == {'status': 'FAILED', 'reason': 'ZeroDivisionError'}
    with pytest.raises(SystemExit):
        N.main(['--state-dir', str(tmp_path), '--record'])            # --record needs --message-id


def test_the_note_writes_no_ledger_and_names_no_pick():
    import inspect
    src = inspect.getsource(N)
    for ledger in ('model_picks', 'ledger.csv', 'news_calls', 'gap_calls', 'pead_calls'):
        assert ledger not in src
    assert 'LONG ' not in '\n'.join(N.CPI_TABLE) + N.REPORT_FACTS and 'SHORT ' not in N.REPORT_FACTS


def test_the_evening_routine_runs_the_note_and_checks_its_html():
    import re
    from pathlib import Path
    root = Path(__file__).resolve().parent.parent
    body = (root/'ROUTINE_EVENING.md').read_text()
    prompt = body.split('\n---\n', 1)[1]
    assert '1c. NOTE' in prompt and prompt.index('1b. WIRE') < prompt.index('1c. NOTE') < prompt.index('2. PUSH')
    assert 'python events_note.py --state-dir .rb-state --build' in prompt
    assert 'python events_note.py --state-dir .rb-state --record --message-id <id>' in prompt
    assert 'send_check.py' in prompt and '--snippet' in prompt and 'htmlBody is REQUIRED' in prompt
    assert 'step 1c (the evening note)' in prompt             # it runs on a Sunday evening too
    assert prompt.rstrip().endswith('Never create, modify, enable, disable or delete any Routine.')
    # the note is never pushed: the push list is the record files it always was
    push = prompt[prompt.index('2. PUSH'):prompt.index('3. REPORT')]
    assert 'evening_note' not in push and 'events_note' not in push
    # every script it names exists, and the note's flags are real options
    for script in set(re.findall(r'python ([a-z_]+\.py)', prompt)):
        assert (root/script).is_file(), script
    parser_flags = {'--state-dir', '--build', '--record', '--message-id'}
    for flag in re.findall(r'events_note\.py((?: --[a-z-]+(?: [^ `-][^ `]*)?)+)', prompt):
        assert set(re.findall(r'--[a-z-]+', flag)) <= parser_flags
    # no live credential is committed with it
    assert not re.search(r'sk-[A-Za-z0-9]{16,}|apikey=|AIza[0-9A-Za-z_-]{20,}', body)
