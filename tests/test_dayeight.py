"""
test_dayeight.py — day-8 lessons: the peer-contradiction gate (TD's exact
case is the regression test) and the daily-pair quality contract.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import r945

GROUPS = {"financials": ["RY.TO", "TD.TO", "BMO.TO", "BNS.TO", "CM.TO", "MFC.TO", "SLF.TO"],
          "gold": ["ABX.TO", "AEM.TO"]}


def _p(t, p_up):
    return {"t": t, "p_up": p_up}


def test_td_case_lone_bank_short_excluded():
    # Day-8 reality: 6 financial longs qualified, TD alone short -> excluded
    longs = [_p("BMO.TO", .65), _p("MFC.TO", .61), _p("SLF.TO", .60),
             _p("BNS.TO", .58), _p("CM.TO", .57), _p("RY.TO", .56)]
    shorts = [_p("TD.TO", .45)]
    L, S, ex = r945.peer_gate(longs, shorts, GROUPS, 3)
    assert S == [] and len(ex) == 1 and ex[0]["t"] == "TD.TO"
    assert "financials" in ex[0]["excluded_reason"]
    assert len(L) == 6                          # longs untouched


def test_gate_symmetric_for_lone_long():
    longs = [_p("TD.TO", .56)]
    shorts = [_p("BMO.TO", .44), _p("MFC.TO", .44), _p("SLF.TO", .45)]
    L, S, ex = r945.peer_gate(longs, shorts, GROUPS, 3)
    assert L == [] and ex[0]["t"] == "TD.TO" and len(S) == 3


def test_gate_needs_min_opposed():
    longs = [_p("BMO.TO", .60), _p("MFC.TO", .59)]      # only 2 opposing
    shorts = [_p("TD.TO", .45)]
    L, S, ex = r945.peer_gate(longs, shorts, GROUPS, 3)
    assert len(S) == 1 and ex == []             # below threshold: kept


def test_gate_ignores_ungrouped_names():
    longs = [_p("SHOP.TO", .60)] * 5
    shorts = [_p("AC.TO", .44)]
    L, S, ex = r945.peer_gate(longs, shorts, GROUPS, 3)
    assert len(S) == 1 and ex == []


def test_pair_quality_and_missing_leg():
    pair = r945.pair_of_day([_p("BMO.TO", .65)], [])
    assert pair["long"]["status"] == "STRONG"
    assert pair["short"]["status"] == "NONE"
    pair2 = r945.pair_of_day([_p("X.TO", .551)], [_p("Y.TO", .449)])
    assert "WEAK" in pair2["long"]["status"] and "WEAK" in pair2["short"]["status"]
