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
    assert status == 'RECORDED' and info['press_archived'] == 1
    rows = PF.read(tmp_path/'press')
    assert [(r['title'], r['tickers'], r['url']) for r in rows] == [
        ('Equinox Gold Reports Q3 Results', ['EQX.TO'], 'https://www.globenewswire.com/eqx-q3')]
    # a quiet night archives nothing and breaks nothing
    (status, _), _ = build(tmp_path/'quiet', feed=live(press={}), press_root=tmp_path/'none')
    assert status == 'NOTHING' and PF.read(tmp_path/'none') == []
    assert U._archive_press({'X.TO': [{'source': PF.SOURCE, 'url': 'https://a.test/1', 'title': 't'}]},
                            tmp_path/'bad') == 'KeyError'                  # a fault is named, never raised


# ── 3. the pre-open desk sends no email of its own ──────────────────────────

def test_the_pre_open_desk_records_and_sends_nothing(tmp_path):
    import us_preopen as U
    from tests.test_us_preopen import Client, build
    assert U.EMAIL is False
    (status, info), ledger = build(tmp_path, client=Client(), press_root=tmp_path/'press')
    assert status == 'RECORDED' and info['recorded'] == 1 and info['material'] == 1
    assert 'the 09:00 email' in info['shown_in']
    assert not (tmp_path/'state'/'us_preopen'/'subject.txt').exists()          # nothing to send
    assert [r['ticker'] for r in U.read_ledger(ledger)] == ['EQX.TO']
    # a second read (the morning job's, about 08:52) asks nothing twice and is never "already sent"
    again = Client()
    (status, info), _ = build(tmp_path, client=again, press_root=tmp_path/'press')
    assert status == 'RECORDED' and info['recorded'] == 0 and again.seen == []


def test_a_second_read_adds_only_the_names_with_a_release_since(tmp_path):
    import us_preopen as U
    from tests.test_us_preopen import NOW, Client, build, live, ms, press
    build(tmp_path, client=Client(), press_root=tmp_path/'press')
    later = NOW + dt.timedelta(minutes=37)                                      # 08:52
    td = press('TD Bank Group to Acquire a US Wealth Manager', dt.datetime(2026, 11, 10, 8, 30), 'A deal.',
               'https://www.prnewswire.com/td-1')
    eqx = press('Equinox Gold Reports Q3 Results', dt.datetime(2026, 11, 9, 17, 30), 'Record revenue.')
    feed = live(press={'EQX': [eqx], 'TD': [td]},
                quotes={'TD': {'bidPrice': 90.0, 'askPrice': 90.1, 'timestamp': ms(later - dt.timedelta(minutes=1))},
                        'SPY': {'bidPrice': 751.0, 'askPrice': 751.1,
                                'timestamp': ms(later - dt.timedelta(minutes=1))}},
                closes={'TD': [{'date': '2026-11-09', 'close': 89.0}], 'SPY': [{'date': '2026-11-09', 'close': 752.69}],
                        'EQX': [{'date': '2026-11-09', 'close': 12.09}]})
    second = Client(side='SHORT')
    (status, info), ledger = build(tmp_path, feed=feed, client=second, now=later, press_root=tmp_path/'press')
    assert status == 'RECORDED' and info['recorded'] == 1
    assert [i['ticker'] for i in second.seen[0]] == ['TD.TO']                    # EQX's first answer stands
    rows = {r['ticker']: r for r in U.read_ledger(ledger)}
    assert rows['EQX.TO']['side'] == 'LONG' and rows['EQX.TO']['asked_at'].startswith('2026-11-10T08:15')
    assert rows['TD.TO']['side'] == 'SHORT' and rows['TD.TO']['asked_at'].startswith('2026-11-10T08:52')
    assert float(rows['TD.TO']['us_px']) == pytest.approx(90.05)                 # its own price, at its own read


# ── 4. the one 09:00 email ───────────────────────────────────────────────────

import council_flash as F                                                # noqa: E402

AT = dt.datetime(2026, 11, 10, 8, 59, tzinfo=ET)
TWINS = {'SU.TO': {'us': 'SU'}, 'ARIS.TO': {'us': 'ARIS'}, 'GFL.TO': {'us': 'GFL'}}


