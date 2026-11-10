#!/usr/bin/env python3
"""THE PRE-OPEN DESK (day-149; council lab item 9) — an overnight release, read
before the bell, on the name's US listing.

The one measured signal on this record: DeepSeek reading an overnight release
takes the side of the gap it causes more often than chance (+0.21% a call,
t = 2.7, day-122), and the TSX open has priced it before any 09:45 entry. A
name listed in New York as well trades from 04:00 ET, so this desk asks the
registered question (PREREGISTER_day149_us_preopen.md): between the moment the
model reads the release and the 09:30 open, is anything left?

The owner, 2026-11-09: "I can trade US shares also yes", then "Build all that
are missing ... schedule them when it makes sense to get into the trade".

* The names: the morning's list, where the same shares (one ISIN) trade on
  NYSE, Nasdaq or NYSE American (`data/us_twins.json`, `--build-twins`).
* The releases: since the prior session's 16:00 ET close, from FMP's press
  feed for the US symbol and the Canadian wire archive. The release pages
  themselves refuse automated readers, so the model reads the title and the
  feed's summary, and the email says so.
* The read: day-122's prompt, byte for byte (`news_desk.SYSTEM_PROMPT`); its
  side is the gap call, as it was measured.
* The price: FMP's last extended-hours trade on the US listing at the read
  (the quote's mid when there is no trade today), with SPY's beside it.
* The measure: side x (US 09:30 open / price at the read - 1), less SPY's move
  over the same span; the 09:45 price and the close are recorded beside it.

A FORWARD SHADOW: never sized, never in the Top 2, never on the desks'
scoreboard, never fed to a prompt. A failure is a code, never the URL.

    python us_preopen.py --build-twins                   refresh data/us_twins.json (FMP, about a minute)
    python us_preopen.py --state-dir .rb-state --build   0 READY, 3 NOTHING/TOO_LATE, 4 ALREADY_SENT, 1 FAILED
    python us_preopen.py --state-dir .rb-state --record --message-id ID
    python us_preopen.py --score                         evening: fills the blanks, never rewrites a cell
    python us_preopen.py --verdict                       the registered decision (NOT_DUE before 40 sessions)
"""
from __future__ import annotations

import argparse
import collections
import concurrent.futures as cf
import csv
import datetime as dt
import io
import json
import math
import os
import random
import re
import statistics as st
import sys
from pathlib import Path
from zoneinfo import ZoneInfo

ET = ZoneInfo('America/New_York')
ROOT = Path(__file__).resolve().parent
TWINS = ROOT/'data'/'us_twins.json'
LEDGER = ROOT/'data'/'us_preopen_calls.csv'
OUT_DIR = 'us_preopen'
SENT = 'sent.json'
US_EXCHANGES = ('NYSE', 'NASDAQ', 'AMEX')
MARKET = 'SPY'
OPEN_AT = dt.time(9, 30)
EARLIEST = dt.time(4, 0)            # US pre-market opens
MAX_RELEASES = 3
SUMMARY_CHARS = 600
PROMPT_VERSION = 'day122-v1+day149-us-preopen'
SUBJECT = 'RB Pre-Open Desk'
LABEL = 'Pre-open research note · not an order'
DECISION, FINAL = 40, 80             # sessions with a material, priced call
BAR, PLACEBO_P, DRAWS, SEED = 3.0, 0.01, 2000, 149
EXIT_COST = 0.05                     # % for the exit at the open; the entry pays its own half-spread
DEFAULT_HALF = 0.10                  # % half-spread for a call whose quote was not recorded
FIELDS = ('session', 'ticker', 'us', 'side', 'confidence', 'material', 'reason', 'releases',
          'first_at', 'last_at', 'title', 'url', 'read_from', 'model', 'prompt_version', 'asked_at',
          'us_prev_close', 'us_px', 'us_px_at', 'us_px_source', 'us_bid', 'us_ask',
          'spy_px', 'spy_px_at',
          'us_open', 'us_0945', 'us_close', 'spy_open', 'spy_0945', 'spy_close',
          'w_open', 'w_0945', 'w_close', 'scored_at')
SCORES = ('us_open', 'us_0945', 'us_close', 'spy_open', 'spy_0945', 'spy_close',
          'w_open', 'w_0945', 'w_close', 'scored_at')


def _now(now=None):
    now = now or dt.datetime.now(ET)
    if now.tzinfo is None:
        raise ValueError('AWARE_CLOCK_REQUIRED')
    return now.astimezone(ET)


def _num(v):
    return float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v) else None


