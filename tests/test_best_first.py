"""Day-145 (council lab item 5, PREREGISTER_day145_best_first.md): the
best-first test's machinery, on synthetic data only. No API call and no real
record is read here."""
import json
import random
import sqlite3

import best_first as B

SESSIONS = ['2026-10-%02d' % d for d in (14, 15, 16, 19, 20, 21, 22, 23, 26, 27, 28, 29, 30)] + \
           ['2026-11-02', '2026-11-03']


def make(tmp_path, edge=0.0, noise=1.0, seed=1):
    """Rows for every (session, model, side): a first-named name whose result
    is the second's plus `edge`, and a review file giving the order."""
    rng = random.Random(seed)
    rows = []
    reviews = tmp_path / 'reviews'
    reviews.mkdir()
    for s in SESSIONS:
        review = []
        for m in B.MODELS:
            for side in B.SIDES:
                a, b = '%s%s1.TO' % (m[:2].upper(), side[0]), '%s%s2.TO' % (m[:2].upper(), side[0])
                y2 = rng.gauss(0, noise)
                y1 = rng.gauss(0, noise) + edge
                rows.append({'session': s, 'model': m, 'kind': 'nominated', 'side': side,
                             'ticker': a, 'r_pct': y1, 'confidence': 0.6})
                rows.append({'session': s, 'model': m, 'kind': 'nominated', 'side': side,
                             'ticker': b, 'r_pct': y2, 'confidence': 0.5})
                review += [{'section': B.SECTION, 'model': m, 'side': side, 'ticker': a},
                           {'section': B.SECTION, 'model': m, 'side': side, 'ticker': b}]
        (reviews / ('%s.json' % s)).write_text(json.dumps({'rows': review}))
    return rows, reviews


def test_the_frozen_order_wins_and_unknown_or_unscored_sides_are_left_out(tmp_path):
    rows, reviews = make(tmp_path)
    db = tmp_path / 'reports.sqlite3'
    con = sqlite3.connect(str(db))
    con.execute('create table reports (session text, body text)')
    # the frozen report reverses Claude's LONG order on the first session
    body = {'intraday': {'council': {'nomination_picks': {'claude': {
        'longs': [{'ticker': 'CLL2.TO'}, {'ticker': 'CLL1.TO'}], 'shorts': []}}}}}
    con.execute('insert into reports values (?, ?)', (SESSIONS[0], json.dumps(body)))
    con.commit()
    con.close()
    # an unscored pick, and a side whose review lists one name only
    rows = [dict(r, r_pct='') if (r['session'] == SESSIONS[1] and r['ticker'] == 'DEL1.TO') else r
            for r in rows]
    f = reviews / ('%s.json' % SESSIONS[2])
    review = json.loads(f.read_text())
    review['rows'] = [r for r in review['rows'] if r['ticker'] != 'GES2.TO']
    f.write_text(json.dumps(review))
    prs, left, agree = B.pairs(rows, db=db, reviews=reviews)
    first = [p for p in prs if p['session'] == SESSIONS[0] and p['model'] == 'claude' and p['side'] == 'LONG']
    assert first[0]['first'] == 'CLL2.TO' and first[0]['source'] == 'frozen'
    assert agree == {'both sources': 1, 'agree': 0}
    assert left['not scored'] == 1 and left['order unknown'] == 1
    assert len(prs) == len(SESSIONS) * 6 - 2


def test_the_window_does_not_move(tmp_path):
    rows, reviews = make(tmp_path)
    later = [dict(r, session='2026-11-04') for r in rows if r['session'] == SESSIONS[-1]]
    prs, _, _ = B.pairs(rows + later, db=tmp_path / 'none.sqlite3', reviews=reviews)
    assert max(p['session'] for p in prs) == B.LAST


def test_a_planted_edge_passes_either_way_and_noise_does_not(tmp_path):
    for edge, want in ((1.5, 'FIRST_BETTER'), (-1.5, 'SECOND_BETTER'), (0.0, 'NULL')):
        where = tmp_path / str(edge)
        where.mkdir()
        rows, reviews = make(where, edge=edge)
        prs, _, _ = B.pairs(rows, db=tmp_path / 'none.sqlite3', reviews=reviews)
        v = B.verdict(prs, draws=500)
        assert v['status'] == want, (edge, v)
        assert v['control']['detected']


def test_a_harness_that_cannot_see_one_percent_says_underpowered(tmp_path):
    rows, reviews = make(tmp_path, noise=12.0)
    prs, _, _ = B.pairs(rows, db=tmp_path / 'none.sqlite3', reviews=reviews)
    v = B.verdict(prs, draws=500)
    assert not v['control']['detected'] and v['status'] == 'UNDERPOWERED'


def test_the_placebo_tails_and_the_control_are_built_as_registered():
    ds = [0.5, 0.4, 0.6, 0.55, 0.45, 0.5, 0.52, 0.48]
    assert B.placebo(ds, tail='upper', draws=2000) < 0.01
    assert B.placebo(ds, tail='lower', draws=2000) > 0.9
    prs = [{'session': 's%d' % (i // 2), 'd': d} for i, d in enumerate([3.0, -1.0, 2.0, 1.0, 0.0, 1.0])]
    ctl = B.control(prs)
    # centred on the mean d (1.0), then +1.0 on every first-named pick: the
    # session means read 1.0, 1.5 and 0.5, so t = 1.0 / (0.5 / sqrt 3)
    assert ctl['planted_pct'] == 1.0 and abs(ctl['t'] - 3.46) < 0.01 and ctl['detected']
