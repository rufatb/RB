#!/usr/bin/env python3
"""
classify.py — is this 8-K ANNOUNCING the event, or merely mentioning it?

THE BLOCKER THIS REMOVES. Day-56 killed the catalyst backtest: random
three-day windows on the same tickers were indistinguishable from "event"
windows (CRL vs random t=+0.31, approval t=+0.99). That was a verdict on the
LABELS, not on FDA decisions. A full-text search for "complete response letter"
returns every filing that MENTIONS one, and companies keep referring back to a
CRL for months — in resubmission news, guidance updates, financing documents —
so rejections entered the sample at dates when the stock had long recovered.

The clearest illustration found while diagnosing it: Ardelyx's 8-K of
2021-07-30 matched the phrase and is about a LOAN AGREEMENT amendment, saying
"following the July 28, 2021 issuance by the FDA of a complete response
letter". The CRL is two days old and incidental to the filing.

THE THREE SIGNALS, in order of reliability.

  1  ANNOUNCEMENT PHRASING. A filing that announces says so, in the lead:
     "announced that it received a Complete Response Letter" (RGNX),
     "to announce receipt of a Complete Response Letter" (ALDX),
     "announcing that it had received a Complete Response Letter" (VNDA, PTCT).
     Searching for that phrasing instead of the bare noun cuts 4,463 matches to
     34 over two and a half years.

  2  MENTION MARKERS veto. "previously disclosed", "previously received",
     "following the ... issuance". These are how a filing refers to something
     already known, and they beat any announcement phrasing in the same text.

  3  DATE LAG. When a date sits beside the phrase, compare it to the filing
     date. Zero to two days is an announcement; two months is a reference to
     history. Ardelyx's loan 8-K carries a lag of 2 days and is still a mention,
     which is why this signal ranks BELOW the marker veto rather than above it.

FAILS CLOSED TOWARD "MENTION". An uncertain filing is excluded rather than
admitted. Losing a real event costs sample size; admitting a false one poisons
the labels, and poisoned labels are what produced a study that could not tell an
FDA decision from a random Tuesday. Sample size can be recovered by widening the
window later; a contaminated sample cannot be cleaned afterwards.
"""

from __future__ import annotations

import datetime as dt
import re

# NOTE ON `.` VS `[^.]`. These patterns first used `[^.]` to stay inside a
# sentence, which fails on the single most common phrase in this domain: "the
# U.S. Food and Drug Administration" contains two periods, so a sentence-scoped
# gap could never reach from "approved by" to "Food and Drug Administration".
# The character BOUND does the scoping work instead.

# Phrasing that announces rather than refers.
ANNOUNCE_RE = re.compile(
    r"(?:announc\w+|issued a press release|reported|disclos\w+)"
    r".{0,120}?(?:receipt of|received|receiving)\s+(?:a|the)\s+"
    r"[Cc]omplete\s+[Rr]esponse\s+[Ll]etter"
    r"|(?:has|have|had)\s+received\s+(?:a|the)\s+"
    r"[Cc]omplete\s+[Rr]esponse\s+[Ll]etter"
    r"|announce\w*\s+receipt\s+of\s+(?:a|the)\s+"
    r"[Cc]omplete\s+[Rr]esponse\s+[Ll]etter", re.I)

# How a filing refers to something already public. These veto.
MENTION_RE = re.compile(
    r"previously\s+(?:disclosed|received|announced|reported|approved)"
    r"|following\s+the\s+.{0,60}?(?:issuance|receipt)"
    r"|as\s+previously"
    r"|the\s+prior\s+[Cc]omplete\s+[Rr]esponse", re.I)

DATE_RE = re.compile(
    r"\b(January|February|March|April|May|June|July|August|September|"
    r"October|November|December)\s+(\d{1,2}),\s+(20\d\d)\b")

# English puts the agency on either side of the verb -- "the FDA approved X"
# and "X was approved by the FDA" are equally common, and the first version of
# this pattern demanded the first order only, so it missed the more common one.
APPROVAL_ANNOUNCE_RE = re.compile(
    r"(?:announc\w+|issued a press release|reported).{0,160}?"
    r"(?:(?:FDA|Food and Drug Administration).{0,60}?approv\w+"
    r"|approv\w+.{0,60}?(?:FDA|Food and Drug Administration))"
    r"|(?:FDA|Food and Drug Administration)\s+(?:has\s+)?approved", re.I)


