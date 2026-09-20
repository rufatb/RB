"""The email that was never sent, and the two ways this could keep happening.

THE DEFECT. `morning.sh` has carried a complete, correct SMTP send since
day-97. It has never once fired. The guard read the environment directly:

    if [ -n "${RB_SMTP_USER:-}" ] && [ -n "${RB_REPORT_TO:-}" ]

and a scheduled container is FRESH — `.rb-state/` is gitignored and the Routine
never exported those variables — so every morning took the else branch, logged
one quiet line in the middle of a long log, exited 0, and the Routine reported
SUCCEEDED. The board really was published. The inbox was empty and nothing
anywhere said an email had even been attempted.

Two things have to hold, and each has its own trap:

1. A credential must be able to arrive the way the DeepSeek and OpenRouter keys
   do — a private file under $RB_STATE_DIR/secrets. An env-only credential
   cannot survive into a scheduled container, which is the whole reason this
   path never ran.
2. A GMAIL APP PASSWORD CONTAINS SPACES. Google shows it as four groups of
   four and that is what gets pasted. `prepare_deepseek.load_private_key`
   REJECTS any credential containing whitespace — correct for a bearer token,
   and it would reject every app password anyone ever pastes. Copying that
   validator here is the obvious mistake and it is tested against.
"""
import os
import subprocess

import pytest

import smtp_credential as S

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP_PASSWORD = 'abcd efgh ijkl mnop'          # exactly how Google displays it


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    for var in S.FIELDS:
        monkeypatch.delenv(var, raising=False)


def secrets(tmp_path, **files):
    d = tmp_path/'secrets'
    d.mkdir(parents=True, exist_ok=True)
    for name, body in files.items():
        (d/name).write_text(body)
    return tmp_path


# ── the app-password trap ────────────────────────────────────────────────────

def test_an_app_password_pasted_with_spaces_is_accepted(tmp_path):
    """The DeepSeek validator would reject this, and it is the ONLY form a
    person ever pastes."""
    state = secrets(tmp_path, smtp_user='a@b.com', smtp_app_password=APP_PASSWORD,
                    report_to='c@d.com')
    assert S.load_private_smtp(state) == []
    assert os.environ['RB_SMTP_PASSWORD'] == 'abcdefghijklmnop'


def test_a_trailing_newline_on_the_password_does_not_become_part_of_it(tmp_path):
    state = secrets(tmp_path, smtp_user='a@b.com',
                    smtp_app_password=APP_PASSWORD + '\n', report_to='c@d.com')
    S.load_private_smtp(state)
    assert os.environ['RB_SMTP_PASSWORD'] == 'abcdefghijklmnop'


def test_an_empty_password_file_is_a_fault_not_a_credential(tmp_path):
    state = secrets(tmp_path, smtp_user='a@b.com', smtp_app_password='   \n',
                    report_to='c@d.com')
    assert 'RB_SMTP_PASSWORD' in S.load_private_smtp(state)


# ── addresses ────────────────────────────────────────────────────────────────

def test_a_line_break_in_an_address_is_refused_before_it_reaches_the_mailer(tmp_path):
    """Header injection. deliver_report.message re-checks this; a credential
    carrying a newline must never get far enough to be re-checked."""
    state = secrets(tmp_path, smtp_user='a@b.com\nBcc: x@y.com',
                    smtp_app_password=APP_PASSWORD, report_to='c@d.com')
    with pytest.raises(ValueError, match='line break'):
        S.load_private_smtp(state)


def test_something_that_is_not_an_address_is_refused(tmp_path):
    state = secrets(tmp_path, smtp_user='not-an-address',
                    smtp_app_password=APP_PASSWORD, report_to='c@d.com')
    with pytest.raises(ValueError, match='not an email address'):
        S.load_private_smtp(state)


# ── absence is a reportable state, never an exception ────────────────────────

def test_absence_names_every_missing_variable(tmp_path):
    assert set(S.load_private_smtp(tmp_path)) == set(S.FIELDS)


