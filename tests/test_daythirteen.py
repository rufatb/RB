"""
test_daythirteen.py — day-13: the deep search found NO encodable fix, and
that is the finding. The crowding stat (44% on two windows, a live warned
loss) flipped to 61% with ONE added session; board-tilt flipped between
splits. At ~50 sessions of free 5m data no further gate is provable.
Encoded instead: the accountability header (the tool prints its own live
record and a no-demonstrated-edge warning) and the explicit sizing
contract (share counts ARE the risk model).
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import ledger
import r945


def _row(hit, role="board"):
    return {"date": "2026-07-16", "ticker": "X.TO", "side": "LONG",
            "p_sided": "0.55", "confidence": "mid", "p945": "1", "role": role,
            "r1": "0.1", "hit": hit}


def test_live_summary_counts_all_pair_recent():
    rows = [_row("1"), _row("0", role="pair"), _row("1", role="pair"), _row("0")]
    s = ledger.live_summary(rows, last_n=2)
    assert s["all_n"] == 4 and s["all_hits"] == 2
    assert s["pair_n"] == 2 and s["pair_hits"] == 1
    assert s["recent_n"] == 2 and s["recent_hits"] == 1


def test_live_summary_none_when_unscored():
    assert ledger.live_summary([dict(_row("1"), hit="")]) is None


def _res(live_record):
    pick = {"t": "CVE.TO", "p_up": 0.55, "nd": 0.4, "confidence": "dense",
            "p945": 38.62, "last": 38.61, "r0": 0.18, "gap": 0.23}
    return {"now": "2026-07-16T09:46:00", "n_names": 21, "longs": [pick],
            "shorts": [], "excluded": [], "min_p": 0.55, "too_early": False,
            "pair": r945.pair_of_day([pick], []), "late_min": 0.0,
            "stale_after_min": 20, "spent_drift_pct": 0.3,
            "max_chase_pct": 0.15, "live_record": live_record}


def test_render_prints_live_record_and_no_edge_warning(capsys):
    lr = {"all_n": 66, "all_hits": 33, "pair_n": 8, "pair_hits": 3,
          "recent_n": 20, "recent_hits": 10}
    r945.render(_res(lr))
    out = capsys.readouterr().out
    assert "LIVE RECORD" in out and "33/66" in out and "PAIR 3/8" in out
    assert "NOT yet demonstrated an edge" in out


def test_no_edge_warning_suppressed_when_record_clears_bar(capsys):
    lr = {"all_n": 100, "all_hits": 58, "pair_n": 40, "pair_hits": 24,
          "recent_n": 20, "recent_hits": 12}
    r945.render(_res(lr))
    out = capsys.readouterr().out
    assert "LIVE RECORD" in out and "NOT yet demonstrated" not in out
