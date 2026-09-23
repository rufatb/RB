"""A null-placeholder session is rebuilt only from a complete hourly session."""
import datetime as dt
from zoneinfo import ZoneInfo

import pandas as pd
import pytest

import daily_technicals
import session_fill

TZ = 'America/Toronto'
HOLE = dt.date(2026, 9, 22)


def hourly(day=HOLE, times=('09:30', '10:30', '11:30', '12:30', '13:30', '14:30', '15:30'), close=10.0):
    idx = [pd.Timestamp('%s %s' % (day, t), tz=TZ) for t in times]
    n = len(idx)
    return pd.DataFrame({'Open': [close]*n, 'High': [close+1]*n, 'Low': [close-1]*n,
                         'Close': [close]*(n-1)+[close+0.5], 'Volume': [100.0]*n}, index=idx)


def daily(days):
    idx = [pd.Timestamp('%s 09:30' % d, tz=TZ) for d in days]
    return pd.DataFrame({'Open': 1.0, 'High': 2.0, 'Low': 0.5, 'Close': 1.5, 'Volume': 1000.0}, index=idx)


def test_complete_session_is_rebuilt_open_high_low_last_close_summed_volume():
    frame, filled = session_fill.fill(daily(['2026-09-21', '2026-09-23']), hourly(), [HOLE])
    assert filled == [HOLE]
    row = frame.loc[[i.date() == HOLE for i in frame.index]].iloc[0]
    assert (row['Open'], row['High'], row['Low'], row['Close'], row['Volume']) == (10.0, 11.0, 9.0, 10.5, 700.0)
    assert [i.date().isoformat() for i in frame.index] == ['2026-09-21', '2026-09-22', '2026-09-23']


@pytest.mark.parametrize('times', [
    ('09:30', '10:30', '11:30', '12:30', '13:30', '14:30'),          # no last hour
    ('10:30', '11:30', '12:30', '13:30', '14:30', '15:30', '15:30'),  # no first hour
    ('09:30', '10:30', '11:30', '12:30'),                            # half day
    ('09:30',),                                                      # one bar
])
def test_incomplete_hourly_session_leaves_the_hole(times):
    frame, filled = session_fill.fill(daily(['2026-09-21', '2026-09-23']), hourly(times=times), [HOLE])
    assert filled == [] and len(frame) == 2


def test_an_hour_without_a_print_is_zero_volume_not_a_hole():
    """Illiquid names (DRMA, QNRX on 2026-09-22) have no bar for an hour with
    no trade; the bookends still prove the session ran to 15:30."""
    times = ('09:30', '10:30', '11:30', '12:30', '13:30', '15:30')
    _, filled = session_fill.fill(daily(['2026-09-21', '2026-09-23']), hourly(times=times), [HOLE])
    assert filled == [HOLE]


def test_placeholder_dates_are_the_provider_null_closes():
    stamps = [int(pd.Timestamp('%s 09:30' % d, tz=TZ).timestamp()) for d in ('2026-09-21', '2026-09-22', '2026-09-23')]
    raw = {'timestamp': stamps, 'indicators': {'quote': [{'close': [1.0, None, 2.0]}]}}
    assert session_fill.placeholder_dates(raw, TZ) == [HOLE]


class FakeAdapter:
    """Yahoo's daily chart with a null placeholder on 09-22, and its hourly bars."""
    exchange_tz = TZ

    def __init__(self, hourly_frame):
        self.hourly = hourly_frame
        days = pd.bdate_range('2025-09-01', '2026-09-23')
        self.days = [d.date() for d in days]

    def _chart(self, ticker, interval, rng):
        if interval == '60m':
            if self.hourly is None:
                raise RuntimeError('rate limited')
            return {'hourly': True}
        stamps = [int(pd.Timestamp('%s 09:30' % d, tz=TZ).timestamp()) for d in self.days]
        closes = [None if d == HOLE else 100.0 + i*0.1 for i, d in enumerate(self.days)]
        return {'meta': {'symbol': ticker, 'instrumentType': 'EQUITY', 'currency': 'CAD'},
                'timestamp': stamps,
                'indicators': {'quote': [{'open': closes, 'high': [c and c+1 for c in closes],
                                          'low': [c and c-1 for c in closes], 'close': closes,
                                          'volume': [c and 1000.0 for c in closes]}]}}

    def _bars_df(self, raw):
        if raw.get('hourly'):
            return self.hourly
        q = raw['indicators']['quote'][0]
        idx = pd.to_datetime(raw['timestamp'], unit='s', utc=True).tz_convert(TZ)
        return pd.DataFrame({'Open': q['open'], 'High': q['high'], 'Low': q['low'],
                             'Close': q['close'], 'Volume': q['volume']}, index=idx).dropna(subset=['Close'])


NOW = dt.datetime(2026, 9, 24, 9, 5, tzinfo=ZoneInfo('America/New_York'))


def test_daily_technicals_rebuild_the_hole_and_disclose_it():
    tech, meta = daily_technicals.from_yahoo('ABC.TO', FakeAdapter(hourly(close=250.0)), NOW)
    assert meta['rebuilt_sessions'] == ['2026-09-22']
    # The last move is 09-23 against the REBUILT 09-22, not against 09-21.
    assert tech['daily_close_prev'] == 250.5
    scope = daily_technicals.scope(tech['daily_sessions'], meta['rebuilt_sessions'])
    assert '2026-09-22 from hourly bars' in scope and len(scope) <= 160


def test_an_unfillable_recent_hole_refuses_the_name():
    with pytest.raises(ValueError, match='DAILY_SESSION_PLACEHOLDER_UNFILLED'):
        daily_technicals.from_yahoo('ABC.TO', FakeAdapter(None), NOW)
