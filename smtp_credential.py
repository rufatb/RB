#!/usr/bin/env python3
"""Where the morning's email credential comes from, and what it means when it is absent.

THE DEFECT THIS FILE EXISTS FOR. `morning.sh` has carried a working SMTP send
since day-97 and it has never once fired. The guard reads

    if [ -n "${RB_SMTP_USER:-}" ] && [ -n "${RB_REPORT_TO:-}" ]

and a scheduled container is FRESH — `.rb-state/` is gitignored, nothing in the
Routine ever exported those variables, so every single morning took the `else`
branch and logged one line in the middle of a long log:

    no RB_SMTP_USER / RB_REPORT_TO — published without emailing

That is a silent no-op wearing a log line as a disguise: the run exits 0, the
Routine reports SUCCEEDED, the board really is published, and the owner's inbox
is empty with nothing anywhere saying an email was even attempted. It is the
same shape as the staged-then-ignored cache (day-110d) and the computed-then-
dropped `cache_degraded` (day-110c), and house rule 1 covers all three.

So this module does two things the raw environment cannot:

1. **It accepts a credential FILE**, `$RB_STATE_DIR/secrets/*`, mode 0600 and
   gitignored — the same contract as the DeepSeek and OpenRouter keys. An
   env-only credential cannot survive into a scheduled container, which is
   precisely why this path has never run.
2. **It NAMES what is missing.** `readiness()` returns the specific variables
   and the remedy, so a morning without email says which credential was absent
   instead of saying nothing.

A GMAIL APP PASSWORD CONTAINS SPACES. Google displays it as four groups of
four ("abcd efgh ijkl mnop") and that is what gets pasted. The DeepSeek loader
REJECTS any credential containing whitespace, which is right for a bearer token
and would reject every app password a user ever pastes. Whitespace is stripped
here, not rejected.

AND A CREDENTIAL IS NOT THE WHOLE STORY — MEASURED 2026-09-20. From a Claude
Code container, `smtp.gmail.com` TIMES OUT on 25, 465 AND 587: outbound traffic
goes through an agent proxy that tunnels HTTPS and does not route raw SMTP. So
the credential this module loads is necessary and NOT sufficient here, and
"just add an app password" is the wrong remedy to reach for — the send would
fail at the socket with a perfectly valid password. `REMEDY` says so, because
the obvious reading of "no SMTP credential" is that supplying one fixes it.

Where a scheduled container CAN deliver is over HTTPS: the Gmail connector,
handed `prepare_delivery.artifacts()`'s `gmail_payload.json` (that function
exists for exactly this and predates all of it). This module and the SMTP path
remain correct and tested for a real host, which is where they were designed to
run.

Nothing in this module sends anything.
"""
from __future__ import annotations
import os
from pathlib import Path

# env var -> filename under $RB_STATE_DIR/secrets/
FIELDS = {
    'RB_SMTP_USER': 'smtp_user',
    'RB_SMTP_PASSWORD': 'smtp_app_password',
    'RB_REPORT_TO': 'report_to',
}
MAX_BYTES = 256

REMEDY = (
    'A CLAUDE CODE CONTAINER CANNOT SEND SMTP AT ALL — measured 2026-09-20, '
    'smtp.gmail.com times out on 25, 465 and 587 because the agent proxy '
    'tunnels HTTPS only. An app password does not help there; connect the '
    'Gmail connector (claude.ai Settings -> Connectors) and have the morning '
    'session send prepare_delivery.py\'s gmail_payload.json. '
    'ON A REAL HOST, where port 465 is open: write the three files under '
    '$RB_STATE_DIR/secrets/ (mode 0600) — smtp_user (the sending address), '
    'smtp_app_password (a Google App Password, not the account password), '
    'report_to (the recipient) — or export RB_SMTP_USER / RB_SMTP_PASSWORD / '
    'RB_REPORT_TO.'
)


def _read(state_dir, name):
    path = Path(state_dir)/'secrets'/name
    if not path.is_file():
        return None
    if path.stat().st_size > MAX_BYTES:
        raise ValueError(f'INVALID_SMTP_CREDENTIAL: {name} is implausibly large')
    return path.read_text(encoding='utf-8')


def _clean_address(raw, field):
    value = raw.strip()
    # Header injection: deliver_report.message re-checks this, but a credential
    # carrying a newline must never reach the point of being re-checked.
    if '\n' in value or '\r' in value:
        raise ValueError(f'INVALID_SMTP_CREDENTIAL: {field} contains a line break')
    if '@' not in value:
        raise ValueError(f'INVALID_SMTP_CREDENTIAL: {field} is not an email address')
    return value


def _clean_password(raw):
    # Every whitespace character, not just the ends: a pasted app password is
    # four space-separated groups and Google accepts it either way.
    value = ''.join(raw.split())
    if not value:
        raise ValueError('INVALID_SMTP_CREDENTIAL: empty app password')
    return value


def load_private_smtp(state_dir):
    """Populate os.environ from private files. The environment always wins.

    Returns the list of env var names that are still missing afterwards —
    EMPTY means the morning can email. Raises only on a credential that is
    present and malformed, because that is a different fact from absence and
    must not be reported as "not configured".
    """
    missing = []
    for var, name in FIELDS.items():
        raw = os.environ.get(var)
        if raw is None:
            raw = _read(state_dir, name)
        if raw is None or not raw.strip():
            missing.append(var)
            continue
        value = (_clean_password(raw) if var == 'RB_SMTP_PASSWORD'
                 else _clean_address(raw, var))
        os.environ[var] = value
    return missing


def readiness(state_dir):
    """A description of the delivery channel, for the log and the summary.

    Never raises for absence. A malformed credential is reported as a fault
    with its reason rather than as a missing one — "you pasted the account
    password with a newline in it" and "you have not set this up" need
    different remedies and must not print the same line.
    """
    try:
        missing = load_private_smtp(state_dir)
    except ValueError as exc:
        return dict(ready=False, missing=[], error=str(exc), remedy=REMEDY,
                    sender=None, recipient=None)
    return dict(ready=not missing, missing=missing, error=None,
                remedy=None if not missing else REMEDY,
                sender=os.environ.get('RB_SMTP_USER'),
                recipient=os.environ.get('RB_REPORT_TO'))


def main(argv=None):
    import argparse
    import json
    p = argparse.ArgumentParser(description='Report whether the morning can email.')
    p.add_argument('--state-dir', default=os.getenv('RB_STATE_DIR', '.rb-state'))
    a = p.parse_args(argv)
    state = readiness(a.state_dir)
    print(json.dumps(state, indent=2))
    return 0 if state['ready'] else 2


if __name__ == '__main__':
    raise SystemExit(main())
