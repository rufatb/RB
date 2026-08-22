#!/usr/bin/env python3
"""
validate_adcom.py — does an advisory-committee vote predict the FDA's decision?

THE QUESTION. An AdCom is a public expert panel voting on the evidence weeks
before the agency rules, and the FDA follows its panels most of the time. If
that frequency is stable and measurable, a vote becomes a genuine probability
input to set against the market's implied one — which is the only quantity that
matters for a binary trade (day-68: the rejection is violent and unpriced, the
approval is largely priced, so the whole edge is being right when the market's
number is wrong).

WHAT MAKES THIS TESTABLE NOW. Day-66's classifier verified which 8-Ks ANNOUNCE
a decision rather than mention one, and day-68's placebo gate confirmed the CRL
labels separate from random windows (t=-3.41). So there is, for the first time,
a trustworthy set of OUTCOMES to join votes against.

THE JOIN. For each verified vote, look for a verified decision by the same CIK
within `max_gap` days after it. A PDUFA typically follows an AdCom by one to
three months, so the window is generous; votes with no subsequent decision in
the data are reported separately rather than dropped silently, because a
missing outcome is usually a decision this repo failed to capture, not one that
never happened.

POWER IS REPORTED BEFORE THE RESULT, and deliberately so. The interesting
comparison is P(approval | favourable) against P(approval | unfavourable), and
distinguishing, say, 85% from 60% needs far more pairs than 8-K text is likely
to yield: "Advisory Committee voted" returns 48 hits across twelve years. If
the sample cannot separate those two hypotheses, the honest output is the
confidence interval and a refusal — not a point estimate that reads like
knowledge. A number with no power is worse than no number, because it gets
quoted.
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import os
import re
import sys
import time
import urllib.parse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import adcom  # noqa: E402
from pdufa import BIO_SIC, TICKER_RE, _get, strip_html  # noqa: E402
from validate_exit import SCRATCH  # noqa: E402

FTS = "https://efts.sec.gov/LATEST/search-index"
PHRASES = ['"Advisory Committee voted"', '"Advisory Committee recommended"',
           '"Advisory Committee meeting"', '"advisory committee"']


def wilson(k: int, n: int, z: float = 1.96) -> tuple:
    if n == 0:
        return (0.0, 1.0)
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * ((p * (1 - p) / n + z * z / (4 * n * n)) ** 0.5) / d
    return (max(0.0, c - h), min(1.0, c + h))


def harvest_votes(start: int, end: int, cache: str | None = None) -> list:
    """Verified AdCom votes with direction and tally, 8-K sourced."""
    if cache and os.path.exists(cache):
        return json.load(open(cache))
    seen, out = set(), []
    for y in range(start, end + 1):
        hits = []
        for p in PHRASES:
            try:
                hits += json.loads(_get(
                    f"{FTS}?q={urllib.parse.quote(p)}&forms=8-K"
                    f"&startdt={y}-01-01&enddt={y}-12-31")
                ).get("hits", {}).get("hits", [])
            except Exception:
                continue
        n_y = 0
        for h in hits:
            s = h.get("_source", {})
            if (s.get("sics") or [""])[0] not in BIO_SIC:
                continue
            cik, acc = (s.get("ciks") or [""])[0].lstrip("0"), s.get("adsh", "")
            if not cik or (cik, acc) in seen:
                continue
            seen.add((cik, acc))
            try:
                text = strip_html(_get(f"https://www.sec.gov/Archives/edgar/"
                                       f"data/{cik}/{acc}.txt"))
            except Exception:
                continue
            time.sleep(0.1)
            if "advisory committee voted" not in text.lower():
                continue
            nm = (s.get("display_names") or [""])[0]
            tm = TICKER_RE.search(re.sub(r"\s*\(CIK.*", "", nm).strip())
            out.append({"cik": cik, "ticker": tm.group(1) if tm else "",
                        "date": s.get("file_date", ""),
                        "direction": adcom.vote_direction(text),
                        "tally": adcom.vote_tally(text)})
            n_y += 1
        print(f"  votes {y}: {len(hits):>4} hits -> {n_y:>3} verified", flush=True)
    out.sort(key=lambda r: r["date"])
    if cache:
        json.dump(out, open(cache, "w"), indent=1)
    return out


def join(votes: list, events: list, max_gap: int = 200) -> tuple:
    """(pairs, orphan_votes). One decision per vote — the FIRST that follows."""
    by_cik: dict = {}
    for e in events:
        by_cik.setdefault(e["cik"].lstrip("0"), []).append(e)
    pairs, orphans = [], []
    for v in votes:
        cands = []
        for e in by_cik.get(v["cik"], []):
            try:
                gap = (dt.date.fromisoformat(e["date"])
                       - dt.date.fromisoformat(v["date"])).days
            except ValueError:
                continue
            if 0 <= gap <= max_gap:
                cands.append((gap, e))
        if not cands:
            orphans.append(v)
            continue
        gap, e = min(cands, key=lambda x: x[0])
        pairs.append({**v, "outcome": e["kind"], "gap": gap,
                      "outcome_date": e["date"]})
    return pairs, orphans


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", type=int, default=2015)
    ap.add_argument("--end", type=int, default=2026)
    ap.add_argument("--events", default=os.path.join(SCRATCH,
                                                     "catalyst_events.csv"))
    ap.add_argument("--max-gap", type=int, default=200)
    a = ap.parse_args(argv)

    print("=" * 72)
    print("ADVISORY COMMITTEE VOTE -> FDA DECISION")
    print("=" * 72)
    with open(a.events) as f:
        events = list(csv.DictReader(f))
    votes = harvest_votes(a.start, a.end,
                          os.path.join(SCRATCH, "adcom_votes.json"))
    pairs, orphans = join(votes, events, a.max_gap)
    print(f"\nverified votes {len(votes)} · joined to a decision {len(pairs)} · "
          f"no decision found {len(orphans)}")

    if not pairs:
        print("\nNothing to measure. The vote and outcome sets do not overlap.")
        return 2

    print(f"\n  {'vote':<14}{'n':>5}{'approved':>10}{'P(approve)':>12}"
          f"{'95% CI':>18}")
    stats = {}
    for d in ("favourable", "unfavourable", "unclear"):
        sub = [p for p in pairs if p["direction"] == d]
        if not sub:
            continue
        k = sum(1 for p in sub if p["outcome"] == "APPROVAL")
        lo, hi = wilson(k, len(sub))
        stats[d] = (k, len(sub), lo, hi)
        print(f"  {d:<14}{len(sub):>5}{k:>10}{k/len(sub):>12.0%}"
              f"{f'{lo:.0%} - {hi:.0%}':>18}")

    print("\n" + "=" * 72)
    f_, u_ = stats.get("favourable"), stats.get("unfavourable")
    if not (f_ and u_):
        print("VERDICT: one side of the comparison is empty. No conditional.")
        return 0
    overlap = not (f_[2] > u_[3] or u_[2] > f_[3])
    print(f"VERDICT: favourable {f_[0]}/{f_[1]} vs unfavourable {u_[0]}/{u_[1]}")
    if overlap:
        print("  The confidence intervals OVERLAP. This sample cannot")
        print("  distinguish the two, so no conditional probability may be")
        print("  quoted from it. A point estimate here would read like")
        print("  knowledge and be noise -- and it would get quoted.")
        print(f"  8-K text yields ~{len(votes)} votes across "
              f"{a.end - a.start + 1} years; the constraint is the SOURCE,")
        print("  not the method.")
    else:
        print("  The intervals SEPARATE. An AdCom vote carries measurable")
        print("  information about the decision. Pre-register before using it.")
    print("=" * 72)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
