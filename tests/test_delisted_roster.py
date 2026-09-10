"""The delisted roster is a MEASUREMENT, not the survivorship fix.

Day-97. An EODHD free key returns 896 delisted TSX common stocks and 0 rows of
price history for them. That distinction is the whole point: a list of the dead
without their delisting returns cannot correct a backtest, and treating the
roster as if it could would reintroduce exactly the bias DATA_CEILING.md warns
manufactures effects.
"""
import csv
import os

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DELISTED = os.path.join(HERE, "data", "tsx_delisted.csv")
LIVE = os.path.join(HERE, "data", "tsx_live_symbols.csv")


def rows(path):
    with open(path) as f:
        return list(csv.DictReader(f))


def commons(path):
    return [r for r in rows(path) if r["Type"] == "Common Stock"]


def test_both_legs_of_the_ratio_exist():
    """Rule 7: a ratio needs both legs from one population. The delisted count
    means nothing without the live count from the same exchange and provider."""
    assert os.path.exists(DELISTED) and os.path.exists(LIVE)


def test_the_delisting_share_is_recorded_and_substantial():
    dead, live = len(commons(DELISTED)), len(commons(LIVE))
    assert dead > 500 and live > 500
    share = dead / (dead + live)
    assert 0.45 < share < 0.60, f"delisting share moved to {share:.3f}"


def test_the_roster_carries_no_dates_so_it_is_not_a_rate_per_period():
    """The measurement is the provider's whole history, not a per-decade rate,
    and the absence of dates is why it cannot be attributed to our sample."""
    assert not ({"Delisted", "DelistedDate", "date"} & set(rows(DELISTED)[0]))


def test_the_documentation_says_the_roster_is_not_the_fix():
    """If this ever reads as 'survivorship solved', a later study will build on
    a panel that does not exist."""
    doc = open(os.path.join(HERE, "DATA_CEILING.md")).read()
    assert "does NOT fix survivorship" in doc
    assert "0 rows of price history" in doc
    assert "UNCONDITIONAL" in doc          # rule 8, next to the rate


def test_no_delisted_name_leaked_into_the_traded_universe():
    """The roster is reference data. If a dead ticker ever reached config.yaml
    the engine would be selecting something that cannot be traded."""
    import yaml
    cfg = yaml.safe_load(open(os.path.join(HERE, "config.yaml")))
    universe = set(cfg["scan"]["universe"]) | {cfg["ticker"]}
    dead = {r["Code"] + ".TO" for r in commons(DELISTED)}
    assert not (universe & dead), f"delisted names in the universe: {universe & dead}"


def test_the_api_key_is_not_in_any_tracked_file():
    """The key was supplied in chat. It lives in .rb-state/secrets, which is
    gitignored, and must never reach a tracked file."""
    import subprocess
    out = subprocess.run(["git", "grep", "-lE", r"[0-9a-f]{12,}\.[0-9]{6,}"],
                         cwd=HERE, capture_output=True, text=True).stdout.strip()
    assert not out, f"possible credential in tracked files: {out}"
