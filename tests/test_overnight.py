"""Day-87: the overnight expression, and the guards that keep it honest.

The two ways this study could cheat, and so the two things tested hardest:

  1. COSTING ONE WINDOW AND NOT THE OTHER, which decides the question by
     construction.
  2. REPORTING A NET MEAN BESIDE A GROSS TAIL, so a variance transfer reads as
     an improvement. Day-24 measured the overnight penalty in the tail, not in
     the mean.
"""

import numpy as np
import pytest

import validate_overnight as O


def rows(n=400, over=0.05, intra=0.03, sd=1.0, seed=0, over_sd=None):
    rng = np.random.default_rng(seed)
    out = []
    for i in range(n):
        o = rng.normal(over, over_sd if over_sd else sd)
        v = rng.normal(intra, sd)
        out.append({"date": f"2026-{1 + i // 28:02d}-{1 + i % 28:02d}",
                    "t": "BASKET", "overnight": o, "intraday": v,
                    "gap": o - v})
    return out


# ── cost is applied per session, before any statistic ──────────────────────

def test_cost_is_subtracted_from_every_session_not_from_the_mean():
    """If cost were applied to the mean, the tail would still be gross and a
    variance transfer could read as an improvement."""
    r = rows(n=50)
    net = O.net_rows(r, "overnight", 10.0)
    for a, b in zip(r, net):
        assert abs(b["overnight_net"] - (a["overnight"] - 0.10)) < 1e-12


def test_the_net_tail_moves_with_the_cost():
    r = rows(n=200)
    t_gross = O.tails(r, "overnight")
    t_net = O.tails(O.net_rows(r, "overnight", 20.0), "overnight_net")
    assert t_net["worst"] < t_gross["worst"]
    assert t_net["win"] < t_gross["win"]


def test_both_windows_are_costed_in_the_report():
    """Costing the overnight leg against a gross intraday leg would decide the
    question by construction."""
    out = O.report(rows(n=300))
    for bps in O.COST_GRID:
        block = out.split(f"NET of {bps:.0f}bps")[1]
        assert "overnight" in block and "intraday" in block


def test_the_deciding_cost_is_marked_in_the_output():
    assert "<- DECIDES" in O.report(rows(n=300))
    assert O.DECIDING_COST in O.COST_GRID


# ── the verdict ────────────────────────────────────────────────────────────

def test_a_negative_net_result_is_rejected_and_says_why():
    """The gross gap is 2.3bps; a 10bps round trip is four times that."""
    v = O.verdict(rows(n=400, over=0.02, intra=0.01), bps=10.0)
    assert "REJECTED" in v and "NEGATIVE" in v


def test_a_large_real_edge_survives_cost():
    """Rule 4: the harness must be able to SEE a tradeable edge."""
    v = O.verdict(rows(n=800, over=0.60, intra=0.01, sd=0.5, seed=3), bps=10.0)
    assert "CLEARS the bar" in v, v


def test_an_edge_that_worsens_the_tail_is_named_a_variance_transfer():
    """Day-24: one night at 2x volatility with a 2.3x worse tail. An edge in
    the mean bought with a worse 5th percentile is not an improvement."""
    r = rows(n=800, over=0.60, intra=0.01, sd=0.5, over_sd=3.0, seed=4)
    v = O.verdict(r, bps=10.0)
    assert "variance transfer" in v, v


def test_a_sign_flip_across_blocks_fails_even_with_a_big_t():
    r = rows(n=400, over=0.8, intra=0.0, sd=0.3, seed=5)
    for i, x in enumerate(r):                    # flip one block negative
        if 100 <= i < 200:
            x["overnight"] = -x["overnight"]
    v = O.verdict(r, bps=10.0)
    assert "block consistency" in v or "REJECTED" in v, v


# ── the tail report ────────────────────────────────────────────────────────

def test_the_tail_report_prints_both_windows_and_the_ratio():
    out = O.tail_report(rows(n=300, over_sd=2.0))
    assert "std dev" in out and "5th pct" in out and "worst day" in out
    assert "VARIANCE TRANSFER" in out


def test_a_more_volatile_overnight_window_is_called_out():
    out = O.tail_report(rows(n=400, over_sd=3.0, seed=6))
    assert "MORE" in out


# ── no overlapping windows here, unlike the weekly arms ────────────────────

def test_the_block_size_is_one_and_the_reason_is_stated():
    """Each session's overnight leg is disjoint from the next, so the day-85
    block bootstrap does not apply — and that must be asserted, not assumed."""
    src = open(O.__file__).read()
    assert "block=1" in src
    assert "do not " in " ".join(src.split())
    flat = " ".join(src.split())
    assert "overlap" in flat


def test_the_arithmetic_that_makes_this_short_is_in_the_docstring():
    flat = " ".join(open(O.__file__).read().split())
    assert "2.3 basis points" in flat or "2.3bps" in flat