def _trading(day):
    import dashboard
    return dashboard.is_trading_day(day)


def _reader():
    from events_note import Reader
    return Reader()


# ── the US listings ─────────────────────────────────────────────────────────

def build_twins(names, read, today):
    """{ticker: {'us', 'isin', 'name', 'exchange'}} for the names whose own ISIN
    also trades on a US exchange. The ticker is not the company (IAG.TO is iA
    Financial, IAG in New York is IAMGOLD), so the match is the ISIN, never the
    letters. A name FMP cannot answer for is counted, not guessed."""
    def one(t):
        p = read('profile', symbol=t)
        isin = (p[0].get('isin') if isinstance(p, list) and p and isinstance(p[0], dict) else None)
        if not isin:
            return t, None, 'no ISIN'
        for row in read('search-isin', isin=isin) or []:
            sym = str((row or {}).get('symbol') or '')
            if not sym or '.' in sym:
                continue
            q = read('profile', symbol=sym)
            x = q[0] if isinstance(q, list) and q and isinstance(q[0], dict) else {}
            if (x.get('isin') == isin and x.get('exchange') in US_EXCHANGES
                    and x.get('isActivelyTrading') is not False):
                return t, {'us': sym, 'isin': isin, 'exchange': x['exchange'],
                           'name': str(x.get('companyName') or '')[:80]}, None
        return t, None, 'no US listing'
    twins, missing = {}, {}
    with cf.ThreadPoolExecutor(8) as pool:
        for t, twin, why in pool.map(one, sorted(names)):
            if twin:
                twins[t] = twin
            else:
                missing[why] = missing.get(why, 0) + 1
    return {'captured': today.isoformat(), 'names_asked': len(set(names)), 'twins': twins,
            'not_listed': missing, 'rule': 'same ISIN on NYSE, NASDAQ or AMEX (FMP profile and search-isin)'}


def load_twins(path=TWINS):
    try:
        obj = json.loads(Path(path).read_text())
        twins = obj.get('twins')
        return twins if isinstance(twins, dict) else {}
    except (OSError, ValueError, AttributeError):
        return {}


# ── the releases ────────────────────────────────────────────────────────────

def prior_close(now, is_trading=None):
    """16:00 ET on the last trading day before today."""
    is_trading = is_trading or _trading
    day = now.date() - dt.timedelta(days=1)
    for _ in range(10):
        if is_trading(day):
            break
        day -= dt.timedelta(days=1)
    return dt.datetime.combine(day, dt.time(16, 0), tzinfo=ET)


def _key(title):
    return re.sub(r'[^a-z0-9]+', ' ', str(title or '').lower()).strip()


SUFFIXES = frozenset(('the', 'inc', 'incorporated', 'corp', 'corporation', 'ltd', 'limited', 'company',
                      'co', 'plc', 'lp', 'trust'))
GENERIC = frozenset(('canadian', 'royal', 'national', 'first', 'north', 'american', 'bank', 'brookfield',
                     'toronto', 'great', 'united', 'pacific', 'western', 'international'))
# How these issuers title their own releases, where it is not their legal name.
ALIASES = {'TD.TO': ('td bank', 'td announces', 'td reports'), 'RY.TO': ('rbc', 'royal bank'),
           'BMO.TO': ('bmo',), 'BNS.TO': ('scotiabank',), 'CM.TO': ('cibc',),
           'CNR.TO': ('cn ', 'canadian national'), 'CP.TO': ('cpkc', 'canadian pacific kansas'),
           'BN.TO': ('brookfield corporation',), 'ABX.TO': ('barrick',), 'T.TO': ('telus',),
           'BCE.TO': ('bce ', 'bell '), 'RCI-B.TO': ('rogers',), 'GIB-A.TO': ('cgi',),
           'CCO.TO': ('cameco',), 'OTEX.TO': ('opentext', 'open text'), 'K.TO': ('kinross',)}
# A law firm's notice names the company and is not the company's news.
NOTICE = re.compile(r'class action|investor alert|shareholder alert|stock drop|securities fraud|'
                    r'lead plaintiff|law firm|law offices|\bLLP\b|\bBFA Law\b|shareholder rights|'
                    r'recover (?:your )?losses|reminds? (?:investors|shareholders)|'
                    r'encourages? (?:investors|shareholders)|investors? (?:who|with) (?:lost|losses)|'
                    # amendment 1 (2026-11-10): a notice whose title opens with the company's name
                    r'\blaw group\b|\bPLLC\b|your (?:legal )?rights|sued for|securities law violations|'
                    r'investors? (?:are )?(?:encouraged|urged|notified)|\battorneys?\b', re.I)


