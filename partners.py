#!/usr/bin/env python3
"""
partners.py — does this company OWN the application, or is it someone else's?

THE CALL THIS WOULD HAVE CHANGED. On 2026-08-25 Zymeworks' PDUFA resolved in
approval and the stock rose 10%. Twice in the preceding days this repo told the
portfolio manager to exit, on the grounds that a single-asset developer facing
its own binary is paid too little to carry it. That reasoning was sound and the
premise was wrong: Zymeworks does not hold the application. Jazz does.
Zymeworks licensed zanidatamab out, and what the approval delivered was a
contractual **$250 million milestone**, eligibility for $1.3 billion more, and
tiered royalties of 10-20% on someone else's net sales.

A $250M payment against a company holding $179M of cash is a different object
from an NDA outcome, and the base rate for "single-asset sponsors" was never the
right prior for it. The signal was sitting in filings this repo had already
downloaded — a 2026-06-29 8-K carrying item 1.01, a material definitive
agreement — and nothing surfaced it.

THE DIRECTION IS THE WHOLE POINT, and it is why this cannot be a keyword list
for the word "partner". Biotech filings mention partnerships constantly, and
the two roles are opposite trades:

  LICENSOR   you licensed the asset OUT. Someone else's application, someone
             else's approval letter, and your payoff is contractual — a
             milestone that lands whole on the day, plus a royalty stream. Your
             exposure to the FDA is real but INDIRECT, and the milestone is
             frequently large against your own size, because a small developer
             licenses to a large one.
  LICENSEE   you licensed the asset IN. You hold the application and you OWE
             the milestone. An approval is revenue minus a payment; a rejection
             is a write-down.
  OWNED      no partnership language found. Treat as the single-asset case.

RECEIVE versus PAY is therefore the discriminator, not the presence of a
partner. "Eligible to receive up to $1.3 billion" and "obligated to pay up to
$1.3 billion" contain nearly the same words and describe opposite positions.

WHAT IT DELIBERATELY DOES NOT DO. It does not estimate what the milestone is
worth, or adjust any probability. There is no measured base rate for partnered
assets in this repo — the day-71 strata are built on sponsor FILING frequency,
which is not the same cut — so this prints a FLAG and the numbers the company
itself disclosed, and leaves the judgement where it belongs.

FAILS CLOSED. Absence of partnership language is reported as "not detected",
never as "owned outright". The filings this reads are 8-Ks about a review, not
a corporate structure chart, and a licence signed years ago may not be
mentioned in any of them.
"""

from __future__ import annotations

import argparse
import re
import sys

# Money, as filings write it: "$250 million", "$1.3 billion", "$250.0 million".
MONEY_RE = re.compile(
    r"\$\s?([\d,]+(?:\.\d+)?)\s*(million|billion|M\b|B\b)", re.I)

# You RECEIVE. The asset is out-licensed and the counterparty runs it.
LICENSOR_RE = re.compile(
    r"eligible to receive"
    r"|(?:has|have)\s+earned\s+a\s+milestone"
    r"|milestone payment[s]?\s+(?:of|from|based on)"
    r"|royalt\w+\s+on\s+(?:\w+['’]?s?\s+){0,3}net sales"
    r"|our\s+partner\b|its\s+partner\b|the\s+Company['’]?s\s+partner\b"
    r"|licensed\s+(?:\w+\s+){0,3}to\s+[A-Z]"
    r"|out-licens\w+", re.I)

# You PAY. The asset is in-licensed and you hold the application.
LICENSEE_RE = re.compile(
    r"obligated to pay"
    r"|(?:we|the Company)\s+(?:will\s+)?(?:be\s+)?(?:required|obligated)\s+to\s+pay"
    r"|pay\w*\s+(?:\w+\s+){0,4}milestone payment[s]?\s+to"
    r"|licensed\s+(?:\w+\s+){0,3}from\s+[A-Z]"
    r"|in-licens\w+"
    r"|royalt\w+\s+to\s+[A-Z]", re.I)

# Phrases that name who actually holds the marketing application.
HOLDER_RE = re.compile(
    r"(?:partner|licensee|collaborat\w+)[,\s]+([A-Z][A-Za-z&.\- ]{2,40}?)"
    r"[,\s]+(?:has|have|had)\s+(?:received|submitted|filed)"
    r"|([A-Z][A-Za-z&.\- ]{2,40}?)['’]s\s+(?:NDA|BLA|application)", re.I)


