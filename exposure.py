"""Is a model's pair of picks one bet expressed twice?

Day-113 review, item 4, and the one thing the analyst-prompt library spotted
that the report was genuinely missing. On 2026-09-22 DeepSeek shorted SU.TO and
CNQ.TO and gave the same reason for both — "WTI -5.98% overnight". That is one
oil position written down twice, and nothing on the page said so.

`risk_evidence.concentration` already makes this disclosure for the ENGINE'S
board. It never ran over the model picks. This does, from the committed sector
map (data/tsx_sectors.json) and the models' own stated reasons. It is a
disclosure: it changes no selection, no size and no ranking.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

SECTORS_PATH = Path(__file__).with_name('data') / 'tsx_sectors.json'

# A shared DRIVER is named only when every pick in the group cites it. Words,
# not inference: the model said it, or the line is not printed.
DRIVERS = {
    'crude oil': re.compile(r'\b(wti|crude|oil)\b', re.I),
    'gold': re.compile(r'\bgold\b', re.I),
    'the Canadian dollar': re.compile(r'\b(cad|cadusd|loonie|canadian dollar)\b', re.I),
    'interest rates': re.compile(r'\b(rates?|yields?|bond)\b', re.I),
    'the TSX index': re.compile(r'\btsx\b', re.I),
}


def load_sectors(path=SECTORS_PATH):
    """Same freshness rule as the pool: {} when missing or older than 62 days."""
    from prepare_factor_pool import load_sector_map
    return load_sector_map(path)


def shared_exposure(evidence, sectors):
    """Groups of two or more same-side picks sharing a sector.

    Reads `longs`/`shorts` only — the SELECTED picks. A ranking is not a book,
    and a forced pick is one name per side by construction."""
    groups = []
    for side, key in (('LONG', 'longs'), ('SHORT', 'shorts')):
        by_sector = {}
        for pick in (evidence or {}).get(key) or []:
            ticker = pick.get('ticker')
            label = (sectors.get(ticker) or {}).get('sector') if isinstance(ticker, str) else None
            if label:
                by_sector.setdefault(label, []).append(pick)
        for label, picks in sorted(by_sector.items()):
            if len(picks) < 2:
                continue
            # Strip the market tag every reason opens with ("CA/CAD: ...", as
            # the prompt requires). Left in, it would make 'the Canadian
            # dollar' a "shared driver" of every pair of TSX picks.
            reasons = [re.sub(r'^\s*(CA|US)/(CAD|USD)\s*:\s*', '', str(p.get('reason') or ''))
                       for p in picks]
            driver = next((name for name, pattern in DRIVERS.items()
                           if all(pattern.search(r) for r in reasons)), None)
            groups.append({'side': side, 'sector': label,
                           'tickers': [p['ticker'] for p in picks], 'driver': driver})
    return groups


def line(group, model):
    names = ' and '.join(group['tickers'])
    driver = (f", and every one of them cites {group['driver']}" if group.get('driver') else '')
    return (f"{model}'s {group['side']} picks {names} are all {group['sector']}{driver}. "
            "Treat them as ONE position, not independent ones — they can lose together.")
