"""Provider-contract failures must not become authenticated historical data."""
import datetime as dt
import io
import json
import pytest
import build_tsx as B


def payload():
    return {"chart": {"result": [{"meta": {
        "symbol": "RY.TO", "currency": "CAD", "dataGranularity": "1d"},
        "timestamp": [int(dt.datetime(2026, 8, d, 13, 30,
                       tzinfo=dt.timezone.utc).timestamp()) for d in (4, 5, 6)],
        "indicators": {"quote": [{"open": [100, 101, 102],
                                   "close": [101, 102, 103], "volume": [10, 20, 30]}]}}]}}


def fetch(monkeypatch, value):
    monkeypatch.setattr(B.urllib.request, "urlopen",
                        lambda *a, **k: io.BytesIO(json.dumps(value).encode()))
    return B.fetch("RY.TO", dt.date(2026, 8, 1), dt.date(2026, 8, 7))


def test_authenticated_completed_daily_bars_are_retained(monkeypatch):
    rows, gap = fetch(monkeypatch, payload())
    assert len(rows) == 3 and gap == 1


@pytest.mark.parametrize("field,value", [("symbol", "RY"), ("currency", "USD"),
                                         ("dataGranularity", "1wk")])
def test_requested_parameters_do_not_authenticate_returned_data(monkeypatch, field, value):
    p = payload()
    p["chart"]["result"][0]["meta"][field] = value
    with pytest.raises(ValueError):
        fetch(monkeypatch, p)


def test_missing_volume_is_not_zero(monkeypatch):
    p = payload()
    p["chart"]["result"][0]["indicators"]["quote"][0]["volume"][1] = None
    with pytest.raises(ValueError, match="invalid OHLC/volume"):
        fetch(monkeypatch, p)


def test_partial_universe_cannot_replace_previous_panel(monkeypatch, tmp_path):
    out = tmp_path / "history.csv"
    out.write_text("previous validated panel\n")
    def provider(ticker, *a):
        if ticker == "BAD.TO":
            raise ValueError("wrong provider symbol")
        return [dict(date="2026-08-04", open=100, close=101, volume=10),
                dict(date="2026-08-05", open=101, close=102, volume=20)], 1
    monkeypatch.setattr(B, "fetch", provider)
    with pytest.raises(SystemExit, match="incomplete TSX universe"):
        B.build(["RY.TO", "BAD.TO"], dt.date(2026, 8, 1), dt.date(2026, 8, 6), str(out), delay=0)
    assert out.read_text() == "previous validated panel\n"