def read(ticker, side, conf=0.6, us=None, material=True, title=None, at='2026-11-10T07:00:00-05:00', **kw):
    return {'session': '2026-11-10', 'ticker': ticker, 'us': us or ticker.split('.')[0], 'side': side,
            'confidence': conf, 'material': material, 'reason': 'the release says so',
            'title': title or ticker + ' announces something', 'first_at': at, 'last_at': at,
            'us_px': 16.14, 'us_px_at': '2026-11-10T08:18:00-05:00', 'us_prev_close': 16.64, **kw}


READS = [read('ARIS.TO', 'LONG', title='Aris Mining Increases Segovia Gold Reserves by 28%'),
         read('GFL.TO', 'SHORT', 0.6, title='GFL Environmental Concludes Review of Unsolicited Inbound Proposals')]
PRICES = {'SU': {'px': 66.34, 'at': '2026-11-10T08:59:00-05:00', 'prev_close': 67.42},
          'GFL': {'px': 39.75, 'at': '2026-11-10T08:58:00-05:00', 'prev_close': 45.90}}


def day(claude=None, session='2026-11-10'):
    s = led_snap(claude or noms(long_conf=0.40, short_conf=0.38))
    s.update(session=session, finished_at=session + 'T08:59:20-05:00')
    return s


def test_the_production_switch_and_the_subject_that_never_blocks_the_report():
    assert F.COMBINED is True and F.DECISION_SUBJECT == 'RB Morning Decision'
    subj, text, html = F.compose_decision(day(), AT, reads=READS, prices=PRICES, twins=TWINS)
    assert subj == ('RB Morning Decision — 2026-11-10 — SHORT SU.TO (Claude 0.38; council 3 of 3 endorse) '
                    '· no long · 2 overnight release reads')
    assert 'RB Daily Report' not in subj
    assert html.startswith('<!doctype html>') and '<style' not in html


def test_the_decision_is_on_top_and_one_table_holds_the_picks_and_the_releases():
    subj, text, html = F.compose_decision(day(), AT, reads=READS, routine=[read('MDA.TO', 'LONG', material=False)],
                                          prices=PRICES, twins=TWINS, record='Record so far: none.')
    lines = text.splitlines()
    top = lines.index("## Today's decision")
    assert lines[top + 1] == '- SHORT SU.TO stands: Claude 0.38; council 3 of 3 endorse. Wrong if: above 52.'
    assert lines[top + 2].startswith("- No long today: Claude's LONG CNQ.TO was below the quality floor "
                                     '(its own 0.40; council 1 of 3 endorse')
    assert lines[top + 3] == ('- Overnight releases with a call (a separate read; its entry is the New York '
                              'listing before the bell): LONG ARIS.TO · SHORT GFL.TO.')
    assert top < lines.index('## The picks and the overnight releases')
    rows = [x for x in lines if x.startswith('| ') and not x.startswith('| What')]
    assert [x.split(' | ')[0:2] for x in rows] == [
        ['| PICK', 'SHORT SU.TO'], ['| No pick: below the floor', 'LONG CNQ.TO'],
        ['| Release read', 'LONG ARIS.TO (read 0.60)'], ['| Release read', 'SHORT GFL.TO (read 0.60)']]
    assert text.count('| What | Name |') == 1                                    # one table
    # the New York price is the one read just before the email, else the one at the read, labelled
    assert '| SU 66.34 at 08:59, -1.6% since the US close |' in rows[0]
    assert '| ARIS 16.14 at 08:18 (at the read), -3.0% since the US close |' in rows[2]
    assert '| GFL 39.75 at 08:58, -13.4% since the US close |' in rows[3]
    assert '| not on its table |' in rows[2]
    # what the flash carried is under it: the votes of the pick and of the dropped pick, the council's own
    assert any(x.startswith('Council on SHORT SU.TO: ') for x in lines)
    assert any(x.startswith('Council on LONG CNQ.TO: ') for x in lines)
    assert any(x.startswith("The council's own choice, recorded beside and not a pick: ") for x in lines)
    assert any(x.startswith('Below the quality floor, so not a pick') for x in lines)
    assert 'Routine releases, no call: MDA.TO (MDA.TO announces something).' in lines
    assert 'Record so far: none.' in lines and 'no record yet' in text
    assert 'every source on the record is still a coin flip' in lines[-1]


