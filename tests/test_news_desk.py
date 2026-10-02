"""Day-122 Part 6 — the news desk (PREREGISTER_day122_releases.md)."""
import datetime as dt
import json
import re
from pathlib import Path

import pandas as pd
import pytest

import news_desk as N

ET = N.ET
S = dt.date(2026, 10, 2)          # a Friday; window = Thu 16:00 → Fri 09:30


def test_the_prompt_is_the_registered_one_verbatim():
    doc = (Path(__file__).resolve().parent.parent / 'PREREGISTER_day122_releases.md').read_text()
    assert re.search(r'```\n(.*?)\n```', doc, re.S).group(1) == N.SYSTEM_PROMPT
    assert N.PROMPT_VERSION == 'day122-v1' and N.MODEL == 'deepseek-v4-pro'


def daily(n=30, close=10.0, volume=1_000_000, last=S, open_=None, final=None):
    days = pd.bdate_range(end=pd.Timestamp(last), periods=n, tz='America/Toronto')
    f = pd.DataFrame({'Open': close, 'High': close, 'Low': close, 'Close': close,
                      'Volume': volume}, index=days, dtype=float)
    if open_ is not None:
        f.iloc[-1, f.columns.get_loc('Open')] = open_
    if final is not None:
        f.iloc[-1, f.columns.get_loc('Close')] = final
    return f


EQ = {'instrumentType': 'EQUITY', 'currency': 'CAD'}


def test_the_liquidity_filter_names_its_reason():
    assert N.liquid(EQ, daily(), S) is None
    assert N.liquid({'instrumentType': 'ETF', 'currency': 'CAD'}, daily(), S) == 'not an equity'
    assert N.liquid({**EQ, 'currency': 'USD'}, daily(), S) == 'not quoted in CAD'
    assert N.liquid(EQ, daily(n=15), S) == 'fewer than 21 prior sessions'
    assert N.liquid(EQ, daily(close=1.5, volume=10_000_000), S) == 'price under C$2'
    assert N.liquid(EQ, daily(volume=200_000), S) == 'traded value under C$3M a day'
    assert N.liquid(EQ, daily(last=S - dt.timedelta(days=1)), S) == 'no bar for the session'


def archive(tmp_path, rows):
    root = tmp_path / 'wire'
    root.mkdir()
    by = {}
    for r in rows:
        by.setdefault(r['published_at'][:10], []).append(r)
    for day, rs in by.items():
        (root / f'{day}.jsonl').write_text(''.join(json.dumps(r) + '\n' for r in rs))
    return root


def rel(at, tickers, title='T', url=None):
    return {'published_at': at, 'tickers': tickers, 'title': title, 'source': 'newswire.ca',
            'url': url or f'https://www.newswire.ca/x-{abs(hash((at, title)))}.html'}


def test_events_take_the_first_lead_symbol_in_the_window_and_merge_a_name(tmp_path):
    root = archive(tmp_path, [
        rel('2026-10-01T17:00:00-04:00', ['AAA.TO'], 'first'),
        rel('2026-10-02T07:00:00-04:00', ['AAA.TO'], 'second'),
        rel('2026-10-02T07:30:00-04:00', ['BBB.TO', 'CCC.TO'], 'fund names a holding'),
        rel('2026-10-02T08:00:00-04:00', ['DDD.V'], 'venture'),
        rel('2026-10-01T15:00:00-04:00', ['EEE.TO'], 'before the window'),
        rel('2026-10-02T09:35:00-04:00', ['FFF.TO'], 'after the open'),
        rel('2026-10-02T08:10:00-04:00', ['GGG.TO'], 'illiquid'),
    ])
    charts = {'AAA.TO': (EQ, daily()), 'BBB.TO': (EQ, daily()),
              'GGG.TO': (EQ, daily(volume=100))}
    evs, excluded = N.events(S, chart=lambda t: charts[t], archive=root)
    assert [e['ticker'] for e in evs] == ['AAA.TO', 'BBB.TO']
    assert [r['title'] for r in evs[0]['releases']] == ['first', 'second']
    assert excluded == {'traded value under C$3M a day': 1}


def test_items_headline_arm_carries_no_text_and_full_text_is_capped():
    e = {'id': 'x', 'ticker': 'AAA.TO', 'releases': [rel('2026-10-02T07:00:00-04:00', ['AAA.TO'],
                                                         url='u1')]}
    full = N.items([e], 'full', {'u1': 'y' * 5000})[0]['releases'][0]
    head = N.items([e], 'headline', {'u1': 'y' * 5000})[0]['releases'][0]
    assert len(full['text']) == N.BODY_CHARS and 'text' not in head
    assert full['at'] == '2026-10-02 07:00 ET'


def test_a_bad_entry_loses_only_its_own_item():
    batch = [{'id': i, 'ticker': i} for i in 'abcdef']
    reply = {'calls': [
        {'id': 'a', 'side': 'long', 'confidence': 0.6, 'material': True, 'reason': 'ok'},
        {'id': 'b', 'side': 'HOLD', 'confidence': 0.6},
        {'id': 'c', 'side': 'SHORT', 'confidence': 0.4},
        {'id': 'd', 'side': 'SHORT', 'confidence': 0.7}, {'id': 'd', 'side': 'LONG', 'confidence': 0.7},
        {'id': 'zz', 'side': 'LONG', 'confidence': 0.7},
    ]}
    calls, problems = N.parse(reply, batch)
    assert calls == {'a': {'side': 'LONG', 'confidence': 0.6, 'material': True, 'reason': 'ok'}}
    assert problems == {'invalid side': 1, 'confidence outside 0.5-1': 1, 'id answered twice': 2,
                        'unknown id': 1, 'item not answered': 2}


