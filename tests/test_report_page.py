"""The daily HTML page, and the one rule it must enforce by construction.

The page was being rewritten by hand every morning. The standing instruction
for that rewrite had to shout "render NO share count on an ABSTAIN leg" in
capitals, because nothing enforced it — and a leg rendered with a size has
twice been acted on as an order. A renderer cannot be reminded; it can only be
built so the number has no path to the page.

`report_page.render` is pure: frozen digest in, string out. No clock, no
network, no writes.
"""
import json

import pytest

import report_page


def leg(ticker, status='ABSTAIN', **over):
    row = {'ticker': ticker, 'side': 'LONG', 'status': status,
           'signal_reference': 12.34, 'entry_reference': None, 'entry_spread_bps': None,
           'baseline_shares': 4242, 'baseline_alloc': 987654.0, 'reasons': [], 'quote': {}}
    row.update(over)
    return row


def digest(legs=(), status='ON_TIME', **over):
    out = {
        'session': '2026-09-16', 'generated_at': '2026-09-16T09:46:12-04:00',
        'report_status': status, 'schema_version': 2,
        'provenance': {'code_commit': 'abcdef1234567890'},
        'errors': [], 'biotech': {'errors': []},
        'intraday': {
            'contract': '09:46 entry / 15:59 exit, same session',
            'model_claim': 'No demonstrated predictive edge.',
            'legs': list(legs), 'recorded_today': [],
            'res': {'n_names': 21, 'source': 'yahoo_direct'},
            'record': {'hits': 52, 'n': 107, 'rate': .486, 'mean': -.058,
                       'net_rate': .5, 'net_mean': .247, 'net_n': 6, 'net_unpriced': 101},
            'risk_evidence': {'rate': {'rate': .486, 'ci95': [.375, .597],
                                       'mde80_pp': 23.8, 'n': 107, 'sessions': 39},
                              'calibration': []},
            'exact_record': {'scored_legs': 0},
        }}
    out['intraday'].update(over.pop('intraday', {}))
    out.update(over)
    return out


def body(html):
    """Just the legs table, so a match cannot come from CSS or a footnote."""
    return html.split('<tbody>')[1].split('</tbody>')[0]


# ── the rule ──────────────────────────────────────────────────────────────

def test_an_abstained_leg_renders_no_share_count():
    html = report_page.render(digest([leg('AC.TO')]))
    assert '4242' not in body(html), 'a size reached an abstained row'
    assert report_page.ABSTAIN_CELL in body(html)


def test_an_abstained_leg_renders_no_dollar_allocation():
    html = report_page.render(digest([leg('AC.TO')]))
    assert '987,654' not in html and '987654' not in html


@pytest.mark.parametrize('status', ['ABSTAIN'])
def test_the_helper_itself_cannot_emit_a_size(status):
    """Enforced at the one place a number becomes text, so a future table
    column cannot reintroduce it by accident."""
    assert report_page._alloc_cell(leg('X', status), 'baseline_shares') == report_page.ABSTAIN_CELL
    assert report_page._alloc_cell(leg('X', status), 'baseline_alloc') == report_page.ABSTAIN_CELL


def test_an_eligible_leg_does_render_its_size():
    """The rule is about abstention, not about hiding everything — an eligible
    leg on an on-time board is the one case a size is meaningful."""
    assert report_page._alloc_cell(leg('X', 'ELIGIBLE'), 'baseline_shares') == '4242'


def test_a_missing_size_never_renders_as_none():
    assert report_page._alloc_cell(leg('X', 'ELIGIBLE', baseline_shares=None),
                                   'baseline_shares') == report_page.ABSTAIN_CELL


# ── entry versus informational ────────────────────────────────────────────

def test_an_all_abstain_board_is_not_an_entry_even_when_on_time():
    html = report_page.render(digest([leg('AC.TO')], status='ON_TIME'))
    assert 'Not an executable entry' in html


def test_a_late_run_is_not_an_entry():
    html = report_page.render(digest([leg('AC.TO', 'ELIGIBLE')],
                                     status='INFORMATIONAL — outside 09:46 delivery minute'))
    assert 'Not an executable entry' in html


def test_an_on_time_eligible_board_is_an_entry():
    html = report_page.render(digest([leg('AC.TO', 'ELIGIBLE')], status='ON_TIME'))
    assert 'Not an executable entry' not in html
    assert 'Morning entry board' in html


