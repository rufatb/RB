#!/usr/bin/env python3
"""Wait by command, for the morning rescue (2026-11-11).

The rescue run (ROUTINE_RESCUE.md) must give the owner's own session a few
minutes to send its 09:00 decision before it acts. A model told "wait two
minutes" either does not, or ends its turn and loses its machine. This blocks
for a fixed time and prints the ET clock, like `morning_wait.py` does for the
morning job.

    python rescue_wait.py --seconds 110      ->  WAITED 110 s · now 09:01:52 ET
    python rescue_wait.py --until 09:12      ->  waits until then (capped at 115 s a call)

Capped below the Bash tool's two-minute default so a call never times out.
"""
from __future__ import annotations

import argparse
import datetime as dt
import sys
import time
from zoneinfo import ZoneInfo

ET = ZoneInfo('America/New_York')
CAP = 115


def seconds_until(hhmm, now=None):
    now = (now or dt.datetime.now(ET)).astimezone(ET)
    h, m = (int(x) for x in hhmm.split(':'))
    target = now.replace(hour=h, minute=m, second=0, microsecond=0)
    return max(0.0, (target - now).total_seconds())


def main(argv=None, *, sleep=time.sleep, clock=None):
    p = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument('--seconds', type=float)
    g.add_argument('--until', metavar='HH:MM')
    a = p.parse_args(argv)
    now = clock() if clock else None
    wait = a.seconds if a.seconds is not None else seconds_until(a.until, now)
    wait = max(0.0, min(CAP, wait))
    sleep(wait)
    after = (clock() if clock else dt.datetime.now(ET)).astimezone(ET)
    left = seconds_until(a.until, after) if a.until else 0.0
    print('%s %d s · now %s ET' % ('WAITED' if left <= 0 else 'STILL_BEFORE', round(wait),
                                   after.strftime('%H:%M:%S')))
    return 0 if left <= 0 else 2


if __name__ == '__main__':
    sys.exit(main())
