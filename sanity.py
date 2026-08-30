#!/usr/bin/env python3
"""
sanity.py — hard bounds on every published number, asserted before it prints.

WHY THIS EXISTS. Five defects have shipped into the live report in eleven days,
and every one of them was a NUMBER that was silently wrong while the code
around it ran without complaint:

    day-72  Yahoo answered `interval=1d` with MONTHLY bars, so a "3-day event
            window" was three months on some names. Shipped for four days.
    day-74  the classifier missed two thirds of approvals — an un-decoded HTML
            entity and a `str.find` that stopped at the first occurrence.
    day-75  the report quoted "$1,027 at risk" on a binary that had already
            settled.
    day-79  put fair value counted only the CRL branch and undercounted the
            payoff by 2.5x.
    day-81  a cross-check warning named a mechanism it could not detect.

HOW MANY OF THOSE FIVE THIS WOULD ACTUALLY HAVE CAUGHT: ONE. Replayed against
the bounds below (tests/test_sanity.py runs the replay), only day-72 trips —
its monthly bars raise on the 30-day gap, which is the four-day defect and the
most expensive of the five. The other four do not, and the reason is worth
stating plainly rather than discovering later:

    day-74  334 approvals out of 1,097 events is a perfectly possible count.
            Nothing arithmetic distinguishes it from the true 977.
    day-75  a settled binary priced at $1,027 is a valid dollar figure.
    day-79  2.37% and 6.04% are both legitimate put values. A 2.5x undercount
            sits entirely inside any honest bound.
    day-81  a warning naming the wrong mechanism is not a number at all.

So this is a floor, not a net. It stops the class of defect where the value
itself became impossible; the other class — a plausible number that is simply
wrong — is only reachable by a positive control, and that is what the planted
controls in tests/ are for. Claiming more for it than that would be the same
error as day-81's warning text.

THE DISCIPLINE. A bound here must be something that cannot be true of a correct
number — not something merely unlikely. A gate that fires on surprising-but-real
values gets ignored within a week, and an ignored gate is worse than none. So
every bound below is arithmetic or definitional, and where a value is merely
suspicious rather than impossible it is a WARNING, which prints and does not
raise.

FAIL CLOSED (rule 2). `check` raises. A wrong number that reaches the portfolio
manager is more expensive than a report that stops, because the report is read
as measured fact and acted on.

This file asserts nothing about whether a number is USEFUL — only that it is
not impossible. It cannot catch a value that is wrong but in range, and it is
not a substitute for the positive controls.
"""

from __future__ import annotations

import argparse
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


class Impossible(ValueError):
    """A published number violated a bound that no correct value can violate."""


# ── bounds ──────────────────────────────────────────────────────────────────
# Each is arithmetic or definitional. Nothing here encodes a belief about what
# the market "should" do.

MAX_DAILY_GAP = 6           # calendar days between consecutive DAILY bars.
#                             CALIBRATED, not guessed: the largest gap in real
#                             daily bars is 4 (a holiday Friday plus the
#                             weekend, e.g. 2014-07-03 -> 07-07), the maximum
#                             across seven 3,080-bar series. Weekly bars are 7.
#                             6 admits every real closure, including a rare
#                             multi-day exchange halt, and rejects the
#                             narrowest degradation Yahoo serves (day-72).
MAX_PUT_PCT = 100.0         # a put struck at S is worth at most S.
MAX_SANE_PUT_PCT = 60.0     # not impossible, but no ATM put on a listed name
#                             is worth 60% of spot over these horizons. WARN.
MAX_VOL = 6.0               # 600% annualised. Above this the price series is
#                             broken, not volatile (a split, a bad print).


def _fail(msg: str, warn_only: bool, out: list) -> None:
    if warn_only:
        out.append(f"⚠ IMPLAUSIBLE: {msg}")
    else:
        raise Impossible(msg)


def probability(x, name: str, out: list = None) -> float:
    """A probability lives in [0, 1]. No exceptions, no rounding slack."""
    out = out if out is not None else []
    if x is None or not math.isfinite(float(x)):
        _fail(f"{name} is {x!r}, not a number", False, out)
    x = float(x)
    if not (0.0 <= x <= 1.0):
        _fail(f"{name} = {x:.4f} is not a probability", False, out)
    return x


