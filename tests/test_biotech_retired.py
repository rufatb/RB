"""Day-136: Part 2 (biotech) is retired by the owner (2026-10-19).

One switch, `biotech.RETIRED`. A report computed after it freezes the section
as RETIRED, and every view prints nothing for it. A report frozen before it
renders exactly as it did: the renderers read the frozen section, not the
switch.
"""
import json

import pytest

import biotech
import brief
import email_render
import late_picks
import prepare_delivery
import report_page
from test_daily_pipeline import NOW, services
from test_pool_widening import biotech_snapshot, daily_fetcher, run
from test_factor_pool_day101 import NOW as POOL_NOW, history  # noqa: F401  (fixture)


def plain_subject(d, monkeypatch):
    """The subject on a morning with no board-state warning to lead it."""
    monkeypatch.setattr(prepare_delivery, 'subject_state', lambda report: '')
    return prepare_delivery.subject(d)


def views(d):
    return {'email text': email_render.text(d), 'email html': email_render.html(d),
            'full text': brief.render_text(d), 'full html': brief.render_html(d),
            'page': report_page.render(d)}


def test_the_switch_is_on():
    assert biotech.RETIRED is True


def test_a_report_freezes_part_2_as_retired_and_never_reads_its_inputs(monkeypatch):
    s = services()
    s['biotech_inputs'] = lambda: pytest.fail('a retired Part 2 read its inputs')
    d = brief.compute(now=NOW, services=s)
    assert d['biotech']['status'] == 'RETIRED' and biotech.retired(d['biotech'])
    assert d['research_calendar']['events'] == [] and d['research_calendar']['retired']
    for name, body in views(d).items():
        assert 'Part 1' in body, name
        assert 'Part 2' not in body, name
        assert 'FORWARD CALENDAR' not in body, name
    assert plain_subject(d, monkeypatch).endswith('— Intraday')


def test_a_report_frozen_before_the_retirement_still_prints_its_part_2(monkeypatch):
    monkeypatch.setattr(biotech, 'RETIRED', False)
    d = brief.compute(now=NOW, services=services())
    monkeypatch.setattr(biotech, 'RETIRED', True)
    assert not biotech.retired(d['biotech'])
    assert 'Part 2' in email_render.text(d)
    assert 'Part 2' in brief.render_text(d)
    assert plain_subject(d, monkeypatch).endswith('— Intraday + Biotech')


def test_the_factor_pool_carries_no_us_rows(tmp_path, monkeypatch, history):
    result = run(tmp_path, monkeypatch, history, daily_fetcher=daily_fetcher())
    assert result['biotech_retired'] is True and result['biotech_added'] == 0
    assert 'biotech_error' not in result
    pool = json.loads((tmp_path/'deepseek_candidates.json').read_text())
    assert not any(c.get('market') == 'US' for c in pool['candidates'])


def test_an_injected_snapshot_still_reaches_the_kept_code(tmp_path, monkeypatch, history):
    """The retired path is the default only; a caller that hands the pool a
    snapshot (the kept tests) still exercises the code it kept."""
    result = run(tmp_path, monkeypatch, history, daily_fetcher=daily_fetcher(),
                 biotech_snapshot=biotech_snapshot(POOL_NOW))
    assert result['biotech_added'] == 2 and 'biotech_retired' not in result


def test_the_late_and_picks_only_emails_print_no_part_2(tmp_path):
    assert late_picks.biotech_part(tmp_path, NOW) == []
