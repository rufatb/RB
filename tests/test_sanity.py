"""Day-81: the plausibility gate, with the five historical defects replayed.

A gate that cannot detect a planted defect cannot certify anything (rule 4).
So the five defects that actually shipped are replayed here, and the test
records the honest score: ONE of five trips. The four that do not are asserted
to NOT trip, so that the file can never quietly be read as a net.
"""

import numpy as np
import pytest

import sanity as S


def caught(fn):
    """'RAISE', 'WARN' or 'no' — what the gate does with a value."""
    out = []
    try:
        fn(out)
    except S.Impossible:
        return "RAISE"
    return "WARN" if out else "no"


# ── the replay: what this gate would have stopped ───────────────────────────

def test_day72_monthly_bars_sold_as_daily_are_stopped():
    """THE ONE IT CATCHES, and the one that cost four days of live reports.

    Yahoo answers interval=1d with monthly bars and no error.
    """
    monthly = np.array(["2024-01-31", "2024-02-29", "2024-03-31"],
                       dtype="datetime64[D]")
    assert caught(lambda o: S.daily_bars(monthly, "SRPT", o)) == "RAISE"


def test_genuine_daily_bars_pass_including_the_worst_real_holiday():
    """A gate that fires on real data gets ignored within a week.

    The largest gap in real daily bars is 4 days — a holiday Friday plus the
    weekend, e.g. 2014-07-03 -> 2014-07-07, which is the maximum observed
    across seven 3,080-bar series. Weekly bars are 7. The bound sits at 6.
    """
    real = np.array(["2014-07-01", "2014-07-02", "2014-07-03", "2014-07-07",
                     "2014-07-08"], dtype="datetime64[D]")
    assert caught(lambda o: S.daily_bars(real, "AAPL", o)) == "no"


def test_weekly_bars_are_rejected_too():
    """The narrowest degradation, and the one easiest to miss in aggregate."""
    weekly = np.array(["2024-01-05", "2024-01-12", "2024-01-19"],
                      dtype="datetime64[D]")
    assert caught(lambda o: S.daily_bars(weekly, "X", o)) == "RAISE"


@pytest.mark.parametrize("label,fn", [
    # day-74: the classifier found 334 approvals where the truth was 977.
    ("day-74 classifier undercount", lambda o: S.counts(334, 1097, "x", o)),
    # day-79: put fair value counted only the CRL branch — 2.37% vs 6.04%.
    ("day-79 put undercount", lambda o: S.put_value(2.37, "x", o)),
    ("day-79 the corrected value", lambda o: S.put_value(6.04, "x", o)),
])
def test_the_four_defects_this_gate_does_not_catch(label, fn):
    """Recorded as a limit, not hidden. These are all possible numbers.

    day-75 (pricing a settled binary) and day-81 (a warning naming the wrong
    mechanism) are not numeric bounds at all and have no representation here.
    """
    assert caught(fn) == "no", f"{label} unexpectedly tripped — update the docs"


# ── the bounds themselves ───────────────────────────────────────────────────

def test_a_probability_outside_zero_one_raises():
    assert caught(lambda o: S.probability(1.4, "p", o)) == "RAISE"
    assert caught(lambda o: S.probability(-0.01, "p", o)) == "RAISE"
    assert caught(lambda o: S.probability(0.117, "p", o)) == "no"


def test_nan_is_not_a_probability():
    assert caught(lambda o: S.probability(float("nan"), "p", o)) == "RAISE"


def test_a_point_estimate_outside_its_own_interval_raises():
    """Day-78 turned on a 0.3pp overlap; the arithmetic has to hold."""
    assert caught(lambda o: S.interval(0.08, 0.16, 0.117, "r", o)) == "no"
    assert caught(lambda o: S.interval(0.08, 0.16, 0.21, "r", o)) == "RAISE"
    assert caught(lambda o: S.interval(0.16, 0.08, 0.12, "r", o)) == "RAISE"


def test_a_put_cannot_be_worth_more_than_the_stock():
    assert caught(lambda o: S.put_value(140.0, "p", o)) == "RAISE"


def test_an_enormous_but_possible_put_warns_rather_than_stopping():
    """Suspicious is not impossible. Warnings print; errors stop the report."""
    assert caught(lambda o: S.put_value(75.0, "p", o)) == "WARN"


def test_a_positive_rejection_drawdown_raises():
    """Every breakeven in the report is built on this sign."""
    assert caught(lambda o: S.drawdown_sign(+11.79, "CRL median", o)) == "RAISE"
    assert caught(lambda o: S.drawdown_sign(-11.79, "CRL median", o)) == "no"


def test_a_numerator_larger_than_its_denominator_raises():
    assert caught(lambda o: S.counts(80, 71, "n", o)) == "RAISE"


def test_a_broken_price_series_is_not_merely_volatile():
    assert caught(lambda o: S.volatility(9.0, "vol", o)) == "RAISE"
    assert caught(lambda o: S.volatility(1.52, "PRAX vol", o)) == "no"


def test_rule_seven_made_mechanical():
    """Legs differing by orders of magnitude are two populations spliced."""
    assert caught(lambda o: S.one_population(71, 9000, "ratio", o)) == "WARN"
    assert caught(lambda o: S.one_population(71, 534, "ratio", o)) == "no"


# ── the live constants ──────────────────────────────────────────────────────

def test_the_shipped_catalyst_constants_are_inside_their_bounds():
    assert S.check_catalyst_constants([]) == []


def test_a_tail_cannot_be_fatter_than_the_body_containing_it():
    import catalyst as C
    assert C.CRL_WORSE_THAN_40 <= C.CRL_WORSE_THAN_18


def test_fair_value_output_passes_its_own_gate():
    import fairvalue as F
    rng = np.random.default_rng(3)
    s = 100 * np.cumprod(1 + rng.normal(0, 0.02, 900))
    assert S.check_fair_value(F.fair_put(s, 21), "TEST", []) == []


def test_a_negative_event_premium_raises():
    """A binary cannot make protection cheaper than no binary."""
    bad = {"fair": 5.0, "ordinary": 6.0, "own3": 2.0, "event": -1.0,
           "fair_lo": 4.0, "fair_hi": 6.0, "cross": {}}
    assert caught(lambda o: S.check_fair_value(bad, "X", o)) == "RAISE"


def test_the_gate_does_not_swallow_its_own_exceptions():
    """Rule 1. An Impossible must reach the caller, not become a warning."""
    with pytest.raises(S.Impossible):
        S.gate(lambda o: S.probability(2.0, "p", o))
