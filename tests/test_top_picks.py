"""TOP 2: at most two names the models AGREE on (2026-10-01), never padded, honestly labelled."""
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


def test_with_no_agreement_it_is_empty_and_says_so():
    """2026-10-01: both slots were one model's forced pick, one was traded and
    lost. A name one model backs is not agreement and never fills a slot."""
    out = T.select(snap(status='NO_OPPORTUNITY'), snap(status='NO_OPPORTUNITY'),
                   jev('X.TO', 'Y.TO', long_ranked=['X.TO', 'Z.TO']))
    assert out['picks'] == [] and out['status'] == 'NO_AGREEMENT'
    text = '\n'.join(T.table(out))
    assert 'No agreement today' in text and 'nothing here to act on' in text
    assert 'X.TO' not in text


def test_one_agreed_name_leaves_the_second_slot_empty():
    out = T.select(snap([('AC.TO', .6), ('K.TO', .7)]), snap([('AC.TO', .55)], [('SU.TO', .6)]),
                   jev('Q.TO', 'R.TO'))
    assert [p['ticker'] for p in out['picks']] == ['AC.TO'] and out['status'] == 'PARTIAL'
    assert 'second slot is left empty' in '\n'.join(T.table(out))


def test_a_selection_and_a_jev_rank_count_as_agreement():
    out = T.select(snap([('SEL.TO', .52)]), snap(status='NO_OPPORTUNITY'),
                   jev(long_ranked=['SEL.TO', 'RNK.TO']))
    assert [p['ticker'] for p in out['picks']] == ['SEL.TO']
    assert out['picks'][0]['agreement'] == '2 of 3'


def test_jev_alone_never_agrees_with_itself():
    """Jev's forced pick and its own ranked list are ONE model, not two."""
    out = T.select(snap(status='NO_OPPORTUNITY'), snap(status='NO_OPPORTUNITY'),
                   jev('X.TO', long_ranked=['X.TO']))
    assert out['picks'] == []


def test_opposite_sides_are_split_and_left_out():
    out = T.select(snap([('AC.TO', .6)]), snap([], [('AC.TO', .6)]), jev(long_ranked=['AC.TO']))
    assert out['picks'] == [] and out['split'] == ['AC.TO']
    assert 'opposite sides of: AC.TO' in '\n'.join(T.table(out))


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
    assert {(r['model'], r['kind'], r['ticker'], r['agreement'], r['prompt_version']) for r in rows} == {
        ('top2', 'pick', 'AC.TO', '3 of 3', 'day121-agreement')}
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
    assert 'Top 2 today: LONG AC.TO (3 of 3)' in hero and 'SU.TO' not in hero
    assert hero.index('Top 2 today') < hero.index('No picks today')
    none = T.select(snap(status='NO_OPPORTUNITY'), snap(status='NO_OPPORTUNITY'), jev('X.TO', 'Y.TO'))
    assert 'no agreement between the models — nothing to act on' in email_render._hero(
        {'intraday': {'top_two': none}})


def test_a_day_without_agreement_points_at_each_models_own_picks():
    """Owner, 2026-10-03: an active trader wants the single-model names named on
    a no-agreement day — as pointers, never as Top 2 slots."""
    import email_render
    out = T.select(snap([('AC.TO', .6)]), snap([('SU.TO', .58)]), None)
    assert out['status'] == 'NO_AGREEMENT' and out['picks'] == []
    text = '\n'.join(T.table(out, concise=True))
    assert 'No agreement today — nothing to act on.' in text
    assert 'Single-model picks (one model only, no agreement): LONG AC.TO (Claude 0.60)' in text
    assert 'LONG SU.TO (DeepSeek 0.58)' in text and 'Agreement is not confirmation' not in text
    hero = email_render._hero({'intraday': {'top_two': out}})
    assert 'single-model picks: LONG AC.TO (Claude)' in hero
    none = T.select(snap(status='NO_OPPORTUNITY'), snap(status='NO_OPPORTUNITY'), jev('X.TO', 'Y.TO'))
    assert none['single'] == []                      # forced Jev names are not selections
    assert 'Single-model picks: none' in '\n'.join(T.table(none, concise=True))
    # an older publication without the field prints no single-model line
    old = {k: v for k, v in out.items() if k != 'single'}
    assert 'Single-model' not in '\n'.join(T.table(old, concise=True))
