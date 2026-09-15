"""Pure Day101 forward, paired-session evidence; no files, fetches or adoption.

Input contract (``evaluate(panel, as_of=aware_clock)``):

``panel`` has ``schema_version=1``, ``evidence_mode=FORWARD|SIMULATED``,
``experiment`` and ``sessions``. The experiment declares registration, aware
``registered_at`` and ``confirmation_frozen_at`` clocks, ``start_session``,
``end_session``, baseline/challenger arm names, and an ``arm_configs`` mapping
of every registered arm to its SHA256, ``preserved_prior_arms`` identifying
at least the three older H1/H2/watchlist arms, and ``benchmark_ticker``.
The fixed first60 TSX calendar slots
are development; subsequent slots are confirmation. Missing slots do not move
the boundary. Confirmatory settings must have been frozen before slot61.

Each session has ``session`` and ``arms``. Every arm has
``state=TRADE|ABSTAIN|UNAVAILABLE``. UNAVAILABLE includes a reason. A successful
evaluation, including cash ABSTAIN, requires ``decision`` with aware recorded_at,
input_as_of, membership_as_of; config/input/membership SHA256 values; and
selection_sha256 from ``selection_hash(session, arm_name, record)``. That seal
binds state and all selected tickers, sides, capital weights, sectors/industries
before entry. ABSTAIN requires no legs and a factual reason; no absent arm or
missing execution observation is interpreted as an abstention.

TRADE contains legs with ticker, side LONG|SHORT, weight (fraction of original
capacity), sector, industry, entry/exit quotes, costs, and (for shorts) borrow.
Quotes contain ticker, currency CAD, bid, ask, quote_time, source_url,
source_receipt_sha256. The registered windows are09:46 and15:59 ET on the same
full TSX session. Costs contain measured=True, fees_bps, slippage_bps,
recorded_at and receipt_sha256. Borrow additionally contains available=True,
available_at, cost_bps, availability_sha256 and financing_receipt_sha256.
Each traded arm also requires a benchmark with return_bps, observed_at,
source_url and receipt_sha256. Benchmark return spans the same registered
windows. Required prices and measured costs are never imputed.

Returns are timestamped BBO crossing proxies using execution.score_leg with
measured fee/slippage/financing inputs, not claimed brokerage fills. Source
receipt hashes are references: this evaluator checks structure, selection seal
and chronology, but cannot independently authenticate receipt custody. Keep
the underlying dated source receipts in the operational archive. SIMULATED
fixtures exercise the harness only and can never become forward evidence.

Statistics use session clusters, moving blocks of five consecutive exchange
sessions,2000 draws, seed101, threshold3.5 and MDE80=(3.5+.8416212336)*SE.
No block bridges a missing session. Primary comparison is the expanded arm
minus unchanged baseline, alongside all other declared arms. Numeric means
are descriptive; no output authorizes strategy adoption or rewrites history.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import math
import re
from urllib.parse import parse_qs, urlsplit
from zoneinfo import ZoneInfo

import numpy as np

REGISTRATION = 'PREREGISTER_day101_tsx_expansion.md'
ET = ZoneInfo('America/New_York')
BLOCK = 5
DRAWS = 2000
SEED = 101
Z = 3.5
POWER_Z = .8416212336
DEVELOPMENT = CONFIRMATION = 60
_HASH = re.compile(r'^[a-f0-9]{64}$')


def _stamp(value):
    if isinstance(value, str):
        value = dt.datetime.fromisoformat(value.replace('Z', '+00:00'))
    if not isinstance(value, dt.datetime) or value.tzinfo is None:
        raise ValueError('AWARE_CLOCK_REQUIRED')
    return value.astimezone(ET)


def _number(value, *, nonnegative=False, positive=False):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError('FINITE_NUMBER_REQUIRED')
    if nonnegative and value < 0 or positive and value <= 0:
        raise ValueError('INVALID_NUMBER_SIGN')
    return float(value)


def _hash(value):
    if not isinstance(value, str) or not _HASH.fullmatch(value):
        raise ValueError('RECEIPT_HASH_REQUIRED')
    return value


def _url(value):
    url = urlsplit(value if isinstance(value, str) else '')
    if (url.scheme != 'https' or not url.hostname or url.username or url.password
            or any(k.lower() in {'apikey', 'api_key', 'api_token', 'token', 'key', 'authorization'}
                   for k in parse_qs(url.query))):
        raise ValueError('CREDENTIAL_FREE_SOURCE_URL_REQUIRED')


def selection_hash(session, arm, record):
    """Canonical pre-entry selection seal; execution outcomes are excluded."""
    decision = record['decision']
    selected = [{name: leg[name] for name in ('ticker', 'side', 'weight', 'sector', 'industry')}
                for leg in record.get('legs', [])]
    payload = {'session': session, 'arm': arm, 'state': record['state'],
               'legs': selected, 'reason': record.get('reason'),
               'decision': {name: decision[name] for name in ('recorded_at', 'input_as_of',
                   'membership_as_of', 'config_sha256', 'input_sha256', 'membership_sha256')}}
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(',', ':'),
                                    allow_nan=False).encode()).hexdigest()


def _quote(raw, ticker, session, minute, now):
    clock = _stamp(raw['quote_time'])
    if (raw.get('ticker') != ticker or raw.get('currency') != 'CAD'
            or str(clock.date()) != session or clock.strftime('%H:%M') != minute or clock > now):
        raise ValueError('EXACT_WINDOW_QUOTE_REQUIRED')
    bid, ask = _number(raw['bid'], positive=True), _number(raw['ask'], positive=True)
    if ask < bid:
        raise ValueError('CROSSED_QUOTE')
    _hash(raw['source_receipt_sha256'])
    _url(raw['source_url'])
    return {'status': 'OK', 'bid': bid, 'ask': ask, 'quote_time': clock.isoformat(),
            'spread_bps': (ask-bid)/((ask+bid)/2)*10000}, clock


def _arm(session, name, record, experiment, now, full_session):
    """An invalid leg makes its whole arm/session missing; never drop losers."""
    missing = {'state': 'UNAVAILABLE', 'net_bps': None, 'gross_bps': None,
               'tide_bps': None, 'selection_net_bps': None, 'legs': [], 'turnover': None}
    try:
        if not isinstance(record, dict):
            raise ValueError('ARM_NOT_RECORDED')
        state = record.get('state')
        if state == 'UNAVAILABLE':
            return {**missing, 'reason': 'RECORDED_UNAVAILABLE'}
        if state not in ('TRADE', 'ABSTAIN'):
            raise ValueError('INVALID_ARM_STATE')
        decision = record['decision']
        recorded = _stamp(decision['recorded_at'])
        input_at, member_at = _stamp(decision['input_as_of']), _stamp(decision['membership_as_of'])
        cutoff = dt.datetime.combine(dt.date.fromisoformat(session), dt.time(9, 47), ET)
        if (str(recorded.date()) != session or recorded >= cutoff or recorded > now
                or input_at > recorded or member_at > recorded
                or str(input_at.date()) != session or str(member_at.date()) != session
                or recorded <= _stamp(experiment['registered_at'])):
            raise ValueError('POINT_IN_TIME_DECISION_REQUIRED')
        for key in ('config_sha256', 'input_sha256', 'membership_sha256', 'selection_sha256'):
            _hash(decision[key])
        if decision['config_sha256'] != experiment['arm_configs'][name]:
            raise ValueError('REGISTERED_CONFIG_CHANGED')
        if decision['selection_sha256'] != selection_hash(session, name, record):
            raise ValueError('SELECTION_SEAL_MISMATCH')
        legs = record.get('legs')
        if not isinstance(legs, list):
            raise ValueError('LEGS_REQUIRED')
        if state == 'ABSTAIN':
            if legs or not isinstance(record.get('reason'), str) or not record['reason'].strip():
                raise ValueError('EVALUATED_ABSTENTION_REQUIRED')
            return {'state': state, 'net_bps': 0., 'gross_bps': 0., 'tide_bps': 0.,
                    'selection_net_bps': 0., 'turnover': 0., 'legs': [], 'reason': record['reason'][:160]}
        if not full_session:
            raise ValueError('REGISTERED_EXIT_UNAVAILABLE_SHORT_SESSION')
        if not legs or len(legs) > 150:
            raise ValueError('TRADE_LEGS_REQUIRED')
        benchmark = record['benchmark']
        if benchmark.get('ticker') != experiment['benchmark_ticker'] or benchmark.get('currency') != 'CAD':
            raise ValueError('REGISTERED_BENCHMARK_REQUIRED')
        index_bps = _number(benchmark['return_bps'])
        observed = _stamp(benchmark['observed_at'])
        if (str(observed.date()) != session or observed.strftime('%H:%M') != '15:59' or observed > now):
            raise ValueError('EXACT_WINDOW_BENCHMARK_REQUIRED')
        if benchmark.get('entry_time') != '09:46' or benchmark.get('exit_time') != '15:59':
            raise ValueError('EXACT_WINDOW_BENCHMARK_REQUIRED')
        _url(benchmark['source_url'])
        _hash(benchmark['receipt_sha256'])
        scored, seen = [], set()
        from execution import score_leg
        for leg in legs:
            ticker, side = leg['ticker'], leg['side']
            if (not isinstance(ticker, str) or not re.fullmatch(r'[A-Z0-9.-]+\.TO', ticker)
                    or ticker in seen or side not in ('LONG', 'SHORT')):
                raise ValueError('EXACT_UNIQUE_TSX_LEG_REQUIRED')
            seen.add(ticker)
            if any(not isinstance(leg.get(k), str) or not leg[k].strip() for k in ('sector', 'industry')):
                raise ValueError('POINT_IN_TIME_INDUSTRY_REQUIRED')
            weight = _number(leg['weight'], positive=True)
            entry, entry_at = _quote(leg['entry'], ticker, session, '09:46', now)
            exit_quote, exit_at = _quote(leg['exit'], ticker, session, '15:59', now)
            if recorded > entry_at:
                raise ValueError('SELECTION_RECORDED_AFTER_ENTRY')
            costs = leg['costs']
            if costs.get('measured') is not True or not exit_at <= _stamp(costs['recorded_at']) <= now:
                raise ValueError('MEASURED_COST_RECEIPT_REQUIRED')
            _hash(costs['receipt_sha256'])
            fees = _number(costs['fees_bps'], nonnegative=True)
            slippage = _number(costs['slippage_bps'], nonnegative=True)
            borrow_bps = 0.
            if side == 'SHORT':
                borrow = leg['borrow']
                available_at = _stamp(borrow['available_at'])
                if (borrow.get('available') is not True or str(available_at.date()) != session
                        or available_at > entry_at):
                    raise ValueError('SHORT_AVAILABILITY_RECEIPT_REQUIRED')
                _hash(borrow['availability_sha256'])
                _hash(borrow['financing_receipt_sha256'])
                borrow_bps = _number(borrow['cost_bps'], nonnegative=True)
            metrics = score_leg({'side': side, 'quote': entry}, exit_quote, index_bps/100,
                fees_bps=fees, slippage_bps=slippage, borrow_bps=borrow_bps)
            scored.append({'ticker': ticker, 'side': side, 'weight': weight,
                'sector': leg['sector'], 'industry': leg['industry'],
                'net_bps': metrics['net_pct']*100, 'gross_bps': metrics['gross_pct']*100,
                'tide_bps': metrics['tide_pct']*100,
                'selection_net_bps': metrics['selection_net_pct']*100,
                'round_trip_spread_bps': metrics['round_trip_spread_bps']})
        portfolio = {'state': state, 'legs': scored, 'turnover': 2*sum(x['weight'] for x in scored),
            **{key: sum(x['weight']*x[key] for x in scored)
               for key in ('net_bps', 'gross_bps', 'tide_bps', 'selection_net_bps')}}
        for key in ('turnover', 'net_bps', 'gross_bps', 'tide_bps', 'selection_net_bps'):
            _number(portfolio[key])
        return portfolio
    except (ValueError, TypeError, KeyError, OverflowError, AttributeError) as exc:
        reason = str(exc) if isinstance(exc, ValueError) and re.fullmatch(r'[A-Z_]+', str(exc)) else type(exc).__name__
        return {**missing, 'reason': reason[:100]}


def estimate(values):
    """Moving block bootstrap with missing calendar slots retained as None."""
    x = np.asarray([np.nan if v is None else _number(v) for v in values], dtype=float)
    finite = x[np.isfinite(x)]
    out = {'status': 'UNAVAILABLE', 'complete_sessions': len(finite), 'calendar_slots': len(x),
           'descriptive_mean_difference_bps': float(finite.mean()) if len(finite) else None,
           'se_bps': None, 'ci95_bps': None, 'mde80_bps': None, 'adjusted_lower_bps': None,
           'block_sessions': BLOCK, 'draws': DRAWS, 'seed': SEED, 'alpha_claim': None}
    blocks = np.asarray([x[i:i+BLOCK] for i in range(max(0, len(x)-BLOCK+1))
                         if np.isfinite(x[i:i+BLOCK]).all()])
    if not len(blocks):
        return {**out, 'reason': 'NO_COMPLETE_FIVE_SESSION_BLOCK'}
    rng = np.random.default_rng(SEED)
    samples = blocks[rng.integers(0, len(blocks), size=(DRAWS, math.ceil(len(finite)/BLOCK)))]
    means = samples.reshape(DRAWS, -1)[:, :len(finite)].mean(axis=1)
    se = float(means.std(ddof=1))
    center = out['descriptive_mean_difference_bps']
    if len(blocks) == 1 or np.ptp(finite) == 0 or not math.isfinite(se) or se <= 0:
        return {**out, 'status': 'DEGENERATE', 'valid_blocks': len(blocks),
                'reason': 'UNCERTAINTY_UNAVAILABLE_WITHOUT_OBSERVED_BLOCK_VARIATION'}
    return {**out, 'status': 'DESCRIPTIVE', 'valid_blocks': len(blocks),
            'se_bps': se, 'ci95_bps': [float(v) for v in np.quantile(means, [.025, .975])],
            'mde80_bps': (Z+POWER_Z)*se, 'adjusted_lower_bps': center-Z*se,
            'controls': {'scope': 'ENGINEERING_ONLY; centered or planted session differences',
                'placebo_expected_bps': 0., 'placebo_observed_bps': float((finite-center).mean()),
                'positive_control_expected_bps': 5.,
                'positive_control_observed_bps': float((finite-center+5).mean()),
                'positive_control_detectable': bool(se > 0 and 5 >= (Z+POWER_Z)*se)}}


def _summary(rows):
    valid = [row for row in rows if row['state'] != 'UNAVAILABLE']
    traded = [row for row in valid if row['state'] == 'TRADE']
    legs = [leg for row in traded for leg in row['legs']]
    exposure = {}
    maximum_common = 0.
    for row in traded:
        common = {}
        for leg in row['legs']:
            key = leg['side']+' / '+leg['sector']
            exposure[key] = exposure.get(key, 0.)+leg['weight']
            common[key] = common.get(key, 0.)+leg['weight']
        maximum_common = max(maximum_common, max(common.values(), default=0.))
    wealth, peak, drawdown = 1., 1., 0.
    for row in valid:
        wealth *= 1+row['net_bps']/10000
        if wealth <= 0:
            drawdown = None
            break
        peak = max(peak, wealth)
        drawdown = max(drawdown, (peak-wealth)/peak)
    return {'calendar_sessions': len(rows), 'complete_sessions': len(valid),
        'trade_sessions': len(traded), 'abstain_sessions': sum(r['state'] == 'ABSTAIN' for r in rows),
        'unavailable_sessions': len(rows)-len(valid),
        'participation_all_sessions': len(traded)/len(rows) if rows else None,
        'scored_legs': len(legs), 'net_leg_hit_rate': sum(x['net_bps'] > 0 for x in legs)/len(legs) if legs else None,
        'net_active_session_hit_rate': sum(x['net_bps'] > 0 for x in traded)/len(traded) if traded else None,
        'mean_turnover_original_capacity': sum(r['turnover'] for r in valid)/len(valid) if valid else None,
        'max_drawdown_pct': drawdown*100 if drawdown is not None and len(valid) == len(rows) and rows else None,
        'drawdown_status': 'COMPLETE_WINDOW' if len(valid) == len(rows) and drawdown is not None and rows else 'UNAVAILABLE',
        'mean_common_exposure': {k: v/len(valid) for k, v in sorted(exposure.items())} if valid else {},
        'maximum_same_side_sector_weight': maximum_common if valid else None,
        'missingness': [{'session': row['session'], 'reason': row.get('reason', 'UNAVAILABLE')}
                        for row in rows if row['state'] == 'UNAVAILABLE'],
        **{'mean_'+key: sum(r[key] for r in valid)/len(valid) if valid else None
           for key in ('gross_bps', 'net_bps', 'tide_bps', 'selection_net_bps')}}


def evaluate(panel, *, as_of=None):
    """Return explicit unavailable/underpowered evidence; never choose or adopt."""
    now = _stamp(as_of or dt.datetime.now(ET))
    out = {'schema_version': 1, 'registration': REGISTRATION, 'adopted': False,
           'status': 'UNAVAILABLE', 'alpha_claim': None,
           'label': 'Forward research; BBO crossing proxy with measured costs; no adoption',
           'source_custody': 'Selection hash and chronology checked; provider receipt custody not independently authenticated.'}
    try:
        if not isinstance(panel, dict) or panel.get('schema_version') != 1 or panel.get('evidence_mode') not in ('FORWARD', 'SIMULATED'):
            raise ValueError('EXPLICIT_EVIDENCE_MODE_REQUIRED')
        exp = panel['experiment']
        if exp.get('registration') != REGISTRATION:
            raise ValueError('REGISTRATION_MISMATCH')
        configs = exp['arm_configs']
        baseline, challenger = exp['baseline'], exp['challenger']
        if (not isinstance(configs, dict) or not 2 <= len(configs) <= 16 or baseline == challenger
                or baseline not in configs or challenger not in configs
                or any(not isinstance(name, str) or not name for name in configs)):
            raise ValueError('REGISTERED_ARMS_REQUIRED')
        for hash_value in configs.values():
            _hash(hash_value)
        prior = exp['preserved_prior_arms']
        if (not isinstance(prior, list) or len(set(prior)) != len(prior) or len(prior) < 3
                or any(name not in configs or name in (baseline, challenger) for name in prior)):
            raise ValueError('OLDER_RESEARCH_ARMS_MUST_REMAIN_REGISTERED')
        if exp['benchmark_ticker'] not in ('XIU.TO', '^GSPTSE'):
            raise ValueError('REGISTERED_TSX_BENCHMARK_REQUIRED')
        from intraday_history import session_schedule
        schedule = session_schedule(exp['start_session'], exp['end_session'])
        dates = [str(d.date()) for d in schedule.index]
        if not dates or len(dates) > 5000 or exp['start_session'] != dates[0] or exp['end_session'] != dates[-1]:
            raise ValueError('EXACT_EXCHANGE_SESSION_WINDOW_REQUIRED')
        if _stamp(exp['registered_at']).date() >= dt.date.fromisoformat(dates[0]):
            raise ValueError('FORWARD_REGISTRATION_REQUIRED')
        if dt.date.fromisoformat(dates[-1]) > now.date():
            raise ValueError('FUTURE_EVALUATION_WINDOW')
        raw_sessions = panel['sessions']
        if not isinstance(raw_sessions, list):
            raise ValueError('SESSION_RECORDS_REQUIRED')
        by_date = {}
        for row in raw_sessions:
            if not isinstance(row, dict) or row.get('session') not in dates or row['session'] in by_date:
                raise ValueError('DUPLICATE_OR_OUTSIDE_SESSION')
            if not isinstance(row.get('arms'), dict) or set(row['arms'])-set(configs):
                raise ValueError('UNREGISTERED_ARM')
            by_date[row['session']] = row
        frozen = _stamp(exp['confirmation_frozen_at'])
        cutoff = (dt.datetime.combine(dt.date.fromisoformat(dates[DEVELOPMENT]), dt.time(9, 30), ET)
                  if len(dates) > DEVELOPMENT else None)
        confirmation_locked = cutoff is not None and _stamp(exp['registered_at']) <= frozen < cutoff
        evaluated = {name: [] for name in configs}
        for day, (_, calendar) in zip(dates, schedule.iterrows()):
            full = calendar['market_close'].to_pydatetime().astimezone(ET).time() >= dt.time(16)
            records = by_date.get(day, {}).get('arms', {})
            for name in configs:
                evaluated[name].append({'session': day,
                    **_arm(day, name, records.get(name), exp, now, full)})
        comparisons = {}
        for name in configs:
            if name == baseline:
                continue
            values = [(arm['net_bps']-base['net_bps'])
                if arm['net_bps'] is not None and base['net_bps'] is not None else None
                for base, arm in zip(evaluated[baseline], evaluated[name])]
            comparisons[name] = {'all_sessions': estimate(values),
                'development': estimate(values[:DEVELOPMENT]),
                'confirmation': estimate(values[DEVELOPMENT:]),
                'matched_sessions': sum(x is not None for x in values),
                'missing_sessions': [day for day, value in zip(dates, values) if value is None]}
        primary = comparisons[challenger]
        floor = (primary['development']['complete_sessions'] >= DEVELOPMENT
                 and primary['confirmation']['complete_sessions'] >= CONFIRMATION
                 and confirmation_locked)
        quarters = sorted({day[:4]+'Q'+str((int(day[5:7])-1)//3+1) for day in dates})
        status = ('EVIDENCE_ONLY' if floor else 'UNDERPOWERED') if primary['matched_sessions'] else 'UNAVAILABLE'
        if panel['evidence_mode'] == 'SIMULATED':
            status = 'SIMULATED_ENGINEERING_ONLY'
        return {**out, 'status': status, 'evidence_mode': panel['evidence_mode'],
            'session_window': {'start': dates[0], 'end': dates[-1], 'slots': len(dates),
                'development_slots': min(DEVELOPMENT, len(dates)),
                'confirmation_slots': max(0, len(dates)-DEVELOPMENT)},
            'confirmation_locked_before_open': confirmation_locked,
            'minimum_forward_floor_met': floor and panel['evidence_mode'] == 'FORWARD',
            'arm_count': len(configs), 'registered_comparison_count': len(configs)-1,
            'multiplicity_threshold': Z, 'summaries': {k: _summary(v) for k, v in evaluated.items()},
            'comparisons': comparisons, 'sessions': evaluated,
            'robustness': {'observed_calendar_quarters': quarters,
                'four_quarter_performance_verified': False, 'two_market_performance_verified': False,
                'status': 'UNESTABLISHED; one TSX panel does not satisfy independent market robustness'},
            'claim': 'Descriptive evidence only. No numerical alpha claim or automatic strategy adoption.'}
    except (ValueError, TypeError, KeyError, OverflowError, AttributeError) as exc:
        reason = str(exc) if isinstance(exc, ValueError) and re.fullmatch(r'[A-Z_]+', str(exc)) else type(exc).__name__
        return {**out, 'reason': reason[:100]}
