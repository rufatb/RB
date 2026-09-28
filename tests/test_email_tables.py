"""Every picks section of the email is ONE table; Jev shows its forced picks only."""
import email_render
import primary_board as P

CFG = {'risk': {'account_equity': 100000, 'max_position_pct': 20},
       'execution': {'accept_corroborated_bbo': True}}
OPEN = {'eligible': True}
Q = {'AC.TO': {'status': 'OK', 'ask': 26.4, 'bid': 26.3, 'currency': 'CAD'}}


def intra(jev):
    ds = {'status': 'READY', 'longs': [{'ticker': 'AC.TO', 'confidence': 0.53, 'invalid_at': 25.9,
                                        'reason': 'Broke the opening range | on volume'}], 'shorts': []}
    desks = []
    for desk_id, label, key, snap in (('claude', 'Claude', 'claude', {'status': 'NO_OPPORTUNITY'}),
                                      ('deepseek', 'DeepSeek', 'opportunities', ds),
                                      ('jev', 'Jev', 'jev', jev)):
        board = P.build(snap, Q, CFG, OPEN, True, source=label)
        board.update(id=desk_id, evidence_key=key)
        desks.append(board)
    return {'desks': desks, 'claude': {'status': 'NO_OPPORTUNITY'}, 'opportunities': ds, 'jev': jev,
            'open_measured': {'GIL.TO': {'status': 'OK', 'price': 58.26, 'vwap': 58.45,
                                         'price_vs_vwap_pct': -0.32, 'rvol': 3.02}}}


JEV = {'status': 'NO_OPPORTUNITY', 'longs': [], 'shorts': [],
       'long_ranked': [{'ticker': 'SHOP.TO', 'probability': 0.09, 'abstain_probability': 0.56}],
       'forced_long': {'ticker': 'DOL.TO', 'probability': 0.27, 'gated_abstain_probability': 0.56,
                       'cleared_gated_abstain': False},
       'forced_short': {'ticker': 'GIL.TO', 'probability': 0.60, 'gated_abstain_probability': 0.44,
                        'cleared_gated_abstain': True}}


def test_a_desk_is_one_table_with_its_reason_in_the_row():
    text = '\n'.join(email_render.desk_sections(intra(JEV)))
    row = next(l for l in text.splitlines() if 'LONG AC.TO' in l)
    assert row.startswith('| SHADOW | LONG AC.TO') and 'Broke the opening range / on volume' in row
    assert 'below 25.90' in row
    assert not any(l.startswith('- LONG') for l in text.splitlines())     # no bullet list


def test_jev_prints_its_forced_picks_only():
    text = '\n'.join(email_render.desk_sections(intra(JEV)))
    jev = text[text.index('### 3 · Jev'):]
    assert '| LONG DOL.TO | 0.27 | 0.56 | not measured | below its own "none"' in jev
    assert '| SHORT GIL.TO | 0.60 | 0.44 | YES — below VWAP' in jev
    assert 'SHOP.TO' not in jev and 'Top-ranked' not in jev


def test_a_jev_selection_is_never_hidden_behind_the_forced_table():
    jev = {**JEV, 'status': 'READY', 'longs': [{'ticker': 'AC.TO', 'probability': 0.6,
                                               'abstain_probability': 0.3}]}
    text = '\n'.join(email_render.desk_sections(intra(jev)))
    assert 'Jev also SELECTED (sized, in the full report): LONG AC.TO.' in text


def test_the_newsletter_renders_the_tables_as_tables():
    body = '# T\nstamp\n' + '\n'.join(email_render.desk_sections(intra(JEV)))
    html = email_render.html_from_text(body)
    assert html.count('<table role="table"') == 2        # DeepSeek's desk and Jev's forced picks
