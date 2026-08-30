#!/usr/bin/env python3
"""
validate_priorcrl.py — TEST B: is P(CRL) conditional on the sponsor's history?

THE WEAKNESS THIS ATTACKS. Every rate this repo prints carries the word
UNCONDITIONAL beside it. That is honest, and it is also the largest thing wrong
with the number: a portfolio manager is never looking at "a decision drawn at
random from the population", they are looking at ONE sponsor with a history.

The harvest already contains what is needed to condition on the most obvious
piece of that history — whether this sponsor has been rejected before.

    P(CRL | the sponsor has a prior CRL)   vs   P(CRL | no prior CRL)

WHY THIS IS NOT A TRADING RULE, and gets a different bar. It is a descriptive
conditional rate. It does not predict anything on its own; it changes the
denominator that every breakeven in `screen.py` is compared against. So the bar
is not |t| >= 3 but simply: do the two Wilson intervals overlap? If they do,
the conditioning adds nothing and the unconditional rate stands.

THE LOOK-AHEAD, closed by construction. For each decision, only that sponsor's
STRICTLY EARLIER decisions may be consulted. A sponsor's later rejections must
not inform its earlier ones — which is trivially easy to get wrong by grouping
per CIK and counting the whole group.

THE BIAS THAT RUNS ONE WAY, and it is worth stating before the number. A
sponsor rejected once may never file again — it may not survive. So "has a
prior CRL" over-selects the companies that lived through a rejection, and the
conditional rate is therefore biased DOWN relative to the truth. If the
conditional rate comes out HIGHER anyway, that bias is working against the
finding rather than producing it.
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import baserate as B  # noqa: E402


def wilson(k: int, n: int, z: float = 1.96) -> tuple:
    if n == 0:
        return (float("nan"), float("nan"))
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (max(0.0, c - h), min(1.0, c + h))


def label_prior(rows: list) -> list:
    """Tag each decision with what was knowable about its sponsor BEFOREHAND."""
    rows = sorted(rows, key=lambda r: (r["cik"], r["date"]))
    out, seen = [], {}
    for r in rows:
        hist = seen.setdefault(r["cik"], {"crl": 0, "appr": 0})
        out.append({**r,
                    "prior_crl": hist["crl"],
                    "prior_appr": hist["appr"],
                    "prior_total": hist["crl"] + hist["appr"]})
        if r["kind"] == "CRL":
            hist["crl"] += 1
        else:
            hist["appr"] += 1
    return out


def rate(rows: list) -> dict:
    n = len(rows)
    k = sum(1 for r in rows if r["kind"] == "CRL")
    lo, hi = wilson(k, n)
    return {"n": n, "k": k, "p": k / n if n else float("nan"),
            "lo": lo, "hi": hi}


def overlap(a: dict, b: dict) -> bool:
    return not (a["hi"] < b["lo"] or b["hi"] < a["lo"])


def report(rows: list, start: str, end: str) -> str:
    rows = [r for r in rows if start <= r["date"] <= end]
    tagged = label_prior(rows)
    no_prior = [r for r in tagged if r["prior_crl"] == 0]
    prior = [r for r in tagged if r["prior_crl"] >= 1]
    a, b = rate(no_prior), rate(prior)
    L = ["=" * 74,
         "TEST B — is P(CRL) conditional on the sponsor's own prior rejections?",
         "=" * 74, "",
         f"window {start} .. {end}   (only STRICTLY EARLIER events inform each)",
         "",
         f"  {'stratum':<34}{'P(CRL)':>9}{'95% Wilson':>20}{'n':>8}",
         f"  {'no prior CRL for this sponsor':<34}{a['p']:>8.1%}"
         f"   [{a['lo']:>5.1%}, {a['hi']:>5.1%}]{a['n']:>8}",
         f"  {'HAS a prior CRL':<34}{b['p']:>8.1%}"
         f"   [{b['lo']:>5.1%}, {b['hi']:>5.1%}]{b['n']:>8}"]
    # a finer cut: does a SECOND prior rejection say more than a first?
    two = [r for r in tagged if r["prior_crl"] >= 2]
    if two:
        c = rate(two)
        L.append(f"  {'HAS two or more prior CRLs':<34}{c['p']:>8.1%}"
                 f"   [{c['lo']:>5.1%}, {c['hi']:>5.1%}]{c['n']:>8}")
    L += ["", "-" * 74, "VERDICT"]
    if b["n"] < 20:
        L.append(f"  UNDERPOWERED — only {b['n']} decisions follow a prior CRL. "
                 "The interval is")
        L.append("  too wide to separate from anything; this is not a null.")
    elif overlap(a, b):
        L.append("  REJECT — the intervals OVERLAP. A sponsor's prior rejection "
                 "does not")
        L.append("  measurably change its next rejection rate, so the "
                 "unconditional rate")
        L.append("  stands and the report keeps saying UNCONDITIONAL.")
    else:
        L.append(f"  ADOPT — {b['p']:.1%} after a prior CRL versus {a['p']:.1%} "
                 f"without, intervals")
        L.append("  disjoint. A resubmission is a different population and "
                 "screen.py should")
        L.append("  compare its breakevens against this rate, saying which one "
                 "it used.")
    L += ["",
          "  BIAS, stated before the number was computed: a sponsor rejected "
          "once may",
          "  never file again, so 'has a prior CRL' over-selects survivors and "
          "biases",
          "  this rate DOWN. A higher conditional rate survives that bias "
          "rather than",
          "  being produced by it.",
          "-" * 74]
    return "\n".join(L)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--events", default=B.EVENTS)
    ap.add_argument("--start", default="2015-01-01")
    ap.add_argument("--end", default="2026-12-31")
    a = ap.parse_args(argv)
    with open(a.events, newline="") as f:
        rows = B.dedupe(list(csv.DictReader(f)))
    print(report(rows, a.start, a.end))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
