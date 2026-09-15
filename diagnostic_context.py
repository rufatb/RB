"""Explicit isolated current-time diagnostics; never a production clock override."""
from __future__ import annotations

import datetime as dt
import json
from pathlib import Path
from zoneinfo import ZoneInfo

KIND = 'DEEPSEEK_PIPELINE_DIAGNOSTIC'
SNAPSHOT_KIND = 'CURRENT_TIME_DIAGNOSTIC'
ET = ZoneInfo('America/New_York')


def create_context(directory, *, now=None):
    """A new empty directory only; no copied publication database or attempt."""
    root = Path(directory)
    now = now or dt.datetime.now(ET)
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError('AWARE_DIAGNOSTIC_CLOCK_REQUIRED')
    root.mkdir(parents=True, exist_ok=False)
    obj = {'kind': KIND, 'started_at': now.astimezone(ET).isoformat(),
           'morning_snapshot': False, 'prediction_evidence': False,
           'scope': 'Current-time integration diagnostic; not a reconstructed morning prediction.'}
    (root/'diagnostic_context.json').write_text(json.dumps(obj, indent=2))
    return obj


def require_context(directory):
    """Refuse a canonical report state even if somebody copies in a marker."""
    root = Path(directory)
    if (root/'reports.sqlite3').exists() or (root/'operations.json').exists():
        raise ValueError('DIAGNOSTIC_REQUIRES_ISOLATED_NONPUBLICATION_STATE')
    try:
        obj = json.loads((root/'diagnostic_context.json').read_text())
        started = dt.datetime.fromisoformat(obj['started_at'])
        if (obj.get('kind') != KIND or obj.get('morning_snapshot') is not False
                or obj.get('prediction_evidence') is not False
                or started.tzinfo is None or started.utcoffset() is None):
            raise ValueError('INVALID_DIAGNOSTIC_CONTEXT')
    except (OSError, ValueError, TypeError, KeyError):
        raise ValueError('EXPLICIT_ISOLATED_DIAGNOSTIC_CONTEXT_REQUIRED') from None
    return obj
