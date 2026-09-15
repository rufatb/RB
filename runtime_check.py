"""Verify this host's Python and pinned checkout before the report window.

TWO CLASSES OF IMPORT, and the distinction is the whole point of this file.

REQUIRED is what the 09:46 report cannot produce a board without. A failure
here is a real blackout and `morning.sh` must stop rather than publish a
half-computed record.

OPTIONAL is everything the report is designed to DEGRADE around — today that
is the day-99 DeepSeek factor layer, which is shadow, unadopted, read from a
pre-staged snapshot, and already wrapped in `brief.compute`'s recorded-error
path. Blocking the morning on it would mean an optional research module with
no adopted output could silently cost the day's entire record and email. That
is exactly what this list previously did: `openai` and `socksio` went into the
required set with the day-99 merge, and on any host whose venv predates that
merge `runtime_check` exits non-zero, `morning.sh` exits 1, and no report and
no email are produced at all.

Optional failures are NOT swallowed (house rule 1). They are counted, named,
carried in the JSON, and `morning.sh` logs them loudly — the run is marked
DEGRADED and says which module is missing. It just does not lose the day.
"""
import importlib
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parent

REQUIRED = ('pandas', 'numpy', 'yaml', 'requests', 'pandas_market_calendars',
            'scipy', 'yfinance', 'brief')

# Reason each optional module is optional, printed beside the failure so the
# cron mail says what is lost rather than only what is missing.
# Day-101/102 added sixteen more names to the blocking list. Every one of them
# is reached through a try/except in `brief._compute` that records the failure
# and degrades — `research_coverage` and `research_opening` included (see
# brief.py, the `expanded_present` and `research_opening_snapshot` blocks).
# Hard-requiring twenty-four imports in front of the report means any one of
# sixteen degradable research modules can cost the day's board, its ledger row
# and its email. They are checked and named here; they do not block.
OPTIONAL = {
    'openai': 'DeepSeek preparation client (prepare_deepseek only; never the 09:46 path)',
    'socksio': 'SOCKS proxy support for that client on headless hosts',
    'adapters.deepseek_adapter': 'staged DeepSeek snapshot parsing; report degrades to UNAVAILABLE',
    'factor_inputs': 'staged DeepSeek input validation; report degrades to UNAVAILABLE',
    'prepare_factor_pool': 'pre-open factor pool staging; coverage degrades to UNAVAILABLE',
    'prepare_yahoo_auth': 'pre-open Yahoo auth staging; live acquisition re-authenticates',
    'yahoo_auth_cache': 'cached Yahoo crumb; acquisition falls back to bootstrap',
    'tsx_universe': 'expanded TSX directory; research coverage degrades',
    'prepare_tsx_universe': 'pre-open directory staging; research coverage degrades',
    'research_shortlist': 'expanded research shortlist; unadopted research only',
    'research_coverage': 'expanded coverage section; brief records the failure and degrades',
    'research_opening': 'shadow opening context; brief records the failure and degrades',
    'research_evaluation': 'unadopted research evaluation',
    'factor_grounding': 'DeepSeek evidence grounding; assessment degrades',
    'grounded_records': 'grounded evidence records; assessment degrades',
    'factor_news': 'pre-open headline evidence; preparation-only',
    'factor_macro': 'pre-open macro references; preparation-only',
}


def _import_failures(modules):
    failures = []
    for module in modules:
        try:
            importlib.import_module(module)
        except Exception as exc:
            failures.append({'module': module, 'error': type(exc).__name__})
    return failures


def check():
    failures = _import_failures(REQUIRED)
    optional_failures = _import_failures(OPTIONAL)
    for failure in optional_failures:
        failure['degrades'] = OPTIONAL[failure['module']]
    revision = subprocess.check_output(['git', '-C', str(ROOT), 'rev-parse', 'HEAD'],
                                       text=True, timeout=5).strip()
    return {'status': 'READY' if not failures else 'NOT READY',
            'degraded': bool(optional_failures),
            'python': sys.executable, 'root': str(ROOT), 'code_commit': revision,
            'failures': failures,
            'optional_failures': optional_failures,
            'scope': 'Interpreter/import check only; live data access is not certified. '
                     'Optional failures degrade the shadow factor section; they do not '
                     'block publication and are not evidence the provider is reachable.'}


def exit_code(result):
    """Only a REQUIRED failure is non-zero.

    Separated from __main__ so the rule itself is testable: a degraded result
    must still exit 0, because `morning.sh` turns any non-zero here into a lost
    report and a silent inbox.
    """
    return 0 if result['status'] == 'READY' else 2


if __name__ == '__main__':
    result = check()
    print(json.dumps(result, indent=2))
    raise SystemExit(exit_code(result))
