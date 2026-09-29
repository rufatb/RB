"""Parts 3 and 4: separate tests beside the desks — honest records, no leakage."""
import datetime as dt
import json

import pandas as pd

import gap_signal as G
import pead as P

ET = G.ET


def daily(closes, end=dt.date(2026, 9, 28)):
    days = pd.bdate_range(end=end, periods=len(closes))
    return pd.DataFrame({'Close': closes}, index=[pd.Timestamp(d, tz=ET) for d in days])


def test_gap_inputs_use_only_sessions_before_today():
    f = daily([100 + (i % 2) for i in range(30)] + [500.0])
    out = G.inputs_for(f, dt.date(2026, 9, 28))
    assert out['prior_close'] != 500.0 and out['prior_date'] < '2026-09-28'
    assert out['sd20'] > 0
    assert G.inputs_for(daily([100.0] * 10), dt.date(2026, 9, 28)) is None


def staged(tmp_path, session='2026-09-29', **names):
    (tmp_path / G.INPUTS).write_text(json.dumps({'session': session, 'names': {
        t: {'sd20': sd, 'prior_close': 10.0, 'prior_date': '2026-09-28'} for t, sd in names.items()}}))


NOW = dt.datetime(2026, 9, 29, 9, 46, tzinfo=ET)


def test_the_gap_rule_is_one_normal_day_in_the_gaps_direction(tmp_path):
    staged(tmp_path, **{'A.TO': 1.0, 'B.TO': 1.0, 'C.TO': 2.0})
    res = {'factor_candidates': [{'t': 'A.TO', 'gap': 1.5, 'p945': 10.2},
                                 {'t': 'B.TO', 'gap': -2.5, 'p945': 9.7},
                                 {'t': 'C.TO', 'gap': 1.5, 'p945': 10.1}]}
    sec = G.section(tmp_path, NOW, res, path=tmp_path / 'g.csv')
    assert [(p['side'], p['ticker']) for p in sec['picks']] == [('SHORT', 'B.TO'), ('LONG', 'A.TO')]
    assert sec['checked'] == 3 and 'Not better than a coin flip' in sec['record']
    text = '\n'.join(G.lines(sec))
    assert '## Part 3 — Gap signal' in text and '| SHORT B.TO | -2.50% | -2.5 | 9.70 |' in text


def test_the_gap_section_says_why_it_is_empty(tmp_path):
    assert G.section(tmp_path, NOW, {})['status'] == 'UNAVAILABLE'
    staged(tmp_path, session='2026-09-28', **{'A.TO': 1.0})
    assert "not today's" in G.section(tmp_path, NOW, {'factor_candidates': [{'t': 'A.TO', 'gap': 3}]})['reason']
    staged(tmp_path, **{'A.TO': 1.0})
    quiet = G.section(tmp_path, NOW, {'factor_candidates': [{'t': 'A.TO', 'gap': 0.2}]})
    assert quiet['picks'] == [] and 'No signal today' in '\n'.join(G.lines(quiet))


def bars5(day='2026-09-29', o=10.0, e=10.2, c=10.5):
    idx, rows = [], []
    for t, px in (('09:30', (o, o)), ('09:40', (e, e)), ('15:55', (c, c))):
        idx.append(pd.Timestamp(f'{day} {t}', tz=ET))
        rows.append({'Open': px[0], 'Close': px[1]})
    return pd.DataFrame(rows, index=idx)


def test_gap_signals_are_recorded_once_and_scored_from_the_open_and_from_0945(tmp_path):
    path = tmp_path / 'gap.csv'
    report = {'session': '2026-09-29', 'intraday': {'gap_signal': {'picks': [
        {'ticker': 'A.TO', 'side': 'LONG', 'gap_pct': 1.5, 'g': 1.5, 'sd20': 1.0, 'p945': 10.2}]}}}
    assert G.record(report, path) == 1 and G.record(report, path) == 0
    now = dt.datetime(2026, 9, 29, 17, 0, tzinfo=ET)
    assert G.score(path, now=now, bars_for=lambda t: bars5()) == 1
    row = G.read(path)[0]
    assert float(row['r_open_pct']) == 5.0 and round(float(row['r_945_pct']), 2) == 2.94
    assert 'Live: from the open 1/1' in G.record_line(path)


