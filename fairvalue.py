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

HOW BIG THE EVENT PREMIUM IS. Expressed as a multiple of the name's own 3-day
put value, an FDA decision is worth **2.45x, 95% [1.95x, 3.00x]**, measured over
605 decisions across 184 names with the bootstrap resampling names rather than
events.

AND A CORRECTION TO DAY-79, which this file previously stated as measured fact.
It claimed the premium scaled with volatility — 1.54x / 2.29x / 2.91x across
terciles — and concluded "a higher-volatility name gets a proportionally BIGGER
kick from the binary". Re-measured on the same 605 events by a script that is
now committed, the terciles are 2.09x / 2.09x / 2.82x: the ladder does not
reproduce and the bottom two rungs are identical. Tested directly, high minus
low is +0.76x with a 95% interval of [-0.34, +1.84] — wider than the effect
itself, so the data cannot resolve a tercile difference below about 1.1x.

That is UNDERPOWERED, not refuted (rule 10). The volatility effect may be real.
But pricing off a three-rung ladder this sample cannot distinguish is not
defensible, so ONE multiplier is used, the name's tercile is still printed, and
the unresolved question is printed beside it rather than folded into the price.

WHAT IS MEASURED AND WHAT IS NOT, stated plainly because the distinction is the
whole value of this file. The fair values ARE measured: 605 events across 184
names, 240 resampled windows per name, 2,000 name-clustered bootstrap
replicates. (This paragraph said "7,440 random windows" until day-82, a figure
no committed script produces — the module was asserting a measurement that no
longer existed.) Whether TRADING the gap between fair value and market price
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

# RE-MEASURED day-81 by validate_eventmult.py (committed, reproducible; the
# day-79 measurement had no script, so its numbers could not be re-derived).
# 605 decisions across 184 names, bootstrap resampling NAMES not events.
#
# THE TERCILE LADDER IS GONE, and it is worth saying why rather than quietly
# changing a constant. Day-79 shipped 1.54 / 2.29 / 2.91 by volatility tercile
# and this docstring asserted that "a higher-volatility name gets a
# proportionally BIGGER kick from the binary". Re-measured on the same 605
# events, the terciles come out 2.09 / 2.09 / 2.82 — the ladder does not
# reproduce, low and mid are identical, and a DIRECT bootstrap of the
# difference gives:
#
#     high - low   +0.76x   95% [-0.34, +1.84]
#     mid  - low   -0.01x   95% [-1.19, +1.25]
#
# Neither excludes zero, and both intervals are WIDER than the effect: the
# study cannot resolve a tercile difference below about 1.1x. By rule 10 that
# is UNDERPOWERED, not refuted — a volatility effect of the size day-79 claimed
# may well be real and this data cannot see it. What is not defensible is
# pricing off a three-rung ladder the sample cannot distinguish, so one
# multiplier is used and the unresolved question is printed beside it.
#
# It also removes an arithmetic defect the plausibility gate caught on its
# first run: the point estimate took the TERCILE multiplier while the interval
# took the OVERALL one, so for any low-vol name the printed fair value fell
# outside its own printed range. Two populations in one line — rule 7.
EVENT_MULT_POINT = 2.45
EVENT_MULT_CI = (1.95, 3.00)          # 95%, names clustered
# Kept only so the unresolved tercile question can be printed, never priced on.
TERCILE_OBSERVED = {"low": 2.09, "mid": 2.09, "high": 2.82}
TERCILE_EDGES = (1.96, 2.88)
TERCILE_MDE = 1.09                    # smallest difference this data resolves
N_EVENTS, N_NAMES = 605, 184
# RETIRED day-82. This was `N_RANDOM = 7440`, printed in the report as
# "measured on ... 7,440 random windows" — and nothing could re-derive it. The
# committed script draws 240 resampled windows per name inside put_fair_value
# and 2,000 name-clustered bootstrap replicates; there is no construction in it
# that yields 7,440. It was a day-79 figure from a study whose script was never
# committed, so the sentence asserted a measurement that no longer existed.
# These two ARE what validate_eventmult.py does, and both are re-derivable.
RESAMPLES_PER_NAME = 240
BOOT_REPLICATES = 2000
SAMPLE_TRADING_DAYS = 3               # the event window this was measured on