def test_a_release_on_a_picks_own_name_sits_in_its_row_and_the_council_vote_is_shown():
    claude = noms(long_conf=0.55, short_conf=0.52)
    reads = [read('SU.TO', 'SHORT', 0.7, us='SU', title='Suncor Energy Reports Third Quarter Results'),
             read('CNQ.TO', 'SHORT', 0.6, us='CNQ'), read('AC.TO', 'LONG', 0.55, us='AC')]
    subj, text, _ = F.compose_decision(day(claude), AT, reads=reads, prices={}, twins=TWINS)
    rows = [x for x in text.splitlines() if x.startswith('| ') and not x.startswith('| What')]
    assert [x.split(' | ')[0:2] for x in rows] == [
        ['| PICK', 'LONG CNQ.TO'], ['| PICK', 'SHORT SU.TO'],
        ['| Release read', 'SHORT CNQ.TO (read 0.60)'], ['| Release read', 'LONG AC.TO (read 0.55)']]
    assert 'Suncor Energy Reports Third Quarter Results (read: SHORT 0.70)' in rows[1]
    assert 'CNQ.TO announces something (read: SHORT 0.60)' in rows[0]              # the read disagrees: both shown
    # AC.TO long was on the council's table (2 of 3 endorse) and is Claude's second long (0.50)
    assert rows[3].split(' | ')[2:4] == ['0.50', '2 of 3 endorse, 1 object']
    assert subj.endswith('· 3 overnight release reads')


def test_no_release_gives_the_decision_alone_and_no_council_gives_nothing():
    subj, text, _ = F.compose_decision(day(noms()), AT)
    assert subj == ('RB Morning Decision — 2026-11-10 — LONG CNQ.TO (Claude 0.55; council 1 of 3 endorse, '
                    '2 object) · SHORT SU.TO (Claude 0.52; council 3 of 3 endorse)')
    assert 'Release read' not in text and 'How to read the release reads' not in text
    assert F.compose_decision(None, AT) is None
    assert F.compose_decision({'status': 'UNAVAILABLE'}, AT) is None


def test_the_councils_own_top_two_keeps_its_table_and_the_releases_follow(monkeypatch):
    monkeypatch.setattr(K, 'CLAUDE_LEADS', False)
    subj, text, _ = F.compose_decision(day(), AT, reads=READS[:1], prices={}, twins=TWINS)
    lines = text.splitlines()
    assert lines[lines.index("## Today's decision") + 1].startswith("- LONG AC.TO stands: the council's pick")
    assert "## Top 2 — the council's decision" in lines and '## Overnight releases with a call' in lines
    assert any(x.startswith('| Release read | LONG ARIS.TO (read 0.60) |') for x in lines)


def write_state(tmp_path, snap=None, reads=(), monkeypatch=None):
    import us_preopen as U
    if snap is not None:
        (tmp_path/'council.json').write_text(json.dumps(snap))
    ledger = tmp_path/'calls.csv'
    U.write_ledger(list(reads), ledger)
    monkeypatch.setattr(U, 'LEDGER', ledger)
    monkeypatch.setattr(F, 'new_york_prices', lambda symbols, now, read=None: {})
    return ledger


def test_the_wait_sends_the_combined_email_from_the_ledger(tmp_path, monkeypatch):
    notice = read('K.TO', 'SHORT', title='Kinross Gold Corporation Sued for Securities Law Violations - '
                                         'Contact the DJS Law Group')
    write_state(tmp_path, day(), [*READS, notice, read('MDA.TO', 'LONG', material=False)], monkeypatch)
    code, info = F.wait(tmp_path, 0, now_fn=lambda: AT)
    assert code == 0 and info['subject'].startswith('RB Morning Decision — 2026-11-10 — SHORT SU.TO')
    text = (tmp_path/'flash'/'report.txt').read_text()
    assert '| Release read | LONG ARIS.TO (read 0.60) |' in text and 'K.TO' not in text      # a notice is never shown
    assert 'Routine releases, no call: MDA.TO' in text
    assert json.loads((tmp_path/'flash'/'plan.json').read_text())['kind'] == 'council'
    F.record(tmp_path, 'id1', now=AT)
    assert F.wait(tmp_path, 0, now_fn=lambda: AT)[0] == 4                                     # one a day


