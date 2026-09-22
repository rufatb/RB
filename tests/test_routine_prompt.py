"""The scheduled prompt is executable instructions. Check it like code.

THE DEFECT, found 2026-09-21 by the session that had to paste it. The file
carried two stale step numbers from an earlier draft, where the email was
STEP 6. After the artifact-files step was inserted every number shifted, the
headings moved, and two cross-references did not:

  * "You send the email in STEP 6" — STEP 6 is the artifact publish.
  * ALREADY_ATTEMPTED said "continue to STEP 7" — and STEP 7 IS THE SEND.
    That routes a delivery which has already been attempted straight back into
    sending it, which is exactly and only what the publish-once claim exists to
    prevent. A second copy of the morning board in the owner's inbox.

Neither was reachable by any test in this repo, because the prompt is prose. It
is not prose: an unattended agent follows it at 09:05 with nobody watching, and
a wrong number in it is a live bug with the same consequences as a wrong number
in Python. The file's own header warns that a prompt out of sync with the live
Routine "becomes a confident description of something that no longer exists" —
this is that, one level down.
"""
import os
import re

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROMPT = os.path.join(ROOT, 'ROUTINE_PROMPT.md')


def text():
    return open(PROMPT, encoding='utf-8').read()


def headings():
    """{number: title} for every `STEP n — title` that opens a step."""
    return {int(n): title.strip()
            for n, title in re.findall(r'^STEP (\d+) — (.+)$', text(), re.M)}


def test_the_steps_are_numbered_consecutively_from_one():
    steps = headings()
    assert steps, 'no steps found — the file layout changed'
    assert sorted(steps) == list(range(1, len(steps) + 1)), sorted(steps)


def test_every_referenced_step_exists():
    steps = headings()
    for n in {int(n) for n in re.findall(r'STEP (\d+)', text())}:
        assert n in steps, f'the prompt points at STEP {n}, which does not exist'


def test_the_email_is_sent_at_the_step_the_prompt_says_it_is():
    """"You send the email in STEP 6" pointed at the artifact publish."""
    steps = headings()
    send = [n for n, title in steps.items() if 'EMAIL IT' in title]
    assert len(send) == 1, 'exactly one step sends the email'
    line = next(l for l in text().splitlines() if 'You send the email in STEP' in l)
    assert f'STEP {send[0]}' in line, line


def test_an_already_attempted_delivery_is_never_routed_into_the_send():
    """THE BUG THAT MATTERED. It said "continue to STEP 7" and STEP 7 is the
    send, so the one branch whose entire job is to NOT send pointed at
    sending."""
    steps = headings()
    send = next(n for n, title in steps.items() if 'EMAIL IT' in title)
    line = next(l for l in text().splitlines() if 'ALREADY_ATTEMPTED' in l)
    targets = {int(n) for n in re.findall(r'continue to STEP (\d+)', line)}
    assert targets, 'the ALREADY_ATTEMPTED branch no longer says where to go'
    assert send not in targets, (
        f'ALREADY_ATTEMPTED routes into STEP {send}, the send — that is a '
        'duplicate email, the exact failure the claim prevents')
    summary = next(n for n, title in steps.items() if 'SHORT summary' in title)
    assert targets == {summary}, targets


@pytest.mark.parametrize('secret', ['sk-f8691', 'sk-or-v1-'])
def test_no_live_credential_is_committed_in_the_prompt(secret):
    """GitHub push protection caught this once already. It is a public repo and
    "private credentials and diagnostics stay outside git" is a standing rule."""
    assert secret not in text()
    assert '<DEEPSEEK_API_KEY>' in text() and '<OPENROUTER_API_KEY>' in text()


def test_the_prompt_still_forbids_touching_the_schedule():
    """The live task carries scheduled-task tools, so this refusal is the
    second line of defence behind removing the connector."""
    body = text()
    assert 'DO NOT TOUCH THE SCHEDULE' in body
    assert 'Never create, modify, enable, disable or delete any Routine' in body


def test_every_command_the_prompt_names_actually_exists():
    """A prompt that tells an unattended agent to run a script that is not
    there fails at 09:05 with nobody watching."""
    for script in re.findall(r'python (\w+\.py)', text()):
        assert os.path.exists(os.path.join(ROOT, script)), script
    for script in re.findall(r'\./(\w+\.sh)', text()):
        assert os.path.exists(os.path.join(ROOT, script)), script


def flags_of(module):
    """Every long option the module's parser accepts, from its own source."""
    import inspect
    return set(re.findall(r"add_argument\(\s*'(--[a-z-]+)'", inspect.getsource(module)))


@pytest.mark.parametrize('module_name', ['gmail_delivery', 'report_page',
                                         'prepare_factor_pool', 'deepseek_opportunities', 'claude_opportunities',
                                         'jev_opportunities'])
def test_every_flag_the_prompt_quotes_is_a_real_option(module_name):
    """The prompt quotes command lines verbatim for an unattended agent to run.
    A flag renamed in Python and not here is discovered at 09:46, by which time
    the staging window has closed."""
    module = __import__(module_name)
    accepted = flags_of(module)
    if not accepted:
        pytest.skip(f'{module_name} exposes no long options to check')
    for line in text().splitlines():
        if f'{module_name}.py' not in line:
            continue
        for flag in re.findall(r'(--[a-z-]+)', line):
            assert flag in accepted, (
                f'the prompt runs {module_name}.py {flag}, which it does not accept')
