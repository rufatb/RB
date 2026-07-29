"""
test_daynine.py — day-9: THE PAIR's legs are selected by DENSITY (smallest
k-NN neighbour distance), not by highest P. (Day-12 walkback: the density
EDGE claim did not survive a window roll — densest remains the deterministic
tie-break these tests lock in; see validate_pair.py.) Also: the
crowded-sector warning, pair-only sizing, and the ledger role column.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import ledger
import r945

GROUPS = {"financials": ["RY.TO", "TD.TO", "BMO.TO", "BNS.TO", "CM.TO", "MFC.TO", "SLF.TO"]}


def _pick(t, p_up, nd, tag="mid", p945=100.0):
    return {"t": t, "p_up": p_up, "nd": nd, "confidence": tag, "p945": p945}


def test_pair_selects_densest_not_max_p():
    # B has lower P but a denser neighbourhood -> B is the leg.
    longs = [_pick("A.TO", 0.62, nd=1.4, tag="sparse"),
             _pick("B.TO", 0.56, nd=0.4, tag="dense")]
    pair = r945.pair_of_day(longs, [])
    assert pair["long"]["pick"]["t"] == "B.TO"
    assert pair["long"]["status"] == "DENSE"
    assert pair["long"]["rank_by_p"] == 2       # honesty: shown as #2 by P


def test_pair_max_p_selector_kept_for_comparison():
    longs = [_pick("A.TO", 0.62, nd=1.4), _pick("B.TO", 0.56, nd=0.4)]
    pair = r945.pair_of_day(sorted(longs, key=lambda r: -r["p_up"]), [],
                            selector="max_p")
    assert pair["long"]["pick"]["t"] == "A.TO"


def test_pair_unvalidated_selector_refused():
    with pytest.raises(AssertionError):
        r945.pair_of_day([_pick("A.TO", 0.60, 1.0)], [], selector="vibes")


def test_pair_short_leg_densest_by_sided_direction():
    shorts = [_pick("X.TO", 0.44, nd=0.9), _pick("Y.TO", 0.45, nd=0.3)]
    pair = r945.pair_of_day([], shorts)
    assert pair["short"]["pick"]["t"] == "Y.TO"
    assert pair["short"]["sided"] == pytest.approx(0.55)
    assert pair["long"]["status"] == "NONE"     # never invents the other leg


def test_pair_crowding_warning():
    # Densest leg sits inside a 4-strong same-direction financials move.
    longs = [_pick("RY.TO", 0.58, nd=0.2), _pick("TD.TO", 0.57, nd=0.5),
             _pick("BMO.TO", 0.56, nd=0.6), _pick("CM.TO", 0.56, nd=0.7)]
    pair = r945.pair_of_day(longs, [], groups=GROUPS, crowd_warn=3)
    assert "crowded" in pair["long"].get("warning", "")
    # Two same-group companions only -> no warning.
    pair2 = r945.pair_of_day(longs[:3], [], groups=GROUPS, crowd_warn=3)
    assert "warning" not in pair2["long"]


def test_pair_book_two_legs_capped():
    picks = [_pick("A.TO", 0.58, 0.4, p945=50.0) | {"last": 50.0},
             _pick("B.TO", 0.43, 0.5, p945=25.0) | {"last": 25.0}]
    r945.allocate_book(picks, equity=100_000, max_book_pct=50)
    total = sum(p["alloc"] for p in picks)
    assert total <= 50_000
    assert picks[0]["alloc"] == pytest.approx(25_000, abs=picks[0]["last"])


def test_ledger_role_column_and_pair_report(tmp_path):
    path = str(tmp_path / "ledger.csv")
    ledger.append_picks([
        {"ticker": "A.TO", "side": "LONG", "p_sided": 0.58, "confidence": "dense",
         "p945": 50.0, "role": "pair"},
        {"ticker": "B.TO", "side": "SHORT", "p_sided": 0.56, "confidence": "mid",
         "p945": 25.0, "role": "board"},
    ], "2026-07-11", path)
    rows = ledger.load(path)
    assert [r["role"] for r in rows] == ["pair", "board"]
    rows, n, _ = ledger.score_rows(rows, lambda t: 51.0 if t == "A.TO" else 24.0)
    assert n == 2
    rep = ledger.report(rows)
    assert "PAIR legs" in rep and "board (untraded)" in rep


def test_ledger_old_rows_without_role_still_load(tmp_path):
    # Pre-day-9 CSV had no role column — must load and re-save cleanly.
    path = str(tmp_path / "ledger.csv")
    with open(path, "w") as f:
        f.write("date,ticker,side,p_sided,confidence,p945,r1,hit\n"
                "2026-07-10,T.TO,LONG,0.560,mid,14.8600,,\n")
    rows = ledger.load(path)
    ledger.save(rows, path)                      # restval fills role=""
    rows2 = ledger.load(path)
    assert rows2[0]["role"] == ""
    assert "PAIR legs" not in ledger.report(
        [dict(rows2[0], hit="1", r1="0.5")])     # legacy rows never count as pair


def test_single_leg_day_gets_half_book_not_all(  ):
    # Day-18: a one-legged day must REDUCE exposure — the lone leg gets the
    # standard per-leg size (book/2), never the whole book.
    pick = _pick("MFC.TO", 0.60, 0.4, p945=60.63) | {"last": 60.70}
    r945.allocate_book([pick], equity=100_000, max_book_pct=50)
    assert pick["alloc"] <= 25_000
    assert pick["shares"] == int(25_000 // 60.70)


def test_publish_once_guard_blocks_second_book_run(tmp_path, monkeypatch, capsys):
    # Day-18: a later --book re-run (revised bars -> different board) must
    # not add or alter ledger rows; the first publication stands.
    path = str(tmp_path / "ledger.csv")
    monkeypatch.setattr(ledger, "LEDGER", path)
    ledger.append_picks([{"ticker": "MFC.TO", "side": "LONG", "p_sided": 0.60,
                          "confidence": "dense", "p945": 60.63, "role": "pair"}],
                        "2026-07-22", path)
    fake = {"now": "2026-07-22T09:52:00", "n_names": 21, "min_p": 0.55,
            "longs": [dict(_pick("CM.TO", 0.55, 0.3, tag="dense", p945=166.08),
                           last=166.42, r0=0.17, gap=0.08)],
            "shorts": [], "excluded": [], "too_early": False,
            "late_min": 6.0, "stale_after_min": 20, "spent_drift_pct": 0.3,
            "max_chase_pct": 0.15, "live_record": None}
    fake["pair"] = r945.pair_of_day(fake["longs"], [])
    monkeypatch.setattr(r945, "run", lambda cfg, workers: fake)
    monkeypatch.setattr(r945, "load_config", lambda p: {"risk": {"account_equity": 100000}})
    r945.main(["--book"])
    out = capsys.readouterr().out
    assert "already published" in out
    rows = ledger.load(path)
    assert len(rows) == 1 and rows[0]["ticker"] == "MFC.TO"   # nothing added
