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
            # The dated attention snapshot is a record too — forward
            # collection has no history endpoint, so an unpushed snapshot is
            # a permanently lost session. It is allowed BY EXACT PATH only;
            # `git add -- data/social` would stage whatever else is in the
            # directory, which is the failure this test exists to catch.
            if f == '"$today_snap"':
                continue
            assert f.endswith(".csv"), f"{f} is not a record file"

    c_no_comments = "\n".join(l for l in c.splitlines()
                              if not l.lstrip().startswith("#"))
    if '"$today_snap"' in c_no_comments:
        assert re.search(r'today_snap="data/social/\$\(.*\)\.json"',
                         c_no_comments), \
            "today_snap must be a dated data/social JSON path, nothing else"
        assert "git add -- data/social " not in c_no_comments, \
            "staging the directory would carry unread files with the record"


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


# ── day-94: the publish contract changed under the wrapper ─────────────────

def test_it_passes_publish_because_brief_alone_writes_nothing():
    """REGRESSION. `brief.py` became a PREVIEW that persists nothing; a wrapper
    omitting --publish runs cleanly every morning, exits 0, and records
    NOTHING. Silent success is the worst available failure here."""
    c = code()
    assert "brief.py --publish" in c, "the wrapper would only preview"


def test_a_missed_publication_window_is_not_reported_as_success():
    """A LATE run renders a full page and publishes nothing. Without this it
    reads like an ordinary morning while the day goes unrecorded."""
    c = code()
    assert "exit 5" in c
    for marker in ("LATE — informational", "entry window missed"):
        assert marker in c, f"{marker} would pass as a normal run"


# ── day-95b: the unrecorded-day class ────────────────────────────────────────

def test_an_unrecorded_eligible_day_exits_loudly():
    """brief.py exits 7 when the window was ELIGIBLE but nothing was recorded
    (2026-09-09: emailed, went 1/4, never recorded). The wrapper maps it to a
    loud block and its own cron-visible exit 7 -- distinct from a hard failure
    (1) and from main's exit-6 provenance signal (58da082)."""
    c = code()
    assert '"$rc" -eq 7' in c or "[ $rc -eq 7 ]" in c
    assert "RECORD NOT WRITTEN" in c
    i = c.index("$rc -eq 7")
    assert "exit 7" in c[i:i + 900]


def test_no_record_rows_is_never_claimed_without_a_record():
    """The coverage-fail fall-through: 'no new record rows (already published
    today)' may only be logged after checking TODAY'S date actually exists in
    ledger.csv or universe_prints.csv."""
    c = code()
    i = c.index("no new record rows")
    window = c[max(0, i - 800):i]
    assert "ledger.csv" in window and "universe_prints.csv" in window
    assert "grep" in window, "the claim must be backed by a record check"


def test_the_publication_window_is_documented_where_it_is_scheduled():
    """DAY-95 (C1): this pinned the old SIXTY-second window. The window is now
    09:46:00-09:49:59 ET (PREREGISTER_day95b.md); execution.clock_status keeps
    09:47-09:49 publishable as a marked-late LATE-WINDOW and marks a run LATE
    at 09:50:00. The clock is still checked AFTER acquisition."""
    s = src()
    assert "FOUR MINUTES" in s or "four minutes" in s
    assert "after acquisition" in s.lower()


def test_the_clock_window_is_actually_four_minutes_wide():
    """DAY-95: this pinned the old ONE-minute window (`dt.time(9,47)` as the
    LATE boundary). It now pins the day-95 contract directly against the
    clock, so a change to execution.py surfaces here rather than as a silent
    empty ledger."""
    import datetime as dt
    from zoneinfo import ZoneInfo

    import execution
    # Day-95b: the 09:46 ENTRY minute is unchanged; the LATE boundary moved
    # from 09:47 to 09:50 by registration (PREREGISTER_day95b.md), so the old
    # source pin on dt.time(9,47) is intentionally retired in favour of the
    # behavioral checks below.
    src_ = open(execution.__file__).read()
    assert "dt.time(9,46)" in src_
    assert execution.PUBLISH_WINDOW_MINUTES == 4

    def at(hh, mm, ss):
        return dt.datetime(2026, 9, 8, hh, mm, ss,
                           tzinfo=ZoneInfo("America/New_York"))
    assert not execution.clock_status(at(9, 45, 59))["eligible"]
    on_time = execution.clock_status(at(9, 46, 0))
    assert on_time["eligible"] and on_time["status"] == "09:46 publication window"
    late_window = execution.clock_status(at(9, 49, 59))
    assert late_window["eligible"] and "LATE-WINDOW" in late_window["status"]
    late = execution.clock_status(at(9, 50, 0))
    assert not late["eligible"] and late["status"].startswith("LATE")


# ── day-95: running everything that exists, and collecting what cannot wait ──

def test_provenance_is_checked_before_the_report_runs():
    """Pulling proves this clone matches origin/main. It says nothing about
    whether main is the WHOLE of the work -- clock_vs_data sat finished on
    another branch for five weeks while every morning ran without it."""
    c = code()          # commands, not the header prose — see code()
    assert "provenance.py" in c
    assert c.index("provenance.py") < c.index("python brief.py")


def test_unclean_provenance_warns_but_never_blocks_the_record():
    """A day's record outweighs a tidy branch list. Refusing to publish over
    an unmerged research branch would trade a real, unrecoverable loss for a
    bookkeeping one."""
    c = code()          # commands, not the header prose — see code()
    assert "exit 6" in c
    i = c.index("PROVENANCE NOT CLEAN")
    assert "exit 1" not in c[i:i + 400], "an unclean audit must not abort the run"
    assert c.index("PROVENANCE NOT CLEAN") < c.index("python brief.py")


def test_an_integrity_refusal_outranks_an_unclean_audit():
    """Exit 4 and 5 are decided before provenance colours the exit code, so a
    guard refusal is never downgraded to 'published but untidy'."""
    c = code()
    assert c.index("exit 4") < c.index("exit 6")
    assert c.index("exit 5") < c.index("exit 6")


def test_a_missing_attention_snapshot_is_reported_not_passed_over():
    """Forward collection has no history endpoint, so a missed morning is a
    permanently missing session. Silence is the wrong response."""
    s = src()
    assert "NO ATTENTION SNAPSHOT" in s
    assert "cannot be recovered" in s or "permanently" in s.lower()


def test_the_collector_is_checked_here_but_never_RUN_here():
    """Registered at 09:20 ET, pre-open. Running it from this wrapper would
    put it at ~09:48 -- after the board is selected -- so its rows would carry
    the market's reaction to the open. That look-ahead would arrive disguised
    as a scheduling convenience."""
    c = code()
    assert "build_social.py" not in c, \
        "morning.sh must not invoke the collector; 09:46 is after the decision"
