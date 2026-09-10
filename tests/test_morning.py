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
    assert c.index("git pull") < c.index("python daily_job.py")


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
    assert s.index("python daily_job.py") < s.index("git push")
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

def test_it_runs_daily_job_not_brief_because_brief_stores_nothing():
    """REGRESSION, day-97. `brief.py --publish` writes the ledger rows but never
    creates the immutable Store entry, so there is nothing for deliver_report to
    send and no durable publication to reconcile a delivery against. The two are
    not interchangeable."""
    c = code()
    assert "daily_job.py" in c
    assert "brief.py --publish" not in c, "brief publishes no Store entry"


def test_send_is_not_passed_to_daily_job():
    """With --send, daily_job prints only the SMTP result, and the LATE and
    refusal greps below would have nothing to read. Sending is a separate step
    AFTER those guards have had their say."""
    c = code()
    i = c.index("daily_job.py")
    assert "--send" not in c[i:i + 300]


def test_the_email_is_sent_after_the_integrity_guards_not_before():
    c = code()
    assert c.index("daily_job.py") < c.index("deliver_report.py")
    assert c.index("REFUSING TO PUBLISH") < c.index("deliver_report.py")


def test_a_late_run_still_gets_emailed():
    """Silence is the worse failure: it is indistinguishable from a job that
    never ran, and that ambiguity made a whole session unexplainable. The
    subject line carries the state instead."""
    c = code()
    assert c.index("deliver_report.py") < c.index("exit 5")


def test_a_failed_email_does_not_discard_the_record():
    """Delivery failure is not publication failure. The board is published and
    the CSVs must still travel."""
    s = src()
    i = s.index("EMAIL FAILED")
    window = s[i:i + 400]
    assert "board IS published" in window
    assert "Do not re-run the report" in window


def test_a_missed_publication_window_is_not_reported_as_success():
    """A LATE run renders a full page and publishes nothing. Without this it
    reads like an ordinary morning while the day goes unrecorded."""
    c = code()
    assert "exit 5" in c
    for marker in ("LATE — informational", "entry window missed"):
        assert marker in c, f"{marker} would pass as a normal run"


def test_the_sixty_second_window_is_documented_where_it_is_scheduled():
    """execution.clock_status marks a run LATE at 09:47:00 and checks AFTER
    acquisition, so the fetch must finish inside the 09:46 minute."""
    s = src()
    assert "60 SECONDS" in s or "60 seconds" in s
    assert "after acquisition" in s.lower()


def test_the_clock_window_is_actually_one_minute_wide():
    """Pins the contract the wrapper is written against, so a change to
    execution.py surfaces here rather than as a silent empty ledger."""
    import datetime as dt

    import execution
    src_ = open(execution.__file__).read()
    assert "dt.time(9,46)" in src_ and "dt.time(9,47)" in src_


# ── day-95: running everything that exists, and collecting what cannot wait ──

def test_provenance_is_checked_before_the_report_runs():
    """Pulling proves this clone matches origin/main. It says nothing about
    whether main is the WHOLE of the work -- clock_vs_data sat finished on
    another branch for five weeks while every morning ran without it."""
    c = code()          # commands, not the header prose — see code()
    assert "provenance.py" in c
    assert c.index("provenance.py") < c.index("python daily_job.py")


def test_unclean_provenance_warns_but_never_blocks_the_record():
    """A day's record outweighs a tidy branch list. Refusing to publish over
    an unmerged research branch would trade a real, unrecoverable loss for a
    bookkeeping one."""
    c = code()          # commands, not the header prose — see code()
    assert "exit 6" in c
    i = c.index("PROVENANCE NOT CLEAN")
    assert "exit 1" not in c[i:i + 400], "an unclean audit must not abort the run"
    assert c.index("PROVENANCE NOT CLEAN") < c.index("python daily_job.py")


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