def test_results_releases_are_told_from_date_notices():
    assert P.is_results('Aritzia Reports First Quarter Fiscal 2027 Financial Results')
    assert P.is_results('Intact Financial Corporation reports Q2-2026 results')
    assert not P.is_results('BCE Q2 2026 results to be announced August 6')
    assert not P.is_results('Tucows Announces Timing for Q2 2026 Financial Results News Release')
    assert not P.is_results('Aritzia Reports on Voting Results from the 2026 Annual General Meeting')


def test_the_reaction_session_follows_the_release_time():
    f = daily([100.0 + (i % 3) * 0.5 for i in range(40)] + [110.0, 111.0], end=dt.date(2026, 9, 25))
    days = [i.date() for i in f.index]
    before_open = dt.datetime.combine(days[-2], dt.time(7, 0), tzinfo=ET)
    after_close = dt.datetime.combine(days[-3], dt.time(16, 30), tzinfo=ET)
    s1, r1, g1 = P.reaction(f, before_open, dt.date(2026, 9, 28))
    s2, _, _ = P.reaction(f, after_close, dt.date(2026, 9, 28))
    assert s1 == days[-2] == s2 and r1 > 5 and g1 > 1


def test_pead_stages_a_signal_only_for_yesterdays_reaction_and_records_it(tmp_path, monkeypatch):
    import newswire as N
    wire = tmp_path / 'wire'
    f = daily([100.0 + (i % 3) * 0.5 for i in range(40)] + [110.0], end=dt.date(2026, 9, 28))
    N.append([{'url': 'https://www.newswire.ca/news-releases/x-1.html',
               'title': 'Acme Reports Third Quarter 2026 Results',
               'published_at': '2026-09-28T07:00:00-04:00', 'tickers': ['RY.TO'], 'source': 'newswire.ca'}], wire)
    monkeypatch.setattr(P, '_universe', lambda: {'RY.TO'})
    now = dt.datetime(2026, 9, 29, 9, 10, tzinfo=ET)
    ledger = tmp_path / 'pead.csv'
    out = P.stage(tmp_path, now, daily=lambda t: f, archive=wire, path=ledger)
    assert [(p['side'], p['ticker']) for p in out['new']] == [('LONG', 'RY.TO')]
    assert P.read(ledger)[0]['entry_session'] == '2026-09-29'
    P.stage(tmp_path, now, daily=lambda t: f, archive=wire, path=ledger)
    assert len(P.read(ledger)) == 1                                   # never appended twice
    sec = P.section(tmp_path, now, path=ledger)
    text = '\n'.join(P.lines(sec))
    assert '## Part 4 — Post-earnings drift' in text and '| LONG RY.TO |' in text
    later = P.section(tmp_path, dt.datetime(2026, 9, 30, 9, 10, tzinfo=ET), path=ledger)
    assert later['held'][0]['ticker'] == 'RY.TO' and 'Still holding: LONG RY.TO' in '\n'.join(P.lines(later))


def test_a_pead_position_is_scored_after_five_sessions():
    row = {'entry_session': '2026-09-22', 'side': 'SHORT', 'ticker': 'RY.TO'}
    d = daily([100.0] * 30 + [100, 99, 98, 97, 95], end=dt.date(2026, 9, 28))
    res = P.score_one(row, bars5('2026-09-22', e=100.0), d)
    assert res['exit_session'] == '2026-09-28' and res['r_pct'] == 5.0     # entry day is day 1
    short = daily([100.0] * 30 + [100, 99, 98, 97], end=dt.date(2026, 9, 25))
    assert P.score_one(row, bars5('2026-09-22', e=100.0), short) is None   # only 4 sessions yet


def test_every_view_prints_parts_3_and_4_and_old_reports_do_not():
    import brief
    import email_render
    import report_page
    from test_daily_pipeline import NOW as N0, services
    d = brief.build(now=N0, services=services())
    assert 'gap_signal' in d['intraday'] and 'pead' in d['intraday']
    for body in (email_render.text(d), brief.render_text(d)):
        assert '## Part 3 — Gap signal' in body and '## Part 4 — Post-earnings drift' in body
    assert 'Part 3 — Gap signal' in report_page.render(d)
    old = dict(d)
    old['intraday'] = {k: v for k, v in d['intraday'].items() if k not in ('gap_signal', 'pead')}
    assert 'Gap signal' not in email_render.text(old)
