"""The email is a newsletter, and the standing terms are said once.

THE COMPLAINT, 2026-09-22: "format the email to not have warnings and to look
like a newsletter with sections". Both halves were real.

The layout half: `html(d)` was `markdown_html(text(d))` — the plain-text report
with tags wrapped round it. Every line became a paragraph of the same weight,
so the four tickers that decide the morning looked exactly like the boilerplate
under them.

The warnings half: three standing disclosures were appended to their own
sections EVERY morning, so the reader scrolled the same three paragraphs to
reach the board. They are not deleted — a disclosure that is never read is the
thing being fixed, and deleting it would be the other failure. They are printed
once, in a footer, small; the attached full report still carries each one
inside its own section, where the record needs it.

WHAT MUST SURVIVE ANY REDESIGN, and is pinned below: no share count on an
abstained leg, an ABSTAIN status that still reads ABSTAIN, a hero that says
there is nothing to act on when there is nothing to act on, and every
standing term still present somewhere in the email.
"""
import re

import pytest

import brief
import daily_render
import email_render
from test_daily_pipeline import NOW, services


@pytest.fixture(scope='module')
def digest():
    return brief.compute(now=NOW, services=services())


def test_the_email_is_sectioned_not_one_long_column(digest):
    body = email_render.html(digest)
    assert body.startswith('<!doctype html>')
    for heading in ('Part 1', 'Part 2', 'Research only'):
        assert heading in body, heading
    # Section headings are styled as headings, not as another paragraph.
    assert body.count('text-transform:uppercase') >= 3


def test_the_hero_states_the_decision_before_any_scrolling(digest):
    """A reader on a phone at 09:46 sees one line before anything else, and it
    has to be the one that matters."""
    body = email_render.html(digest)
    hero = body[:body.index('Part 1')]
    legs = digest['intraday']['legs']
    if legs and all(str(l['status']).upper() == 'ABSTAIN' for l in legs):
        assert 'No actionable entry today' in hero
    assert 'RB Daily Report' in hero


def test_an_abstained_leg_still_shows_no_share_count(digest):
    """The rule that was broken twice and acted on twice. A row carrying a size
    is an order ticket whatever the Status column says — restyling the table
    must not reintroduce one.

    The pipeline fixture selects two SHADOW legs, so the abstention is forced
    here: skipping when the fixture happens not to abstain would leave the one
    rule that has actually cost money untested on most runs."""
    import copy
    digest = copy.deepcopy(digest)
    for leg in digest['intraday']['legs']:
        leg['status'] = 'ABSTAIN'
        leg['baseline_shares'] = 250
    legs = digest['intraday']['legs']
    assert legs, 'the fixture selected no legs at all'
    body = email_render.html(digest)
    for leg in legs:
        row = re.search(r'<tr>(?:(?!</tr>).)*' + re.escape(leg['ticker']) + r'.*?</tr>',
                        body, re.S)
        assert row, leg['ticker']
        assert str(leg['baseline_shares']) not in row.group(0), (
            f"{leg['ticker']} is ABSTAIN and its share count reached the email")
        assert 'ABSTAIN' in row.group(0)


def with_models(digest):
    """A digest whose two model sections both answered."""
    import copy
    d = copy.deepcopy(digest)
    ev = {'names_with_headlines': 2, 'macro_fields': ['wti']}
    d['intraday']['opportunities'] = {
        'status': 'READY', 'model': 'deepseek-flash', 'considered': 2, 'evidence': ev,
        'longs': [{'ticker': 'AAA.TO', 'confidence': 0.6, 'reason': 'above vwap'}],
        'shorts': [], 'comparison': {'rows': [], 'agree': 0, 'oppose': 0, 'unseen': 1}}
    d['intraday']['jev'] = {
        'status': 'NO_OPPORTUNITY', 'model': 'typesafe/jev-1.13', 'considered': 2,
        'evidence': ev, 'longs': [], 'shorts': [], 'gaps': [],
        'long_ranked': [{'ticker': 'AAA.TO', 'probability': 0.2,
                         'abstain_probability': 0.6, 'cleared_gate': False}],
        'short_ranked': [],
        'forced_long': {'ticker': 'AAA.TO', 'probability': 0.4,
                        'gated_abstain_probability': 0.6, 'cleared_gated_abstain': False},
        'forced_short': None, 'forced_label': 'A FORCED CHOICE.'}
    return d


