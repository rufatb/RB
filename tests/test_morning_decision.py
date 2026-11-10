"""Day-150 (owner, 2026-11-10; PREREGISTER_day150_morning_decision.md).

"i dont think these are good picks ... can we combine them so that i get one
good quality decision by 9am? and another at 9:31". Then "Yes" to dropping a
weak pick. Four things:

* the quality floor on Claude's Top 2 (`council.FLOOR`);
* the press feed in the desks' and the council's headlines (`press_feed`);
* one combined 09:00 email (`council_flash.COMBINED`), the pre-open desk
  recording without an email of its own (`us_preopen.EMAIL`);
* KEEP / DROP / CAUTION at 09:31.

The rest of the suite runs with the switches as they were (tests/conftest.py).
Every test here is marked `day150` and runs on the production values.
"""
import datetime as dt
import json

import pytest

import council as K
from tests.test_claude_leads import CLAUDE, led_snap

pytestmark = pytest.mark.day150
ET = dt.timezone(dt.timedelta(hours=-5))


def noms(long_conf=0.55, short_conf=0.52, long='CNQ.TO', short='SU.TO'):
    """Claude's nominations with chosen confidences. On the fixture's table
    CNQ.TO long drew 1 of 3 endorse (2 object) and SU.TO short 3 of 3."""
    return {'longs': [{'ticker': long, 'confidence': long_conf, 'reason': 'Claude long reason',
                       'invalid_at': 40.0}, CLAUDE['longs'][1]],
            'shorts': [{'ticker': short, 'confidence': short_conf, 'reason': 'Claude short reason',
                        'invalid_at': 52.0}, CLAUDE['shorts'][1]]}


# ── 1. the quality floor ─────────────────────────────────────────────────────

def test_the_production_switches_from_the_eleven_eleven_morning():
    assert K.FLOOR is True and K.FLOOR_RULE == 'day150-floor'
    assert K.FLOOR_CONFIDENCE == 0.50 and K.FLOOR_ENDORSE == 2
    assert K.CLAUDE_LEADS is True and K.SKIP_RUNS is True


def test_a_pick_claude_rates_at_the_floor_or_above_stands_whatever_the_council_said():
    sec = K.top_two(led_snap(noms(long_conf=0.50)), previous={})
    assert [(p['side'], p['ticker']) for p in sec['picks']] == [('LONG', 'CNQ.TO'), ('SHORT', 'SU.TO')]
    assert sec['picks'][0]['council_vote'] == '1 of 3 endorse, 2 object'
    assert sec['status'] == 'READY' and 'passed_floor' not in sec
    assert sec['rule_version'] == 'day144-claude-leads+day150-floor'


def test_a_weak_pick_nobody_backs_is_dropped_and_nothing_stands_in_its_place():
    sec = K.top_two(led_snap(noms(long_conf=0.40)), previous={})
    # 11-10's case: Claude's own 0.40 and one endorsement. No long today.
    assert [(p['side'], p['ticker']) for p in sec['picks']] == [('SHORT', 'SU.TO')]
    assert sec['status'] == 'PARTIAL'
    (x,) = sec['passed_floor']
    assert (x['side'], x['ticker'], x['confidence'], x['endorsed']) == ('LONG', 'CNQ.TO', 0.40, 1)
    # Claude's second long (AC.TO, 0.50, which the council endorsed) is not tried
    assert 'AC.TO' not in [p['ticker'] for p in sec['picks']]
    assert sec['reason'].startswith("No long today: Claude's LONG CNQ.TO (its own 0.40; council 1 of 3 endorse")
    line = K.floor_line(sec)
    assert 'LONG CNQ.TO (its own 0.40; council 1 of 3 endorse, 2 object)' in line
    assert 'not shown to raise accuracy' in line and 'Recorded as a shadow, never sized.' in line
    import top_picks
    table = top_picks.table(sec, concise=True)
    assert line in table
    assert not any(row.startswith('|') and 'CNQ.TO' in row for row in table)     # never a row of the picks
    assert any('0.50 or higher or at least two council members endorse it' in row for row in table)


def test_two_council_endorsements_carry_a_pick_claude_rates_low():
    sec = K.top_two(led_snap(noms(short_conf=0.38)), previous={})
    short = sec['picks'][1]
    assert (short['ticker'], short['confidence'], short['endorsed']) == ('SU.TO', 0.38, 3)
    assert 'passed_floor' not in sec and sec['status'] == 'READY'


def test_a_pick_the_council_never_voted_on_has_only_claudes_number():
    low = K.top_two(led_snap(noms(long_conf=0.45, long='BNS.TO')), previous={})
    assert [p['ticker'] for p in low['picks']] == ['SU.TO']
    assert low['passed_floor'][0]['ticker'] == 'BNS.TO'
    assert "its own 0.45; council not voted on (not on the council's table)" in K.floor_line(low)
    high = K.top_two(led_snap(noms(long_conf=0.60, long='BNS.TO')), previous={})
    assert [p['ticker'] for p in high['picks']] == ['BNS.TO', 'SU.TO']