# ── an empty board is not a zero-opportunity claim ────────────────────────

def test_an_empty_board_says_why_it_is_empty():
    html = report_page.render(digest([]))
    assert 'not a statement that no opportunity existed' in html


# ── the interval figure ───────────────────────────────────────────────────

def test_the_interval_marks_stay_inside_the_drawing():
    """One scale places band, point and coin line; a rate outside 30-70% is
    clamped so no mark escapes its container."""
    d = digest([leg('A')])
    d['intraday']['risk_evidence']['rate'] = {'rate': .95, 'ci95': [.90, .99],
                                              'mde80_pp': 5, 'n': 500, 'sessions': 100}
    html = report_page.render(d)
    import re
    for value in re.findall(r'(?:left|width):([\d.]+)%', html):
        assert 0 <= float(value) <= 100, value


def test_an_interval_containing_a_coin_flip_says_so():
    html = report_page.render(digest([leg('A')]))
    assert 'not distinguishable from a coin flip' in html


def test_an_interval_excluding_a_coin_flip_does_not_say_so():
    d = digest([leg('A')])
    d['intraday']['risk_evidence']['rate'] = {'rate': .62, 'ci95': [.55, .69],
                                              'mde80_pp': 8, 'n': 400, 'sessions': 90}
    html = report_page.render(d)
    assert 'not distinguishable from a coin flip' not in html
    assert 'excludes 50%' in html


def test_a_record_with_no_interval_does_not_invent_one():
    d = digest([leg('A')])
    d['intraday']['risk_evidence']['rate'] = {}
    html = report_page.render(d)
    assert 'interval unavailable' in html


# ── faults reach the reader in words ──────────────────────────────────────

def test_an_acquisition_fault_is_named_in_english():
    d = digest([leg('A')], errors=[{'layer': 'intraday', 'error': 'TimeoutExpired'}])
    html = report_page.render(d)
    assert 'did not answer inside its budget' in html and 'TimeoutExpired' in html


def test_a_record_hole_is_carried_onto_the_page():
    d = digest([leg('A')])
    d['intraday']['record']['record_gaps'] = {'missing': ['2026-09-09'], 'zero_pick': []}
    assert 'RECORD HAS A HOLE' in report_page.render(d)


# ── purity and safety ─────────────────────────────────────────────────────

def test_rendering_does_not_mutate_the_frozen_digest():
    d = digest([leg('A')])
    before = json.dumps(d, sort_keys=True, default=str)
    report_page.render(d)
    assert json.dumps(d, sort_keys=True, default=str) == before


def test_a_hostile_ticker_cannot_inject_markup():
    html = report_page.render(digest([leg('<script>alert(1)</script>')]))
    assert '<script>alert(1)</script>' not in html
    assert '&lt;script&gt;' in html


def test_the_page_names_itself_by_session():
    assert '<title>RB Report 2026-09-16</title>' in report_page.render(digest([]))


def test_both_themes_define_every_colour_token():
    """A token defined only inside a media block renders one theme's text on
    the other theme's ground."""
    html = report_page.render(digest([]))
    base = html.split(':root {')[1].split('}')[0]
    dark = html.split(':root[data-theme="dark"] {')[1].split('}')[0]
    names = lambda block: {line.split(':')[0].strip()
                           for line in block.split(';') if line.strip().startswith('--')}
    assert names(dark) <= names(base), names(dark) - names(base)
    assert '--ground' in names(base) and '--ink' in names(base)


# ── the factor section (added after it was found missing entirely) ─────────

def factor_digest(**snap):
    body = {'status': 'UNAVAILABLE', 'assessments': [], 'covered': 0, 'requested': 0,
            'gaps': ['DeepSeek inputs have not been prepared for this session.'],
            'shadow': {'rows': []}, 'model': None}
    body.update(snap)
    return digest([leg('AC.TO')], intraday={'deepseek': body})


def test_a_factor_layer_that_did_not_run_says_so_rather_than_vanishing():
    """A MISSING section reads as 'no signal'. That is a different claim from
    'not evaluated', and the first one is not true."""
    html = report_page.render(factor_digest())
    assert 'Factor research' in html
    assert 'not evaluated' in html


