#!/usr/bin/env python3
"""
build_social.py — day-94 Arm A. Forward collection of social/search attention.

Pre-registered in PREREGISTER_day94.md (committed before any outcome was
computed). This module COLLECTS ONLY: one dated snapshot per session into
data/social/YYYY-MM-DD.json. It computes no outcome, runs no inference and is
imported by nothing in the daily report path. SHADOW RESEARCH.

WHY FORWARD COLLECTION ONLY. Neither source serves point-in-time history:
StockTwits does not serve stream history, and Google re-normalizes Trends
values on every pull, so a "historical" download is not the series observable
at the time (rule 9). The only honest attention panel is one collected
prospectively, which is what this file does and all it does.

FAIL-CLOSED CONTRACT (rules 1, 2 and the registration's Forbidden list).
A fetch error is recorded per name with its error class and is NEVER stored
as zero attention. A TSX->US mapping that the API's returned symbol title
does not authenticate is recorded UNMAPPED and contributes nothing. A
response that is not for the requested symbol is a contract violation,
counted and rejected. The snapshot distinguishes OK / UNMAPPED / ERROR so
the coverage gate never has to guess.

COVERAGE GATE (registered, runs via --coverage): after >= 20 collected
sessions, per-name median messages/day over that name's OK sessions. Fewer
than 8 of 21 names at median >= 1 message/day means the family is
UNRUNNABLE for this universe — a finding, not an inconvenience.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import statistics
import sys
import tempfile
import time
from zoneinfo import ZoneInfo

import requests
import yaml

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

STOCKTWITS_STREAM = "https://api.stocktwits.com/api/2/streams/symbol/{symbol}.json"
TRENDS_EXPLORE = "https://trends.google.com/trends/api/explore"
TRENDS_MULTILINE = "https://trends.google.com/trends/api/widgetdata/multiline"

# Registered coverage gate (PREREGISTER_day94.md). These do not move.
GATE_SESSIONS = 20          # sessions collected before the gate is decidable
GATE_MIN_NAMES = 8          # of the 21 universe names
GATE_MIN_MEDIAN = 1.0       # messages/day, median over a name's OK sessions

# The ticker is not the company. Each TSX name's US-mapped stream must return
# a symbol title containing one of these fragments, or the mapping is
# UNMAPPED — never guessed (same load-bearing rule as build_shortinterest.py).
# Note T.TO -> T is EXPECTED to fail this check (T is AT&T, not TELUS); the
# check existing is the point, and its failure is recorded, not routed around.
EXPECTED_ISSUER = {
    "RY.TO": ("royal bank",), "TD.TO": ("toronto",),
    "BNS.TO": ("nova scotia",), "BMO.TO": ("montreal",),
    "CM.TO": ("canadian imperial",), "ENB.TO": ("enbridge",),
    "TRP.TO": ("tc energy", "transcanada"),
    "CNQ.TO": ("canadian natural",), "SU.TO": ("suncor",),
    "CVE.TO": ("cenovus",), "CP.TO": ("canadian pacific",),
    "CNR.TO": ("canadian national",), "SHOP.TO": ("shopify",),
    "ABX.TO": ("barrick",),
    "AEM.TO": ("agnico",), "NTR.TO": ("nutrien",),
    "MFC.TO": ("manulife",), "SLF.TO": ("sun life",),
    "BCE.TO": ("bce",), "T.TO": ("telus",),
    "AC.TO": ("air canada",),
}

UA = {"User-Agent": "Mozilla/5.0 (day-94 attention collector; research)"}


class StreamContractError(ValueError):
    """The response was not for the requested symbol. Never downgraded."""


def error_class(exc: BaseException) -> str:
    """A short, stable failure label. Failures are counted by class (rule 1)."""
    if isinstance(exc, requests.HTTPError) and exc.response is not None:
        return f"HTTP_{exc.response.status_code}"
    if isinstance(exc, requests.Timeout):
        return "TIMEOUT"
    if isinstance(exc, requests.ConnectionError):
        return "CONNECTION"
    if isinstance(exc, (json.JSONDecodeError, ValueError)):
        return "DECODE"
    return type(exc).__name__.upper()


def parse_stream(payload: dict, requested_symbol: str,
                 now: dt.datetime | None = None) -> dict:
    """Counts from one StockTwits symbol-stream response. Pure given a payload.

    Asserts the response is for the requested symbol (rule 9). Sentiment tags
    are author-applied `entities.sentiment.basic` values; messages without one
    are counted in `messages` but in neither sentiment bucket. Messages with an
    unparseable timestamp are rejected and COUNTED, never silently kept.

    `messages` IS NOT AN ATTENTION MEASURE, AND MUST NEVER BE USED AS ONE.
    Day-94 collection, first live run: all 18 mappable names returned EXACTLY
    30 — the endpoint's page size. The stream serves one page of most-recent
    messages, so `len(messages)` saturates and carries zero variance across
    names and across days. It is the page size, not the traffic.

    The page's TIMESTAMPS still hold the signal, and the same run showed how
    much: ENB's newest message was hours old while SLF's was 23 DAYS old, and
    both stored `messages = 30`. So attention is measured here as a count in a
    fixed lookback window (rule 9 -- verify the data you GOT):

        msgs_24h / msgs_7d   messages in that window before `now`
        censored_24h/_7d     True when the WHOLE page falls inside the window,
                             so the count is a LOWER BOUND (>= page_size) and
                             the true rate is unknown-but-larger
        page_size            what the endpoint actually returned

    A censored window is not a bad reading, it is a partial one, and it is
    flagged rather than folded in (rule 2, and rule 7's habit of showing a
    correction beside a raw figure instead of merging them).
    """
    if not isinstance(payload, dict):
        raise StreamContractError("stream payload is not an object")
    status = (payload.get("response") or {}).get("status")
    if status != 200:
        raise StreamContractError(f"stream response status {status!r}")
    sym = payload.get("symbol") or {}
    returned = str(sym.get("symbol") or "")
    if returned.upper() != requested_symbol.upper():
        raise StreamContractError(
            f"asked for {requested_symbol}, got stream for {returned!r}")
    messages = payload.get("messages") or []
    if now is None:
        now = dt.datetime.now(dt.timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=dt.timezone.utc)
    bullish = bearish = rejects = 0
    max_ts = min_ts = None
    stamps = []
    for m in messages:
        if not isinstance(m, dict):
            rejects += 1
            continue
        basic = ((m.get("entities") or {}).get("sentiment") or {}).get("basic")
        if basic == "Bullish":
            bullish += 1
        elif basic == "Bearish":
            bearish += 1
        raw = m.get("created_at")
        try:
            ts = dt.datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
        except (ValueError, TypeError):
            rejects += 1
            continue
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=dt.timezone.utc)
        stamps.append(ts)
        if max_ts is None or ts > max_ts:
            max_ts = ts
        if min_ts is None or ts < min_ts:
            min_ts = ts

    page_size = len(messages)
    windows = {}
    for label, hours in (("24h", 24), ("7d", 24 * 7)):
        cutoff = now - dt.timedelta(hours=hours)
        n = sum(1 for ts in stamps if ts >= cutoff)
        # Censored when EVERY dated message on the page is inside the window:
        # the page ran out before the window did, so `n` is a lower bound.
        windows["msgs_" + label] = n
        windows["censored_" + label] = bool(stamps) and n == len(stamps)

    return {"us": requested_symbol, "symbol_title": sym.get("title"),
            "messages": page_size, "page_size": page_size,
            "bullish": bullish, "bearish": bearish,
            "max_message_ts": max_ts.isoformat() if max_ts else None,
            "min_message_ts": min_ts.isoformat() if min_ts else None,
            "rejected_messages": rejects, **windows}


def verify_mapping(tsx: str, symbol_title: str | None) -> bool:
    """Does the returned stream title actually belong to the company `tsx` is?"""
    frags = EXPECTED_ISSUER.get(tsx)
    if not frags:
        raise StreamContractError(f"{tsx} has no registered expected issuer")
    name = (symbol_title or "").lower()
    return any(f in name for f in frags)


def fetch_stream(symbol: str, tries: int = 3, timeout: float = 30.0,
                 session=None) -> tuple:
    """(payload, None) or (None, error_class). Retries with backoff; the final
    failure is RETURNED for the caller to record, never swallowed (rule 1)."""
    http = session or requests
    last = None
    for attempt in range(max(1, tries)):
        try:
            r = http.get(STOCKTWITS_STREAM.format(symbol=symbol),
                         headers=UA, timeout=timeout)
            r.raise_for_status()
            return r.json(), None
        except Exception as e:                      # noqa: BLE001 — returned below
            last = e
            if attempt + 1 < tries:
                time.sleep(1.0 * (attempt + 1))
    return None, f"{error_class(last)} after {max(1, tries)} tries"


def fetch_trends(terms: list, timeout: float = 20.0, session=None) -> dict:
    """Guarded unofficial Google Trends pull. pytrends is deliberately NOT a
    dependency (registration). Any deviation from the two-response contract is
    recorded as UNAVAILABLE/ERROR with its class — never parsed into a number
    and never fabricated. Values are stored verbatim as observed at collection
    time, because later pulls are re-normalized and NOT the same series.
    """
    http = session or requests
    out = {"status": "OK", "terms": {}, "batches": 0, "failures": {}}
    for i in range(0, len(terms), 5):
        batch = terms[i:i + 5]
        try:
            req = {"comparisonItem": [{"keyword": t, "geo": "CA",
                                       "time": "today 3-m"} for t in batch],
                   "category": 0, "property": ""}
            r = http.post(TRENDS_EXPLORE, headers=UA, timeout=timeout,
                          data={"hl": "en-CA", "tz": "300",
                                "req": json.dumps(req)})
            r.raise_for_status()
            explore = json.loads(r.text.lstrip(")]}',\n "))
            widget = next((w for w in explore.get("widgets") or []
                           if w.get("id") == "TIMESERIES"), None)
            if not widget or "token" not in widget or "request" not in widget:
                raise StreamContractError("no TIMESERIES widget in explore response")
            r2 = http.get(TRENDS_MULTILINE, headers=UA, timeout=timeout,
                          params={"hl": "en-CA", "tz": "300",
                                  "req": json.dumps(widget["request"]),
                                  "token": widget["token"]})
            r2.raise_for_status()
            series = json.loads(r2.text.lstrip(")]}',\n "))
            timeline = (series.get("default") or {}).get("timelineData") or []
            for j, t in enumerate(batch):
                out["terms"][t] = [
                    {"date": str(int(p["time"])), "value": (p.get("value") or [None])[j]}
                    for p in timeline if "time" in p]
            out["batches"] += 1
        except Exception as e:                      # noqa: BLE001 — recorded
            for t in batch:
                out["failures"][t] = error_class(e)
    if out["failures"]:
        out["status"] = "ERROR" if not out["batches"] else "PARTIAL"
    if not out["terms"] and not out["failures"]:
        out["status"] = "UNAVAILABLE"
        out["error"] = "no terms requested"
    return out


def universe_from_config(cfg: dict) -> list:
    """The 21 registered names: scan.universe plus the configured anchor."""
    names = sorted(set((cfg.get("scan") or {}).get("universe") or [])
                   | {cfg.get("ticker")})
    return [n for n in names if n]


def collect(cfg: dict, session=None, trends_session=None,
            now: dt.datetime | None = None) -> dict:
    """One session's snapshot. Every name ends in OK / UNMAPPED / ERROR."""
    social = cfg.get("social") or {}
    if not social.get("enabled", False):
        raise SystemExit("social.enabled is false — collector disabled in config")
    smap = social.get("us_symbol_map") or {}
    delay = float(social.get("request_delay_sec", 0.5))
    tries = int(social.get("retries", 3))
    timeout = float(social.get("timeout_sec", 30.0))
    now = now or dt.datetime.now(dt.timezone.utc)
    names, counts = {}, {"ok": 0, "unmapped": 0, "error": 0}
    universe = universe_from_config(cfg)
    for i, tsx in enumerate(universe):
        us = smap.get(tsx)
        entry = {"us": us, "status": None, "messages": None, "bullish": None,
                 "bearish": None, "max_message_ts": None,
                 "symbol_title": None, "rejected_messages": 0, "error": None}
        if not us:
            entry.update(status="UNMAPPED", error="no us_symbol_map entry")
            counts["unmapped"] += 1
        else:
            payload, err = fetch_stream(us, tries=tries, timeout=timeout,
                                        session=session)
            if err is not None:
                entry.update(status="ERROR", error=err)
                counts["error"] += 1
            else:
                try:
                    parsed = parse_stream(payload, us)
                    entry.update(parsed)
                    if verify_mapping(tsx, parsed["symbol_title"]):
                        entry["status"] = "OK"
                        counts["ok"] += 1
                    else:
                        # The stream is another company's attention. Null the
                        # counts: under the TSX name they are UNKNOWN, not data.
                        entry.update(status="UNMAPPED", messages=None,
                                     bullish=None, bearish=None,
                                     max_message_ts=None, rejected_messages=0,
                                     error="title does not authenticate "
                                           f"{tsx}: {parsed['symbol_title']!r}")
                        counts["unmapped"] += 1
                except Exception as e:              # noqa: BLE001 — counted
                    entry.update(status="ERROR", error=error_class(e),
                                 error_detail=str(e))
                    counts["error"] += 1
        names[tsx] = entry
        state = entry["status"]
        if state == "OK":
            # page= is the endpoint's page size and saturates at 30; 24h= is
            # the attention measure. Printing both is what made the censoring
            # visible in the first place -- do not collapse them.
            extra = (f" 24h={entry.get('msgs_24h')}"
                     f"{'+' if entry.get('censored_24h') else ''}"
                     f" 7d={entry.get('msgs_7d')}"
                     f"{'+' if entry.get('censored_7d') else ''}"
                     f" page={entry['page_size']}")
        else:
            extra = f" ({entry['error']})"
        print(f"  [{i + 1:2d}/{len(universe)}] {tsx:9s}<-{str(us):6s} {state}{extra}",
              flush=True)
        if i + 1 < len(universe):
            time.sleep(delay)                       # polite; never hammer
    terms = [smap[t] for t in universe if smap.get(t)]
    trends = fetch_trends(terms, session=trends_session)
    if trends["status"] != "OK":
        print(f"  Google Trends: {trends['status']} "
              f"({trends.get('failures') or trends.get('error')}) — "
              "recorded, continuing with StockTwits only", flush=True)
    return {"date": now.date().isoformat(),
            "collected_at": now.isoformat(),
            "source": "stocktwits+google_trends(unofficial)",
            "registration": "PREREGISTER_day94.md",
            "names": names, "trends": trends,
            **decision_usability(now),
            "coverage": {"total": len(universe), **counts,
                         "sessions_in_file": 1}}


