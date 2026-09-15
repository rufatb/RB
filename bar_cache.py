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


def inspect_cache(cfg, directory, now=None):
    """Verify persisted bytes, not just a manifest claiming completeness."""
    from quotes import stamp
    import pandas_market_calendars as mcal
    now=now or dt.datetime.now(ZoneInfo('America/New_York'))
    now=stamp(now).astimezone(ZoneInfo('America/New_York'))
    expected_tickers=cfg['scan']['universe']
    out={'status':'NOT READY','session':now.date().isoformat(),
         'verified':0,'expected':len(expected_tickers),'errors':[], 'training_history':[]}
    try:
        root=Path(directory)
        manifest=json.loads((root/'manifest.json').read_text())
        prepared=stamp(manifest['prepared_at']).astimezone(ZoneInfo('America/New_York'))
        if (not manifest.get('complete') or manifest.get('session')!=out['session']
            or prepared.date()!=now.date() or prepared.time()>=dt.time(9,30) or prepared>now
            or manifest.get('source')!=cfg.get('data_sources',{}).get('primary','yahoo_direct')
            or sorted(manifest.get('tickers',[]))!=sorted(expected_tickers)):
            raise ValueError('cache session/source/universe/pre-open identity mismatch')
        prior=mcal.get_calendar('TSX').valid_days(start_date=now.date()-dt.timedelta(days=12),
              end_date=now.date()-dt.timedelta(days=1))[-1].date()
        for ticker in expected_tickers:
            item=json.loads((root/key(ticker)).read_text())
            frame=json.loads(item['frame'])
            index=pd.to_datetime(frame['index'],utc=True).tz_convert(cfg['exchange_tz'])
            if (item['ticker']!=ticker or item['session']!=out['session'] or len(index)==0
                or len(index)!=len(frame['data']) or index.has_duplicates or not index.is_monotonic_increasing
                or index[-1].date()!=prior or any(i.date()>=now.date() for i in index)
                or not {'Open','High','Low','Close','Volume'}.issubset(frame['columns'])):
                raise ValueError('missing/invalid cached history: '+ticker)
            values=pd.DataFrame(frame['data'],columns=frame['columns'])
            import numpy as np
            if (not np.isfinite(values[['Open','High','Low','Close','Volume']].to_numpy(dtype=float)).all()
                or (values[['Open','High','Low','Close']]<=0).any().any() or (values['Volume']<0).any()):
                raise ValueError('invalid cached OHLCV: '+ticker)
            from intraday_history import completed_history
            values.index = index
            validated = completed_history(values, ticker, now, timezone=cfg['exchange_tz'])
            out['training_history'].append(validated['diagnostics'])
            if validated['prior_close'] is None or not validated['rows']:
                raise ValueError('incomplete prior session or no valid training history: '+ticker)
            out['verified']+=1
        out['status']='READY'
    except (OSError,ValueError,KeyError,TypeError,IndexError) as exc:
        out['errors'].append(type(exc).__name__+': '+str(exc)[:160])
    return out


class CacheMiss(Exception):
    """The cache cannot serve this ticker. NOT a data outage — see get_bars."""


def cache_ready(adapter, now, directory=None):
    """Can the cache serve THIS session from THIS source? Cheap, manifest-only.

    Lets the caller decide before fetching whether it is on the fast cached
    path (small same-day responses, a 2s socket timeout is generous) or the
    live path (60 days per name, which needs the full timeout)."""
    directory=directory or os.getenv('RB_INTRADAY_CACHE_DIR')
    if not directory:
        return False, 'no cache directory configured'
    try:
        manifest=json.loads((Path(directory)/'manifest.json').read_text())
    except (OSError, ValueError) as exc:
        return False, 'cache manifest unreadable: '+type(exc).__name__
    if not manifest.get('complete'):
        return False, 'cache marked incomplete'
    if manifest.get('session')!=now.date().isoformat():
        return False, f"cache staged for session {manifest.get('session')}, not {now.date().isoformat()}"
    if manifest.get('source')!=adapter.name:
        return False, f"cache staged from {manifest.get('source')}, not {adapter.name}"
    return True, None


def get_bars(adapter, ticker, now, *, on_fallback=None):
    """Cached history when it is usable for this session; live history when not.

    A CACHE MISS IS NOT A DATA OUTAGE. This used to raise, and because the
    09:46 path passes `require_cache`, an unstaged cache produced a board with
    zero names evaluated and an email reading "SCAN UNAVAILABLE" — on 2026-09-14
    and again on 2026-09-15, with a healthy feed both mornings. The cache
    "changes acquisition only, not baseline features or rules" (CLAUDE.md,
    September 8 recovery), so the live path yields the SAME board; it just
    spends more of the 22s budget. Measured on the live TSX-21: 4.1-4.9s for
    the whole universe against that budget, 0 fetch errors.

    The fallback is never silent. Every fallback is reported through
    `on_fallback(ticker, reason)`, counted by the caller, and printed in the
    report — a stale or corrupt cache is a real operational fault even though
    it must not cost the day's board (house rule 1)."""
    def live(reason):
        if on_fallback is not None:
            on_fallback(ticker, reason)
        return adapter._bars_df(adapter._chart(ticker,'5m','60d'))
    directory=os.getenv('RB_INTRADAY_CACHE_DIR')
    if not directory:
        return live('no cache directory configured')
    ready, why = cache_ready(adapter, now, directory)
    if not ready:
        return live(why)
    try:
        return _cached_bars(adapter, ticker, now, Path(directory))
    except CacheMiss as exc:
        return live(str(exc))


def _cached_bars(adapter, ticker, now, directory):
    """Prior session from disk + today from the feed. Raises CacheMiss only."""
    try:
        manifest=json.loads((directory/'manifest.json').read_text())
        if ticker not in manifest.get('tickers',[]):
            raise CacheMiss('ticker not in the staged universe')
        row=json.loads((directory/key(ticker)).read_text())
    except (OSError, ValueError) as exc:
        raise CacheMiss('cached row unreadable: '+type(exc).__name__) from exc
    if row['ticker']!=ticker or row['session']!=now.date().isoformat():
        raise CacheMiss('history cache identity mismatch')
    encoded=json.loads(row['frame'])
    prior=pd.DataFrame(encoded['data'],columns=encoded['columns'],
                       index=pd.to_datetime(encoded['index'],utc=True).tz_convert(adapter.exchange_tz))
    if any(i.date()>=now.date() for i in prior.index):
        # LEAKAGE. A pre-open cache holding today's bars would put the future
        # into the training window. Discarding it for a live fetch is the safe
        # answer, not a lenient one: completed_history excludes today on the
        # live path. It is reported as a fallback, which is how it gets seen.
        raise CacheMiss('pre-open history contains today/future bars')
    current=adapter._bars_df(adapter._chart(ticker,'5m','1d'))
    current.index=pd.to_datetime(current.index,utc=True).tz_convert(adapter.exchange_tz)
    current=current[[i.date()==now.date() for i in current.index]]
    combined=pd.concat([prior,current]).sort_index()
    if combined.index.has_duplicates:
        raise CacheMiss('duplicate cached/current bars')
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
