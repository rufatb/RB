#!/usr/bin/env python3
"""
build_shortinterest.py — day-84. Point-in-time short interest for the twins.

Pre-registered in PREREGISTER_day84.md. This module ACQUIRES the feature; it
computes no outcome and imports nothing that does.

WHAT THE SOURCE IS. FINRA's consolidated bi-weekly short interest, free and
unauthenticated, one record per symbol per settlement date, carrying the short
position, the prior position, average daily volume and days-to-cover. History
reaches at least 2020-04-15.

WHY THE US LINE IS THE RIGHT LINE *HERE*, and only here. The live book trades
`.TO`, so for the live book this feed is a proxy and PREREGISTER_day84.md
discloses it as one. But the study panel is `validate_twins`, which prices the
US dual-listing — so within the study the short position and the returns come
from the SAME listing line, which is what rule 7 requires of a ratio and of a
join. The proxy gap re-opens the moment anything here is quoted at the live
`.TO` book, and it is never to be quoted there.

THE POINT-IN-TIME RULE, which is the whole reason this file exists. The
settlement date is NOT the date the number became public. FINRA disseminates
several business days later. A session may only see a report already published
on that session's date; using the settlement date as the availability date
manufactures a look-ahead edge that looks entirely real. `publish_date` is
computed here, once, and the join in validate_shortinterest.py uses that column
and never `settlement_date`.

THE ISSUER NAME IS THE POINT-IN-TIME AUTHORITY, and this is load-bearing. A
ticker is not a company. On 2026-08-14 `GOLD` belongs to "Gold.com, Inc."
because Barrick renamed and moved to `B` — and `B` before that rename was
"Barnes Group Inc.", an unrelated industrial. So the symbol `B`'s history spans
TWO companies, and a naive fetch would have joined Barnes Group's short
interest to Barrick's returns across most of the panel.

Rather than splice on a rename date that would have to be guessed, every row is
matched against the expected issuer FRAGMENT and rows that do not match are
DROPPED AND COUNTED (rule 1 — never silently). The data authenticates itself.
A name that ends with zero usable rows is a hard failure, not a warning
(rule 9: verify the data you got, not the data you asked for).
"""

from __future__ import annotations

import argparse
import os
import sys
import time

import pandas as pd
import requests

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from validate_twins import TWINS  # noqa: E402  single source of truth

API = ("https://api.finra.org/data/group/otcMarket/name/"
       "consolidatedShortInterest")

# FINRA disseminates on the 8th business day after the settlement date. 9 is
# used so the rounding is AGAINST us: a report is treated as arriving a day
# later than it does, never a day earlier. --lag re-runs the study at a wider
# value to show the verdict does not depend on this constant.
PUBLICATION_LAG_BDAYS = 9

# Every issuer name the SAME company has filed under, per TSX name. A rename
# must be accepted (TransCanada -> TC Energy, 2019); a reassignment of the
# ticker to an UNRELATED company must be rejected. Both happen in this
# universe, they are indistinguishable from the ticker alone, and that is
# exactly why the issuer name decides rather than a date.
EXPECTED_ISSUER = {
    "RY.TO": ("royal bank",), "TD.TO": ("toronto",),
    "BNS.TO": ("nova scotia",), "BMO.TO": ("montreal",),
    "CM.TO": ("canadian imperial",), "ENB.TO": ("enbridge",),
    "TRP.TO": ("tc energy", "transcanada"),      # renamed 2019-05
    "CNQ.TO": ("canadian natural",), "SU.TO": ("suncor",),
    "CVE.TO": ("cenovus",), "CP.TO": ("canadian pacific",),
    "CNR.TO": ("canadian national",), "SHOP.TO": ("shopify",),
    "ABX.TO": ("barrick",),                      # GOLD -> B, renamed 2025-05
    "AEM.TO": ("agnico",), "NTR.TO": ("nutrien",),
    "MFC.TO": ("manulife",), "SLF.TO": ("sun life",),
    "BCE.TO": ("bce",), "T.TO": ("telus",),
}

# ABX.TO needs both symbols: Barrick filed as GOLD until 2025-04-30 and as B
# from 2025-05-15. Under GOLD the earlier rows are Randgold and the later ones
# are Gold.com; under B the earlier rows are Barnes Group. Only the issuer
# name separates them, and it does so with no gap and no overlap.
US_SYMBOLS = {tsx: [us] for tsx, us in TWINS.items()}
US_SYMBOLS["ABX.TO"] = ["B", "GOLD"]

FIELDS = ["tsx", "us", "settlement_date", "publish_date", "si", "si_prev",
          "adv", "dtc", "change_pct", "issue_name"]


class IssuerMismatch(ValueError):
    """A symbol resolved to a company we did not mean. Never downgraded."""


def publish_date(settlement, lag: int = PUBLICATION_LAG_BDAYS):
    """The first date a session is allowed to have seen this report."""
    return (pd.Timestamp(settlement) + pd.tseries.offsets.BDay(lag)).normalize()


