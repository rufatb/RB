"""Deterministic evidence labels for the unadopted factor experiment.

This is a bounded protocol check, not a natural-language truth detector. It
never fetches, recalculates indicators, estimates probabilities or selects a
production name. Model prose is private audit material; the public explanation
is assembled from validated references and Python facts. Evidence-ID membership
does not establish that a source is relevant, novel, material or true.
"""
from __future__ import annotations

import copy
import hashlib
import json
import re

from deepseek_policy import MAX_RATIONALE_CHARS

from deepseek_policy import PROMPT_VERSION as VERSION
FORECAST_HORIZON = 'remaining_session_to_1559_ET'

# These are units of the existing Python producers, not new transformations.
# In particular r0 and gap are PERCENT, whereas vp/rvol are dimensionless ratios.
TECHNICAL_DEFINITIONS = {
    'r0': ('percent', '100 * (09:45 bar reference / 09:30 open - 1), for the declared technical session'),
    'gap': ('percent', '100 * (session open / immediate previous session close - 1); positive means UP, negative DOWN'),
    'vp': ('ratio', 'first-15-minute volume / mean first-15-minute volume of 20 prior sessions'),
    'quant_probability': ('bounded_score', 'unproven model score, not a calibrated win probability'),
    'vwap': ('quote_currency', 'Python volume-weighted price over the declared technical scope'),
    'rsi': ('index_0_100', 'Python RSI of completed daily closes when scope declares daily RSI'),
    'macd': ('quote_currency', 'Python MACD line; positive is above zero, not proof of future direction'),
    'macd_signal': ('quote_currency', 'Python MACD signal line'),
    'macd_hist': ('quote_currency', 'Python MACD line minus signal line; positive means MACD above signal'),
    'orb_high': ('quote_currency', 'first-15-minute high of the declared technical session'),
    'orb_low': ('quote_currency', 'first-15-minute low of the declared technical session'),
    'rvol': ('ratio', 'completed session volume / mean volume of 20 previous full sessions; not current opening RVOL'),
    'last': ('quote_currency', 'last price in the declared technical scope, not an executable live quote'),
    'price': ('quote_currency', 'supplied price in the declared technical scope'),
    'open': ('quote_currency', 'open of the declared technical session'),
    'volume': ('shares', 'volume over the declared technical scope'),
}

# Deliberately conservative, bounded vocabulary refusal. This catches the
# observed gap/MACD contradictions without claiming to interpret arbitrary
# language or prove every other statement. All raw prose is withheld even when
# none of these words occur. A benign use of e.g. "gap" is a visible exclusion.
PROHIBITED_TECHNICAL_PROSE = re.compile(
    r'\b(?:gaps?|gapped|gapping|macd|histograms?|rsi|vwap|orb|rvol|technicals?|'
    r'momentum|overbought|oversold|r0|vp|quant_probability|macd_signal|'
    r'macd_hist|orb_high|orb_low)\b|'
    r'\b(?:opening[ -]range|relative[ -]volume|moving[ -]average|'
    r'price[ -]action|volume[ -]weighted|bid[ -]ask)\b', re.I)


def _hash(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                    allow_nan=False, separators=(',', ':')).encode()).hexdigest()


def technical_facts(candidate):
    """Describe already-validated numeric values with exact sign and scope."""
    facts = []
    for field, value in sorted(candidate['technicals'].items()):
        unit, definition = TECHNICAL_DEFINITIONS[field]
        if (field in ('rvol', 'vp', 'rsi', 'macd', 'macd_signal', 'macd_hist')
                and not candidate['technicals_scope'].startswith('previous_completed_session')):
            definition = ('Supplied Python value in the declared scope; the completed-session '
                          'producer formula is not independently certified for this custom scope')
        sign = ('UNKNOWN' if value is None else 'POSITIVE' if value > 0
                else 'NEGATIVE' if value < 0 else 'ZERO')
        number = 'unavailable' if value is None else format(value, '+.8g')
        suffix = '%' if unit == 'percent' and value is not None else ''
        facts.append({'field': field, 'value': value, 'unit': unit, 'sign': sign,
                      'as_of': candidate['technicals_as_of'],
                      'scope': candidate['technicals_scope'],
                      'statement': field+' '+number+suffix+' ('+sign+')',
                      'definition': definition})
    return facts


