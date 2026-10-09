"""THE WEB SCOUT — live web news on the council's positions (day-126).

Registered in PREREGISTER_day126_research.md. Before the council's Round 1,
Perplexity `sonar-pro` (through the OpenRouter key Jev already uses) is asked,
once per position on the table, for dated news from the last 72 hours with
its sources. What it returns is UNVERIFIED web text: it reaches the members as
`web_news` beside their rows, with the citation URLs, and never as a fact.
On the probe (2026-10-05) it missed that morning's Cenovus–Athabasca deal.
"""
from __future__ import annotations

import concurrent.futures as cf
import datetime as dt
import os
import re
from zoneinfo import ZoneInfo

ET = ZoneInfo('America/New_York')
MODEL = 'perplexity/sonar-pro'
URL = 'https://openrouter.ai/api/v1/chat/completions'
MAX_POSITIONS = 16      # day-129: the council table holds up to 16 positions
MAX_FACTS = 3

PROMPT = ('List at most {n} news items about {who} published between {start} and {end} '
          '(Eastern time). One line each, exactly: "YYYY-MM-DD — what happened (source)". '
          'Only items whose publication date you can see in the source. Facts only: no '
          'opinions, price targets or forecasts. If there is nothing, answer NONE.')


def _names(tickers, get):
    out = {}
    for t in tickers:
        try:
            p = (get('profile', symbol=t) or [{}])[0]
            out[t] = str(p.get('companyName') or '')[:60]
        except Exception:          # the ticker alone is still a usable query
            out[t] = ''
    return out


def ask_one(post, ticker, name, now):
    start = (now - dt.timedelta(hours=72)).strftime('%Y-%m-%d %H:%M')
    who = '%s (%s)' % (name, ticker) if name else ticker
    r = post({'model': MODEL, 'messages': [{'role': 'user', 'content': PROMPT.format(
        n=MAX_FACTS, who=who, start=start, end=now.strftime('%Y-%m-%d %H:%M'))}],
              'web_search_options': {'search_context_size': 'low'}, 'max_tokens': 400})
    msg = r['choices'][0]['message']
    text = msg.get('content') or ''
    lines = [re.sub(r'\[\d+\]', '', l).strip(' -*•') for l in text.splitlines()]
    facts = [l[:220] for l in lines if re.match(r'\d{4}-\d{2}-\d{2}', l)][:MAX_FACTS]
    urls = []
    for a in msg.get('annotations') or []:
        u = (a.get('url_citation') or {}).get('url') if isinstance(a, dict) else None
        if u and u not in urls:
            urls.append(u)
    return {'facts': facts, 'sources': urls[:4], 'cost': (r.get('usage') or {}).get('cost')}


def scout(tickers, now, *, post=None, get=None):
    """{ticker: {'facts', 'sources'}} and a list of gaps. Never raises."""
    import research as RS
    import fmp_client as F
    gaps = []
    tickers = list(dict.fromkeys(tickers))[:MAX_POSITIONS]
    if post is None:
        key = os.environ.get('OPENROUTER_API_KEY', '').strip()
        if not key:
            return {}, ['No OpenRouter credential; the web scout did not run.']
        post = RS.http_post(URL, {'Authorization': 'Bearer ' + key}, 60)
    get = get or (lambda path, **p: F.get(path, **p))
    names = _names(tickers, get)
    out = {}

    def one(t):
        try:
            return t, ask_one(post, t, names.get(t, ''), now), None
        except Exception as exc:
            return t, None, (str(exc)[:30] if str(exc).isupper() else type(exc).__name__)
    with cf.ThreadPoolExecutor(min(MAX_POSITIONS, max(1, len(tickers)))) as pool:
        for t, res, err in pool.map(one, tickers):
            if res:
                out[t] = res
            else:
                gaps.append('web scout failed on %s (%s)' % (t, err))
    return out, gaps


def row_text(result):
    """The compact string a council row carries."""
    if not result or not result.get('facts'):
        return 'no dated web news found in the last 72 hours'
    return ' | '.join(result['facts']) + ' [sources: %s]' % ', '.join(result['sources'][:2])
