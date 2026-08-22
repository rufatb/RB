"""Day-54: arithmetic guardrails for binary-catalyst theses.

The prompting case stated upside $36 / downside $20.50 / price $25 / p=85%.
That triple is impossible: it implies a -$37.33 downside. These lock the
three failure modes and, just as importantly, lock the SILENCE on a sound
thesis — a checker that always objects is worth nothing.
"""

import pytest

import catalyst as c


def test_implied_probability_is_the_price_inside_the_bracket():
    assert c.implied_probability(25.0, 36.0, 20.5) == pytest.approx(0.2903, abs=1e-4)
    assert c.implied_probability(20.5, 36.0, 20.5) == 0.0     # priced for failure
    assert c.implied_probability(36.0, 36.0, 20.5) == 1.0     # priced for approval


def test_implied_probability_refuses_an_inverted_bracket():
    with pytest.raises(ValueError):
        c.implied_probability(25.0, 20.0, 30.0)


def test_the_prompting_thesis_is_arithmetically_impossible():
    a = c.assess(25.0, 36.0, 20.5, 0.85)
    assert a["blocking"] is True
    assert a["needed_downside"] < 0
    assert any("Impossible" in f for f in a["findings"])


def test_market_implied_probability_beats_the_claim_into_the_open():
    a = c.assess(25.0, 36.0, 20.5, 0.85)
    assert a["p_market"] == pytest.approx(0.2903, abs=1e-4)
    assert a["gap"] == pytest.approx(0.56, abs=0.01)
    assert any("UNDEFENDED" in f for f in a["findings"])


def test_a_price_outside_the_bracket_blocks():
    a = c.assess(40.0, 36.0, 20.5, 0.85)          # trading above the upside
    assert a["blocking"] is True
    assert any("sits above the upside" in f for f in a["findings"])


def test_breakeven_rises_as_the_assumed_floor_falls():
    t = c.breakeven_table(25.0, 36.0, [20.5, 15.0, 12.0, 9.0])
    bes = [be for _, _, be in t]
    assert bes == sorted(bes)                      # strictly worse floors, higher bar
    assert bes[0] == pytest.approx(0.290, abs=1e-3)
    assert bes[-1] == pytest.approx(0.593, abs=1e-3)


def test_claim_above_the_first_cycle_base_rate_is_flagged():
    a = c.assess(25.0, 36.0, 22.0, 0.85)
    assert any("ABOVE BASE RATE" in f for f in a["findings"])


def test_a_sound_thesis_passes_silently():
    """A checker that always objects carries no information, so lock the pass.

    Note the first candidate written here — price 25, up 30, down 22, p=45% —
    was REJECTED by the tool as fragile, and the tool was right: its edge
    breaks even at a $20.91 floor, only 4% of the share price below the
    assumed $22. Picking a genuinely sound example needs a wide bracket, a
    price near the low end, and a claim only modestly above the market's.
    """
    a = c.assess(22.0, 40.0, 18.0, 0.32)
    assert a["blocking"] is False
    assert a["findings"] == [], a["findings"]
    assert a["cushion"] > 0.20              # real room to be wrong on the floor


def test_the_fragile_warning_fires_on_a_thin_cushion():
    a = c.assess(25.0, 30.0, 22.0, 0.45)
    assert any("FRAGILE" in f for f in a["findings"])
    assert a["cushion"] < 0.05


def test_negative_edge_is_named_when_ev_is_below_the_price():
    """Claiming a probability BELOW the market's own means paying up to be
    less optimistic than the tape — the fair value sits under the price."""
    a = c.assess(25.0, 36.0, 20.5, 0.20)     # market implies 29%, claim 20%
    assert a["cushion"] is None
    assert any("NEGATIVE EDGE" in f for f in a["findings"])


def test_expected_value_matches_the_hand_calculation():
    assert c.expected_value(0.85, 36.0, 20.5) == pytest.approx(33.675)