def test_assessments_are_rendered_with_their_leans():
    html = report_page.render(factor_digest(
        status='PARTIAL', covered=2, requested=60,
        assessments=[{'ticker': 'CNQ.TO', 'directional_lean': 'BULL', 'sentiment_score': .30,
                      'factor_rationale': 'Python gap +2.21% positive'},
                     {'ticker': 'TD.TO', 'directional_lean': 'NO_EDGE', 'sentiment_score': .10,
                      'factor_rationale': 'Python gap -0.49% negative'}]))
    assert 'CNQ.TO' in html and 'BULL' in html and '+0.30' in html
    assert 'NO_EDGE' in html
    assert '2 / 60' in html


def test_a_lean_is_never_presented_as_a_recommendation():
    html = report_page.render(factor_digest(
        status='PARTIAL', covered=1, requested=60,
        assessments=[{'ticker': 'CNQ.TO', 'directional_lean': 'BULL', 'sentiment_score': .30,
                      'factor_rationale': 'x'}]))
    assert 'not a recommendation' in html
    assert 'Nothing in this section is adopted' in html
    assert '0 name(s) cleared the registered threshold' in html


def test_threshold_passes_are_counted_from_the_shadow_rows():
    html = report_page.render(factor_digest(
        status='PARTIAL', covered=1, requested=60,
        assessments=[{'ticker': 'A.TO', 'directional_lean': 'BULL', 'sentiment_score': .6,
                      'factor_rationale': 'x'}],
        shadow={'rows': [{'ticker': 'A.TO', 'status': 'CANDIDATE'},
                         {'ticker': 'B.TO', 'status': 'ABSTAIN'}]}))
    assert '1 name(s) cleared the registered threshold' in html
    assert 'do not enter the baseline board' in html


# ── the factor layer's own top two per side ───────────────────────────────

def shadow_digest(h1):
    return factor_digest(status='PARTIAL', covered=2, requested=130,
                         assessments=[{'ticker': 'A.TO', 'directional_lean': 'BULL',
                                       'sentiment_score': .4, 'factor_rationale': 'x'}],
                         shadow={'rows': [{'ticker': 'A.TO', 'status': 'CANDIDATE'}], 'h1': h1})


def test_the_top_two_comes_from_the_registered_arm_not_a_new_ranking():
    top = report_page._factor_top2({'h1': {
        'longs': [{'ticker': 'CNQ.TO', 'sided_score': .61, 'combined_probability': .61,
                   'quant_probability': .60, 'spread_bps': 7.2},
                  {'ticker': 'SU.TO', 'sided_score': .58, 'combined_probability': .58,
                   'quant_probability': .57, 'spread_bps': None}],
        'shorts': [{'ticker': 'TD.TO', 'sided_score': .59, 'combined_probability': .41,
                    'quant_probability': .42, 'spread_bps': 4.0}]}})
    assert [(r['side'], r['rank'], r['ticker']) for r in top] == [
        ('LONG', 1, 'CNQ.TO'), ('LONG', 2, 'SU.TO'), ('SHORT', 1, 'TD.TO')]


def test_never_more_than_two_per_side_reach_the_page():
    """MAX_PER_SIDE is 2 and the page must not widen it."""
    many = [{'ticker': f'T{i}.TO', 'sided_score': .6, 'combined_probability': .6,
             'quant_probability': .6, 'spread_bps': 1.0} for i in range(5)]
    top = report_page._factor_top2({'h1': {'longs': many, 'shorts': many}})
    assert len([r for r in top if r['side'] == 'LONG']) == 2
    assert len([r for r in top if r['side'] == 'SHORT']) == 2


def test_nothing_clearing_renders_nothing_rather_than_the_two_highest():
    """THE RULE. A top two taken from names that did not clear is a pick
    manufactured out of ties. Abstention is the answer, not a missing one."""
    block = report_page._factor_top2_block([], 0)
    assert 'Top two: none' in block
    assert 'manufactured out of ties' in block
    assert '<table' not in block


def test_an_all_no_edge_day_produces_no_top_two():
    """End to end: 23 NO_EDGE assessments, empty h1 — the real 2026-09-16 shape."""
    html = report_page.render(factor_digest(
        status='PARTIAL', covered=23, requested=130,
        assessments=[{'ticker': f'N{i}.TO', 'directional_lean': 'NO_EDGE',
                      'sentiment_score': 0.0, 'factor_rationale': 'x'} for i in range(23)],
        shadow={'rows': [], 'h1': {'longs': [], 'shorts': []}}))
    assert 'Top two: none' in html
    assert '0 name(s) cleared the registered threshold' in html


