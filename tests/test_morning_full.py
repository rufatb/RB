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
    explains it. Same trap as test_morning.code() and test_deploy_units.

    TRAILING comments count as prose too, and this helper used to keep them:
    `STAGE_DEADLINE=0930   # prepare_deepseek / bar_cache refuse...` made an
    ordering assertion about `prepare_deepseek` match a COMMENT forty lines
    above the command it describes. A hash inside a quoted string is not a
    comment, so only cut at one with balanced quotes before it."""
    out = []
    for line in src().splitlines():
        for i, ch in enumerate(line):
            if ch == '#' and line[:i].count("'") % 2 == 0 and line[:i].count('"') % 2 == 0:
                line = line[:i]
                break
        if line.strip():
            out.append(line.rstrip())
    return '\n'.join(out)


def test_the_helper_reads_commands_not_the_prose_about_them():
    assert '# ' not in code() and 'WHY THIS EXISTS' not in code()
    assert 'STAGE_DEADLINE=0930' in code(), 'the command itself must survive'


def test_it_is_executable_and_valid_shell():
    assert os.access(SH, os.X_OK)
    assert subprocess.run(['bash', '-n', SH]).returncode == 0


def test_it_stages_before_it_publishes():
    body = code()
    for tool in ('bar_cache.py', 'build_biotech.py', 'prepare_deepseek.py',
                 'deepseek_opportunities.py'):
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
    for tool in ('prepare_deepseek', 'deepseek_opportunities'):
        assert tool not in taken, f'the post-cutoff branch must not stage {tool}'
        assert tool in skipped, f'the pre-cutoff branch must stage {tool}'
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
    assert body.count('stage_faults+=') >= 5, 'faults must be counted per step'
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


def test_a_missing_credential_is_reported_before_staging_not_inside_it():
    """`.rb-state/` is gitignored, so a fresh container has no key and both
    DeepSeek sections read UNAVAILABLE against a healthy account. The remedy
    only works before 09:30, so the warning has to come first."""
    body = code()
    check = body.index('DEEPSEEK_API_KEY')
    assert check < body.index('prepare_deepseek'), \
        'the credential check must precede staging, while there is still time to act'
    assert check < body.index('STAGE_DEADLINE" ]'), \
        'it must not sit inside the post-cutoff branch'
    assert 'secrets/deepseek_api_key' in body, 'the warning must name the remedy'


def test_the_credential_warning_never_prints_the_credential():
    body = src()
    warn = body[body.index('NO DEEPSEEK CREDENTIAL'):body.index('STAGE_DEADLINE" ]')]
    assert '$DEEPSEEK_API_KEY' not in warn and '${DEEPSEEK_API_KEY}' not in warn


def test_the_research_pool_is_staged_and_before_the_news_refresh():
    """`prepare_factor_pool` writes `deepseek_candidates.json` and NOTHING ELSE
    DOES. It was absent from this script, so no scheduled run ever staged the
    130-name pool: on 2026-09-18 the opportunities section read "the candidate
    pool has not been staged" on a healthy account. It must also precede the
    news refresh, so headlines are fetched for the pool's names rather than
    only the baseline twenty-one."""
    body = code()
    assert 'prepare_factor_pool.py' in body, 'nothing else writes the candidate pool'
    assert body.index('prepare_factor_pool.py') < body.index('prepare_deepseek.py'), \
        'the pool must exist before headlines are fetched for it'
    assert body.index('prepare_factor_pool.py') < body.index('deepseek_opportunities.py')


def test_the_staged_cache_is_actually_pointed_at():
    """bar_cache writes into $RB_STATE_DIR/intraday_cache; morning.sh reads
    RB_INTRADAY_CACHE_DIR. Nothing set it, so every morning staged a cache and
    then acquired all 21 names live beside it."""
    body = code()
    assert 'export RB_INTRADAY_CACHE_DIR' in body
    assert body.index('RB_INTRADAY_CACHE_DIR') < body.index('bar_cache.py')
