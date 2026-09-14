"""Explicit synthetic API contract check; never a market or morning snapshot."""
import argparse
import datetime as dt
import json
import os
import time
from pathlib import Path
from zoneinfo import ZoneInfo

from adapters.deepseek_adapter import evaluate_batch, MACRO_KEYS
from build_biotech import write_atomic
from prepare_deepseek import load_private_key, load_private_model


def probe(state_dir, *, evaluator=evaluate_batch):
    now = dt.datetime.now(ZoneInfo('America/New_York'))
    # Deliberately fictitious symbols and explicitly synthetic public-looking
    # fixture URLs; no observed market fact or provider data receipt is asserted.
    rows = [{'ticker': 'TEST'+str(i), 'technicals': {'rsi': 50.0},
             'technicals_as_of': now.isoformat(), 'technicals_scope': 'SYNTHETIC CONTRACT FIXTURE',
             'technical_source': 'python', 'source_url': 'https://example.com/synthetic',
             'headlines': [{'title': 'Synthetic API contract fixture: no directional evidence; not a real issuer.',
                            'source_url': 'https://example.com/synthetic', 'published_at': now.isoformat()}],
             'catalyst_tags': []} for i in range(25)]
    macro = {name: {'value': 100.0, 'as_of': now.isoformat(),
                    'source_url': 'https://example.com/synthetic'} for name in MACRO_KEYS}
    load_private_key(state_dir)
    model = load_private_model(state_dir)
    started = time.monotonic()
    result = evaluator(rows, macro, now.isoformat(), model=model)
    receipt = {'kind': 'SYNTHETIC_API_SCHEMA_PROBE_NOT_MARKET_DATA',
               'checked_at': now.isoformat(), 'elapsed_seconds': round(time.monotonic()-started, 3),
               'requested': 25, 'covered': len(result.get('assessments', [])),
               **{k: result.get(k) for k in ('status', 'model', 'response_model', 'inference_mode',
                    'request_id', 'response_id', 'input_sha256', 'errorcode', 'details')},
               'prediction_evidence': False}
    path = Path(state_dir)/'diagnostics'/('deepseek-contract-'+now.strftime('%Y%m%dT%H%M%S%f')+'.json')
    write_atomic(path, receipt)
    return receipt


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--state-dir', required=True)
    args = parser.parse_args()
    result = probe(args.state_dir)
    print(json.dumps(result, indent=2))
    raise SystemExit(0 if result['status'] == 'READY' else 2)
