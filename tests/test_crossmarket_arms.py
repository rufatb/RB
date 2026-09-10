"""Day-95/96: one unavailable series must not delete two runnable arms.

The day-95 run reported BLOCKED with nothing computed because `missing` was
`(names | PROXIES) - fetched`. Any single missing proxy killed the whole study.
That is fail-closed at the wrong granularity: B1 reads only SPY, B2 reads only
SPY/XLF/USO, and neither touches USDCAD. XLE was blocking too and is mapped by
no arm at all.
"""
import validate_crossmarket as V


def test_each_arm_declares_the_proxies_it_actually_reads():
    assert V.ARM_PROXIES["B1"] == {"SPY"}
    assert V.ARM_PROXIES["B3"] == {"USDCAD", "USO"}
    # B2's proxies are DERIVED from SECTOR_PROXY, not hand-copied, so a change
    # to the sector map cannot silently desynchronise the two.
    assert V.ARM_PROXIES["B2"] == set(V.SECTOR_PROXY.values()) | {"SPY"}


def test_a_missing_fx_series_blocks_only_the_arm_that_reads_it():
    """THE CASE THIS EXISTS FOR. Yahoo redirects USDCAD=X to CAD=X and the
    harness rightly refuses an unauthenticated FX bar — but B1 and B2 never
    read FX."""
    ok, blocked = V.runnable_arms({"SPY", "XLF", "XLE", "USO"})
    assert set(ok) == {"B1", "B2"}
    assert blocked == {"B3": ["USDCAD"]}


def test_xle_is_not_required_by_any_arm():
    """It is fetched but mapped by no arm, so requiring it blocked the study
    for a series nothing consumes."""
    assert not any("XLE" in need for need in V.ARM_PROXIES.values())
    ok, blocked = V.runnable_arms({"SPY", "XLF", "USO", "USDCAD"})
    assert set(ok) == set(V.ARMS) and blocked == {}


def test_losing_every_proxy_still_blocks_everything():
    ok, blocked = V.runnable_arms(set())
    assert ok == {} and set(blocked) == set(V.ARMS)


def test_a_blocked_arm_does_not_loosen_the_holm_correction():
    """Rule 3. Correcting across the 2 arms that happened to run, instead of
    the 3 the registration declared, would relax the bar exactly when a data
    failure has already weakened the result — a bar moved in our own favour
    after seeing which fetches failed."""
    registered = V.holm([0.01, 0.02], V.REGISTERED_ARM_COUNT)
    shrunk = V.holm([0.01, 0.02])
    assert V.REGISTERED_ARM_COUNT == 3
    assert all(r > s for r, s in zip(registered, shrunk)), \
        "the registered family size must give STRICTER adjusted p-values"


def test_holm_never_reports_below_the_raw_p_value():
    for fam in (1, 3, 5):
        for adj, raw in zip(V.holm([0.01, 0.04, 0.2], fam), [0.01, 0.04, 0.2]):
            assert adj >= raw - 1e-12


def test_holm_preserves_input_order_and_keeps_none():
    out = V.holm([0.2, None, 0.01], 3)
    assert out[1] is None and out[2] <= out[0]