def _squash(text):
    return re.sub(r'[^a-z0-9]+', '', str(text or '').lower())


def _lead(name):
    """The words a company's own release title starts with: its name without
    'The' and the corporate forms; two words when the first is a common one."""
    words = [w.lower() for w in re.split(r'[^A-Za-z0-9]+', str(name or '')) if w]
    words = [w for w in words if w not in SUFFIXES]
    if not words:
        return ''
    if len(words[0]) >= 5 and words[0] not in GENERIC:
        return words[0]
    return ' '.join(words[:2]) if len(words) >= 2 else ''


def notice(title):
    """A third party's notice about the company (a law firm's class-action
    reminder), which the feeds carry under the company's symbol."""
    return bool(NOTICE.search(str(title or '')))


def _names_issuer(row, ticker, twin):
    """Whether an FMP press row is the issuer's own release: its title starts
    with the company's name (or the name it titles its releases with). The feed
    files a release under every symbol it mentions and under look-alike symbols
    (iA Financial, TSX: IAG, arrives under IAMGOLD's New York symbol IAG), so a
    symbol in the text proves nothing. A miss costs a release; a false match
    would put another company's news on this name."""
    title = str(row.get('title') or '')
    low = ' '.join(re.sub(r'[^a-z0-9]+', ' ', title.lower()).split()) + ' '
    if any(low.startswith(a) for a in ALIASES.get(ticker, ())):
        return True
    lead = _lead(twin.get('name'))
    return bool(lead) and _squash(title).startswith(_squash(lead))


def releases(read, twins, start, end, archive=None):
    """({ticker: [release, oldest first]}, dropped) published in (start, end]:
    FMP's press feed for the US symbol and the Canadian wire archive, one row
    per title. `dropped` counts the third-party notices left out."""
    import newswire
    dropped = collections.Counter()

    def one(item):
        ticker, twin = item
        rows, out = {}, 0
        for r in read('news/press-releases', symbols=twin['us'], limit=15) or []:
            if not isinstance(r, dict):
                continue
            try:
                at = dt.datetime.strptime(str(r.get('publishedDate')), '%Y-%m-%d %H:%M:%S').replace(tzinfo=ET)
            except ValueError:
                continue
            if not (start < at <= end and r.get('title')):
                continue
            if notice(r['title']):
                out += 1
            elif _names_issuer(r, ticker, twin):
                rows[_key(r['title'])] = {'published_at': at.isoformat(), 'title': str(r['title'])[:200],
                                          'url': str(r.get('url') or 'fmp:' + _key(r['title']))[:300],
                                          'text': ' '.join(str(r.get('text') or '').split())[:SUMMARY_CHARS],
                                          'source': 'FMP press feed'}
        try:
            for r in newswire.releases_for(ticker, start, end, archive):
                at = dt.datetime.fromisoformat(r['published_at']).astimezone(ET)
                if not start < at <= end:
                    continue
                if notice(r['title']):
                    out += 1
                    continue
                rows.setdefault(_key(r['title']), {
                    'published_at': at.isoformat(), 'title': str(r['title'])[:200],
                    'url': str(r.get('url') or 'wire:' + _key(r['title']))[:300],
                    'text': ' '.join(str(r.get('summary') or '').split())[:SUMMARY_CHARS],
                    'source': 'newswire.ca list'})
        except Exception:                      # the archive is a second source; the feed stands alone
            pass
        return ticker, sorted(rows.values(), key=lambda r: r['published_at'])[-MAX_RELEASES:], out
    found = {}
    if twins:
        with cf.ThreadPoolExecutor(8) as pool:
            for ticker, rows, out in pool.map(one, sorted(twins.items())):
                if rows:
                    found[ticker] = rows
                if out:
                    dropped['third-party notice'] += out
    return found, dict(dropped)


# ── the price at the read ───────────────────────────────────────────────────

QUOTE_FRESH = dt.timedelta(minutes=10)
TRADE_FRESH = dt.timedelta(minutes=30)
QUOTE_MAX_SPREAD = 0.01              # a wider book has no usable mid
CLOCK_SLACK = dt.timedelta(minutes=2)


def last_close(read, symbol, today):
    """The last regular close before `today`, from daily bars: (close, date)."""
    rows = read('historical-price-eod/full', symbol=symbol,
                **{'from': (today - dt.timedelta(days=12)).isoformat(),
                   'to': (today - dt.timedelta(days=1)).isoformat()})
    best = None
    for r in rows if isinstance(rows, list) else []:
        d, c = str((r or {}).get('date') or '')[:10], _num((r or {}).get('close'))
        if c and d < today.isoformat() and (best is None or d > best[1]):
            best = (c, d)
    return best or (None, None)