def test_with_no_council_by_0920_the_releases_go_alone_and_say_so(tmp_path, monkeypatch):
    write_state(tmp_path, None, READS, monkeypatch)
    assert F.wait(tmp_path, 0, now_fn=lambda: AT)[0] == 2                                     # still waiting at 08:59
    late = dt.datetime(2026, 11, 10, 9, 20, tzinfo=ET)
    code, info = F.wait(tmp_path, 0, now_fn=lambda: late)
    assert code == 0 and info['subject'] == ('RB Morning Decision — 2026-11-10 — no council decision yet · '
                                             '2 overnight release reads')
    text = (tmp_path/'flash'/'report.txt').read_text()
    assert '- The council has not sat yet; its decision comes with the 09:46 report.' in text
    assert '## Overnight releases with a call' in text and 'Top 2' not in text
    assert json.loads((tmp_path/'flash'/'plan.json').read_text())['kind'] == 'reads_only'
    # no council and no release: nothing to send, as before
    write_state(tmp_path/'x' if (tmp_path/'x').mkdir() is None else tmp_path, None, [], monkeypatch)
    assert F.wait(tmp_path/'x', 0, now_fn=lambda: late)[0] == 2


def test_a_council_that_did_not_sit_still_sends_the_releases(tmp_path, monkeypatch):
    write_state(tmp_path, {'status': 'UNAVAILABLE', 'session': '2026-11-10', 'reason': 'one member answered'},
                READS, monkeypatch)
    code, info = F.wait(tmp_path, 0, now_fn=lambda: AT)
    assert code == 0 and 'no council decision yet' in info['subject']
    assert 'The council did not sit today (one member answered)' in (tmp_path/'flash'/'report.txt').read_text()
    write_state(tmp_path, {'status': 'UNAVAILABLE', 'session': '2026-11-10', 'reason': 'one member answered'},
                [], monkeypatch)
    assert F.wait(tmp_path, 0, now_fn=lambda: AT)[1]['status'] == 'NOTHING'


def test_the_new_york_prices_are_read_before_the_bell_only_and_one_failure_costs_one_price():
    asked = []

    def feed(path, **p):
        asked.append((path, p.get('symbol')))
        if p.get('symbol') == 'BAD':
            raise RuntimeError('FMP_HTTP_500')
        if path == 'historical-price-eod/full':
            return [{'date': '2026-11-09', 'close': 10.0}]
        if path == 'aftermarket-quote':
            return [{'bidPrice': 10.98, 'askPrice': 11.02, 'timestamp': int(AT.timestamp() * 1000) - 60000}]
        return []
    got = F.new_york_prices(['GOOD', 'BAD', None, 'GOOD'], AT, read=feed)
    assert set(got) == {'GOOD'} and got['GOOD']['px'] == 11.0 and got['GOOD']['prev_close'] == 10.0
    assert F.new_york_prices(['GOOD'], dt.datetime(2026, 11, 10, 9, 30, tzinfo=ET), read=feed) == {}
    assert F._ny_cell('GOOD', got['GOOD']) == 'GOOD 11.00 at 08:58, +10.0% since the US close'
    assert F._ny_cell('X', None) == 'X: no fresh pre-market price' and F._ny_cell(None, None) == '—'


# ── 5. KEEP / DROP / CAUTION at 09:31 ────────────────────────────────────────

OPEN = dt.datetime(2026, 11, 10, 9, 31, tzinfo=ET)


def checked(**kw):
    return {'ticker': 'SU.TO', 'side': 'SHORT', 'verdict': 'STILL VALID', 'price': 94.0, 'at': '09:31',
            'now_days': 0.3, **kw}


