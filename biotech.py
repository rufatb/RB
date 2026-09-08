"""Independent factual biotech monitor; no intraday imports or trade calls.

Rank ALL US-listed Biotechnology common equities by trailing 20 completed
sessions' average share volume, then intersect top 100 with cap < USD500m.
A partial universe cannot certify a top-100 rank. Crowding is a tri-state
2-of-3 rule: unknown evidence can never be silently counted as false.
Thresholds describe expectations, not probabilities of clinical success.
"""
from __future__ import annotations
import calendar
import datetime as dt
import hashlib
import json
from pathlib import Path
from zoneinfo import ZoneInfo
from urllib.parse import urlparse
import numpy as np
from quotes import number, stamp, fresh

KINDS = {"topline", "interim", "conference", "PDUFA", "AdCom", "CRL", "financing"}
# US venues, including OTC microcaps; a major-exchange-only screen would change
# the top-100 ADV intersection requested by the user.
US_EXCHANGES = {"NMS", "NGM", "NCM", "NYQ", "ASE", "OEM", "OQB", "OQX",
                "NAE", "CXI", "PNK", "PCX", "YHD", "BTS", "NASDAQ", "NYSE",
                "NYSEAMERICAN", "OTC", "OTCQB", "OTCQX", "OTCEM", "PINKSHEETS"}
LABELS = ["Event & Date Window", "Asset/Indication/Stage", "New Information vs. Known Data",
          "3–6 Month Read-throughs", "Objective Expectation Indicators"]


def six_months(day):
    month = day.month - 1 + 6
    year, month = day.year + month // 12, month % 12 + 1
    return dt.date(year, month, min(day.day, calendar.monthrange(year, month)[1]))


def history_metrics(bars, today):
    """Daily observations only; ADV excludes today's incomplete session.

    Require a contiguous sequence of recent exchange sessions in the builder;
    independently reject duplicates, future dates, invalid prices and volumes.
    Split-adjusted closes are required for return/RV comparisons.
    """
    if any(dt.date.fromisoformat(b['date']) > today for b in bars):
        raise ValueError('future daily observation')
    completed = [b for b in bars if dt.date.fromisoformat(b["date"]) < today]
    dates = [b["date"] for b in completed]
    if dates != sorted(set(dates)) or len(dates) < 20:
        raise ValueError("need >=20 unique ordered completed daily bars")
    if (today-dt.date.fromisoformat(dates[-1])).days > 4:
        raise ValueError("daily volume history is stale")
    if len(dates) > 1 and np.median(np.diff([dt.date.fromisoformat(d).toordinal() for d in dates])) > 2:
        raise ValueError("bars are not daily")
    volumes = [number(b.get("volume")) for b in completed]
    closes = [number(b.get("adjusted_close"), positive=True) for b in completed]
    if any(v is None or v < 0 for v in volumes) or any(p is None for p in closes):
        raise ValueError("invalid volume or split-adjusted price")
    m = {"adv20": float(np.mean(volumes[-20:])), "r21": None, "r63": None,
         "rv_ratio": None, "repricing": None, "history_end": dates[-1]}
    if len(closes) >= 64:
        returns = np.diff(np.log(closes))
        old = float(np.std(returns[-60:-20], ddof=1))
        recent = float(np.std(returns[-20:], ddof=1))
        m.update(r21=closes[-1]/closes[-22]-1, r63=closes[-1]/closes[-64]-1)
        if old > 0:
            m["rv_ratio"] = recent/old
            m["repricing"] = bool((abs(m["r21"]) >= .30 or abs(m["r63"]) >= .60)
                                    and m["rv_ratio"] >= 1.5)
        elif recent == 0:
            m.update(rv_ratio=1.0, repricing=False)
    return m


