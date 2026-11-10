"""Day-149 — the pre-open desk on New York listings (PREREGISTER_day149_us_preopen.md)."""
import datetime as dt
import json
from pathlib import Path

import pytest

import news_desk as N
import us_preopen as U

ET = U.ET
ROOT = Path(__file__).resolve().parent.parent
NOW = dt.datetime(2026, 11, 10, 8, 15, tzinfo=ET)                 # a Tuesday
TWINS = {'EQX.TO': {'us': 'EQX', 'isin': 'CA29446Y5020', 'exchange': 'AMEX', 'name': 'Equinox Gold Corp.'},
         'IMG.TO': {'us': 'IAG', 'isin': 'CA4509131088', 'exchange': 'NYSE', 'name': 'IAMGOLD Corporation'},
         'TD.TO': {'us': 'TD', 'isin': 'CA8911605092', 'exchange': 'NYSE', 'name': 'The Toronto-Dominion Bank'}}
WEEKDAYS = lambda d: d.weekday() < 5                                   # noqa: E731


def ms(when):
    return int(when.timestamp() * 1000)


class FMP:
    """Canned answers by path and symbol; counts what it was asked."""
    def __init__(self, press=None, quotes=None, trades=None, closes=None, bars=None):
        self.press, self.quotes, self.trades = press or {}, quotes or {}, trades or {}
        self.closes, self.bars = closes or {}, bars or {}
        self.failures, self.asked = {}, []

    def __call__(self, path, **p):
        sym = p.get('symbol') or p.get('symbols')
        self.asked.append((path, sym))
        if path == 'news/press-releases':
            return self.press.get(sym, [])
        if path == 'aftermarket-quote':
            return [self.quotes[sym]] if sym in self.quotes else []
        if path == 'aftermarket-trade':
            return [self.trades[sym]] if sym in self.trades else []
        if path == 'historical-price-eod/full':
            return self.closes.get(sym, [])
        if path == 'historical-chart/5min':
            return self.bars.get(sym, [])
        raise AssertionError(path)


class Client:
    """Answers every item with one side; records what it was shown."""
    def __init__(self, side='LONG', material=True):
        self.seen, self.side, self.material = [], side, material
        self.chat = self
        self.completions = self

    def create(self, **kw):
        items = json.loads(kw['messages'][1]['content'])['items']
        self.seen.append(items)
        assert kw['messages'][0]['content'] == N.SYSTEM_PROMPT            # day-122's, byte for byte
        content = json.dumps({'calls': [{'id': i['id'], 'ticker': i['ticker'], 'side': self.side,
                                         'confidence': 0.7, 'material': self.material, 'reason': 'r'}
                                        for i in items]})

        class R:
            model = 'deepseek-v4-pro'
            choices = [type('C', (), {'finish_reason': 'stop',
                                      'message': type('M', (), {'content': content})})]
        return R


def press(title, at, text='', url='https://example.test/r'):
    return {'title': title, 'publishedDate': at.strftime('%Y-%m-%d %H:%M:%S'), 'text': text, 'url': url}


RESULTS = press('Equinox Gold Reports Q3 Results', dt.datetime(2026, 11, 9, 17, 30), 'Record revenue.')


def live(**over):
    """A feed with one Equinox release, a tight fresh quote on EQX and SPY."""
    kw = dict(
        press={'EQX': [RESULTS]},
        quotes={'EQX': {'bidPrice': 12.30, 'askPrice': 12.34, 'timestamp': ms(NOW - dt.timedelta(minutes=1))},
                'SPY': {'bidPrice': 750.0, 'askPrice': 750.1, 'timestamp': ms(NOW - dt.timedelta(minutes=1))}},
        closes={'EQX': [{'date': '2026-11-09', 'close': 12.09}, {'date': '2026-11-06', 'close': 11.52}],
                'SPY': [{'date': '2026-11-09', 'close': 752.69}]})
    kw.update(over)
    return FMP(**kw)


# ── whose release is it ─────────────────────────────────────────────────────

def test_a_release_is_the_issuers_only_when_its_title_starts_with_the_company():
    eqx = TWINS['EQX.TO']
    assert U._names_issuer({'title': 'Equinox Gold Reports Q3 Results'}, 'EQX.TO', eqx)
    assert not U._names_issuer({'title': 'Caprock Provides an Update', 'text': 'Equinox Gold (TSX: EQX)'},
                               'EQX.TO', eqx)
    # 11-09's dry run: iA Financial (TSX: IAG) arrives under IAMGOLD's New York symbol IAG.
    assert not U._names_issuer({'title': 'iA Financial Group Reports Third Quarter Results',
                                'text': 'iA Financial Corporation (TSX: IAG) today reported'},
                               'IMG.TO', TWINS['IMG.TO'])
    assert U._names_issuer({'title': 'IAMGOLD Reports Third Quarter 2026 Results'}, 'IMG.TO', TWINS['IMG.TO'])