def test_the_verdict_follows_the_registered_order():
    assert F.MOVED_ATR == 1.0
    assert F.open_decision({'ticker': 'SU.TO', 'side': 'SHORT', 'verdict': 'NOT CHECKED',
                            'why': 'no quote stamped today after 09:30'}) == (
        'CAUTION', 'not checked: no quote stamped today after 09:30')
    assert F.open_decision(checked(verdict='VOID', now_days=-2.0)) == ('DROP', 'already past its own "wrong if"')
    assert F.open_decision(checked(now_days=-1.0)) == ('CAUTION', 'already 1.0 normal day against it')
    assert F.open_decision(checked(now_days=1.4)) == (
        'CAUTION', 'already 1.4 normal days its way; an entry now does not get that part')
    assert F.open_decision(checked(now_days=0.99)) == ('KEEP', 'nothing at the open contradicts it')
    assert F.open_decision(checked(now_days=-0.99))[0] == 'KEEP'
    # no "wrong if" is not a reason by itself; no normal range leaves only the "wrong if"
    assert F.open_decision(checked(verdict='NOT CHECKED'))[0] == 'KEEP'
    assert F.open_decision(checked(now_days=None)) == ('KEEP', 'not past its "wrong if"; its normal range is unknown')


def quotes(su=50.0, etf=20.1):
    def q(symbol):
        price, prev, open_ = {'SU.TO': (su, 50.5, 50.25), 'ARIS.TO': (22.0, 23.5, 22.6),
                              'GFL.TO': (60.0, 65.0, 58.0)}.get(symbol, (etf, 20.2, 20.15))
        return {'price': price, 'open': open_, 'previousClose': prev, 'timestamp': OPEN.timestamp()}
    return q


def test_the_0931_email_gives_each_pick_one_word_and_the_releases_none(tmp_path, monkeypatch):
    write_state(tmp_path, day(), READS, monkeypatch)
    monkeypatch.setattr(F, 'atr_map', lambda root, now, tickers: {'SU.TO': 2.0, 'ARIS.TO': 5.0, 'GFL.TO': 3.0})
    assert F.wait_open(tmp_path, 0, now_fn=lambda: AT, quote=quotes())[0] == 2          # waits for 09:31
    code, info = F.wait_open(tmp_path, 0, now_fn=lambda: OPEN, quote=quotes())
    assert code == 0 and info['subject'] == 'RB Open Check — 2026-11-10 — KEEP SHORT SU.TO'
    text = (tmp_path/'flash'/'open_report.txt').read_text()
    # SU fell 0.99% from 50.50 to 50: 0.5 normal days the short's way; its fund fell 0.50%
    assert ('| SHORT SU.TO | KEEP | nothing at the open contradicts it | 50 at 09:31 | +0.50% (0.2 normal days) '
            '| +0.99% (0.5 normal days) | +0.50% vs XEG.TO | above 52 '
            '| 4.0% away = 2.0 normal days: OUT OF REACH, not a usable stop |') in text
    assert 'CNQ.TO' not in text                                    # a pick below the floor is not checked
    assert '| LONG ARIS.TO | 22 at 09:31 | -3.83% | -6.38% (1.3 normal days) | moved against the read by 1.3 normal days |' in text
    assert '| SHORT GFL.TO | 60 at 09:31 | +10.77% | +7.69% (2.6 normal days) | moved its way by 2.6 normal days: the news is in the price |' in text
    assert 'No verdict is given on a release read' in text and 'not a forecast' in text
    assert 'The 09:46 report keeps every pick the 09:00 email named' in text
    # recorded once, the pick only
    import csv
    rows = list(csv.DictReader(F.OPEN_LEDGER.open()))
    assert [(r['session'], r['ticker'], r['side'], r['decision']) for r in rows] == [
        ('2026-11-10', 'SU.TO', 'SHORT', 'KEEP')]
    assert rows[0]['now_days'] == '0.495' and rows[0]['e1'] == 'STILL VALID'
    assert F.record_open_checks([checked(open_days=0.1)], OPEN) == 0                 # never rewritten
    plan = json.loads((tmp_path/'flash'/'open_plan.json').read_text())
    assert plan['rows'][0]['decision'] == 'KEEP'


