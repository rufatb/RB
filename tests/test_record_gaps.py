"""A hole in the record must stay visible until it is explained.

Ported from day-95b (`kimi/day95-record-integrity`, C3) after verifying the
defect on this repo's own ledger rather than taking the branch's word for it.

THE DEFECT. `ledger.missing_sessions` anchors on `max(dates)` — the ledger's
LAST entry — and walks forward. So an interior gap is visible only while the
record ends at the gap. The moment any later session publishes, the anchor
jumps past the hole and the warning goes silent **exactly when the record
starts looking healthy again**. Four sessions went unrecorded here (2026-09-09
through 2026-09-14) and nothing would have said so afterwards.

`record_gaps` anchors on TODAY and walks backward, and knows about universe
prints, so it can tell "the run never happened" from "the run happened and
picked nothing". Those are different events and only one of them is a gap.
"""
import datetime as dt

import ledger


def trading(day):
    """Mon-Fri. Injected, so these tests need no calendar package or network."""
    return day.weekday() < 5


def rows(*dates):
    return [{'date': d, 'ticker': 'AC.TO'} for d in dates]


def prints(*dates):
    return [{'date': d, 'ticker': 'AC.TO', 'p945': '1.00'} for d in dates]


TODAY = dt.date(2026, 9, 14)          # Monday
# 09-08 Tue, 09-09 Wed, 09-10 Thu, 09-11 Fri — all trading days.


# ── the defect, stated as a test so it cannot come back ────────────────────

def test_the_old_check_goes_blind_the_moment_a_later_session_publishes():
    """Not a criticism of missing_sessions — it answers a different question.
    This pins the behaviour that made a real hole invisible."""
    before = ledger.missing_sessions(rows('2026-09-08'), TODAY, trading)
    assert before == ['2026-09-09', '2026-09-10', '2026-09-11']
    after = ledger.missing_sessions(rows('2026-09-08', '2026-09-11'), TODAY, trading)
    assert after == [], "the anchor moved past the hole"


def test_record_gaps_still_sees_the_interior_hole():
    got = ledger.record_gaps(rows('2026-09-08', '2026-09-11'), TODAY, trading)
    assert got['missing'] == ['2026-09-09', '2026-09-10']


def test_it_reproduces_on_the_real_ledger():
    """The live record, not a fixture. If this ever returns [] while the CSV
    still stops at 2026-09-08, the port has been undone."""
    import dashboard
    real = [r for r in ledger.load() if r.get('date', '') < TODAY.isoformat()]
    if not real or max(r['date'] for r in real) != '2026-09-08':
        return  # the record moved on; the fixture tests above still bind
    got = ledger.record_gaps(real, TODAY, dashboard.is_trading_day,
                             ledger.load_prints())
    assert '2026-09-09' in got['missing']


# ── the distinction that stops a false alarm ───────────────────────────────

def test_a_day_that_ran_and_picked_nothing_is_not_a_gap():
    """Universe prints prove the run happened. A run that evaluated the board
    and declined is the system working, not a missed publication."""
    got = ledger.record_gaps(rows('2026-09-08'), TODAY, trading,
                             prints('2026-09-08', '2026-09-09', '2026-09-10',
                                    '2026-09-11'))
    assert got['missing'] == []
    assert got['zero_pick'] == ['2026-09-09', '2026-09-10', '2026-09-11']


def test_the_two_classes_do_not_overlap():
    got = ledger.record_gaps(rows('2026-09-08'), TODAY, trading,
                             prints('2026-09-08', '2026-09-10'))
    assert got['missing'] == ['2026-09-09', '2026-09-11']
    assert got['zero_pick'] == ['2026-09-10']
    assert not set(got['missing']) & set(got['zero_pick'])


