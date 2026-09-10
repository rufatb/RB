"""SMTP acceptance ambiguity, dedupe and late-report labeling."""
import datetime as dt
import pytest
import brief
import deliver_report as D
from report_store import Store
from test_daily_pipeline import NOW,services


class SMTP:
    sent=[]
    fail=False
    def __init__(self,*a,**k):pass
    def __enter__(self):return self
    def __exit__(self,*a):pass
    def login(self,*a):pass
    def send_message(self,msg):
        self.sent.append(msg)
        if self.fail:raise TimeoutError('ambiguous')
        return {}


def fixture(tmp_path,monkeypatch):
    store=Store(tmp_path)
    store.publish(NOW.date().isoformat(),brief.compute(now=NOW,services=services()))
    monkeypatch.setenv('RB_SMTP_USER','sender@example.org')
    monkeypatch.setenv('RB_SMTP_PASSWORD','test-only')
    SMTP.sent=[];SMTP.fail=False
    return store


def test_one_message_for_repeated_delivery(tmp_path,monkeypatch):
    store=fixture(tmp_path,monkeypatch)
    for _ in range(2):D.send(store,'2026-09-08','sender@example.org','recipient@example.org',smtp_factory=SMTP,now=NOW)
    assert len(SMTP.sent)==1 and store.delivery('2026-09-08')['state']=='sent'
    msg=SMTP.sent[0]
    assert len(msg.get_payload())==2
    assert 'Part 1' in msg.get_body(preferencelist=('plain',)).get_content()
    assert 'Part 2' in msg.get_body(preferencelist=('html',)).get_content()


def test_ambiguous_send_is_not_blindly_retried(tmp_path,monkeypatch):
    store=fixture(tmp_path,monkeypatch);SMTP.fail=True
    with pytest.raises(RuntimeError,match='ambiguous'):
        D.send(store,'2026-09-08','s@e.org','r@e.org',smtp_factory=SMTP,now=NOW)
    SMTP.fail=False
    D.send(store,'2026-09-08','s@e.org','r@e.org',smtp_factory=SMTP,now=NOW)
    assert len(SMTP.sent)==1 and store.delivery('2026-09-08')['state']=='unknown'


def test_late_delivery_is_informational_without_mutating_frozen_report(tmp_path,monkeypatch):
    store=fixture(tmp_path,monkeypatch)
    original=store.get('2026-09-08')
    D.send(store,'2026-09-08','s@e.org','r@e.org',smtp_factory=SMTP,now=NOW+dt.timedelta(minutes=30))
    assert 'INFORMATIONAL' in str(SMTP.sent[0]['Subject'])
    assert store.get('2026-09-08')==original


def test_missing_credentials_does_not_claim_a_delivery(tmp_path,monkeypatch):
    store=fixture(tmp_path,monkeypatch);monkeypatch.delenv('RB_SMTP_PASSWORD')
    with pytest.raises(ValueError,match='missing'):
        D.send(store,'2026-09-08','s@e.org','r@e.org',smtp_factory=SMTP,now=NOW)
    assert store.delivery('2026-09-08') is None


# ── day-94: an ABSTAIN table must not read as an order sheet ───────────────

def test_all_abstaining_legs_lead_with_do_not_trade():
    """2026-09-09 COST REAL MONEY HERE. All four legs ABSTAINED (the quote
    endpoint returned HTTP 406 all session, so no spread could be priced), and
    the table still led with name, side, dollar allocation and share count with
    ABSTAIN as the last column under a heading reading "shadow tracking". It
    was read as an order sheet and traded; three of the four went the wrong way.
    """
    import daily_render as R
    legs = [{"ticker": t, "status": "ABSTAIN"}
            for t in ("TRP.TO", "ENB.TO", "BCE.TO", "SLF.TO")]
    head = "\n".join(R._leg_heading({"legs": legs}))
    assert "DO NOT TRADE" in head
    assert "every leg below ABSTAINED" in head
    assert "not a recommendation" in head