def select_universe(snapshot, now):
    """Intersection, not top-100 AFTER selecting microcaps. No partial ranking."""
    if not snapshot.get("universe_complete"):
        raise ValueError("universe coverage incomplete; top-100 rank cannot be certified: " + "; ".join(snapshot.get("errors", [])))
    if not fresh(snapshot.get("as_of"), now, 36*3600):
        raise ValueError("universe snapshot missing, stale or future")
    securities = snapshot.get("securities", [])
    if not securities or len(securities) != snapshot.get("universe_count"):
        raise ValueError("universe count mismatch or empty universe")
    seen, rows = set(), []
    for s in securities:
        t = s["ticker"]
        if t in seen:
            raise ValueError("duplicate security " + t)
        seen.add(t)
        if s.get("industry") != "Biotechnology" or s.get("exchange") not in US_EXCHANGES:
            raise ValueError("unverified US Biotechnology membership: " + t)
        if s.get("security_type") not in {"COMMON", "ADR"} or s.get("currency") != "USD":
            raise ValueError("unverified equity type or USD cap: " + t)
        cap = number(s.get("market_cap"), positive=True)
        if cap is None or not fresh(s.get("market_cap_asof"), now, 36*3600):
            raise ValueError("missing/stale USD market cap: " + t)
        m = history_metrics(s.get("daily_bars", []), stamp(now).astimezone(ZoneInfo('America/New_York')).date())
        if m["adv20"] <= 0:
            raise ValueError("no measurable liquidity: " + t)
        rows.append({**s, **m})
    rows.sort(key=lambda s: (-s["adv20"], s["ticker"]))
    return [{**s, "liquidity_rank": i+1} for i, s in enumerate(rows[:100])
            if s["market_cap"] < 500_000_000]


def evidence_url(url):
    p = urlparse(str(url))
    return p.scheme == "https" and bool(p.hostname) and not p.username and not p.password


def validate_event(event, now):
    """Require an issuer/FDA/conference source and reviewed event-specific facts.

    Trial administrative completion dates and keyword-only search hits are not
    verified readout dates. Auto-discovered candidates stay in a review queue.
    """
    if event.get("kind") not in KINDS or event.get("status") != "scheduled":
        raise ValueError("not an eligible scheduled catalyst")
    start, end = (dt.date.fromisoformat(event[k]) for k in ("window_start", "window_end"))
    today = stamp(now).astimezone(ZoneInfo('America/New_York')).date()
    if start > end or end < today or start > six_months(today) or end > six_months(today):
        raise ValueError("event window outside 0–6 calendar months or unresolved past date")
    if not fresh(event.get("verified_at"), now, 7*86400):
        raise ValueError("event evidence needs re-verification (maximum 7 days)")
    if stamp(event["announced_at"]) > stamp(now):
        raise ValueError("future announcement cannot be known at snapshot time")
    if event.get("date_basis") not in {"issuer_guidance", "FDA", "conference_program", "financing_terms"}:
        raise ValueError("administrative trial date or unverified date basis")
    if not evidence_url(event.get("source_url")):
        raise ValueError("missing primary source URL")
    if event.get("source_type") not in {"issuer", "SEC", "FDA", "conference"}:
        raise ValueError("primary-source verification required")
    host=urlparse(event['source_url']).hostname
    authority={'SEC':'sec.gov','FDA':'fda.gov'}.get(event['source_type'])
    if authority and host != authority and not host.endswith('.'+authority):
        raise ValueError('primary-source type does not match authority domain')
    if event.get("review_status") != "verified":
        raise ValueError("discovered candidate has not been evidence-reviewed")
    if event.get('kind') == 'CRL':
        if dt.date.fromisoformat(event.get('crl_issued_on','')) > today:
            raise ValueError('CRL must already be disclosed; never predict an FDA rejection')
    required = ("event_id", "ticker", "asset", "indication", "stage", "new_information", "known_data", "read_throughs")
    if any(not isinstance(event.get(k), str) or not event[k].strip() for k in required):
        raise ValueError("missing event-specific evidence fields")
    return event


