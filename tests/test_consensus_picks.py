"""Part 3: the owner's strategy picks — consensus, confirmed at the open, never empty."""
import datetime as dt
from zoneinfo import ZoneInfo

import pandas as pd

import consensus_picks as C

ET = ZoneInfo('America/New_York')
DAY = dt.date(2026, 9, 25)
AT_0946 = dt.datetime(2026, 9, 25, 9, 46, 5, tzinfo=ET)


def bars(today_close=10.0, today_vol=(300.0, 300.0), prior_vol=(100.0, 100.0), sessions=10,
         auction_0930=0.0, today=True):
    """Five-minute bars: `sessions` prior days and (optionally) today's opening."""
    rows, idx = [], []
    days = [DAY - dt.timedelta(days=n) for n in range(sessions, 0, -1)] + ([DAY] if today else [])
    for d in days:
        vols = today_vol if d == DAY else prior_vol
        close = today_close if d == DAY else 9.0
        for t, v in ((dt.time(9, 30), auction_0930), (dt.time(9, 35), vols[0]),
                     (dt.time(9, 40), vols[1]), (dt.time(9, 45), 50.0)):
            idx.append(pd.Timestamp(dt.datetime.combine(d, t), tz=ET))
            rows.append({'Open': close, 'High': close + 0.2, 'Low': close - 0.2,
                         'Close': close, 'Volume': v})
    return pd.DataFrame(rows, index=idx)


# ── the measurement ─────────────────────────────────────────────────────────

def test_opening_price_vwap_and_rvol_from_the_0935_and_0940_bars():
    m = C.opening(bars(), DAY)
    assert m['status'] == 'OK' and m['price'] == 10.0 and m['vwap'] == 10.0
    assert m['rvol'] == 3.0 and m['baseline_sessions'] == 10


def test_the_0930_auction_bar_moves_neither_rvol_nor_vwap():
    """Yahoo's 09:30 TSX bar is 0 on most sessions and the whole auction on a
    few (CP.TO 09-18: 1,017,019). It must not swing the reading."""
    assert C.opening(bars(auction_0930=1e6), DAY)['rvol'] == C.opening(bars(), DAY)['rvol']


def test_one_huge_prior_session_does_not_set_the_norm():
    frame = bars()
    first = frame.index[1]                                  # a prior 09:35 bar
    frame.loc[first, 'Volume'] = 1e7
    assert C.opening(frame, DAY)['rvol'] == 3.0             # the median ignores it


def test_missing_opening_or_short_history_is_not_measured():
    assert C.opening(bars(today=False), DAY)['status'] == 'OPENING_BARS_INCOMPLETE'
    assert C.opening(bars(sessions=3), DAY)['status'] == 'RVOL_BASELINE_SHORT'
    assert C.opening(None, DAY)['status'] == 'NO_BARS'


def test_the_rule_both_sides_and_its_boundary():
    up = {'status': 'OK', 'price': 10.1, 'vwap': 10.0, 'price_vs_vwap_pct': 1.0, 'rvol': 1.5}
    down = {**up, 'price': 9.9, 'price_vs_vwap_pct': -1.0}
    assert C.passes('LONG', up)[0] and not C.passes('SHORT', up)[0]
    assert C.passes('SHORT', down)[0] and not C.passes('LONG', down)[0]
    assert not C.passes('LONG', {**up, 'rvol': 1.2})[0]              # strictly above 1.2
    met, why = C.passes('LONG', {'status': 'FETCH_FAILED: Timeout'})
    assert not met and 'not measured' in why


def test_measure_refuses_before_the_0940_bar_has_closed():
    early = AT_0946.replace(minute=44)
    out = C.measure(['AAA.TO'], early, fetch=lambda t: bars())
    assert out == {'AAA.TO': {'status': 'BEFORE_09:46'}}


def test_measure_names_every_failure_and_a_rate_limit_stops_it():
    class ChartRateLimitError(RuntimeError):
        pass
    calls = []

    def fetch(t):
        calls.append(t)
        if t == 'BAD.TO':
            raise ChartRateLimitError()
        return bars()
    out = C.measure(['BAD.TO', 'X1.TO', 'X2.TO'], AT_0946, fetch=fetch, workers=1)
    assert out['BAD.TO']['status'] == 'FETCH_FAILED: ChartRateLimitError'
    assert out['X1.TO']['status'] == out['X2.TO']['status'] == 'RATE_LIMITED'
    assert calls == ['BAD.TO']


# ── the selection ───────────────────────────────────────────────────────────

def ok(price, vwap, rvol):
    return {'status': 'OK', 'price': price, 'vwap': vwap,
            'price_vs_vwap_pct': (price / vwap - 1) * 100, 'rvol': rvol}


