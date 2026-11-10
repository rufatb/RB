"""Suite-wide isolation.

The wire archive (`data/newswire/`) grows every morning. A test that stages
news or classifies a headline must not see the real archive, or a release
collected tomorrow changes today's fixture. Tests that need releases pass
their own `root`.
"""
import pytest


@pytest.fixture(autouse=True)
def _empty_wire_archive(tmp_path_factory, monkeypatch):
    import newswire
    monkeypatch.setattr(newswire, 'ARCHIVE', tmp_path_factory.mktemp('wire'))
    newswire._INDEX.clear()


@pytest.fixture(autouse=True)
def _empty_state_dir(tmp_path_factory, monkeypatch):
    """The live `.rb-state/` holds this morning's staged snapshots. A test that
    builds a brief must not read them: on 2026-09-29 two legacy-report tests
    failed only on days a morning had staged research into the container.
    Tests that need state set RB_STATE_DIR or pass state_dir themselves."""
    monkeypatch.setenv('RB_STATE_DIR', str(tmp_path_factory.mktemp('state')))


@pytest.fixture(autouse=True)
def _no_previous_top2(tmp_path_factory, monkeypatch):
    """Day-129: the Top 2 flags a name that was the previous session's Top 2,
    read from the real record. A test must not see it — tomorrow's record would
    change today's fixture. Tests that need a previous session pass `previous`."""
    import council
    monkeypatch.setattr(council, 'PREVIOUS_LEDGER', tmp_path_factory.mktemp('picks')/'none.csv')


@pytest.fixture(autouse=True)
def _pre_day144_rules(request, monkeypatch):
    """Day-144 (owner, 2026-10-30) changed four switches for the morning of
    2026-11-02: Claude's picks lead the Top 2 (`council.CLAUDE_LEADS`), and the
    big-mover, high-volatility and 09:46 void rules are off (`SKIP_MOVERS`,
    `SKIP_WILD`, `entry_checks.VOID_TOP2`). The suite was written for the
    council's own Top 2 under all three, so every test runs on those rules
    unless it is marked `day144`, which runs on the production values
    (tests/test_claude_leads.py)."""
    if any(request.node.get_closest_marker(m) for m in ('day144', 'day146', 'day150')):
        return
    import council
    import entry_checks
    monkeypatch.setattr(council, 'CLAUDE_LEADS', False)
    monkeypatch.setattr(council, 'SKIP_MOVERS', True)
    monkeypatch.setattr(council, 'SKIP_WILD', True)
    monkeypatch.setattr(entry_checks, 'VOID_TOP2', True)


@pytest.fixture(autouse=True)
def _pre_day146_rules(request, monkeypatch):
    """Day-146 (owner, 2026-11-04) passes over a Top 2 pick that follows a
    three-day run (`council.SKIP_RUNS`). The suite was written before it, so
    every test runs with it off unless it is marked `day146`, which runs on the
    production values (tests/test_runs_rule.py)."""
    if request.node.get_closest_marker('day146') or request.node.get_closest_marker('day150'):
        return
    import council
    monkeypatch.setattr(council, 'SKIP_RUNS', False)


@pytest.fixture(autouse=True)
def _pre_day148_hedge(request, monkeypatch):
    """Day-148c (owner, 2026-11-09) prints a hedge line under a Top 2 whose
    picks all stand on one side (`top_picks.HEDGE`), with the lab's running
    record beside it. The suite was written before it, so every test runs with
    it off unless it is marked `day148`, which runs on the production value
    (tests/test_hedge_line.py) and passes its own record: tomorrow's lab rows
    must not change today's fixture."""
    if request.node.get_closest_marker('day148'):
        return
    import top_picks
    monkeypatch.setattr(top_picks, 'HEDGE', False)


@pytest.fixture(autouse=True)
def _pre_day150_rules(request, monkeypatch):
    """Day-150 (owner, 2026-11-10) changed three switches for the morning of
    2026-11-11: a quality floor on Claude's Top 2 (`council.FLOOR`), one
    combined 09:00 email with KEEP / DROP / CAUTION at 09:31
    (`council_flash.COMBINED`), and no email of the pre-open desk's own
    (`us_preopen.EMAIL`). The suite was written before them, so every test
    runs with them as they were unless it is marked `day150`, which runs on
    the production values (tests/test_morning_decision.py)."""
    if request.node.get_closest_marker('day150'):
        return
    import council
    import council_flash
    import us_preopen
    monkeypatch.setattr(council, 'FLOOR', False)
    monkeypatch.setattr(council_flash, 'COMBINED', False)
    monkeypatch.setattr(us_preopen, 'EMAIL', True)


@pytest.fixture(autouse=True)
def _no_preopen_ledger(tmp_path_factory, monkeypatch):
    """Day-150: the 09:00 email shows today's pre-open desk calls from
    `data/us_preopen_calls.csv`. A test must not see the real ledger: a call
    recorded tomorrow would change today's fixture. Tests that need calls
    write their own ledger and point `us_preopen.LEDGER` at it."""
    import us_preopen
    monkeypatch.setattr(us_preopen, 'LEDGER', tmp_path_factory.mktemp('preopen')/'calls.csv')


@pytest.fixture(autouse=True)
def _no_open_check_ledger(tmp_path_factory, monkeypatch):
    """Day-150: the 09:31 check records its verdicts in
    `data/reviews/open_checks.csv`. A test must never write the real record."""
    import council_flash
    monkeypatch.setattr(council_flash, 'OPEN_LEDGER', tmp_path_factory.mktemp('open')/'open_checks.csv')


@pytest.fixture(autouse=True)
def _empty_press_archive(tmp_path_factory, monkeypatch):
    """Day-150: the press archive (`data/newswire/press/`) grows every
    morning, like the wire archive. A test must not see the real one."""
    import press_feed
    monkeypatch.setattr(press_feed, 'ARCHIVE', tmp_path_factory.mktemp('press'))
    press_feed._INDEX.clear()


@pytest.fixture()
def biotech_live(monkeypatch):
    """Day-136: Part 2 is retired (`biotech.RETIRED`). A test of the kept
    biotech code asks for this and runs it as it ran before the retirement."""
    import biotech
    monkeypatch.setattr(biotech, 'RETIRED', False)