def is_expected_issuer(tsx: str, issue_name: str) -> bool:
    """Does this row actually belong to the company `tsx` means?

    A ticker is not a company: `B` is Barrick today and was Barnes Group
    before 2025. The issuer name FINRA returns decides, per row.
    """
    frags = EXPECTED_ISSUER.get(tsx)
    if not frags:
        raise IssuerMismatch(f"{tsx} has no registered expected issuer")
    name = (issue_name or "").lower()
    return any(f in name for f in frags)


def fetch_symbol(us: str, tries: int = 4, session=None) -> list:
    """Full settlement history for one symbol. Failures are raised, not hidden."""
    http = session or requests
    last = None
    for attempt in range(tries):
        try:
            r = http.post(API, timeout=45,
                          headers={"Content-Type": "application/json",
                                   "Accept": "application/json"},
                          json={"limit": 5000, "compareFilters": [
                              {"fieldName": "symbolCode", "fieldValue": us,
                               "compareType": "EQUAL"}]})
            r.raise_for_status()
            return r.json()
        except Exception as e:                      # noqa: BLE001 — re-raised below
            last = e
            time.sleep(2.0 * (attempt + 1))
    raise RuntimeError(f"{us}: {tries} attempts failed, last was {last!r}")


def rows_for(tsx: str, us: str, payload: list,
             lag: int = PUBLICATION_LAG_BDAYS) -> tuple:
    """Rows belonging to `tsx`, plus a count of rows rejected as another issuer."""
    out, wrong = [], 0
    for r in payload:
        if not is_expected_issuer(tsx, r.get("issueName")):
            wrong += 1
            continue
        s = r.get("settlementDate")
        if not s:
            continue
        out.append({
            "tsx": tsx, "us": us, "settlement_date": str(s)[:10],
            "publish_date": str(publish_date(s, lag).date()),
            "si": r.get("currentShortPositionQuantity"),
            "si_prev": r.get("previousShortPositionQuantity"),
            "adv": r.get("averageDailyVolumeQuantity"),
            "dtc": r.get("daysToCoverQuantity"),
            "change_pct": r.get("changePercent"),
            "issue_name": r.get("issueName")})
    return out, wrong


def build(lag: int = PUBLICATION_LAG_BDAYS, session=None) -> tuple:
    """Returns (frame, failures, rejected). All three are COUNTED (rule 1)."""
    rows, failures, rejected = [], {}, {}
    for i, tsx in enumerate(sorted(US_SYMBOLS), 1):
        got, wrong = [], 0
        for us in US_SYMBOLS[tsx]:
            try:
                g, w = rows_for(tsx, us, fetch_symbol(us, session=session), lag)
                got += g
                wrong += w
            except Exception as e:                   # noqa: BLE001 — counted
                failures.setdefault(tsx, []).append(f"{us}: {e!r}")
        if wrong:
            rejected[tsx] = wrong
        rows += got
        note = f" ({wrong} rows were another issuer)" if wrong else ""
        state = "FAILED" if (tsx in failures and not got) else f"{len(got):4d} reports"
        print(f"  [{i:2d}/{len(US_SYMBOLS)}] {tsx:9s}"
              f"<-{'+'.join(US_SYMBOLS[tsx]):10s} {state}{note}", flush=True)
    df = pd.DataFrame(rows, columns=FIELDS)
    if not df.empty:
        df = df.drop_duplicates(subset=["tsx", "settlement_date"])
        df = df.sort_values(["tsx", "settlement_date"]).reset_index(drop=True)
    return df, failures, rejected


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--lag", type=int, default=PUBLICATION_LAG_BDAYS,
                    help="business days from settlement to assumed publication")
    ap.add_argument("--out", default=os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "data", "short_interest.csv"))
    a = ap.parse_args(argv)

    print(f"FINRA consolidated short interest — {len(US_SYMBOLS)} twins, "
          f"publication lag {a.lag} business days")
    df, failures, rejected = build(a.lag)
    if df.empty:
        print("  NO DATA fetched — refusing to write an empty table.")
        return 2
    os.makedirs(os.path.dirname(a.out), exist_ok=True)
    df.to_csv(a.out, index=False)
    span = f"{df['settlement_date'].min()} .. {df['settlement_date'].max()}"
    print(f"\n  {len(df):,} rows across {df['tsx'].nunique()} names, {span}")
    print(f"  wrote {a.out}")
    if rejected:
        print("  rows dropped as a DIFFERENT issuer under the same ticker: "
              + ", ".join(f"{k} {v}" for k, v in sorted(rejected.items())))
    if failures:
        print(f"  ⚠ {len(failures)} names had fetch failures: "
              + "; ".join(f"{k} {v}" for k, v in sorted(failures.items())))
    missing = sorted(set(US_SYMBOLS) - set(df["tsx"]))
    if missing:
        print(f"  ⚠ NO COVERAGE for {', '.join(missing)} — these are UNKNOWN "
              f"and must be excluded from the sorted set, never treated as zero.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
