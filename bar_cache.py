"""Same-session pre-open 60-day history cache; baseline calculations unchanged."""
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
from zoneinfo import ZoneInfo
import pandas as pd
from build_biotech import write_atomic


def key(ticker):
    return hashlib.sha256(ticker.encode()).hexdigest()+'.json'


def get_bars(adapter, ticker, now):
    directory=os.getenv('RB_INTRADAY_CACHE_DIR')
    if not directory:
        return adapter._bars_df(adapter._chart(ticker,'5m','60d'))
    directory=Path(directory)
    manifest=json.loads((directory/'manifest.json').read_text())
    if (not manifest.get('complete') or manifest.get('session')!=now.date().isoformat()
        or manifest.get('source')!=adapter.name or ticker not in manifest.get('tickers',[])):
        raise ValueError('intraday history cache not prepared for this session/source/universe')
    row=json.loads((directory/key(ticker)).read_text())
    if row['ticker']!=ticker or row['session']!=now.date().isoformat():
        raise ValueError('history cache identity mismatch')
    encoded=json.loads(row['frame'])
    prior=pd.DataFrame(encoded['data'],columns=encoded['columns'],
                       index=pd.to_datetime(encoded['index'],utc=True).tz_convert(adapter.exchange_tz))
    if any(i.date()>=now.date() for i in prior.index):
        raise ValueError('pre-open history contains today/future bars')
    current=adapter._bars_df(adapter._chart(ticker,'5m','1d'))
    current.index=pd.to_datetime(current.index,utc=True).tz_convert(adapter.exchange_tz)
    current=current[[i.date()==now.date() for i in current.index]]
    combined=pd.concat([prior,current]).sort_index()
    if combined.index.has_duplicates: raise ValueError('duplicate cached/current bars')
    return combined


def prepare(cfg,directory,now=None):
    """Run pre-open, never fabricate a cache after the entry window.

    Any missing symbol blocks cache readiness; no partial-universe ranking.
    Source bytes are cached as bars, not trained-model outcomes or new signals.
    """
    from adapters import build_adapter
    from bounded import acquire
    import pandas_market_calendars as mcal
    now=now or dt.datetime.now(ZoneInfo(cfg['exchange_tz']))
    if now.time()>=dt.time(9,30): raise ValueError('history preparation is pre-open only')
    directory=Path(directory);directory.mkdir(parents=True,exist_ok=True)
    source=cfg.get('data_sources',{}).get('primary','yahoo_direct')
    tickers=cfg['scan']['universe']
    adapter=build_adapter(source,exchange_tz=cfg['exchange_tz'])
    expected=mcal.get_calendar('TSX').valid_days(start_date=now.date()-dt.timedelta(days=12),
                end_date=now.date()-dt.timedelta(days=1))[-1].date()
    manifest={'session':now.date().isoformat(),'source':source,'tickers':tickers,
              'complete':False,'errors':[], 'prepared_at':now.isoformat()}
    write_atomic(directory/'manifest.json',manifest)
    def fetch(t):
        bars=adapter._bars_df(adapter._chart(t,'5m','60d'))
        bars=bars[[i.date()<now.date() for i in bars.index]]
        if bars.empty or bars.index[-1].date()!=expected or bars.index.has_duplicates:
            raise ValueError('missing or duplicate prior-session history')
        encoded={'columns':list(bars.columns),'index':[i.isoformat() for i in bars.index],
                 'data':bars.to_numpy().tolist()}
        return {'ticker':t,'session':now.date().isoformat(),
                'frame':json.dumps(encoded,allow_nan=False)}
    # Four concurrent requests; per-symbol timeout kills 2-host failover promptly.
    for offset in range(0,len(tickers),4):
        results=acquire({t:(lambda t=t:fetch(t),25) for t in tickers[offset:offset+4]})
        for t,r in results.items():
            if r['status']=='OK': write_atomic(directory/key(t),r['value'])
            else: manifest['errors'].append(t+': '+r['error'])
        if manifest['errors']:
            break  # provider failure is not a reason to hammer the rest of the universe
    manifest['complete']=not manifest['errors']
    write_atomic(directory/'manifest.json',manifest)
    return manifest


if __name__=='__main__':
    import argparse
    from dashboard import load_config
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--directory',required=True);p.add_argument('--config',default='config.yaml')
    a=p.parse_args();result=prepare(load_config(a.config),a.directory)
    print(json.dumps(result));raise SystemExit(0 if result['complete'] else 2)
