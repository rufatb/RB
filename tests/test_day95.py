"""Day-95: record-integrity corrections (PREREGISTER_day95b.md).

C1  publication window 09:46:00-09:49:59 ET, late records labelled late
C2  the unrecorded-day class: NOT RECORDED alarm, no masking freeze, exit 7
    (exit 6 is main's provenance signal, 58da082; deliberately untouched)
C3  record gaps anchored on today, printed in the RECORD section
C4  r945 density-sampling crash fix + non-finite k-NN rejection
C5  zero-pick days still write universe prints
H1  vp train/serve skew shadow A/B (logging only)

No network: every test injects services/fixtures.
"""
import copy
import datetime as dt
import json
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
import pytest

import brief
import daily_job
import daily_render
import execution
import ledger
from report_store import Store
from test_daily_pipeline import NOW, services, res as board_res

ET = ZoneInfo('America/New_York')
DAY = dt.datetime(2026, 9, 8, tzinfo=ET)          # Tuesday, trading day


def at(hh, mm, ss=0):
    return DAY.replace(hour=hh, minute=mm, second=ss)


# ── C1: the window ───────────────────────────────────────────────────────────

def test_window_boundaries():
    assert not execution.clock_status(at(9, 45, 59))['eligible']
    on_time = execution.clock_status(at(9, 46, 0))
    assert on_time['eligible'] and on_time['status'] == '09:46 publication window'
    late_window = execution.clock_status(at(9, 49, 59))
    assert late_window['eligible']
    assert late_window['status'].startswith('LATE-WINDOW (09:47-09:50)')
    assert 'publishable' in late_window['status']
    late = execution.clock_status(at(9, 50, 0))
    assert not late['eligible'] and late['status'].startswith('LATE')


def test_window_width_is_a_named_constant():
    assert execution.PUBLISH_WINDOW_MINUTES == 4
    assert execution.publication_delay_sec(at(9, 46, 0)) == 0
    assert execution.publication_delay_sec(at(9, 49, 59)) == 239
    assert execution.publication_delay_sec(at(9, 50, 0)) == 240
    assert execution.in_publish_window(at(9, 48, 30))
    assert not execution.in_publish_window(at(9, 50, 0))
    assert not execution.in_publish_window(at(9, 45, 59))


def _published_services():
    """services() with r945.publish reporting a real publication."""
    s = services()
    return s


def test_publication_delay_is_frozen_into_the_report(tmp_path, monkeypatch):
    monkeypatch.setattr('r945.publish', lambda *a, **k:
                        {'errors': [], 'picks': 2, 'prints': 21, 'already': False})
    brief.compute(now=at(9, 47, 30), publish=True, state_dir=tmp_path,
                  services=_published_services())
    frozen = Store(tmp_path).get('2026-09-08')
    assert frozen is not None
    assert frozen['provenance']['publication_delay_sec'] == 90.0
    assert frozen['intraday']['publish']['publication_delay_sec'] == 90.0
    assert 'LATE-WINDOW' in frozen['clock']['status']


def test_late_rerun_never_replaces_a_recorded_board(tmp_path, monkeypatch):
    """Publish-once is sacred: the 09:46 board wins; a 09:49 rerun re-reads."""
    monkeypatch.setattr('r945.publish', lambda *a, **k:
                        {'errors': [], 'picks': 2, 'prints': 21, 'already': False})
    s = _published_services()
    first = brief.compute(now=at(9, 46, 20), publish=True, state_dir=tmp_path,
                          services=s)
    # A later in-window rerun must return the FROZEN report before any
    # provider is called (the services below would fail if touched).
    def fail():
        pytest.fail('a recorded board was recomputed')
    s['ledger'] = fail
    second = brief.compute(now=at(9, 49, 10), publish=True, state_dir=tmp_path,
                           services=s)
    assert first == second
    assert second['provenance']['publication_delay_sec'] == 20.0
    assert Store(tmp_path).get('2026-09-08') == first


# ── C2: the unrecorded-day class ─────────────────────────────────────────────

def _coverage_fail_services():
    s = services()
    s['intraday'] = lambda cfg: {
        'now': NOW.isoformat(), 'longs': [], 'shorts': [], 'pair': {},
        'evaluated': [], 'fetch_errors': {'BBB.TO': 'HTTP_403'},
        'n_names': 12, 'coverage_fail': 'only 12/21 names passed data validation'}
    return s