def test_both_picks_below_the_floor_leave_no_pick_and_say_why():
    sec = K.top_two(led_snap(noms(long_conf=0.40, short_conf=0.30, short='TD.TO')), previous={})
    assert sec['picks'] == [] and sec['status'] == 'NO_AGREEMENT'
    assert [x['ticker'] for x in sec['passed_floor']] == ['CNQ.TO', 'TD.TO']
    assert sec['reason'].startswith("Neither of Claude's picks cleared the quality floor")
    assert K.passed_head(sec) == "Claude's picks were below the quality floor"
    import top_picks
    assert sec['reason'] in top_picks.table(sec, concise=True)


def test_the_floor_comes_after_the_run_rule_and_the_line_says_what_happened():
    s = led_snap({'longs': [CLAUDE['longs'][0],
                            {'ticker': 'BNS.TO', 'confidence': 0.41, 'reason': 'next', 'invalid_at': 70.0}],
                  'shorts': CLAUDE['shorts']})
    s['runs'] = {'CNQ.TO': {'run': 3, 'as_of': '2026-11-10', 'dates': [], 'changes_pct': [0.5, 0.8, 1.2]}}
    sec = K.top_two(s, previous={})
    # CNQ.TO follows a run; Claude's next long, BNS.TO, is below the floor: no long.
    assert [(p['side'], p['ticker']) for p in sec['picks']] == [('SHORT', 'SU.TO')]
    assert sec['rule_version'] == 'day144-claude-leads+day146-runs+day150-floor'
    (run,) = sec['passed_run']
    assert run['replaced_by'] is None and run['replaced_dropped'] == 'BNS.TO'
    assert "Claude's next long, LONG BNS.TO, was below the quality floor, so the long slot is empty" \
        in K.run_line(sec)
    assert [x['ticker'] for x in sec['passed_floor']] == ['BNS.TO']
    assert sec['reason'].count('quality floor') == 1 and 'three-day' not in sec['reason']


def test_the_switch_off_restores_the_rule_before_it():
    weak = led_snap(noms(long_conf=0.40))
    sec = K.top_two(weak, previous={}, floor=False)
    assert [p['ticker'] for p in sec['picks']] == ['CNQ.TO', 'SU.TO']
    assert sec['rule_version'] == 'day144-claude-leads' and 'passed_floor' not in sec


def test_without_a_council_only_claudes_number_can_carry_a_pick():
    s = led_snap(noms(long_conf=0.62, short_conf=0.45))
    s['status'], s['tally'], s['positions'], s['reason'] = 'UNAVAILABLE', {}, [], 'it was not staged'
    sec = K.decide({'picks': [], 'status': 'NO_AGREEMENT'}, s)
    assert [(p['side'], p['ticker']) for p in sec['picks']] == [('LONG', 'CNQ.TO')]
    assert sec['passed_floor'][0]['ticker'] == 'SU.TO'
    assert 'council not voted on (the council did not sit)' in K.floor_line(sec)


def test_the_dropped_pick_is_recorded_as_a_shadow_and_reviewed():
    import inspect

    import daily_review
    import execution_lab
    import model_picks as M
    sec = K.top_two(led_snap(noms(long_conf=0.40)), previous={})
    rows = M.rows_from_report({'session': '2026-11-11', 'intraday': {'top_two': sec}})
    shadow = [r for r in rows if r['model'] == 'top2floor']
    assert [(r['kind'], r['side'], r['ticker']) for r in shadow] == [('pick', 'LONG', 'CNQ.TO')]
    assert shadow[0]['prompt_version'] == 'day144-claude-leads+day150-floor'
    assert [(r['side'], r['ticker']) for r in rows if r['model'] == 'top2'] == [('SHORT', 'SU.TO')]
    assert 'top2floor' in M.POOLED_EXCLUDED
    assert "'top2floor'" in inspect.getsource(execution_lab._model_picks)
    assert 'Below the quality floor (shadow)' in inspect.getsource(daily_review)


def test_the_subject_and_the_hero_say_why_there_is_no_pick():
    import email_render
    import prepare_delivery
    sec = K.top_two(led_snap(noms(long_conf=0.40, short_conf=0.30, short='TD.TO')), previous={})
    intraday = {'top_two': sec, 'desks': [{'name': 'Claude', 'legs': []}]}
    assert prepare_delivery.subject_state({'intraday': intraday, 'report_status': 'ON_TIME'}) == \
        "⛔ NO PICK — Claude's picks were below the quality floor — "
    hero = email_render._hero({'intraday': intraday})
    assert "Claude&#x27;s picks were below the quality floor — no pick" in hero


