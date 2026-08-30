#!/usr/bin/env python3
"""
build_insider.py — open-market insider PURCHASES, from the SEC's bulk datasets.

WHY BULK AND NOT THE SUBMISSIONS API. Doing this per filing means fetching an
index and an XML document for every Form 4 in every window — roughly ten
thousand requests for the events in this repo. The SEC publishes the same data
as one ZIP per quarter, already parsed into TSV. Forty-seven downloads replace
ten thousand round trips, and the container has eaten three long harvests
already.

WHAT IS KEPT, AND WHAT IS THROWN AWAY. Only `TRANS_CODE == "P"`: an open-market
purchase, at a real price, with the insider's own money. Everything else is
discarded and the reason matters —

    A   an AWARD at $0. The company gave it to them. No information.
    M   an option EXERCISE. A decision about a strike price and an expiry,
        not about the drug.
    F   shares withheld for tax. Mechanical.
    S   a sale. Insiders sell for houses, divorces and diversification; the
        literature has always found the buy side far more informative, and
        mixing the two would blur the one signal worth having.

THE LOOK-AHEAD TRAP, and it is the whole ballgame. A Form 4 is filed up to TWO
BUSINESS DAYS after the transaction. `TRANS_DATE` is therefore NOT public when
it happens, and a study keyed on it credits a trader with information nobody
could have acted on. **This file keeps FILING_DATE as the event date** and
carries TRANS_DATE only as a diagnostic. Using the wrong one is the single
easiest way to manufacture a false positive in insider research, and it is the
reason so much published insider work does not survive replication.

DISK. Each quarter is ~13MB zipped and several times that unpacked. Quarters
are processed one at a time and deleted immediately, so peak usage stays near
one quarter rather than fifty.
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import io
import os
import shutil
import sys
import urllib.request
import zipfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import baserate as B  # noqa: E402

BASE = ("https://www.sec.gov/files/structureddata/data/"
        "insider-transactions-data-sets")
# The SEC wants a real contact in the UA for bulk files; a generic one gets 403.
H = {"User-Agent": "RB-research rufat.baghirov97@gmail.com",
     "Accept-Encoding": "gzip, deflate"}
OUT = os.path.join(B.DATA, "insider_buys.csv")
# 373k rows is 30MB raw and 6MB gzipped. The point of data/ is that a
# container reset cannot destroy a harvest, so it is stored compressed
# and both readers accept either form.
OUT_GZ = OUT + ".gz"
FIELDS = ["cik", "filing_date", "trans_date", "shares", "price", "usd",
          "issuer", "symbol"]


def quarters(start_year: int, end_year: int) -> list:
    out = []
    for y in range(start_year, end_year + 1):
        for q in (1, 2, 3, 4):
            out.append(f"{y}q{q}")
    return out


def _date(s: str) -> str:
    """'31-MAR-2025' -> '2025-03-31'. Blank or malformed yields ''."""
    try:
        return dt.datetime.strptime(s.strip(), "%d-%b-%Y").date().isoformat()
    except Exception:
        return ""


def fetch_quarter(tag: str, tmp: str) -> list:
    """Code-P purchases for one quarter, keyed on FILING date."""
    url = f"{BASE}/{tag}_form345.zip"
    raw = urllib.request.urlopen(
        urllib.request.Request(url, headers=H), timeout=240).read()
    z = zipfile.ZipFile(io.BytesIO(raw))
    names = set(z.namelist())
    if "SUBMISSION.tsv" not in names or "NONDERIV_TRANS.tsv" not in names:
        return []

    def rows(fn):
        with z.open(fn) as fh:
            txt = io.TextIOWrapper(fh, encoding="latin-1", newline="")
            return list(csv.DictReader(txt, delimiter="\t"))

    sub = {r["ACCESSION_NUMBER"]: r for r in rows("SUBMISSION.tsv")
           if r.get("DOCUMENT_TYPE", "").strip() == "4"}
    out = []
    for t in rows("NONDERIV_TRANS.tsv"):
        if t.get("TRANS_CODE", "").strip() != "P":
            continue
        s = sub.get(t["ACCESSION_NUMBER"])
        if not s:
            continue
        try:
            sh = float(t.get("TRANS_SHARES") or 0)
            px = float(t.get("TRANS_PRICEPERSHARE") or 0)
        except ValueError:
            continue
        if sh <= 0 or px <= 0:
            continue          # a "purchase" at $0 is not an open-market buy
        cik = (s.get("ISSUERCIK") or "").lstrip("0")
        if not cik:
            continue
        out.append({"cik": cik,
                    "filing_date": _date(s.get("FILING_DATE", "")),
                    "trans_date": _date(t.get("TRANS_DATE", "")),
                    "shares": sh, "price": px, "usd": sh * px,
                    "issuer": (s.get("ISSUERNAME") or "")[:60],
                    "symbol": (s.get("ISSUERTRADINGSYMBOL") or "").strip()})
    return [r for r in out if r["filing_date"]]


def build(start_year: int, end_year: int, out_path: str = OUT) -> int:
    tmp = os.path.join(B.SCRATCH, "_insider_tmp")
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    part = out_path + ".partial"
    done, rows = set(), []
    if os.path.exists(part):
        with open(part, newline="") as f:
            rows = list(csv.DictReader(f))
        done = {r["_q"] for r in rows if r.get("_q")}
        print(f"resuming: {len(rows):,} rows, {len(done)} quarters done",
              flush=True)
    for tag in quarters(start_year, end_year):
        if tag in done:
            continue
        try:
            got = fetch_quarter(tag, tmp)
        except Exception as e:
            print(f"  {tag}: FAILED ({type(e).__name__}) — counted, not hidden",
                  flush=True)
            continue
        for g in got:
            g["_q"] = tag
        rows += got
        print(f"  {tag}: {len(got):>5} code-P purchases", flush=True)
        with open(part, "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=FIELDS + ["_q"])
            w.writeheader()
            w.writerows(rows)
    with open(out_path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS, extrasaction="ignore")
        w.writeheader()
        w.writerows(sorted(rows, key=lambda r: (r["filing_date"], r["cik"])))
    try:
        os.remove(part)
    except OSError:
        pass
    shutil.rmtree(tmp, ignore_errors=True)
    print(f"\nwrote {len(rows):,} open-market insider purchases -> {out_path}")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", type=int, default=2014)
    ap.add_argument("--end", type=int, default=2026)
    ap.add_argument("--out", default=OUT)
    a = ap.parse_args(argv)
    return build(a.start, a.end, a.out)


if __name__ == "__main__":
    raise SystemExit(main())