def snapshot(read, symbol, now):
    """The US listing's price at the read, in the registered order: the mid of
    a fresh, tight quote (stamped in the last 10 minutes, no wider than 1%);
    else the last extended-hours trade of the last 30 minutes, or failing that
    feed the close of the last one-minute bar of the last 30 minutes; else nothing.
    Never a price from before today's pre-market, and never a stale trade:
    one made before the release would hand the desk the whole reaction."""
    floor = dt.datetime.combine(now.date(), EARLIEST, tzinfo=ET)
    out = {'px': None, 'at': None, 'source': None, 'bid': None, 'ask': None}
    out['prev_close'], out['prev_date'] = last_close(read, symbol, now.date())

    def stamped(row):
        ts = _num((row or {}).get('timestamp'))
        at = dt.datetime.fromtimestamp(ts / 1000, ET) if ts else None
        return at if at and floor <= at <= now + CLOCK_SLACK else None
    a = read('aftermarket-quote', symbol=symbol)
    a = a[0] if isinstance(a, list) and a and isinstance(a[0], dict) else {}
    bid, ask, quote_at = _num(a.get('bidPrice')), _num(a.get('askPrice')), stamped(a)
    if bid and ask and 0 < bid <= ask and quote_at:
        out['bid'], out['ask'] = bid, ask
        mid = (bid + ask) / 2
        if (ask - bid) / mid <= QUOTE_MAX_SPREAD and now - quote_at <= QUOTE_FRESH:
            out.update(px=round(mid, 4), at=quote_at.isoformat(timespec='seconds'), source='quote mid')
            return out
    t = read('aftermarket-trade', symbol=symbol)
    t = t[0] if isinstance(t, list) and t and isinstance(t[0], dict) else {}
    px, trade_at = _num(t.get('price')), stamped(t)
    if px and px > 0 and trade_at and now - trade_at <= TRADE_FRESH:
        out.update(px=px, at=trade_at.isoformat(timespec='seconds'), source='last trade')
        return out
    # The same fact from a second endpoint: the last extended-hours one-minute bar.
    day = now.date().isoformat()
    last = None
    for r in read('historical-chart/1min', symbol=symbol, **{'from': day, 'to': day, 'extended': 'true'}) or []:
        try:
            end = (dt.datetime.strptime(str((r or {}).get('date')), '%Y-%m-%d %H:%M:%S').replace(tzinfo=ET)
                   + dt.timedelta(minutes=1))
        except ValueError:
            continue
        c = _num(r.get('close'))
        if c and c > 0 and floor <= end <= now + CLOCK_SLACK and (last is None or end > last[0]):
            last = (end, c)
    if last and now - last[0] <= TRADE_FRESH:
        out.update(px=last[1], at=last[0].isoformat(timespec='seconds'), source='last bar')
    return out


# ── the ledger ──────────────────────────────────────────────────────────────

def read_ledger(path=LEDGER):
    path = Path(path)
    if not path.is_file():
        return []
    return list(csv.DictReader(io.StringIO(path.read_text())))


def _cell(v):
    if v is None:
        return ''
    if isinstance(v, bool):
        return 'true' if v else 'false'
    if isinstance(v, float):
        return ('%.4f' % v).rstrip('0').rstrip('.')
    return str(v)


def _typed(row):
    """A ledger row with its numbers and flags back as values."""
    out = dict(row)
    for k in ('confidence', 'us_prev_close', 'us_px', 'us_bid', 'us_ask', 'spy_px'):
        out[k] = _float(row.get(k))
    out['material'] = row.get('material') == 'true'
    out['releases'] = int(row['releases']) if str(row.get('releases') or '').isdigit() else 0
    for k in ('us_px_at', 'us_px_source', 'spy_px_at'):
        out[k] = row.get(k) or None
    return out


def write_ledger(rows, path=LEDGER):
    """Atomic: a kill mid-write leaves the old ledger whole."""
    out = io.StringIO()
    w = csv.DictWriter(out, fieldnames=FIELDS, extrasaction='ignore', lineterminator='\n')
    w.writeheader()
    for r in rows:
        w.writerow({k: _cell(r.get(k)) for k in FIELDS})
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = Path(str(path) + '.tmp')
    with open(tmp, 'w') as f:
        f.write(out.getvalue())
        f.flush()
        os.fsync(f.fileno())
    tmp.replace(path)


