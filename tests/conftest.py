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