DS = {'status': 'READY', 'longs': [{'ticker': 'AC.TO', 'confidence': 0.53, 'invalid_at': 28.24,
                                    'reason': 'broke the opening range'},
                                   {'ticker': 'ATZ.TO', 'confidence': 0.56}],
      'shorts': [{'ticker': 'GIL.TO', 'confidence': 0.6, 'invalid_at': 58.03},
                 {'ticker': 'K.TO', 'confidence': 0.55}]}
JEV = {'status': 'NO_OPPORTUNITY', 'longs': [], 'shorts': [],
       'forced_long': {'ticker': 'DOL.TO', 'probability': 0.25},
       'forced_short': {'ticker': 'GIL.TO', 'probability': 0.58},
       'long_ranked': [{'ticker': 'AC.TO', 'probability': 0.3}], 'short_ranked': []}
CLAUDE = {'status': 'READY', 'longs': [{'ticker': 'LUG.TO', 'confidence': 0.52, 'reason': 'sealed'}],
          'shorts': []}


def test_consensus_confirmed_leads_and_a_single_model_confirmed_follows():
    measured = {'GIL.TO': ok(58.26, 58.45, 3.02), 'ATZ.TO': ok(116.62, 116.40, 1.89),
                'AC.TO': ok(26.35, 26.55, 13.8), 'LUG.TO': ok(90.88, 91.13, 0.61),
                'K.TO': ok(35.10, 35.11, 2.86)}
    out = C.select(CLAUDE, DS, JEV, [], measured)
    first, second = out['picks']
    assert (first['ticker'], first['side'], first['tier']) == ('GIL.TO', 'SHORT', 'A')
    assert first['models'] == ['DeepSeek', 'Jev'] and first['rule_met']
    assert second['tier'] == 'B' and second['rule_met']
    # AC.TO: DeepSeek + Jev agree, but it sat BELOW VWAP — the rule does not take it.
    assert all(p['ticker'] != 'AC.TO' for p in out['picks'])
    assert out['considered'] == 6 and len(out['picks']) == 2


def test_never_empty_when_nothing_meets_the_rule_and_says_so():
    out = C.select(CLAUDE, DS, JEV, [], {})
    assert out['status'] == 'READY' and len(out['picks']) == 2
    assert not any(p['rule_met'] for p in out['picks'])
    # Consensus (tier C) outranks a single model, and Claude leads within a tier.
    assert out['picks'][0]['tier'] == 'C'
    text = '\n'.join(C.lines(out))
    assert 'RULE NOT MET' in text and 'never empty' in text and 'shares' not in text.lower()


def test_claude_leads_when_it_is_among_the_flags():
    ds = {'status': 'READY', 'longs': [{'ticker': 'LUG.TO', 'confidence': 0.7, 'invalid_at': 80.0}],
          'shorts': []}
    out = C.select(CLAUDE, ds, {}, [], {'LUG.TO': ok(91, 90, 2.0)})
    assert out['picks'][0]['lead'].startswith('Claude') and out['picks'][0]['tier'] == 'A'


def test_opposite_sides_are_excluded_not_netted():
    ds = {'status': 'READY', 'longs': [], 'shorts': [{'ticker': 'LUG.TO', 'confidence': 0.6}]}
    out = C.select(CLAUDE, ds, {}, [{'ticker': 'CP.TO', 'side': 'SHORT', 'p_sided': 0.62}], {})
    assert out['conflicts'] == ['LUG.TO'] and [p['ticker'] for p in out['picks']] == ['CP.TO']


def test_with_every_model_down_the_engine_fills_and_with_nothing_it_says_why():
    legs = [{'ticker': 'CP.TO', 'side': 'SHORT', 'p_sided': 0.62},
            {'ticker': 'NTR.TO', 'side': 'LONG', 'p_sided': 0.55}]
    down = {'status': 'UNAVAILABLE'}
    out = C.select(down, down, down, legs, {})
    assert [p['tier'] for p in out['picks']] == ['D', 'D']
    empty = C.select(down, down, down, [], {})
    assert empty['status'] == 'UNAVAILABLE' and 'nothing to confirm' in '\n'.join(C.lines(empty))


def test_a_level_already_crossed_at_0945_is_flagged():
    out = C.select({}, DS, JEV, [], {'GIL.TO': ok(58.26, 58.45, 3.0)})
    gil = out['picks'][0]
    assert gil['invalid_at'] == 58.03 and gil['past_invalid_at_entry'] is True
    assert '(already past)' in '\n'.join(C.lines(out))


