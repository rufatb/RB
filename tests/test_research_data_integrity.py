"""Day-91 synthetic regressions; no downloaded prices or strategy outcomes."""

from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest
import requests

import build_us as builder
import validate_entry as entry


def feature_panel(sessions=50, names=6):
    dates = pd.bdate_range("2025-01-01", periods=sessions).strftime("%Y-%m-%d")
    return pd.DataFrame([
        {"t": f"T{n}", "date": date, "v15": float((i + 1) * (n + 1)),
         "r0": 0.1, "gap": 0.2, "r1": 0.3}
        for n in range(names) for i, date in enumerate(dates)
    ])


def test_volume_history_requires_twenty_prior_observations_per_name():
    frame = feature_panel(25, 2).sample(frac=1, random_state=3)
    out = entry.add_past_volume_pace(frame)
    for _, group in out.groupby("t"):
        assert group["vp"].iloc[:20].isna().all()
        assert group["vp"].iloc[20] == pytest.approx(21 / 10.5)
    assert "vp" not in frame.columns


def test_current_and_future_volume_cannot_change_a_prior_denominator():
    frame = feature_panel(30, 1)
    original = entry.add_past_volume_pace(frame)
    changed = frame.copy()
    changed.loc[20:, "v15"] *= 1_000_000
    out = entry.add_past_volume_pace(changed)
    pd.testing.assert_series_equal(original["vp"].iloc[:20], out["vp"].iloc[:20])
    assert out["vp"].iloc[20] / 1_000_000 == pytest.approx(original["vp"].iloc[20])


def test_appended_future_data_cannot_change_walk_forward_predictions(monkeypatch):
    monkeypatch.setattr(entry, "extrapolation_check", lambda train, rec: (True, ""))
    monkeypatch.setattr(entry, "knn_probability", lambda train, rec: (rec["vp"], 1, 1))
    full = feature_panel(55)
    dates = sorted(full["date"].unique())
    cutoff = dates[44]
    history = full[full["date"] <= cutoff]
    first = entry.scored(history, min_train=25)
    full.loc[full["date"] > cutoff, ["v15", "r1"]] = 1e12
    second = [d for d in entry.scored(full, min_train=25) if d["date"] <= cutoff]
    assert first and len(first) == len(second)
    for before, after in zip(first, second):
        assert before["date"] == after["date"]
        for field in ("p", "nd", "r"):
            np.testing.assert_array_equal(before[field], after[field])


def test_duplicate_sessions_and_zero_volume_do_not_fabricate_history():
    frame = feature_panel(30, 1)
    with pytest.raises(ValueError, match="duplicate ticker/session"):
        entry.add_past_volume_pace(pd.concat([frame, frame.iloc[[0]]]))
    frame["v15"] = 0.0
    assert entry.add_past_volume_pace(frame)["vp"].isna().all()


def test_entry_fetch_reports_missing_names_without_exception_secrets(monkeypatch, capsys):
    secret = "https://provider.invalid/data?apiKey=DO_NOT_PRINT"

    class Adapter:
        def __init__(self, **kwargs):
            pass

        def _chart(self, ticker, interval, rng):
            if ticker == "DENIED":
                error = requests.HTTPError(secret)
                error.response = SimpleNamespace(status_code=403)
                raise error
            if ticker == "BAD":
                raise ValueError(secret)
            return ticker

        def _bars_df(self, ticker):
            return pd.DataFrame() if ticker == "EMPTY" else pd.DataFrame({"Close": [1]})

    monkeypatch.setattr(entry, "YahooDirectAdapter", Adapter)
    bars = entry.fetch_all(["GOOD", "DENIED", "BAD", "EMPTY"], "5m", "60d", "UTC")
    assert not bars["GOOD"].empty
    assert all(bars[t].empty for t in ("DENIED", "BAD", "EMPTY"))
    output = capsys.readouterr().out
    assert "3 absent" in output and "HTTP_403=1" in output
    assert "ValueError=1" in output and "EmptyBars=1" in output
    assert "DO_NOT_PRINT" not in output and "https://" not in output