# Back-compat for callers that indexed by bucket. Every bucket now returns the
# one measured multiple; the key is retained only to name the tercile in the
# output, and no longer changes the price.
EVENT_MULT = {b: EVENT_MULT_POINT for b in ("low", "mid", "high")}


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


def realised_vol(closes, lookback: int = 500) -> float | None:
    """Annualised volatility from the name's own daily returns."""
    s = np.asarray(closes, dtype=float)
    s = s[np.isfinite(s) & (s > 0)]
    if len(s) < 60:
        return None
    r = np.diff(s[-lookback:]) / s[-lookback:-1]
    r = r[np.isfinite(r)]
    return float(np.std(r) * np.sqrt(252)) if len(r) > 30 else None


def lognormal_put(vol_ann: float, horizon_days: int) -> float:
    """ATM put value under a lognormal with no drift, as % of spot.

    A SECOND, INDEPENDENT ESTIMATOR, and the FRAGILE one of the two — which is
    the opposite of what this docstring claimed on day-80. It said a single
    historical crash inflates the EMPIRICAL estimate. Measured on planted
    controls, one -55% day in 900 lifts realised vol from 12% to 31% and this
    estimate with it, while moving the empirical figure barely at all. Sigma is
    a second moment and one day dominates it; E[max(0,-r)] is a first moment and
    one day in 900 carries about 1/900 of the weight. So when `vol_outlier`
    fires, it is THIS leg to distrust.

    ATM, zero rate: P = S[N(s/2) - N(-s/2)] with s = vol*sqrt(T), which for the
    horizons here is within a whisker of the 0.3989*vol*sqrt(T) approximation.
    """
    from math import erf, sqrt
    t = max(horizon_days, 1) / 252.0
    s = vol_ann * sqrt(t)

    def N(x):
        return 0.5 * (1.0 + erf(x / sqrt(2.0)))
    return float((N(s / 2) - N(-s / 2)) * 100.0)


# PRE-REGISTERED day-81 (PREREGISTER_day81.md) from synthetic controls, before
# any live name was run. Not to be moved.
#
# The two estimators diverge. Alone that says nothing about WHY, which is the
# error day-80 shipped: a single tolerance that asserted a cause it could not
# detect. Each bar below now answers for one mechanism, and each has a planted
# positive control in tests/test_fairvalue.py.
DISAGREE_TOL = 0.40   # the two legs diverge — says THAT, never WHY
DRIFT_TOL = 0.010     # |mean window return| > 1.0% of spot: a trend, not a
#                       distribution.  clean control 0.05%, drift control 1.13%
TAIL_TOL = 0.25       # sigma falls >25% when winsorised: a few days carry the
#                       vol.  clean control 3%, crash control 63%


def window_drift(closes, horizon: int) -> float | None:
    """Mean return over the name's own `horizon`-day windows, as % of spot.

    THE MECHANISM DAY-80 MISSED. A name that fell over its history gives every
    window a negative mean return, which lifts E[max(0,-r)] while leaving sigma
    — and so the lognormal — untouched. On planted controls this, not tail
    weight, is what drives the two estimators apart: the drift control opens a
    60% gap with no outlier at all.

    A put priced off a name's own history is then quoting the trend it happened
    to have, which is a forecast dressed as a measurement. Report it, never net
    it out silently.
    """
    s = np.asarray(closes, dtype=float)
    s = s[np.isfinite(s) & (s > 0)]
    if len(s) < horizon + 40:
        return None
    i = np.arange(0, len(s) - horizon - 1)
    return float(((s[i + horizon] / s[i] - 1) * 100).mean())


def vol_outlier(closes, lookback: int = 500, trim: float = 0.02) -> dict:
    """Is realised vol carried by a handful of days? The REAL tail diagnostic.

    `trimmed_fv` trims the window returns of the empirical estimator, which is
    the leg that was already robust — which is exactly why it moved 1-8% on
    every live name and flagged nothing. Sigma is where a lone crash lands, so
    sigma is what has to be trimmed to find one.
    """
    s = np.asarray(closes, dtype=float)
    s = s[np.isfinite(s) & (s > 0)]
    if len(s) < 60:
        return {"vol": None, "trimmed_vol": None, "drop": None, "heavy": None}
    r = np.diff(s[-lookback:]) / s[-lookback:-1]
    r = r[np.isfinite(r)]
    if len(r) < 31:
        return {"vol": None, "trimmed_vol": None, "drop": None, "heavy": None}
    raw = float(np.std(r) * np.sqrt(252))
    lo, hi = np.quantile(r, [trim, 1 - trim])
    tr = float(np.std(np.clip(r, lo, hi)) * np.sqrt(252))
    drop = 1.0 - tr / raw if raw > 0 else 0.0
    return {"vol": raw, "trimmed_vol": tr, "drop": drop,
            "heavy": drop > TAIL_TOL}