def test_names_to_measure_are_the_most_flagged_first():
    assert C.names_from([CLAUDE, DS, JEV])[:2] == ['AC.TO', 'GIL.TO']


# ── recording, scoring and the report ───────────────────────────────────────

def test_strategy_picks_are_recorded_as_their_own_kinds_and_on_the_scoreboard():
    import model_picks
    import primary_board
    section = C.select(CLAUDE, DS, JEV, [], {'GIL.TO': ok(58.26, 58.45, 3.02)})
    rows = model_picks.rows_from_report({'session': '2026-09-25', 'intraday': {'consensus': section}})
    kinds = sorted((r['model'], r['kind'], r['ticker']) for r in rows)
    assert ('consensus', 'rule_met', 'GIL.TO') in kinds
    assert any(k[1] == 'rule_not_met' for k in kinds)
    sources = [r['source'] for r in primary_board.leaderboard({})]
    assert 'Strategy picks (rule met)' in sources and 'Strategy picks (rule not met)' in sources


def test_the_section_is_the_last_one_in_the_email_and_on_every_view():
    import brief
    import email_render
    import report_page
    from test_daily_pipeline import NOW, services
    d = brief.build(now=NOW, services=services())
    section = d['intraday']['consensus']
    assert section['status'] == 'READY' and len(section['picks']) == 2
    assert 'not fetched' in section['measured_note']
    body = email_render.text(d)
    assert body.index('## Part 3') > body.index('## Part 2')
    assert body.index('## Part 3') < body.index('Research only: share counts')
    assert 'Part 3' in email_render.html(d) and 'Part 3' in brief.render_text(d)
    assert 'Part 3 · Strategy picks' in report_page.render(d)


def test_an_older_publication_renders_without_the_section():
    import brief
    import email_render
    import report_page
    from test_daily_pipeline import NOW, services
    d = dict(brief.build(now=NOW, services=services()))
    d['intraday'] = {k: v for k, v in d['intraday'].items() if k != 'consensus'}
    assert 'Part 3' not in email_render.text(d) and 'Part 3' not in report_page.render(d)


# ── every desk pick verified at the open; each desk's top pick named (day-115b) ──

def desk(legs, id_='deepseek'):
    return {'id': id_, 'source': 'DeepSeek', 'legs': [
        {'ticker': t, 'side': s, 'status': 'SHADOW', 'confidence': c, 'reasons': [],
         'baseline_shares': 10, 'entry_reference': 10.0, 'currency': 'CAD'}
        for t, s, c in legs], 'sizing': None}


def test_the_top_pick_is_the_most_confident_that_passed_not_the_most_confident():
    d = desk([('AC.TO', 'LONG', 0.70), ('ATZ.TO', 'LONG', 0.56), ('GIL.TO', 'SHORT', 0.60)])
    C.verify_desks([d], {'AC.TO': ok(26.35, 26.55, 13.8), 'ATZ.TO': ok(116.62, 116.40, 1.89),
                         'GIL.TO': ok(58.26, 58.45, 3.02)})
    assert d['top_pick']['ticker'] == 'GIL.TO' and d['top_pick']['verified']
    assert d['top_pick']['passed'] == 2 and d['top_pick']['of'] == 3
    ac = d['legs'][0]['open_check']
    assert not ac['met'] and ac['cell'].startswith('NO — below VWAP')
    # Display only: nothing about the sized board moved.
    assert [l['status'] for l in d['legs']] == ['SHADOW'] * 3
    assert [l['baseline_shares'] for l in d['legs']] == [10] * 3


def test_with_nothing_verified_the_top_pick_says_not_verified():
    d = desk([('AC.TO', 'LONG', 0.53), ('K.TO', 'SHORT', 0.55)])
    C.verify_desks([d], {})
    assert d['top_pick']['ticker'] == 'K.TO' and not d['top_pick']['verified']
    assert 'NOT VERIFIED' in C.top_line(d)
    assert all(l['open_check']['cell'] == 'not measured' for l in d['legs'])


def test_a_desk_without_picks_has_no_top_pick():
    d = {'id': 'jev', 'legs': [], 'reason': 'no SELECTED pick'}
    C.verify_desks([d], {})
    assert d['top_pick'] is None and C.top_line(d) is None


def test_the_desk_table_prints_the_check_and_the_star():
    import daily_render
    d = desk([('GIL.TO', 'SHORT', 0.60), ('AC.TO', 'LONG', 0.53)])
    C.verify_desks([d], {'GIL.TO': ok(58.26, 58.45, 3.02)})
    text = '\n'.join(daily_render.desk_lines(d))
    assert 'Open check' in text and 'GIL.TO SHORT ★' in text and 'YES — below VWAP' in text
    assert '★ Top pick: SHORT GIL.TO — VERIFIED' in text


