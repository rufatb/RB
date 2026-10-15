"""The council flash (owner, 2026-10-06): the council's decision by email the
moment it is sealed, ahead of the 09:46 report."""
import datetime as dt
import json

import council_flash as F

ET = F.ET
AT = dt.datetime(2026, 10, 6, 9, 0, tzinfo=ET)


def council(status='READY', picks=('P1',), stances=None):
    stances = stances or dict.fromkeys(('Claude', 'DeepSeek', 'Gemini'), 'ENDORSE')
    votes = {m: {'stance': s, 'conviction': 0.6, 'argument': 'rows say so'} for m, s in stances.items()}
    endorse = [m for m, s in stances.items() if s == 'ENDORSE']
    return {'session': '2026-10-06', 'status': status, 'picks': list(picks),
            'asked_at': '2026-10-06T08:57:55-04:00', 'finished_at': '2026-10-06T08:58:23-04:00',
            'positions': [{'id': 'P1', 'ticker': 'CVE.TO', 'side': 'SHORT', 'lead': 'Gemini',
                           'reason': 'dilution selling', 'invalid_at': 45.81}],
            'tally': {'members': ['Claude', 'DeepSeek', 'Gemini'], 'absent': [],
                      'rows': [{'id': 'P1', 'side': 'SHORT', 'ticker': 'CVE.TO',
                                'consensus': status == 'READY', 'endorse': endorse,
                                'oppose': [m for m, s in stances.items() if s == 'OPPOSE'],
                                'seats': endorse, 'votes': votes, 'weakest': 0.6}]}}


# Day-129: a turned-down position is no runner-up (E 1, O 2); one with a lone
# endorsement and no objection is (E 1, O 0).
TURNED_DOWN = {'Claude': 'ENDORSE', 'DeepSeek': 'OPPOSE', 'Gemini': 'OPPOSE'}
ONE_ENDORSES = {'Claude': 'ENDORSE', 'DeepSeek': 'ABSTAIN', 'Gemini': 'ABSTAIN'}


def write(tmp_path, obj):
    (tmp_path/'council.json').write_text(json.dumps(obj))


def test_flash_carries_the_decision_and_its_wrong_if(tmp_path):
    write(tmp_path, council())
    code, info = F.wait(tmp_path, 0, now_fn=lambda: AT)
    assert code == 0 and info['subject'] == 'RB Council Flash — 2026-10-06 — SHORT CVE.TO (3 of 3 endorse)'
    text = (tmp_path/'flash'/'report.txt').read_text()
    assert 'above 45.81' in text and 'decided at 08:58 ET (before the open)' in text
    assert 'not yet checked against the open' in text
    assert (tmp_path/'flash'/'report.html').read_text().startswith('<!doctype html>')


def test_the_subject_never_blocks_the_report():
    """Every sender skips the report when it finds "RB Daily Report — <today>"."""
    for c in (council(), council('NO_CONSENSUS', (), TURNED_DOWN), council('NO_CONSENSUS', (), ONE_ENDORSES)):
        import council as K
        assert 'RB Daily Report' not in F.subject('2026-10-06', K.top_two(c))


def test_no_consensus_still_flashes_and_says_so(tmp_path):
    write(tmp_path, council('NO_CONSENSUS', (), TURNED_DOWN))
    code, info = F.wait(tmp_path, 0, now_fn=lambda: AT)
    assert code == 0 and info['subject'].endswith('no consensus — nothing to act on')
    text = (tmp_path/'flash'/'report.txt').read_text()
    assert 'No runner-up: every other position drew at least as many objections as endorsements.' in text


def test_a_runner_up_is_flashed_labelled_and_never_as_a_pick(tmp_path):
    """Day-129: with no consensus, the best remaining position is shown, labelled."""
    write(tmp_path, council('NO_CONSENSUS', (), ONE_ENDORSES))
    code, info = F.wait(tmp_path, 0, now_fn=lambda: AT)
    assert code == 0
    assert info['subject'] == ('RB Council Flash — 2026-10-06 — no consensus · '
                               'runner-up, no consensus: SHORT CVE.TO')
    text = (tmp_path/'flash'/'report.txt').read_text()
    assert 'No consensus today — no council pick.' in text
    assert ('Runner-up — no consensus, not a council pick: SHORT CVE.TO (1 of 3 endorse; named best '
            'by 1); wrong if above 45.81. Gemini: dilution selling') in text
    assert '| 1 | SHORT CVE.TO' not in text                 # never a row of the picks table


