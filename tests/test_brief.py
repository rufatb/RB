"""Day-58: the unified morning page.

The brief's value is that it can say "nothing to do" and that it never
presents a layer as stronger than its evidence. These lock both.
"""

import datetime as dt

import brief
import positions as P

TODAY = dt.date(2026, 8, 24)


def _book(marks):
    rows = P.open_position([], "ZYME", "LONG", 400, 24.90, "2026-08-19",
                           "catalyst", "close on PDUFA outcome",
                           event_date="2026-08-25", event_kind="PDUFA")
    return P.mark_book(rows, marks, TODAY)


def test_a_flat_book_says_so_plainly():
    out = brief.render_positions(P.mark_book([], {}, TODAY), TODAY)
    assert "none" in out and "Flat" in out


def test_stale_marks_are_named_and_excluded_not_carried_at_cost():
    out = brief.render_positions(_book({}), TODAY, {"ZYME": "HTTPError"})
    assert "EXCLUDED" in out and "HTTPError" in out
    assert "stale leg is not a flat leg" in out


def test_a_directional_book_is_labelled_directional():
    out = brief.render_positions(_book({"ZYME": 28.67}), TODAY)
    assert "DIRECTIONAL long" in out


def test_binary_window_warning_fires_before_the_event():
    out = brief.render_actions(_book({"ZYME": 28.67}), TODAY, "nothing")
    assert "enters its PDUFA window in 1d" in out
    assert "a decision taken during the gap is not a decision" in out


def test_actions_can_report_nothing_to_do():
    """The old report could not say this; it manufactured a pair every day."""
    out = brief.render_actions(P.mark_book([], {}, TODAY), TODAY,
                               "nothing — no leg qualified")
    assert "nothing due" in out and "nothing — no leg qualified" in out


def _res(long_pick="SU.TO", short_status="OK"):
    longs = [{"t": "SU.TO", "nd": 0.223, "confidence": "mid", "p945": 94.10},
             {"t": "AEM.TO", "nd": 0.579, "confidence": "sparse", "p945": 297.0}]
    shorts = [{"t": "TD.TO", "nd": 0.243, "confidence": "mid", "p945": 163.23},
              {"t": "MFC.TO", "nd": 0.293, "confidence": "mid", "p945": 59.0}]
    pair = {"long": {"pick": longs[0], "extra": [longs[1]], "sided": 0.57},
            "short": ({"status": "NONE", "note": "no qualified short"}
                      if short_status == "NONE"
                      else {"pick": shorts[0], "extra": [], "sided": 0.55})}
    return {"longs": longs, "shorts": shorts, "pair": pair,
            "live_record": {"pair_n": 70, "pair_hits": 34}}


def test_intraday_prints_its_own_record_next_to_the_picks():
    out, _ = brief.render_intraday(_res(), {}, shadow=False)
    assert "34/70" in out and "coin flip" in out


def test_intraday_explains_which_rival_the_pick_beat():
    out, _ = brief.render_intraday(_res(), {}, shadow=False)
    assert "chosen over AEM.TO" in out and "invalidated if" in out


def test_a_near_tie_is_called_arbitrary():
    r = _res()
    r["longs"][1]["nd"] = 0.230          # 0.007 from the pick
    out, _ = brief.render_intraday(r, {}, shadow=False)
    assert "near tie — treat as arbitrary" in out


def test_sector_concentration_is_named_on_the_side_that_has_it():
    cfg = {"peer_groups": {"financials": ["TD.TO", "MFC.TO"]}}
    out, _ = brief.render_intraday(_res(), cfg, shadow=False)
    assert "2 of this side's candidates are financials" in out


def test_a_missing_side_is_never_forced():
    out, note = brief.render_intraday(_res(short_status="NONE"), {}, shadow=False)
    assert "do not force one" in out
    assert "SU.TO" in note and "TD.TO" not in note


def test_shadow_mode_claims_no_capital():
    out, note = brief.render_intraday(_res(), {}, shadow=True)
    assert "NO capital" in out and "shadow" in note


def test_coverage_failure_blocks_the_board():
    out, note = brief.render_intraday({"coverage_fail": "only 9/21 names"},
                                      {}, shadow=False)
    assert "INSUFFICIENT COVERAGE" in out and "nothing" in note


