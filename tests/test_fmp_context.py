"""Day-125: FMP fields in every model's brief (PREREGISTER_day125_fmp.md)."""
import datetime as dt
import json
import re
from pathlib import Path

import pytest

import deepseek_opportunities as O
import fmp_client as F
import fmp_context as X

ET = X.ET
NOW = dt.datetime(2026, 10, 6, 8, 55, tzinfo=ET)
TODAY = NOW.date()

GRADES = [{'date': '2026-10-02', 'gradingCompany': 'RBC Capital', 'action': 'upgrade',
           'previousGrade': 'Sector Perform', 'newGrade': 'Outperform'},
          {'date': '2026-09-30', 'gradingCompany': 'TD', 'action': 'maintain',
           'previousGrade': 'Buy', 'newGrade': 'Buy'},
          {'date': '2026-08-01', 'gradingCompany': 'Old', 'action': 'downgrade',
           'previousGrade': 'Buy', 'newGrade': 'Hold'}]
CONSENSUS = [{'strongBuy': 1, 'buy': 10, 'hold': 16, 'sell': 1, 'strongSell': 0}]
EARNINGS = [{'date': '2026-12-03', 'epsActual': None, 'epsEstimated': 4.14},
            {'date': '2026-08-27', 'epsActual': 4.24, 'epsEstimated': 4.03},
            {'date': '2026-05-28', 'epsActual': 3.9, 'epsEstimated': 3.8}]
CALENDAR = [{'date': '2026-10-06 12:30:00', 'country': 'CA', 'event': 'Balance of Trade',
             'impact': 'Medium', 'estimate': 1.7, 'previous': 0.77},
            {'date': '2026-10-06 14:00:00', 'country': 'CA', 'event': 'Ivey PMI',
             'impact': 'High', 'estimate': 65.2, 'previous': 64.3},
            {'date': '2026-10-06 14:00:00', 'country': 'JP', 'event': 'Other', 'impact': 'High'},
            {'date': '2026-10-06 15:00:00', 'country': 'US', 'event': 'Minor', 'impact': 'Low'},
            {'date': '2026-10-06 21:30:00', 'country': 'US', 'event': 'After close', 'impact': 'High'}]


def test_analyst_changes_are_the_last_30_days_and_never_a_maintain():
    out = X.analyst_fields(GRADES, CONSENSUS, TODAY)
    assert out['analyst_30d'] == ['2026-10-02 RBC Capital upgrade Sector Perform→Outperform']
    assert out['analyst_consensus'] == 'buy 11 / hold 16 / sell 1'


def test_earnings_last_surprise_and_next_date():
    assert X.earnings_fields(EARNINGS, TODAY) == {
        'last_report': '2026-08-27', 'eps_surprise_pct': 5.2, 'next_report': '2026-12-03'}


def test_events_are_canada_and_us_in_session_hours_in_eastern_time():
    """FMP stamps the calendar in UTC: 12:30Z is 08:30 ET in October."""
    assert X.events_today(CALENDAR, TODAY) == [
        '08:30 CA Balance of Trade (Medium) est 1.7 prev 0.77',
        '10:00 CA Ivey PMI (High) est 65.2 prev 64.3']


def fake_get(fail=()):
    def get(path, **p):
        if path in fail:
            raise F.FMPError('FMP_HTTP_429')
        return {'grades': GRADES, 'grades-consensus': CONSENSUS, 'earnings': EARNINGS,
                'economic-calendar': CALENDAR}[path]
    return get


def test_stage_seals_and_load_revalidates_today_only(tmp_path):
    out = X.stage(tmp_path, now=NOW, get=fake_get(), tickers=['RY.TO'])
    assert out['status'] == 'READY' and out['counts']['events_today'] == 2
    ctx = X.load(tmp_path, NOW)
    assert ctx['names']['RY.TO']['eps_surprise_pct'] == 5.2
    assert X.load(tmp_path, NOW + dt.timedelta(days=1)) is None      # stale is refused


def test_a_failed_endpoint_costs_its_fields_and_is_named(tmp_path):
    out = X.stage(tmp_path, now=NOW, get=fake_get(fail=('grades',)), tickers=['RY.TO'])
    row = out['names']['RY.TO']
    assert 'analyst_30d' not in row and row['next_report'] == '2026-12-03'
    assert any('FMP_HTTP_429' in g and 'RY.TO' in g for g in out['gaps'])


def test_no_credential_is_unavailable_and_says_so(tmp_path, monkeypatch):
    monkeypatch.delenv('FMP_API_KEY', raising=False)
    out = X.stage(tmp_path, now=NOW)
    assert out['status'] == 'UNAVAILABLE' and 'No FMP credential' in out['gaps'][0]


