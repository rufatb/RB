"""Day-94 Arm A (build_social.py): fixture-based, no network.

The collector is fail-closed: errors are recorded by class and never become
zero attention, mappings are verified against the returned symbol title, and
the coverage gate is arithmetic over accumulated snapshots only.
"""
import datetime as dt
import json
import os

from zoneinfo import ZoneInfo

import pytest
import requests

import build_social as S
NOW = dt.datetime.fromisoformat('2026-09-09T09:20:00-04:00')


def sessions(n):
    import pandas_market_calendars as mcal
    return [str(d.date()) for d in mcal.get_calendar('TSX').schedule(
        start_date='2026-08-01', end_date='2026-09-08').index[:n]]


def stream(symbol="RY", title="Royal Bank of Canada", messages=None):
    return {"response": {"status": 200},
            "symbol": {"id": 1, "symbol": symbol, "title": title},
            "messages": messages if messages is not None else [
                {"id": 1, "body": "long", "created_at": "2026-09-08T13:31:00Z",
                 "entities": {"sentiment": {"basic": "Bullish"}}},
                {"id": 2, "body": "short", "created_at": "2026-09-08T14:05:00Z",
                 "entities": {"sentiment": {"basic": "Bearish"}}},
                {"id": 3, "body": "untagged", "created_at": "2026-09-08T19:59:00Z",
                 "entities": {"sentiment": None}},
                {"id": 4, "body": "no entities", "created_at": "2026-09-08T20:15:00Z"}]}


class FakeResponse:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


class FakeSession:
    """Serves a fixed stream per symbol; any other use is a test bug."""
    def __init__(self, by_symbol=None, error=None):
        self.by_symbol = by_symbol or {}
        self.error = error
        self.calls = []

    def get(self, url, headers=None, timeout=None, params=None):
        self.calls.append(url)
        if self.error is not None:
            raise self.error
        symbol = url.rsplit("/", 1)[-1].replace(".json", "")
        return FakeResponse(self.by_symbol[symbol])


def cfg_two_names():
    return {"ticker": "AC.TO", "scan": {"universe": ["T.TO"]},
            "social": {"enabled": True, "request_delay_sec": 0,
                       "retries": 1, "timeout_sec": 1,
                       "us_symbol_map": {"T.TO": "T", "AC.TO": "ACDVF"}}}


def test_parse_stream_counts_sentiment_and_max_ts():
    out = S.parse_stream(stream(), "RY", now=NOW)
    assert out["messages"] == 4 and out["bullish"] == 1 and out["bearish"] == 1
    assert out["max_message_ts"] == "2026-09-08T20:15:00+00:00"
    assert out["rejected_messages"] == 0
    assert out["symbol_title"] == "Royal Bank of Canada"


def test_parse_stream_rejects_bad_timestamps_before_counting_sentiment():
    s = stream(messages=[{"id": 1, "created_at": "not-a-date",
                          "entities": {"sentiment": {"basic": "Bullish"}}},
                         {"id": 2, "created_at": "2026-09-08T10:00:00Z"}])
    out = S.parse_stream(s, "RY", now=NOW)
    assert out["msgs_24h"] == 0 and out["messages"] == 2 and out["bullish"] == 0
    assert out["rejected_messages"] == 1
    assert out["max_message_ts"] == "2026-09-08T10:00:00+00:00" and out["older_messages"] == 1


def test_parse_stream_asserts_the_response_is_for_the_requested_symbol():
    with pytest.raises(S.StreamContractError):
        S.parse_stream(stream(symbol="TD", title="Toronto-Dominion Bank"), "RY")


def test_mapping_mismatch_is_unmapped_never_guessed():
    # T.TO -> T is AT&T's stream; the title does not authenticate TELUS.
    sess = FakeSession({"T": stream(symbol="T", title="AT&T Inc."),
                        "ACDVF": stream(symbol="ACDVF", title="Air Canada")})
    snap = S.collect(cfg_two_names(), session=sess,
                     trends_session=FakeSession(error=requests.ConnectionError()))
    assert snap["names"]["T.TO"]["status"] == "UNMAPPED"
    assert "AT&T" in snap["names"]["T.TO"]["error"]
    assert snap["names"]["T.TO"]["messages"] is None  # unknown, never zero
    assert snap["names"]["AC.TO"]["status"] == "OK"
    assert snap["coverage"]["unmapped"] == 1 and snap["coverage"]["ok"] == 1
    assert snap["trends"]["status"] == "ERROR"  # recorded, collection continued


