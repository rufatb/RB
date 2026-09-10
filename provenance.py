#!/usr/bin/env python3
"""provenance.py — is `main` everything, and is what I am running `main`?

WHY THIS EXISTS. Twice now, work that was finished, tested and committed did
not reach the morning run because it sat on a branch nobody merged:

  * `clock_vs_data`, the guard against publishing on a wrong host clock, was
    written 2026-08-04 and stranded for FIVE WEEKS. main, the session branch
    and the day-92 branch all shipped without it.
  * `build_social.py`, a FORWARD collector, sat unmerged from 09-08. Forward
    collection cannot be back-filled, so every unmerged day was a day of data
    permanently lost -- and the first live run showed its attention measure was
    the endpoint's page size, a bug that could only ever be found by RUNNING it.

Both were invisible to `git status`, which reports a clean tree, and both were
invisible to the test suite, which passes perfectly on an incomplete main.

WHAT IT REFUSES TO DO. It does not use commit counts as evidence. On day-95 the
dashboard branch showed "2 commits ahead of main" and was FULLY ABSORBED -- the
guard had been cherry-picked, and main's copy had MORE documentation than the
branch's. Commit-ahead is a false alarm generator; the questions worth asking
are about CONTENT:

  1. does a branch hold a FILE main does not have at all?
  2. does a branch hold a top-level FUNCTION OR CLASS whose name appears
     nowhere in main? (this is what stranded `clock_vs_data`)
  3. does a branch hold RECORD ROWS -- ledger, prints, positions -- for dates
     main has never seen? records cannot be re-derived from anything.

Read-only. Runs no git command that writes. Nothing here places, sizes or
cancels an order.
"""

from __future__ import annotations

import argparse
import ast
import subprocess
import sys

RECORD_FILES = ("ledger.csv", "universe_prints.csv", "positions.csv",
                "data/advice.csv")


def git(*args: str) -> str:
    """One transport, and failures are RAISED. A provenance check that
    silently swallows a git error reports 'all clear' on a broken repo, which
    is worse than not running it (house rule 1)."""
    return subprocess.run(("git",) + args, capture_output=True, text=True,
                          check=True).stdout


def git_ok(*args: str) -> tuple:
    try:
        return True, git(*args)
    except subprocess.CalledProcessError as exc:
        return False, (exc.stderr or "").strip()


def branches(remote: str = "origin", trunk: str = "main") -> list:
    out = git("for-each-ref", "--format=%(refname:short)",
              f"refs/remotes/{remote}")
    skip = {f"{remote}/{trunk}", f"{remote}/HEAD"}
    return [b.strip() for b in out.splitlines()
            if b.strip() and b.strip() not in skip]


def files_at(ref: str) -> set:
    return {p for p in git("ls-tree", "-r", "--name-only", ref).splitlines() if p}


def toplevel_symbols(ref: str, path: str) -> set:
    """Top-level def/class names in one python file at one ref.

    Parsed, not grepped. A regex over source text counts names inside strings
    and comments, and this check is only worth having if a hit means something.
    A file that does not parse is reported rather than skipped.
    """
    try:
        src = git("show", f"{ref}:{path}")
    except subprocess.CalledProcessError:
        return set()
    try:
        tree = ast.parse(src)
    except SyntaxError:
        return {f"<unparseable:{path}>"}
    return {n.name for n in tree.body
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef,
                              ast.ClassDef))}


def all_symbols(ref: str, paths: set) -> set:
    out = set()
    for p in paths:
        if p.endswith(".py"):
            out |= toplevel_symbols(ref, p)
    return out


def record_dates(ref: str, path: str) -> set:
    """First-column dates in a record CSV. Records are the one artifact that
    cannot be recomputed, so a date on a branch and not on main is a real
    loss, not a merge preference."""
    try:
        text = git("show", f"{ref}:{path}")
    except subprocess.CalledProcessError:
        return set()
    dates = set()
    for line in text.splitlines()[1:]:
        cell = line.split(",")[0].strip().strip('"')
        if len(cell) == 10 and cell[4] == "-" and cell[7] == "-":
            dates.add(cell)
    return dates


def is_ancestor(branch: str, trunk: str) -> bool:
    return subprocess.run(("git", "merge-base", "--is-ancestor", branch, trunk),
                          capture_output=True).returncode == 0


def audit_branch(branch: str, trunk: str, trunk_files: set,
                 trunk_symbols: set) -> dict:
    empty = {"branch": branch, "commits_ahead": 0, "missing_files": [],
             "missing_symbols": [], "missing_records": {}}

    # A branch that is an ANCESTOR of the trunk is fully contained in it, and
    # git guarantees that -- no content check can add information. Anything
    # the trunk no longer has was removed by a LATER commit that is itself on
    # the trunk, i.e. a decision, not a stranding.
    #
    # This is not a shortcut, it is a correctness fix. The first run of this
    # tool flagged session-rw51c2 for holding `Quotes` and `Yahoo`, which main
    # "lacks" only because a later consolidation on main RENAMED Quotes to
    # YahooMarketData and superseded seven tests. Reporting a rename as lost
    # work trains the reader to ignore the tool, which is how the guard got
    # stranded for five weeks in the first place.
    if is_ancestor(branch, trunk):
        return {**empty, "fully_merged": True}

    bf = files_at(branch)
    missing_files = sorted(f for f in bf - trunk_files
                           if not f.startswith(".git"))
    # Only inspect symbols in files BOTH refs have, plus the branch-only files;
    # a branch-only file is already reported above and its symbols would just
    # restate that.
    shared_py = {f for f in bf & trunk_files if f.endswith(".py")}
    branch_symbols = all_symbols(branch, shared_py)
    missing_symbols = sorted(branch_symbols - trunk_symbols)

    missing_records = {}
    for rf in RECORD_FILES:
        extra = record_dates(branch, rf) - record_dates(trunk, rf)
        if extra:
            missing_records[rf] = sorted(extra)

    ahead = len(git("rev-list", "--count", f"{trunk}..{branch}").split() and
                git("rev-list", f"{trunk}..{branch}").splitlines())
    return {"branch": branch, "commits_ahead": ahead,
            "missing_files": missing_files,
            "missing_symbols": missing_symbols,
            "missing_records": missing_records,
            "fully_merged": False}


