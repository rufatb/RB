"""
test_ledger.py — the permanent learning ledger: publish-time append with
dedupe, outcome scoring, and the cumulative report (density hypothesis).
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import ledger


def _picks():
    return [{"ticker": "A.TO", "side": "LONG", "p_sided": 0.58,
             "confidence": "dense", "p945": 100.0},
            {"ticker": "B.TO", "side": "SHORT", "p_sided": 0.56,
             "confidence": "sparse", "p945": 50.0}]


def test_append_and_dedupe(tmp_path):
    p = str(tmp_path / "l.csv")
    assert ledger.append_picks(_picks(), "2026-07-09", p) == 2
    assert ledger.append_picks(_picks(), "2026-07-09", p) == 0   # re-run: no dupes
    assert ledger.append_picks(_picks(), "2026-07-10", p) == 2   # new day: new rows


def test_score_rows_direction_aware(tmp_path):
    p = str(tmp_path / "l.csv")
    ledger.append_picks(_picks(), "2026-07-09", p)
    rows = ledger.load(p)
    rows, n = ledger.score_rows(rows, {"A.TO": 101.0, "B.TO": 51.0}.get)
    assert n == 2
    a = next(r for r in rows if r["ticker"] == "A.TO")
    b = next(r for r in rows if r["ticker"] == "B.TO")
    assert a["hit"] == "1"        # long, closed +1%
    assert b["hit"] == "0"        # short, closed +2% against
    # scoring is idempotent: already-scored rows untouched
    rows, n2 = ledger.score_rows(rows, lambda t: 999.0)
    assert n2 == 0 and a["hit"] == "1"


def test_report_aggregates_by_tag(tmp_path):
    p = str(tmp_path / "l.csv")
    ledger.append_picks(_picks(), "2026-07-09", p)
    rows, _ = ledger.score_rows(ledger.load(p), {"A.TO": 101.0, "B.TO": 51.0}.get)
    rep = ledger.report(rows)
    assert "ALL" in rep and "[dense]" in rep and "[sparse]" in rep
    assert "1/1" in rep           # dense long hit