def positioning(s, now):
    """Elevated SI OR borrow is one flag, never two votes toward crowding."""
    flags, notes = [], []
    for field, when, threshold, age, label in [
        ("short_float", "short_asof", .20, 35*86400, "short/float"),
        ("borrow_apr", "borrow_asof", .20, 24*3600, "borrow APR")]:
        v = number(s.get(field))
        if v is not None and v >= 0 and fresh(s.get(when), now, age):
            flags.append(v >= threshold)
            notes.append(f"{label} {v:.1%} ({str(s[when])[:10]})")
        else:
            flags.append(None)
            notes.append(f"{label} unknown")
    flag = True if True in flags else (False if all(v is False for v in flags) else None)
    return flag, "; ".join(notes)


def crowding(flags):
    """Monitor only if even unknown flags cannot bring the count to two."""
    yes = sum(v is True for v in flags)
    unknown = sum(v is None for v in flags)
    if yes >= 2:
        return "Crowded / High-Expectations"
    if yes + unknown >= 2:
        return "Insufficient evidence"
    return "Monitor"


def option_percentile(option, peers, now):
    """Top-quintile IV in a comparable time-to-expiry cohort, minimum 20 names.

    Event moves across different tenors are not directly compared. This engine
    uses annualized ATM IV, within <=30 / 31–90 / 91–190 DTE buckets. A small
    or missing cohort produces UNKNOWN, never an invented percentile.
    """
    def good(o):
        return (o.get("status") == "OK" and number(o.get("iv"), positive=True) is not None
                and fresh(o.get("as_of"), now, 120) and o.get("expiry")
                and 0 < (dt.date.fromisoformat(o['expiry'])-stamp(now).astimezone(ZoneInfo('America/New_York')).date()).days <= 190)
    def bucket(o):
        d = (dt.date.fromisoformat(o["expiry"])-stamp(now).astimezone(ZoneInfo('America/New_York')).date()).days
        return 0 if d <= 30 else 1 if d <= 90 else 2
    if not good(option):
        return None, 0
    values = {p["ticker"]: p["iv"] for p in peers if good(p) and bucket(p) == bucket(option)}
    if len(values) < 20:
        return None, len(values)
    # Midrank handles ties without declaring an entirely flat cohort crowded.
    pct = (sum(x < option["iv"] for x in values.values()) +
           .5*sum(x == option["iv"] for x in values.values())) / len(values)
    return pct, len(values)