def test_a_pick_past_its_wrong_if_is_dropped_and_a_big_move_is_a_caution(tmp_path, monkeypatch):
    write_state(tmp_path, day(noms(short_conf=0.6)), [], monkeypatch)
    monkeypatch.setattr(F, 'atr_map', lambda root, now, tickers: {'SU.TO': 2.0, 'CNQ.TO': 2.0})
    rows = F.check_open(K.load(tmp_path, OPEN), OPEN, quote=quotes(su=51.8), atr={'SU.TO': 2.0})
    su = next(r for r in rows if r['ticker'] == 'SU.TO')
    # up 2.6% against a short whose "wrong if" (52) is not crossed: 1.3 normal days against it
    assert F.open_decision(su) == ('CAUTION', 'already 1.3 normal days against it')
    past = next(r for r in F.check_open(K.load(tmp_path, OPEN), OPEN, quote=quotes(su=52.4), atr={'SU.TO': 2.0})
                if r['ticker'] == 'SU.TO')
    assert past['verdict'] == 'VOID' and F.open_decision(past)[0] == 'DROP'
    code, info = F.wait_open(tmp_path, 0, now_fn=lambda: OPEN, quote=quotes(su=49.0))
    assert code == 0 and 'CAUTION SHORT SU.TO' in info['subject']                            # 1.5 days its way
    assert 'an entry now does not get that part' in (tmp_path/'flash'/'open_report.txt').read_text()


def test_a_day_with_no_pick_still_checks_the_releases_and_a_quiet_day_sends_nothing(tmp_path, monkeypatch):
    nothing = day(noms(long_conf=0.40, short_conf=0.30, short='TD.TO'))
    write_state(tmp_path, nothing, READS[:1], monkeypatch)
    monkeypatch.setattr(F, 'atr_map', lambda root, now, tickers: {})
    code, info = F.wait_open(tmp_path, 0, now_fn=lambda: OPEN, quote=quotes())
    assert code == 0 and info['subject'].endswith('— no pick today · 1 release read at the open')
    text = (tmp_path/'flash'/'open_report.txt').read_text()
    assert "No pick stood at 09:00: Claude's picks were below the quality floor, so there is no verdict" in text
    assert not F.OPEN_LEDGER.exists()
    write_state(tmp_path, nothing, [], monkeypatch)
    assert F.wait_open(tmp_path, 0, now_fn=lambda: OPEN, quote=quotes())[1]['status'] == 'NOTHING'


def test_a_release_read_gets_words_and_never_a_verdict():
    assert F.read_words({}) == 'not checked: no live quote'
    assert F.read_words({'price': 1, 'now_days': None, 'now_for_read': 0.2}) == 'little reaction so far'
    assert F.read_words({'price': 1, 'now_days': 0.4, 'now_for_read': 1.2}) == 'moved its way, less than a normal day'
    assert F.read_words({'price': 1, 'now_days': -0.4, 'now_for_read': -1.2}) == (
        'moved against the read, less than a normal day')
    for words in map(F.read_words, ({'price': 1, 'now_days': 2.0, 'now_for_read': 5.0}, {})):
        assert not any(w in words for w in ('KEEP', 'DROP', 'CAUTION'))


# ── 6. the wiring: the morning job, its push, the 08:12 Routine ─────────────

def _code(name):
    from pathlib import Path
    body = (Path(__file__).resolve().parent.parent/name).read_text()
    return '\n'.join(line for line in body.splitlines() if not line.lstrip().startswith('#'))


def test_the_morning_job_reads_a_second_time_beside_the_pool_and_joins_before_the_news_refresh():
    body = _code('morning_full.sh')
    second = body.index('python us_preopen.py --state-dir "$RB_STATE_DIR" --build')
    pool = body.index('python prepare_factor_pool.py')
    wire = body.index('python newswire.py --collect')
    join = body.index('wait "$preopen_pid"')
    refresh = body.index('python prepare_deepseek.py --state-dir "$RB_STATE_DIR" --refresh-public-inputs')
    assert body.index('python prepare_tsx_universe.py') < second < pool < wire < join < refresh
    # in the background and bounded: it can never hold the staging window
    line = body[body.rfind('\n', 0, second) + 1:body.index('\n', second)]
    assert line.strip().startswith('( timeout 170 python us_preopen.py')
    assert 'preopen_pid=$!' in body[second:pool]
    # a failure is named, never fatal
    assert 'pre-open desk second read failed' in body and 'pre-open desk second read timed out' in body


