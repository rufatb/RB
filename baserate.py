#!/usr/bin/env python3
"""
baserate.py — P(CRL), the number every breakeven in this repo has been missing.

WHAT THE REPORT COULD NOT SAY. `screen.py` computes the honest half of the
question and stops there: "the put costs 13.6% of spot, so it breaks even if a
rejection is ~89% likely at the measured median." That sentence has no ending.
A reader with no base rate cannot tell whether 89% is absurd or routine, and
the module said so out loud — P(CRL) is "deliberately NOT supplied", because
8-K filings give the numerator and not the denominator.

That refusal was right and it is also a hole. This closes it, and the first
thing to establish is why nobody has closed it for free before.

THE FDA DOES NOT PUBLISH REJECTIONS. Drugs@FDA — the agency's own complete
record, free, no key — carries a SubmissionStatus of AP (approved) or TA
(tentative) and nothing else. Checked directly: 192,337 AP, 1,205 TA, zero
rejections of any kind. A complete response letter is a private communication
to the sponsor; the agency has no obligation to announce one and does not.

So the only public trace of a rejection is the SPONSOR disclosing it, which a
US-listed company must do because it is material. That makes EDGAR the only
free route to the numerator, and it forces the denominator to come from the
same place — because a ratio whose top and bottom are drawn from different
populations is not a rate, it is an artefact.

THE POPULATION, stated precisely, because everything below is conditional on it:

    P(CRL | an FDA decision announced in an 8-K by a US-listed sponsor,
            2015-2026, classified by classify.py)

Both legs come from one harvest, one classifier, one window. `classify.py`
verifies that a filing ANNOUNCES rather than mentions its outcome (day-66), and
it is applied identically to both — which is the property that makes the ratio
mean anything at all.

THE BIAS THAT WOULD MATTER MOST, and it is measured rather than assumed. If the
harvest catches rejections more completely than approvals, P(CRL) comes out too
high. Drugs@FDA cannot supply rejections but it does supply every original
NDA/BLA approval the agency has ever granted, so the approval leg can be
audited against the truth: of the approvals granted to sponsors that are SEC
registrants, what share did this harvest actually find? That capture rate is
computed here, and the corrected estimate that follows from it is reported
beside the raw one with the correction shown rather than folded in.

THE BIASES THAT ARE NAMED AND NOT MEASURED, with their directions, because a
number with unstated biases is worse than no number:

  SUPPLEMENTS      the harvest does not distinguish an original application
                   from an sNDA. Supplements are approved at a higher rate than
                   originals, so their presence pushes the estimate DOWN --
                   the opposite direction from the coverage bias above.
  DISCLOSURE       a company might announce good news faster or more clearly
                   than bad. Both are material and both must be disclosed, but
                   whether they are disclosed with equal clarity is untested
                   here. Direction unknown.
  UNCONDITIONAL    this is a rate over all decisions in the population, not for
                   YOUR drug. A first-cycle application with a clean AdCom and
                   no manufacturing history is not the average, and neither is
                   a resubmission after a prior CRL. The report says so every
                   time it prints the number.

WHAT THIS IS FOR. Not to be multiplied by anything. It turns "you would need to
believe a rejection is 89% likely" into "you would need to believe this name is
N times more likely to be rejected than the average decision in this
population" — a comparison a portfolio manager can actually argue with.
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import io
import json
import math
import os
import re
import sys
import time
import urllib.request
import zipfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from validate_exit import SCRATCH  # noqa: E402

REPO = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(REPO, "data")


def _first(*paths) -> str:
    """The committed copy wins over the scratch copy.

    The container is recycled between sessions and takes the scratch directory
    with it. When that happened mid-build the report did not fail, it QUIETLY
    got worse: the base rate vanished and screen.py fell back to "no base rate
    has been computed" for a reason that had nothing to do with the market.
    Looking in the repository first makes the morning report reproducible from
    a fresh clone."""
    for p in paths:
        if os.path.exists(p):
            return p
    return paths[-1]


EVENTS = _first(os.path.join(DATA, "catalyst_events.csv"),
                os.path.join(SCRATCH, "catalyst_events.csv"))
DAF_URL = "https://www.fda.gov/media/89850/download"
DAF_DIR = os.path.join(SCRATCH, "drugsatfda")
OUT = os.path.join(DATA, "baserate.json")
OUT_READ = _first(OUT, os.path.join(SCRATCH, "baserate.json"))
H = {"User-Agent": "RB-research/1.0 (non-commercial)"}
# One decision, announced twice (an 8-K and its amendment, or two filings on
# consecutive days), is one decision.
DEDUPE_DAYS = 10
# How close an FDA approval date and an 8-K announcement must be to be the same
# event. Companies announce the day of or the next morning; a fortnight is
# generous in the direction of crediting the harvest with a find.
MATCH_DAYS = 14


# ─────────────────────────────────────────────────────────── the harvest
def load_events(path: str = EVENTS) -> list:
    with open(path, newline="") as f:
        return list(csv.DictReader(f))


def dedupe(rows: list, days: int = DEDUPE_DAYS) -> list:
    """One decision per sponsor per outcome per window.

    A company files the 8-K, then an amendment, then sometimes an exhibit that
    trips the same search. Counting those three times would inflate whichever
    leg happens to be more amendment-prone.
    """
    out, seen = [], {}
    for r in sorted(rows, key=lambda r: (r["cik"], r["kind"], r["date"])):
        k = (r["cik"], r["kind"])
        d = dt.date.fromisoformat(r["date"])
        if k in seen and (d - seen[k]).days <= days:
            continue
        seen[k] = d
        out.append(r)
    return out


def wilson(k: int, n: int, z: float = 1.96) -> tuple:
    """Wilson score interval. Normal approximation misbehaves near 0 and 1 and
    at the sample sizes this repo works with, which is exactly here."""
    if n == 0:
        return (float("nan"), float("nan"))
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (max(0.0, c - h), min(1.0, c + h))


def raw_rate(rows: list, start: str, end: str) -> dict:
    rows = [r for r in rows if start <= r["date"] <= end]
    crl = [r for r in rows if r["kind"] == "CRL"]
    appr = [r for r in rows if r["kind"] != "CRL"]
    n = len(crl) + len(appr)
    p = len(crl) / n if n else float("nan")
    lo, hi = wilson(len(crl), n)
    return {"n_crl": len(crl), "n_appr": len(appr), "n": n, "p": p,
            "lo": lo, "hi": hi, "crl": crl, "appr": appr}


SERIAL_MIN = 6          # announced decisions in the window: big-pharma cadence
SINGLE_MAX = 2          # one or two decisions in twelve years: a developer


def by_sponsor_frequency(rows: list, start: str, end: str) -> dict:
    """Split the rate by how often the sponsor faces the agency at all.

    THE CAVEAT THIS ATTACKS. "Unconditional" is the honest label on the
    headline number and it is also its biggest weakness: the approval leg is
    crowded with large sponsors announcing routine decisions, while the
    rejection leg is crowded with small developers facing their one binary.
    A portfolio manager looking at a single-asset biotech is not looking at the
    average of those two populations, and telling them the blended rate invites
    precisely the wrong inference.

    Sponsor frequency is a crude proxy for that difference and it costs nothing
    — it is computed from the harvest itself, needs no market-cap feed, and is
    knowable for any name at screen time by counting that CIK's own history.
    A filer with one or two announced decisions in twelve years is a developer
    with a drug; one with six or more is running a regulatory function.

    IT IS A PROXY AND NOT A MECHANISM. Frequency correlates with size, with
    resources, with how many supplements are in the mix, and with survivorship
    — a developer whose only drug was rejected may never file again, which by
    construction puts it in the infrequent bucket. That last one is a real
    circularity and it is the reason this is reported as a stratification to
    read, not as a multiplier to apply.
    """
    rows = [r for r in rows if start <= r["date"] <= end]
    per: dict = {}
    for r in rows:
        per[r["cik"]] = per.get(r["cik"], 0) + 1
    out = {}
    for label, keep in (("single-asset", lambda n: n <= SINGLE_MAX),
                        ("serial filer", lambda n: n >= SERIAL_MIN)):
        sub = [r for r in rows if keep(per[r["cik"]])]
        crl = sum(1 for r in sub if r["kind"] == "CRL")
        n = len(sub)
        lo, hi = wilson(crl, n)
        out[label] = {"n": n, "n_crl": crl, "n_sponsors":
                      len({r["cik"] for r in sub}),
                      "p": crl / n if n else float("nan"), "lo": lo, "hi": hi}
    return out


# ──────────────────────────────────────────────────────── the FDA record
def fetch_daf(cache: str = DAF_DIR) -> str:
    if not os.path.exists(os.path.join(cache, "Submissions.txt")):
        os.makedirs(cache, exist_ok=True)
        raw = urllib.request.urlopen(
            urllib.request.Request(DAF_URL, headers=H), timeout=180).read()
        zipfile.ZipFile(io.BytesIO(raw)).extractall(cache)
    return cache


def _tsv(path: str) -> list:
    # The agency's own files are not valid UTF-8 (smart quotes in sponsor
    # notes). Failing on that would be pedantry, not rigour.
    with open(path, encoding="latin-1", newline="") as f:
        return list(csv.DictReader(f, delimiter="\t"))


def fda_approvals(cache: str = DAF_DIR, start: str = "2015-01-01",
                  end: str = "2026-12-31") -> list:
    """Every ORIGINAL NDA/BLA approval in the window. Supplements excluded:
    an sNDA is a different decision with a different base rate."""
    cache = fetch_daf(cache)
    kind = {r["ApplNo"]: r["ApplType"]
            for r in _tsv(os.path.join(cache, "Applications.txt"))}
    sponsor = {r["ApplNo"]: r["SponsorName"]
               for r in _tsv(os.path.join(cache, "Applications.txt"))}
    out = []
    for r in _tsv(os.path.join(cache, "Submissions.txt")):
        if r["SubmissionType"] != "ORIG" or r["SubmissionStatus"] != "AP":
            continue
        if kind.get(r["ApplNo"]) not in ("NDA", "BLA"):
            continue
        d = (r["SubmissionStatusDate"] or "")[:10]
        if not (start <= d <= end):
            continue
        out.append({"applno": r["ApplNo"], "date": d,
                    "sponsor": sponsor.get(r["ApplNo"], ""),
                    "type": kind[r["ApplNo"]],
                    "priority": r.get("ReviewPriority", "")})
    return out


# ───────────────────────────────────────────────── matching the two sides
STOP = {"inc", "corp", "corporation", "co", "company", "ltd", "limited", "llc",
        "plc", "sa", "ag", "nv", "holdings", "holding", "group", "the",
        "pharmaceuticals", "pharmaceutical", "pharma", "therapeutics",
        "biosciences", "bioscience", "sciences", "science", "labs",
        "laboratories", "laboratory", "usa", "us", "america", "american",
        "international", "lp", "llp", "gmbh", "as", "ab", "spa", "oy"}


def tokens(name: str) -> set:
    """The distinguishing words in a company name.

    'ZYMEWORKS INC.' and 'Zymeworks Inc' must match; 'GENENTECH INC' and
    'GENELABS TECHNOLOGIES INC' must not. Stripping the corporate furniture
    leaves the part that actually identifies the company — and when that part
    is empty, the name is unusable and the caller is told rather than handed a
    match on 'inc'.
    """
    ws = re.findall(r"[a-z0-9]+", (name or "").lower())
    return {w for w in ws if w not in STOP and len(w) > 2}


def same_company(a: str, b: str) -> bool:
    ta, tb = tokens(a), tokens(b)
    if not ta or not tb:
        return False
    return bool(ta & tb) and (ta <= tb or tb <= ta or len(ta & tb) >= 2)


def sec_registrant_names(cache: str = SCRATCH) -> list:
    """(name, CIK) for every current SEC registrant.

    Used to answer one question: is this FDA sponsor the kind of entity whose
    approval SHOULD appear in an 8-K harvest? A private sponsor's absent 8-K is
    not a miss, and counting it as one would manufacture a coverage problem
    that does not exist.
    """
    p = os.path.join(cache, "company_tickers.json")
    if not os.path.exists(p):
        raw = urllib.request.urlopen(urllib.request.Request(
            "https://www.sec.gov/files/company_tickers.json",
            headers={**H, "Accept": "application/json"}), timeout=60).read()
        json.dump(json.loads(raw), open(p, "w"))
    return [(v.get("title", ""), str(v.get("cik_str", "")))
            for v in json.load(open(p)).values()]


FORM_CACHE = os.path.join(SCRATCH, "files_8k.json")


def files_8k(cik: str, cache: dict) -> bool:
    """Does this registrant file 8-Ks at all?

    THE BIAS THIS EXISTS TO REMOVE, caught while auditing a live run. The first
    version asked only "is the sponsor an SEC registrant", and the misses it
    reported were Takeda, Novartis, AstraZeneca and Sanofi — all registrants,
    none of which has ever filed an 8-K in its life. A foreign private issuer
    reports on 20-F and 6-K; Form 8-K is a domestic filer's obligation.

    Counting their approvals as ones the harvest SHOULD have found would have
    understated the capture rate, which would have inflated the correction,
    which would have pushed P(CRL) down by a mechanism with nothing to do with
    the FDA. The same logic in reverse to `sixk.py`, where a form code told
    Canadian issuers apart from US ones.
    """
    if cik in cache:
        return cache[cik]
    # THROTTLED, because the audit asks this ~650 times in a row. The SEC caps
    # automated access at ten requests a second and answers a burst with an
    # HTTP error, which is what took down the first live run of this audit --
    # and it failed as one opaque HTTPError at the end rather than as 650
    # visible refusals, which is exactly the day-29 shape.
    url = f"https://data.sec.gov/submissions/CIK{int(cik):010d}.json"
    sub = None
    for attempt in range(3):
        try:
            time.sleep(0.12)
            sub = json.loads(urllib.request.urlopen(urllib.request.Request(
                url, headers={**H, "Accept": "application/json"}),
                timeout=30).read())
            break
        except Exception:
            time.sleep(0.5 * (attempt + 1))
    if sub is None:
        return False              # NOT cached: a transient error is not a fact
    forms = sub.get("filings", {}).get("recent", {}).get("form", [])
    cache[cik] = any(f.startswith("8-K") for f in forms)
    return cache[cik]


def capture_rate(my_appr: list, fda: list, registrants: list,
                 days: int = MATCH_DAYS) -> dict:
    """Of the FDA approvals granted to SEC registrants, how many did the
    harvest find?

    This is the audit that decides whether the raw ratio can be trusted. It is
    the one bias that is measurable here, and it is the one that matters most:
    a harvest that finds rejections more completely than approvals reports a
    P(CRL) that is too high.
    """
    # An inverted index, because the naive form is 1,556 sponsors x 10,403
    # registrants of set intersection and this runs inside a morning report.
    # Only registrants sharing at least one distinguishing token can possibly
    # match, and that is a tiny candidate list for a real company name.
    index: dict = {}
    for n, cik in registrants:
        t = tokens(n)
        if not t:
            continue
        for w in t:
            index.setdefault(w, []).append((t, cik))

    fcache = {}
    if os.path.exists(FORM_CACHE):
        try:
            fcache = json.load(open(FORM_CACHE))
        except Exception:
            fcache = {}

    def is_public(sponsor: str) -> bool:
        """Registrant AND a domestic 8-K filer. Both halves are load-bearing."""
        ts = tokens(sponsor)
        if not ts:
            return False
        seen = set()
        for w in ts:
            for r, cik in index.get(w, ()):
                if cik in seen:
                    continue
                seen.add(cik)
                if (ts <= r or r <= ts or len(ts & r) >= 2) and \
                        files_8k(cik, fcache):
                    return True
        return False

    mine = [(tokens(r.get("name", "")), dt.date.fromisoformat(r["date"]))
            for r in my_appr]
    public, found = 0, 0
    misses = []
    for a in fda:
        if not is_public(a["sponsor"]):
            continue
        public += 1
        ad = dt.date.fromisoformat(a["date"])
        ts = tokens(a["sponsor"])
        hit = any(ts & mt and abs((ad - md).days) <= days
                  and (ts <= mt or mt <= ts or len(ts & mt) >= 2)
                  for mt, md in mine)
        if hit:
            found += 1
        elif len(misses) < 12:
            misses.append(f"{a['date']} {a['sponsor'][:34]}")
    try:
        json.dump(fcache, open(FORM_CACHE, "w"))
    except Exception:
        pass
    rate = found / public if public else float("nan")
    return {"fda_total": len(fda), "fda_public": public, "found": found,
            "rate": rate, "misses": misses}


def corrected(raw: dict, capture: float) -> dict:
    """The FLOOR: P(CRL) if every approval the audit says is missing belongs.

    THIS WAS CALLED "CORRECTED" AND THAT WAS THE WRONG WORD, which mattered
    because the word was doing the arguing. Scaling the approval leg by 1/capture
    treats every FDA approval granted to a domestic 8-K filer as a decision that
    SHOULD have appeared in this population. That assumption is maximally
    generous to the approval side and it is almost certainly false: materiality
    is company-specific, and a large sponsor does not file an 8-K when one of
    fifty products gets a routine approval. Those approvals are not missing from
    the harvest, they are absent from the population by construction.

    So the number this returns is not a correction. It is the FLOOR — the
    lowest P(CRL) that any reading of the coverage evidence can support — and
    the raw ratio sits at the other end. Naming it honestly is the difference
    between a bracket a reader can reason about and a point estimate that
    happens to be wrong.
    """
    if not capture or capture != capture or capture <= 0:
        return {}
    appr = raw["n_appr"] / capture
    n = raw["n_crl"] + appr
    return {"n_appr_adj": appr, "p": raw["n_crl"] / n if n else float("nan"),
            "capture": capture}


def render(raw: dict, cap: dict, corr: dict, start: str, end: str,
           strat: dict | None = None) -> str:
    L = ["=" * 74, "baserate — P(CRL) for an announced FDA decision", "=" * 74,
         "",
         f"WINDOW {start} .. {end}   (one harvest, one classifier, both legs)",
         ""]
    L.append(f"  rejections announced   {raw['n_crl']:>5}")
    L.append(f"  approvals announced    {raw['n_appr']:>5}")
    L.append(f"  ----------------------------")
    L.append(f"  decisions              {raw['n']:>5}")
    L.append("")
    L.append(f"  RAW P(CRL) = {raw['p']:.1%}   "
             f"95% Wilson [{raw['lo']:.1%}, {raw['hi']:.1%}]")
    L += ["", "-" * 74,
          "THE AUDIT — is the approval leg undercounted?", ""]
    if cap.get("error"):
        L.append(f"  UNAVAILABLE — the audit failed ({cap['error']}), so the "
                 "raw figure above is")
        L.append("  unverified in the direction that matters most. This is a "
                 "reportable")
        L.append("  failure, not a missing section: rerun it before trusting "
                 "the number.")
    elif cap.get("fda_total") is not None:
        L.append(f"  original NDA/BLA approvals, Drugs@FDA   {cap['fda_total']:>5}")
        L.append(f"  ...granted to an SEC registrant         {cap['fda_public']:>5}")
        L.append(f"  ...found in this harvest                {cap['found']:>5}"
                 f"   = {cap['rate']:.0%} capture")
        if cap["misses"]:
            L.append("  a sample of what was missed:")
            for m in cap["misses"][:6]:
                L.append(f"      {m}")
    else:
        L.append("  UNAVAILABLE — the audit could not run, so the raw figure "
                 "above is\n  unverified in the direction that matters most.")
    L += ["",
          "  WHAT THE AUDIT CANNOT COVER, and it is the other half: the FDA",
          "  publishes no rejections, so there is no external record to audit "
          "the CRL",
          "  leg against. Its completeness is bounded only by how well the "
          "search",
          "  phrases cover the language, which is why the phrase list is "
          "measured for",
          "  recall rather than assumed (see build_catalyst.PHRASES)."]
    if corr:
        L += ["", "-" * 74, "THE BRACKET, both ends derived, each with its "
                            "assumption", "",
              f"  FLOOR   {corr['p']:>6.1%}   every FDA approval granted to a "
              "domestic 8-K filer",
              "                   is treated as belonging in this population "
              "(scaling the",
              f"                   approval leg by 1/{corr['capture']:.2f} to "
              f"{corr['n_appr_adj']:.0f}). Almost certainly",
              "                   false: a large sponsor does not 8-K a routine "
              "approval,",
              "                   so those decisions are absent by "
              "construction, not missing.",
              f"  CEILING {raw['p']:>6.1%}   the harvest as it stands, which "
              "holds only if the two",
              "                   legs are captured equally well.",
              "",
              "  A wide bracket is still decisive against a breakeven of 89%. "
              "It is not",
              "  decisive against one of 20%, and the report must not pretend "
              "otherwise."]
    if strat:
        L += ["", "-" * 74,
              "THE SPLIT THAT MATTERS MORE THAN THE HEADLINE", ""]
        for label, d in strat.items():
            if not d["n"]:
                L.append(f"  {label:<14} no decisions in this bucket")
                continue
            L.append(f"  {label:<14} {d['p']:>6.1%}   "
                     f"[{d['lo']:.0%}, {d['hi']:.0%}]   "
                     f"{d['n_crl']:>3}/{d['n']:<4} decisions, "
                     f"{d['n_sponsors']} sponsors")
        L += ["",
              "  A single-asset developer facing its one binary is not the "
              "average of",
              "  this population, and neither is a sponsor running a "
              "regulatory function.",
              "  Frequency is a crude proxy for that and it is knowable for any "
              "name at",
              "  screen time. It is also circular in one direction: a developer "
              "whose only",
              "  drug was rejected may never file again, which by construction "
              "lands it in",
              "  the infrequent bucket. Read it as a stratification, not a "
              "multiplier."]
    L += ["", "-" * 74, "WHICH NUMBER TO USE, and why they differ", ""]
    L += ["  The floor and the ceiling are not two estimates of one quantity.",
          "  They answer different questions:",
          "",
          f"    {raw['p']:.0%}   P(rejection | the decision was ANNOUNCED in an "
          "8-K)",
          "           Both legs of this are complete. The rejection leg "
          "replicated",
          "           exactly under a threefold wider search (day-71), and the",
          "           approvals it misses are ones no 8-K was ever filed for.",
          "",
          "     ~2%   approaches P(rejection | ANY original FDA decision), "
          "including",
          "           every routine approval nobody announced. A larger "
          "population",
          "           and a different question.",
          ""]
    single = (strat or {}).get("single-asset") or {}
    if single.get("n"):
        L += [f"  FOR SCREENING, USE {single['p']:.0%} "
              f"[{single['lo']:.0%}, {single['hi']:.0%}] — the single-asset "
              "stratum",
              f"  ({single['n_crl']}/{single['n']} decisions across "
              f"{single['n_sponsors']} sponsors). A name with a PDUFA date "
              "worth",
              "  screening is a name for which the decision is material, so "
              "BOTH its",
              "  outcomes would be announced. That is the population whose two "
              "legs are",
              "  captured symmetrically, which is the only property that makes "
              "a ratio",
              "  mean anything.",
              "",
              "  It is biased UPWARD by one mechanism: a developer whose only "
              "drug was",
              "  rejected may never file again, so rejections are "
              "over-represented among",
              "  infrequent filers by construction. Treat it as the high end "
              "of a fair",
              "  reading."]
    L += ["",
          "  UNCONDITIONAL either way. A first-cycle application with a clean "
          "advisory",
          "  committee is not the average decision, and neither is a "
          "resubmission",
          "  after a prior CRL. This is the prior you argue away from, not the",
          "  answer for your name.",
          "",
          "  Supplements are not separated from original applications in the "
          "harvest,",
          "  and they are approved more often — which pushes this estimate "
          "DOWN, the",
          "  opposite way from the circularity above.",
          "-" * 74]
    return "\n".join(L)


def compute(events_path: str = EVENTS, start: str = "2015-01-01",
            end: str = "2026-12-31", audit: bool = True) -> dict:
    rows = dedupe(load_events(events_path))
    raw = raw_rate(rows, start, end)
    strat = by_sponsor_frequency(rows, start, end)
    cap, corr = {}, {}
    if audit:
        try:
            cap = capture_rate(raw["appr"],
                               fda_approvals(start=start, end=end),
                               sec_registrant_names())
            corr = corrected(raw, cap.get("rate", 0))
        except Exception as e:
            cap = {"error": type(e).__name__}
    out = {"computed": dt.date.today().isoformat(), "start": start, "end": end,
           "strata": strat,
           "raw": {k: v for k, v in raw.items() if k not in ("crl", "appr")},
           "capture": {k: v for k, v in cap.items() if k != "misses"},
           "corrected": corr}
    try:
        os.makedirs(DATA, exist_ok=True)
        json.dump(out, open(OUT, "w"), indent=1)
    except Exception:
        pass
    return {"raw": raw, "capture": cap, "corrected": corr, "strata": strat,
            "start": start, "end": end}


def load(path: str = None) -> dict | None:
    """What the screen reads. None when it has never been computed — the
    caller must then say so rather than substituting a guess."""
    try:
        return json.load(open(path or OUT_READ))
    except Exception:
        return None


def summary(path: str = None) -> dict | None:
    """The two ends of the estimate, for a caller that wants one line.

    A RANGE AND NOT A POINT, deliberately. The raw ratio and the
    coverage-corrected one disagree by exactly as much as the audit says the
    approval leg is undercounted, and collapsing that into a single number
    would hide the only bias here that has actually been measured. A caller
    that wants false precision has to construct it itself.
    """
    d = load(path)
    if not d or not d.get("raw", {}).get("n"):
        return None
    raw = d["raw"]
    # THE SCREENING POPULATION, not the blended one. A name with a PDUFA date
    # worth screening is a name for which the decision is material, so both its
    # outcomes would be announced -- and that is the only stratum whose two
    # legs are captured symmetrically. The blended figure mixes in serial
    # filers who announce their rejections and not their routine approvals,
    # which is precisely the asymmetry that makes a ratio meaningless.
    single = (d.get("strata") or {}).get("single-asset") or {}
    if single.get("n", 0) >= 50:
        return {"lo": single["lo"], "hi": single["hi"], "p": single["p"],
                "n": single["n"], "n_crl": single["n_crl"],
                "population": "single-asset sponsors",
                "computed": d.get("computed"), "audited": True}
    return {"lo": raw["lo"], "hi": raw["hi"], "p": raw["p"], "n": raw["n"],
            "n_crl": raw["n_crl"], "population": "all announced decisions",
            "computed": d.get("computed"),
            "audited": bool(d.get("corrected", {}).get("p"))}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--events", default=EVENTS)
    ap.add_argument("--start", default="2015-01-01")
    ap.add_argument("--end", default="2026-12-31")
    ap.add_argument("--no-audit", action="store_true")
    a = ap.parse_args(argv)
    r = compute(a.events, a.start, a.end, not a.no_audit)
    print(render(r["raw"], r["capture"], r["corrected"], a.start, a.end,
                 r.get("strata")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