# ── the morning read ────────────────────────────────────────────────────────

def record_line(path=LEDGER):
    """The running record on the registered measure, one sentence."""
    rows = [r for r in read_ledger(path) if r.get('material') == 'true' and r.get('w_open') not in (None, '')
            and not notice(r.get('title'))]
    if not rows:
        return 'Record so far: no scored call yet. This desk started on 2026-11-10.'
    w = [float(r['w_open']) for r in rows]
    return ('Record so far, from the read to the 09:30 open against SPY: %d of %d right, %+.2f%% a call '
            'over %d session(s). Decision at %d sessions with a call (PREREGISTER_day149_us_preopen.md).'
            % (sum(x > 0 for x in w), len(w), st.mean(w), len({r['session'] for r in rows}), DECISION))


def _move(px, prev):
    return None if not (px and prev) else 100 * (px / prev - 1)


def compose(session, rows, now, record, problems, dropped=None):
    shown = [r for r in rows if r['material']]
    routine = [r for r in rows if not r['material']]
    lines = ['# %s — %s' % (SUBJECT, session),
             'Read at %s ET, before the 09:30 open. A test in shadow with no record yet: never sized.'
             % _now(now).strftime('%H:%M'),
             '', '## Overnight releases on names that also trade in New York']
    if shown:
        lines += ['', '| Call | New York listing | Price at the read | Since the US close | Release | Why (DeepSeek) |',
                  '|---|---|---|---:|---|---|']
        for r in shown:
            mv = _move(r['us_px'], r['us_prev_close'])
            px = ('%.2f at %s (%s)' % (r['us_px'], str(r['us_px_at'])[11:16], r['us_px_source'])
                  if r['us_px'] else 'no fresh pre-market price')
            at = dt.datetime.fromisoformat(r.get('last_at') or r['first_at']).astimezone(ET).strftime('%a %H:%M')
            lines.append('| %s %s (%.2f) | %s | %s | %s | %s %s | %s |' % (
                r['side'], r['ticker'], r['confidence'], r['us'], px,
                '%+.1f%%' % mv if mv is not None else '—', at,
                str(r['title']).replace('|', '/')[:110], str(r['reason']).replace('|', '/')[:220]))
    else:
        lines.append('No release the model marked as material.')
    if routine:
        lines.append('Routine, no call shown: ' + ' · '.join(
            '%s (%s)' % (r['ticker'], str(r['title'])[:60]) for r in routine) + '.')
    lines += ['', '## If you act on one',
              '- The entry is the New York listing now, before the bell. The registered exit is the '
              '09:30 open.',
              '- From the open onward the record says nothing is left: asked the same way, the read '
              'made +0.09% from the open to the close, which is noise.',
              '- "Since the US close" is how much of the move the price already has. A call with no '
              'fresh pre-market price is not scored.',
              '', '## How to read it',
              'The call is DeepSeek\'s side on the release, read from its title and the wire\'s summary '
              '(the release pages refuse automated readers). On 420 past releases this read matched the '
              'overnight gap more often than chance (+0.21% a call), and the 09:30 open had priced it. '
              'The New York listing trades before 09:30, so this desk tests whether anything is left '
              'between the read and the open.',
              record]
    notes = ['%s ×%d' % kv for kv in sorted((problems or {}).items())]
    if notes:
        lines.append('Not read: ' + ', '.join(notes) + '.')
    if dropped:
        lines.append('Left out: ' + ', '.join('%d %s(s)' % (n, k) for k, n in sorted(dropped.items())) + '.')
    lines += ['', '---', 'Research only, not an order. No call here is a prediction; this desk has no '
                         'record yet, and every other source on the record is still a coin flip.']
    body = '\n'.join(lines)
    head = (' · '.join('%s %s (%s)' % (r['side'], r['ticker'], r['us']) for r in shown[:4])
            or 'no material release')
    subject = '%s — %s — %s' % (SUBJECT, session, head)
    import email_render
    hero = ('<tr><td style="padding:22px 26px;background:#f4f7f9;border-bottom:1px solid #dde4ea">'
            '<div style="font:600 15px/1.45 Arial,sans-serif;color:#17212b">%s</div></td></tr>'
            % email_render.full.escape(head + ' — New York listings, before the open'))
    return subject, body, email_render.html_from_text(body, hero=hero, label=LABEL)


