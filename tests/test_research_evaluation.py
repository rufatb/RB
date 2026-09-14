"""Synthetic execution fixtures test accounting/controls, never market alpha."""
import copy
import datetime as dt
import hashlib
import math

import pytest

import research_evaluation as R
from intraday_history import session_schedule

ARMS = ('baseline', 'expanded', 'H1', 'H2', 'watchlist')


def sha(value):
    return hashlib.sha256(value.encode()).hexdigest()


def clock(day, time):
    return dt.datetime.fromisoformat(day+'T'+time).replace(tzinfo=R.ET).isoformat()


def decision(day, arm, state='TRADE', gross_bps=0., side='LONG'):
    def quote(mid, time):
        return {'ticker': 'NA.TO', 'currency': 'CAD', 'bid': mid-.01, 'ask': mid+.01,
                'quote_time': clock(day, time), 'source_url': 'https://example.test/quote',
                'source_receipt_sha256': sha(day+time)}
    record = {'state': state, 'reason': 'Evaluated threshold not cleared' if state == 'ABSTAIN' else None,
        'decision': {'recorded_at': clock(day, '09:46:00'), 'input_as_of': clock(day, '09:45:59'),
            'membership_as_of': clock(day, '08:15:00'), 'config_sha256': sha(arm),
            'input_sha256': sha(day+arm), 'membership_sha256': sha(day+'membership')},
        'legs': []}
    if state == 'TRADE':
        leg = {'ticker': 'NA.TO', 'side': side, 'weight': 1., 'sector': 'Financials',
               'industry': 'Banks', 'entry': quote(100., '09:46:01'),
               'exit': quote(100*(1+gross_bps/10000), '15:59:00'),
               'costs': {'measured': True, 'fees_bps': 1., 'slippage_bps': .5,
                         'recorded_at': clock(day, '16:00:00'), 'receipt_sha256': sha(day+'costs')}}
        if side == 'SHORT':
            leg['borrow'] = {'available': True, 'available_at': clock(day, '09:45:00'),
                'cost_bps': .25, 'availability_sha256': sha(day+'availability'),
                'financing_receipt_sha256': sha(day+'financing')}
        record['legs'] = [leg]
        record['benchmark'] = {'ticker': 'XIU.TO', 'currency': 'CAD', 'return_bps': 0.,
            'entry_time': '09:46', 'exit_time': '15:59', 'observed_at': clock(day, '15:59:01'),
            'source_url': 'https://example.test/benchmark', 'receipt_sha256': sha(day+'index')}
    record['decision']['selection_sha256'] = R.selection_hash(day, arm, record)
    return record


def panel(n=12, delta=lambda i: 0., mode='SIMULATED'):
    schedule = session_schedule('2026-09-15', '2027-06-30').iloc[:n]
    days = [str(d.date()) for d in schedule.index]
    states = ['TRADE' if row['market_close'].tz_convert(R.ET).time() >= dt.time(16) else 'ABSTAIN'
              for _, row in schedule.iterrows()]
    sessions = [{'session': day, 'arms': {arm: decision(day, arm, state=states[i], gross_bps=delta(i) if arm == 'expanded' else 0.)
                                         for arm in ARMS}} for i, day in enumerate(days)]
    result = {'schema_version': 1, 'evidence_mode': mode,
        'experiment': {'registration': R.REGISTRATION, 'registered_at': '2026-09-14T17:00:00-04:00',
            'confirmation_frozen_at': '2026-09-14T17:01:00-04:00', 'start_session': days[0],
            'end_session': days[-1], 'baseline': 'baseline', 'challenger': 'expanded',
            'arm_configs': {arm: sha(arm) for arm in ARMS},
            'preserved_prior_arms': ['H1', 'H2', 'watchlist'], 'benchmark_ticker': 'XIU.TO'},
        'sessions': sessions}
    return result, clock(days[-1], '16:05:00')