DECISION_ET = dt.time(9, 46)


def decision_usability(collected_at: dt.datetime) -> dict:
    """Was this snapshot knowable at the 09:46 decision, or is it look-ahead?

    The registration collects at 09:20 ET -- PRE-OPEN, and therefore knowable
    when the board is selected. That timing is not cosmetic. A snapshot taken
    at 09:48 contains the market's REACTION to the open, so a feature built
    from it would predict a 09:46 decision using information from after it.
    That is the look-ahead this repo exists to exclude, and it would arrive
    disguised as a scheduling convenience -- run the collector from the
    morning wrapper, after the report, and every row is quietly poisoned.

    So the snapshot carries the verdict rather than the reader inferring it
    from a timestamp. `decision_usable` false does not make a snapshot
    worthless; it makes it unusable AS A FEATURE for that session's board,
    which is a different and narrower thing.
    """
    et = collected_at.astimezone(ZoneInfo("America/Toronto"))
    usable = et.time() < DECISION_ET
    return {"collected_at_et": et.isoformat(),
            "decision_usable": usable,
            "decision_note": (
                "collected before the 09:46 ET decision — knowable at "
                "selection time" if usable else
                f"COLLECTED AT {et.strftime('%H:%M')} ET, AFTER the 09:46 "
                "decision — contains the market's reaction to the open and "
                "MUST NOT be used as a feature for this session's board")}


