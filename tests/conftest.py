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