def test_cost_accounting_cash_and_missing_data_have_distinct_denominators():
    data, now = panel(12)
    days = [r['session'] for r in data['sessions']]
    data['sessions'][0]['arms']['expanded'] = decision(days[0], 'expanded', state='ABSTAIN')
    del data['sessions'][1]['arms']['expanded']['legs'][0]['costs']['slippage_bps']
    del data['sessions'][2]['arms']['expanded']
    original = copy.deepcopy(data)
    result = R.evaluate(data, as_of=now)
    assert data == original
    summary = result['summaries']['expanded']
    assert summary['complete_sessions'] == 10 and summary['unavailable_sessions'] == 2
    assert summary['trade_sessions'] == 9 and summary['abstain_sessions'] == 1
    assert summary['participation_all_sessions'] == .75
    assert summary['mean_net_bps'] == pytest.approx(-3.5*.9)
    assert summary['mean_turnover_original_capacity'] == pytest.approx(1.8)
    assert summary['max_drawdown_pct'] is None
    rows = result['sessions']['expanded']
    assert rows[0]['net_bps'] == 0 and rows[1]['net_bps'] is None and rows[2]['net_bps'] is None
    assert result['comparisons']['expanded']['matched_sessions'] == 10
    assert result['comparisons']['expanded']['missing_sessions'] == days[1:3]


@pytest.mark.parametrize('damage,reason', [
    ('selection', 'SELECTION_SEAL_MISMATCH'), ('late', 'POINT_IN_TIME_DECISION_REQUIRED'),
    ('missing_exit', 'KeyError'), ('unmeasured', 'MEASURED_COST_RECEIPT_REQUIRED'),
    ('borrow', 'SHORT_AVAILABILITY_RECEIPT_REQUIRED'),
    ('benchmark', 'REGISTERED_BENCHMARK_REQUIRED'),
    ('benchmark_clock', 'EXACT_WINDOW_BENCHMARK_REQUIRED'),
    ('weight_overflow', 'FINITE_NUMBER_REQUIRED'),
])
def test_unverifiable_leg_invalidates_whole_session_without_replacing_it(damage, reason):
    data, now = panel(6)
    day = data['sessions'][0]['session']
    arm = decision(day, 'expanded', gross_bps=20., side='SHORT')
    if damage == 'selection':
        arm['legs'][0]['weight'] = .5
    elif damage == 'late':
        arm['decision']['recorded_at'] = clock(day, '10:00:00')
        arm['decision']['selection_sha256'] = R.selection_hash(day, 'expanded', arm)
    elif damage == 'missing_exit':
        del arm['legs'][0]['exit']
    elif damage == 'unmeasured':
        arm['legs'][0]['costs']['measured'] = False
    elif damage == 'borrow':
        arm['legs'][0]['borrow']['available'] = False
    elif damage == 'benchmark':
        arm['benchmark']['ticker'] = 'SPY'
    elif damage == 'benchmark_clock':
        arm['benchmark']['observed_at'] = clock(day, '16:00:00')
    else:
        arm['legs'][0]['weight'] = 1e308
        arm['decision']['selection_sha256'] = R.selection_hash(day, 'expanded', arm)
    data['sessions'][0]['arms']['expanded'] = arm
    result = R.evaluate(data, as_of=now)
    row = result['sessions']['expanded'][0]
    assert row['state'] == 'UNAVAILABLE' and row['reason'] == reason
    assert row['net_bps'] is None and row['legs'] == []
    assert result['comparisons']['expanded']['matched_sessions'] == 5


def test_window_includes_absent_sessions_and_never_moves_development_boundary():
    data, now = panel(121, delta=lambda i: 2+math.sin(i), mode='FORWARD')
    missing = data['sessions'].pop(12)['session']
    result = R.evaluate(data, as_of=now)
    comparison = result['comparisons']['expanded']
    assert comparison['matched_sessions'] == 120
    assert comparison['development']['complete_sessions'] == 59
    assert comparison['confirmation']['complete_sessions'] == 61
    assert result['status'] == 'UNDERPOWERED' and not result['minimum_forward_floor_met']
    assert missing in comparison['missing_sessions']
    assert result['session_window']['development_slots'] == 60
    assert result['adopted'] is False and result['alpha_claim'] is None