def test_brand_names_and_joined_names_are_recognised():
    assert U._names_issuer({'title': 'TD Bank Group Reports Fourth Quarter Results'}, 'TD.TO', TWINS['TD.TO'])
    assert not U._names_issuer({'title': 'Toronto Hydro Announces Rates'}, 'TD.TO', TWINS['TD.TO'])
    otex = {'us': 'OTEX', 'name': 'Open Text Corporation'}
    assert U._names_issuer({'title': 'OpenText Reports First Quarter Results'}, 'OTEX.TO', otex)
    assert U._lead('Shopify Inc.') == 'shopify' and U._lead('The Toronto-Dominion Bank') == 'toronto dominion'
    assert U._lead('Brookfield Corporation') == ''          # one common word names nobody


def test_a_law_firms_notice_is_not_the_companys_news():
    for title in ('GIL EQUITY ACTION REMINDER: Faruqi & Faruqi, LLP Reminds Gildan Activewear Investors',
                  'KGC Stock Drop Alert: BFA Law Announces a Securities Fraud Class Action',
                  'SHAREHOLDER ALERT: Pomerantz Law Firm Investigates Claims'):
        assert U.notice(title)
    assert not U.notice('Kinross reports 2026 third-quarter results')


def test_releases_keeps_the_window_drops_notices_and_merges_the_wire(tmp_path):
    start, end = dt.datetime(2026, 11, 9, 16, 0, tzinfo=ET), NOW
    feed = FMP(press={'EQX': [
        RESULTS,
        press('Equinox Gold Reports Q3 Results', dt.datetime(2026, 11, 9, 17, 31)),          # the same title
        press('Equinox Gold Declares Dividend', dt.datetime(2026, 11, 9, 15, 59)),           # before the close
        press('EQX ALERT: Rosen Law Firm Reminds Investors of Class Action', dt.datetime(2026, 11, 9, 18, 0)),
        press('Caprock Provides an Update', dt.datetime(2026, 11, 9, 18, 0), 'Equinox Gold (TSX: EQX)')]})
    wire = tmp_path/'wire'
    wire.mkdir()
    (wire/'2026-11-10.jsonl').write_text(json.dumps({
        'published_at': '2026-11-10T07:00:00-05:00', 'title': 'Equinox Gold Announces a Sale',
        'url': 'https://www.newswire.ca/x', 'tickers': ['EQX.TO'], 'summary': 'Equinox Gold (TSX: EQX) sells.',
        'source': 'newswire.ca list'}) + '\n')
    found, dropped = U.releases(feed, TWINS, start, end, wire)
    assert list(found) == ['EQX.TO'] and dropped == {'third-party notice': 1}
    assert [r['title'] for r in found['EQX.TO']] == ['Equinox Gold Reports Q3 Results',
                                                     'Equinox Gold Announces a Sale']
    assert found['EQX.TO'][1]['source'] == 'newswire.ca list' and found['EQX.TO'][1]['text'].startswith('Equinox')


def test_the_prior_close_skips_weekends_and_holidays():
    monday = dt.datetime(2026, 11, 9, 8, 0, tzinfo=ET)
    assert U.prior_close(monday, WEEKDAYS) == dt.datetime(2026, 11, 6, 16, 0, tzinfo=ET)
    closed = {dt.date(2026, 11, 9)}
    assert U.prior_close(NOW, lambda d: d.weekday() < 5 and d not in closed) == \
        dt.datetime(2026, 11, 6, 16, 0, tzinfo=ET)


# ── the price at the read ───────────────────────────────────────────────────

def test_a_tight_fresh_quote_gives_its_mid_and_the_close_comes_from_daily_bars():
    s = U.snapshot(live(), 'EQX', NOW)
    assert s['px'] == pytest.approx(12.32) and s['source'] == 'quote mid'
    assert (s['bid'], s['ask']) == (12.30, 12.34)
    assert (s['prev_close'], s['prev_date']) == (12.09, '2026-11-09')