def test_waits_for_the_council_then_stops_at_0944(tmp_path):
    assert F.wait(tmp_path, 0, now_fn=lambda: AT)[0] == 2
    late = AT.replace(hour=9, minute=44)
    assert F.wait(tmp_path, 0, now_fn=lambda: late)[1]['status'] == 'TOO_LATE'
    write(tmp_path, {**council(), 'session': '2026-10-05'})          # yesterday's is not today's
    assert F.wait(tmp_path, 0, now_fn=lambda: AT)[0] == 2


def test_a_council_that_did_not_sit_sends_nothing(tmp_path):
    write(tmp_path, {**council(), 'status': 'UNAVAILABLE', 'reason': 'fewer than two members'})
    code, info = F.wait(tmp_path, 0, now_fn=lambda: AT)
    assert code == 3 and info['status'] == 'NOTHING'


def test_sent_once(tmp_path):
    write(tmp_path, council())
    F.record(tmp_path, 'abc', now=AT)
    assert F.wait(tmp_path, 0, now_fn=lambda: AT)[0] == 4


def test_morning_prompt_sends_the_flash_before_the_wait():
    from pathlib import Path
    body = (Path(__file__).resolve().parent.parent/'ROUTINE_PROMPT.md').read_text()
    assert body.index('council_flash.py') < body.index('python morning_wait.py')


# ── day-127: exposure line and the open check ───────────────────────────────

OPEN = dt.datetime(2026, 10, 6, 9, 31, tzinfo=ET)


def quote_at(price, when=OPEN, prev=44.86, open_=44.48):
    def q(symbol):
        return {'price': price if symbol == 'CVE.TO' else 28.5, 'open': open_, 'previousClose': prev,
                'timestamp': when.timestamp()}
    return q


def test_flash_names_the_exposure_and_the_prior_session(tmp_path):
    write(tmp_path, council())
    F.wait(tmp_path, 0, now_fn=lambda: AT)
    text = (tmp_path/'flash'/'report.txt').read_text()
    assert 'Exposure: SHORT CVE.TO: Energy, moves with XEG.TO — in effect a bet on crude oil' in text
    assert 'describes 2026-10-05, the prior session' in text


def test_open_check_waits_for_0931_then_applies_e1(tmp_path):
    write(tmp_path, council())
    assert F.wait_open(tmp_path, 0, now_fn=lambda: AT, quote=quote_at(44.5))[0] == 2
    code, info = F.wait_open(tmp_path, 0, now_fn=lambda: OPEN, quote=quote_at(44.5))
    assert code == 0 and info['subject'].endswith('SHORT CVE.TO STILL VALID')
    text = (tmp_path/'flash'/'open_report.txt').read_text()
    # No brief staged here, so no ATR: the distance prints, with no reach call.
    assert ('| SHORT CVE.TO | STILL VALID | above 45.81 | 2.9% away (normal range unknown) '
            '| 44.5 at 09:31 | +0.85% |') in text


def test_open_check_voids_a_position_past_its_wrong_if(tmp_path):
    write(tmp_path, council())
    code, info = F.wait_open(tmp_path, 0, now_fn=lambda: OPEN, quote=quote_at(45.90))
    assert code == 0 and info['subject'].endswith('SHORT CVE.TO VOID')


def test_a_stale_quote_is_not_checked(tmp_path):
    write(tmp_path, council())
    yesterday = OPEN - dt.timedelta(days=1)
    F.wait_open(tmp_path, 0, now_fn=lambda: OPEN, quote=quote_at(45.90, when=yesterday))
    assert 'NOT CHECKED' in (tmp_path/'flash'/'open_subject.txt').read_text()


def test_open_check_sends_once_and_skips_a_day_without_picks(tmp_path):
    write(tmp_path, council('NO_CONSENSUS', (), TURNED_DOWN))
    assert F.wait_open(tmp_path, 0, now_fn=lambda: OPEN, quote=quote_at(44.5))[1]['status'] == 'NOTHING'
    write(tmp_path, council())
    F.record(tmp_path, 'x', now=OPEN, name=F.OPEN_SENT)
    assert F.wait_open(tmp_path, 0, now_fn=lambda: OPEN, quote=quote_at(44.5))[0] == 4