def test_full_pipeline_positive_control_and_placebo_never_claim_market_alpha():
    positive, now = panel(120, delta=lambda i: 20+math.sin(i/3), mode='FORWARD')
    result = R.evaluate(positive, as_of=now)
    assert result['status'] == 'EVIDENCE_ONLY' and result['minimum_forward_floor_met']
    stats = result['comparisons']['expanded']['confirmation']
    assert stats['adjusted_lower_bps'] > 0 and stats['se_bps'] > 0
    assert stats['mde80_bps'] == pytest.approx((3.5+.8416212336)*stats['se_bps'])
    assert stats['controls']['positive_control_detectable'] is True
    assert stats['controls']['positive_control_observed_bps'] == pytest.approx(5.)
    assert stats['controls']['placebo_observed_bps'] == pytest.approx(0., abs=1e-12)
    assert result['registered_comparison_count'] == 4
    assert set(result['comparisons']) == {'expanded', 'H1', 'H2', 'watchlist'}
    assert result['summaries']['expanded']['maximum_same_side_sector_weight'] == 1.
    assert result['summaries']['baseline']['max_drawdown_pct'] > 0
    assert result['robustness']['two_market_performance_verified'] is False
    assert not result['adopted'] and result['alpha_claim'] is None
    # Identical arms have exactly zero paired gain; no lucky selection creates it.
    placebo, now = panel(120)
    placebo_result = R.evaluate(placebo, as_of=now)
    placebo_stats = placebo_result['comparisons']['expanded']['all_sessions']
    assert placebo_stats['descriptive_mean_difference_bps'] == pytest.approx(0.)
    assert placebo_stats['status'] == 'DEGENERATE'
    assert all(placebo_stats[key] is None for key in ('se_bps', 'ci95_bps', 'mde80_bps', 'adjusted_lower_bps'))
    assert placebo_result['status'] == 'SIMULATED_ENGINEERING_ONLY'
    assert placebo_result['minimum_forward_floor_met'] is False


def test_confirmation_cannot_be_relabelled_untouched_after_it_started():
    data, now = panel(120, mode='FORWARD')
    data['experiment']['confirmation_frozen_at'] = clock(data['sessions'][61]['session'], '08:00:00')
    result = R.evaluate(data, as_of=now)
    assert result['status'] == 'UNDERPOWERED'
    assert result['confirmation_locked_before_open'] is False
    assert not result['minimum_forward_floor_met']
    data['experiment']['preserved_prior_arms'] = []
    assert R.evaluate(data, as_of=now)['reason'] == 'OLDER_RESEARCH_ARMS_MUST_REMAIN_REGISTERED'


def test_blocks_never_bridge_missing_sessions_and_repeated_runs_are_deterministic():
    for constant in ([2.]*20, [1., 2., 3., 4., 5.]):
        degenerate = R.estimate(constant)
        assert degenerate['status'] == 'DEGENERATE'
        assert degenerate['mde80_bps'] is None and degenerate['ci95_bps'] is None
    interrupted = [1., 2., 3., 4., None, 6., 7., 8., 9.]
    assert R.estimate(interrupted)['reason'] == 'NO_COMPLETE_FIVE_SESSION_BLOCK'
    values = [math.sin(i/2) for i in range(25)]+[None]+[math.cos(i/2) for i in range(25)]
    first = R.estimate(values)
    assert first == R.estimate(values)
    assert first['valid_blocks'] == 42 and first['complete_sessions'] == 50
    assert first['block_sessions'] == 5 and first['draws'] == 2000 and first['seed'] == 101