def test_a_partial_abstention_names_which_legs():
    import daily_render as R
    legs = [{"ticker": "TRP.TO", "status": "SHADOW"},
            {"ticker": "ENB.TO", "status": "ABSTAIN"}]
    head = "\n".join(R._leg_heading({"legs": legs}))
    assert "1 of 2 legs ABSTAINED" in head
    assert "ENB.TO" in head and "TRP.TO" not in head


def test_clean_legs_still_say_they_are_not_orders():
    import daily_render as R
    legs = [{"ticker": "TRP.TO", "status": "SHADOW"}]
    head = "\n".join(R._leg_heading({"legs": legs}))
    assert "not orders" in head
    assert "coin flip" in head


def test_the_warning_precedes_any_ticker_in_the_rendered_page():
    """A status in the right-hand column is not a guardrail. The consequence
    has to appear before the first name, side or dollar figure."""
    import daily_render as R
    legs = [{"ticker": t, "status": "ABSTAIN"} for t in ("TRP.TO", "ENB.TO")]
    head = "\n".join(R._leg_heading({"legs": legs}))
    assert "DO NOT TRADE" in head.splitlines()[0]


# ── day-94: the day's shape and the book's concentration reach the page ────

def test_the_expected_bad_day_frequency_is_on_the_page():
    """A binomial illustration must disclose its unverified independence assumption."""
    import ledger
    lines = ledger.day_shape_line(51, 107, 4)
    assert lines
    joined = " ".join(lines)
    assert "1-or-fewer hits" in joined
    assert "one in 2.9" in joined
    assert "not a forecast" in joined
    assert 'Assumes independent legs' in joined


def test_a_single_leg_day_says_nothing_about_shape():
    import ledger
    assert ledger.day_shape_line(51, 107, 1) == []
    assert ledger.day_shape_line(0, 0, 4) == []


def test_the_distribution_sums_to_one():
    import ledger
    d = ledger.day_shape(51, 107, 4)
    assert abs(sum(d["dist"]) - 1.0) < 1e-12


def test_two_same_sector_legs_on_one_side_are_disclosed():
    """THE GAP THAT COST THE DAY. sector_warning fires on a fully-aligned
    group or 4+ same-group picks; TRP and ENB were 2 of 5 energy names, both
    long, both sized, and neither condition fired."""
    import r945
    groups = {"energy": ["CNQ.TO", "SU.TO", "CVE.TO", "ENB.TO", "TRP.TO"]}
    legs = [{"t": "TRP.TO", "side_hint": "LONG"},
            {"t": "ENB.TO", "side_hint": "LONG"}]
    w = r945.book_concentration(legs, groups)
    assert len(w) == 1
    assert "BOTH LONG legs are energy" in w[0]
    assert "one bet, not two" in w[0]  # legacy text; daily report uses risk_evidence


def test_the_disclosure_states_that_the_gate_was_tested_and_refused():
    """Day-34 rejection #23. Without this the next reader re-litigates it."""
    import r945
    groups = {"energy": ["ENB.TO", "TRP.TO"]}
    w = r945.book_concentration([{"t": "TRP.TO", "side_hint": "LONG"},
                                 {"t": "ENB.TO", "side_hint": "LONG"}], groups)
    assert "0.517" in w[0] and "disclosure, not a rule" in w[0]


def test_a_diversified_book_triggers_nothing():
    import r945
    groups = {"energy": ["TRP.TO"], "financials": ["RY.TO"]}
    assert r945.book_concentration(
        [{"t": "TRP.TO", "side_hint": "LONG"},
         {"t": "RY.TO", "side_hint": "LONG"}], groups) == []


def test_opposite_sides_in_one_sector_are_not_concentration():
    """Opposite sides are not the same-direction concentration this helper counts.

    This does not establish an effective hedge or remove residual risk.
    """
    import r945
    groups = {"energy": ["ENB.TO", "TRP.TO"]}
    assert r945.book_concentration(
        [{"t": "TRP.TO", "side_hint": "LONG"},
         {"t": "ENB.TO", "side_hint": "SHORT"}], groups) == []