def test_the_open_check_covers_the_runner_up_labelled(tmp_path):
    write(tmp_path, council('NO_CONSENSUS', (), ONE_ENDORSES))
    code, info = F.wait_open(tmp_path, 0, now_fn=lambda: OPEN, quote=quote_at(44.5))
    assert code == 0 and info['subject'].endswith('— runner-up SHORT CVE.TO STILL VALID')
    text = (tmp_path/'flash'/'open_report.txt').read_text()
    assert '| SHORT CVE.TO (runner-up, no consensus) | STILL VALID | above 45.81 |' in text


def test_morning_prompt_runs_the_open_check_before_the_wait():
    from pathlib import Path
    body = (Path(__file__).resolve().parent.parent/'ROUTINE_PROMPT.md').read_text()
    assert body.index('--open-check') < body.index('python morning_wait.py')


def test_a_uranium_miner_is_not_an_oil_bet():
    """2026-10-07: the flash called CCO.TO (Cameco) 'a bet on crude oil'. Day-135
    (2026-10-15): it still 'moved with XEG.TO', a fund its daily moves do not
    follow (correlation -0.08 over a year, 0.88 with URNM)."""
    import exposure
    line = exposure.exposure_line([{'side': 'LONG', 'ticker': 'CCO.TO'}, {'side': 'SHORT', 'ticker': 'CVE.TO'}])
    assert 'LONG CCO.TO: uranium miner, moves with URNM — in effect a bet on uranium' in line
    assert 'SHORT CVE.TO: Energy, moves with XEG.TO — in effect a bet on crude oil' in line
    assert exposure.position_exposure('NXE.TO')['etf'] == 'URNM'


# ── day-135 (owner, 2026-10-15): a stop out of reach, the move already made ──

OCT15 = dt.datetime(2026, 10, 15, 9, 31, tzinfo=ET)


def oct15_council():
    """10-15's Top 2 as the council sealed it: two shorts, two sectors."""
    votes = {m: {'stance': 'ENDORSE', 'conviction': 0.7, 'argument': 'rows say so'}
             for m in ('Claude', 'DeepSeek', 'Gemini', 'Jev')}
    row = lambda pid, t: {'id': pid, 'side': 'SHORT', 'ticker': t, 'consensus': True,
                          'endorse': list(votes), 'oppose': [], 'seats': list(votes),
                          'votes': votes, 'weakest': 0.7}
    return {'session': '2026-10-15', 'status': 'READY', 'picks': ['P4', 'P3'],
            'finished_at': '2026-10-15T09:01:37-04:00',
            'positions': [{'id': 'P4', 'ticker': 'CLS.TO', 'side': 'SHORT', 'lead': 'Gemini',
                           'reason': 'selloff', 'invalid_at': 486.55},
                          {'id': 'P3', 'ticker': 'CCO.TO', 'side': 'SHORT', 'lead': 'Gemini',
                           'reason': 'breakdown', 'invalid_at': 121.29}],
            'tally': {'members': list(votes), 'absent': [],
                      'rows': [row('P4', 'CLS.TO'), row('P3', 'CCO.TO')]}}


def oct15_quote(symbol):
    q = {'CLS.TO': (434.25, 438.0, 460.44), 'CCO.TO': (112.46, 113.45, 115.97)}.get(symbol, (30.0, 30.0, 30.0))
    return {'price': q[0], 'open': q[1], 'previousClose': q[2], 'timestamp': OCT15.timestamp()}


def test_reach_measures_the_distance_to_the_wrong_if_in_normal_days():
    x = F.reach('SHORT', 486.55, 434.25, 6.7308)          # CLS.TO at 09:31 on 10-15
    assert round(x['pct'], 2) == 12.04 and round(x['days'], 2) == 1.79 and x['out_of_reach']
    near = F.reach('LONG', 99.0, 100.0, 2.0)               # 1% below a 2%-ATR name: reachable
    assert round(near['pct'], 6) == 1.0 and round(near['days'], 6) == 0.5 and near['out_of_reach'] is False
    assert F.reach('SHORT', 100.0, 101.0, 2.0) is None      # already crossed: that is E1's VOID
    assert F.reach('SHORT', None, 101.0, 2.0) is None
    unknown = F.reach('SHORT', 110.0, 100.0, None)
    assert unknown['days'] is None and unknown['out_of_reach'] is None