def test_failed_fetch_is_recorded_by_class_and_is_not_zero_attention():
    sess = FakeSession(error=requests.ConnectionError("refused"))
    snap = S.collect(cfg_two_names(), session=sess,
                     trends_session=FakeSession(error=requests.Timeout()))
    for name in ("T.TO", "AC.TO"):
        e = snap["names"][name]
        assert e["status"] == "ERROR" and e["messages"] is None
        assert e["error"].startswith("CONNECTION")
    assert snap["coverage"]["error"] == 2 and snap["coverage"]["ok"] == 0


def test_http_error_records_status_class():
    sess = FakeSession()
    r = requests.Response(); r.status_code = 403
    sess.error = requests.HTTPError(response=r)
    payload, err = S.fetch_stream("RY", tries=1, session=sess)
    assert payload is None and err.startswith("HTTP_403")


def test_snapshot_write_is_atomic_and_dated(tmp_path):
    snap = {"date": "2026-09-08", "names": {}, "coverage": {}}
    path = S.write_snapshot(snap, str(tmp_path))
    assert path.endswith(os.path.join("data" if False else "", "")[1:] + "2026-09-08.json")
    with open(path) as f:
        assert json.load(f)["date"] == "2026-09-08"
    leftovers = [p for p in os.listdir(tmp_path) if p.endswith(".tmp")]
    assert leftovers == []


def snapshot(date, counts):
    """counts: {tsx: message count}; every entry OK."""
    return {"schema_version":2, "date": date,
            'collected_at':date+'T09:20:00-04:00',
            'completed_at':date+'T09:20:01-04:00', "names": {
        t: {"status": "OK", "messages": 30, "page_size": 30,
            "msgs_24h": n, "censored_24h": False} for t, n in counts.items()}}


def test_coverage_gate_arithmetic_7_fails_8_passes():
    names21 = [f"N{i:02d}.TO" for i in range(21)]
    days = sessions(20)
    counts7 = {t: (3 if i < 7 else 0) for i, t in enumerate(names21)}
    counts8 = {t: (3 if i < 8 else 0) for i, t in enumerate(names21)}
    gate7 = S.coverage_gate([snapshot(d, counts7) for d in days])
    gate8 = S.coverage_gate([snapshot(d, counts8) for d in days])
    assert gate7["sessions_collected"] == 20
    assert gate7["usable_names"] == 7 and gate7["gate"] == "UNRUNNABLE_FOR_UNIVERSE"
    assert gate8["usable_names"] == 8 and gate8["gate"] == "PASS"


def test_coverage_gate_excludes_failed_fetches_from_medians():
    days = sessions(20)
    snaps = []
    for d in days:
        snap = snapshot(d, {'RY.TO':5})
        snap['names']['TD.TO'] = {'status':'ERROR','messages':None}
        snaps.append(snap)
    gate = S.coverage_gate(snaps)
    assert gate["names"]["RY.TO"]["median_messages_per_day"] == 5.0
    assert gate["names"]["TD.TO"]["ok_sessions"] == 0
    assert gate["names"]["TD.TO"]["usable"] is False


def test_empty_snapshot_dir_is_collecting_not_a_crash(tmp_path):
    gate = S.coverage_gate(S.load_snapshots(str(tmp_path)))
    assert gate["sessions_collected"] == 0
    assert gate["gate"] == "COLLECTING" and gate["usable_names"] == 0


def test_gate_not_decidable_before_20_sessions():
    snaps = [snapshot(d, {"RY.TO": 9}) for d in sessions(7)]
    gate = S.coverage_gate(snaps)
    assert gate["sessions_collected"] == 7 and gate["gate"] == "COLLECTING"


# ── day-94 live-run correction: the page size is not the traffic ────────────

def _msg(ts, sentiment=None):
    ent = {"sentiment": {"basic": sentiment}} if sentiment else {}
    return {"created_at": ts, "entities": ent}


def _page(stamps):
    return {"response": {"status": 200},
            "symbol": {"symbol": "RY", "title": "Royal Bank of Canada"},
            "messages": [dict(_msg(t), id=i) for i, t in enumerate(stamps)]}


WINDOW_NOW = dt.datetime(2026, 9, 10, 12, 0, tzinfo=dt.timezone.utc)


def test_two_names_with_identical_page_sizes_have_different_attention():
    """THE CASE THIS EXISTS FOR. On the first live run all 18 mappable names
    returned exactly 30 -- the page size -- while ENB's newest message was
    hours old and SLF's was 23 DAYS old. Stored as `messages` both were 30,
    so the registered feature would have had zero variance and 120 sessions
    of collection would have produced a null about a constant."""
    busy = _page([(WINDOW_NOW - dt.timedelta(hours=h)).isoformat() for h in range(30)])
    quiet = _page([(WINDOW_NOW - dt.timedelta(days=23 + d)).isoformat() for d in range(30)])

    b = S.parse_stream(busy, "RY", now=WINDOW_NOW)
    q = S.parse_stream(quiet, "RY", now=WINDOW_NOW)

    assert b["messages"] == q["messages"] == 30      # the trap
    # 25, not 24: hours 0..24, and the message landing exactly ON the cutoff
    # is inside the window (`ts >= cutoff`). Stated rather than rounded off.
    assert b["msgs_24h"] == 25 and q["msgs_24h"] == 0   # the measurement
    assert b["msgs_7d"] == 30 and q["msgs_7d"] == 0


