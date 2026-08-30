#!/usr/bin/env python3
"""
fairvalue.py — what protection SHOULD cost, measured, per name.

THE ERROR THIS CORRECTS, and it has been shipping in the morning report for two
weeks. `screen.py` prices a put by asking:

    breakeven P(CRL) = put cost / |mean CRL drawdown|

which reads as "how likely must a rejection be for this put to pay for itself".
It is a fair question and it is NOT fair value, because **a put does not only
pay on rejections.** Measured over 605 FDA decisions, the event-window return
is negative **50.7% of the time** — the median approval is +0.10%, so roughly
half of all approvals also fall, and every one of those pays the put too.

Counting only the CRL branch credits a put with a fraction of its payoff:

    CRL-only approximation   P(CRL) x |mean CRL| = 0.117 x 20.30% = 2.37%
    ACTUAL measured payoff   E[max(0, -return)]                   = 6.04%

The report has therefore been calling protection "dear" and printing STAND
ASIDE on a calculation that undercounts what the protection is worth by about
two and a half times.

WHY THIS CANNOT BE A SINGLE CROSS-SECTIONAL NUMBER. The 6.04% above is an
average over a sample whose volatility ranges from 23% to 153% annualised. The
names that actually appear in the screen are the liquid end of it — IONS at 48%
vol has an own-volatility put fair value of 3.03%, not 7.95%. Comparing a
specific name's option to a cross-sectional average dominated by micro-caps is
the same category of error as rule 7: a ratio needs both legs from one
population. So fair value is computed FROM THE NAME'S OWN REALISED RETURNS.

AND THE EVENT PREMIUM IS NOT SCALE-FREE, which was tested rather than assumed.
Expressed as a multiple of the name's own 3-day put value, an FDA decision is
worth:

    low-vol tercile    1.54x        (own 3d FV 1.36% -> event payoff 2.10%)
    mid-vol tercile    2.29x        (own 3d FV 2.32% -> event payoff 5.31%)
    high-vol tercile   2.91x        (own 3d FV 3.70% -> event payoff 10.78%)
    overall            2.46x   95% CI [2.07x, 2.86x]

A higher-volatility name gets a proportionally BIGGER kick from the binary, not
merely a bigger absolute one. A single multiplier would overprice the event for
quiet names and underprice it for violent ones, so the tercile the name falls
in is used and named in the output.

WHAT IS MEASURED AND WHAT IS NOT, stated plainly because the distinction is the
whole value of this file. The fair values ARE measured: 605 events and 7,440
random windows. Whether TRADING the gap between fair value and market price
makes money is NOT backtested and cannot be with free data — there is no
historical option price series available without paying for one. This prints a
comparison, not a track record.
"""

from __future__ import annotations

import argparse
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# MEASURED day-79. Event put payoff as a multiple of the name's own 3-day put
# fair value, by volatility tercile of the same 605-event sample.
EVENT_MULT = {"low": 1.54, "mid": 2.29, "high": 2.91}
EVENT_MULT_CI = (2.07, 2.86)          # overall, 95%
# Tercile boundaries on the name's OWN 3-day put fair value (% of spot).
TERCILE_EDGES = (1.80, 2.95)
N_EVENTS, N_RANDOM = 605, 7440
SAMPLE_TRADING_DAYS = 3               # the event window this was measured on


def put_fair_value(closes, horizon: int, samples: int = 240,
                   seed: int = 0) -> float | None:
    """E[max(0, -return)] over random `horizon`-day windows of THIS name.

    The name's own realised distribution, not a peer group and not a model.
    An option is worth what the underlying actually does.
    """
    s = np.asarray(closes, dtype=float)
    s = s[np.isfinite(s) & (s > 0)]
    if len(s) < horizon + 40:
        return None
    rng = np.random.default_rng(seed)
    i = rng.integers(0, len(s) - horizon - 1, size=samples)
    r = (s[i + horizon] / s[i] - 1) * 100
    return float(np.maximum(0.0, -r).mean())


def vol_bucket(own3: float) -> str:
    lo, hi = TERCILE_EDGES
    return "low" if own3 < lo else ("mid" if own3 < hi else "high")


def fair_put(closes, days_to_expiry: int, seed: int = 0) -> dict | None:
    """What a put covering an FDA decision should cost, for THIS name.

    Two components, kept separate because they answer different questions:
      ORDINARY   what the name does over the option's life with no event
      EVENT      the incremental value of the binary, as a multiple of the
                 name's own 3-day put value, using its volatility tercile
    """
    own3 = put_fair_value(closes, SAMPLE_TRADING_DAYS, seed=seed)
    ordinary = put_fair_value(closes, max(days_to_expiry, 1), seed=seed + 1)
    if own3 is None or ordinary is None:
        return None
    b = vol_bucket(own3)
    event = own3 * (EVENT_MULT[b] - 1.0)     # the INCREMENT over an ordinary 3d
    lo = own3 * (EVENT_MULT_CI[0] - 1.0)
    hi = own3 * (EVENT_MULT_CI[1] - 1.0)
    return {"own3": own3, "ordinary": ordinary, "bucket": b,
            "event": event, "fair": ordinary + event,
            "fair_lo": ordinary + lo, "fair_hi": ordinary + hi}


def verdict(actual_pct: float | None, fv: dict | None) -> tuple:
    """(label, ratio). Fails to 'unpriced' rather than guessing."""
    if actual_pct is None or not fv or not fv["fair"]:
        return "unpriced", None
    ratio = actual_pct / fv["fair"]
    if ratio < 0.80:
        return "CHEAP vs measured fair value", ratio
    if ratio > 1.25:
        return "RICH vs measured fair value", ratio
    return "roughly FAIR", ratio


def render(actual_pct: float | None, fv: dict | None, days: int) -> list:
    lab, ratio = verdict(actual_pct, fv)
    if lab == "unpriced":
        return ["        fair value: not computable (no usable price history)"]
    L = [f"        FAIR VALUE (measured, this name's own returns): "
         f"{fv['fair']:.1f}% of spot",
         f"          = {fv['ordinary']:.1f}% ordinary over ~{days}d "
         f"+ {fv['event']:.1f}% for the binary "
         f"({fv['bucket']}-vol tercile, x{EVENT_MULT[fv['bucket']]:.2f})",
         f"        QUOTED {actual_pct:.1f}%  ->  {ratio:.2f}x fair  —  {lab}"]
    L.append(f"          fair-value range on the event multiple: "
             f"{fv['fair_lo']:.1f}%-{fv['fair_hi']:.1f}%")
    L.append(f"          measured on {N_EVENTS} decisions and "
             f"{N_RANDOM:,} random windows. The FAIR VALUE is measured;")
    L.append("          whether trading the gap pays is NOT backtested — no "
             "free historical option prices exist.")
    return L


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("ticker")
    ap.add_argument("--days", type=int, default=21)
    ap.add_argument("--put", type=float, default=None,
                    help="quoted ATM put as %% of spot")
    a = ap.parse_args(argv)
    from validate_catalyst import fetch_prices
    px = fetch_prices([a.ticker], workers=1)
    df = px.get(a.ticker)
    if df is None:
        print("no usable price history")
        return 1
    fv = fair_put(df["Close"].dropna().to_numpy(), a.days)
    print("\n".join(render(a.put, fv, a.days)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
