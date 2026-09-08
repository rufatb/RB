"""Day-93: the unattended morning run.

An automated run has no human watching, so the two things that matter are that
it PUSHES the record it writes, and that a refusal does not look like a normal
morning in the cron mail.
"""

import os
import re
import subprocess


SH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                  "morning.sh")


def src():
    return open(SH).read()


def code():
    """The script with comments stripped.

    Order assertions must look at COMMANDS, not prose. Both of these tests
    first failed against the header comment, which names `python brief.py` and
    `git pull` in the opposite order while explaining why the real order is
    what it is — the test was reading the explanation, not the script.
    """
    out = []
    for line in src().splitlines():
        t = line.strip()
        if t.startswith("#") or not t:
            continue
        out.append(line.split("  #")[0])
    return "\n".join(out)


def test_it_is_executable():
    assert os.access(SH, os.X_OK), "cron cannot run a non-executable script"


def test_it_is_valid_shell():
    assert subprocess.run(["bash", "-n", SH]).returncode == 0


def test_it_pulls_before_running():
    """House rule 6. A board published from a stale clone can duplicate or
    contradict rows another machine already wrote."""
    c = code()
    assert c.index("git pull") < c.index("python brief.py")


def test_a_failed_pull_aborts_rather_than_running_anyway():
    c = code()
    i = c.index("git pull")
    assert "exit 1" in c[i:i + 600]
    assert "refusing to run" in src().lower()


def test_it_pushes_the_record_it_writes():
    """THE FAILURE THIS SCRIPT EXISTS FOR. brief.py writes the permanent
    record; a run that does not push leaves it on one machine, which is exactly
    what stranded 2026-09-08 on a single branch."""
    s = src()
    assert s.index("python brief.py") < s.index("git push")
    for f in ("ledger.csv", "universe_prints.csv", "data/advice.csv"):
        assert f in s, f"{f} is never staged — its rows would not travel"


def test_it_never_pushes_code_only_the_record():
    """An unattended job must not publish edits nobody has read."""
    c = code()
    adds = re.findall(r"git add[^\n]*", c)
    assert adds, "nothing is staged at all"
    for add in adds:
        assert " -- " in add, f"unscoped stage: {add}"
        assert " -A" not in add and " ." not in add, f"stages code too: {add}"
        args = add.split(" -- ")[1]
        args = re.sub(r"\d?>[&]?\S+", "", args)      # drop shell redirects
        for f in args.split():
            assert f.endswith(".csv"), f"{f} is not a record file"


def test_a_non_trading_day_exits_distinctly_and_is_not_an_error():
    s = src()
    assert "exit 3" in s
    assert "not an error" in s.lower()


def test_an_integrity_refusal_does_not_look_like_a_normal_morning():
    """A refusal is a SUCCESSFUL run that declined to publish. If it exited 0
    silently, the cron mail would read like any other day."""
    s = src()
    assert "exit 4" in s
    for guard in ("REFUSING TO PUBLISH", "CLOCK IS BEHIND", "FEED IS STALE",
                  "NOTHING PUBLISHED", "MARKET CLOSED"):
        assert guard in s, f"{guard} would pass as a normal run"


def test_a_failed_push_says_the_machine_is_the_only_copy():
    s = src()
    i = s.index("PUSH FAILED after")
    assert "only copy" in s[i:i + 300]


def test_the_push_retries_rather_than_giving_up_once():
    assert re.search(r"for attempt in [\d ]+", src())


def test_it_places_no_orders():
    s = src()
    assert "places, sizes or cancels" in s
    for w in ("submit_order", "place_order", "broker"):
        assert w not in s


def test_the_trading_day_status_is_captured_directly_not_through_a_negation():
    """`if ! cmd; then rc=$?` captures the status of the NEGATION -- always 1
    -- so the inner exit 3 never survives and every holiday would report as a
    hard failure. Found by running the script, not by reading it."""
    c = code()
    i = c.index("is_trading_day")
    window = c[i:i + 400]
    assert "rc=$?" in window
    assert "if ! python" not in c, "the negation form swallows the exit code"


def test_a_holiday_and_a_broken_check_are_distinguishable():
    c = code()
    assert '"$rc" -eq 3' in c
    assert '"$rc" -ne 0' in c
