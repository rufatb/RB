"""Deterministic headline hygiene, not semantic event or issuer verification.

Ticker-channel membership does not establish materiality, novelty or the
issuer's role. These deliberately conservative labels expose what a headline
does not establish. They perform no network requests or model inference.
"""
from __future__ import annotations

import re
import unicodedata
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit


_TRACKING_KEYS = frozenset(('guccounter', 'guce_referrer', 'guce_referrer_sig',
                          'ncid', 'soc_src', 'soc_trk', 'gclid', 'fbclid'))
_COMMENTARY = re.compile(
    r'\b(?:best|top)\s+(?:\d+\s+)?(?:canadian\s+)?(?:dividend\s+)?stocks?\b|'
    r'\bstocks?\s+(?:to\s+)?(?:buy|own|hold)\b|'
    r'\b(?:buy|own|hold)\s+(?:and\s+hold\s+)?(?:for\s+)?decades?\b|'
    r'\b(?:should\s+you\s+buy|dividend\s+stocks?|your\s+portfolio)\b', re.I)
_MULTI_YEAR = re.compile(
    r'\b(?:[2-9]|[1-9][0-9]+|two|three|four|five|six|seven|eight|nine|ten)'
    r'[\s\-]+year\b|\b(?:decades?|long[\s\-]+term)\b', re.I)


def canonical_url(value):
    """Remove only known tracking parameters; preserve article identity fields."""
    from factor_inputs import _url
    value = _url(value)
    parts = urlsplit(value)
    query = [(key, val) for key, val in parse_qsl(parts.query, keep_blank_values=True)
             if not key.lower().startswith('utm_') and key.lower() not in _TRACKING_KEYS]
    netloc = parts.hostname.lower()
    # _url already excludes non-HTTPS ports and credentials.
    return urlunsplit(('https', netloc, parts.path or '/', urlencode(sorted(query)), ''))


def normalized_title(value):
    """Exact normalized title equality, not an inferred same-event classifier."""
    return ' '.join(re.findall(r'\w+', unicodedata.normalize('NFKC', value).casefold()))


def wire_release(title, source_url, ticker=None, archive=None):
    """The archived wire row this headline IS, or None.

    Recomputed from `data/newswire/` (collected by `newswire.py` from the wire
    itself), never from a staged claim: the URL must be an archived release AND
    the title must be that release's title. Anything else is not a release."""
    try:
        import newswire
        row = newswire.index(archive).get(canonical_url(source_url))
    except (OSError, ValueError, KeyError, TypeError):
        return None
    if not row or normalized_title(row.get('title') or '') != normalized_title(title):
        return None
    return row


def classify_headline(title, source_url, ticker=None, archive=None):
    """Labels are derived from explicit title words, never claimed as facts —
    except an ISSUER_RELEASE, which is derived from the wire archive (day-118):
    its disclosure time is the wire's own, and the issuer is VERIFIED only when
    the release's lead names `ticker`."""
    wire = wire_release(title, source_url, ticker, archive)
    if wire:
        return {
            'classification': 'ISSUER_RELEASE',
            'issuer_role': 'VERIFIED' if ticker and ticker in (wire.get('tickers') or []) else 'UNVERIFIED',
            'novelty': 'UNVERIFIED',
            'first_disclosed_at': wire['published_at'], 'updated_at': None,
            'impact_horizon': 'MULTI_YEAR_TITLE' if _MULTI_YEAR.search(title) else 'UNSPECIFIED',
            'primary_source_verified': True,
            'classification_basis': 'archived newswire.ca release; symbol named in its lead',
            'canonical_url': canonical_url(source_url),
        }
    commentary = bool(_COMMENTARY.search(title))
    return {
        'classification': 'COMMENTARY' if commentary else 'UNCLASSIFIED',
        'issuer_role': 'UNVERIFIED', 'novelty': 'UNVERIFIED',
        'first_disclosed_at': None, 'updated_at': None,
        'impact_horizon': 'MULTI_YEAR_TITLE' if _MULTI_YEAR.search(title) else 'UNSPECIFIED',
        'primary_source_verified': False,
        'classification_basis': 'explicit title pattern' if commentary else 'insufficient structured evidence',
        'canonical_url': canonical_url(source_url),
    }


def _rank(row):
    """Wire releases first, commentary last; provider order otherwise."""
    c = row['evidence_metadata']['classification']
    return 0 if c == 'ISSUER_RELEASE' else 2 if c == 'COMMENTARY' else 1


def prepare_headlines(items, maximum, ticker=None, archive=None):
    """Deduplicate validated rows before capping; expose every removed row.

    Retain provider order within the unclassified/commentary groups. An
    unclassified headline is not a verified factual catalyst. Repeated URLs and
    identical normalized titles are counted separately from a size truncation.
    """
    unique, urls, titles, reasons = [], set(), set(), {}
    for item in items:
        metadata = classify_headline(item['title'], item['source_url'], ticker, archive)
        url, title = metadata['canonical_url'], normalized_title(item['title'])
        duplicate = ('DUPLICATE_CANONICAL_URL' if url in urls else
                     'DUPLICATE_NORMALIZED_TITLE' if title in titles else None)
        if duplicate:
            reasons[duplicate] = reasons.get(duplicate, 0)+1
            continue
        urls.add(url); titles.add(title)
        unique.append({**item, 'evidence_metadata': metadata})
    unique.sort(key=_rank)
    if len(unique) > maximum:
        reasons['ITEM_LIMIT'] = len(unique)-maximum
    return unique[:maximum], reasons
