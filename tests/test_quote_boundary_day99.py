"""One quote boundary: isolate failures, preserve timestamps and outage records."""
import datetime as dt
import json
import urllib.error
from zoneinfo import ZoneInfo

import pytest

import quotes as Q

NOW = dt.datetime(2026, 9, 11, 9, 46, 20, tzinfo=ZoneInfo('America/New_York'))


def raw(ticker='TRP.TO', now=NOW):
    return dict(symbol=ticker, currency='CAD' if ticker.endswith('.TO') else 'USD',
                regularMarketPrice=100, regularMarketTime=now.timestamp(),
                bid=99.99, ask=100.01, bidAskTimestamp=now.timestamp())


def test_malformed_rows_do_not_discard_healthy_quotes():
    source={'TRP.TO':raw(), 'ENB.TO':None, 'BCE.TO':['bad']}
    rows=Q.validate_equities(source, ['TRP.TO','ENB.TO','BCE.TO','SLF.TO'], NOW)
    assert rows['TRP.TO']['status']=='OK'
    assert rows['ENB.TO']['reason_code']=='INVALID_PAYLOAD'
    assert rows['BCE.TO']['reason_code']=='INVALID_PAYLOAD'
    assert rows['SLF.TO']['status']=='UNAVAILABLE'
    assert rows['SLF.TO']['spread_bps'] is None
    assert source['ENB.TO'] is None


@pytest.mark.parametrize('payload', [None, [], 'not a quote batch'])
def test_invalid_batch_has_an_explicit_row_for_every_requested_symbol(payload):
    out=Q.validate_equities(payload,['TRP.TO','ENB.TO'],NOW)
    assert len(out)==2
    assert all(r['reason_code']=='INVALID_PAYLOAD' for r in out.values())


@pytest.mark.parametrize('shift', [-600, 60])
def test_supplied_stale_or_future_timestamp_cannot_be_corroborated(shift):
    quote=raw();quote['bidAskTimestamp']=(NOW+dt.timedelta(seconds=shift)).timestamp()
    def forbid(t): pytest.fail('a supplied invalid timestamp must not be corroborated')
    out=Q.validate_equity(quote,'TRP.TO',NOW,corroborate=forbid)
    assert out['status']=='UNAVAILABLE' and out['reason_code']=='STALE_QUOTE'


def test_failed_corroboration_is_explicit_and_does_not_leak_exception_text(caplog):
    quote=raw();quote.pop('bidAskTimestamp')
    def fail(t): raise ConnectionError('https://provider.test/?api_key=PRIVATE_TOKEN')
    out=Q.validate_equity(quote,'TRP.TO',NOW,corroborate=fail)
    assert out['corroboration_error_class']=='ConnectionError'
    assert out['status']=='UNAVAILABLE'
    assert 'PRIVATE_TOKEN' not in json.dumps(out)+caplog.text


class Client:
    def __init__(self, errors=()): self.errors=list(errors);self.calls=0
    def get(self,tickers):
        self.calls+=1
        if self.errors: raise self.errors.pop(0)
        return {t:raw(t) for t in tickers}


def test_transient_error_has_one_retry_and_preserves_success(caplog):
    client=Client([ConnectionError('PRIVATE_TOKEN')])
    out=Q.fetch_equities(client,['TRP.TO'],NOW)
    assert client.calls==2 and out['TRP.TO']['status']=='OK'
    assert out['TRP.TO']['acquisition_attempts']==2
    assert 'PRIVATE_TOKEN' not in caplog.text


@pytest.mark.parametrize('code', [401,403,429,400])
def test_auth_rate_limit_and_bad_request_never_retry(code):
    error=urllib.error.HTTPError('https://host/?key=PRIVATE_TOKEN',code,'PRIVATE_TOKEN',{},None)
    client=Client([error])
    out=Q.fetch_equities(client,['TRP.TO'],NOW)
    assert client.calls==1 and out['TRP.TO']['status']=='UNAVAILABLE'
    assert 'PRIVATE_TOKEN' not in json.dumps(out)


def test_a_second_transient_error_stops():
    client=Client([TimeoutError('x'),TimeoutError('y'),TimeoutError('z')])
    out=Q.fetch_equities(client,['TRP.TO'],NOW)
    assert client.calls==2 and out['TRP.TO']['reason_code']=='TRANSPORT_TIMEOUT'


def test_deadline_is_aggregate_and_never_increases_existing_timeout(monkeypatch):
    clock=[0.0];monkeypatch.setattr(Q.time,'monotonic',lambda:clock[0])
    client=Q.YahooMarketData(timeout=.5)
    seen=[]
    class Opener:
        def open(self,request,timeout):
            seen.append(timeout);clock[0]+=.75
            raise ConnectionError('network')
    client.op=Opener()
    monkeypatch.setattr(client,'get',lambda tickers:client._get('https://host.test'))
    out=Q.fetch_equities(client,['TRP.TO'],NOW,budget_seconds=1)
    assert seen==[.5,.25]
    assert client.timeout==.5 and client._quote_deadline is None
    assert out['TRP.TO']['status']=='UNAVAILABLE'


def test_provider_valueerror_is_not_exposed_as_validation_text():
    class Chain:
        def chain(self,*a): raise ValueError('https://provider/?key=PRIVATE_TOKEN')
    out=Q.event_quote(Chain(),'ZYME',NOW.date(),NOW)
    assert out['reason_code']=='INVALID_PAYLOAD'
    assert out['error_class']=='ValueError'
    assert 'PRIVATE_TOKEN' not in json.dumps(out)


def test_missing_chain_remains_typed():
    class Chain:
        def chain(self,*a): raise Q.MissingOptionChain('provider returned no option chain')
    out=Q.event_quote(Chain(),'ZYME',NOW.date(),NOW)
    assert out['reason_code']=='MISSING_OPTION_CHAIN'


def test_cost_respects_prepared_market_client(monkeypatch):
    import cost
    client=Client()
    monkeypatch.setattr(cost,'market_client',lambda:client)
    rows=cost.assess([{'ticker':'TRP.TO','shares':10,'price':100}],now=NOW)
    assert client.calls==1 and rows[0]['status']=='OK'
    assert rows[0]['cost']['bps']==pytest.approx(2)


def test_exit_transport_outage_is_immutable_and_not_retried(tmp_path):
    import collect_execution
    from report_store import Store
    store=Store(tmp_path)
    entry=Q.validate_equity(raw(),'TRP.TO',NOW)
    report={'session':NOW.date().isoformat(), 'intraday':{
        'legs':[{'ticker':'TRP.TO','side':'LONG','quote':entry,'entry_time':NOW.isoformat()}],
        'benchmark_symbol':'XIU.TO','benchmark':Q.validate_equity(raw('XIU.TO'),'XIU.TO',NOW)}}
    store.publish(report['session'],report)
    exit_now=NOW.replace(hour=15,minute=59)
    fail=Client([ConnectionError('PRIVATE_TOKEN')])
    first=collect_execution.collect(store,'15:59',exit_now,client=fail)
    assert fail.calls==1 and first[0]['status']=='INCOMPLETE'
    assert first[0]['exit_quote']['reason_code']=='TRANSPORT_ERROR'
    assert 'PRIVATE_TOKEN' not in json.dumps(first)
    healthy=Client()
    second=collect_execution.collect(store,'15:59',exit_now,client=healthy)
    assert second==first and healthy.calls==0