def candidate(t='RY.TO'):
    return {'ticker': t, 'market': 'CA', 'currency': 'CAD',
            'technicals': {'rsi': 50.0, 'macd_hist': 0.1, 'rvol': 1.0, 'last': 100.0}}


def test_every_model_gets_the_same_fmp_row_and_todays_releases(tmp_path):
    X.stage(tmp_path, now=NOW, get=fake_get(), tickers=['RY.TO'])
    payload = {'candidates': [candidate()], 'macro': {}}
    X.attach(payload, tmp_path, NOW)
    req = O.build_request(payload['candidates'], X.with_events(payload), NOW)
    row = req['payload']['candidates'][0]
    assert row['analyst_30d'][0].startswith('2026-10-02 RBC Capital upgrade')
    assert row['analyst_consensus'] == 'buy 11 / hold 16 / sell 1'
    assert row['eps_surprise_pct'] == 5.2 and row['next_report'] == '2026-12-03'
    assert req['payload']['macro']['events_today'][1].startswith('10:00 CA Ivey PMI')
    assert payload['macro'] == {}                     # the validated macro is never changed
    # Jev's rows are built by the same _row
    import jev_opportunities as J
    sent = {}

    def poster(body, key, timeout):
        sent.update(body)
        raise RuntimeError('stop')
    J.rank(payload['candidates'], macro=X.with_events(payload), poster=poster, now=NOW)
    state = json.dumps(sent['state'])
    assert 'RBC Capital upgrade' in state and 'Ivey PMI' in state


def test_every_desk_stage_asks_with_todays_releases():
    """The seam that loses data is the one nothing crosses (day-112d): every
    place a desk is asked must pass the macro WITH events, never the bare one."""
    root = Path(__file__).resolve().parent.parent
    for name in ('deepseek_opportunities.py', 'gemini_opportunities.py', 'jev_opportunities.py',
                 'claude_opportunities.py', 'late_picks.py', 'council.py'):
        src = (root / name).read_text()
        assert 'fmp_context.with_events(' in src, name
        assert not re.search(r"rank\(candidates, macro=payload\.get\('macro'\)", src), name
        assert "build_request(staged['candidates'], staged.get('macro')" not in src, name


def test_the_factor_layer_never_sees_the_fmp_key():
    """Its adapter raises on unknown candidate keys (day-113); the public
    whitelist must keep 'fmp' out."""
    from adapters.deepseek_adapter import CANDIDATE_KEYS
    assert 'fmp' not in CANDIDATE_KEYS


def test_the_prompts_describe_the_fields_and_the_registered_result():
    import jev_opportunities as J
    assert O.PROMPT_VERSION == 'day125-v4' and J.PROMPT_VERSION == 'day125-v2'
    for text in (O.SYSTEM_PROMPT, J.INSTRUCTIONS):
        assert 'analyst_30d' in text and 'events_today' in text and '+0.10%' in text
    summary = json.loads((Path(__file__).resolve().parent.parent / 'data' /
                          'replay_day125_analyst.json').read_text())
    assert summary['verdict'] == 'FAIL' and summary['primary']['mean_pct'] == pytest.approx(0.0987, abs=1e-4)


def test_the_client_never_echoes_its_url(monkeypatch):
    import urllib.error

    def opener(url, timeout):
        raise urllib.error.HTTPError(url, 403, 'secret ' + url, {}, None)
    with pytest.raises(F.FMPError) as exc:
        F.get('quote', 'SECRETKEY', opener=opener, retries=0, symbol='RY.TO')
    assert str(exc.value) == 'FMP_HTTP_403' and 'SECRETKEY' not in str(exc.value)


def test_the_email_prints_todays_releases_and_a_top_two_analyst_change():
    import email_render as E
    intra = {'fmp': {'events_today': ['10:00 CA Ivey PMI (High) est 65.2 prev 64.3'],
                     'analyst_changes': {'TRP.TO': ['2026-10-01 Goldman Sachs upgrade Neutral→Buy']}},
             'top_two': {'picks': [{'ticker': 'TRP.TO'}]}}
    lines = E.fmp_lines(intra)
    assert lines[0] == 'Scheduled today (ET): 10:00 CA Ivey PMI (High) est 65.2 prev 64.3.'
    assert lines[1].startswith('Analyst change on TRP.TO: 2026-10-01 Goldman Sachs upgrade')
    assert E.fmp_lines({}) == []