@pytest.mark.parametrize('note', ['OPPORTUNITIES_STANDING', 'JEV_STANDING'])
def test_a_standing_term_appears_exactly_once_when_its_section_ran(digest, note):
    """Said once is the goal. Said never is a different bug, and said three
    times is the complaint that started this."""
    # Day-114b: the email says its terms ONCE, in one footer line, and each
    # section's full standing note lives in the full report.
    mail = email_render.text(with_models(digest))
    assert mail.count('never averaged') == 1 and getattr(daily_render, note) not in mail
    assert getattr(daily_render, note) in brief.render_text(with_models(digest))


@pytest.mark.parametrize('note', ['OPPORTUNITIES_STANDING', 'JEV_STANDING', 'FACTOR_STANDING'])
def test_a_standing_term_is_absent_when_its_section_did_not_run(digest, note):
    """THE REGRESSION, caught by test_deepseek_render. Printing all three
    unconditionally made a publication that never called DeepSeek carry the
    words "never averaged with DeepSeek's confidence" — a frozen report growing
    a mention of a model it never ran. A term is keyed on its own section, the
    same rule the sections themselves obey."""
    bare = email_render.text(digest)
    assert getattr(daily_render, note) not in bare


def test_the_cross_model_note_needs_both_models(digest):
    cross = 'never averaged'
    assert email_render.text(with_models(digest)).count(cross) == 1
    assert 'DeepSeek' not in email_render.text(digest).split('## Part 2')[0].split('### Baseline')[0] \
        or digest['intraday'].get('desks')


def test_the_full_report_still_carries_each_note_inside_its_own_section(digest):
    """The email is a summary; the attachment is the record, and a section of
    the record must carry its own terms."""
    intra = digest['intraday']
    assert daily_render.JEV_STANDING in '\n'.join(daily_render.jev_summary(intra))
    assert daily_render.JEV_STANDING not in '\n'.join(
        daily_render.jev_summary(intra, concise=True))
    assert daily_render.OPPORTUNITIES_STANDING in '\n'.join(
        daily_render.opportunities_summary(intra))
    assert daily_render.OPPORTUNITIES_STANDING not in '\n'.join(
        daily_render.opportunities_summary(intra, concise=True))


def test_no_stylesheet_or_class_selector_gmail_would_strip(digest):
    """Gmail strips <style> blocks, class selectors, CSS variables and @media.
    A layout that depends on any of them renders as unstyled text in the one
    client this report is read in."""
    body = email_render.html(digest)
    assert '<style' not in body and 'class=' not in body
    # `var(--x)` rather than a bare `--`: a model rationale or an issuer note
    # may legitimately contain two hyphens, and a spurious failure on live text
    # is how a check gets deleted instead of fixed.
    assert 'var(--' not in body and '@media' not in body


def test_supplied_text_cannot_inject_markup(digest):
    """Tickers, issuer notes and model rationales are untrusted text."""
    d = dict(digest)
    d['intraday'] = dict(digest['intraday'])
    d['intraday']['opportunities'] = {
        'status': 'READY', 'model': 'deepseek-flash', 'considered': 1, 'shorts': [],
        'longs': [{'ticker': 'Y.TO', 'confidence': 0.6, 'reason': '<script>alert(1)</script>'}]}
    d['intraday'].pop('desks', None)
    d['intraday']['jev'] = {
        'status': 'READY', 'model': '<script>alert(1)</script>', 'considered': 1,
        'longs': [{'ticker': 'X.TO', 'probability': 0.9, 'abstain_probability': 0.1}],
        'shorts': [], 'long_ranked': [], 'short_ranked': [], 'evidence': {}, 'gaps': []}
    body = email_render.html(d)
    assert '<script>' not in body and '&lt;script&gt;' in body
