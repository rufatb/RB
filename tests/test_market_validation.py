"""Adversarial market-data gates; every invalid price must fail closed."""
import copy
import datetime as dt
from zoneinfo import ZoneInfo
import pytest
import quotes as Q
from test_daily_pipeline import NOW,market_row


@pytest.mark.parametrize('bid,ask',[(None,2),(0,2),(-1,2),(2,1),(float('nan'),2),(1,float('inf')),(True,2)])
def test_invalid_bbo_cannot_become_a_zero_cost_trade(bid,ask):
    row=market_row('AAA.TO');row.update(bid=bid,ask=ask)
    q=Q.validate_equity(row,'AAA.TO',NOW,currency='CAD')
    assert q['status']!='OK' and q['spread_bps'] is None
    assert Q.option_mid(row)==(None,'none')


@pytest.mark.parametrize('field,value',[('symbol','BBB.TO'),('currency','USD'),
    ('bidAskTimestamp',None),('bidAskTimestamp',(NOW-dt.timedelta(minutes=3)).timestamp()),
    ('bidAskTimestamp',(NOW+dt.timedelta(seconds=1)).timestamp())])
def test_bad_identity_or_clock_is_unusable(field,value):
    row=market_row('AAA.TO');row[field]=value
    assert Q.validate_equity(row,'AAA.TO',NOW,currency='CAD')['status']!='OK'


def test_last_trade_timestamp_is_not_bbo_timestamp():
    row=market_row('AAA.TO');del row['bidAskTimestamp']
    out=Q.validate_equity(row,'AAA.TO',NOW,currency='CAD')
    assert out['mark']==100 and out['spread_bps'] is None


def chain():
    expiry=int(dt.datetime(2026,10,16,tzinfo=dt.timezone.utc).timestamp())
    row={'strike':100.,'bid':4.9,'ask':5.1,'currency':'USD','expiration':expiry,
         'quoteTime':NOW.timestamp(),'openInterest':10,'impliedVolatility':.5}
    initial={'quote':market_row('AAA'),'expirationDates':[expiry]}
    full={'options':[{'expirationDate':expiry,'calls':[row.copy()],'puts':[row.copy()]}]}
    class Client:
        def chain(self,t,exp=None):return full if exp else initial
    return Client(),initial,full


def test_valid_matched_options_and_expiry():
    client,_,_=chain();r=Q.event_quote(client,'AAA',dt.date(2026,10,1),NOW)
    assert r['status']=='OK' and r['move']==.1 and r['iv']==.5


@pytest.mark.parametrize('kind',['crossed','nan','wrong_strike','wrong_expiry','stale','missing_timestamp','zero_oi','wrong_currency','stale_spot'])
def test_option_pair_rejects_each_invalid_case(kind):
    client,initial,full=chain();leg=full['options'][0]['puts'][0]
    if kind=='crossed':leg['bid']=9
    if kind=='nan':leg['ask']=float('nan')
    if kind=='wrong_strike':leg['strike']=95
    if kind=='wrong_expiry':leg['expiration']+=86400
    if kind=='stale':leg['quoteTime']=NOW.timestamp()-3600
    if kind=='missing_timestamp':del leg['quoteTime']
    if kind=='zero_oi':leg['openInterest']=0
    if kind=='wrong_currency':leg['currency']='CAD'
    if kind=='stale_spot':initial['quote']['regularMarketTime']=NOW.timestamp()-3600
    r=Q.event_quote(client,'AAA',dt.date(2026,10,1),NOW)
    assert r['status']!='OK' and r['move'] is None and r['put_pct'] is None


def test_same_strike_required_even_for_diagnostics():
    assert Q.option_metrics([{'strike':100,'bid':1,'ask':2}],
                            [{'strike':99,'bid':1,'ask':2}],100)['move'] is None