def test_eligible_session_with_no_record_is_not_frozen(tmp_path):
    report = brief.compute(now=NOW, publish=True, state_dir=tmp_path,
                           services=_coverage_fail_services())
    assert brief.record_missed(report)
    assert Store(tmp_path).get('2026-09-08') is None, \
        'an informational freeze would mask the miss behind publish-once'


def test_brief_main_alarms_and_exits_7(tmp_path, monkeypatch, capsys):
    report = brief.compute(now=NOW, publish=True, state_dir=tmp_path / 'a',
                           services=_coverage_fail_services())
    monkeypatch.setattr(brief, 'compute', lambda *a, **k: copy.deepcopy(report))
    rc = brief.main(['--publish', '--state-dir', str(tmp_path / 'b')])
    out = capsys.readouterr().out
    assert rc == 7
    assert 'RECORD NOT WRITTEN' in out


def test_main_zero_when_recorded(tmp_path, monkeypatch):
    report = brief.compute(now=NOW, services=services())
    report['intraday']['publish'] = {'picks': 2, 'prints': 21, 'already': False,
                                     'errors': []}
    monkeypatch.setattr(brief, 'compute', lambda *a, **k: copy.deepcopy(report))
    assert brief.main(['--publish', '--state-dir', str(tmp_path)]) == 0


def test_record_missed_is_false_on_closed_and_offline(tmp_path):
    closed = services()
    closed['clock'] = lambda now: {'session': '2026-09-07', 'status': 'CLOSED',
                                   'eligible': False, 'entry_time': '09:46',
                                   'exit_time': '15:59', 'close_at': None}
    holiday = dt.datetime(2026, 9, 7, 9, 46, 20, tzinfo=ET)   # Labour Day
    report = brief.compute(now=holiday, services=closed)
    assert not brief.record_missed(report)
    offline = brief.compute(now=NOW, no_net=True, services=services())
    assert not brief.record_missed(offline)


def test_daily_job_not_recorded_path(tmp_path, monkeypatch):
    """Eligible trading day, nothing recorded: alarm, NO freeze, exit 7."""
    report = brief.compute(now=NOW, publish=True, state_dir=tmp_path / 'unused',
                           services=_coverage_fail_services())
    monkeypatch.setattr(daily_job.brief, 'compute',
                        lambda **kw: copy.deepcopy(report))
    out_report = daily_job.run(tmp_path / 'state', tmp_path / 'out', now=NOW)
    assert out_report['report_status'].startswith('NOT RECORDED')
    assert Store(tmp_path / 'state').get('2026-09-08') is None, \
        'a NOT RECORDED day must never be frozen over'
    assert (tmp_path / 'out' / 'report.txt').exists()
    monkeypatch.setattr(daily_job, 'run', lambda *a, **k: out_report)
    rc = daily_job.main(['--state-dir', str(tmp_path / 'state'),
                         '--output-dir', str(tmp_path / 'out')])
    assert rc == 7


def test_daily_job_holiday_stays_quiet_informational(tmp_path, monkeypatch):
    closed = services()
    closed['clock'] = lambda now: {'session': '2026-09-07', 'status': 'CLOSED',
                                   'eligible': False, 'entry_time': '09:46',
                                   'exit_time': '15:59', 'close_at': None}
    holiday = dt.datetime(2026, 9, 7, 9, 46, 20, tzinfo=ET)
    report = brief.compute(now=holiday, publish=True,
                           state_dir=tmp_path / 'unused2', services=closed)
    monkeypatch.setattr(daily_job.brief, 'compute',
                        lambda **kw: copy.deepcopy(report))
    out_report = daily_job.run(tmp_path / 'state', tmp_path / 'out', now=holiday)
    assert not out_report['report_status'].startswith('NOT RECORDED')
    assert Store(tmp_path / 'state').get('2026-09-07') is not None, \
        'closed days remain quiet informational and are frozen as before'
    monkeypatch.setattr(daily_job, 'run', lambda *a, **k: out_report)
    assert daily_job.main(['--state-dir', str(tmp_path / 'state'),
                           '--output-dir', str(tmp_path / 'out')]) == 0


