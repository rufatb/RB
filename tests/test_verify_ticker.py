"""A ticker is not a company, and a symbol that resolves is not a symbol that
resolves to what you meant.

2026-09-10: an outside source recommended shorting "RBC.TO", which does not
exist — Royal Bank is RY.TO. That one fails loudly at the broker. The dangerous
case is the one that succeeds: `GOLD` is Gold.com Inc, not Barrick, and a
day-84 probe took its numbers with no error at all.
"""
import urllib.error

import pytest

import verify_ticker as V


def payload(symbol="RY.TO", name="Royal Bank of Canada", price=285.2,
            currency="CAD", exchange="Toronto"):
    return {"chart": {"result": [{"meta": {
        "symbol": symbol, "longName": name, "regularMarketPrice": price,
        "currency": currency, "fullExchangeName": exchange}}]}}


@pytest.fixture()
def stub(monkeypatch):
    def install(fn):
        monkeypatch.setattr(V, "lookup", lambda s, timeout=20.0: fn(s))
    return install


def test_a_symbol_the_venue_does_not_know_is_NOT_FOUND(stub):
    stub(lambda s: {"status": V.NOT_FOUND, "detail": "venue returned HTTP 404"})
    assert V.check("RBC.TO")["status"] == V.NOT_FOUND


def test_a_symbol_that_resolves_to_the_wrong_company_is_caught(stub):
    """THE CASE THIS EXISTS FOR. GOLD resolves, prices, and is not Barrick."""
    stub(lambda s: {"status": V.OK, "symbol": "GOLD", "name": "Gold.com, Inc.",
                    "price": 8.0, "currency": "USD", "exchange": "NYSE",
                    "redirected": False})
    r = V.check("GOLD", expect="barrick")
    assert r["status"] == V.WRONG_ISSUER
    assert "Gold.com" in r["detail"]


def test_the_right_ticker_for_the_same_company_passes(stub):
    stub(lambda s: {"status": V.OK, "symbol": "ABX.TO",
                    "name": "Barrick Mining Corporation", "price": 60.5,
                    "currency": "CAD", "exchange": "Toronto",
                    "redirected": False})
    assert V.check("ABX.TO", expect="barrick")["status"] == V.OK


def test_without_an_expected_issuer_only_existence_is_claimed(stub):
    """Verifying existence is not verifying identity, and the tool must not
    imply the stronger check was made."""
    stub(lambda s: {"status": V.OK, "symbol": "GOLD", "name": "Gold.com, Inc.",
                    "price": 8.0, "redirected": False})
    assert V.check("GOLD")["status"] == V.OK


def test_a_transport_failure_is_never_reported_as_not_found(monkeypatch):
    """Rule 1. "I could not check" and "it does not exist" are different
    answers and only one of them is safe to act on."""
    def boom(url, timeout=None):
        raise urllib.error.URLError("dns")
    monkeypatch.setattr(V.urllib.request, "urlopen", boom)
    r = V.lookup("RY.TO")
    assert r["status"] == V.LOOKUP_FAILED and r["status"] != V.NOT_FOUND


def test_a_404_is_not_found_but_a_500_is_a_failed_lookup(monkeypatch):
    def code(n):
        def boom(url, timeout=None):
            raise urllib.error.HTTPError(url, n, "x", {}, None)
        return boom
    monkeypatch.setattr(V.urllib.request, "urlopen", code(404))
    assert V.lookup("RBC.TO")["status"] == V.NOT_FOUND
    monkeypatch.setattr(V.urllib.request, "urlopen", code(500))
    assert V.lookup("RY.TO")["status"] == V.LOOKUP_FAILED


def test_a_silent_venue_redirect_is_surfaced(monkeypatch):
    """Yahoo answers USDCAD=X with CAD=X. A symbol swap the caller did not ask
    for must be visible, not absorbed."""
    import json
    monkeypatch.setattr(V.urllib.request, "urlopen",
                        lambda url, timeout=None: type("R", (), {
                            "read": staticmethod(lambda: json.dumps(
                                payload(symbol="CAD=X", name="USD/CAD")).encode())})())
    r = V.lookup("USDCAD=X")
    assert r["redirected"] is True and r["symbol"] == "CAD=X"


def test_a_listed_but_unpriced_symbol_is_not_reported_OK(monkeypatch):
    import json
    monkeypatch.setattr(V.urllib.request, "urlopen",
                        lambda url, timeout=None: type("R", (), {
                            "read": staticmethod(lambda: json.dumps(
                                payload(price=None)).encode())})())
    assert V.lookup("RY.TO")["status"] == V.NO_PRICE


def test_the_exit_code_is_nonzero_when_anything_failed(stub, capsys):
    stub(lambda s: {"status": V.NOT_FOUND, "detail": "404"})
    assert V.main(["RBC.TO"]) == 1
    assert "did NOT verify clean" in capsys.readouterr().out