def test_a_wide_or_old_quote_falls_back_to_a_fresh_trade_and_never_to_a_stale_one():
    wide = {'bidPrice': 11.5, 'askPrice': 12.24, 'timestamp': ms(NOW - dt.timedelta(minutes=1))}
    fresh = {'price': 12.05, 'timestamp': ms(NOW - dt.timedelta(minutes=20))}
    s = U.snapshot(live(quotes={'EQX': wide}, trades={'EQX': fresh}), 'EQX', NOW)
    assert s['px'] == 12.05 and s['source'] == 'last trade' and s['bid'] == 11.5
    old = {'price': 12.05, 'timestamp': ms(NOW - dt.timedelta(minutes=45))}
    assert U.snapshot(live(quotes={'EQX': wide}, trades={'EQX': old}), 'EQX', NOW)['px'] is None
    stale_quote = {'bidPrice': 12.30, 'askPrice': 12.34, 'timestamp': ms(NOW - dt.timedelta(minutes=25))}
    assert U.snapshot(live(quotes={'EQX': stale_quote}), 'EQX', NOW)['px'] is None


def test_yesterdays_after_hours_print_is_never_todays_price():
    evening = dt.datetime(2026, 11, 9, 19, 58, tzinfo=ET)
    feed = live(quotes={'EQX': {'bidPrice': 12.0, 'askPrice': 12.02, 'timestamp': ms(evening)}},
                trades={'EQX': {'price': 12.01, 'timestamp': ms(evening)}})
    s = U.snapshot(feed, 'EQX', NOW)
    assert s['px'] is None and s['bid'] is None and s['prev_close'] == 12.09


# ── the morning read ────────────────────────────────────────────────────────

def build(tmp_path, feed=None, client=None, now=NOW, **kw):
    ledger = tmp_path/'calls.csv'
    out = U.build(tmp_path/'state', now, read=feed or live(), client=client or Client(), twins=TWINS,
                  archive=tmp_path/'wire', path=ledger, is_trading=WEEKDAYS, **kw)
    return out, ledger


def test_a_morning_records_the_call_with_its_price_and_writes_the_email(tmp_path):
    client = Client()
    (status, info), ledger = build(tmp_path, client=client)
    assert status == 'READY' and info['calls'] == 1 and info['recorded'] == 1
    shown = client.seen[0][0]
    assert shown['ticker'] == 'EQX.TO' and shown['releases'][0]['text'] == 'Record revenue.'
    row, = U.read_ledger(ledger)
    assert (row['ticker'], row['us'], row['side'], row['material']) == ('EQX.TO', 'EQX', 'LONG', 'true')
    assert float(row['us_px']) == pytest.approx(12.32) and row['us_px_source'] == 'quote mid'
    assert float(row['spy_px']) == pytest.approx(750.05) and float(row['us_prev_close']) == 12.09
    assert row['prompt_version'] == 'day122-v1+day149-us-preopen' and row['read_from'] == 'title and summary'
    assert row['w_open'] == '' and row['scored_at'] == ''
    subject = Path(info['subject_path']).read_text()
    assert subject == 'RB Pre-Open Desk — 2026-11-10 — LONG EQX.TO (EQX)'
    assert 'RB Daily Report — ' not in subject
    text, html = Path(info['text_path']).read_text(), Path(info['html_path']).read_text()
    assert '| LONG EQX.TO (0.70) | EQX | 12.32 at 08:14 (quote mid) | +1.9% |' in text
    assert 'before the bell' in text and 'never sized' in text and 'not a prediction' not in text.lower()[:0]
    assert html.startswith('<!doctype html>') and 'Pre-open research note' in html and '<style' not in html


def test_it_refuses_at_the_open_and_drops_an_answer_that_arrives_after_it(tmp_path):
    client = Client()
    (status, info), ledger = build(tmp_path, client=client, now=dt.datetime(2026, 11, 10, 9, 30, tzinfo=ET))
    assert status == 'TOO_LATE' and client.seen == [] and not ledger.exists()
    ticks = iter([dt.datetime(2026, 11, 10, 9, 29, 50, tzinfo=ET), dt.datetime(2026, 11, 10, 9, 30, 4, tzinfo=ET)])
    status, info = U.build(tmp_path/'late', None, read=live(), client=Client(), twins=TWINS,
                           archive=tmp_path/'wire', path=tmp_path/'late.csv', is_trading=WEEKDAYS,
                           clock=lambda: next(ticks))
    assert status == 'TOO_LATE' and 'ANSWERED_AFTER_THE_OPEN' in info['reason']
    assert not (tmp_path/'late.csv').exists()