def sent_today(root, now):
    try:
        obj = json.loads((Path(root)/OUT_DIR/SENT).read_text())
    except (OSError, ValueError):
        return False
    return isinstance(obj, dict) and obj.get('session') == now.date().isoformat()


def build(state_dir, now=None, *, read=None, client=None, twins=None, archive=None, path=LEDGER,
          is_trading=None, clock=None):
    """(status, info). Every answered call is appended to the ledger; READY
    also writes the email's three files, and needs at least one release the
    model marked as material. A call answered at or after 09:30 is not
    recorded. On a rerun the first recorded answer stands and is not re-asked."""
    import news_desk
    clock = clock or ((lambda: now) if now else (lambda: dt.datetime.now(ET)))
    now = _now(now or clock())
    root, session = Path(state_dir), now.date()
    is_trading = is_trading or _trading
    if not is_trading(session):
        return 'NOTHING', {'reason': 'not a trading day'}
    if now.time() >= OPEN_AT:
        return 'TOO_LATE', {'reason': 'PREOPEN_ONLY: asked at or after 09:30'}
    if sent_today(root, now):
        return 'ALREADY_SENT', {}
    twins = load_twins() if twins is None else twins
    if not twins:
        return 'FAILED', {'reason': 'NO_US_LISTINGS_MAP'}
    read = read or _reader()
    found, dropped = releases(read, twins, prior_close(now, is_trading), now, archive)
    if not found:
        fails = dict(getattr(read, 'failures', None) or {})
        if fails and sum(fails.values()) >= len(twins):
            return 'FAILED', {'reason': ', '.join(sorted(fails))}
        return 'NOTHING', {'reason': 'no overnight release on a name with a US listing',
                           'names_checked': len(twins), 'dropped': dropped}
    ledger = read_ledger(path)
    kept = [_typed(r) for r in ledger if r.get('session') == session.isoformat()]
    have = {r['ticker'] for r in kept}                 # the first answer stands: never asked twice
    evs = [{'id': '%s:%s' % (session.isoformat(), t), 'ticker': t, 'releases': rows}
           for t, rows in sorted(found.items()) if t not in have]
    added, problems, answered = [], {}, now
    if evs:
        if client is None:
            import prepare_deepseek
            prepare_deepseek.load_private_key(state_dir)
        texts = {r['url']: r['text'] for e in evs for r in e['releases']}
        calls, problems, model = news_desk.answer(evs, 'full', texts, client=client)
        answered = _now(clock())
        if answered.time() >= OPEN_AT:
            return 'TOO_LATE', {'reason': 'ANSWERED_AFTER_THE_OPEN at %s' % answered.strftime('%H:%M:%S')}
        spy = snapshot(read, MARKET, answered)
        for e in evs:
            c = calls.get(e['id'])
            if not c:
                continue
            twin = twins[e['ticker']]
            s = snapshot(read, twin['us'], answered)
            last_at = e['releases'][-1]['published_at']
            if s['at'] and s['at'] < last_at:           # a price from before the release is not an entry
                s.update(px=None, source='older than the release')
            added.append({'session': session.isoformat(), 'ticker': e['ticker'], 'us': twin['us'], **c,
                          'releases': len(e['releases']), 'first_at': e['releases'][0]['published_at'],
                          'last_at': last_at,
                          'title': e['releases'][-1]['title'], 'url': e['releases'][-1]['url'],
                          'read_from': 'title and summary', 'model': model or news_desk.MODEL,
                          'prompt_version': PROMPT_VERSION,
                          'asked_at': answered.isoformat(timespec='seconds'),
                          'us_prev_close': s['prev_close'], 'us_px': s['px'], 'us_px_at': s['at'],
                          'us_px_source': s['source'], 'us_bid': s['bid'], 'us_ask': s['ask'],
                          'spy_px': spy['px'], 'spy_px_at': spy['at']})
        if added:
            write_ledger(ledger + added, path)
    rows = kept + added
    if not rows:
        return 'FAILED', {'reason': 'no call answered: ' + (', '.join(sorted(problems)) or 'NO_CALLS')}
    rows = [r for r in rows if not notice(r.get('title'))]     # amendment 1: recorded, never shown
    rows.sort(key=lambda r: (-r['confidence'], r['ticker']))
    if not any(r['material'] for r in rows):            # recorded above; nothing worth an email
        return 'NOTHING', {'reason': 'no release the model marked as material', 'calls': len(rows),
                           'recorded': len(added), 'dropped': dropped}
    fails = {**dict(getattr(read, 'failures', None) or {}), **problems}
    subject, body, html = compose(session.isoformat(), rows, answered, record_line(path), fails, dropped)
    out = root/OUT_DIR
    out.mkdir(parents=True, exist_ok=True)
    (out/'subject.txt').write_text(subject, encoding='utf-8')
    (out/'report.txt').write_text(body, encoding='utf-8')
    (out/'report.html').write_text(html, encoding='utf-8')
    (out/'calls.json').write_text(json.dumps({'session': session.isoformat(), 'calls': rows}, indent=1,
                                             ensure_ascii=False, default=str), encoding='utf-8')
    return 'READY', {'subject': subject, 'subject_path': str(out/'subject.txt'),
                     'text_path': str(out/'report.txt'), 'html_path': str(out/'report.html'),
                     'calls': len(rows), 'material': sum(1 for r in rows if r['material']),
                     'recorded': len(added)}


