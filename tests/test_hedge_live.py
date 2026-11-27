"""Day-156 lab item 18 (PREREGISTER_day156_hedge_live.md): the hedge on the live record.

Synthetic rows only: the registered run reads the pinned lab once, by hand."""
import hashlib
import random

import pytest

import execution_lab
import hedge_live as H


def row(session, ticker, side='LONG', model='gemini', kind='selected', r=0.1, r_vs_etf=0.05,
        beta=1.0, etf='XEG.TO'):
    return {'session': session, 'model': model, 'kind': kind, 'side': side, 'ticker': ticker,
            'r': '' if r is None else str(r), 'r_vs_etf': '' if r_vs_etf is None else str(r_vs_etf),
            'beta': '' if beta is None else str(beta), 'etf': etf}


def sessions(n, start=1):
    return [f'2026-10-{d:02d}' for d in range(start, start + n)]


def test_the_pinned_file_is_refused_unless_its_hash_is_the_registered_one():
    blob = b'session,model,kind,side,ticker,r,r_vs_etf,beta,etf\n'
    good = hashlib.sha256(blob).hexdigest()[:16]
    rows, digest = H.pinned_rows(sha_prefix=good, show=lambda spec: blob)
    assert rows == [] and digest.startswith(good)
    with pytest.raises(SystemExit, match='REFUSED'):
        H.pinned_rows(sha_prefix='0' * 16, show=lambda spec: blob)


def test_the_population_is_the_hedge_lines_own():
    rows = [row('2026-10-01', 'A.TO', model='gemini', r=0.5, r_vs_etf=0.2),
            row('2026-10-01', 'A.TO', model='deepseek', r=0.9, r_vs_etf=0.9),   # the same name: once
            row('2026-10-01', 'B.TO', model='engine'),                           # the engine is out
            row('2026-10-01', 'C.TO', model='top2floor'),                         # a shadow is out
            row('2026-10-01', 'D.TO', model='claude', kind='nominated'),          # forced nominations out
            row('2026-10-01', 'E.TO', model='top2runner', r=-0.3, r_vs_etf=-0.1),  # the runner-up is in
            row('2026-10-02', 'F.TO', model='jev', kind='forced', r=0.2, r_vs_etf=None),  # one window
            row('2026-10-02', 'F.TO', model='gemini', r=0.4, r_vs_etf=0.1),      # the first row decides
            row('2026-11-27', 'G.TO', model='gemini')]                            # after the cut
    ps, counts = H.line_positions(rows)
    assert [(p['ticker'], p['model']) for p in ps] == [('A.TO', 'gemini'), ('E.TO', 'top2runner')]
    assert counts['unique_missing_a_window'] == 1 and counts['positions'] == 2
    # The same picks and the same gross difference as the line's own record.
    cut = [r for r in rows if r['session'] <= H.CUT]
    pairs = [(execution_lab._float(r.get('r')), execution_lab._float(r.get('r_vs_etf')))
             for r in execution_lab._model_picks(cut)]
    pairs = [(a, b) for a, b in pairs if a is not None and b is not None]
    assert len(pairs) == len(ps)
    assert sorted(b - a for a, b in pairs) == pytest.approx(sorted(p['g'] for p in ps))
    # Day-153's population, beside the verdict, leaves the runner-up out.
    assert [p['ticker'] for p in H.day153_positions(rows)] == ['A.TO', 'F.TO']


def test_the_hedges_own_leg_is_charged_on_the_size_of_its_beta():
    (p,) = H.line_positions([row('2026-10-01', 'A.TO', r=0.5, r_vs_etf=0.4, beta=-0.5)])[0]
    assert p['g'] == pytest.approx(-0.1) and p['d'] == pytest.approx(-0.1 - 0.13 * 0.5)
    (q,) = H.line_positions([row('2026-10-01', 'A.TO', beta=None)])[0]
    assert q['d'] is None


def synthetic(n_sessions, per=6, *, market=0.2, own_sd=0.2, cost_pct=0.0, seed=1):
    """A market move the hedge removes, +market and -market on alternate
    sessions: r = m + e, and the hedged r_vs_etf = e + 0.13 - cost, so that
    d = -m - cost (the 0.13 offsets the charge on a beta of 1)."""
    rng = random.Random(seed)
    days = (sessions(n_sessions) if n_sessions <= 31
            else [f'2026-{(i // 28) + 9:02d}-{(i % 28) + 1:02d}' for i in range(n_sessions)])
    rows = []
    for i, s in enumerate(days):
        m = market if i % 2 else -market
        for k in range(per):
            e = rng.gauss(0, own_sd)
            rows.append(row(s, f'T{k}.TO', r=m + e, r_vs_etf=e + 0.13 - cost_pct, beta=1.0))
    return rows


def test_a_hedge_that_removes_swing_at_no_cost_is_confirmed_and_a_costly_one_is_worse():
    good = H.run(synthetic(60), draws=300)
    assert good['verdict'] == 'CONFIRMED' and all(good['legs'].values()) and not good['worse']
    assert good['full']['ratio'] > 1.15 and good['control']['t_planted'] >= 3
    costly = H.run(synthetic(60, cost_pct=0.5), draws=300)
    assert costly['verdict'] == 'WORSE' and costly['worse'] and not costly['legs']['mean']


def test_too_few_sessions_is_underpowered_and_the_worse_flag_still_shows():
    thin = H.run(synthetic(4, per=2, market=2.0, own_sd=3.0, cost_pct=0.3), draws=200)
    assert thin['verdict'] == 'UNDERPOWERED' and not thin['legs']['control']
    assert 'worse' in thin and 'better' in thin and thin['control']['mde_pct'] is not None


def test_halves_split_an_odd_count_and_sit_the_middle_out():
    ps, _ = H.line_positions(synthetic(5, per=1))
    a, b, middle = H.halves(ps)
    assert len({p['session'] for p in a}) == 2 == len({p['session'] for p in b})
    assert middle == '2026-10-03'


def test_the_line_s_occasion_is_a_one_sided_top2_morning():
    rows = [row('2026-10-01', 'A.TO', model='top2'), row('2026-10-01', 'B.TO', model='top2', side='SHORT'),
            row('2026-10-02', 'C.TO', model='top2', side='SHORT')]
    assert H.one_sided_sessions(rows) == {'2026-10-02'}


def test_the_script_does_nothing_without_run(capsys):
    assert H.main([]) == 2