def cross_check(closes, horizon_days: int, empirical: float) -> dict:
    """Do two independent methods agree, and if not, WHICH LEG is at fault?

    Day-80 answered only the first half and then guessed at the second, naming
    a cause — outliers in the empirical leg — that the test could not see and
    that points the wrong way. The gap is now reported with the two mechanisms
    that can produce it measured separately, so the output can say which
    estimate to distrust instead of asserting it.
    """
    vol = realised_vol(closes)
    if vol is None or not empirical:
        return {"vol": None, "lognormal": None, "gap": None, "agree": None,
                "drift": None, "tail": {}, "why": "",
                "blame": "not enough history for a second estimate"}
    ln = lognormal_put(vol, horizon_days)
    gap = abs(empirical - ln) / max(ln, 1e-9)
    agree = gap <= DISAGREE_TOL
    drift = window_drift(closes, max(horizon_days, 1))
    tail = vol_outlier(closes)
    drifty = drift is not None and abs(drift) > DRIFT_TOL * 100

    # BOTH can be true at once, and on live names they often are. Reporting
    # only the first match would narrow the finding silently — the same fault
    # as day-80, one layer in. Every cause that fires is named.
    faults = []
    if tail.get("heavy"):
        faults.append(("LOGNORMAL",
                       f"realised vol falls {tail['drop']:.0%} when the "
                       f"extreme 2% of days are winsorised "
                       f"({tail['vol']*100:.0f}% -> "
                       f"{tail['trimmed_vol']*100:.0f}%), so a handful of days "
                       "is carrying sigma and the lognormal leg with it"))
    if drifty:
        direction = "understating" if drift > 0 else "overstating"
        faults.append(("EMPIRICAL",
                       f"this name's own {horizon_days}d windows average "
                       f"{drift:+.1f}%, so the empirical figure is quoting the "
                       "trend it happened to have rather than its "
                       f"distribution, and is {direction} the fair value"))
    if not faults and not agree:
        faults.append(("UNEXPLAINED",
                       f"the two estimates differ by {gap:.0%} with neither "
                       f"drift ({drift:+.1f}%) nor tail weight "
                       f"({tail['drop']:.0%}) large enough to account for it"))
    return {"vol": vol, "lognormal": ln, "gap": gap, "agree": agree,
            "drift": drift, "drifty": drifty, "tail": tail,
            "faults": faults,
            "blame": "+".join(b for b, _ in faults),
            "why": "; and ".join(w for _, w in faults)}


def trimmed_fv(closes, horizon: int, samples: int = 240, trim: float = 0.02,
               seed: int = 0) -> float | None:
    """The empirical fair value with the extreme WINDOW returns winsorised.

    KEPT, BUT DEMOTED, and the reason is worth stating. This was built as the
    outlier test and it is not one: it trims the empirical leg, which planted
    controls show is already robust — 1% movement on a clean series and 1% on a
    series with a -55% day dropped into it. That is why it flagged nothing on
    every live name, and reading that silence as "the book is clean" was the
    day-80 error. `vol_outlier` is the tail diagnostic. This one is now a
    consistency check whose expected reading is ~0; a large value here is the
    surprise, not the reassurance.
    """
    s = np.asarray(closes, dtype=float)
    s = s[np.isfinite(s) & (s > 0)]
    if len(s) < horizon + 40:
        return None
    rng = np.random.default_rng(seed)
    i = rng.integers(0, len(s) - horizon - 1, size=samples)
    r = (s[i + horizon] / s[i] - 1) * 100
    lo, hi = np.quantile(r, [trim, 1 - trim])
    return float(np.maximum(0.0, -np.clip(r, lo, hi)).mean())


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
    # ONE multiplier, and its OWN interval. Day-79 took the point from the
    # tercile and the bracket from the overall sample, which put the printed
    # fair value outside its own printed range for every low-vol name.
    event = own3 * (EVENT_MULT_POINT - 1.0)  # the INCREMENT over an ordinary 3d
    lo = own3 * (EVENT_MULT_CI[0] - 1.0)
    hi = own3 * (EVENT_MULT_CI[1] - 1.0)
    out = {"own3": own3, "ordinary": ordinary, "bucket": b,
           "event": event, "fair": ordinary + event,
           "fair_lo": ordinary + lo, "fair_hi": ordinary + hi}
    out["cross"] = cross_check(closes, max(days_to_expiry, 1), ordinary)
    tr = trimmed_fv(closes, max(days_to_expiry, 1), seed=seed + 1)
    out["trimmed"] = tr
    out["trim_gap"] = (abs(ordinary - tr) / max(tr, 1e-9)
                       if tr is not None else None)
    return out


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


