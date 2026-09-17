"""Ask DeepSeek directly for the day's top long and short opportunities.

WHY THIS EXISTS SEPARATELY FROM `deepseek_factors`. That module asks a
deliberately narrow question — "is there directional sentiment in these
headlines" — under the day-102 grounded contract, and on a commentary-only news
feed the honest answer is almost always NO_EDGE. It is a registered sentiment
overlay, not an opinion. For six consecutive sessions the owner was shown that
abstention and reasonably read it as "DeepSeek is broken", when in fact nobody
had ever asked DeepSeek the question they wanted answered.

This module asks that question: given the same prepared technicals, WHICH NAMES
WOULD YOU BUY AND SHORT TODAY, and how sure are you? That is a different
instrument, so it lives in a different file, is staged by a different job, and
is reported in its own section beside the quantitative board rather than inside
it.

WHAT A CONFIDENCE HERE IS AND IS NOT. The number returned is the model's own
stated confidence. It is NOT a calibrated win probability, it has NO track
record, and it has never been scored against outcomes. It is not commensurate
with the engine's sided probability, which has 107 recorded legs behind it and
a published hit rate. The two are printed side by side so they can be compared
GOING FORWARD — that comparison is the entire point, and it requires forward
evidence this instrument does not yet have. Nothing here blends the two numbers,
because averaging a measured quantity with an unmeasured one launders the
second into the first.

THE MODEL SEES ONLY PYTHON-COMPUTED NUMBERS. Every indicator in the prompt was
computed locally from completed exchange sessions by `factor_inputs`; the model
does not compute indicators, does not see the ledger, does not see prices after
the previous close, and cannot select, size or rank anything outside the
supplied list.

NOTHING HERE IS ADOPTED. It selects nothing, sizes nothing, and enters neither
the baseline board nor the ledger. It cannot place an order.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import re
from pathlib import Path
from zoneinfo import ZoneInfo

from diagnostics import safe_detail

ET = ZoneInfo('America/New_York')

REGISTRATION = 'PREREGISTER_day110_deepseek_opportunities.md'
SCHEMA_VERSION = 'day110-opportunities-v1'
PROMPT_VERSION = 'day110-v1'
SNAPSHOT_NAME = 'deepseek_opportunities.json'
MAX_PER_SIDE = 2
MAX_NAMES = 60          # keep one request well inside the response-token budget
MAX_SNAPSHOT_AGE_HOURS = 6
MAX_SNAPSHOT_BYTES = 1_000_000
REQUEST_TIMEOUT = 150.0
# deepseek-flash is a REASONING model. Measured on the 2026-09-17 pool of 46
# names it spent 15,939 tokens thinking before emitting 349 tokens of JSON, so
# the obvious-looking 4,096 budget truncated every reply and the whole section
# read UNAVAILABLE with a healthy provider. Size this for the thinking, not the
# answer, and never parse a truncated reply.
MAX_COMPLETION_TOKENS = 32768
TICKER = re.compile(r'[A-Z0-9][A-Z0-9.\-]{0,19}\Z')
PREOPEN_CUTOFF = dt.time(9, 30)

SYSTEM_PROMPT = """You are ranking same-session intraday trading candidates on the Toronto Stock Exchange.

The entry is 09:46 ET and the exit is 15:59 ET on the SAME day. You are choosing
which names a trader should be long and which they should be short over those
hours, from the supplied list only.

You are given, per name, indicators computed in Python from completed sessions:
  r0        percent, 09:45 bar vs the 09:30 open, for the prior completed session
  gap       percent, session open vs previous session close; positive is UP
  rsi       0-100, daily RSI
  macd_hist MACD line minus signal; positive means MACD above signal
  rvol      completed-session volume / mean of 20 previous sessions
  vwap,last,open,orb_high,orb_low   prices in CAD

Rules you must follow:
- Choose at most 2 LONG and at most 2 SHORT. Fewer is correct when the evidence
  is thin. An empty list is a valid and often correct answer.