def record(state_dir, message_id, now=None):
    from build_biotech import write_atomic
    now = _now(now)
    (Path(state_dir)/OUT_DIR).mkdir(parents=True, exist_ok=True)
    write_atomic(Path(state_dir)/OUT_DIR/SENT, {'session': now.date().isoformat(),
                                                'message_id': message_id, 'sent_at': now.isoformat()})


# ── the evening score ───────────────────────────────────────────────────────

def session_marks(rows5, session):
    """{'open', 'p0945', 'close'} from FMP 5-minute bars of one regular session."""
    by = {}
    for b in rows5 or []:
        d, _, t = str(b.get('date') or '').partition(' ')
        if d == session:
            by[t] = b
    o, e, x = by.get('09:30:00'), by.get('09:40:00'), by.get('15:55:00')
    return {'open': _num((o or {}).get('open')), 'p0945': _num((e or {}).get('close')),
            'close': _num((x or {}).get('close'))}


def outcomes(side, px, spy_px, us, spy):
    """Side-signed % from the price at the read, less SPY's move over the same span."""
    s = 1 if side == 'LONG' else -1
    out = {}
    for key, name in (('open', 'w_open'), ('p0945', 'w_0945'), ('close', 'w_close')):
        if px and spy_px and us.get(key) and spy.get(key):
            out[name] = round(s * 100 * ((us[key] / px - 1) - (spy[key] / spy_px - 1)), 4)
    return out


def score(path=LEDGER, *, now=None, read=None):
    """Fill the blanks for sessions that have closed. A filled cell is never
    rewritten; a row without a price at the read stays unscored, and is counted."""
    now = _now(now)
    rows = read_ledger(path)
    due = [r for r in rows if not r.get('scored_at') and (
        r['session'] < now.date().isoformat() or (r['session'] == now.date().isoformat()
                                                  and now.time() >= dt.time(16, 5)))]
    if not due:
        return {'scored': 0, 'unpriced': 0, 'waiting': 0}
    read = read or _reader()
    bars = {}

    def marks(symbol, session):
        if (symbol, session) not in bars:
            bars[(symbol, session)] = session_marks(
                read('historical-chart/5min', symbol=symbol, **{'from': session, 'to': session}), session)
        return bars[(symbol, session)]
    scored = unpriced = waiting = 0
    for r in due:
        px, spy_px = _float(r.get('us_px')), _float(r.get('spy_px'))
        if not px or not spy_px:
            unpriced += 1
            r['scored_at'] = now.isoformat(timespec='seconds')        # nothing to score, and it says so
            continue
        us, spy = marks(r['us'], r['session']), marks(MARKET, r['session'])
        if not (us['open'] and spy['open'] and us['close'] and spy['close']):
            waiting += 1
            continue
        for k, v in (('us_open', us['open']), ('us_0945', us['p0945']), ('us_close', us['close']),
                     ('spy_open', spy['open']), ('spy_0945', spy['p0945']), ('spy_close', spy['close'])):
            if r.get(k) in (None, '') and v is not None:
                r[k] = v
        for k, v in outcomes(r['side'], px, spy_px, us, spy).items():
            if r.get(k) in (None, ''):
                r[k] = v
        r['scored_at'] = now.isoformat(timespec='seconds')
        scored += 1
    if scored or unpriced:
        write_ledger(rows, path)
    return {'scored': scored, 'unpriced': unpriced, 'waiting': waiting}


def _float(v):
    try:
        x = float(v)
        return x if math.isfinite(x) else None
    except (TypeError, ValueError):
        return None


# ── the registered decision ─────────────────────────────────────────────────