def _cat_leg(mark, entry=24.90, up=36.00, dn=20.50):
    return {"ticker": "ZYME", "side": "LONG", "entry_px": entry, "mark": mark,
            "days": 2, "event_date": "2026-08-25", "event_kind": "PDUFA",
            "exit_condition": "close on outcome", "source": "catalyst",
            "thesis": "priority review", "upside": str(up), "downside": str(dn)}


def test_catalyst_block_recomputes_implied_probability_from_the_live_mark():
    """A thesis is written once; the implied probability moves with the price."""
    out = brief.render_catalyst_detail([_cat_leg(28.67)], TODAY)
    assert "implied P at your $24.90 entry: 28%" in out
    assert "implied P NOW at $28.67       : 53%" in out
    assert "+24 pts since entry" in out


def test_catalyst_block_states_remaining_reward_against_remaining_risk():
    out = brief.render_catalyst_detail([_cat_leg(28.67)], TODAY)
    assert "+25.6% if approved, -28.5% if not" in out
    assert "risk/reward 0.90:1" in out


def test_a_priced_in_thesis_is_flagged():
    """If the market has come to agree, the edge is gone even in profit."""
    out = brief.render_catalyst_detail([_cat_leg(32.00)], TODAY)
    assert "market has largely come to agree" in out


def test_an_unpriced_thesis_is_not_flagged():
    out = brief.render_catalyst_detail([_cat_leg(22.00)], TODAY)
    assert "market has largely come to agree" not in out


def test_catalyst_block_never_lets_an_assumed_floor_stand_unchallenged():
    """Day-68 replaced the warning with EVIDENCE. The block used to say a cash
    floor is "an ASSUMPTION, not a bound"; it now prints the measured CRL
    distribution and the median-implied floor beside whatever the thesis
    assumed, which does the same job with numbers instead of an adjective.
    """
    import catalyst as _c
    out = brief.render_catalyst_detail([_cat_leg(28.67)], TODAY)
    assert "MEASURED downside" in out
    assert f"n={_c.CRL_N} verified CRLs" in out
    assert "worse than -40%" in out
    # the assumed floor is confronted with the measured one, not just flagged
    assert "compare with the $20.50 the thesis assumes" in out
    # day-72: the approval leg is positive-below-bar, NOT "already priced" --
    # that claim came from bars that were silently monthly.
    assert "Approvals DO separate, but below the bar" in out
    assert f"t=+{_c.APPROVAL_T:.2f}" in out


def test_a_stale_mark_does_not_fabricate_a_probability():
    out = brief.render_catalyst_detail([_cat_leg(None)], TODAY)
    assert "unavailable (mark is stale)" in out
    assert "implied P NOW" not in out


def test_non_binary_positions_produce_no_catalyst_block():
    leg = _cat_leg(28.67)
    leg["upside"] = leg["downside"] = ""
    assert brief.render_catalyst_detail([leg], TODAY) == ""


def test_the_brief_publishes_before_it_renders(tmp_path, monkeypatch):
    # Functional replacement for a source-string assertion after consolidation.
    from test_daily_pipeline import NOW, services
    from report_store import Store
    monkeypatch.setattr('r945.publish', lambda *a, **k: {'errors': []})
    report = brief.compute(now=NOW, publish=True, state_dir=tmp_path, services=services())
    assert Store(tmp_path).get('2026-09-08') == report
    assert 'AAA.TO' in brief.render_text(report)


def test_publish_and_main_share_one_implementation():
    """Two publish paths would drift, and the one that drifts holds the only
    evidence this system has about itself."""
    import inspect

    import r945
    assert "publish(res, cfg)" in inspect.getsource(r945.main)


def test_shadow_mode_prints_no_share_counts():
    r = _res()
    r["pair"]["long"]["pick"]["shares"] = 160
    r["pair"]["long"]["pick"]["alloc"] = 15042
    out, _ = brief.render_intraday(r, {}, shadow=True)
    assert "BUY" not in out and "160 sh" not in out


# ── day-87: the cost line must cost the WHOLE book ─────────────────────────

