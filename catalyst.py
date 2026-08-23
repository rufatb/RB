#!/usr/bin/env python3
"""
catalyst.py — arithmetic guardrails for binary-event (PDUFA/AdCom) theses.

WHAT THIS IS FOR. A catalyst matrix states an upside, a downside, and a
probability, and concludes with an expected value. The price it is quoting
ALREADY contains the market's own probability, and the two are almost never
compared. This computes the comparison, and refuses to let a thesis pass
without it.

Worked example (day-54, the thesis that prompted this file):

    upside $36.00 | downside $20.50 | price $25.00 | claimed p = 85%
    -> market-implied p = (25.00 - 20.50) / (36.00 - 20.50) = 29.0%

The claim is 85%, the tape says 29%, and that 56-point gap IS the entire trade.
Worse, the three numbers cannot coexist: for p=85% and a $36 upside to produce a
$25 price, the downside would have to be -$37.33/share. At least one input is
wrong and the arithmetic says which side of the trade is carrying the assumption.

WHAT IT DELIBERATELY DOES NOT DO. It cannot tell you whether 85% is right. That
is a research question about the drug, and it is the only question that matters
— so the tool's job is to make the size of the claim explicit rather than to
launder it into an "expected value" that reads like a measurement.

THE THREE FAILURE MODES IT CATCHES
  1. INCONSISTENT   the stated triple implies a negative or absurd downside,
                    i.e. the market cannot be holding those beliefs at that
                    price. Fail-closed, like coverage_ok in the 9:45 engine.
  2. UNDEFENDED     the claimed probability exceeds the market-implied one by
                    more than a threshold with no drug-specific evidence
                    supplied. Reported as the size of the bet on being right.
  3. FRAGILE        the edge survives only under an optimistic downside. Small
                    and mid-cap biotech routinely trades BELOW cash after a CRL,
                    so a "cash floor" downside is an assumption, not a bound.
                    Measured as the CUSHION: `implied_downside` is exactly the
                    floor at which the claimed probability breaks even, so the
                    gap between it and the assumed floor is the room the thesis
                    has to be wrong. A first version instead fired whenever a
                    -64% stress demanded a high breakeven — true of nearly every
                    binary trade, so the warning was noise. A checker that
                    always objects carries no information.

BASE RATE. FDA's own first-cycle review data puts recent first-cycle complete
response rates at roughly 30%, i.e. a first-cycle approval base rate near 70% —
a PDUFA date IS a first-cycle decision. (The ~75-80% figure quoted in most
theses is EVENTUAL approval across multiple cycles, which is a different and
much friendlier number, and using it for a single PDUFA date overstates the odds.)
`BASE_RATE_FIRST_CYCLE` is that anchor; anything above it needs stated evidence.

Read-only and order-free, exactly like the rest of this repo: it prints an
assessment and never sizes or places anything.
"""

from __future__ import annotations

import argparse

BASE_RATE_FIRST_CYCLE = 0.70      # see BASE RATE note above

# DAY-72 SUPERSEDES DAY-68, and the reason is a data bug that nothing caught
# for four days. `fetch_prices` asked Yahoo for interval="1d" over range="max".
# Yahoo does not refuse that; it silently returns WEEKLY, MONTHLY or even
# QUARTERLY bars depending on how long the ticker has existed -- SRPT came back
# at a 31-day median gap, HRTX at 92. Every window in validate_catalyst.py
# counts BARS, so the "close t-2 -> close t+1" event window was three MONTHS on
# those names. The numbers below were wrong and were quoted in the morning
# report for four days.
#
# What caught it was a positive control: validate_runup.py could not detect a
# planted +1% drift, which is only possible if the sample is far noisier than a
# daily window should be. The aggregate looked plausible throughout.
#
# Re-measured on verified daily bars (median gap <= 4 days, asserted rather
# than requested), same events, same classifier:
#
#     CRL        n=57    mean -18.48%   median -8.97%   p10 -60.38%   worst -74.95%
#                42% worse than -18%, 19% worse than -40%
#                vs random windows: -18.31pp, t=-5.64   (was -15.00pp, t=-3.41)
#     APPROVAL   n=173   mean  +5.21%   median +0.21%
#                vs random windows:  +5.38pp, t=+2.42   (was +0.98, and NEGATIVE)
#
# TWO THINGS CHANGED MATERIALLY. The rejection finding got STRONGER -- it was
# never in doubt and now separates from random at t=-5.64. But the approval
# claim this repo has been repeating, that an approval is "indistinguishable
# from a random window" and therefore already priced, does NOT survive: on
# daily bars the approval reaction is positive, +5.4pp over random at t=+2.42.
#
# That still does not clear the pre-registered |t| >= 3 bar, so it is NOT
# adopted and no long is recommended on it. The honest statement is "positive
# and below the bar", which is a different sentence from "indistinguishable
# from random", and the report must stop saying the second one.
#
# MEAN AND MEDIAN ARE BOTH KEPT because they answer different questions. An
# option's payoff is an expectation, so a breakeven belongs against the MEAN
# (-18.48%); the median (-8.97%) describes the case a holder should picture.
# The gap between them is the fat left tail, and quoting only one hides it.
CRL_MEDIAN, CRL_MEAN = -8.97, -18.48
CRL_P10, CRL_WORST = -60.38, -74.95
CRL_WORSE_THAN_18, CRL_WORSE_THAN_40 = 0.42, 0.19
CRL_N, CRL_VS_RANDOM_PP, CRL_T = 57, -18.31, -5.64
APPROVAL_MEDIAN, APPROVAL_MEAN = 0.21, 5.21
APPROVAL_VS_RANDOM_PP, APPROVAL_T, APPROVAL_N = 5.38, 2.42, 173
APPROVAL_RANDOM = -0.17
# The bar that was pre-registered and is not being moved now that a number
# came close to it.
ADOPT_T = 3.0
GAP_WARN = 0.15                   # claimed - implied, above which the bet is "on the gap"


