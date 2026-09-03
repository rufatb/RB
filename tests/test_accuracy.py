"""Day-82 §3: the accuracy definitions, fixed before anything optimises them.

ACCURACY.md is the contract. These tests exist so a later change cannot quietly
redefine "accuracy" instead of improving it — which is easier to miss than
moving a pre-registered bar, and has the same effect.
"""

import ledger as L


def row(r1, side="LONG", spread=None, **kw):
    d = {"role": "pair", "side": side, "r1": f"{r1}",
         "hit": "1" if (r1 > 0) == (side == "LONG") else "0",
         "spread_bps": "" if spread is None else f"{spread}"}
    d.update(kw)
    return d


# ── §1 the hit ──────────────────────────────────────────────────────────────

def test_a_short_that_falls_is_a_hit_and_a_long_that_falls_is_not():
    """The whole definition in one test."""
    assert L.capture(row(-1.0, "SHORT")) > 0
    assert L.capture(row(-1.0, "LONG")) < 0
    assert L.capture(row(+1.0, "SHORT")) < 0
    assert L.capture(row(+1.0, "LONG")) > 0


def test_an_unscored_leg_has_no_capture_rather_than_zero():
    """Zero is a real outcome. Absent is not. Rule 2."""
    assert L.capture({"side": "LONG", "r1": ""}) is None
    assert L.capture({"side": "LONG"}) is None


def test_scratches_are_excluded_and_counted_never_silently_dropped():
    """Day-35: 11% of legs land inside the threshold and 4 of 5 on the winning
    side, inflating the headline ~3pp. Excluding them is the LESS flattering
    treatment, and the count must be visible or the exclusion is invisible."""
    rows = [row(+0.01), row(-0.01), row(+1.0), row(-1.0), row(+2.0)]
    a = L.accuracy(rows)
    assert a["n"] == 5
    assert a["scratches"] == 2
    assert a["decisive_n"] == 3
    assert a["decisive_hits"] == 2


def test_the_decisive_threshold_is_a_named_registered_constant():
    """It sets the hit rate printed beside every pick; it may not be an
    anonymous default argument that drifts."""
    import constants as K
    assert L.DECISIVE_PCT == 0.10
    assert K.REGISTRY["ledger.DECISIVE_PCT"].kind == K.DESIGN


# ── §2 net of cost ──────────────────────────────────────────────────────────

def test_all_three_figures_are_reported_together():
    """A hit rate is not a P&L claim and a gross return is not a cost claim.

    Each can move without the others, so reporting one at a time is how a
    change that raised the hit rate while paying more spread reads as a win.
    """
    a = L.accuracy([row(+1.0, spread=10), row(-1.0, spread=10)])
    assert a["rate"] is not None
    assert a["mean"] is not None
    assert a["net_mean"] is not None


def test_net_capture_subtracts_the_stored_spread_in_the_right_units():
    """spread_bps is basis points; capture is percent. 10bps = 0.10%."""
    a = L.accuracy([row(+1.0, spread=10)])
    assert abs(a["mean"] - 1.0) < 1e-9
    assert abs(a["net_mean"] - 0.90) < 1e-9


def test_a_leg_without_a_stored_spread_is_excluded_and_counted():
    """THE RULE THAT MATTERS. The spread on the day a leg was published is not
    recoverable; substituting today's would describe one session with another
    session's data — the fault that made a board re-pick its own names."""
    a = L.accuracy([row(+1.0, spread=10), row(+2.0)])
    assert a["net_n"] == 1
    assert a["net_unpriced"] == 1
    assert abs(a["net_mean"] - 0.90) < 1e-9      # the 2.0 leg is NOT in it


def test_no_spread_anywhere_reports_not_computable_not_zero_cost():
    """Defaulting a missing spread to zero would make every historical leg look
    costless, which is the most flattering possible error."""
    a = L.accuracy([row(+1.0), row(-1.0)])
    assert a["net_mean"] is None
    assert a["net_unpriced"] == 2
    line = L.accuracy_line([row(+1.0), row(-1.0)])
    assert "not computable" in line


def test_the_line_says_how_many_legs_the_net_figure_covers():
    """A net figure over 2 of 90 legs is not the book's net figure."""
    rows = [row(+1.0, spread=10)] + [row(+1.0) for _ in range(9)]
    assert "on 1 of 10" in L.accuracy_line(rows)


def test_a_malformed_spread_is_unpriced_rather_than_crashing_the_report():
    a = L.accuracy([row(+1.0, spread="junk")])
    assert a["net_unpriced"] == 1 and a["net_mean"] is None


# ── the schema carries it ───────────────────────────────────────────────────

def test_spread_survives_a_write_and_read(tmp_path):
    """Schema is not behaviour — the `shares` column was declared and never
    written once, and the next board published without it."""
    p = str(tmp_path / "l.csv")
    L.append_picks([{"ticker": "SU.TO", "side": "LONG", "p_sided": 0.55,
                     "confidence": "sparse", "p945": 93.36, "role": "pair",
                     "leg": "primary", "weight": 0.25, "shares": 135,
                     "spread_bps": 16.0}], "2026-09-03", p)
    assert L.load(p)[0]["spread_bps"] == "16.0"


def test_a_leg_with_no_measurable_spread_writes_blank(tmp_path):
    p = str(tmp_path / "l.csv")
    L.append_picks([{"ticker": "X.TO", "side": "LONG", "p_sided": 0.5,
                     "confidence": "n/a", "p945": 10.0, "role": "pair",
                     "spread_bps": None}], "2026-09-03", p)
    assert L.load(p)[0]["spread_bps"] == ""


def test_accuracy_on_an_empty_record_says_so_rather_than_dividing_by_zero():
    a = L.accuracy([])
    assert a["n"] == 0 and a["rate"] is None
    assert "no scored legs" in L.accuracy_line([])