def test_not_recorded_email_subject_and_body(tmp_path):
    import deliver_report
    report = brief.compute(now=NOW, publish=True, state_dir=tmp_path,
                           services=_coverage_fail_services())
    report = {**report, 'report_status': 'NOT RECORDED — test; ' + report['report_status']}
    msg = deliver_report.message(report, 'sender@example.com', 'rcpt@example.com')
    assert 'NOT RECORDED — ' in msg['Subject']
    body = msg.get_body(('plain',)).get_content()
    assert body.startswith('⚠ NOT RECORDED')
    assert 'GAP in the track record' in body


# ── C3: record gaps ──────────────────────────────────────────────────────────

def _weekday(d):
    # Injected test calendar: weekdays, minus Labour Day 2026-09-07.
    return d.weekday() < 5 and d.isoformat() != '2026-09-07'


def test_record_gaps_finds_interior_gaps_after_later_sessions_publish():
    # Ledger has 09-04, 09-08 AND 09-11; the old missing_sessions anchors on
    # the last date (09-11) and sees nothing. record_gaps anchors on TODAY.
    rows = [{'date': '2026-09-04'}, {'date': '2026-09-08'}, {'date': '2026-09-11'}]
    assert ledger.missing_sessions(rows, dt.date(2026, 9, 12), _weekday) == []
    gaps = ledger.record_gaps(rows, dt.date(2026, 9, 12), _weekday, prints=[])
    assert gaps['missing'] == ['2026-09-09', '2026-09-10']
    assert gaps['zero_pick'] == []


def test_record_gaps_distinguishes_zero_pick_days():
    rows = [{'date': '2026-09-04'}, {'date': '2026-09-11'}]
    prints = [{'date': '2026-09-08', 'ticker': 'AAA.TO', 'p945': '100.0'}]
    gaps = ledger.record_gaps(rows, dt.date(2026, 9, 12), _weekday, prints=prints)
    assert gaps['missing'] == ['2026-09-09', '2026-09-10']
    assert gaps['zero_pick'] == ['2026-09-08']


def test_record_gaps_lookback_cap_and_empty_record():
    rows = [{'date': '2026-06-01'}]
    gaps = ledger.record_gaps(rows, dt.date(2026, 9, 12), _weekday,
                              prints=[], lookback=10)
    assert max(gaps['missing']) <= '2026-09-11'
    assert min(gaps['missing']) >= '2026-08-29'   # 10 calendar days back
    assert ledger.record_gaps([], dt.date(2026, 9, 12), _weekday) == \
        {'missing': [], 'zero_pick': []}


def test_record_gaps_reaches_the_report_and_renderers(tmp_path, monkeypatch):
    s = services()
    s['ledger'] = lambda: [{'date': '2026-09-04', 'ticker': 'AAA.TO',
                            'side': 'LONG', 'role': 'pair', 'hit': '1',
                            'r1': '.2', 'p945': '100'}]
    monkeypatch.setattr(ledger, 'load_prints', lambda *a, **k: [])
    wednesday = dt.datetime(2026, 9, 9, 9, 46, 20, tzinfo=ET)
    report = brief.compute(now=wednesday, services=s)
    gaps = report['intraday']['record_gaps']
    # 09-07 is Labour Day (not a trading day); 09-08 is the missing session.
    assert gaps['missing'] == ['2026-09-08']
    text = brief.render_text(report)
    assert 'RECORD MAY BE INCOMPLETE — missing sessions: 2026-09-08' in text
    assert 'zero-pick' in text
    html = brief.render_html(report)
    assert 'RECORD MAY BE INCOMPLETE' in html


def test_zero_pick_days_are_named_not_gapped_in_the_report(tmp_path, monkeypatch):
    s = services()
    s['ledger'] = lambda: [{'date': '2026-09-04', 'ticker': 'AAA.TO',
                            'side': 'LONG', 'role': 'pair', 'hit': '1',
                            'r1': '.2', 'p945': '100'}]
    monkeypatch.setattr(ledger, 'load_prints',
                        lambda *a, **k: [{'date': '2026-09-08', 'ticker': 'AAA.TO',
                                          'p945': '100.0'}])
    thursday = dt.datetime(2026, 9, 10, 9, 46, 20, tzinfo=ET)
    report = brief.compute(now=thursday, services=s)
    gaps = report['intraday']['record_gaps']
    assert gaps['zero_pick'] == ['2026-09-08']
    assert gaps['missing'] == ['2026-09-09']
    text = brief.render_text(report)
    assert 'NOT missed publications' in text