def test_weekends_and_holidays_are_not_holes():
    """09-12 and 09-13 are a weekend and must not be counted. 09-14 IS a
    trading day with nothing recorded, so it is a genuine hole and stays."""
    got = ledger.record_gaps(rows('2026-09-11'), dt.date(2026, 9, 15), trading)
    assert got['missing'] == ['2026-09-14']
    assert '2026-09-12' not in got['missing'] and '2026-09-13' not in got['missing']
    assert got['zero_pick'] == []


def test_it_never_reports_days_before_the_record_began():
    """A record that starts on Friday did not 'miss' the preceding Monday."""
    got = ledger.record_gaps(rows('2026-09-11'), TODAY, trading, lookback=45)
    assert got == {'missing': [], 'zero_pick': []}


def test_today_is_not_yet_a_gap():
    """At 09:46 today's board has not been written. Flagging it would fire
    every single morning and train the reader to ignore the line."""
    got = ledger.record_gaps(rows('2026-09-11'), TODAY, trading,
                             prints('2026-09-11'))
    assert TODAY.isoformat() not in got['missing']


def test_an_empty_record_claims_nothing():
    assert ledger.record_gaps([], TODAY, trading) == {'missing': [], 'zero_pick': []}


def test_it_is_pure(tmp_path, monkeypatch):
    """The calendar is injected and nothing is read from disk, so the frozen
    computation cannot acquire a dependency at render time."""
    monkeypatch.chdir(tmp_path)
    seen = []
    got = ledger.record_gaps(rows('2026-09-08'), TODAY,
                             lambda d: (seen.append(d), trading(d))[1])
    assert seen, "the injected calendar was never consulted"
    assert got['missing'] == ['2026-09-09', '2026-09-10', '2026-09-11']


def test_a_nonsense_lookback_fails_loudly():
    try:
        ledger.record_gaps(rows('2026-09-08'), TODAY, trading, lookback=0)
    except ValueError:
        return
    raise AssertionError('a zero lookback silently reported a complete record')


# ── it has to reach the reader ─────────────────────────────────────────────

def test_the_line_names_the_days_and_qualifies_the_hit_rate():
    line = ledger.record_gap_line({'missing': ['2026-09-09', '2026-09-10'],
                                   'zero_pick': []})
    assert '2026-09-09' in line and '2026-09-10' in line
    assert 'computed on what IS recorded' in line, \
        "a gap warning that does not qualify the rate beside it is decoration"


def test_a_clean_record_says_nothing_at_all():
    assert ledger.record_gap_line({'missing': [], 'zero_pick': []}) == ''
    assert ledger.record_gap_line(None) == ''


def test_a_zero_pick_day_is_reported_without_an_alarm():
    line = ledger.record_gap_line({'missing': [], 'zero_pick': ['2026-09-10']})
    assert line and '⚠' not in line
    assert 'a result, not a gap' in line


def test_the_email_carries_it_beside_the_hit_rate():
    """THE POINT OF THE PORT. It was already computable; it never reached the
    inbox, which is the only place it gets read at 09:46."""
    import daily_render
    import email_render
    rec = {'status': 'OK', 'hits': 52, 'n': 107, 'rate': .486, 'mean': -.058,
           'net_rate': .5, 'net_mean': .247, 'net_n': 6, 'net_unpriced': 101,
           'record_gaps': {'missing': ['2026-09-09'], 'zero_pick': []}}
    assert 'RECORD HAS A HOLE' in '\n'.join(daily_render._historical_record(rec))
    assert 'RECORD HAS A HOLE' in daily_render.record_gap_line(rec)
    assert email_render.full.record_gap_line(rec), "the concise email lost it"


def test_the_gap_check_can_never_block_a_board():
    """It protects the RECORD, not the bet. A crash here must cost the line,
    not the morning — the opposite trade from the coverage guards."""
    import inspect
    import brief
    src = inspect.getsource(brief._compute)
    i = src.index("record['record_gaps'] = ledger.record_gaps")
    window = src[i - 200:i + 400]
    assert 'except Exception' in window and "error('record_gaps'" in window, \
        'an unhandled record_gaps failure would take the whole report down'