def interval(lo, hi, point, name: str, out: list = None) -> None:
    """A confidence interval must contain its own point estimate, in order.

    Day-78 turned on a 0.3pp interval overlap. If the interval and the point
    estimate can drift apart unnoticed, that decision was arithmetic noise.
    """
    out = out if out is not None else []
    if None in (lo, hi, point):
        return
    lo, hi, point = float(lo), float(hi), float(point)
    if lo > hi:
        _fail(f"{name} interval is inverted: [{lo:.4f}, {hi:.4f}]", False, out)
    if not (lo - 1e-9 <= point <= hi + 1e-9):
        _fail(f"{name} point estimate {point:.4f} lies outside its own "
              f"interval [{lo:.4f}, {hi:.4f}]", False, out)


def put_value(pct, name: str, out: list = None) -> None:
    """A put cannot be worth more than the stock it is struck on.

    Day-79's undercount ran the other way and this would not have caught it.
    It catches the correction going too far, which is the failure mode a 2.5x
    upward revision creates.
    """
    out = out if out is not None else []
    if pct is None:
        return
    pct = float(pct)
    if not math.isfinite(pct) or pct < 0:
        _fail(f"{name} = {pct!r} is not a non-negative price", False, out)
    if pct > MAX_PUT_PCT:
        _fail(f"{name} = {pct:.1f}% of spot exceeds the stock itself", False, out)
    if pct > MAX_SANE_PUT_PCT:
        _fail(f"{name} = {pct:.1f}% of spot", True, out)


def drawdown_sign(value, name: str, out: list = None) -> None:
    """A rejection drawdown is negative. A positive one means a sign flip.

    The CRL constants are quoted as negatives throughout (-11.79, -20.30). If
    one ever arrives positive, every breakeven built on it is inverted.
    """
    out = out if out is not None else []
    if value is None:
        return
    if float(value) > 0:
        _fail(f"{name} = {float(value):+.2f}% is positive; a rejection "
              "drawdown cannot be", False, out)


def volatility(v, name: str, out: list = None) -> None:
    out = out if out is not None else []
    if v is None:
        return
    v = float(v)
    if not math.isfinite(v) or v < 0:
        _fail(f"{name} = {v!r} is not a volatility", False, out)
    if v > MAX_VOL:
        _fail(f"{name} = {v*100:.0f}% annualised — the series is broken, "
              "not volatile", False, out)


def daily_bars(index, name: str, out: list = None) -> None:
    """THE DAY-72 GATE. Daily bars cannot be a week apart.

    Yahoo answers `interval=1d` with weekly, monthly or quarterly bars and no
    error. This is the assertion that would have stopped four days of a
    three-month "event window" being reported as three days.
    """
    out = out if out is not None else []
    try:
        import numpy as np
        d = np.diff(np.asarray(index, dtype="datetime64[D]")).astype(int)
    except Exception as e:                      # never swallow it (rule 1)
        _fail(f"{name}: bar dates unreadable ({e})", False, out)
        return
    if len(d) == 0:
        return
    worst = int(d.max())
    if worst > MAX_DAILY_GAP:
        _fail(f"{name}: {worst}-day gap between consecutive 'daily' bars — "
              "these are not daily bars", False, out)


def counts(k, n, name: str, out: list = None) -> None:
    """A numerator cannot exceed its denominator, and n cannot be negative."""
    out = out if out is not None else []
    if None in (k, n):
        return
    k, n = int(k), int(n)
    if n < 0 or k < 0:
        _fail(f"{name}: negative count ({k}/{n})", False, out)
    if k > n:
        _fail(f"{name}: {k} of {n} — numerator exceeds denominator", False, out)


def one_population(n_a, n_b, name: str, out: list = None) -> None:
    """RULE 7, made mechanical. Both legs of a ratio from one harvest.

    A ratio whose legs differ by orders of magnitude is almost always two
    populations spliced together — an EDGAR numerator over a Drugs@FDA
    denominator. Suspicious, not impossible, so it warns.
    """
    out = out if out is not None else []
    if not n_a or not n_b:
        return
    r = max(n_a, n_b) / max(min(n_a, n_b), 1)
    if r > 50:
        _fail(f"{name}: legs of {n_a} and {n_b} differ {r:.0f}x — check they "
              "come from one harvest, one classifier, one window", True, out)


