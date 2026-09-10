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
sessions, per-name median observed messages/day over at least 20 OK sessions. Fewer
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


def parse_stream(payload: dict, requested_symbol: str, *, now=None) -> dict:
    """Validate an issuer stream and count unique observations in fixed windows.

    ``messages`` and ``page_size`` are raw page sizes, NEVER attention rates.
    ``msgs_24h`` / ``msgs_7d`` count dated, unique messages at or before the
    aware observation clock, including the window's lower boundary. A window
    containing every accepted message is censored: its count is a lower bound,
    not total traffic. Invalid, duplicate, future and older rows remain counted
    separately. Bullish/bearish are author tags in the valid 24-hour window.
    No timezone, issuer identity or missing observation is guessed.
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
    now = now or dt.datetime.now(dt.timezone.utc)
    if now.tzinfo is None or now.utcoffset() is None:
        raise StreamContractError("aware observation clock required")
    start = now - dt.timedelta(hours=24)
    messages = payload.get("messages")
    if not isinstance(messages, list):
        raise StreamContractError("messages must be a list")
    bullish = bearish = rejects = old = future = duplicate = 0
    seen, stamps = set(), []
    for m in messages:
        if not isinstance(m, dict):
            rejects += 1
            continue
        try:
            ts = dt.datetime.fromisoformat(str(m.get("created_at")).replace("Z", "+00:00"))
            if ts.tzinfo is None or ts.utcoffset() is None or type(m.get("id")) is not int:
                raise ValueError("aware timestamp and integer message id required")
        except (ValueError, TypeError):
            rejects += 1
            continue
        if m["id"] in seen:
            duplicate += 1
            continue
        seen.add(m["id"])
        if ts > now:
            future += 1
            continue
        stamps.append(ts)
        if ts < start:
            old += 1
            continue
        basic = ((m.get("entities") or {}).get("sentiment") or {}).get("basic")
        bullish += basic == "Bullish"
        bearish += basic == "Bearish"
    windows = {}
    for label, hours in (("24h", 24), ("7d", 168)):
        n = sum(ts >= now - dt.timedelta(hours=hours) for ts in stamps)
        windows["msgs_" + label] = n
        windows["censored_" + label] = bool(stamps) and n == len(stamps)
    return {"us": requested_symbol, "symbol_title": sym.get("title"),
            "messages": len(messages), "page_size": len(messages),
            "raw_messages": len(messages), "bullish": bullish, "bearish": bearish,
            "max_message_ts": max(stamps).isoformat() if stamps else None,
            "min_message_ts": min(stamps).isoformat() if stamps else None,
            "rejected_messages": rejects, "older_messages": old,
            "future_messages": future, "duplicate_messages": duplicate,
            "window_start": start.isoformat(), "window_end": now.isoformat(),
            "count_basis": "unique observed messages; capped stream, not total traffic",
            **windows}


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
    injected_clock = now is not None
    now = now or dt.datetime.now(dt.timezone.utc)
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError('aware collection clock required')
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
                    parsed = parse_stream(payload, us, now=now)
                    entry.update(parsed)
                    if verify_mapping(tsx, parsed["symbol_title"]):
                        entry["status"] = "OK"
                        counts["ok"] += 1
                    else:
                        # The stream is another company's attention. Null the
                        # counts: under the TSX name they are UNKNOWN, not data.
                        entry.update(status="UNMAPPED", messages=None,
                                     msgs_24h=None, msgs_7d=None,
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
    completed_at = now if injected_clock else dt.datetime.now(dt.timezone.utc)
    return {"schema_version":2, "date": now.astimezone(ZoneInfo('America/New_York')).date().isoformat(),
            "collected_at": now.isoformat(),
            'completed_at':completed_at.isoformat(),
            'trends_qualification':'Unverified search terms; not authenticated issuer sentiment.',
            "source": "stocktwits+google_trends(unofficial)",
            "registration": "PREREGISTER_day94.md",
            "names": names, "trends": trends,
            **decision_usability(completed_at),
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
    if collected_at.tzinfo is None or collected_at.utcoffset() is None:
        raise ValueError("aware completion timestamp required")
    et = collected_at.astimezone(ZoneInfo("America/New_York"))
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
    """Atomic first-write publication; a rerun cannot overwrite observations."""
    session = dt.date.fromisoformat(snapshot['date']).isoformat()
    os.makedirs(outdir, exist_ok=True)
    path = os.path.join(outdir, f"{session}.json")
    fd, tmp = tempfile.mkstemp(dir=outdir, prefix=".social-", suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(snapshot, f, indent=2, sort_keys=True)
        # link is atomic and fails if the dated observation already exists.
        os.link(tmp, path)
        os.unlink(tmp)
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
    Reads msgs_24h, never raw page size. Censored counts are lower bounds.
    Day95 additionally requires 20 OK sessions per usable name and verifies
    dated pre-open exchange sessions; duplicates/late files do not add evidence.
    """
    import pandas_market_calendars as mcal
    per_name: dict = {}
    qualified = []
    rejected = []
    seen = set()
    for snap in snapshots:
        try:
            date = dt.date.fromisoformat(snap['date'])
            if date in seen:
                raise ValueError('duplicate dated snapshot')
            seen.add(date)
            start = dt.datetime.fromisoformat(snap['collected_at'])
            end = dt.datetime.fromisoformat(snap['completed_at'])
            if any(t.tzinfo is None or t.utcoffset() is None for t in (start,end)):
                raise ValueError('naive collection timestamp')
            et = ZoneInfo('America/New_York')
            start, end = start.astimezone(et), end.astimezone(et)
            if (snap.get('schema_version') != 2 or start.date() != date or end.date() != date
                    or end < start or end.time() >= dt.time(9,30)):
                raise ValueError('not a certified pre-open observation')
            if mcal.get_calendar('TSX').schedule(start_date=date,end_date=date).empty:
                raise ValueError('not a TSX session')
            qualified.append(snap)
        except (KeyError, TypeError, ValueError) as exc:
            rejected.append(dict(date=snap.get('date'), error=str(exc)))
    for snap in qualified:
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
                      "usable": bool(rec['ok_sessions'] >= min_sessions and med is not None and med >= min_median)}
    usable = sum(1 for n in names.values() if n["usable"])
    sessions = len(qualified)
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
            'rejected_snapshots':rejected,
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