def write_snapshot(snapshot: dict, outdir: str) -> str:
    """Atomic dated write: temp file in the target directory, then replace."""
    os.makedirs(outdir, exist_ok=True)
    path = os.path.join(outdir, f"{snapshot['date']}.json")
    fd, tmp = tempfile.mkstemp(dir=outdir, prefix=".social-", suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(snapshot, f, indent=2, sort_keys=True)
        os.replace(tmp, path)
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise
    return path


def load_snapshots(outdir: str) -> list:
    """All dated snapshots, oldest first. Unparseable files fail loudly."""
    out = []
    if not os.path.isdir(outdir):
        return out
    for fn in sorted(os.listdir(outdir)):
        if fn.endswith(".json") and not fn.startswith("."):
            with open(os.path.join(outdir, fn)) as f:
                out.append(json.load(f))
    return out


def coverage_gate(snapshots: list, min_sessions: int = GATE_SESSIONS,
                  min_names: int = GATE_MIN_NAMES,
                  min_median: float = GATE_MIN_MEDIAN) -> dict:
    """The registered 20-session coverage gate. Failed fetches are EXCLUDED
    from a name's medians — never counted as zero attention (Forbidden list).

    THE BAR HAS NOT MOVED (rule 3). GATE_SESSIONS, GATE_MIN_NAMES and
    GATE_MIN_MEDIAN are exactly as registered. What changed day-94 is that the
    gate now reads the quantity the registration NAMED -- "median messages/day"
    -- instead of `len(messages)`, which is the endpoint's page size and was 30
    for every name on every name's first live pull. Taking a median of a
    constant returned "18/21 usable" while measuring nothing at all, and 120
    sessions later a constant feature would have produced a zero AUC difference
    that read as a null about attention rather than a broken instrument.

    Reading the registered quantity makes the gate HARDER to pass, not easier,
    which is the only safe direction for a correction like this. The
    registration's own expected outcome was that most TSX names fail it.

    Snapshots written before the fix have no `msgs_24h` and are skipped for
    that name with `pre_fix_sessions` counted, never back-filled from the
    page-size figure.
    """
    per_name: dict = {}
    for snap in snapshots:
        for tsx, e in (snap.get("names") or {}).items():
            rec = per_name.setdefault(
                tsx, {"ok_sessions": 0, "counts": [], "censored": 0,
                      "pre_fix_sessions": 0})
            if e.get("status") != "OK":
                continue
            if e.get("msgs_24h") is None:
                rec["pre_fix_sessions"] += 1
                continue
            rec["ok_sessions"] += 1
            rec["counts"].append(int(e["msgs_24h"]))
            if e.get("censored_24h"):
                rec["censored"] += 1
    names = {}
    for tsx, rec in sorted(per_name.items()):
        med = (float(statistics.median(rec["counts"]))
               if rec["counts"] else None)
        names[tsx] = {"ok_sessions": rec["ok_sessions"],
                      "median_messages_per_day": med,
                      "censored_sessions": rec["censored"],
                      "pre_fix_sessions": rec["pre_fix_sessions"],
                      "usable": bool(med is not None and med >= min_median)}
    usable = sum(1 for n in names.values() if n["usable"])
    sessions = len(snapshots)
    if sessions < min_sessions:
        gate = "COLLECTING"
        note = (f"{sessions}/{min_sessions} sessions collected — the gate is "
                "not decidable yet and no attention inference is registered "
                "before 120 sessions")
    else:
        gate = "PASS" if usable >= min_names else "UNRUNNABLE_FOR_UNIVERSE"
        note = (f"{usable}/{len(names)} names at median >= {min_median} "
                f"messages/day over their OK sessions; registered bar is "
                f">= {min_names} names")
    return {"sessions_collected": sessions, "min_sessions": min_sessions,
            "names": names, "usable_names": usable, "min_names": min_names,
            "gate": gate, "note": note}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--config", default=os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "config.yaml"))
    ap.add_argument("--outdir", default=os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "data", "social"))
    ap.add_argument("--coverage", action="store_true",
                    help="no network: evaluate the registered coverage gate "
                         "over accumulated snapshots and exit")
    a = ap.parse_args(argv)

    if a.coverage:
        snaps = load_snapshots(a.outdir)
        result = coverage_gate(snaps)
        print(f"DAY-94 ARM-A COVERAGE GATE — {result['sessions_collected']} "
              f"snapshots in {a.outdir}")
        for tsx, n in result["names"].items():
            med = n["median_messages_per_day"]
            flags = []
            if n["censored_sessions"]:
                flags.append(f"{n['censored_sessions']} censored(>=)")
            if n["pre_fix_sessions"]:
                flags.append(f"{n['pre_fix_sessions']} pre-fix skipped")
            print(f"  {tsx:9s} ok={n['ok_sessions']:3d} median_msgs/day="
                  f"{med if med is not None else 'n/a':>6} "
                  f"{'USABLE' if n['usable'] else '-':7s}"
                  f"{'  ' + ', '.join(flags) if flags else ''}")
        print(f"  usable names: {result['usable_names']} "
              f"(registered bar >= {result['min_names']} of 21)")
        print(f"  GATE: {result['gate']} — {result['note']}")
        return 0 if result["gate"] == "PASS" else 1

    with open(a.config) as f:
        cfg = yaml.safe_load(f)
    snap = collect(cfg)
    path = write_snapshot(snap, a.outdir)
    c = snap["coverage"]
    print(f"\n  wrote {path}")
    print(f"  coverage: {c['ok']} OK / {c['unmapped']} UNMAPPED / "
          f"{c['error']} ERROR of {c['total']} names; "
          f"trends={snap['trends']['status']}")
    if c["error"] or c["unmapped"]:
        print("  non-OK names are UNKNOWN attention, never zero — they are "
              "excluded from medians by the coverage gate.")
    return 0 if c["ok"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
