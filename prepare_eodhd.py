"""Opt-in, pre-open EODHD entitlement probe and dated reference staging.

No strategy or live-feed switch. Up to 15 API credits, eight HTTP requests,
40 seconds; stops transport/auth/rate-limit failures without retry. A same-day
attempt is reused, including failures, unless the operator supplies --retry.
"""
import argparse
import datetime as dt
import json
import os
from pathlib import Path

import eodhd as E
from build_biotech import write_atomic

TICKERS = ['TRP.TO','ENB.TO','BCE.TO','SLF.TO','XIU.TO']


def prepare(state, *, now=None, client=None, retry=False):
    live_clock = now is None
    now = E.aware(now or dt.datetime.now(E.ET))
    if now.time() >= dt.time(9,30):
        raise E.DataGap('PRE_OPEN_ONLY — do not delay or alter the 09:46 computation')
    state = Path(state)
    status_path = state/'eodhd_status.json'
    if status_path.exists() and not retry:
        prior = json.loads(status_path.read_text())
        checked = E.aware(prior['checked_at'])
        if checked > now:
            raise E.DataGap('FUTURE_PROVIDER_CHECK')
        if checked.date() == now.date():
            return prior
    result = {'schema_version':1, 'checked_at':now.isoformat(), 'status':'PARTIAL',
              'references':{}, 'intraday':{'status':'NOT TESTED'}, 'gaps':[],
              'claim':'No predictive or live-readiness claim; baseline unchanged.'}
    try:
        client = client or E.Client()
        result['account_limits'] = client.limits(now)
        catalog = client.get('exchange-symbol-list/TO')
        instruments = {}
        for ticker in TICKERS:
            try:
                instruments[ticker] = E.identity(catalog,ticker)
            except E.DataGap as exc:
                result['gaps'].append({'ticker':ticker,'reason':str(exc)})
        expected = E.previous_session(now)
        # One native Canadian intraday entitlement check only. A US demo cannot
        # certify this market. A paid upgrade is never inferred from daily data.
        cal = E.schedule(expected,expected).iloc[0]
        try:
            if 'TRP.TO' not in instruments:
                raise E.DataGap('INVALID_IDENTITY — intraday sample not requested')
            rows = client.get('intraday/TRP.TO', cost=5, params={'interval':'5m',
                'from':int(cal['market_open'].timestamp()),
                'to':int(cal['market_close'].timestamp())-1})
            frame = E.five_minute_history(rows,instruments['TRP.TO'],now,expected,expected)
            result['intraday'] = {'status':'SAMPLE VALIDATED — NOT UNIVERSE/HISTORY CERTIFIED',
                'ticker':'TRP.TO','session':expected.isoformat(),'bars':len(frame)}
        except E.DataGap as exc:
            result['intraday'] = {'status':str(exc)}
        for ticker in TICKERS:
            if ticker not in instruments:
                continue
            try:
                rows = client.get('eod/'+ticker, params={'from':expected.isoformat(),'to':expected.isoformat()})
                result['references'][ticker] = E.daily_reference(rows,instruments[ticker],dt.datetime.now(E.ET) if live_clock else now)
            except E.DataGap as exc:
                result['gaps'].append({'ticker':ticker,'reason':str(exc)})
                if '*' in client.blocked:
                    break
        if len(result['references']) == len(TICKERS):
            result['status'] = 'REFERENCES READY — HISTORICAL RESEARCH ONLY'
    except E.DataGap as exc:
        result['gaps'].append({'provider':'EODHD','reason':str(exc)})
    result['requested_symbols'] = TICKERS
    result['api_requests_attempted'] = client.requests if client else 0
    result['api_credits_budgeted'] = client.credits if client else 0
    # Keep failures as dated evidence and never erase the last successful input.
    write_atomic(state/'diagnostics'/f'eodhd-{now.date().isoformat()}.json',result)
    write_atomic(status_path,result)
    if len(result['references']) == len(TICKERS):
        write_atomic(state/'eodhd_reference_closes.json',result['references'])
    return result


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--state-dir',default=os.getenv('RB_STATE_DIR','.rb-state'))
    p.add_argument('--retry',action='store_true',help='Operator-authorized retry only after resolving the blocker')
    a = p.parse_args()
    result = prepare(a.state_dir,retry=a.retry)
    print(json.dumps(result,indent=2,allow_nan=False))
    raise SystemExit(0 if len(result['references']) == len(TICKERS) else 2)
