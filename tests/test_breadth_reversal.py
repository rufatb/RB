"""Day-135d's registered test (breadth_reversal.py) and the live chase audit
(chase_audit.py) on synthetic data."""
import types

import numpy as np

import breadth_reversal as BR
import chase_audit as CA


def panel(k=60, s=900, reversal=0.0, seed=11):
    """k names over s sessions; every 10th session is a broad one (many movers).
    After a broad session the movers' next open -> close carries `reversal`
    (in %, against the move)."""
    rng = np.random.default_rng(seed)
    m = rng.normal(0, 0.6, size=(k, s))
    broad = np.arange(s) % 10 == 0
    m[:, broad] = rng.normal(0, 1.6, size=(k, broad.sum()))
    r = rng.normal(0, 2.0, size=(k, s))
    mover = np.abs(m) >= 1
    r += np.where(mover & broad[None, :], -reversal * np.sign(m), 0.0)
    mr = rng.normal(0, 0.8, size=s)
    return types.SimpleNamespace(m=m, r=r + mr, mr=mr, adj=r, cal=['2020-01-01'] * s,
                                 tickers=['N%d.TO' % j for j in range(k)])


def test_broad_days_are_causal_and_the_top_decile():
    rng = np.random.default_rng(3)
    B = rng.uniform(0.05, 0.2, size=400)
    B[350] = 0.6
    broad, eligible, thr = BR.broad_days(B)
    assert not eligible[:BR.WINDOW].any() and eligible[BR.WINDOW:].all()
    assert broad[350] and 0.05 < broad[eligible].mean() < 0.2      # about a decile
    later = B.copy()
    later[360:] = 0.9                                     # the future never relabels the past
    assert (BR.broad_days(later)[0][:360] == broad[:360]).all()


def test_a_planted_reversal_after_broad_days_is_found_and_none_is_null():
    found = BR.run(panel(reversal=1.0))
    assert found['raw']['verdict'] == 'REVERSAL' and found['raw']['after_broad_days']['t'] < -3
    none = BR.run(panel(reversal=0.0))
    assert none['raw']['verdict'] == 'NULL'
    assert none['raw']['control']['t_planted'] <= -3


def test_a_pick_follows_a_big_move_fades_it_or_is_calm():
    assert CA.kind_of('LONG', 2.5) == 'follows' and CA.kind_of('SHORT', -1.5) == 'follows'
    assert CA.kind_of('LONG', -1.2) == 'fades' and CA.kind_of('SHORT', 1.0) == 'fades'
    assert CA.kind_of('LONG', 0.99) == 'calm' and CA.kind_of('SHORT', None) == 'unknown'


def test_the_audit_counts_each_stage_against_the_lists_base_rate():
    def bars(closes):
        # [date, open, high, low, close]: a steady 1.0 range, so ATR is about 1
        out, prev = [], closes[0]
        for i, c in enumerate(closes):
            out.append(['2026-09-%02d' % (i + 1) if i < 30 else '2026-10-%02d' % (i - 29),
                        prev, max(prev, c) + 0.5, min(prev, c) - 0.5, c])
            prev = c
        return out
    flat = [100.0] * 40
    jump = [100.0] * 39 + [103.0]                         # +3 on the last bar: a big mover
    data = {'UP.TO': bars(jump), 'A.TO': bars(flat), 'B.TO': bars(flat)}
    session = '2026-10-11'
    fetch = lambda path, symbol, **kw: [{'date': d, 'open': o, 'high': h, 'low': lo, 'close': c}
                                        for d, o, h, lo, c in data[symbol]]
    rows = [{'session': session, 'model': 'top2', 'kind': 'pick', 'side': 'LONG', 'ticker': 'UP.TO', 'r_pct': '-1.0'},
            {'session': session, 'model': 'deepseek', 'kind': 'selected', 'side': 'SHORT', 'ticker': 'A.TO', 'r_pct': ''}]
    out = CA.audit(fetch, rows, ['UP.TO', 'A.TO', 'B.TO'])
    top = out['stages']['the council Top 2']
    assert top['follows'] == 1 and top['follow_share'] == 1.0
    assert top['base_follow_share'] == round(1 / 6, 3)     # one mover in three names, half its sides
    assert out['stages']['desk selections']['calm'] == 1
    assert out['top2_sessions'][session]['same_side'] is False