def amounts(text: str, cap: int = 6) -> list:
    """Dollar figures as stated, normalised to millions. Never inferred."""
    out = []
    for m in MONEY_RE.finditer(text):
        try:
            v = float(m.group(1).replace(",", ""))
        except ValueError:
            continue
        unit = m.group(2).lower()
        out.append(v * 1000 if unit.startswith("b") else v)
        if len(out) >= cap:
            break
    return out


def royalty_range(text: str) -> str | None:
    m = re.search(r"royalt\w+\s+of\s+(\d{1,2})%\s*(?:to|-|–)\s*(\d{1,2})%",
                  text, re.I)
    if m:
        return f"{m.group(1)}-{m.group(2)}%"
    m = re.search(r"(\d{1,2})%\s*(?:to|-|–)\s*(\d{1,2})%\s+(?:tiered\s+)?royalt",
                  text, re.I)
    return f"{m.group(1)}-{m.group(2)}%" if m else None


def holder(text: str) -> str | None:
    m = HOLDER_RE.search(text)
    if not m:
        return None
    name = (m.group(1) or m.group(2) or "").strip(" ,.")
    return name if 2 < len(name) < 42 else None


def classify(text: str) -> dict:
    """(role, evidence). Fails closed to 'not detected'.

    Both directions are counted rather than taking the first match, because a
    single filing can contain both — a company that in-licensed one asset and
    out-licensed another. The stronger side wins and the tie is reported as
    ambiguous rather than resolved arbitrarily.
    """
    lic_out = LICENSOR_RE.findall(text)
    lic_in = LICENSEE_RE.findall(text)
    n_out, n_in = len(lic_out), len(lic_in)
    if not n_out and not n_in:
        return {"role": "not detected", "out": 0, "in": 0,
                "milestones": [], "royalty": None, "holder": None}
    if n_out == n_in:
        role = "ambiguous"
    else:
        role = "LICENSOR" if n_out > n_in else "LICENSEE"
    return {"role": role, "out": n_out, "in": n_in,
            "milestones": amounts(text), "royalty": royalty_range(text),
            "holder": holder(text)}


def render(p: dict | None, spot: float | None = None,
           shares: float | None = None) -> list:
    """Report lines. Silent only when partnership was checked and not found."""
    if p is None:
        return ["        ownership: NOT CHECKED — this calendar row predates "
                "the check; absence is not evidence of a wholly-owned asset"]
    if p["role"] == "not detected":
        return []
    L = []
    if p["role"] == "LICENSOR":
        who = f" ({p['holder']})" if p.get("holder") else ""
        L.append(f"        ⚑ PARTNERED — OUT-licensed{who}. The application is "
                 "not this company's;")
        L.append("          the payoff is contractual: a milestone that lands "
                 "whole on the day,")
        L.append("          plus a royalty. Direct FDA exposure is INDIRECT "
                 "and the milestone is")
        L.append("          often large against a small licensor's own size.")
    elif p["role"] == "LICENSEE":
        L.append("        ⚑ PARTNERED — IN-licensed. This company holds the "
                 "application AND owes")
        L.append("          the milestone: an approval is revenue minus a "
                 "payment.")
    else:
        L.append("        ⚑ PARTNERSHIP language on BOTH sides — read the "
                 "filing; this name may")
        L.append("          license in one asset and out-license another.")
    if p.get("milestones"):
        # DISTINCT values, largest first. A filing states a near-term payment
        # and a lifetime ceiling in the same paragraph ("earned $250 million...
        # eligible for up to $1.3 billion"), and collapsing them to one number
        # either overstates what just landed or hides what is still to come.
        vals = sorted({round(v) for v in p["milestones"]}, reverse=True)[:3]
        shown = ", ".join(f"${v:,.0f}M" for v in vals)
        line = f"          disclosed milestone figures: {shown}"
        if spot and shares:
            cap = spot * shares / 1e6
            line += (f"  (market cap ~${cap:,.0f}M — "
                     f"the largest is {vals[0]/cap:.0%} of it)")
        L.append(line)
    if p.get("royalty"):
        L.append(f"          tiered royalty {p['royalty']} on net sales")
    L.append("          NOT a probability adjustment: this repo has no "
             "measured base rate for")
    L.append("          partnered assets. It is a flag and the company's own "
             "disclosed numbers.")
    return L


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("path", help="a file containing filing text")
    a = ap.parse_args(argv)
    text = open(a.path).read()
    print("\n".join(render(classify(text))) or "no partnership language found")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
