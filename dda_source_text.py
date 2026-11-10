"""Retrieve longer excerpts only for already classified source URLs, within budget."""
from concurrent.futures import ThreadPoolExecutor
import datetime as dt
import threading
import time

from dda_protocol import ET, NOTICE, public_url, stamp, words


def enrich(staged, root, cutoff, *, get=None, clock=None, monotonic=time.monotonic, seconds=15, twins=None):
    import fmp_client as F
    from factor_news import canonical_url
    clock = clock or (lambda: dt.datetime.now(ET))
    cutoff = stamp(cutoff)
    until = monotonic()+max(0, seconds)
    if twins is None:
        from us_preopen import load_twins
        twins = load_twins()
    lock, last = threading.Lock(), [0.]
    if get is None:
        try:
            key = F.load_key(root)
        except ValueError:
            key = None
        def get(path, **params):
            if not key:
                raise ValueError('DDA_SOURCE_NO_FMP_CREDENTIAL')
            with lock:
                pause = max(0, last[0]+1/9-monotonic())
                if monotonic()+pause >= until:
                    raise ValueError('DDA_SOURCE_BUDGET')
                if pause:
                    time.sleep(pause)
                last[0] = monotonic()
            return F.get(path, key, timeout=max(.1, min(4, until-monotonic())), retries=0, **params)
    targets = []
    for candidate in staged.get('candidates', []):
        heads = []
        for h in candidate.get('headlines', []):
            meta = h.get('evidence_metadata') or {}
            at = stamp(meta.get('first_disclosed_at') or h.get('published_at'))
            if (meta.get('issuer_role') == 'VERIFIED' and meta.get('classification') == 'ISSUER_RELEASE'
                    and at and at <= cutoff and cutoff-at <= dt.timedelta(hours=72)
                    and public_url(h.get('source_url')) and not NOTICE.search(words(h.get('title')))):
                heads.append(h)
        heads.sort(key=lambda h: stamp(h.get('published_at')).timestamp() if stamp(h.get('published_at')) else 0, reverse=True)
        if heads:
            targets.append((candidate['ticker'], heads[:2]))

    def one(target):
        ticker, heads = target
        receipt = {'ticker': ticker, 'matched': 0, 'status': 'UNMATCHED', 'excerpt_limit': 4000}
        try:
            if monotonic() >= until:
                raise ValueError('DDA_SOURCE_BUDGET')
            symbol = (twins.get(ticker) or {}).get('us') or ticker
            rows = get('news/press-releases', symbols=symbol, limit=15)
            if not isinstance(rows, list):
                raise ValueError('DDA_SOURCE_RESPONSE')
            lookup = {canonical_url(h['source_url']): h for h in heads}
            for r in rows[:30]:
                link = public_url(r.get('url'))
                if not link or canonical_url(link) not in lookup:
                    continue
                at = stamp(r.get('publishedDate'))
                if at is None:
                    try:
                        at = dt.datetime.strptime(str(r.get('publishedDate')), '%Y-%m-%d %H:%M:%S').replace(tzinfo=ET)
                    except ValueError:
                        continue
                if at > cutoff or cutoff-at > dt.timedelta(hours=72) or NOTICE.search(words(r.get('title'))):
                    continue
                excerpt = ' '.join(str(r.get('text') or '').split())[:4000]
                if not excerpt:
                    continue
                head = lookup[canonical_url(link)]
                if len(excerpt) <= len(head.get('summary') or ''):
                    continue
                head['summary'] = excerpt
                head['source_retrieved_at'] = stamp(clock()).isoformat()
                head['excerpt_provider'] = 'FMP matched archived issuer URL'
                receipt['matched'] += 1
            receipt['status'] = 'EXPANDED' if receipt['matched'] else 'UNMATCHED'
        except Exception as exc:
            receipt.update(status='UNAVAILABLE', error=type(exc).__name__)
        return receipt
    with ThreadPoolExecutor(max_workers=5) as pool:
        receipts = list(pool.map(one, targets))
    return {'budget_seconds': seconds, 'issuers_requested': len(targets),
            'excerpts_expanded': sum(r['matched'] for r in receipts), 'receipts': receipts,
            'note': 'Bounded release excerpts; unavailable or unmatched text retains the archived summary. No full-document diligence claim.'}