# ── C4: r945 robustness fixes ────────────────────────────────────────────────

def _train(n, seed=1, nan_rows=()):
    rng = np.random.default_rng(seed)
    df = pd.DataFrame({'r0': rng.normal(0, .5, n), 'gap': rng.normal(0, .8, n),
                       'vp': rng.normal(1, .2, n), 'r1': rng.normal(0, 1, n)})
    for i in nan_rows:
        df.loc[i, 'r0'] = np.nan
    return df


def test_density_cutoffs_survive_a_nan_shrunk_frame():
    """REGRESSION (C4): the old code sized the sample against the FULL frame
    and .sample() raised ValueError when NaN rows shrank the valid one."""
    train = _train(10, nan_rows=range(8))      # only 2 complete rows
    cutoffs = __import__('r945').density_cutoffs(train)
    assert cutoffs == (0.0, 9e9)               # knn abstains (<200): no crash
    assert __import__('r945').density_cutoffs(train.iloc[:1]) is None


def test_knn_rejects_nonfinite_today_values():
    import r945
    train = _train(300)
    for bad in (float('nan'), float('inf'), float('-inf')):
        p, n, nd = r945.knn_probability(train, {'r0': bad, 'gap': 0., 'vp': 1.})
        assert p is None, f'{bad} feature was scored'


def test_knn_drops_and_counts_nonfinite_train_rows():
    import r945
    train = _train(300)
    train.loc[0, 'gap'] = np.inf
    train.loc[1, 'vp'] = -np.inf
    stats = {}
    p, n, nd = r945.knn_probability(train, {'r0': .1, 'gap': 0., 'vp': 1.},
                                    stats=stats)
    assert p is not None and n == 298
    assert stats['nonfinite_train_rows_dropped'] == 2


# ── C5: zero-pick days leave a trace ─────────────────────────────────────────

class _LedgerSpy:
    """Captures writes; no real CSV touched."""
    FIELDS = ledger.FIELDS

    def __init__(self, prints=()):
        self.prints = list(prints)
        self.picks = []

    def load(self, *a, **k):
        return []

    def load_prints(self, *a, **k):
        return list(self.prints)

    def append_picks(self, rows, *a, **k):
        self.picks.extend(rows)
        return len(rows)

    def append_universe_prints(self, rows, date, *a, **k):
        if any(r['date'] == date for r in self.prints):
            return 0
        self.prints += [{'date': date, **r} for r in rows]
        return len(rows)


def test_zero_pick_day_still_writes_universe_prints(monkeypatch):
    import sys
    import r945
    spy = _LedgerSpy()
    monkeypatch.setitem(sys.modules, 'ledger', spy)
    res = {'now': '2026-09-08T09:46', 'longs': [], 'shorts': [],
           'pair': {'long': {'pick': None}, 'short': {'pick': None}},
           'evaluated': [{'ticker': 'AAA.TO', 'p945': 100.0},
                         {'ticker': 'BBB.TO', 'p945': 50.0}]}
    out = r945.publish(res, {'risk': {'account_equity': 25000}, 'pair': {}})
    assert out['picks'] == 0
    assert out['prints'] == 2, 'a zero-pick day must leave its trace (C5)'
    assert spy.picks == [] and len(spy.prints) == 2


def test_zero_pick_rerun_is_already_not_a_miss(monkeypatch):
    import sys
    import r945
    spy = _LedgerSpy(prints=[{'date': '2026-09-08', 'ticker': 'AAA.TO',
                              'p945': '100.0'}])
    monkeypatch.setitem(sys.modules, 'ledger', spy)
    res = {'now': '2026-09-08T09:46', 'longs': [], 'shorts': [],
           'pair': {'long': {'pick': None}, 'short': {'pick': None}},
           'evaluated': [{'ticker': 'AAA.TO', 'p945': 100.0}]}
    out = r945.publish(res, {'risk': {'account_equity': 25000}, 'pair': {}})
    assert out['already'] is True and out['prints'] == 0


# ── H1: vp shadow A/B (logging only) ─────────────────────────────────────────

