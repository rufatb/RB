#!/usr/bin/env python3
"""COUNCIL LAB ITEM 9, ON HISTORY (day-151): the pre-open desk replayed.

The forward desk (us_preopen.py, day-149) has run since 2026-11-10. This asks
its question of the sessions before it, from 2026-07-02 to 2026-11-09:
on a TSX name that also trades in New York, an overnight release read before
the bell, is anything left between the read and the 09:30 open on the New
York listing? Registered in PREREGISTER_day151_us_preopen_history.md before
any return was computed.

The population is pinned first (`--population`), from the forward desk's own
filter (`us_preopen.releases`) run on a clock cut at each morning's read, over
FMP's press feed for the US symbol (fetched by month, served as it stood at
the read) and the Canadian wire archive. It holds titles, times and the
feed's summary: no price and no return.

    python us_preopen_history.py --population     write data/us_preopen_history_day151.json (FMP, ~1 min)

The run itself (DeepSeek reads, the New York bars, the registered statistics)
is added in its own commit before it runs.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from pathlib import Path
from zoneinfo import ZoneInfo

import us_preopen as U

ET = ZoneInfo('America/New_York')
ROOT = Path(__file__).resolve().parent
POPULATION = ROOT/'data'/'us_preopen_history_day151.json'
FIRST, LAST = dt.date(2026, 7, 2), dt.date(2026, 11, 9)   # the forward desk starts 2026-11-10
READS = (dt.time(8, 15), dt.time(8, 55))                   # the 08:12 Routine; morning_full's second read
REGISTRATION = 'PREREGISTER_day151_us_preopen_history.md'


def sessions(first=FIRST, last=LAST, is_trading=None):
    is_trading = is_trading or U._trading
    day, out = first, []
    while day <= last:
        if is_trading(day):
            out.append(day)
        day += dt.timedelta(days=1)
    return out


def months(first=FIRST, last=LAST):
    """[(from, to)] calendar months covering the window, padded a week back
    for the first session's overnight."""
    start = first - dt.timedelta(days=7)
    out, cur = [], dt.date(start.year, start.month, 1)
    while cur <= last:
        nxt = dt.date(cur.year + (cur.month == 12), cur.month % 12 + 1, 1)
        out.append((max(cur, start), min(nxt - dt.timedelta(days=1), last)))
        cur = nxt
    return out


def press_history(read, twins, first=FIRST, last=LAST):
    """{us symbol: [FMP press rows]} for the window, fetched by month."""
    out = {}
    for twin in twins.values():
        rows, seen = [], set()
        for a, b in months(first, last):
            for r in read('news/press-releases', symbols=twin['us'], limit=100,
                          **{'from': a.isoformat(), 'to': b.isoformat()}) or []:
                if isinstance(r, dict):
                    k = (r.get('publishedDate'), r.get('title'))
                    if k not in seen:
                        seen.add(k)
                        rows.append(r)
        out[twin['us']] = rows
    return out


class AsOf:
    """A read function that serves the press feed as it stood at `end`: the
    newest 15 rows published at or before it, as the live call returns the
    newest 15. Any other endpoint is refused: the population needs no price."""

    def __init__(self, history, end):
        self.history, self.end, self.failures = history, end, {}

    def __call__(self, path, **params):
        if path != 'news/press-releases':
            raise KeyError('ASOF_PRESS_ONLY')
        rows = []
        for r in self.history.get(params.get('symbols'), []):
            try:
                at = dt.datetime.strptime(str(r.get('publishedDate')), '%Y-%m-%d %H:%M:%S').replace(tzinfo=ET)
            except ValueError:
                continue
            if at <= self.end:
                rows.append((at, r))
        rows.sort(key=lambda x: x[0], reverse=True)
        return [r for _, r in rows[:int(params.get('limit') or 15)]]


def population(read=None, twins=None, days=None, archive=None, is_trading=None):
    """Every (session, ticker) the forward desk would have asked about, with
    the read it belongs to. The first read stands; a name first seen at the
    second read keeps its own read time, as on the live desk."""
    import newswire
    read = read or U._reader()
    twins = U.load_twins() if twins is None else twins
    days = sessions(is_trading=is_trading) if days is None else days
    history = press_history(read, twins, days[0], days[-1])
    events, dropped = [], 0
    every = newswire.read(archive)                 # read once: the live call re-reads the archive per name
    original = newswire.read
    newswire.read = lambda root=None, since=None: [r for r in every if not since or
                                                   r['published_at'][:10] >= (since - dt.timedelta(days=1)).isoformat()]
    try:
        return _population(read, twins, days, archive, is_trading, history, events, dropped)
    finally:
        newswire.read = original


def _population(read, twins, days, archive, is_trading, history, events, dropped):
    for day in days:
        start = U.prior_close(dt.datetime.combine(day, dt.time(8), tzinfo=ET), is_trading)
        have = set()
        for t in READS:
            at = dt.datetime.combine(day, t, tzinfo=ET)
            found, out = U.releases(AsOf(history, at), twins, start, at, archive)
            dropped += sum(out.values())
            for ticker, rows in sorted(found.items()):
                if ticker in have:
                    continue
                have.add(ticker)
                events.append({'session': day.isoformat(), 'ticker': ticker, 'us': twins[ticker]['us'],
                               'read_at': at.isoformat(timespec='minutes'), 'releases': rows})
    return {'registration': REGISTRATION, 'window': [days[0].isoformat(), days[-1].isoformat()],
            'sessions': len(days), 'names': len(twins), 'reads': [t.strftime('%H:%M') for t in READS],
            'events': events, 'notices_dropped': dropped,
            'fetch_failures': dict(getattr(read, 'failures', None) or {})}


def summary(pop):
    evs = pop['events']
    by_session = {}
    for e in evs:
        by_session[e['session']] = by_session.get(e['session'], 0) + 1
    src = {}
    for e in evs:
        for r in e['releases']:
            src[r['source']] = src.get(r['source'], 0) + 1
    return {'events': len(evs), 'sessions_with_event': len(by_session), 'sessions': pop['sessions'],
            'second_read': sum(1 for e in evs if e['read_at'][11:16] == READS[1].strftime('%H:%M')),
            'names': len({e['ticker'] for e in evs}), 'releases_by_source': src,
            'notices_dropped': pop['notices_dropped'], 'fetch_failures': pop['fetch_failures']}


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    p.add_argument('--population', action='store_true')
    a = p.parse_args(argv)
    if a.population:
        pop = population()
        POPULATION.write_text(json.dumps(pop, indent=1, ensure_ascii=False) + '\n', encoding='utf-8')
        print(json.dumps(summary(pop), indent=1))
        return 0
    p.print_help()
    return 2


if __name__ == '__main__':
    sys.exit(main())