def test_the_page_says_the_floor_too():
    import report_page
    html = report_page._top_two_section({'top_two': K.top_two(led_snap(noms(long_conf=0.40)), previous={})})
    assert 'quality floor of 2026-11-10' in html and 'Below the quality floor, so not a pick' in html
    old = report_page._top_two_section({'top_two': K.top_two(led_snap(), previous={}, floor=False)})
    assert 'quality floor' not in old


# ── 2. the press feed in the desks' and the council's headlines ─────────────

import newswire as N                                                     # noqa: E402
import press_feed as PF                                                  # noqa: E402
from factor_news import classify_headline, prepare_headlines             # noqa: E402

ARIS = {'url': 'https://www.businesswire.com/news/home/20261110/en/aris-reserves',
        'title': 'Aris Mining Increases Segovia Gold Reserves by 28% to 1.9 Million Ounces',
        'published_at': '2026-11-10T07:00:00-05:00', 'tickers': ['ARIS.TO'],
        'summary': 'Reserves rose.', 'source': PF.SOURCE}


def test_only_the_feeds_own_rows_with_an_address_are_archived(tmp_path):
    found = {'ARIS.TO': [{'published_at': ARIS['published_at'], 'title': ARIS['title'], 'url': ARIS['url'],
                          'text': 'Reserves rose.', 'source': PF.SOURCE},
                         {'published_at': '2026-11-10T07:30:00-05:00', 'title': 'From the wire',
                          'url': 'https://www.newswire.ca/x.html', 'text': '', 'source': 'newswire.ca list'},
                         {'published_at': '2026-11-10T07:40:00-05:00', 'title': 'No address',
                          'url': 'fmp:no address', 'text': '', 'source': PF.SOURCE}]}
    rows = PF.rows_from(found)
    assert [(r['title'], r['tickers'], r['source']) for r in rows] == [(ARIS['title'], ['ARIS.TO'], PF.SOURCE)]
    assert PF.append(rows, tmp_path) == 1 and PF.append(rows, tmp_path) == 0        # once per address
    assert (tmp_path/'2026-11-10.jsonl').exists() and PF.read(tmp_path)[0]['summary'] == 'Reserves rose.'


def test_a_press_row_is_an_issuer_release_with_the_feeds_time(tmp_path):
    PF.append([ARIS], tmp_path)
    meta = classify_headline(ARIS['title'], ARIS['url'] + '?utm_source=x', 'ARIS.TO', None, tmp_path)
    assert meta['classification'] == 'ISSUER_RELEASE' and meta['issuer_role'] == 'VERIFIED'
    assert meta['first_disclosed_at'] == ARIS['published_at']
    assert 'FMP press-feed' in meta['classification_basis'] and meta['primary_source_verified'] is False
    # another name's row, another title at that address, or an address not archived: no release
    assert classify_headline(ARIS['title'], ARIS['url'], 'K.TO', None, tmp_path)['issuer_role'] == 'UNVERIFIED'
    assert classify_headline('Aris to be acquired', ARIS['url'], 'ARIS.TO', None, tmp_path)[
        'classification'] == 'UNCLASSIFIED'
    assert classify_headline(ARIS['title'], 'https://example.com/aris', 'ARIS.TO', None, tmp_path)[
        'classification'] == 'UNCLASSIFIED'


def test_the_wire_archives_readers_never_open_the_press_rows(tmp_path):
    """The press rows sit in a subdirectory of the wire archive so every
    `git add data/newswire/` carries them, and no registered reader sees them."""
    wire = tmp_path/'newswire'
    PF.append([ARIS], wire/'press')
    N.append([{'url': 'https://www.newswire.ca/news-releases/acme-1.html', 'title': 'ACME reports',
               'published_at': '2026-11-10T07:00:00-05:00', 'tickers': ['ACM.TO'], 'source': 'newswire.ca'}], wire)
    assert [r['title'] for r in N.read(wire)] == ['ACME reports']
    assert list(N.index(wire)) == ['https://www.newswire.ca/news-releases/acme-1.html']
    start = dt.datetime(2026, 11, 9, 16, 0, tzinfo=ET)
    assert N.releases_for('ARIS.TO', start, start + dt.timedelta(days=1), wire) == []
    import inspect
    assert "ARCHIVE = ROOT/'data'/'newswire'/'press'" in inspect.getsource(PF)   # (the suite's copy is a tmp dir)