def stranded(a: dict) -> bool:
    return bool(a["missing_files"] or a["missing_symbols"]
                or a["missing_records"])


def check_head(trunk: str) -> list:
    """Is the tree I am about to RUN the same thing as the trunk I just
    verified? A perfect audit of main is worth nothing if the morning run
    executes uncommitted edits or a stale checkout."""
    problems = []
    ok, cur = git_ok("rev-parse", "--abbrev-ref", "HEAD")
    cur = cur.strip() if ok else "?"
    if cur != trunk:
        problems.append(f"HEAD is on {cur!r}, not {trunk!r}")

    dirty = git("status", "--porcelain").strip()
    if dirty:
        n = len(dirty.splitlines())
        problems.append(f"working tree has {n} uncommitted change(s) — the "
                        "morning run would execute code that is in no record")

    ok, _ = git_ok("rev-parse", "--verify", f"origin/{trunk}")
    if ok:
        behind = len(git("rev-list", f"{trunk}..origin/{trunk}").splitlines())
        ahead = len(git("rev-list", f"origin/{trunk}..{trunk}").splitlines())
        if behind:
            problems.append(f"{trunk} is {behind} commit(s) BEHIND "
                            f"origin/{trunk} — fetch and fast-forward first "
                            "(house rule 6)")
        if ahead:
            problems.append(f"{trunk} is {ahead} commit(s) ahead of "
                            f"origin/{trunk} — this machine is the only copy")
    else:
        problems.append(f"no origin/{trunk} — cannot tell if this clone is "
                        "current")
    return problems


def report(trunk: str = "main", remote: str = "origin") -> tuple:
    lines = ["PROVENANCE — is main everything, and am I running main?", ""]

    head_problems = check_head(trunk)
    lines.append("THIS CHECKOUT")
    if head_problems:
        for p in head_problems:
            lines.append(f"  ✗ {p}")
    else:
        lines.append(f"  ✓ on {trunk}, clean, in sync with {remote}/{trunk}")
    lines.append("")

    trunk_files = files_at(trunk)
    trunk_symbols = all_symbols(trunk, trunk_files)
    lines.append(f"BRANCHES (content, not commit counts)")

    audits = [audit_branch(b, trunk, trunk_files, trunk_symbols)
              for b in branches(remote, trunk)]
    if not audits:
        lines.append("  (no other branches)")

    for a in audits:
        if not stranded(a):
            note = ("fully merged" if a.get("fully_merged") else
                    "absorbed" if not a["commits_ahead"] else
                    f"absorbed by content despite {a['commits_ahead']} "
                    "commit(s) ahead")
            lines.append(f"  ✓ {a['branch']} — {note}")
            continue
        lines.append(f"  ✗ {a['branch']} — HOLDS WORK MAIN DOES NOT HAVE")
        for f in a["missing_files"][:20]:
            lines.append(f"      file    {f}")
        if len(a["missing_files"]) > 20:
            lines.append(f"      ... and {len(a['missing_files']) - 20} more files")
        for s in a["missing_symbols"][:20]:
            lines.append(f"      symbol  {s}()")
        if len(a["missing_symbols"]) > 20:
            lines.append(f"      ... and {len(a['missing_symbols']) - 20} more symbols")
        for rf, dates in a["missing_records"].items():
            lines.append(f"      RECORD  {rf}: {len(dates)} date(s) not on "
                         f"{trunk} — {', '.join(dates[:5])}"
                         f"{' ...' if len(dates) > 5 else ''}")

    bad = head_problems or [a for a in audits if stranded(a)]
    lines.append("")
    if bad:
        lines.append("VERDICT: NOT CLEAN — the morning run would not be "
                     "running everything that exists.")
    else:
        lines.append("VERDICT: CLEAN — every branch is absorbed and this "
                     "checkout is the trunk.")
    return "\n".join(lines), (1 if bad else 0)


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--trunk", default="main")
    p.add_argument("--remote", default="origin")
    p.add_argument("--fetch", action="store_true",
                   help="fetch first, so the audit is against the real remote")
    a = p.parse_args(argv)
    if a.fetch:
        ok, err = git_ok("fetch", "--all", "--prune", "--quiet")
        if not ok:
            print(f"fetch failed: {err}\nrefusing to report on a stale view "
                  "of the remote (house rule 6)", file=sys.stderr)
            return 2
    text, code = report(a.trunk, a.remote)
    print(text)
    return code


if __name__ == "__main__":
    raise SystemExit(main())
