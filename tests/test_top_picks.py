"""TOP 2: exactly two names, ranked by how many models back them, honestly labelled."""
import top_picks as T


def snap(longs=(), shorts=(), status='READY'):
    return {'status': status,
            'longs': [{'ticker': t, 'confidence': c, 'reason': f'r {t}', 'invalid_at': 9.5}
                      for t, c in longs],
            'shorts': [{'ticker': t, 'confidence': c, 'reason': f's {t}', 'invalid_at': 10.5}
                       for t, c in shorts]}


def jev(forced_long=None, forced_short=None, long_ranked=(), short_ranked=(), longs=()):
    return {'status': 'NO_OPPORTUNITY', 'longs': [{'ticker': t, 'probability': .6} for t in longs],
            'shorts': [],
            'forced_long': {'ticker': forced_long, 'probability': .4} if forced_long else None,
            'forced_short': {'ticker': forced_short, 'probability': .5} if forced_short else None,
            'long_ranked': [{'ticker': t, 'probability': .3} for t in long_ranked],
            'short_ranked': [{'ticker': t, 'probability': .3} for t in short_ranked]}


def test_all_three_agreeing_lead_and_the_section_is_exactly_two():
    out = T.select(snap([('AC.TO', .6), ('K.TO', .55)]), snap([('AC.TO', .58)], [('SU.TO', .57)]),
                   jev('AC.TO', 'SU.TO'))
    assert [(p['side'], p['ticker']) for p in out['picks']] == [('LONG', 'AC.TO'), ('SHORT', 'SU.TO')]
    assert out['picks'][0]['agreement'] == '3 of 3' and out['picks'][1]['agreement'] == '2 of 3'
    assert out['picks'][0]['lead'] == 'Claude' and out['picks'][0]['reason'] == 'r AC.TO'
    assert out['status'] == 'READY' and len(out['picks']) == 2
    text = '\n'.join(T.table(out))
    assert 'ALL 3 AGREE' in text and '2 of 3 agree' in text


def test_never_more_than_two_even_when_many_names_agree():
    c = snap([('A.TO', .6), ('B.TO', .6)], [('C.TO', .6), ('D.TO', .6)])
    out = T.select(c, c, jev(long_ranked=['A.TO', 'B.TO'], short_ranked=['C.TO', 'D.TO']))
    assert len(out['picks']) == 2


def test_with_no_agreement_it_still_fills_two_and_says_so():
    out = T.select(snap(status='NO_OPPORTUNITY'), snap(status='NO_OPPORTUNITY'),
                   jev('X.TO', 'Y.TO', long_ranked=['X.TO', 'Z.TO']))
    assert len(out['picks']) == 2 and {p['ticker'] for p in out['picks']} == {'X.TO', 'Y.TO'}
    assert all(p['agreement'] == '1 of 3' for p in out['picks'])
    text = '\n'.join(T.table(out))
    assert '1 of 3 — no agreement on this slot' in text
    assert 'gives probabilities, not reasons' in text


def test_a_selection_outranks_a_ranked_name_at_equal_backing():
    out = T.select(snap([('SEL.TO', .52)]), snap(status='NO_OPPORTUNITY'),
                   jev(long_ranked=['RNK.TO']))
    assert [p['ticker'] for p in out['picks']] == ['SEL.TO', 'RNK.TO']


def test_opposite_sides_are_split_and_go_last():
    out = T.select(snap([('AC.TO', .6)]), snap([], [('AC.TO', .6)]),
                   jev('K.TO', 'SU.TO'))
    assert {p['ticker'] for p in out['picks']} == {'K.TO', 'SU.TO'}
    only = T.select(snap([('AC.TO', .6)]), snap([], [('AC.TO', .6)]), {'status': 'UNAVAILABLE'})
    assert len(only['picks']) == 1 and only['picks'][0]['split'] is True
    assert 'SPLIT' in '\n'.join(T.table(only)) and only['status'] == 'SHORT'


def test_with_every_model_down_it_says_why_and_invents_nothing():
    down = {'status': 'UNAVAILABLE'}
    out = T.select(down, down, down)
    assert out['picks'] == [] and 'No model answered' in out['reason']
    assert 'No model answered' in '\n'.join(T.table(out))


def test_agreement_counts_only_models_that_answered():
    out = T.select(snap([('AC.TO', .6)]), {'status': 'UNAVAILABLE'}, jev('AC.TO', 'SU.TO'))
    assert out['picks'][0]['agreement'] == '2 of 2'
    assert 'ALL 2 AGREE' in '\n'.join(T.table(out))


def test_top_two_is_recorded_scored_and_on_the_board():
    import model_picks
    import primary_board
    out = T.select(snap([('AC.TO', .6)]), snap([('AC.TO', .58)]), jev('AC.TO', 'SU.TO'))
    rows = model_picks.rows_from_report({'session': '2026-09-29', 'intraday': {'top_two': out}})
    assert {(r['model'], r['kind'], r['ticker'], r['agreement']) for r in rows} == {
        ('top2', 'pick', 'AC.TO', '3 of 3'), ('top2', 'pick', 'SU.TO', '1 of 3')}
    assert primary_board.leaderboard({})[0]['source'] == 'Top 2 (where the models agree)'


def test_it_is_at_the_top_of_every_email_and_view():
    import brief
    import email_render
    import report_page
    from test_daily_pipeline import NOW, services
    d = brief.build(now=NOW, services=services())
    assert d['intraday']['top_two'] is not None
    body = email_render.text(d)
    assert body.index('## Top 2') < body.index('## Part 1')
    full = brief.render_text(d)
    assert full.index('## Top 2') < full.index('## Part 1')
    page = report_page.render(d)
    assert page.index('Top 2 · where the models agree') < page.index('Part 1 · Intraday')
    assert 'Top 2' in email_render.html(d)


def test_an_older_publication_renders_without_it():
    import brief
    import email_render
    from test_daily_pipeline import NOW, services
    d = dict(brief.build(now=NOW, services=services()))
    d['intraday'] = {k: v for k, v in d['intraday'].items() if k != 'top_two'}
    assert '## Top 2' not in email_render.text(d)


def test_the_email_hero_names_the_top_two_first():
    import email_render
    out = T.select(snap([('AC.TO', .6)]), snap([('AC.TO', .58)]), jev('AC.TO', 'SU.TO'))
    hero = email_render._hero({'intraday': {'top_two': out}})
    assert 'Top 2 today: LONG AC.TO (3 of 3) · SHORT SU.TO (1 of 3)' in hero
    assert hero.index('Top 2 today') < hero.index('No picks today')