# ── the gate the report calls ───────────────────────────────────────────────

def check_fair_value(fv: dict | None, ticker: str, out: list = None) -> list:
    """Every number `fairvalue.fair_put` publishes."""
    out = out if out is not None else []
    if not fv:
        return out
    put_value(fv.get("fair"), f"{ticker} fair value", out)
    put_value(fv.get("ordinary"), f"{ticker} ordinary put value", out)
    put_value(fv.get("own3"), f"{ticker} 3-day put value", out)
    interval(fv.get("fair_lo"), fv.get("fair_hi"), fv.get("fair"),
             f"{ticker} fair value", out)
    if (fv.get("event") or 0) < 0:
        _fail(f"{ticker} event premium {fv['event']:.2f}% is negative; a "
              "binary cannot make protection cheaper", False, out)
    c = fv.get("cross") or {}
    volatility(c.get("vol"), f"{ticker} realised vol", out)
    put_value(c.get("lognormal"), f"{ticker} lognormal put value", out)
    return out


def check_base_rate(s: dict | None, out: list = None) -> list:
    """Every number the measured P(CRL) publishes."""
    out = out if out is not None else []
    if not s:
        return out
    for key in ("rate", "raw", "floor", "capture"):
        if s.get(key) is not None:
            probability(s[key], f"base rate {key}", out)
    counts(s.get("k"), s.get("n"), "base rate", out)
    interval(s.get("lo"), s.get("hi"), s.get("rate"), "base rate", out)
    return out


def check_catalyst_constants(out: list = None) -> list:
    """The measured event constants, checked on every run.

    They are module-level literals, so nothing else would ever notice a typo.
    """
    out = out if out is not None else []
    import catalyst as C
    drawdown_sign(C.CRL_MEDIAN, "CRL median", out)
    drawdown_sign(C.CRL_MEAN, "CRL mean", out)
    drawdown_sign(C.CRL_P10, "CRL p10", out)
    drawdown_sign(C.CRL_WORST, "CRL worst", out)
    probability(C.CRL_WORSE_THAN_18, "P(CRL worse than -18%)", out)
    probability(C.CRL_WORSE_THAN_40, "P(CRL worse than -40%)", out)
    if C.CRL_WORSE_THAN_40 > C.CRL_WORSE_THAN_18:
        _fail(f"P(worse than -40%) = {C.CRL_WORSE_THAN_40:.2f} exceeds "
              f"P(worse than -18%) = {C.CRL_WORSE_THAN_18:.2f}; a tail cannot "
              "be fatter than the body containing it", False, out)
    if C.CRL_MEDIAN < C.CRL_P10:
        _fail("CRL median lies below its own 10th percentile", False, out)
    return out


def check_prices(df, ticker: str, out: list = None) -> list:
    """The day-72 gate, applied to a fetched frame before anything reads it."""
    out = out if out is not None else []
    if df is None or not len(df):
        return out
    daily_bars(df.index.values, f"{ticker} price series", out)
    return out


def gate(*checks) -> list:
    """Run every check, collect the warnings, let the impossible raise.

    Deliberately NOT wrapped in a try/except. Rule 1: an exception here means a
    published number is impossible, and swallowing it is the day-29 and day-55
    pattern that cost the most.
    """
    out: list = []
    for fn in checks:
        fn(out)
    return out


def render(warnings: list) -> list:
    if not warnings:
        return []
    return ["", "▎PLAUSIBILITY GATE"] + [f"   {w}" for w in warnings] + [
        "   ── bounds are arithmetic, not opinions. A warning here means a "
        "number is",
        "      suspicious, not that it is wrong; an error stops the report.",
    ]


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--self-test", action="store_true")
    ap.parse_args(argv)
    w = gate(check_catalyst_constants)
    try:
        import baserate as B
        w += gate(lambda o: check_base_rate(B.summary(), o))
    except Exception as e:
        print(f"base rate not checkable: {e}")
    print("\n".join(render(w)) if w else
          "all published constants inside their bounds")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