def test_a_selected_top_two_is_labelled_as_unadopted_research():
    html = report_page.render(shadow_digest(
        {'longs': [{'ticker': 'CNQ.TO', 'sided_score': .61, 'combined_probability': .61,
                    'quant_probability': .60, 'spread_bps': 7.2}], 'shorts': []}))
    assert 'CNQ.TO' in html and 'LONG #1' in html
    assert 'do not enter the baseline board' in html
    assert 'carry no size' in html
    assert 'not' in html and 'calibrated win probabilities' in html


# ── nearest misses: show the gate, never a substitute pick ────────────────

NEAR = {'rows': [
    {'ticker': 'TRP.TO', 'sided_score': .592, 'quant_probability': .60, 'status': 'ABSTAIN',
     'reason': 'Combined score below threshold or factor disagreement.'},
    {'ticker': 'CM.TO', 'sided_score': .563, 'quant_probability': .579, 'status': 'ABSTAIN',
     'reason': 'Combined score below threshold or factor disagreement.'},
    {'ticker': 'WIN.TO', 'sided_score': .61, 'quant_probability': .62, 'status': 'CANDIDATE',
     'reason': None}]}


def test_a_qualifying_name_is_never_listed_as_a_near_miss():
    near = report_page._nearest_misses(NEAR)
    assert 'WIN.TO' not in [r['ticker'] for r in near]
    assert [r['ticker'] for r in near] == ['TRP.TO', 'CM.TO']


def test_near_misses_are_labelled_as_not_picks():
    block = report_page._factor_top2_block([], 0, NEAR)
    assert 'Not picks' in block
    assert 'did not qualify' in block


def test_the_block_explains_that_a_lean_can_veto_a_high_score():
    """THE THING THE READER NEEDS. On 2026-09-16 TRP.TO scored 0.592 against a
    0.55 threshold and was still rejected — by the lean, not the number. A page
    that only says 'none' hides which gate bound."""
    block = report_page._factor_top2_block([], 0, NEAR)
    assert 'TRP.TO' in block and '0.592' in block
    assert 'vetoes the name however high' in block


def test_near_misses_are_not_shown_when_something_did_qualify():
    top = [{'side': 'LONG', 'rank': 1, 'ticker': 'WIN.TO', 'sided': .61,
            'combined': .61, 'quant': .62, 'spread': 3.0}]
    block = report_page._factor_top2_block(top, 1, NEAR)
    assert 'WIN.TO' in block
    assert 'Not picks' not in block and 'TRP.TO' not in block


def test_no_evaluated_rows_means_no_near_miss_table():
    assert '<table' not in report_page._factor_top2_block([], 0, {'rows': []})
    assert '<table' not in report_page._factor_top2_block([], 0, None)


# ── DeepSeek opportunities: the model's own picks, beside the board ──────────
# This is an OPINION printed next to a measured record. The risks are that a
# self-reported confidence reads as a probability, that a pick reads as an
# order, and that a name the engine never scored reads as one the engine
# rejected. Each of those has a test.

def opportunities(status='READY', rows=(), **over):
    out = {'status': status, 'model': 'deepseek-flash', 'considered': 39,
           'adopted': False, 'longs': [], 'shorts': [], 'gaps': [],
           'confidence_label': 'not a calibrated win probability',
           'comparison': {'rows': list(rows), 'agree': 0, 'oppose': 0,
                          'passed_over': 0, 'unseen': len(rows),
                          'comparable': 0, 'engine_only': []}}
    out.update(over)
    return out


def orow(ticker, side='LONG', confidence=0.65, verdict=report_page.O.UNSEEN, engine=None):
    return {'side': side, 'ticker': ticker, 'confidence': confidence,
            'reason': 'gap and rvol', 'engine_side': None,
            'engine_p_sided': engine, 'engine_status': None, 'verdict': verdict}


def test_the_model_picks_are_rendered_with_their_confidence():
    html = report_page._opportunities_section(
        {'opportunities': opportunities(rows=[orow('EMA.TO', confidence=0.6)])})
    assert 'EMA.TO' in html and '0.60' in html


