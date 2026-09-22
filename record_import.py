#!/usr/bin/env python3
"""Bring a scheduled run's record home, from the files it published.

WHY THIS EXISTS. No automated `record:` commit has EVER landed on any branch
since the scheduled Routine went live on 2026-09-16. Every morning computed a
board, wrote its ledger rows into the container's checkout, failed to push,
and the rows died with the container — which is the "RECORD HAS A HOLE: 9
trading days" line on every report. The run's transcript is not readable from
here, so the cause of the push failure is not established; the fix does not
depend on it.

The morning run now publishes its record files beside the email payload on the
owner's artifact (`record/…`). A session that CAN push — the bridge — reads
them and merges them here, append-only, through the same conflict-checked
`sync_runtime.merge` that already guards imported records: an existing row is
never overwritten, a conflicting row fails the whole import loudly, and code is
never taken from the published files, only CSV rows and the frozen report.
"""
from __future__ import annotations

import argparse
import csv
import io
import json
from pathlib import Path

import model_picks
from sync_runtime import FILES, merge

ROOT = Path(__file__).resolve().parent


def _rows(text):
    return list(csv.DictReader(io.StringIO(text)))


def import_dir(source, *, root=ROOT):
    """Merge `source/{ledger.csv,universe_prints.csv}` and record model picks
    from `source/report.json`. Returns what was added; raises on conflict
    BEFORE writing anything."""
    source, root = Path(source), Path(root)
    staged, added = {}, {}
    for name, keys in FILES.items():
        incoming_path = source / name
        if not incoming_path.exists():
            continue
        target_text = (root / name).read_text()
        incoming_text = incoming_path.read_text()
        header = next(csv.reader(io.StringIO(target_text)))
        if next(csv.reader(io.StringIO(incoming_text))) != header:
            raise ValueError(f'{name}: published schema differs from the repository')
        merged, new = merge(_rows(target_text), _rows(incoming_text), keys)
        out = io.StringIO()
        writer = csv.DictWriter(out, fieldnames=header)
        writer.writeheader()
        writer.writerows(merged)
        staged[name] = out.getvalue()
        added[name] = len(new)
    # All-or-nothing: every file validated before any is written.
    for name, text in staged.items():
        (root / name).write_text(text)
    report_path = source / 'report.json'
    if report_path.exists():
        report = json.loads(report_path.read_text())
        added['model_picks'] = model_picks.append(
            model_picks.rows_from_report(report), root / 'data' / 'model_picks.csv')
        added['session'] = report.get('session')
    return added


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    p.add_argument('source', help='directory holding the published record/ files')
    p.add_argument('--root', default=str(ROOT))
    a = p.parse_args(argv)
    print(json.dumps(import_dir(a.source, root=a.root)))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
