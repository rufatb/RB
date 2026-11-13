"""Data-only DDA sidecars. No wait, email send, or original decision changes."""
import os
from pathlib import Path
import subprocess
import sys


def start(state_dir, action, *, popen=subprocess.Popen):
    if os.getenv('RB_DDA_ENABLED', '1') != '1':
        return False
    root = Path(__file__).resolve().parent
    state = Path(state_dir).resolve()
    state.mkdir(parents=True, exist_ok=True)
    if action not in {'research', 'opening', 'open-check', 'report'}:
        raise ValueError('DDA_UNKNOWN_HOOK')
    args = ['--stage'] if action == 'research' else ['--export', action]
    try:
        with (state/'dda-hook.log').open('ab') as log:
            popen([sys.executable, str(root/'dda_desk.py'), '--state-dir', str(state), *args, '--publish'],
                  cwd=root, stdin=subprocess.DEVNULL, stdout=log, stderr=log,
                  start_new_session=True, close_fds=True)
        return True
    except OSError:
        return False  # The original report and emails must continue.


if __name__ == '__main__':
    start(sys.argv[1], sys.argv[2])