def test_a_page_that_runs_out_inside_the_window_is_flagged_not_guessed():
    """30 messages all inside 24h means the true count is >= 30, unknown-but-
    larger. Rule 2: say so and mark it, never store the lower bound as if it
    were the figure."""
    saturated = _page([(WINDOW_NOW - dt.timedelta(minutes=10 * i)).isoformat()
                       for i in range(30)])
    p = S.parse_stream(saturated, "RY", now=WINDOW_NOW)
    assert p["msgs_24h"] == 30
    assert p["censored_24h"] is True, "a saturated page must announce itself"

    roomy = _page([(WINDOW_NOW - dt.timedelta(hours=6)).isoformat(),
                   (WINDOW_NOW - dt.timedelta(days=4)).isoformat()])
    r = S.parse_stream(roomy, "RY", now=WINDOW_NOW)
    assert r["msgs_24h"] == 1 and r["censored_24h"] is False
    assert r["msgs_7d"] == 2 and r["censored_7d"] is True


def test_the_gate_reads_the_registered_quantity_not_the_page_size():
    """Rule 3: the bar did not move. GATE_MIN_MEDIAN is still 1.0 and
    GATE_MIN_NAMES still 8. The gate now reads "messages/day", which is what
    the registration always said -- and which the page size never was."""
    assert S.GATE_SESSIONS == 20
    assert S.GATE_MIN_NAMES == 8
    assert S.GATE_MIN_MEDIAN == 1.0

    days = sessions(20)
    silent = [snapshot(d, {"RY.TO": 0}) for d in days]
    gate = S.coverage_gate(silent)
    assert gate["names"]["RY.TO"]["median_messages_per_day"] == 0.0
    assert gate["names"]["RY.TO"]["usable"] is False, \
        "a name with no traffic must fail the gate even though its page is full"


def test_snapshots_written_before_the_fix_are_skipped_not_backfilled():
    """A pre-fix snapshot has only the page size. Reading 30 out of it would
    resurrect the exact defect being corrected, so those sessions are counted
    and excluded (rule 2: absence of the measurement is not a measurement)."""
    days = sessions(20)
    old = [snapshot(d, {"RY.TO": 0}) for d in days]
    for snap in old:
        del snap["names"]["RY.TO"]["msgs_24h"]
    gate = S.coverage_gate(old)
    n = gate["names"]["RY.TO"]
    assert n["pre_fix_sessions"] == 20 and n["ok_sessions"] == 0
    assert n["median_messages_per_day"] is None and n["usable"] is False


# ── the snapshot must not become a look-ahead feature by scheduling accident ─

def test_a_preopen_snapshot_is_knowable_at_the_decision():
    et = dt.datetime(2026, 9, 10, 9, 20, tzinfo=ZoneInfo("America/Toronto"))
    d = S.decision_usability(et)
    assert d["decision_usable"] is True
    assert "knowable at selection time" in d["decision_note"]


def test_a_snapshot_taken_after_0946_is_marked_unusable_as_a_feature():
    """The registration collects at 09:20 ET. Running the collector from the
    morning wrapper instead would put it at ~09:48 -- AFTER the board is
    selected -- so every row would carry the market's reaction to the open.
    That look-ahead would arrive disguised as a scheduling convenience, so
    the snapshot states the verdict rather than leaving it to be inferred."""
    et = dt.datetime(2026, 9, 10, 9, 48, tzinfo=ZoneInfo("America/Toronto"))
    d = S.decision_usability(et)
    assert d["decision_usable"] is False
    assert "MUST NOT be used as a feature" in d["decision_note"]
    assert "09:48" in d["decision_note"]


def test_the_boundary_minute_is_not_usable():
    """09:46 itself is the decision minute, not before it."""
    et = dt.datetime(2026, 9, 10, 9, 46, tzinfo=ZoneInfo("America/Toronto"))
    assert S.decision_usability(et)["decision_usable"] is False


def test_usability_is_judged_in_EASTERN_not_in_whatever_the_host_uses():
    """A UTC host would read 13:20 ET as an afternoon collection and mark a
    perfectly good pre-open snapshot unusable -- or worse, the reverse."""
    utc = dt.datetime(2026, 9, 10, 13, 20, tzinfo=dt.timezone.utc)  # 09:20 ET
    assert S.decision_usability(utc)["decision_usable"] is True
