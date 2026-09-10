"""provenance.py — against REAL git repositories, not mocks.

This tool's whole job is to answer a question about git, so a mocked git
proves nothing about it. Each test builds a throwaway repo, strands something
in a specific way, and checks the tool notices -- or, just as importantly,
does not cry wolf.
"""
import subprocess

import pytest

import provenance as P


def run(cwd, *args):
    return subprocess.run(args, cwd=cwd, capture_output=True, text=True,
                          check=True).stdout


@pytest.fixture()
def repo(tmp_path, monkeypatch):
    """A repo with an `origin` that is a real second repository on disk, so
    refs/remotes is populated the way it is in the live clone."""
    origin = tmp_path / "origin"
    work = tmp_path / "work"
    origin.mkdir()
    run(origin, "git", "init", "-q", "--bare", "-b", "main")

    work.mkdir()
    run(work, "git", "init", "-q", "-b", "main")
    run(work, "git", "config", "user.email", "t@t")
    run(work, "git", "config", "user.name", "t")
    run(work, "git", "remote", "add", "origin", str(origin))
    (work / "engine.py").write_text("def publish():\n    return 1\n")
    (work / "ledger.csv").write_text("date,leg\n2026-01-02,A\n")
    run(work, "git", "add", "-A")
    run(work, "git", "commit", "-q", "-m", "base")
    run(work, "git", "push", "-q", "-u", "origin", "main")

    monkeypatch.chdir(work)
    return work


def branch_with(work, name, changes, message="work"):
    run(work, "git", "checkout", "-q", "-b", name)
    for path, text in changes.items():
        (work / path).write_text(text)
    run(work, "git", "add", "-A")
    run(work, "git", "commit", "-q", "-m", message)
    run(work, "git", "push", "-q", "-u", "origin", name)
    run(work, "git", "checkout", "-q", "main")


def test_a_clean_repo_is_reported_clean(repo):
    text, code = P.report()
    assert code == 0
    assert "VERDICT: CLEAN" in text


def test_a_branch_only_FILE_is_stranded_work(repo):
    """build_social.py, day-94: a whole collector nobody merged."""
    branch_with(repo, "feature", {"collector.py": "def collect():\n    pass\n"})
    text, code = P.report()
    assert code == 1
    assert "HOLDS WORK MAIN DOES NOT HAVE" in text
    assert "file    collector.py" in text


def test_a_branch_only_SYMBOL_in_a_shared_file_is_stranded_work(repo):
    """clock_vs_data, day-22: the file existed on both sides, the GUARD did
    not. This is the case a file-level check misses entirely."""
    branch_with(repo, "guard", {"engine.py":
                                "def publish():\n    return 1\n\n"
                                "def clock_vs_data(a, b):\n    return a == b\n"})
    text, code = P.report()
    assert code == 1
    assert "symbol  clock_vs_data()" in text


def test_a_branch_only_RECORD_DATE_is_stranded(repo):
    """A ledger row cannot be recomputed from anything, so a date on a branch
    and not on the trunk is a permanent loss, not a merge preference."""
    branch_with(repo, "record",
                {"ledger.csv": "date,leg\n2026-01-02,A\n2026-03-09,B\n"})
    text, code = P.report()
    assert code == 1
    assert "RECORD  ledger.csv" in text and "2026-03-09" in text


def test_a_merged_branch_is_not_flagged_for_a_later_RENAME(repo):
    """THE FALSE ALARM THIS TOOL MUST NOT RAISE. The first live run flagged a
    fully-merged branch for holding `Quotes`, which main lacked only because a
    LATER commit on main renamed it to YahooMarketData. A tool that reports a
    rename as lost work gets ignored, and being ignored is how the day-22
    guard stayed stranded for five weeks."""
    branch_with(repo, "old", {"engine.py":
                              "def publish():\n    return 1\n\n"
                              "class Quotes:\n    pass\n"})
    run(repo, "git", "merge", "-q", "--no-edit", "old")
    # ... and then main renames it, which is a decision, not a loss.
    (repo / "engine.py").write_text("def publish():\n    return 1\n\n"
                                    "class YahooMarketData:\n    pass\n")
    run(repo, "git", "add", "-A")
    run(repo, "git", "commit", "-q", "-m", "rename")
    run(repo, "git", "push", "-q", "origin", "main")

    text, code = P.report()
    assert "Quotes" not in text, "a rename was reported as stranded work"
    assert "old — fully merged" in text
    assert code == 0


def test_commits_ahead_alone_is_not_evidence_of_stranding(repo):
    """The dashboard branch sat 2 commits ahead of main with its guard already
    cherry-picked across. Commit counts generate false alarms; content is the
    question."""
    branch_with(repo, "picked", {"engine.py":
                                 "def publish():\n    return 1\n\n"
                                 "def guard():\n    return True\n"})
    # main gets the same SYMBOL by a different commit, plus extra docs.
    (repo / "engine.py").write_text('def publish():\n    return 1\n\n'
                                    'def guard():\n    """Documented."""\n'
                                    '    return True\n')
    run(repo, "git", "add", "-A")
    run(repo, "git", "commit", "-q", "-m", "cherry-picked with docs")
    run(repo, "git", "push", "-q", "origin", "main")

    text, code = P.report()
    assert code == 0
    assert "absorbed by content despite 1 commit(s) ahead" in text


def test_an_uncommitted_tree_is_refused_because_the_run_would_use_it(repo):
    (repo / "engine.py").write_text("def publish():\n    return 999\n")
    text, code = P.report()
    assert code == 1
    assert "uncommitted change" in text


def test_being_behind_the_remote_is_refused(repo):
    """House rule 6. A stale clone once put a wrong record in a live report."""
    branch_with(repo, "other", {"engine.py": "def publish():\n    return 2\n"})
    run(repo, "git", "push", "-q", "origin", "other:main")
    run(repo, "git", "fetch", "-q", "origin")
    text, code = P.report()
    assert code == 1
    assert "BEHIND" in text


def test_a_git_failure_is_raised_not_reported_as_all_clear(tmp_path,
                                                           monkeypatch):
    """House rule 1. Swallowing the error would print a reassuring CLEAN on a
    repo the tool could not actually read."""
    monkeypatch.chdir(tmp_path)
    with pytest.raises(subprocess.CalledProcessError):
        P.report()


def test_an_unparseable_file_is_surfaced_not_skipped(repo):
    branch_with(repo, "broken", {"engine.py": "def publish(:\n"})
    text, code = P.report()
    assert code == 1
    assert "unparseable" in text