def implied_probability(price: float, upside: float, downside: float) -> float:
    """The probability the market is holding, backed out of the current price.

    A binary event with two outcomes prices as p*up + (1-p)*dn, so
        p = (price - dn) / (up - dn)
    This is the number a thesis is implicitly disagreeing with. Returns a value
    outside [0,1] when the price sits outside the stated bracket — that is not
    an error to clamp away, it means the bracket is wrong and the caller must
    see it."""
    if upside <= downside:
        raise ValueError("upside must exceed downside")
    return (price - downside) / (upside - downside)


def expected_value(p: float, upside: float, downside: float) -> float:
    """Probability-weighted fair value."""
    return p * upside + (1 - p) * downside


def implied_downside(price: float, upside: float, p: float) -> float:
    """The downside that WOULD make a claimed probability consistent with the
    price. When this comes back negative the thesis is arithmetically
    impossible, which is the cleanest possible refutation."""
    if p >= 1.0:
        raise ValueError("probability must be below 1")
    return (price - upside * p) / (1 - p)


def breakeven_table(price: float, upside: float, downsides: list) -> list:
    """Breakeven probability under progressively worse CRL outcomes.

    The point of the table is that a downside is an ASSUMPTION. A thesis that
    needs p>29% at a -18% floor may need p>54% at a -52% floor, and biotech
    CRL drawdowns reach well past -50%."""
    out = []
    for dn in downsides:
        if dn >= upside:
            continue
        out.append((dn, dn / price - 1, implied_probability(price, upside, dn)))
    return out


def assess(price: float, upside: float, downside: float, p_claim: float,
           base_rate: float = BASE_RATE_FIRST_CYCLE,
           stress: list | None = None) -> dict:
    """Full arithmetic verdict. Pure — no I/O, no network, fully testable."""
    findings, blocking = [], False
    p_mkt = implied_probability(price, upside, downside)
    ev = expected_value(p_claim, upside, downside)
    need_dn = implied_downside(price, upside, p_claim)

    if not 0.0 <= p_mkt <= 1.0:
        blocking = True
        where = "above the upside" if price > upside else "below the downside"
        findings.append(
            f"INCONSISTENT: the price ${price:,.2f} sits {where} of the stated "
            f"bracket (${downside:,.2f}-${upside:,.2f}). The bracket is wrong, "
            "not the market.")
    if need_dn < 0:
        blocking = True
        findings.append(
            f"INCONSISTENT: for p={p_claim:.0%} AND a ${upside:,.2f} upside to "
            f"produce a ${price:,.2f} price, the downside would have to be "
            f"${need_dn:,.2f}/share. Impossible — at least one input is wrong.")

    gap = p_claim - p_mkt
    if gap > GAP_WARN:
        findings.append(
            f"UNDEFENDED: you claim {p_claim:.0%}, the tape implies {p_mkt:.0%}. "
            f"The whole trade is a {gap*100:.0f}-point bet that the market has "
            "mispriced a scheduled, publicly-analysed event. That needs "
            "drug-specific evidence, not a base rate.")
    if p_claim > base_rate:
        findings.append(
            f"ABOVE BASE RATE: {p_claim:.0%} exceeds the ~{base_rate:.0%} "
            "first-cycle approval base rate. A PDUFA date is a FIRST-CYCLE "
            "decision; the friendlier ~75-80% figure is eventual approval "
            "across multiple cycles and does not apply here.")

    stress = stress if stress is not None else [downside, price * 0.60,
                                               price * 0.48, price * 0.36]
    table = breakeven_table(price, upside, sorted(set(stress), reverse=True))

    # CUSHION: how much lower the true floor could be before the claimed
    # probability stops breaking even. `need_dn` IS that break-even floor, so
    # the distance to the assumed one, in units of the share price, is the room
    # the thesis has to be wrong about the downside.
    cushion = (downside - need_dn) / price if need_dn < downside else None
    if cushion is None:
        findings.append(
            f"NEGATIVE EDGE: at your own {p_claim:.0%} the fair value is "
            f"${ev:,.2f}, at or below the ${price:,.2f} price. The thesis does "
            "not clear its own bar before costs.")
    elif cushion < 0.15:
        findings.append(
            f"FRAGILE: the edge breaks even at a ${need_dn:,.2f} floor, only "
            f"{cushion*100:.0f}% of the share price below your assumed "
            f"${downside:,.2f}. Measured CRL drawdowns (day-68, n=64): median "
            f"{CRL_MEDIAN:.1f}%, {CRL_WORSE_THAN_40:.0%} worse than -40%, worst "
            f"{CRL_WORST:.0f}%.")

    return {"p_market": p_mkt, "p_claim": p_claim, "gap": gap,
            "ev": ev, "ev_return": ev / price - 1,
            "needed_downside": need_dn, "cushion": cushion, "table": table,
            "findings": findings, "blocking": blocking}


