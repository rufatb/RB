"""Day-127 (PREREGISTER_day127_dated.md): every input carries its date, so no
model reads the prior session's move or a pre-market print as today's."""
import datetime as dt
import json

import deepseek_opportunities as O

NOW = dt.datetime(2026, 10, 6, 9, 0, tzinfo=O.ET)


def rows_with_news():
    rows = O.control_universe()
    rows[0]['headlines'] = [{'title': 'Deal announced', 'published_at': '2026-10-05T06:00:00-04:00',
                             'evidence_metadata': {'classification': 'UNCLASSIFIED'}}]
    return rows


def test_the_payload_names_the_prior_session_and_ages_every_input():
    req = O.build_request(rows_with_news(), {
        'wti': {'value': 87.4, 'as_of': '2026-10-06T08:44:43-04:00', 'change_pct': -2.3},
        'tsx': {'value': 1.0, 'as_of': '2026-10-05T16:20:01-04:00', 'change_pct': 0.1}}, NOW)
    p = req['payload']
    assert p['data_dates'] == {'today': '2026-10-06', 'rows_describe': '2026-10-05',
                               'written_at': '2026-10-06T09:00-04:00'}
    assert p['candidates'][0]['headlines'][0]['age_hours'] == 27.0
    assert p['macro']['wti']['window'] == 'PRE-MARKET today (08:44 ET)'
    assert p['macro']['tsx']['window'] == 'PRIOR SESSION 2026-10-05'
    # The prompt TEXT is day125-v4's: every added instruction failed the control
    # (PREREGISTER_day127_dated.md, amendment 1). Re-adding one needs a new control.
    assert 'data_dates' not in O.SYSTEM_PROMPT


def test_monday_reads_back_to_friday():
    assert O.prior_session(dt.date(2026, 10, 5)) == dt.date(2026, 10, 2)


def test_jev_and_the_council_see_the_same_dates():
    import jev_opportunities as J
    seen = {}

    def poster(body, key, timeout):
        seen['state'] = body['state']
        raise ValueError('STOP')
    J.rank(rows_with_news(), now=NOW, key='k', poster=poster)
    assert seen['state']['data_dates']['rows_describe'] == '2026-10-05'
    assert seen['state']['candidates'][0]['headlines'][0]['age_hours'] == 27.0
    import council as K
    text = K.brief_text({'session': '2026-10-06', 'positions': [], 'discussion': [], 'rows': [],
                         'data_dates': O.data_dates(NOW, dt.date(2026, 10, 5))})
    assert 'DATA DATES' in text and '2026-10-05' in text