def test_the_cost_line_counts_extra_legs_not_just_primaries(monkeypatch):
    from test_daily_pipeline import NOW, services, res
    s=services(); r=res()
    for side in ('long','short'):
        pick=r['pair'][side]['pick']
        extra={**pick,'t':('CCC.TO' if side=='long' else 'DDD.TO')}
        r['pair'][side]['extra']=[extra]
        r[side+'s'].append(extra)
    s['intraday']=lambda cfg:r
    d=brief.compute(now=NOW,services=s)
    assert {l['ticker'] for l in d['intraday']['legs']}=={'AAA.TO','BBB.TO','CCC.TO','DDD.TO'}
    assert all(l['estimated_round_trip_spread_usd'] is not None for l in d['intraday']['legs'])


# ── day-88: the system's ADVICE is recorded so it can be judged ────────────

def test_exit_advice_is_written_to_the_advice_ledger(monkeypatch, tmp_path):
    """REGRESSION. advice.py was built for exactly this and nothing ever
    called it: the report said "EXIT ZYME" on several mornings and no record
    anywhere captured that it had said so. An adviser whose recommendations
    are not written down cannot be evaluated."""
    import datetime as dt

    import advice as A
    monkeypatch.setattr(A, "PATH", str(tmp_path / "advice.csv"))
    rows, n = A.record([], "ZYME", "EXIT", basis="PDUFA settled APPROVED",
                       horizon_days=5, px=29.19, today=dt.date(2026, 9, 4))
    A.save(rows)
    back = A.load()
    assert n == 1 and len(back) == 1
    assert back[0]["ticker"] == "ZYME" and back[0]["action"] == "EXIT"
    assert back[0]["px_at_advice"].startswith("29.19")


def test_the_same_advice_twice_in_one_day_is_one_recommendation(monkeypatch,
                                                                tmp_path):
    """A re-read of the morning must not multiply the record."""
    import datetime as dt

    import advice as A
    monkeypatch.setattr(A, "PATH", str(tmp_path / "advice.csv"))
    rows, n1 = A.record([], "ZYME", "EXIT", basis="b", horizon_days=5,
                        px=29.19, today=dt.date(2026, 9, 4))
    rows, n2 = A.record(rows, "ZYME", "EXIT", basis="b", horizon_days=5,
                        px=29.30, today=dt.date(2026, 9, 4))
    assert n1 == 1 and n2 == 0 and len(rows) == 1


def test_factual_monitor_does_not_write_directional_advice(tmp_path, monkeypatch):
    import advice
    from test_daily_pipeline import NOW, services
    monkeypatch.setattr(advice,'PATH',str(tmp_path/'advice.csv'))
    d=brief.compute(now=NOW,services=services())
    assert not (tmp_path/'advice.csv').exists()
    assert 'Factual monitoring only' in brief.render_text(d)


def test_closed_exchange_never_publishes_intraday(tmp_path, monkeypatch):
    from test_daily_pipeline import NOW, services
    s=services(); s['clock']=lambda now: {'session':'2026-09-08','status':'CLOSED','eligible':False}
    monkeypatch.setattr('r945.publish',lambda *a,**k: __import__('pytest').fail('closed exchange published picks'))
    d=brief.compute(now=NOW,publish=True,state_dir=tmp_path,services=s)
    assert not d['intraday']['legs']


def test_engine_unavailability_is_reported_not_silent():
    from test_daily_pipeline import NOW, services
    d=brief.compute(now=NOW,no_net=True,services=services())
    assert 'OFFLINE' in brief.render_text(d)


def test_advice_save_resolves_its_path_at_call_time(tmp_path, monkeypatch):
    """A `path=PATH` default binds the production file at import time, so
    monkeypatching the module global silently does nothing and a test writes
    into the real ledger. That happened on day-88."""
    import advice as A
    monkeypatch.setattr(A, "PATH", str(tmp_path / "a.csv"))
    A.save([{"issued": "2026-09-08", "ticker": "X", "action": "EXIT",
             "basis": "b", "horizon_days": "5", "px_at_advice": "1.0",
             "px_at_horizon": "", "move_pct": "", "judged": "", "note": ""}])
    assert (tmp_path / "a.csv").exists(), "save ignored the redirected PATH"
    assert len(A.load()) == 1