def request_payload(validated):
    """Enrich a validated payload; original evidence/numerics are unchanged."""
    payload = copy.deepcopy(validated)
    payload['response_contract'] = VERSION
    payload['forecast'] = {
        'horizon': FORECAST_HORIZON,
        'information_cutoff': validated['as_of'],
        'start_rule': 'Actual assessment completion, or 09:46 ET if prepared before then; never backdate a late assessment',
        'end_rule': '15:59 America/New_York on the same exchange session',
        'scope': 'Unadopted directional context for the remaining session; not a probability, entry instruction, or multi-month thesis',
    }
    payload['evidence_limitations'] = [
        'Evidence IDs prove only supplied-item identity, not semantic support, issuer relevance, novelty or materiality',
        'Publication time is not first-disclosure time; unknown event novelty remains unknown',
        'Previous-completed-session indicators do not describe the current opening path',
        'An absolute macro level does not establish a rising or falling trend',
        'Completed-session RVOL is not current-time relative volume',
    ]
    for candidate in payload['candidates']:
        candidate['technical_facts'] = technical_facts(candidate)
        for field in ('headlines', 'catalyst_tags'):
            for item in candidate[field]:
                # Identity includes the ticker to prevent citing another issuer's
                # item, even when a syndicated story appears in both feeds.
                item['evidence_id'] = 'E'+_hash({'ticker': candidate['ticker'],
                                                'kind': field, 'item': item})[:16]
    return payload


def allowed_evidence(candidate):
    return {item['evidence_id']: item for field in ('headlines', 'catalyst_tags')
            for item in candidate[field]}


def grounding_issues(row, candidate):
    """Check the explicit contract; no claim of semantic truth verification."""
    issues = []
    ids = row['evidence_ids']
    allowed = allowed_evidence(candidate)
    if (not isinstance(ids, list) or len(ids) > len(allowed)
            or any(not isinstance(value, str) for value in ids)
            or len(set(ids)) != len(ids)):
        issues.append('INVALID_EVIDENCE_IDS')
    elif any(value not in allowed for value in ids):
        issues.append('UNKNOWN_OR_OTHER_TICKER_EVIDENCE_ID')
    elif not ids:
        # Even NO_EDGE needs cited input to distinguish assessed abstention
        # from an unassessed ticker. No fabricated citation is substituted.
        issues.append('MISSING_EVIDENCE_SUPPORT')
    elif row['directional_lean'] in ('BULL', 'BEAR'):
        # A fresh RSS timestamp cannot turn explicit investment commentary or
        # a multi-year title into an intraday event. Unknown classifications
        # remain unknown rather than being promoted to verified events or
        # mechanically excluding all independently unclassified evidence.
        cited = [allowed[value] for value in ids]
        def wrong_horizon(item):
            metadata = item.get('evidence_metadata') or {}
            return (metadata.get('classification') == 'COMMENTARY'
                    or metadata.get('impact_horizon') == 'MULTI_YEAR_TITLE')
        if all(wrong_horizon(item) for item in cited):
            issues.append('NO_INTRADAY_EVENT_SUPPORT')
    if row['forecast_horizon'] != FORECAST_HORIZON:
        issues.append('FORECAST_HORIZON_MISMATCH')
    if PROHIBITED_TECHNICAL_PROSE.search(row['factor_rationale']):
        issues.append('TECHNICAL_PROSE_PROHIBITED')
    return issues


def display_rationale(row, candidate):
    """Deterministic compact explanation; never display model-written prose."""
    ids = ','.join(row['evidence_ids'][:2])
    more = (' plus '+str(len(row['evidence_ids'])-2)+' more') if len(row['evidence_ids']) > 2 else ''
    # Scope is rendered by code rather than trusting an arbitrary free-text
    # label to become a technical explanation.
    old = candidate['technicals_scope'].startswith('previous_completed_session')
    scope = 'prior session' if old else 'declared session'
    facts = {fact['field']: fact for fact in candidate['technical_facts']}
    chosen = [facts[key]['statement'] for key in ('gap', 'macd_hist') if key in facts]
    technical = '; Python '+', '.join(chosen) if chosen else '; Python technical facts recorded separately'
    text = ('Model '+row['directional_lean']+' opinion cites '+ids+more+technical+
            '; '+scope+' as of '+candidate['technicals_as_of'])
    # Fixed formatting can exceed 280 only with an unusually long timestamp or
    # very small/large numeric exponent. Drop the optional technical preview,
    # never truncate a number or hide the scope. Full facts stay in grounding.
    if len(text) > MAX_RATIONALE_CHARS:
        text = ('Model '+row['directional_lean']+' opinion cites '+ids+more+
                '; Python facts recorded separately; '+scope+' as of '+candidate['technicals_as_of'])
    return text