def _sessions(path=LEDGER):
    """{session: [(w_open, half-spread %)]} for material calls with a price."""
    out = {}
    for r in read_ledger(path):
        w = _float(r.get('w_open'))
        if r.get('material') != 'true' or w is None or notice(r.get('title')):
            continue
        bid, ask, px = _float(r.get('us_bid')), _float(r.get('us_ask')), _float(r.get('us_px'))
        half = 100 * (ask - bid) / 2 / px if (bid and ask and px) else DEFAULT_HALF
        out.setdefault(r['session'], []).append((w, half))
    return dict(sorted(out.items()))


def _t(means):
    if len(means) < 3:
        return None
    sd = st.stdev(means)
    return st.mean(means) / (sd / math.sqrt(len(means))) if sd > 0 else None


def verdict(path=LEDGER, *, draws=DRAWS, seed=SEED):
    """PASS / FAIL / CONTINUE / UNDERPOWERED at 40 sessions with a call, one
    final look at 80; NOT_DUE before. The statistic is the mean of the session
    means of w_open; the cost is each call's own half-spread plus EXIT_COST."""
    by = _sessions(path)
    n = len(by)
    if n < DECISION:
        return {'verdict': 'NOT_DUE', 'sessions': n, 'due_at': DECISION}
    take = FINAL if n >= FINAL else DECISION
    days = list(by.items())[:take]
    means = [st.mean(w for w, _ in v) for _, v in days]
    cost = st.mean(h for _, v in days for _, h in v) + EXIT_COST
    mean, t = st.mean(means), _t(means)
    rng = random.Random(seed)
    hits = sum(st.mean(m * rng.choice((1, -1)) for m in means) >= mean for _ in range(draws))
    p = (hits + 1) / (draws + 1)
    h1, h2 = st.mean(means[:len(means) // 2]), st.mean(means[len(means) // 2:])
    centred = [m - mean + 0.5 for m in means]
    out = {'sessions': len(means), 'calls': sum(len(v) for _, v in days), 'mean_pct': round(mean, 4),
           't': None if t is None else round(t, 2), 'placebo_p': round(p, 4),
           'halves_pct': [round(h1, 4), round(h2, 4)], 'cost_pct': round(cost, 4),
           'net_pct': round(mean - cost, 4), 'control_t_planted_0_5': (None if _t(centred) is None
                                                                       else round(_t(centred), 2))}
    if t is not None and t >= BAR and p < PLACEBO_P and h1 > 0 and h2 > 0 and mean > cost:
        out['verdict'] = 'PASS'
    elif mean <= 0:
        out['verdict'] = 'FAIL'
    elif take == FINAL:
        out['verdict'] = 'UNDERPOWERED' if (out['control_t_planted_0_5'] or 0) < BAR else 'FAIL'
    else:
        out['verdict'] = 'CONTINUE'
    return out


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    p.add_argument('--state-dir', default='.rb-state')
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument('--build', action='store_true')
    g.add_argument('--record', action='store_true')
    g.add_argument('--score', action='store_true')
    g.add_argument('--verdict', action='store_true')
    g.add_argument('--build-twins', action='store_true')
    p.add_argument('--message-id')
    a = p.parse_args(argv)
    if a.record:
        if not a.message_id:
            p.error('--record needs --message-id')
        record(a.state_dir, a.message_id)
        print(json.dumps({'status': 'RECORDED', 'message_id': a.message_id}))
        return 0
    if a.score:
        print(json.dumps(score()))
        return 0
    if a.verdict:
        print(json.dumps(verdict()))
        return 0
    if a.build_twins:
        from events_note import universe
        read = _reader()
        obj = build_twins(set(universe(a.state_dir)), read, dt.datetime.now(ET).date())
        if len(obj['twins']) < 20:                 # a broken feed must not replace a good map
            print(json.dumps({'status': 'REFUSED', 'twins': len(obj['twins']), 'failures': read.failures}))
            return 1
        TWINS.write_text(json.dumps(obj, indent=1, sort_keys=True) + '\n')
        print(json.dumps({'status': 'WRITTEN', 'twins': len(obj['twins']), 'not_listed': obj['not_listed'],
                          'failures': read.failures}))
        return 0
    try:
        status, info = build(a.state_dir)
    except Exception as exc:              # the desk must never cost the morning
        print(json.dumps({'status': 'FAILED', 'reason': type(exc).__name__}))
        return 1
    print(json.dumps({'status': status, **info}))
    return {'READY': 0, 'NOTHING': 3, 'TOO_LATE': 3, 'ALREADY_SENT': 4}.get(status, 1)


if __name__ == '__main__':
    sys.exit(main())