def nearby_dates(text: str, idx: int, window: int = 260,
                 forward: int = 240) -> list:
    """Dates surrounding the phrase.

    The forward reach matters as much as the backward one: filings routinely
    put the date AFTER the event -- "received a Complete Response Letter from
    the FDA regarding the Company's BLA on February 9, 2026" -- and a 120-char
    forward window clipped exactly that sentence.
    """
    seg = text[max(0, idx - window):idx + forward]
    out = []
    for m in DATE_RE.findall(seg):
        try:
            out.append(dt.datetime.strptime(f"{m[0]} {m[1]} {m[2]}",
                                            "%B %d %Y").date())
        except ValueError:
            continue
    return out


def classify_crl(text: str, filing_date: str, max_lag: int = 3) -> tuple:
    """(is_announcement, reason). Pure + testable.

    Order is deliberate and was learned from real filings: the mention VETO is
    applied before the date test, because Ardelyx's loan-agreement 8-K carries a
    2-day lag — inside any sane window — and is still plainly a reference to
    something that already happened.
    """
    spots = _anchors(text, CRL_ANCHOR_RE)
    if not spots:
        return False, "phrase absent"
    i, first_why = None, None
    for cand in spots:
        ok, why = _judge(text, cand, ANNOUNCE_RE)
        if ok:
            i = cand
            break
        first_why = first_why or why
    if i is None:
        return False, (first_why or "no announcement phrasing near the mention")
    try:
        fd = dt.date.fromisoformat(filing_date)
    except ValueError:
        return True, "announcement phrasing (filing date unparseable)"
    ds = nearby_dates(text, i)
    if ds:
        lag = min(abs((fd - x).days) for x in ds)
        if lag > max_lag:
            return False, f"nearest CRL date is {lag}d from the filing"
        return True, f"announcement phrasing, date lag {lag}d"
    return True, "announcement phrasing, no date stated"


# DAY-74: the anchor list was three literal strings, and a live filing walked
# straight through all three. Zymeworks' 8-K of 2026-08-25 announces an FDA
# approval in its first sentence and was classified "phrase absent":
#
#   "...has received U.S. Food and Drug Administration ("FDA") approval for
#    two Ziihera(R) (zanidatamab-hrii)-containing regimens..."
#
# Two independent misses in one sentence. The anchor "fda approval of" hardcodes
# a PREPOSITION, and this filing says "approval for" and later "approval in".
# And the agency-name form is separated from "approval" by a parenthetical
# gloss, which no fixed string can span.
#
# So the anchor becomes a pattern rather than a list of strings, and it keeps
# the day-66 architecture intact: BROAD ANCHOR, STRICT VERIFICATION. Widening
# what gets LOOKED at is safe precisely because the mention-veto and the
# announcement test still have to pass afterwards.
APPROVAL_ANCHOR_RE = re.compile(
    r"(?:FDA|Food\s+and\s+Drug\s+Administration)[^.]{0,80}?approv\w+"
    r"|approv\w+[^.]{0,80}?(?:by|from)\s+the\s+"
    r"(?:FDA|U\.?S\.?\s+Food\s+and\s+Drug\s+Administration)", re.I)

CRL_ANCHOR_RE = re.compile(r"[Cc]omplete\s+[Rr]esponse\s+[Ll]etter", re.I)


def _anchors(text: str, rx: re.Pattern, cap: int = 40) -> list:
    """Every place the event is named, not just the first.

    THE SECOND RECALL BUG, and it is subtler than the anchor strings. Both
    classifiers used `str.find`, which returns the FIRST occurrence and nothing
    else. A filing whose opening paragraph refers to a prior approval and whose
    body announces a new one was judged entirely on the reference — the veto
    fired on occurrence one and the announcement at occurrence four was never
    examined.

    Scanning every occurrence raises recall without loosening any test: a
    filing still counts only if SOME occurrence carries announcement phrasing
    with no mention marker beside it. Strictness is unchanged; thoroughness is
    not.
    """
    return [m.start() for m in list(rx.finditer(text))[:cap]]


def _judge(text: str, idx: int, announce: re.Pattern) -> tuple:
    seg = text[max(0, idx - 300):idx + 200]
    if MENTION_RE.search(seg):
        return False, "refers to a previously disclosed event"
    if not announce.search(seg):
        return False, "no announcement phrasing near the mention"
    return True, "announcement phrasing"


def classify_approval(text: str, filing_date: str) -> tuple:
    """Same discipline for the approval side, applied at every occurrence."""
    spots = _anchors(text, APPROVAL_ANCHOR_RE)
    if not spots:
        return False, "phrase absent"
    reasons = []
    for i in spots:
        ok, why = _judge(text, i, APPROVAL_ANNOUNCE_RE)
        if ok:
            return True, why
        reasons.append(why)
    return False, reasons[0]