def test_nothing_on_a_closed_day_or_a_quiet_night_and_a_dead_feed_is_a_failure(tmp_path):
    saturday = dt.datetime(2026, 11, 14, 8, 15, tzinfo=ET)
    assert build(tmp_path, now=saturday)[0][0] == 'NOTHING'
    (status, info), ledger = build(tmp_path, feed=live(press={}))
    assert status == 'NOTHING' and info['names_checked'] == 3 and not ledger.exists()
    dead = live(press={})
    dead.failures = {'FMP_HTTP_429': 3}
    (status, info), _ = build(tmp_path, feed=dead)
    assert status == 'FAILED' and info['reason'] == 'FMP_HTTP_429'
    assert U.build(tmp_path/'s', NOW, read=live(), client=Client(), twins={}, path=tmp_path/'x.csv',
                   is_trading=WEEKDAYS) == ('FAILED', {'reason': 'NO_US_LISTINGS_MAP'})


def test_a_rerun_keeps_the_first_answer_and_a_sent_day_sends_nothing_more(tmp_path):
    (status, _), ledger = build(tmp_path, client=Client('LONG'))
    again = Client('SHORT')
    (status, info), _ = build(tmp_path, client=again)
    assert status == 'READY' and again.seen == [] and info['recorded'] == 0
    assert [r['side'] for r in U.read_ledger(ledger)] == ['LONG']
    assert 'LONG EQX.TO' in Path(info['text_path']).read_text()
    U.record(tmp_path/'state', 'abc123', NOW)
    assert build(tmp_path)[0] == ('ALREADY_SENT', {})
    tomorrow = NOW + dt.timedelta(days=1)
    assert build(tmp_path, feed=live(press={}), now=tomorrow)[0][0] == 'NOTHING'      # a new day is not blocked


def test_a_price_from_before_the_release_is_not_an_entry(tmp_path):
    fresh = press('Equinox Gold Announces a Sale', NOW - dt.timedelta(minutes=2))
    quote = {'bidPrice': 12.30, 'askPrice': 12.34, 'timestamp': ms(NOW - dt.timedelta(minutes=5))}
    feed = live(press={'EQX': [fresh]}, quotes={'EQX': quote, 'SPY': live().quotes['SPY']})
    (status, info), ledger = build(tmp_path, feed=feed)
    row, = U.read_ledger(ledger)
    assert status == 'READY' and row['us_px'] == '' and row['us_px_source'] == 'older than the release'
    assert 'no fresh pre-market price' in Path(info['text_path']).read_text()


def test_a_routine_release_is_recorded_and_sends_no_email(tmp_path):
    (status, info), ledger = build(tmp_path, client=Client(material=False))
    assert status == 'NOTHING' and info['recorded'] == 1 and 'material' in info['reason']
    assert U.read_ledger(ledger)[0]['material'] == 'false'
    assert not (tmp_path/'state'/U.OUT_DIR/'subject.txt').exists()


def test_a_routine_release_is_listed_under_a_material_one(tmp_path):
    rows = [{'ticker': 'EQX.TO', 'us': 'EQX', 'side': 'LONG', 'confidence': 0.7, 'material': True,
             'reason': 'r', 'title': 'Equinox Gold Reports Q3 Results', 'first_at': '2026-11-09T17:30:00-05:00',
             'us_px': None, 'us_px_at': None, 'us_px_source': None, 'us_prev_close': 12.09},
            {'ticker': 'TD.TO', 'us': 'TD', 'side': 'LONG', 'confidence': 0.5, 'material': False,
             'reason': 'r', 'title': 'TD Bank Group Declares Dividends', 'first_at': '2026-11-09T17:00:00-05:00',
             'us_px': None, 'us_px_at': None, 'us_px_source': None, 'us_prev_close': None}]
    subject, text, _ = U.compose('2026-11-10', rows, NOW, 'Record so far: none.', {'item not answered': 1},
                                 {'third-party notice': 2})
    assert subject.endswith('LONG EQX.TO (EQX)') and 'TD.TO' not in subject
    assert 'Routine, no call shown: TD.TO (TD Bank Group Declares Dividends).' in text
    assert 'Not read: item not answered ×1.' in text and 'Left out: 2 third-party notice(s).' in text


# ── the evening score ───────────────────────────────────────────────────────