def test_daily_fetch_honors_years_and_reports_recovered_http_failure(monkeypatch, capsys):
    calls = []
    secret = "https://provider.invalid?token=DO_NOT_PRINT"

    class Response:
        def __init__(self, denied):
            self.denied = denied

        def raise_for_status(self):
            if self.denied:
                error = requests.HTTPError(secret)
                error.response = SimpleNamespace(status_code=403)
                raise error

        def json(self):
            return {"chart": {"result": [{"timestamp": [1]}]}}

    def get(url, **kwargs):
        calls.append(kwargs["params"])
        return Response(denied=len(calls) == 1)

    monkeypatch.setattr(builder.requests, "get", get)
    monkeypatch.setattr(builder.time, "time", lambda: 2_000_000_000)
    monkeypatch.setattr(builder.time, "sleep", lambda _: None)
    assert builder.fetch_daily("TEST", years=3, tries=1) == {"timestamp": [1]}
    assert len(calls) == 2
    assert calls[0]["period1"] == 2_000_000_000 - 3 * 366 * 86400
    output = capsys.readouterr().out
    assert "HTTP_403=1" in output and "recovered" in output
    assert "DO_NOT_PRINT" not in output and "https://" not in output


def test_empty_chart_attempts_are_reported_with_safe_reasons(monkeypatch, capsys):
    monkeypatch.setattr(builder.requests, "get", lambda *a, **kw: SimpleNamespace(
        raise_for_status=lambda: None,
        json=lambda: {"chart": {"error": {"description": "secret-url"}, "result": None}}))
    assert builder.fetch_daily("TEST", tries=2) is None
    output = capsys.readouterr().out
    assert "ProviderChartError=4" in output and "no data" in output
    assert "secret-url" not in output


def test_price_builder_propagates_years_and_keeps_failure_categories(monkeypatch, capsys):
    requested = []

    def fetch(ticker, *, years, diagnostics):
        requested.append(years)
        if ticker == "FETCH":
            diagnostics.extend(["HTTP_403", "HTTP_403"])
            return None
        if ticker == "GOOD":
            diagnostics.append("Timeout")
        return {"ticker": ticker}

    def rows(ticker, response):
        if ticker == "PARSE":
            raise ValueError("https://provider.invalid?token=DO_NOT_PRINT")
        return [] if ticker == "SHORT" else [{"t": ticker, "date": "2025-01-02"}]

    monkeypatch.setattr(builder, "fetch_daily", fetch)
    monkeypatch.setattr(builder, "daily_rows", rows)
    frame, bad = builder.build_prices(["GOOD", "FETCH", "PARSE", "SHORT"], years=7)
    assert requested == [7] * 4
    assert frame["t"].tolist() == ["GOOD"]
    assert (bad["fetch"], bad["parse"], bad["granularity_or_short"]) == (1, 1, 1)
    assert bad["attempt_errors"] == {"Timeout": 1, "HTTP_403": 2}
    assert bad["terminal_errors"] == {"HTTP_403": 1, "ValueError": 1}
    assert "DO_NOT_PRINT" not in capsys.readouterr().out


def test_cli_years_reaches_acquisition_and_no_empty_panel_is_written(monkeypatch, tmp_path):
    calls = []
    monkeypatch.setattr(builder, "DATA", str(tmp_path))
    monkeypatch.setattr(builder, "sec_tickers", lambda *a, **kw: [{"ticker": "TEST"}])

    def prices(tickers, *, years):
        calls.append((tickers, years))
        return pd.DataFrame(), {"fetch": 1}

    monkeypatch.setattr(builder, "build_prices", prices)
    assert builder.main(["--years", "3"]) == 2
    assert calls == [(["TEST"], 3)]
    assert list(tmp_path.iterdir()) == []


def test_sec_acquisition_does_not_print_exception_credentials(monkeypatch, capsys):
    def fail(*args, **kwargs):
        raise requests.ConnectionError("https://provider.invalid?token=DO_NOT_PRINT")

    monkeypatch.setattr(builder.requests, "get", fail)
    monkeypatch.setattr(builder.time, "sleep", lambda _: None)
    frame, failed = builder.build_earnings([{"ticker": "TEST", "cik": 1}], workers=1)
    assert frame.empty and failed == ["RuntimeError"]
    output = capsys.readouterr().out
    assert "ConnectionError" in output and "1 absent names" in output
    assert "DO_NOT_PRINT" not in output and "https://" not in output