def test_batches_are_at_most_twelve_in_ticker_order():
    its = [{'id': str(i), 'ticker': f'{i:02d}.TO'} for i in range(25, 0, -1)]
    b = N.batches(its)
    assert [len(x) for x in b] == [12, 12, 1] and b[0][0]['ticker'] == '01.TO'


def bars5(day, entry, exit_):
    idx = pd.date_range(dt.datetime.combine(day, dt.time(9, 30)), periods=78, freq='5min', tz=ET)
    f = pd.DataFrame({'Close': entry}, index=idx, dtype=float)
    f.loc[f.index.time >= dt.time(15, 55), 'Close'] = exit_
    return f


def test_outcomes_are_signed_and_market_adjusted():
    stock1 = daily(open_=10.0, final=10.5)          # prior closes 10.0: gap 0, day +5%
    mkt1 = daily(close=40.0, open_=40.0, final=40.4)  # market day +1%
    o = N.outcomes('SHORT', S, bars5(S, 10.0, 10.2), stock1, bars5(S, 40.0, 40.0), mkt1)
    assert o['w945_raw'] == pytest.approx(-2.0) and o['w945'] == pytest.approx(-2.0)
    assert o['w_day_raw'] == pytest.approx(-5.0) and o['w_day'] == pytest.approx(-4.0)
    assert o['gap'] == pytest.approx(0.0) and 'w5d' not in o


class Client:
    """Answers every item LONG; records what it was shown."""
    def __init__(self):
        self.seen = []
        self.chat = self
        self.completions = self

    def create(self, **kw):
        items = json.loads(kw['messages'][1]['content'])['items']
        self.seen.append(items)
        assert kw['messages'][0]['content'] == N.SYSTEM_PROMPT
        assert kw['extra_body'] == {'thinking': {'type': 'disabled'}}
        content = json.dumps({'calls': [{'id': i['id'], 'ticker': i['ticker'], 'side': 'LONG',
                                         'confidence': 0.55, 'material': True, 'reason': 'r'}
                                        for i in items]})

        class R:
            model = 'deepseek-v4-pro'
            choices = [type('C', (), {'finish_reason': 'stop',
                                      'message': type('M', (), {'content': content})})]
        return R


def staged(tmp_path, client):
    root = archive(tmp_path, [rel('2026-10-02T07:00:00-04:00', ['AAA.TO'], 'Big deal',
                                  url='https://www.newswire.ca/aaa.html')])
    ledger = tmp_path / 'news_calls.csv'
    now = dt.datetime(2026, 10, 2, 9, 32, tzinfo=ET)
    page = '<section class="release-body container">AAA agrees to <b>a deal</b>.</section>'
    import newswire
    orig = newswire._get
    newswire._get = lambda url, session=None: page
    try:
        out = N.stage(tmp_path, now, chart=lambda t: (EQ, daily(last=S - dt.timedelta(days=1))),
                      archive=root, client=client, collect=False, path=ledger)
    finally:
        newswire._get = orig
    return out, ledger, now


def test_stage_asks_both_arms_records_both_and_the_section_reads_it(tmp_path):
    client = Client()
    out, ledger, now = staged(tmp_path, client)
    assert out['events'] == 1 and len(client.seen) == 2
    full, head = client.seen
    assert full[0]['releases'][0]['text'] == 'AAA agrees to a deal .'
    assert 'text' not in head[0]['releases'][0]
    rows = N.read(ledger)
    assert [(r['ticker'], r['arm'], r['side']) for r in rows] == [
        ('AAA.TO', 'full', 'LONG'), ('AAA.TO', 'headline', 'LONG')]
    assert all(r['prompt_version'] == 'day122-v1' for r in rows)
    sec = N.section(tmp_path, now, path=ledger)
    assert sec['status'] == 'READY' and sec['calls'][0]['ticker'] == 'AAA.TO'
    text = '\n'.join(N.lines(sec))
    assert 'Part 6' in text and 'LONG AAA.TO' in text and 'same' in text
    # a rerun the same morning never writes a second row
    N.stage(tmp_path, now, chart=lambda t: (EQ, daily(last=S - dt.timedelta(days=1))),
            archive=tmp_path / 'wire', client=client, collect=False, path=ledger)
    assert len(N.read(ledger)) == 2


def test_section_without_staging_is_unavailable_and_says_why(tmp_path):
    sec = N.section(tmp_path, dt.datetime(2026, 10, 2, 9, 46, tzinfo=ET), path=tmp_path / 'x.csv')
    assert sec['status'] == 'UNAVAILABLE'
    assert 'not read' in '\n'.join(N.lines(sec))


def test_score_fills_same_day_after_the_close_and_never_before(tmp_path):
    client = Client()
    _, ledger, _ = staged(tmp_path, client)
    frames = {'AAA.TO': daily(open_=10.0, final=10.3), N.MARKET: daily(close=40.0)}
    b5 = {'AAA.TO': bars5(S, 10.0, 10.1), N.MARKET: bars5(S, 40.0, 40.0)}
    kw = dict(path=ledger, bars_for=b5.get, chart=lambda t: (EQ, frames[t]))
    assert N.score(now=dt.datetime(2026, 10, 2, 15, 0, tzinfo=ET), **kw) == 0
    assert N.score(now=dt.datetime(2026, 10, 2, 16, 20, tzinfo=ET), **kw) == 2
    r = N.read(ledger)[0]
    assert float(r['w945']) == pytest.approx(1.0) and float(r['w_day']) == pytest.approx(3.0)
    assert r['scored_at'] and not r['scored_5d_at']
    assert '1/1 right' in N.record_line(ledger)