def test_selected_picks_are_measured_before_ranked_and_forced_names():
    jev = {'status': 'NO_OPPORTUNITY', 'longs': [], 'shorts': [],
           'long_ranked': [{'ticker': 'A%02d.TO' % n, 'probability': .1} for n in range(30)]}
    names = C.names_from([CLAUDE, DS, jev])
    assert set(names[:5]) == {'LUG.TO', 'AC.TO', 'ATZ.TO', 'GIL.TO', 'K.TO'}
    assert len(names) == C.MAX_MEASURED


def test_top_picks_are_recorded_and_open_checks_filled_at_scoring(tmp_path):
    import model_picks
    import primary_board
    d = desk([('GIL.TO', 'SHORT', 0.60), ('K.TO', 'SHORT', 0.55)])
    C.verify_desks([d], {'GIL.TO': ok(58.26, 58.45, 3.02)})
    report = {'session': '2026-09-25', 'intraday': {'desks': [d], 'opportunities': {
        'status': 'READY', 'longs': [], 'shorts': [{'ticker': 'GIL.TO', 'confidence': 0.6},
                                                    {'ticker': 'K.TO', 'confidence': 0.55}]}}}
    rows = model_picks.rows_from_report(report)
    assert {r['ticker']: r['top_pick'] for r in rows} == {'GIL.TO': True, 'K.TO': False}
    path = tmp_path / 'picks.csv'
    model_picks.append(rows, path)
    frame = bars(today_close=10.0)                     # price == VWAP -> SHORT not met
    extra = bars(today_close=9.0).iloc[-1:].copy()
    extra.index = [pd.Timestamp('2026-09-25 15:55', tz=ET)]
    frame = pd.concat([frame, extra])
    now = dt.datetime(2026, 9, 25, 17, 0, tzinfo=ET)
    assert model_picks.score(path, now=now, bars_for=lambda t: frame) == 2
    stored = model_picks.read(path)
    assert {r['open_check'] for r in stored} == {'not_met'}
    card = model_picks.verification_card(stored)
    assert card['check_not_met']['picks'] == 2 and card['check_top']['picks'] == 1
    board = primary_board.leaderboard(model_picks.scorecard(stored), card)
    assert board[-1]['source'] == 'Desk top picks' and board[-1]['picks'] == 1


def test_a_row_scored_before_the_check_existed_gets_its_blank_filled_once(tmp_path):
    import model_picks
    path = tmp_path / 'picks.csv'
    row = {'session': '2026-09-25', 'model': 'deepseek', 'kind': 'selected', 'side': 'LONG',
           'ticker': 'AAA.TO', 'r_pct': 1.0, 'hit': True, 'scored_at': '2026-09-25T16:21'}
    late = {**row, 'kind': 'late', 'entry_time': '10:10'}
    model_picks.write([row, late], path)
    now = dt.datetime(2026, 9, 27, 12, 0, tzinfo=ET)
    rising = bars()
    first = rising.index[[i.date() == DAY and i.time() == dt.time(9, 35) for i in rising.index]][0]
    rising.loc[first, ['Open', 'High', 'Low', 'Close']] = [9.5, 9.6, 9.4, 9.5]   # 09:45 above VWAP
    assert model_picks.score(path, now=now, bars_for=lambda t: rising) == 0     # nothing NEWLY scored
    stored = {r['kind']: r for r in model_picks.read(path)}
    assert stored['selected']['open_check'] == 'met'
    assert stored['late']['open_check'] == ''                 # a 10:10 entry is not a 09:45 check
    # A filled value is never rewritten by a later pass, whatever the bars say now.
    model_picks.score(path, now=now, bars_for=lambda t: bars())
    assert {r['kind']: r for r in model_picks.read(path)}['selected']['open_check'] == 'met'


def test_a_late_pick_scored_fresh_gets_no_0945_check(tmp_path):
    import model_picks
    path = tmp_path / 'picks.csv'
    frame = bars()
    for t in ('10:10', '15:55'):
        extra = frame.iloc[-1:].copy()
        extra.index = [pd.Timestamp('2026-09-25 %s' % t, tz=ET)]
        frame = pd.concat([frame, extra])
    model_picks.write([{'session': '2026-09-25', 'model': 'claude', 'kind': 'late', 'side': 'LONG',
                        'ticker': 'AAA.TO', 'entry_time': '10:10'}], path)
    now = dt.datetime(2026, 9, 25, 17, 0, tzinfo=ET)
    assert model_picks.score(path, now=now, bars_for=lambda t: frame) == 1
    assert model_picks.read(path)[0]['open_check'] == ''
