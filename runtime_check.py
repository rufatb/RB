"""Verify this host's Python and pinned checkout before the report window."""
import importlib
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parent


def check():
    failures = []
    for module in ('pandas', 'numpy', 'yaml', 'requests', 'pandas_market_calendars',
                   'scipy', 'yfinance', 'brief', 'openai', 'socksio',
                   'adapters.deepseek_adapter', 'factor_inputs', 'prepare_factor_pool',
                   'prepare_yahoo_auth', 'yahoo_auth_cache', 'tsx_universe',
                   'prepare_tsx_universe', 'research_shortlist', 'research_coverage',
                   'research_opening', 'research_evaluation', 'factor_grounding',
                   'grounded_records', 'factor_news', 'factor_macro'):
        try:
            importlib.import_module(module)
        except Exception as exc:
            failures.append({'module': module, 'error': type(exc).__name__})
    revision = subprocess.check_output(['git', '-C', str(ROOT), 'rev-parse', 'HEAD'],
                                       text=True, timeout=5).strip()
    return {'status': 'READY' if not failures else 'NOT READY',
            'python': sys.executable, 'root': str(ROOT), 'code_commit': revision,
            'failures': failures,
            'scope': 'Interpreter/import check only; live data access is not certified.'}


if __name__ == '__main__':
    result = check()
    print(json.dumps(result, indent=2))
    raise SystemExit(0 if result['status'] == 'READY' else 2)