def _wrap(text: str, width: int = 76, lead: str = "        ",
          cont: str = "          ") -> list:
    import textwrap
    return textwrap.wrap(text, width=width, initial_indent=lead,
                         subsequent_indent=cont) or [lead + text]


def render(actual_pct: float | None, fv: dict | None, days: int) -> list:
    lab, ratio = verdict(actual_pct, fv)
    if lab == "unpriced":
        return ["        fair value: not computable (no usable price history)"]
    L = [f"        FAIR VALUE (measured, this name's own returns): "
         f"{fv['fair']:.1f}% of spot",
         f"          = {fv['ordinary']:.1f}% ordinary over ~{days}d "
         f"+ {fv['event']:.1f}% for the binary "
         f"(x{EVENT_MULT_POINT:.2f} on {N_EVENTS} decisions, "
         f"{N_NAMES} names)",
         f"        QUOTED {actual_pct:.1f}%  ->  {ratio:.2f}x fair  —  {lab}"]
    L.append(f"          fair-value range on the event multiple: "
             f"{fv['fair_lo']:.1f}%-{fv['fair_hi']:.1f}%")
    c = fv.get("cross") or {}
    # Fire on the MECHANISM, not on the gap. A single crash inflates sigma
    # while opening a gap of only ~22% on controls — day-80 would have printed
    # nothing at all for the one case it was built to catch.
    head = {"LOGNORMAL": "⚠ the CROSS-CHECK is unreliable here, not the fair "
                         "value",
            "EMPIRICAL": "⚠ this FAIR VALUE embeds a historical trend",
            "UNEXPLAINED": "⚠ TWO ESTIMATORS DISAGREE, cause unidentified"}
    for leg, why in c.get("faults") or []:
        L.extend(_wrap(f"{head[leg]} — {why}."))
    if c.get("faults"):
        both = len(c["faults"]) > 1
        L += _wrap(f"empirical {fv['ordinary']:.1f}% vs lognormal "
                   f"{c['lognormal']:.1f}% (vol {c['vol']*100:.0f}%, "
                   f"{c['gap']:.0%} apart) — "
                   + ("BOTH legs are compromised; treat the fair value as "
                      "indicative only." if both else
                      f"the {c['blame'].lower()} leg is the one to distrust."),
                   lead="          ", cont="          ")
    if fv.get("trim_gap") is not None and fv["trim_gap"] > 0.25:
        L.append(f"        ⚠ unexpected: winsorising the extreme window "
                 f"returns moves the empirical estimate {fv['trim_gap']:.0%} "
                 f"(to {fv['trimmed']:.1f}%), which controls say should be "
                 "~0%.")
    L += _wrap(f"this name sits in the {fv['bucket']}-vol tercile (observed "
               f"x{TERCILE_OBSERVED[fv['bucket']]:.2f} vs "
               f"x{EVENT_MULT_POINT:.2f} overall), but the sample cannot "
               f"resolve a tercile gap below x{TERCILE_MDE:.2f}, so it is NOT "
               "priced in — shown as an open question, not an adjustment.",
               lead="          ", cont="          ")
    L += _wrap(f"measured on {N_EVENTS} decisions across {N_NAMES} names and "
               f"{RESAMPLES_PER_NAME} resampled windows per name and "
               f"{BOOT_REPLICATES:,} name-clustered bootstrap replicates. "
               "The FAIR VALUE is measured; "
               "whether trading the gap pays is NOT backtested — no free "
               "historical option prices exist.",
               lead="          ", cont="          ")
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