def test_readiness_never_raises_for_absence_and_carries_the_remedy(tmp_path):
    state = S.readiness(tmp_path)
    assert state['ready'] is False and state['error'] is None
    assert state['missing'] and state['remedy']


def test_readiness_separates_malformed_from_missing(tmp_path):
    """"you pasted the account password with a newline in it" and "you have
    not set this up" need different remedies and must not print alike."""
    state = secrets(tmp_path, smtp_user='a@b.com\nBcc: x@y.com',
                    smtp_app_password=APP_PASSWORD, report_to='c@d.com')
    out = S.readiness(state)
    assert out['ready'] is False and out['error'] and not out['missing']


def test_the_environment_wins_over_the_file(tmp_path, monkeypatch):
    state = secrets(tmp_path, smtp_user='file@b.com', smtp_app_password=APP_PASSWORD,
                    report_to='c@d.com')
    monkeypatch.setenv('RB_SMTP_USER', 'env@b.com')
    S.load_private_smtp(state)
    assert os.environ['RB_SMTP_USER'] == 'env@b.com'


def test_the_cli_exit_code_distinguishes_configured_from_not(tmp_path):
    assert S.main(['--state-dir', str(tmp_path)]) == 2
    state = secrets(tmp_path, smtp_user='a@b.com', smtp_app_password=APP_PASSWORD,
                    report_to='c@d.com')
    assert S.main(['--state-dir', str(state)]) == 0


def test_the_cli_never_prints_the_password(tmp_path, capsys):
    state = secrets(tmp_path, smtp_user='a@b.com', smtp_app_password=APP_PASSWORD,
                    report_to='c@d.com')
    S.main(['--state-dir', str(state)])
    assert 'abcdefghijklmnop' not in capsys.readouterr().out


# ── the wiring, which is where the silence lived ─────────────────────────────

def body(name):
    """Commands only — an assertion about behaviour must not match the prose
    that explains it (same trap as test_morning_full.code)."""
    out = []
    for line in open(os.path.join(ROOT, name)).read().splitlines():
        for i, ch in enumerate(line):
            if ch == '#' and line[:i].count("'") % 2 == 0 and line[:i].count('"') % 2 == 0:
                line = line[:i]
                break
        if line.strip():
            out.append(line.rstrip())
    return '\n'.join(out)


def test_morning_no_longer_decides_by_reading_the_environment_itself():
    """THE BUG. The shell guard could not see a private file, so a credential
    staged the documented way would still have been skipped in silence."""
    commands = body('morning.sh')
    assert 'deliver_report.py' in commands
    assert '-n "${RB_SMTP_USER:-}"' not in commands, \
        'the guard is back: a file-supplied credential is invisible to it'


def test_an_unemailed_morning_says_so_in_a_line_the_summary_can_quote():
    commands = body('morning.sh')
    assert 'DELIVERY: NOT EMAILED' in commands and 'DELIVERY: email sent' in commands


def test_morning_full_checks_the_credential_while_there_is_still_time():
    """Beside the DeepSeek check at the top, for the same reason: the remedy
    only helps before the publication window."""
    commands = body('morning_full.sh')
    assert 'smtp_credential.py' in commands
    assert commands.index('smtp_credential.py') < commands.index('./morning.sh')


def test_a_missing_credential_does_not_stop_the_board():
    """Delivery is downstream of publication. An unconfigured inbox may cost
    the email and must never cost the record (the day-99 lesson: a shadow or
    downstream layer never vetoes the morning)."""
    commands = body('morning.sh')
    delivery = commands.index('DELIVERY: NOT EMAILED')
    assert 'git push' in commands[delivery:], 'the record push must still follow'


def test_the_secrets_directory_is_gitignored():
    out = subprocess.run(['git', 'check-ignore', '-q', '.rb-state/secrets/smtp_app_password'],
                         cwd=ROOT)
    assert out.returncode == 0, 'the app password would be committable'
