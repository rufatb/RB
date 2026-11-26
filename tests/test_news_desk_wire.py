"""Day-156: the news desk knows a blind wire from a quiet morning. On 11-26 it read
an empty archive and printed "No liquid TSX name had an overnight release today"
over a wire nobody had read since 09:26 the day before."""
import datetime as dt
import json

import news_desk as N
import newswire

ET = N.ET
S = dt.date(2026, 11, 26)                     # window: Wed 16:00 -> Thu 09:30
NOW = dt.datetime(2026, 11, 26, 9, 32, tzinfo=ET)


class Client:
    def __init__(self):
        self.chat = self
        self.completions = self
        self.seen = 0

    def create(self, **kw):
        self.seen += 1
        items = json.loads(kw['messages'][1]['content'])['items']
        content = json.dumps({'calls': [{'id': i['id'], 'ticker': i['ticker'], 'side': 'LONG',
                                         'confidence': 0.6, 'material': True, 'reason': 'r'}
                                        for i in items]})

        class R:
            model = 'deepseek-v4-pro'
            choices = [type('C', (), {'finish_reason': 'stop',
                                      'message': type('M', (), {'content': content})})]
        return R


def chart(ticker):
    import pandas as pd
    days = pd.bdate_range(end=pd.Timestamp(S), periods=30, tz='America/Toronto')
    frame = pd.DataFrame({'Open': 10.0, 'High': 10.0, 'Low': 10.0, 'Close': 10.0,
                          'Volume': 1_000_000.0}, index=days)
    return {'instrumentType': 'EQUITY', 'currency': 'CAD'}, frame


def wire(tmp_path, rows):
    root = tmp_path / 'wire'
    root.mkdir(exist_ok=True)
    newswire.append(rows, root)
    return root


def row(at, tickers, title='T', source='newswire.ca rss'):
    return {'published_at': at, 'tickers': tickers, 'title': title, 'source': source,
            'url': f'https://www.newswire.ca/news-releases/x-{abs(hash((at, title)))}.html'}


def stage(tmp_path, root, client=None):
    return N.stage(tmp_path, NOW, chart=chart, archive=root, client=client or Client(),
                   collect=False, path=tmp_path / 'news_calls.csv')


def test_an_empty_window_is_blind_not_quiet(tmp_path, monkeypatch, capsys):
    root = wire(tmp_path, [row('2026-11-25T09:26:00-05:00', ['AAA.TO'])])   # before the window
    client = Client()
    out = stage(tmp_path, root, client)
    assert out['events'] == 0 and client.seen == 0
    assert out['wire']['releases_in_window'] == 0 and N.blind(out)
    sec = N.section(tmp_path, NOW, path=tmp_path / 'news_calls.csv')
    assert sec['status'] == 'BLIND'
    text = '\n'.join(N.lines(sec, concise=True))
    assert '⚠ The news desk could not read the wire today' in text
    assert 'not a quiet morning' in text and 'No liquid TSX name' not in text
    # The command says so with its own exit, which the morning logs as a fault.
    monkeypatch.setattr(N, 'stage', lambda state_dir: out)
    assert N.main(['--stage', '--state-dir', str(tmp_path)]) == 7
    assert 'BLIND' in capsys.readouterr().err


def test_a_quiet_window_that_was_read_is_still_quiet(tmp_path):
    """Releases in the window, none on a listed name: read, and nothing to call."""
    root = wire(tmp_path, [row('2026-11-25T18:00:00-05:00', [], 'Government announces funding')])
    for a, b in (('2026-11-25T16:00', '2026-11-26T09:31'),):
        newswire.log_read('rss', dt.datetime.fromisoformat(a).replace(tzinfo=ET),
                          dt.datetime.fromisoformat(b).replace(tzinfo=ET), state_dir=tmp_path)
    out = stage(tmp_path, root)
    assert out['events'] == 0 and not N.blind(out)
    assert out['wire']['coverage']['uncovered_minutes'] == 0
    sec = N.section(tmp_path, NOW, path=tmp_path / 'news_calls.csv')
    assert sec['status'] == 'READY'
    text = '\n'.join(N.lines(sec, concise=True))
    assert 'No liquid TSX name had an overnight release today.' in text and '⚠' not in text


def test_a_window_read_only_in_part_says_which_part(tmp_path):
    root = wire(tmp_path, [row('2026-11-26T08:10:00-05:00', ['AAA.TO'], 'AAA agrees to a deal')])
    newswire.log_read('rss', dt.datetime(2026, 11, 26, 8, 2, tzinfo=ET),
                      dt.datetime(2026, 11, 26, 9, 31, tzinfo=ET), state_dir=tmp_path)
    out = stage(tmp_path, root)
    assert out['events'] == 1 and len(out['calls']) == 1
    assert out['wire']['sources'] == {'newswire.ca rss': 1}
    assert out['wire']['coverage']['uncovered_minutes'] == 962
    sec = N.section(tmp_path, NOW, path=tmp_path / 'news_calls.csv')
    assert sec['status'] == 'READY'
    text = '\n'.join(N.lines(sec, concise=True))
    assert '⚠ The wire was not read from Wed 16:00 to Thu 08:02 (962 minutes' in text
    assert 'LONG AAA.TO' in text


def test_a_window_with_no_read_logged_says_its_coverage_is_unknown(tmp_path):
    root = wire(tmp_path, [row('2026-11-26T08:10:00-05:00', ['AAA.TO'])])
    stage(tmp_path, root)
    sec = N.section(tmp_path, NOW, path=tmp_path / 'news_calls.csv')
    assert sec['status'] == 'READY'
    assert any(l.startswith('⚠ Which part of the night the wire was read is not known')
               for l in N.lines(sec, concise=True))


def test_a_section_from_before_renders_as_it_did(tmp_path):
    sec = {'status': 'READY', 'calls': [], 'layout': N.LAYOUT}      # no `wire`: staged before day-156
    text = N.lines(sec, concise=True)
    assert text[-1] == 'No liquid TSX name had an overnight release today.'
    assert not any('⚠' in l for l in text)


def test_a_failed_coverage_check_says_so(tmp_path):
    sec = {'status': 'READY', 'calls': [], 'layout': N.LAYOUT, 'wire': {'error': 'OSError'}}
    assert N.wire_lines(sec) == ['⚠ Whether the wire was read whole could not be checked today (OSError).']


def test_each_call_records_where_its_symbol_came_from(tmp_path):
    """Day-156b, amendment 2: 'opening' (a feed or list card) or 'tag' (sitemap only)."""
    root = wire(tmp_path, [
        {**row('2026-11-26T08:10:00-05:00', ['AAA.TO'], 'AAA agrees to a deal'), 'tickers_from': 'opening'},
        {**row('2026-11-25T18:00:00-05:00', ['BBB.TO'], 'BBB reports', source='newswire.ca sitemap'),
         'tickers_from': 'tag'},
        row('2026-11-25T19:00:00-05:00', ['CCC.TO'], 'CCC from the list era', source='newswire.ca list')])
    stage(tmp_path, root)
    got = {(r['ticker'], r['arm']): r['tickers_from'] for r in N.read(tmp_path / 'news_calls.csv')}
    assert got == {('AAA.TO', 'full'): 'opening', ('AAA.TO', 'headline'): 'opening',
                   ('BBB.TO', 'full'): 'tag', ('BBB.TO', 'headline'): 'tag',
                   ('CCC.TO', 'full'): 'opening', ('CCC.TO', 'headline'): 'opening'}
    assert N.FIELDS[-1] == 'tickers_from'              # a new last column; older rows read blank
