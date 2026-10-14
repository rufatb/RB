"""Day-132b (owner, 2026-10-14): the scoreboard shows every row net of the
measured round-trip cost, and one pooled row that counts each bet once."""
import daily_render
import email_render
import model_picks
import primary_board as P
import report_page


def row(session, model, kind, side, ticker, r, **kw):
    base = {'session': session, 'model': model, 'kind': kind, 'side': side, 'ticker': ticker,
            'r_pct': str(r), 'hit': '1' if r > 0 else '0', 'scored_at': '2026-10-14T16:30:00-04:00',
            'invalidated': '', 'entry_time': ''}
    base.update(kw)
    return base


def test_net_is_the_gross_mean_less_the_measured_cost():
    assert P.COST_PER_PICK_PCT == 0.13 and P.COST_RANGE_PCT == (0.07, 0.19)
    rows = P.leaderboard({'top2_pick': {'picks': 4, 'hits': 2, 'rate': .5, 'mean_r_pct': -0.10,
                                        'sessions': 2, 'ci95': [.15, .85]}})
    top = rows[0]
    assert abs(top['net_mean_pct'] - (-0.23)) < 1e-9
    assert all(r['net_mean_pct'] is None for r in rows if not r['picks'])


def test_the_pooled_row_counts_each_bet_once_and_leaves_out_late_engine_and_shadows():
    rows = [row('2026-10-14', 'top2', 'pick', 'SHORT', 'SSRM.TO', 1.2),
            row('2026-10-14', 'gemini', 'selected', 'SHORT', 'SSRM.TO', 1.2),
            row('2026-10-14', 'claude', 'nominated', 'SHORT', 'SSRM.TO', 1.2),
            row('2026-10-14', 'deepseek', 'selected', 'LONG', 'TD.TO', 0.5),
            row('2026-10-14', 'jev', 'forced', 'LONG', 'RBA.TO', -0.4),
            row('2026-10-14', 'engine', 'board', 'SHORT', 'CP.TO', -0.6),
            row('2026-10-14', 'top2count', 'pick', 'LONG', 'SHOP.TO', -3.5),
            row('2026-10-14', 'deepseek', 'late', 'SHORT', 'AC.TO', 1.6, entry_time='10:05'),
            row('2026-10-14', 'gemini', 'selected', 'LONG', 'SHOP.TO', -3.5, scored_at='')]
    card = model_picks.pooled_card(rows)['all_model_picks']
    assert card['picks'] == 3 and card['hits'] == 2 and card['sessions'] == 1
    assert abs(card['mean_r_pct'] - (1.2 + 0.5 - 0.4) / 3) < 1e-9


def test_the_email_prints_the_net_column_the_pooled_row_and_the_cost_line():
    card = {'top2_pick': {'picks': 4, 'hits': 2, 'rate': .5, 'mean_r_pct': -0.10, 'sessions': 2,
                          'ci95': [.15, .85]}}
    pooled = {'all_model_picks': {'picks': 9, 'hits': 4, 'rate': 4 / 9, 'mean_r_pct': -0.16,
                                  'sessions': 3, 'ci95': [.2, .7]}}
    text = '\n'.join(email_render._scoreboard(P.leaderboard(card, pooled=pooled)))
    assert '| Source | Right | Mean per pick | Net of costs | Sessions | 95% range |' in text
    assert '| Top 2 (where the models agree) | 2/4 (50%) | -0.10% | -0.23% | 2 | 15%–85% |' in text
    assert 'All model picks together (each name, side and day once) | 4/9 (44%) | -0.16% | -0.29%' in text
    assert '0.13% round trip' in text and 'coin flip' in text
    html = email_render.html_from_text(text)
    assert 'Net of costs' in html


def test_a_publication_from_before_the_net_column_renders_as_it_did():
    old = [{'source': 'Top 2 (where the models agree)', 'picks': 4, 'hits': 2, 'rate': .5,
            'mean_r_pct': -0.10, 'sessions': 2, 'ci95': [.15, .85]}]
    text = '\n'.join(email_render._scoreboard(old))
    assert 'Net of costs' not in text and 'no costs' in text
    assert 'Net of costs' not in report_page._scoreboard(old)


def test_the_full_report_and_the_page_carry_the_whole_cost_note():
    board = P.leaderboard({}, pooled={})
    assert P.COST_NOTE_FULL in '\n'.join(daily_render.scoreboard_lines(board))
    page = report_page._scoreboard(board)
    assert 'Net of costs' in page and 'closing auction' in page