def bars(session, open_, p0945, close):
    return [{'date': session + ' 09:30:00', 'open': open_, 'close': open_},
            {'date': session + ' 09:40:00', 'open': p0945, 'close': p0945},
            {'date': session + ' 15:55:00', 'open': close, 'close': close}]


def test_outcomes_are_signed_to_the_side_and_net_of_the_market():
    us, spy = {'open': 101.0, 'p0945': 102.0, 'close': 99.0}, {'open': 100.2, 'p0945': 100.0, 'close': 101.0}
    long = U.outcomes('LONG', 100.0, 100.0, us, spy)
    assert long == {'w_open': pytest.approx(0.8), 'w_0945': pytest.approx(2.0), 'w_close': pytest.approx(-2.0)}
    short = U.outcomes('SHORT', 100.0, 100.0, us, spy)
    assert short['w_open'] == pytest.approx(-0.8)
    assert U.outcomes('LONG', None, 100.0, us, spy) == {}


def test_the_score_fills_blanks_once_and_counts_what_it_cannot_price(tmp_path):
    (_, _), ledger = build(tmp_path)
    rows = U.read_ledger(ledger)
    rows.append({**rows[0], 'ticker': 'IMG.TO', 'us': 'IAG', 'us_px': '', 'us_px_source': ''})
    U.write_ledger(rows, ledger)
    feed = FMP(bars={'EQX': bars('2026-11-10', 12.50, 12.40, 12.10), 'SPY': bars('2026-11-10', 751.0, 752.0, 753.0)})
    morning = U.score(ledger, now=dt.datetime(2026, 11, 10, 12, 0, tzinfo=ET), read=feed)
    assert morning == {'scored': 0, 'unpriced': 0, 'waiting': 0} and feed.asked == []
    evening = dt.datetime(2026, 11, 10, 16, 25, tzinfo=ET)
    assert U.score(ledger, now=evening, read=feed) == {'scored': 1, 'unpriced': 1, 'waiting': 0}
    eqx, img = U.read_ledger(ledger)
    want = 100 * ((12.50 / 12.32 - 1) - (751.0 / 750.05 - 1))
    assert float(eqx['w_open']) == pytest.approx(want, abs=1e-3) and float(eqx['us_open']) == 12.5
    assert img['w_open'] == '' and img['scored_at'] != ''
    before = ledger.read_text()
    changed = FMP(bars={'EQX': bars('2026-11-10', 99, 99, 99), 'SPY': bars('2026-11-10', 1, 1, 1)})
    assert U.score(ledger, now=evening, read=changed)['scored'] == 0 and ledger.read_text() == before


def test_a_session_without_its_bars_waits(tmp_path):
    (_, _), ledger = build(tmp_path)
    feed = FMP(bars={'EQX': bars('2026-11-10', 12.5, 12.4, 12.1)[:2]})
    out = U.score(ledger, now=dt.datetime(2026, 11, 10, 16, 25, tzinfo=ET), read=feed)
    assert out == {'scored': 0, 'unpriced': 0, 'waiting': 1} and U.read_ledger(ledger)[0]['scored_at'] == ''


# ── the registered decision ─────────────────────────────────────────────────