def test_10_15_would_have_said_the_stops_were_out_of_reach(tmp_path):
    """10-15 printed STILL VALID twice and both shorts lost; the levels were 1.8
    and 2.0 normal days away, so the check could never have said anything else."""
    rows = F.check_open(oct15_council(), OCT15, quote=oct15_quote,
                        atr={'CLS.TO': 6.7308, 'CCO.TO': 3.8944})
    subj, text, html = F.compose_open(oct15_council(), rows, OCT15)
    assert subj.endswith('SHORT CLS.TO STILL VALID, stop out of reach · '
                         'SHORT CCO.TO STILL VALID, stop out of reach')
    assert '12.0% away = 1.8 normal days: OUT OF REACH, not a usable stop' in text
    assert '7.9% away = 2.0 normal days: OUT OF REACH, not a usable stop' in text
    assert '+4.87% (0.7 normal days)' in text                # the open had already moved it
    assert 'Already moved at the open, before any entry: SHORT CLS.TO opened 4.9% its way' in text
    assert '⚠ Both picks are SHORT' in text and '⚠ Both picks are SHORT' in html
    assert 'border-left:3px solid #8a5f19' in html           # a caution, never a quiet line


def test_a_reachable_stop_and_mixed_sides_say_nothing_extra():
    c = oct15_council()
    c['positions'][1].update(side='LONG', invalid_at=110.0)
    c['tally']['rows'][1]['side'] = 'LONG'
    rows = F.check_open(c, OCT15, quote=oct15_quote, atr={'CLS.TO': 6.7308, 'CCO.TO': 3.8944})
    subj, text, _ = F.compose_open(c, rows, OCT15)
    assert subj.endswith('LONG CCO.TO STILL VALID')          # 2.2% away, 0.6 normal days
    assert '2.2% away = 0.6 normal days |' in text
    assert 'Both picks are' not in text


def test_the_open_check_reads_the_atr_from_todays_brief_only(tmp_path):
    assert F.atr_map(tmp_path, OCT15, {'CLS.TO'}) == {}       # no brief: no reach call, no failure


def test_the_flash_and_report_warn_when_both_picks_point_one_way(tmp_path):
    import council as K
    import top_picks
    sec = K.top_two(oct15_council(), previous={})
    line = top_picks.direction_line(sec)
    assert line.startswith('⚠ Both picks are SHORT, so they share one exposure')
    assert 'If the market turns up, both tend to lose at once.' in line
    assert 'Being in different sectors does not make them separate bets.' in line
    table = top_picks.table(sec, concise=True)
    assert table.index(line) == max(i for i, x in enumerate(table) if x.startswith('|')) + 1
    write(tmp_path, oct15_council())
    F.wait(tmp_path, 0, now_fn=lambda: dt.datetime(2026, 10, 15, 9, 2, tzinfo=ET))
    html = (tmp_path/'flash'/'report.html').read_text()
    hero = html.split('</tr>')[1]                           # the hero row, above the tables
    assert 'Both picks are SHORT' in hero


def test_every_view_of_the_top_2_carries_the_one_direction_warning():
    """Report email hero, page (above its table, once), noon email (hero and text)."""
    import council as K
    import email_render as E
    import noon_check as N
    import report_page as P
    sec = K.top_two(oct15_council(), previous={})
    assert 'Both picks are SHORT' in E._hero({'intraday': {'top_two': sec}})
    page = P._top_two_section({'top_two': sec})
    assert page.count('Both picks are SHORT') == 1 and page.index('g-caution') < page.index('<table>')
    rows = [{**p, 'status': 'CHECKED', 'entry': 1.0, 'last': 1.0, 'at': '12:00', 'since_entry': -1.0,
             'crossed': False, 'etf': 'XIT.TO', 'etf_move': 0.5} for p in sec['picks']]
    _, text, html = N.compose('2026-10-15', rows, 'the 09:46 report', dt.datetime(2026, 10, 15, 12, tzinfo=ET))
    assert 'Both picks are SHORT' in text and 'Both picks are SHORT' in html.split('</tr>')[1]
    # A runner-up is never a pick: one pick plus a same-side runner-up says nothing.
    one = {**sec, 'picks': sec['picks'][:1], 'runner_up': {**sec['picks'][1], 'runner_up': True}}
    assert top_direction(one) is None and 'Both picks' not in E._hero({'intraday': {'top_two': one}})


def top_direction(section):
    import top_picks
    return top_picks.direction_line(section)


def test_the_warning_mark_is_the_one_the_email_styles():
    import email_render as E
    import top_picks
    assert top_picks.DIRECTION_MARK == E.WARN_MARK
    html = E.html_from_text('# T\nstamp\n## S\n⚠ Both picks are SHORT, so they share one exposure.\nplain line')
    assert 'border-left:3px solid #8a5f19' in html and '<p style="font:14px/1.6' in html