def test_the_merge_puts_the_wire_first_then_the_press_and_never_a_title_twice(tmp_path):
    state = tmp_path/'state'
    state.mkdir()
    staged = {'ARIS.TO': {'status': 'READY', 'catalyst_tags': [], 'headlines': [
        {'title': ARIS['title'], 'source_url': 'https://finance.yahoo.com/news/aris-1.html',
         'published_at': '2026-11-10T07:05:00-05:00'},
        {'title': 'Gold miners slip', 'source_url': 'https://a.com/2',
         'published_at': '2026-11-10T06:00:00-05:00'}]}}
    (state/'deepseek_news.json').write_text(json.dumps(staged))
    press, wire = tmp_path/'press', tmp_path/'wire'
    PF.append([ARIS], press)
    N.append([{'url': 'https://www.newswire.ca/news-releases/aris-2.html', 'title': 'Aris Mining declares dividend',
               'published_at': '2026-11-10T07:30:00-05:00', 'tickers': ['ARIS.TO'], 'source': 'newswire.ca'}], wire)
    now = dt.datetime(2026, 11, 10, 8, 55, tzinfo=ET)
    assert PF.merge_into_news(state, ['ARIS.TO', 'OTHER.TO'], now, press) == ['ARIS.TO']
    assert N.merge_into_news(state, ['ARIS.TO'], now, wire) == ['ARIS.TO']
    heads = json.loads((state/'deepseek_news.json').read_text())['ARIS.TO']['headlines']
    assert [h['source_url'].split('/')[2] for h in heads] == ['www.newswire.ca', 'www.businesswire.com', 'a.com']
    # a row published after `now` is not staged
    assert PF.headlines('ARIS.TO', dt.datetime(2026, 11, 10, 6, 0, tzinfo=ET), press) == []


def test_the_models_are_shown_a_press_release_as_the_issuers_own(tmp_path, monkeypatch):
    """Through the real validator: staged news -> factor_inputs -> the row the
    desks read carries ISSUER_RELEASE, issuer_verified and the feed's time."""
    import deepseek_opportunities as O
    import factor_inputs
    monkeypatch.setattr(PF, 'ARCHIVE', tmp_path)
    PF.append([ARIS], tmp_path)
    now = dt.datetime(2026, 11, 10, 8, 55, tzinfo=ET)
    gaps = []
    ev = factor_inputs._evidence([{'title': ARIS['title'], 'source_url': ARIS['url'],
                                   'published_at': ARIS['published_at']},
                                  {'title': 'Top 3 gold stocks to buy', 'source_url': 'https://a.com/1',
                                   'published_at': ARIS['published_at']}],
                                 'headlines', factor_inputs._stamp(now), gaps,
                                 factor_inputs._stamp(now), 'ARIS.TO')
    assert gaps == []
    shown = [O._headline(e) for e in ev]
    assert (shown[0]['class'], shown[0]['issuer_verified'], shown[0]['first_disclosed']) == (
        'ISSUER_RELEASE', True, ARIS['published_at'])
    assert shown[1]['class'] == 'COMMENTARY'
    out, _ = prepare_headlines([{'title': 'Miners slip', 'source_url': 'https://a.com/2'},
                                {'title': ARIS['title'], 'source_url': ARIS['url']}], 8, 'ARIS.TO')
    assert out[0]['evidence_metadata']['classification'] == 'ISSUER_RELEASE'       # ranked first


def test_the_refresh_merges_the_press_before_the_wire():
    import inspect

    import prepare_deepseek
    src = inspect.getsource(prepare_deepseek.refresh_public_inputs)
    assert 0 < src.index('press_feed.merge_into_news') < src.index('newswire.merge_into_news')
    assert "'press_release_tickers': press" in src


def test_the_pre_open_desk_keeps_what_it_read_for_the_desks(tmp_path):
    import us_preopen as U
    from tests.test_us_preopen import NOW, Client, build, live, press
    feed = live(press={'EQX': [press('Equinox Gold Reports Q3 Results', dt.datetime(2026, 11, 9, 17, 30),
                                     'Record revenue.', 'https://www.globenewswire.com/eqx-q3'),
                               press('Equinox Gold Corp Sued for Securities Law Violations - Contact the '
                                     'DJS Law Group', dt.datetime(2026, 11, 10, 6, 0), '', 'https://x.test/n')]})
    (status, info), _ = build(tmp_path, feed=feed, client=Client(), press_root=tmp_path/'press')
    assert status == 'READY'
    rows = PF.read(tmp_path/'press')
    assert [(r['title'], r['tickers'], r['url']) for r in rows] == [
        ('Equinox Gold Reports Q3 Results', ['EQX.TO'], 'https://www.globenewswire.com/eqx-q3')]
    # a quiet night archives nothing and breaks nothing
    (status, _), _ = build(tmp_path/'quiet', feed=live(press={}), press_root=tmp_path/'none')
    assert status == 'NOTHING' and PF.read(tmp_path/'none') == []
    assert U._archive_press({'X.TO': [{'source': PF.SOURCE, 'url': 'https://a.test/1', 'title': 't'}]},
                            tmp_path/'bad') == 'KeyError'                  # a fault is named, never raised