def test_the_confidence_is_never_presented_as_a_win_probability():
    html = report_page._opportunities_section(
        {'opportunities': opportunities(rows=[orow('EMA.TO')])})
    assert 'NOT a calibrated win probability' in html
    assert 'never been scored against an outcome' in html


def test_the_two_numbers_are_never_blended_on_the_page():
    """Averaging a measured probability with an unmeasured self-report launders
    the second into the first."""
    html = report_page._opportunities_section(
        {'opportunities': opportunities(rows=[orow('AC.TO', engine=0.6)])})
    assert 'never combined' in html and 'never blended' in html


def test_a_pick_carries_no_share_count_and_no_dollar_figure():
    """A row carrying a size is an order ticket whatever the label says."""
    html = report_page._opportunities_section(
        {'opportunities': opportunities(rows=[orow('EMA.TO')])})
    assert '$' not in html and 'shares' not in html.lower()
    assert 'no size' in html


def test_a_name_the_engine_never_scored_says_so_rather_than_showing_a_number():
    html = report_page._opportunities_section(
        {'opportunities': opportunities(rows=[orow('EMA.TO')])})
    assert 'outside the engine universe' in html
    assert report_page.ABSTAIN_CELL in html


def test_no_opportunity_renders_the_abstention_and_its_control():
    """An empty section reads as 'no signal'; this must read as 'it answered
    no, and the harness can detect a planted edge'."""
    html = report_page._opportunities_section({'opportunities': opportunities('NO_OPPORTUNITY')})
    assert 'no opportunity on either side' in html
    assert 'planted long and a planted short' in html
    assert 'manufactured out of ties' in html


def test_an_unstaged_ranking_states_its_reason_in_one_line():
    html = report_page._opportunities_section(
        {'opportunities': {'status': 'UNAVAILABLE',
                           'reason': 'The opportunity ranking was not staged for this session.'}})
    assert 'not staged for this session' in html
    assert '<table' not in html


def test_a_missing_opportunities_key_still_renders_a_stated_absence():
    html = report_page._opportunities_section({})
    assert 'Not staged this session.' in html and '<table' not in html


def test_the_section_appears_in_the_page_beside_the_board():
    d = digest([leg('AC.TO')])
    d['intraday']['opportunities'] = opportunities(rows=[orow('EMA.TO')])
    html = report_page.render(d)
    assert html.index('DeepSeek opportunities') > html.index('Part 1 &middot; Intraday'.replace('&middot;', '·'))
    assert html.index('DeepSeek opportunities') < html.index('How reliable is this record?')


def test_agreement_and_opposition_are_visually_distinguished():
    agree = report_page._opportunities_section(
        {'opportunities': opportunities(rows=[orow('AC.TO', verdict=report_page.O.AGREE, engine=0.6)])})
    oppose = report_page._opportunities_section(
        {'opportunities': opportunities(rows=[orow('AC.TO', side='SHORT',
                                                   verdict=report_page.O.OPPOSE, engine=0.6)])})
    assert 'g-accent' in agree and 'g-alarm' not in agree
    assert 'g-alarm' in oppose


def test_a_reason_from_the_model_is_escaped_and_labelled_unverified():
    row = orow('EMA.TO')
    row['reason'] = '<script>alert(1)</script> rvol 3.1'
    html = report_page._opportunities_section({'opportunities': opportunities(rows=[row])})
    assert '<script>' not in html and '&lt;script&gt;' in html
    assert 'not verified fact' in html


def test_a_ranking_asked_after_the_open_is_labelled_as_a_diagnostic():
    """Same prior-session inputs, different instrument: the request was not
    blind to the day. The page must say so rather than let it read as a
    pre-open opinion."""
    snap = opportunities(rows=[orow('EMA.TO')])
    snap['diagnostic'] = True
    html = report_page._opportunities_section({'opportunities': snap})
    assert 'Current-time diagnostic' in html
    assert 'not a pre-open opinion' in html
    assert 'asked once, pre-open' not in html


def test_a_pre_open_ranking_carries_no_diagnostic_banner():
    html = report_page._opportunities_section(
        {'opportunities': opportunities(rows=[orow('EMA.TO')])})
    assert 'Current-time diagnostic' not in html
    assert 'asked once, pre-open' in html