def planted(tmp_path, sessions, mean, flip=0.0):
    rows, day = [], dt.date(2026, 11, 10)
    for k in range(sessions):
        w = mean + (0.3 if k % 2 else -0.3) + (flip if k >= sessions // 2 else 0)
        rows.append({'session': (day + dt.timedelta(days=k)).isoformat(), 'ticker': 'EQX.TO', 'us': 'EQX',
                     'side': 'LONG', 'confidence': 0.7, 'material': True, 'us_px': 10.0, 'us_bid': 9.99,
                     'us_ask': 10.01, 'spy_px': 500.0, 'w_open': w})
    path = tmp_path/'v.csv'
    U.write_ledger(rows, path)
    return path


def test_the_verdict_waits_for_forty_sessions_and_reads_the_registered_bar(tmp_path):
    assert U.verdict(planted(tmp_path, 12, 1.0)) == {'verdict': 'NOT_DUE', 'sessions': 12, 'due_at': 40}
    good = U.verdict(planted(tmp_path, 40, 0.6))
    assert good['verdict'] == 'PASS' and good['t'] >= 3 and good['net_pct'] > 0 and good['sessions'] == 40
    assert good['cost_pct'] == pytest.approx(0.1 + U.EXIT_COST)       # each call's own half-spread, plus the exit
    assert U.verdict(planted(tmp_path, 40, -0.05))['verdict'] == 'FAIL'
    assert U.verdict(planted(tmp_path, 40, 0.05))['verdict'] == 'CONTINUE'
    thin = U.verdict(planted(tmp_path, 40, 0.14))                     # positive, under its own cost
    assert thin['verdict'] == 'CONTINUE' and thin['net_pct'] < 0
    assert U.verdict(planted(tmp_path, 40, 0.6, flip=-1.3))['verdict'] != 'PASS'    # the halves disagree


def test_routine_and_unpriced_calls_are_not_in_the_verdict(tmp_path):
    path = planted(tmp_path, 40, 0.6)
    rows = U.read_ledger(path)
    rows[0]['material'] = 'false'
    rows[1]['w_open'] = ''
    U.write_ledger(rows, path)
    assert U.verdict(path) == {'verdict': 'NOT_DUE', 'sessions': 38, 'due_at': 40}


# ── the New York listings ───────────────────────────────────────────────────

def test_a_listing_is_matched_by_isin_never_by_its_letters():
    profiles = {'IMG.TO': {'isin': 'CA_IAMGOLD'}, 'IAG.TO': {'isin': 'CA_IA_FIN'}, 'XYZ.TO': {},
                'IAG': {'isin': 'CA_IAMGOLD', 'exchange': 'NYSE', 'companyName': 'IAMGOLD Corporation'},
                'IAFNF': {'isin': 'CA_IA_FIN', 'exchange': 'OTC', 'companyName': 'iA Financial'}}
    listings = {'CA_IAMGOLD': [{'symbol': 'IMG.TO'}, {'symbol': 'IAG'}],
                'CA_IA_FIN': [{'symbol': 'IAG.TO'}, {'symbol': 'IAFNF'}]}

    def read(path, **p):
        if path == 'profile':
            return [profiles[p['symbol']]] if profiles.get(p['symbol']) else []
        return listings.get(p['isin'], [])
    out = U.build_twins(['IMG.TO', 'IAG.TO', 'XYZ.TO'], read, dt.date(2026, 11, 9))
    assert out['twins'] == {'IMG.TO': {'us': 'IAG', 'isin': 'CA_IAMGOLD', 'exchange': 'NYSE',
                                       'name': 'IAMGOLD Corporation'}}
    assert out['not_listed'] == {'no US listing': 1, 'no ISIN': 1} and out['names_asked'] == 3


def test_the_committed_map_is_real_and_holds_the_known_traps():
    twins = U.load_twins()
    assert len(twins) >= 60 and all(t.endswith('.TO') and v['exchange'] in U.US_EXCHANGES
                                    for t, v in twins.items())
    assert twins['IMG.TO']['us'] == 'IAG' and 'IAG.TO' not in twins          # iA Financial has no US listing
    assert twins['ABX.TO']['us'] == 'B' and twins['K.TO']['us'] == 'KGC' and twins['CCO.TO']['us'] == 'CCJ'
    assert set(U.ALIASES) <= set(twins)


# ── the Routine ─────────────────────────────────────────────────────────────

def test_the_routine_prompt_names_real_commands_and_carries_no_key():
    text = (ROOT/'ROUTINE_PREOPEN.md').read_text()
    for flag in ('--build', '--record', '--message-id', '--state-dir'):
        assert 'us_preopen.py' in text and flag in text
    assert 'send_check.py' in text and 'newswire.py --collect' in text
    assert 'RB Daily Report — ' not in text.replace('never contains "RB Daily Report — "', '')
    for secret in ('sk-', 'apikey=', 'AIza'):
        assert secret not in text
    assert 'Never create, modify, enable, disable or delete any Routine' in text


def test_the_registration_fixes_what_the_code_does():
    doc = (ROOT/'PREREGISTER_day149_us_preopen.md').read_text()
    for needle in ('40 sessions', 'seed 149', '0.05%', 'title and summary', 'ISIN', '09:30 open',
                   '10 minutes', '30 minutes', '1%'):
        assert needle in doc, needle
    assert U.DECISION == 40 and U.FINAL == 80 and U.SEED == 149 and U.BAR == 3.0 and U.PLACEBO_P == 0.01
    assert U.QUOTE_FRESH == dt.timedelta(minutes=10) and U.TRADE_FRESH == dt.timedelta(minutes=30)
    assert U.QUOTE_MAX_SPREAD == 0.01 and U.PROMPT_VERSION == N.PROMPT_VERSION + '+day149-us-preopen'
