"""The subject line is the only part of the report a phone shows at 09:46.

2026-09-09: every leg ABSTAINed on an integrity check and the body was fixed
the same day to say DO NOT TRADE. But the subject read
"RB Daily Report — 2026-09-09 — Intraday + Biotech", which is indistinguishable
from a tradeable morning, and that is the line that was actually read.
"""
import deliver_report as D


def rep(status="ON_TIME", legs=None, session="2026-09-10"):
    return {"session": session, "report_status": status,
            "intraday": {"legs": legs if legs is not None else []},
            "generated_at": "2026-09-10T09:46:00-04:00"}


def leg(status):
    return {"ticker": "RY.TO", "side": "SHORT", "status": status}


def test_all_legs_abstained_says_DO_NOT_TRADE_in_the_subject():
    s = D.subject_state(rep(legs=[leg("ABSTAIN")] * 4))
    assert "DO NOT TRADE" in s and "all 4 legs" in s


def test_a_tradeable_on_time_board_gets_no_warning_prefix():
    assert D.subject_state(rep(legs=[leg("SIZED"), leg("SIZED")])) == ""


def test_a_partial_abstention_is_flagged_but_not_as_a_full_stop():
    s = D.subject_state(rep(legs=[leg("ABSTAIN"), leg("SIZED")]))
    assert "1/2 legs ABSTAINED" in s
    assert "DO NOT TRADE" not in s


def test_no_legs_is_not_treated_as_all_clear():
    """Rule 2. An empty leg list means nothing was selected, which is also not
    a tradeable board — it must not render as an ordinary morning."""
    s = D.subject_state(rep(legs=[]))
    assert "NO LEGS SELECTED" in s


def test_a_data_outage_outranks_everything_else():
    s = D.subject_state(rep(status="DATA OUTAGE — informational only",
                            legs=[leg("SIZED")] * 4))
    assert "DATA OUTAGE" in s and "DO NOT TRADE" in s


def test_status_case_is_not_load_bearing():
    assert "DO NOT TRADE" in D.subject_state(rep(legs=[leg("abstain")]))


def test_the_prefix_reaches_the_real_subject_header():
    """Built on a REAL report, because message() renders the whole body and a
    hand-made dict does not exercise the path the scheduler takes. The offline
    report selects no legs, which is itself a state the subject must flag."""
    import brief
    r = brief.compute(no_net=True)
    msg = D.message(r, "a@b.com", "c@d.com")
    assert msg["Subject"].startswith(f"RB Daily Report — {r['session']} — ")
    assert "⛔" in msg["Subject"], "a board with no legs must be flagged"
    assert len(msg.get_body(("plain",)).get_content()) > 500


def test_an_informational_run_still_says_so_when_legs_are_fine():
    s = D.subject_state(rep(status="INFORMATIONAL — PARTIAL DATA",
                            legs=[leg("SIZED")]))
    assert s == "INFORMATIONAL — "
