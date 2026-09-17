"""Staging and publication sit either side of two clocks that cannot move.

THE DEFECT, 2026-09-17. The scheduled run fired at 09:05, staged its inputs,
and died at 09:12 with nothing published — because it called `morning.sh`
immediately, and `wait_for_publication.py` raises when more than 120 seconds
remain ("start publication preparation at or after 09:44 ET"). Meanwhile
`prepare_deepseek` and `bar_cache` refuse AT OR AFTER 09:30. Both guards are
correct. Nothing sat between them, so the DeepSeek snapshot was staged and then
thrown away with the container, and the factor section read UNAVAILABLE for a
sixth consecutive day.

State is not portable between containers: the snapshot lives in RB_STATE_DIR
and dies with the machine. Staging and publishing must therefore happen in the
same process tree, which is what this script is for.
"""
import os
import re
import subprocess

SH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                  'morning_full.sh')


def src():
    return open(SH).read()


def code():
    """Commands only — assertions about behaviour must not read the prose that
    explains it. Same trap as test_morning.code() and test_deploy_units."""
    return '\n'.join(l for l in src().splitlines()
                     if l.strip() and not l.strip().startswith('#'))


def test_it_is_executable_and_valid_shell():
    assert os.access(SH, os.X_OK)
    assert subprocess.run(['bash', '-n', SH]).returncode == 0


def test_it_stages_before_it_publishes():
    body = code()
    for tool in ('bar_cache.py', 'build_biotech.py', 'prepare_deepseek.py'):
        assert body.index(tool) < body.index('./morning.sh'), \
            f'{tool} must run before the publication hand-off'


def test_it_holds_for_the_publication_window():
    """Without this wait the script is just morning.sh started 40 minutes
    early, which is the thing that failed."""
    body = code()
    assert 'PUBLISH_AT' in body and 'sleep' in body
    hold = body[body.index('while'):body.index('./morning.sh')]
    assert 'minutes_now' in hold and 'sleep' in hold


def test_the_two_deadlines_are_the_real_ones():
    body = code()
    assert re.search(r'STAGE_DEADLINE=0?930', body), 'staging cutoff must be 09:30'
    assert re.search(r'PUBLISH_AT=0?944', body), 'the wait guard allows 09:44 onward'


def test_staging_after_the_cutoff_is_skipped_not_forced():
    """Staging after 09:30 would describe the market's reaction to the open.
    The script must decline and still publish, not push through the guard."""
    body = code()
    guard = body[body.index('if [ "$(minutes_now)" -ge "$STAGE_DEADLINE" ]'):body.index('while')]
    taken, skipped = guard.split('else', 1)
    assert 'prepare_deepseek' not in taken, 'the post-cutoff branch must not stage'
    assert 'prepare_deepseek' in skipped, 'the pre-cutoff branch must stage'
    assert 'exit' not in taken.split('\n')[0]


def test_a_staging_failure_never_stops_the_publication():
    """House rule 1 inverted correctly: count and report, but a shadow input
    may not veto the morning."""
    body = code()
    stage = body[body.index('stage_faults=()'):body.index('while')]
    # A bare `exit` STATEMENT anywhere in the staging block would abandon the
    # publication — including mid-line, e.g. `stage_faults+=(...); exit 1 ;;`.
    # `(exit $?)` inside a log string is text about a failure, not a failure
    # path, so strip quoted strings first and then look for the word.
    bare = re.sub(r'"[^"]*"', '""', stage)
    offenders = [l.strip() for l in bare.splitlines() if re.search(r'\bexit\b', l)]
    assert not offenders, f'a staging failure exits the script: {offenders}'
    assert body.count('stage_faults+=') >= 4, 'faults must be counted per step'
    assert 'stage_faults[*]' in body, 'counted faults must also be reported'


def test_the_exit_code_is_morning_sh_s_own():
    """cron distinguishes 0/3/4/5/6/1 through this script, unchanged."""
    body = code()
    assert 'rc=$?' in body and 'exit "$rc"' in body


def test_it_does_not_bypass_the_publication_guard():
    body = code()
    assert 'wait_for_publication' not in body, \
        'the wait belongs to morning.sh; this script must not reimplement it'
    assert '--send' not in body