def scan(snapshot, events, options, now):
    """Pure scan; no data acquisition, advice, prices targets or side calls."""
    out = {"status": "OK", "monitor": [], "crowded": [], "unverified": [],
           "errors": [], "universe_n": 0, "screened_events": 0, "top_limit": 2}
    try:
        universe = {s["ticker"]: s for s in select_universe(snapshot, now)}
    except (ValueError, KeyError, TypeError) as exc:
        out.update(status="UNAVAILABLE", errors=[str(exc)])
        return out
    out["universe_n"] = len(universe)
    if not events:
        out.update(status='NO VERIFIED EVENT FEED', errors=['No evidence-reviewed events supplied; this does not establish absence of upcoming catalysts.'])
        return out
    from collections import Counter
    identities = Counter(e.get("event_id") for e in events)
    seen = set()
    for e in events:
        t = e.get("ticker")
        if t not in universe:
            continue
        try:
            validate_event(e, now)
            if identities[e["event_id"]] > 1:
                raise ValueError("duplicate event identity; reconcile revised dates")
            seen.add(e["event_id"])
        except (ValueError, KeyError, TypeError) as exc:
            out["unverified"].append({"ticker": t, "reason": str(exc)})
            continue
        s = universe[t]
        opt = options.get(e["event_id"], {})
        percentile, peer_n = option_percentile(opt, list(options.values()), now)
        pos_flag, pos_note = positioning(s, now)
        flags = [None if percentile is None else percentile >= .80, pos_flag, s["repricing"]]
        label = crowding(flags)
        def fmt(v, spec):
            return format(v, spec) if v is not None else "unknown"
        indicators = (f"Cap ${s['market_cap']/1e6:.1f}M; ADV20 {s['adv20']:,.0f} shares "
                      f"(liquidity rank {s['liquidity_rank']}); IV percentile {fmt(percentile, '.0%')} "
                      f"({peer_n} comparable names); {pos_note}; 1m/3m return "
                      f"{fmt(s['r21'], '+.1%')}/{fmt(s['r63'], '+.1%')}; RV ratio "
                      f"{fmt(s['rv_ratio'], '.2f')}; crowding flags {sum(v is True for v in flags)}/3, "
                      f"unknown {sum(v is None for v in flags)}.")
        row = {"ticker": t, "event_id": e["event_id"], "status": label,
               "flags": flags, "window_end": e["window_end"], "adv20": s["adv20"],
               "source_url": e["source_url"], "bullets": [
                   f"{e['kind']} — {e['window_start']} to {e['window_end']} ({e['date_basis']}).",
                   f"{e['asset']} / {e['indication']} / {e['stage']}.",
                   f"New: {e['new_information']} Known: {e['known_data']}",
                   e["read_throughs"], indicators]}
        out["screened_events"] += 1
        if label == "Monitor":
            out["monitor"].append(row)
        elif label.startswith("Crowded"):
            out["crowded"].append(row)
        else:
            out["unverified"].append({"ticker": t, "reason": indicators})
    # Deterministic priority: fewer crowding flags, nearer window, liquidity.
    # No directional or success-probability ranking. Max one event per issuer.
    ranked = sorted(out["monitor"], key=lambda r: (sum(v is True for v in r["flags"]),
                                                  r["window_end"], -r["adv20"], r["ticker"]))
    picked, tickers = [], set()
    for r in ranked:
        if r["ticker"] not in tickers and len(picked) < 2:
            picked.append(r); tickers.add(r["ticker"])
    out["monitor"] = picked
    return out


def load_inputs(snapshot_path=None, events_path=None):
    """Read explicit snapshots; absence is raised and displayed by brief.compute."""
    import os
    snapshot_path=snapshot_path or os.getenv('RB_BIOTECH_SNAPSHOT_JSON','data/biotech_snapshot.json')
    events_path=events_path or os.getenv('RB_BIOTECH_EVENTS_JSON','data/biotech_events.json')
    return json.loads(Path(snapshot_path).read_text()), json.loads(Path(events_path).read_text())["events"]


def render(result):
    """Exactly five bullets per Monitor event; crowded appendix never promotes."""
    lines = ["## Part 2 — Small-Cap Biotech Catalyst Watch (3–6 months)",
             "Factual monitoring only. Upcoming events cover 0–6 calendar months."]
    if result["errors"]:
        lines += ["Data unavailable: " + "; ".join(result["errors"])]
    lines.append(f"Verified universe: {result['universe_n']} names; Monitor: {len(result['monitor'])}/2.")
    if not result["monitor"]:
        lines.append("No verified uncrowded setup passes today. No filler picks.")
    for r in result["monitor"]:
        lines += ["", f"### {r['ticker']} — Monitor", ""]
        for i, (label, value) in enumerate(zip(LABELS, r["bullets"])):
            source = f" [Primary source]({r['source_url']})" if i == 0 else ""
            lines.append(f"- **{label}:** {value}{source}")
    lines += ["", "### Crowded / High-Expectations", ""]
    lines += [f"{r['ticker']}: {r['bullets'][4]}" for r in result["crowded"]] or ["None verified."]
    if result["unverified"]:
        lines += ["", "Evidence gaps: " + " | ".join(f"{r['ticker']}: {r['reason']}" for r in result["unverified"])]
    return "\n".join(lines)