def test_the_jobs_own_push_carries_the_second_reads_files_each_on_its_own_line():
    body = _code('morning.sh')
    assert 'git add -- data/us_preopen_calls.csv 2>/dev/null' in body
    assert 'git add -- data/newswire/press 2>/dev/null' in body
    import provenance
    assert 'data/us_preopen_calls.csv' in provenance.RUN_RECORDS
    assert any(r == 'data/newswire/' for r in provenance.RUN_RECORDS)          # covers press/
    assert any(r == 'data/reviews/' for r in provenance.RUN_RECORDS)           # covers open_checks.csv


def test_the_0812_routine_records_and_never_sends():
    from pathlib import Path
    doc = (Path(__file__).resolve().parent.parent/'ROUTINE_PREOPEN.md').read_text()
    prompt = doc[doc.index('RB PRE-OPEN DESK (08:12 ET).'):]
    assert 'It sends NO email' in prompt and 'Send no email from this Routine' in prompt
    assert 'send_message' not in prompt and '--record --message-id' not in prompt
    assert 'python us_preopen.py --state-dir .rb-state --build' in prompt
    assert 'git add data/us_preopen_calls.csv data/newswire/' in prompt        # press/ rides in newswire/
    assert 'Never create, modify, enable, disable or delete any Routine.' in prompt


def test_the_morning_prompt_needs_no_new_command_for_the_two_emails():
    """The 09:00 and 09:31 emails are what the flash and the open check now
    compose: the morning Routine's commands are the ones it already runs."""
    from pathlib import Path
    body = (Path(__file__).resolve().parent.parent/'ROUTINE_PROMPT.md').read_text()
    for command in ('python council_flash.py --state-dir .rb-state --wait 100',
                    'python council_flash.py --state-dir .rb-state --record --message-id <id>',
                    'python council_flash.py --state-dir .rb-state --open-check 540',
                    'python council_flash.py --state-dir .rb-state --record-open --message-id <id>'):
        assert command in body
    import inspect
    assert "'--wait'" in inspect.getsource(F.main) and "'--open-check'" in inspect.getsource(F.main)


def test_the_registration_fixes_what_the_code_does():
    from pathlib import Path
    import us_preopen as U
    reg = (Path(__file__).resolve().parent.parent/'PREREGISTER_day150_morning_decision.md').read_text()
    for needle in ('`council.FLOOR = True`', "`day150-floor`", '0.50 or higher', 'two or more members endorse',
                   '`top2floor/pick`', '`data/newswire/press/YYYY-MM-DD.jsonl`', '`us_preopen.EMAIL = False`',
                   '`council_flash.COMBINED = True`', 'RB Morning Decision', 'No council by 09:20',
                   '`data/reviews/open_checks.csv`', 'one normal day (ATR', 'KEEP is not a forecast'):
        assert needle in reg, needle
    assert (K.FLOOR_CONFIDENCE, K.FLOOR_ENDORSE, F.MOVED_ATR, F.READS_ALONE_AT) == (0.50, 2, 1.0, dt.time(9, 20))
    assert U.EMAIL is False and F.COMBINED is True


def test_a_fault_in_the_new_emails_falls_back_to_the_ones_they_replaced(tmp_path, monkeypatch):
    write_state(tmp_path, day(noms()), READS, monkeypatch)

    def boom(*a, **k):
        raise RuntimeError('unexpected shape')
    monkeypatch.setattr(F, '_decision', boom)
    code, info = F.wait(tmp_path, 0, now_fn=lambda: AT)
    assert code == 0 and info['subject'].startswith('RB Council Flash — 2026-11-10 — LONG CNQ.TO')
    assert json.loads((tmp_path/'flash'/'plan.json').read_text())['fell_back_to_the_flash'] == 'RuntimeError'
    monkeypatch.setattr(F, 'compose_open_decision', boom)
    monkeypatch.setattr(F, 'atr_map', lambda root, now, tickers: {})
    code, info = F.wait_open(tmp_path, 0, now_fn=lambda: OPEN, quote=quotes())
    assert code == 0 and 'SHORT SU.TO STILL VALID' in info['subject']
    # with no council to fall back on, the reads wait rather than fail
    (tmp_path/'council.json').unlink()
    late = dt.datetime(2026, 11, 10, 9, 21, tzinfo=ET)
    assert F.wait(tmp_path, 0, now_fn=lambda: late)[0] == 2