def render(a: dict, price: float, upside: float, downside: float,
           name: str = "") -> str:
    L = []
    head = f"CATALYST CHECK{' — ' + name if name else ''}"
    L.append("=" * 68)
    L.append(head)
    L.append("=" * 68)
    L.append(f"  price ${price:,.2f}   upside ${upside:,.2f}   "
             f"downside ${downside:,.2f}")
    L.append(f"  claimed P(approval)   : {a['p_claim']:.1%}")
    L.append(f"  MARKET-IMPLIED P      : {a['p_market']:.1%}   "
             f"<- backed out of the price you are paying")
    L.append(f"  gap you are betting on: {a['gap']*100:+.0f} points")
    L.append(f"  stated expected value : ${a['ev']:,.2f} ({a['ev_return']:+.1%})")
    L.append("")
    L.append("  BREAKEVEN UNDER WORSE DOWNSIDES (the floor is an assumption)")
    L.append(f"    {'CRL price':>12}{'drop':>10}{'breakeven p':>14}")
    for dn, drop, be in a["table"]:
        mark = "  <- your assumption" if abs(dn - downside) < 1e-9 else ""
        L.append(f"    {dn:>12,.2f}{drop:>10.0%}{be:>14.1%}{mark}")
    if a.get("cushion") is not None:
        L.append(f"  edge survives a floor down to ${a['needed_downside']:,.2f} "
                 f"(cushion {a['cushion']*100:.0f}% of price)")
    L.append("")
    if a["findings"]:
        for f in a["findings"]:
            L.append(f"  ⚠ {f}")
    else:
        L.append("  ✓ no arithmetic objection — the thesis is internally "
                 "consistent and\n    is not betting heavily against the "
                 "market's own probability.")
    L.append("")
    if a["blocking"]:
        L.append("  ⛔ BLOCKING: the numbers are impossible as stated. Fix the "
                 "inputs before\n     any judgement about the drug is worth "
                 "making.")
    L.append("  This tool checks ARITHMETIC ONLY. It cannot tell you whether "
             "your\n  probability is right — that is the whole trade, and it "
             "is a research\n  question about the drug, not a calculation.")
    return "\n".join(L)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Arithmetic guardrails for a "
                                             "binary-catalyst thesis.")
    ap.add_argument("--price", type=float, required=True)
    ap.add_argument("--upside", type=float, required=True)
    ap.add_argument("--downside", type=float, required=True)
    ap.add_argument("--prob", type=float, required=True,
                    help="claimed probability of the favourable outcome (0-1)")
    ap.add_argument("--name", default="")
    ap.add_argument("--base-rate", type=float, default=BASE_RATE_FIRST_CYCLE)
    a = ap.parse_args(argv)
    if not 0.0 < a.prob < 1.0:
        ap.error("--prob must be strictly between 0 and 1")
    res = assess(a.price, a.upside, a.downside, a.prob, a.base_rate)
    print(render(res, a.price, a.upside, a.downside, a.name))
    return 2 if res["blocking"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