- Every name you return MUST come from the supplied list, by exact ticker.
- confidence is YOUR OWN stated confidence in the range 0.0 to 1.0. Do not
  inflate it. 0.5 means a coin flip. Use the full range honestly.
- reason must be one sentence, under 200 characters, naming the specific
  indicator values that drove the choice.
- Do not claim certainty, do not mention risk management, position sizing or
  stop losses, and do not reference anything outside the supplied data.

Return ONLY this JSON object and nothing else:
{"longs": [{"ticker": "X.TO", "confidence": 0.0, "reason": "..."}],
 "shorts": [{"ticker": "Y.TO", "confidence": 0.0, "reason": "..."}]}"""

CONFIDENCE_LABEL = ("The model's own stated confidence. NOT a calibrated win probability: "
                    "it has no track record, has never been scored against an outcome, and "
                    "is not comparable with the engine's sided probability.")


def unavailable(reason):
    return {'status': 'UNAVAILABLE', 'reason': safe_detail(reason), 'longs': [], 'shorts': [],
            'model': None, 'considered': 0, 'universe': [], 'gaps': [], 'adopted': False,
            'registration': REGISTRATION, 'confidence_label': CONFIDENCE_LABEL}


def _row(candidate):
    """One compact line per name. Only validated Python numerics travel."""
    t = candidate.get('technicals') or {}
    keep = ('r0', 'gap', 'rsi', 'macd_hist', 'rvol', 'last', 'open', 'vwap', 'orb_high', 'orb_low')
    values = {k: round(float(t[k]), 4) for k in keep
              if isinstance(t.get(k), (int, float)) and not isinstance(t.get(k), bool)}
    return {'ticker': candidate['ticker'], **values}


def _clean(rows, allowed, side):
    """Reject anything outside the supplied universe; never repair a bad row."""
    out, seen, gaps = [], set(), []
    if not isinstance(rows, list):
        return out, ['invalid %s list' % side]
    for row in rows[:MAX_PER_SIDE]:
        if not isinstance(row, dict):
            gaps.append('invalid %s row' % side)
            continue
        ticker = row.get('ticker')
        if not isinstance(ticker, str) or not TICKER.fullmatch(ticker):
            gaps.append('invalid ticker')
            continue
        if ticker not in allowed:
            # The model invented a name. That is the one failure mode that
            # could put a ticker in front of the owner that was never assessed.
            gaps.append('%s outside the supplied universe' % safe_detail(ticker, 24))
            continue
        if ticker in seen:
            gaps.append('duplicate %s' % safe_detail(ticker, 24))
            continue
        confidence = row.get('confidence')
        if (isinstance(confidence, bool) or not isinstance(confidence, (int, float))
                or not 0.0 <= float(confidence) <= 1.0):
            gaps.append('%s confidence outside 0-1' % safe_detail(ticker, 24))
            continue
        seen.add(ticker)
        out.append({'ticker': ticker, 'confidence': round(float(confidence), 3),
                    'reason': safe_detail(str(row.get('reason') or ''), 200)})
    return out, gaps


def usable_candidates(candidates):
    """Names carrying enough prepared technicals to be worth asking about.

    RSI alone is not enough: a name with RSI but no MACD or RVOL gives the model
    a thinner row than its neighbours and makes the comparison across names
    uneven. Require the momentum and participation trio, which is exactly the
    set `prepare_factor_pool` counts as complete technicals."""
    required = ('rsi', 'macd_hist', 'rvol', 'last', 'vwap')
    out = []
    for c in candidates or []:
        if not isinstance(c, dict) or not isinstance(c.get('ticker'), str):
            continue
        t = c.get('technicals') or {}
        if all(isinstance(t.get(k), (int, float)) and not isinstance(t.get(k), bool)
               for k in required):
            out.append(c)
    return out[:MAX_NAMES]


def rank(candidates, *, model=None, client=None, now=None, timeout=REQUEST_TIMEOUT):
    """Ask once, validate hard, return at most two per side. Pure of state."""
    now = now or dt.datetime.now(ET)
    usable = usable_candidates(candidates)
    if not usable:
        return unavailable('No candidate carried complete prepared technicals.')
    allowed = {c['ticker'] for c in usable}
    model = model or os.environ.get('DEEPSEEK_MODEL') or 'deepseek-flash'

    if client is None:
        key = os.environ.get('DEEPSEEK_API_KEY', '').strip()
        if not key:
            return unavailable('DEEPSEEK_API_KEY is not set.')
        try:
            from openai import OpenAI
        except ImportError:
            return unavailable('The DeepSeek client library is not installed.')
        client = OpenAI(api_key=key, base_url='https://api.deepseek.com',
                        max_retries=0, timeout=timeout)

    payload = {'session': now.date().isoformat(), 'entry': '09:46 ET', 'exit': '15:59 ET',
               'candidates': [_row(c) for c in usable]}
    try:
        response = client.chat.completions.create(
            model=model,
            messages=[{'role': 'system', 'content': SYSTEM_PROMPT},
                      {'role': 'user', 'content': json.dumps(payload, sort_keys=True, allow_nan=False)}],
            response_format={'type': 'json_object'},
            max_tokens=MAX_COMPLETION_TOKENS, timeout=timeout)
        choice = response.choices[0]
        if choice.finish_reason != 'stop':
            # A truncated reasoning model emits half an object. Parsing it would
            # silently drop a side; say it was cut off instead.
            return unavailable('The model response was cut off (%s).'
                               % safe_detail(str(choice.finish_reason), 40))
        body = json.loads(choice.message.content)
        if not isinstance(body, dict):
            raise ValueError('reply is not an object')
    except Exception as exc:
        # Never echo a provider payload or a credential into the report.
        return unavailable('The ranking request failed: ' + type(exc).__name__)

    longs, long_gaps = _clean(body.get('longs'), allowed, 'long')
    shorts, short_gaps = _clean(body.get('shorts'), allowed, 'short')
    return {'status': 'READY' if (longs or shorts) else 'NO_OPPORTUNITY',
            'model': safe_detail(str(getattr(response, 'model', model)), 60),
            'considered': len(usable), 'universe': sorted(allowed),
            'longs': longs, 'shorts': shorts, 'gaps': long_gaps + short_gaps,
            'asked_at': now.isoformat(), 'adopted': False, 'registration': REGISTRATION,
            'confidence_label': CONFIDENCE_LABEL}


# ── staging ───────────────────────────────────────────────────────────────────

def _seal(obj):
    from report_store import encode
    obj = {k: v for k, v in obj.items() if k != 'snapshot_sha256'}
    obj['snapshot_sha256'] = hashlib.sha256(encode(obj).encode()).hexdigest()
    return obj


def stage(state_dir, *, now=None, client=None, model=None, diagnostic=False):
    """Ask before the open and seal the answer. One request, no retry.

    PRE-OPEN ONLY, for the same reason the rest of this path is: every input is
    a completed-session indicator, and asking after the bell would let the
    market's reaction to the open leak into an opinion about the open. The
    request takes about a minute on a reasoning model, which is another reason
    it cannot live in the 09:46 publication window.
    """
    from build_biotech import write_atomic
    now = (now or dt.datetime.now(ET))
    if now.tzinfo is None:
        raise ValueError('AWARE_CLOCK_REQUIRED')
    now = now.astimezone(ET)
    root = Path(state_dir)
    if diagnostic:
        from diagnostic_context import require_context
        require_context(root)
    elif now.time() >= PREOPEN_CUTOFF:
        raise ValueError('OPPORTUNITIES_PREOPEN_ONLY')

    # THE CREDENTIAL LIVES IN STATE, NOT IN THE ENVIRONMENT. `rank()` reads
    # os.environ, which is correct for a pure function but wrong for a job: run
    # from morning_full.sh in a fresh process nothing has exported the key, and
    # the section would have read "DEEPSEEK_API_KEY is not set" every morning
    # against a healthy account. Reuse prepare_deepseek's loaders rather than
    # copying the contract — one implementation, one place to fix.
    from prepare_deepseek import load_private_key, load_private_model
    credential_gaps = []
    try:
        if not load_private_key(root):
            credential_gaps.append('No DeepSeek credential is staged for this session.')
        model = model or load_private_model(root)
    except (OSError, UnicodeError, ValueError) as exc:
        credential_gaps.append('The staged DeepSeek credential was rejected (%s).'
                               % type(exc).__name__)

    pool_path = root/'deepseek_candidates.json'
    try:
        pool = json.loads(pool_path.read_text())
        candidates = pool['candidates']
        if not isinstance(candidates, list):
            raise ValueError('pool is not a list of candidates')
    except (OSError, UnicodeError, ValueError, TypeError, KeyError) as exc:
        result = unavailable('The candidate pool has not been staged (%s).' % type(exc).__name__)
    else:
        result = rank(candidates, client=client, model=model, now=now)

    context = ({'kind': 'CURRENT_TIME_DIAGNOSTIC', 'morning_snapshot': False,
                'prediction_evidence': False} if diagnostic else {})
    # A missing credential must be named, not left to surface as a generic
    # request failure two layers down (house rule 1).
    result = {**result, 'gaps': list(result.get('gaps') or []) + credential_gaps}
    snapshot = _seal({**result, 'schema_version': SCHEMA_VERSION,
                      'prompt_version': PROMPT_VERSION,
                      'session': now.date().isoformat(), 'prepared_at': now.isoformat(),
                      **context})
    write_atomic(root/SNAPSHOT_NAME, snapshot)
    return snapshot


# ── reading ───────────────────────────────────────────────────────────────────

def load_prepared(state_dir, now, *, diagnostic=False):
    """Revalidate the sealed snapshot. Pure: no provider call, no state written.

    Renderers consume this. A renderer that could reach a model would be able to
    change what the report says after the report was frozen, so this path reads
    bytes and checks them and does nothing else.
    """
    try:
        now = now.astimezone(ET) if now.tzinfo else now.replace(tzinfo=ET)
        path = Path(state_dir)/SNAPSHOT_NAME
        if not path.exists():
            return unavailable('The opportunity ranking was not staged for this session.')
        if path.stat().st_size > MAX_SNAPSHOT_BYTES:
            raise ValueError('oversized snapshot')
        obj = json.loads(path.read_text())
        if not isinstance(obj, dict):
            raise ValueError('snapshot is not an object')
        seal = obj.get('snapshot_sha256')
        if not isinstance(seal, str) or not re.fullmatch(r'[a-f0-9]{64}', seal):
            raise ValueError('missing or malformed integrity seal')
        if _seal(obj)['snapshot_sha256'] != seal:
            raise ValueError('integrity mismatch')
        is_diagnostic = (obj.get('kind') == 'CURRENT_TIME_DIAGNOSTIC'
                         and obj.get('morning_snapshot') is False)
        if diagnostic != is_diagnostic:
            raise ValueError('diagnostic evidence is not a morning snapshot')
        if obj.get('schema_version') != SCHEMA_VERSION:
            raise ValueError('unknown schema version')
        if obj.get('adopted') is not False:
            raise ValueError('a snapshot claiming adoption is not readable here')
        prepared = dt.datetime.fromisoformat(obj['prepared_at'])
        if prepared.tzinfo is None:
            raise ValueError('naive preparation clock')
        prepared = prepared.astimezone(ET)
        if (obj.get('session') != now.date().isoformat() or prepared.date() != now.date()
                or prepared > now
                or (now-prepared).total_seconds() > MAX_SNAPSHOT_AGE_HOURS*3600
                or (not is_diagnostic and prepared.time() >= PREOPEN_CUTOFF)):
            raise ValueError('snapshot identity or clock mismatch')
        universe = obj.get('universe')
        if not isinstance(universe, list):
            raise ValueError('the assessed universe is missing')
        allowed = {t for t in universe if isinstance(t, str) and TICKER.fullmatch(t)}
        # Revalidate the picks against the universe the snapshot itself records,
        # so an edited file cannot put an unassessed ticker in front of a reader.
        longs, long_gaps = _clean(obj.get('longs'), allowed, 'long')
        shorts, short_gaps = _clean(obj.get('shorts'), allowed, 'short')
        status = obj.get('status')
        if status not in ('READY', 'NO_OPPORTUNITY', 'UNAVAILABLE'):
            raise ValueError('unknown status')
        if status == 'UNAVAILABLE':
            return {**unavailable(obj.get('reason') or 'Ranking unavailable.'),
                    'prepared_at': prepared.isoformat(), 'diagnostic': is_diagnostic}
        return {'diagnostic': is_diagnostic,
                'status': 'READY' if (longs or shorts) else 'NO_OPPORTUNITY',
                'model': safe_detail(str(obj.get('model') or 'unavailable'), 60),
                'considered': len(allowed), 'universe': sorted(allowed),
                'longs': longs, 'shorts': shorts,
                'gaps': [safe_detail(str(g)) for g in (obj.get('gaps') or [])]
                        + long_gaps + short_gaps,
                'prepared_at': prepared.isoformat(), 'adopted': False,
                'registration': REGISTRATION, 'confidence_label': CONFIDENCE_LABEL}
    except (OSError, UnicodeError, ValueError, TypeError, KeyError, AttributeError) as exc:
        return unavailable('The staged opportunity ranking was rejected (%s).' % type(exc).__name__)


def load_diagnostic(state_dir, now):
    from diagnostic_context import require_context
    require_context(Path(state_dir))
    return load_prepared(state_dir, now, diagnostic=True)


# ── comparison ────────────────────────────────────────────────────────────────

AGREE = 'both chose this name, same side'
OPPOSE = 'engine took the OPPOSITE side'
PASSED = 'engine scored this name and did not select it'
UNSEEN = 'outside the engine universe — never scored'


def compare(opportunities, legs, engine_universe=None):
    """Line the two instruments up name by name. Computes no combined score.

    Blending a measured probability with an unmeasured self-report would launder
    the second into the first, so this only reports WHERE THEY AGREE — which is
    the observable the forward study needs, and the thing the owner asked for.

    `engine_universe` matters more than it looks. The baseline engine scores 21
    names; the factor pool is 130. Without it, every disagreement reads as "the
    engine rejected this", when on 2026-09-17 all four model picks were simply
    names the engine has never looked at. Those are different findings and only
    one of them is evidence about the engine.
    """
    engine = {}
    for leg in legs or []:
        ticker, side = leg.get('ticker'), leg.get('side')
        if isinstance(ticker, str) and side in ('LONG', 'SHORT'):
            engine[ticker] = {'side': side, 'p_sided': leg.get('p_sided'),
                              'status': leg.get('status')}
    scored = set(engine_universe) if engine_universe else None
    rows = []
    for side, key in (('LONG', 'longs'), ('SHORT', 'shorts')):
        for pick in (opportunities or {}).get(key) or []:
            seen = engine.get(pick['ticker'])
            if seen is not None:
                verdict = AGREE if seen['side'] == side else OPPOSE
            elif scored is None:
                verdict = PASSED
            else:
                verdict = PASSED if pick['ticker'] in scored else UNSEEN
            rows.append({'side': side, 'ticker': pick['ticker'],
                         'confidence': pick['confidence'], 'reason': pick.get('reason'),
                         'engine_side': (seen or {}).get('side'),
                         'engine_p_sided': (seen or {}).get('p_sided'),
                         'engine_status': (seen or {}).get('status'), 'verdict': verdict})
    counts = {key: sum(1 for r in rows if r['verdict'] == key)
              for key in (AGREE, OPPOSE, PASSED, UNSEEN)}
    return {'rows': rows, 'agree': counts[AGREE], 'oppose': counts[OPPOSE],
            'passed_over': counts[PASSED], 'unseen': counts[UNSEEN],
            'comparable': counts[AGREE]+counts[OPPOSE]+counts[PASSED],
            'engine_only': sorted(t for t in engine
                                  if t not in {r['ticker'] for r in rows})}


# ── positive control ──────────────────────────────────────────────────────────

CONTROL_LONG = 'CTLUP.TO'
CONTROL_SHORT = 'CTLDN.TO'


def control_universe():
    """A planted universe: one unambiguous long, one unambiguous short, noise.

    House rule 4: a harness that cannot detect a planted edge cannot report a
    null. If this ranker returns NO_OPPORTUNITY on a real morning, that reading
    is worth nothing until a planted edge is shown to survive the same path.

    The planting is in the NUMBERS ONLY. Day-109's first control failed because
    it wrote "SYNTHETIC CONTROL" into the evidence and the model correctly
    refused to lean on material labelled fake; the tickers here are neutral and
    nothing in the payload announces itself as a test.
    """
    def name(ticker, *, r0, gap, rsi, hist, rvol, last, vwap, orb_high, orb_low):
        return {'ticker': ticker, 'technicals': {
            'r0': r0, 'gap': gap, 'rsi': rsi, 'macd_hist': hist, 'rvol': rvol,
            'last': last, 'open': round(last*(1-r0/100), 2), 'vwap': vwap,
            'orb_high': orb_high, 'orb_low': orb_low}}
    rows = [
        name(CONTROL_LONG, r0=2.9, gap=1.8, rsi=64.0, hist=0.42, rvol=3.10,
             last=42.80, vwap=41.60, orb_high=41.90, orb_low=40.85),
        name(CONTROL_SHORT, r0=-2.7, gap=-1.9, rsi=27.0, hist=-0.39, rvol=2.95,
             last=18.20, vwap=19.05, orb_high=19.45, orb_low=18.55),
    ]
    for i in range(10):
        rows.append(name('NOIS%d.TO' % i, r0=0.04*(i-5), gap=0.03*(5-i), rsi=49.0+0.2*i,
                         hist=0.001*(i-5), rvol=1.0+0.01*i, last=30.0+i,
                         vwap=30.0+i, orb_high=30.2+i, orb_low=29.8+i))
    return rows


def run_control(*, client=None, model=None, now=None):
    """Return the ranking plus whether each planted side was detected."""
    result = rank(control_universe(), client=client, model=model, now=now)
    return {**result,
            'long_detected': any(r['ticker'] == CONTROL_LONG for r in result.get('longs') or []),
            'short_detected': any(r['ticker'] == CONTROL_SHORT for r in result.get('shorts') or [])}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--state-dir', default=os.environ.get('RB_STATE_DIR', '.rb-state'))
    parser.add_argument('--diagnostic', action='store_true',
                        help='run in an isolated current-time diagnostic context')
    parser.add_argument('--control', action='store_true',
                        help='run the planted-edge positive control instead of the pool')
    args = parser.parse_args(argv)
    if args.control:
        result = run_control()
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0 if (result['long_detected'] and result['short_detected']) else 2
    result = stage(args.state_dir, diagnostic=args.diagnostic)
    print(json.dumps({k: v for k, v in result.items() if k != 'universe'},
                     indent=2, sort_keys=True))
    return {'READY': 0, 'NO_OPPORTUNITY': 0}.get(result.get('status'), 2)


if __name__ == '__main__':
    raise SystemExit(main())