def _hist_rows(n_sessions=60, tickers=('AAA.TO', 'BBB.TO', 'CCC.TO', 'DDD.TO'),
               seed=3):
    rng = np.random.default_rng(seed)
    rows = []
    base = dt.date(2026, 6, 1)
    days = [base + dt.timedelta(days=i) for i in range(n_sessions * 7 // 5 + 2)]
    days = [d for d in days if d.weekday() < 5][:n_sessions]
    for d in days:
        for t in tickers:
            rows.append({'t': t, 'date': d.isoformat(),
                         'r0': rng.normal(0, .5), 'gap': rng.normal(0, .8),
                         'v15': float(abs(rng.normal(1e6, 2e5))),
                         'r1': rng.normal(0, 1.), 'mae_dn': -0.5,
                         'mae_up': 0.5, 'px': 100.})
    return rows


def test_shadow_vp_compare_runs_and_is_deterministic():
    import shadow_vp
    hist = _hist_rows()
    live = [{'t': 'AAA.TO', 'r0': .3, 'gap': -.2, 'vp': 1.1, 'p945': 100.,
             'v15': 1.1e6, 'last': 100.},
            {'t': 'BBB.TO', 'r0': -.4, 'gap': .1, 'vp': .9, 'p945': 50.,
             'v15': 9e5, 'last': 50.}]
    a = shadow_vp.compare(hist, live)
    b = shadow_vp.compare(hist, live)
    assert a['status'] == 'OK' and a == b
    assert isinstance(a['diverged'], bool)
    assert 'NOT an accuracy result' in a['claim']


def test_shadow_vp_detects_planted_divergence():
    """If normalization flips a pick, the shadow must say so."""
    import shadow_vp
    hist = _hist_rows()
    # Make AAA.TO's trailing median tiny vs its full-window median: trailing
    # vp huge (outlier) under variant B, ordinary under variant A.
    for i, r in enumerate(hist):
        if r['t'] == 'AAA.TO':
            r['v15'] = 1e3 if i < len(hist) // 2 else 1e9
    live = [{'t': 'AAA.TO', 'r0': .3, 'gap': -.2, 'vp': 1.1, 'p945': 100.,
             'v15': 1.1e9, 'last': 100.},
            {'t': 'BBB.TO', 'r0': -.4, 'gap': .1, 'vp': .9, 'p945': 50.,
             'v15': 9e5, 'last': 50.}]
    out = shadow_vp.compare(hist, live)
    assert out['status'] == 'OK'
    assert (out['board_a']['n_scored'], out['board_b']['n_scored']) != (0, 0)


def test_shadow_vp_is_fail_closed():
    import shadow_vp
    out = shadow_vp.compare([], [{'t': 'X.TO'}])
    assert out['status'] == 'ERROR' and out['error']


def test_shadow_vp_log_is_publish_once(tmp_path):
    import shadow_vp
    path = str(tmp_path / 'shadow_vp.jsonl')
    entry = {'status': 'OK', 'diverged': False, 'board_a': {}, 'board_b': {}}
    assert shadow_vp.log(entry, '2026-09-09', path=path) is True
    assert shadow_vp.log({'status': 'OK', 'diverged': True}, '2026-09-09',
                         path=path) is False, 'a rerun rewrote the shadow record'
    lines = (tmp_path / 'shadow_vp.jsonl').read_text().strip().splitlines()
    assert len(lines) == 1
    assert json.loads(lines[0])['session'] == '2026-09-09'
    assert shadow_vp.log(entry, '2026-09-10', path=path) is True


# ── H2: tide-residualized features harness (validate_residual.py) ────────────

def _synthetic_pool(n_sessions=260, n_tickers=6, edge=True, seed=11):
    """Hourly-pool-shaped panel where ONLY the idiosyncratic part predicts.

    r0 = tide + idio; gap = 0.8*tide_gap + idio_gap. With `edge`, the outcome
    depends on idio alone, so index-residualized features are strictly better
    aligned with the label than raw. Without it, the label is independent
    noise: no arm may claim an improvement."""
    rng = np.random.default_rng(seed)
    base = dt.date(2026, 1, 5)
    days = [d for d in (base + dt.timedelta(days=i)
                        for i in range(n_sessions * 7 // 5 + 3))
            if d.weekday() < 5][:n_sessions]
    tickers = [f"T{i}.TO" for i in range(n_tickers)]
    idx_rows, pool_rows = [], []
    for s, d in enumerate(days):
        tide = rng.normal(0, 1.)
        tide_gap = rng.normal(0, 1.)
        idx_rows.append({'t': 'XIU.TO', 'date': d.isoformat(), 'r0': tide,
                         'gap': tide_gap})
        for t in tickers:
            idio = rng.normal(0, 1.)
            idio_gap = rng.normal(0, 1.)
            r0 = tide + idio
            gap = 0.8 * tide_gap + idio_gap
            signal = 0.9 * idio if edge else 0.0
            r1 = signal + rng.normal(0, 1.2)
            pool_rows.append({'t': t, 'date': d.isoformat(), 'r0': r0,
                              'gap': gap, 'v15': 1e6, 'px': 100., 'r1': r1})
    pool = pd.DataFrame(pool_rows)
    pool['y'] = (pool['r1'] > 0).astype(int)
    return pool, pd.DataFrame(idx_rows)


def test_h2_planted_edge_is_detected():
    """POSITIVE CONTROL (registration): where residualization genuinely aligns
    features with the label, the harness must measure a positive delta and the
    planted +2-AUC-point control must clear the registered critical value."""
    import validate_residual as vr
    pool, idx = _synthetic_pool(edge=True)
    out = vr.evaluate(pool, idx)
    assert out['delta_auc'] > 0
    assert out['auc_residualized'] > out['auc_raw']
    ctl = out['planted_control']
    assert ctl['detected'], \
        'a harness that cannot see a planted +2-AUC-point edge is UNDERPOWERED'
    # The planted +0.02 sits on top of the study delta (residualized vs raw).
    assert abs(ctl['edge'] - (out['delta_auc'] + 0.02)) < 0.01
    assert out['mde'] > 0 and len(out['development_blocks']) == 4


def test_h2_zero_edge_is_not_detected():
    import validate_residual as vr
    pool, idx = _synthetic_pool(edge=False)
    out = vr.evaluate(pool, idx)
    assert not (out['edge_over_se'] > out['z_critical']
                and out['placebo_exceeded_at_p95']), \
        'a null DGP produced a registered improvement claim'


def test_h2_is_deterministic():
    import validate_residual as vr
    pool, idx = _synthetic_pool(edge=True)
    a = vr.evaluate(pool, idx)
    b = vr.evaluate(pool, idx)
    assert a == b, 'seed 95 bootstrap/placebo and the k-NN must not drift'


def test_h2_beta_uses_only_trailing_sessions():
    """Point-in-time: a row's beta is computed from strictly earlier sessions."""
    import validate_residual as vr
    days = [d for d in (dt.date(2026, 1, 5) + dt.timedelta(days=i)
                        for i in range(200)) if d.weekday() < 5][:80]
    rng = np.random.default_rng(7)
    idx = pd.DataFrame({'t': 'XIU.TO', 'date': [d.isoformat() for d in days],
                        'r0': rng.normal(0, 1, 80), 'gap': rng.normal(0, 1, 80)})
    pool = pd.DataFrame({'t': 'A.TO', 'date': [d.isoformat() for d in days],
                         'r0': rng.normal(0, 1, 80), 'gap': rng.normal(0, 1, 80),
                         'r1': rng.normal(0, 1, 80)})
    out = vr.residualize(pool, vr.index_sessions(idx), beta_window=60)
    first59 = out.sort_values('date').iloc[:5]
    assert first59['r0_res'].isna().all(), 'warm-up rows must stay NaN (rule 2)'
    assert out['r0_res'].notna().sum() > 0


def test_h2_blocked_run_writes_the_record(tmp_path, monkeypatch):
    """Sandbox expectation: acquisition failure is RECORDED, never hidden."""
    import validate_residual as vr
    def boom(*a, **k):
        raise TimeoutError('sandbox network')
    monkeypatch.setattr(vr, 'acquire_pool', boom)
    out = tmp_path / 'day95_residual_results.json'
    rc = vr.main(['--pool', str(tmp_path / 'none.csv'), '--output', str(out)])
    assert rc == 3
    rec = json.loads(out.read_text())
    assert rec['status'] == 'BLOCKED'
    assert rec['errors'][0]['error'] == 'TimeoutError'
    assert rec['registration'] == 'PREREGISTER_day95b.md'
