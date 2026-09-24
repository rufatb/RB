#!/usr/bin/env python3
"""Block until the background `morning_full.sh` has finished, a bounded slice at a time.

WHY THIS EXISTS. 2026-09-24: the scheduled report session started
`morning_full.sh` in the background as instructed, answered nothing, and ENDED
ITS TURN at 08:54 ET, three and a half minutes in. A scheduled session that ends
its turn is idle; an idle session's container is reclaimed, and the background
job died with it. Nothing was staged, nothing published, no email. The prompt
said "read the tail of the log now and then", which a model can satisfy once
and then stop.

This makes waiting a COMMAND. Each call blocks for at most `--timeout` seconds
(inside the Bash tool's ten-minute limit) and prints exactly one status line:

    RUNNING <last log line>      the job is alive — call this again
    DONE <exit code>             `morning_full.sh` logged its own exit
    NOT_STARTED                  no log yet — the job was never started
    STALLED <seconds>            the log has not moved for --stall seconds

Exit codes mirror them (0 DONE, 10 RUNNING, 11 NOT_STARTED, 12 STALLED) so a
session can loop on the code without parsing prose. The job's own exit code is
printed, never swallowed (house rule 1).
"""
from __future__ import annotations

import argparse
import re
import sys
import time
from pathlib import Path

DONE = re.compile(r'morning\.sh exit (-?\d+)')
POLL_SECONDS = 5.0


def status(log, stall_seconds, now=None):
    """(state, detail) for the log as it stands. Pure apart from reading the file."""
    path = Path(log)
    if not path.exists():
        return 'NOT_STARTED', ''
    text = path.read_text(errors='replace')
    lines = [l for l in text.splitlines() if l.strip()]
    for line in reversed(lines):
        m = DONE.search(line)
        if m:
            return 'DONE', m.group(1)
    age = (now if now is not None else time.time()) - path.stat().st_mtime
    if age > stall_seconds:
        return 'STALLED', str(int(age))
    return 'RUNNING', (lines[-1] if lines else '')[:200]


def wait(log, timeout, stall_seconds, *, clock=time.monotonic, sleep=time.sleep):
    end = clock() + timeout
    while True:
        state, detail = status(log, stall_seconds)
        if state != 'RUNNING' or clock() >= end:
            return state, detail
        sleep(min(POLL_SECONDS, max(0.0, end - clock())))


CODES = {'DONE': 0, 'RUNNING': 10, 'NOT_STARTED': 11, 'STALLED': 12}


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    p.add_argument('--log', default='.rb-state/morning_full.log')
    p.add_argument('--timeout', type=float, default=540.0,
                   help='seconds to block in this call (keep under the 600s tool limit)')
    p.add_argument('--stall', type=float, default=1500.0,
                   help='seconds without a new log line before reporting STALLED; '
                        'the 09:24-09:44 hold logs nothing for ~20 minutes')
    a = p.parse_args(argv)
    state, detail = wait(a.log, a.timeout, a.stall)
    print(f'{state} {detail}'.rstrip(), flush=True)
    return CODES[state]


if __name__ == '__main__':
    sys.exit(main())
