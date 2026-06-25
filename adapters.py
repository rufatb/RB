"""
adapters.py — pluggable data layer.

WHY a pluggable adapter:
    The decision logic must not care where quotes come from. Today the default
    is free, delayed Yahoo data; tomorrow it might be a real-time broker feed.
    Swapping the source must NOT require touching metrics or the brief logic.

HONESTY CONSTRAINTS BAKED IN HERE (do not strip in future edits):
    * Every quote carries a `source` and an `as_of` timestamp. The freshness
      guard depends on this. A quote with no timestamp is useless for a 9:31
      live decision and is treated as stale.
    * No adapter fabricates fields it cannot source. If a value is missing it
      stays `None`, never a guessed number.
    * Order-flow / bid-ask aggressor delta is NOT exposed by these adapters,
      because none of the supported free/L1 sources actually provide it.
      Inventing it is forbidden (see metrics.py proxies instead).
"""

from __future__ import annotations

import datetime as dt
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional

import pandas as pd


# ─────────────────────────────────────────────────────────────────────────────
# Data containers
# ─────────────────────────────────────────────────────────────────────────────
@dataclass
class Quote:
    """A point-in-time Level-1 quote. Missing fields stay None — never faked."""

    ticker: str
    last: Optional[float]
    open: Optional[float]
    high: Optional[float]
    low: Optional[float]
    prior_close: Optional[float]
    volume: Optional[float]
    source: str
    as_of: Optional[dt.datetime]          # tz-aware; when this quote was current
    session_date: Optional[dt.date]       # the trading session this quote belongs to
    currency: Optional[str] = None
    notes: list = field(default_factory=list)

    def is_complete_for_direction(self) -> bool:
        """Minimum fields needed to even attempt a directional read."""
        return None not in (self.last, self.open, self.prior_close)


# ─────────────────────────────────────────────────────────────────────────────
# Interface
# ─────────────────────────────────────────────────────────────────────────────
class DataAdapter(ABC):
    """Interface every data source must implement."""

    name: str = "abstract"

    @abstractmethod
    def get_quote(self, ticker: str) -> Quote:
        """Full Level-1 quote with timestamp + session date."""

    @abstractmethod
    def get_intraday_bars(self, ticker: str, interval: str = "1m") -> pd.DataFrame:
        """Intraday OHLCV bars for today. Index = tz-aware timestamps."""

    @abstractmethod
    def get_daily_bars(self, ticker: str, lookback_days: int) -> pd.DataFrame:
        """Daily OHLCV bars for the lookback window."""

    @abstractmethod
    def get_quote_simple(self, ticker: str) -> Quote:
        """Lighter quote for correlated tickers (still timestamped)."""


# ─────────────────────────────────────────────────────────────────────────────
# Yahoo (default, free) — DELAYED DATA. Read the caveat.
# ─────────────────────────────────────────────────────────────────────────────
class YahooAdapter(DataAdapter):
    """
    Default free adapter using yfinance.

    CAVEAT (this is why the freshness guard is mandatory):
        * TSX quotes via Yahoo are typically ~15 minutes DELAYED.
        * Yahoo periodically serves CACHED / STALE data — sometimes hours or
          even months old — with no obvious error. This has produced confident
          intraday calls on data that was not live.
        * Therefore: fine for context, but a 9:31 LIVE decision on Yahoo data
          must pass the freshness guard or be replaced with manual broker L1.
    """

    name = "yahoo"

    def __init__(self, exchange_tz: str = "America/Toronto"):
        import yfinance  # imported lazily so stubs don't require it
        self._yf = yfinance
        self.exchange_tz = exchange_tz

    # -- helpers --------------------------------------------------------------
    def _ticker(self, ticker: str):
        return self._yf.Ticker(ticker)

    def _to_exchange_tz(self, ts) -> Optional[dt.datetime]:
        if ts is None:
            return None
        ts = pd.Timestamp(ts)
        if ts.tzinfo is None:
            ts = ts.tz_localize("UTC")
        return ts.tz_convert(self.exchange_tz).to_pydatetime()

    # -- interface ------------------------------------------------------------
    def get_quote(self, ticker: str) -> Quote:
        t = self._ticker(ticker)
        notes: list = []

        # fast_info is the lightest reliable source for last/open/etc.
        fi = {}
        try:
            fi = dict(t.fast_info)
        except Exception as e:  # pragma: no cover - network/library variance
            notes.append(f"fast_info failed: {e}")

        last = fi.get("last_price")
        open_ = fi.get("open")
        high = fi.get("day_high")
        low = fi.get("day_low")
        prior_close = fi.get("previous_close") or fi.get("regular_market_previous_close")
        volume = fi.get("last_volume") or fi.get("volume")
        currency = fi.get("currency")

        # Timestamp: Yahoo's fast_info does not always expose a trade time, so
        # we read the last 1-min bar's timestamp as the authoritative "as_of".
        # If we cannot get a real timestamp, as_of stays None -> treated stale.
        as_of = None
        session_date = None
        try:
            bars = t.history(period="1d", interval="1m", auto_adjust=False)
            if not bars.empty:
                last_ts = self._to_exchange_tz(bars.index[-1])
                as_of = last_ts
                session_date = last_ts.date() if last_ts else None
                # Prefer live bar data for OHLC when fast_info is thin.
                if last is None:
                    last = float(bars["Close"].iloc[-1])
                if open_ is None:
                    open_ = float(bars["Open"].iloc[0])
                if high is None:
                    high = float(bars["High"].max())
                if low is None:
                    low = float(bars["Low"].min())
                if volume is None:
                    volume = float(bars["Volume"].sum())
        except Exception as e:  # pragma: no cover
            notes.append(f"intraday history failed: {e}")

        return Quote(
            ticker=ticker,
            last=_f(last),
            open=_f(open_),
            high=_f(high),
            low=_f(low),
            prior_close=_f(prior_close),
            volume=_f(volume),
            source=self.name,
            as_of=as_of,
            session_date=session_date,
            currency=currency,
            notes=notes,
        )

    def get_intraday_bars(self, ticker: str, interval: str = "1m") -> pd.DataFrame:
        t = self._ticker(ticker)
        df = t.history(period="1d", interval=interval, auto_adjust=False)
        if df.empty:
            return df
        df = df.copy()
        df.index = pd.to_datetime(df.index)
        if df.index.tz is None:
            df.index = df.index.tz_localize("UTC")
        df.index = df.index.tz_convert(self.exchange_tz)
        return df

    def get_daily_bars(self, ticker: str, lookback_days: int) -> pd.DataFrame:
        t = self._ticker(ticker)
        period = f"{max(lookback_days, 5)}d"
        df = t.history(period=period, interval="1d", auto_adjust=False)
        if df.empty:
            return df
        df = df.copy()
        df.index = pd.to_datetime(df.index)
        return df

    def get_quote_simple(self, ticker: str) -> Quote:
        # Reuse the full quote path; correlated tickers still need timestamps so
        # they can be freshness-checked individually.
        return self.get_quote(ticker)


# ─────────────────────────────────────────────────────────────────────────────
# Yahoo DIRECT (default) — raw chart endpoint via requests.
#
# WHY this exists alongside YahooAdapter(yfinance):
#   The yfinance library fetches a cookie + "crumb" before every call and retries
#   aggressively; behind a proxy that handshake can hang for minutes. The raw
#   query1.finance.yahoo.com/v8/finance/chart endpoint returns the same data in
#   one request with a hard timeout — verified live returning AC.TO at 24.51 CAD.
#   Same delayed-data caveat applies, so the freshness guard is still mandatory.
# ─────────────────────────────────────────────────────────────────────────────
_YH_HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; PreOpenBrief/1.0)"}
_YH_HOSTS = ["https://query1.finance.yahoo.com", "https://query2.finance.yahoo.com"]


class YahooDirectAdapter(DataAdapter):
    name = "yahoo_direct"

    def __init__(self, exchange_tz: str = "America/Toronto", timeout: int = 20):
        import requests
        self._requests = requests
        self.exchange_tz = exchange_tz
        self.timeout = timeout

    def _chart(self, ticker: str, interval: str, rng: str) -> dict:
        """Fetch a chart payload, failing over query1 -> query2. Hard timeout."""
        last_err = None
        for host in _YH_HOSTS:
            url = f"{host}/v8/finance/chart/{ticker}"
            try:
                r = self._requests.get(
                    url, params={"interval": interval, "range": rng},
                    headers=_YH_HEADERS, timeout=self.timeout,
                )
                r.raise_for_status()
                j = r.json()
                if j.get("chart", {}).get("result"):
                    return j["chart"]["result"][0]
            except Exception as e:  # pragma: no cover - network variance
                last_err = e
        raise RuntimeError(f"yahoo_direct fetch failed for {ticker}: {last_err}")

    def _bars_df(self, result: dict) -> pd.DataFrame:
        ts = result.get("timestamp") or []
        q = (result.get("indicators", {}).get("quote") or [{}])[0]
        if not ts:
            return pd.DataFrame()
        idx = pd.to_datetime(ts, unit="s", utc=True).tz_convert(self.exchange_tz)
        df = pd.DataFrame({
            "Open": q.get("open"), "High": q.get("high"),
            "Low": q.get("low"), "Close": q.get("close"),
            "Volume": q.get("volume"),
        }, index=idx)
        return df.dropna(subset=["Close"])

    def get_quote(self, ticker: str) -> Quote:
        result = self._chart(ticker, "1m", "1d")
        meta = result.get("meta", {})
        as_of = None
        session_date = None
        rmt = meta.get("regularMarketTime")
        if rmt:
            as_of = pd.Timestamp(rmt, unit="s", tz="UTC").tz_convert(self.exchange_tz).to_pydatetime()
            session_date = as_of.date()
        bars = self._bars_df(result)
        return Quote(
            ticker=ticker,
            last=_f(meta.get("regularMarketPrice")),
            open=_f(bars["Open"].iloc[0]) if not bars.empty else None,
            high=_f(meta.get("regularMarketDayHigh")),
            low=_f(meta.get("regularMarketDayLow")),
            prior_close=_f(meta.get("chartPreviousClose") or meta.get("previousClose")),
            volume=_f(meta.get("regularMarketVolume")),
            source=self.name,
            as_of=as_of,
            session_date=session_date,
            currency=meta.get("currency"),
        )

    def get_intraday_bars(self, ticker: str, interval: str = "1m") -> pd.DataFrame:
        return self._bars_df(self._chart(ticker, interval, "1d"))

    def get_daily_bars(self, ticker: str, lookback_days: int) -> pd.DataFrame:
        # Pick the smallest standard range that covers the lookback.
        rng = "1y"
        for cand, days in [("1mo", 31), ("3mo", 93), ("6mo", 186), ("1y", 366),
                           ("2y", 732), ("5y", 1830), ("10y", 3660), ("max", 10**9)]:
            if days >= lookback_days:
                rng = cand
                break
        else:
            rng = "max"
        return self._bars_df(self._chart(ticker, "1d", rng))

    def get_quote_simple(self, ticker: str) -> Quote:
        return self.get_quote(ticker)


# ─────────────────────────────────────────────────────────────────────────────
# Stooq — free, no API key. Good independent cross-check for many tickers, but
# TSX coverage is spotty (AC.TO is NOT listed there). Returns `unavailable`
# rather than guessing when the symbol is absent — never fabricates.
# ─────────────────────────────────────────────────────────────────────────────
class StooqAdapter(DataAdapter):
    name = "stooq"

    def __init__(self, exchange_tz: str = "America/Toronto", timeout: int = 15):
        import requests
        self._requests = requests
        self.exchange_tz = exchange_tz
        self.timeout = timeout

    def _symbol(self, ticker: str) -> str:
        # Stooq uses lowercase; US tickers add .us. Pass through exchange suffixes.
        t = ticker.lower()
        if "." not in t and "=" not in t and "^" not in t:
            t = f"{t}.us"
        return t

    def get_quote(self, ticker: str) -> Quote:
        url = "https://stooq.com/q/l/"
        try:
            r = self._requests.get(
                url, params={"s": self._symbol(ticker), "f": "sd2t2ohlcv", "h": "", "e": "csv"},
                headers=_YH_HEADERS, timeout=self.timeout,
            )
            r.raise_for_status()
            lines = r.text.strip().splitlines()
            if len(lines) < 2 or "N/D" in lines[1] or "<" in r.text[:1]:
                raise ValueError("stooq returned no data for symbol")
            cols = lines[0].split(",")
            vals = lines[1].split(",")
            row = dict(zip(cols, vals))
            date_s, time_s = row.get("Date"), row.get("Time")
            as_of = None
            session_date = None
            if date_s and date_s != "N/D":
                as_of = pd.Timestamp(f"{date_s} {time_s or '00:00:00'}", tz=self.exchange_tz).to_pydatetime()
                session_date = as_of.date()
            return Quote(
                ticker=ticker, last=_f(row.get("Close")), open=_f(row.get("Open")),
                high=_f(row.get("High")), low=_f(row.get("Low")),
                prior_close=None, volume=_f(row.get("Volume")),
                source=self.name, as_of=as_of, session_date=session_date,
            )
        except Exception as e:
            return Quote(ticker=ticker, last=None, open=None, high=None, low=None,
                         prior_close=None, volume=None, source=self.name,
                         as_of=None, session_date=None,
                         notes=[f"stooq unavailable: {e}"])

    def get_intraday_bars(self, ticker: str, interval: str = "1m") -> pd.DataFrame:
        return pd.DataFrame()  # stooq free tier has no reliable intraday — no fabrication

    def get_daily_bars(self, ticker: str, lookback_days: int) -> pd.DataFrame:
        url = "https://stooq.com/q/d/l/"
        try:
            r = self._requests.get(url, params={"s": self._symbol(ticker), "i": "d"},
                                   headers=_YH_HEADERS, timeout=self.timeout)
            r.raise_for_status()
            from io import StringIO
            df = pd.read_csv(StringIO(r.text))
            if "Date" not in df.columns:
                return pd.DataFrame()
            df["Date"] = pd.to_datetime(df["Date"])
            df = df.set_index("Date").tail(lookback_days)
            return df
        except Exception:
            return pd.DataFrame()

    def get_quote_simple(self, ticker: str) -> Quote:
        return self.get_quote(ticker)


# ─────────────────────────────────────────────────────────────────────────────
# Key-based real-time sources. These are the genuinely INDEPENDENT cross-check
# and the path to real intraday + volume that beats Yahoo's delay. They activate
# only when an API key is present (env var); otherwise they fail loudly rather
# than silently degrade. Free tiers exist for all three.
# ─────────────────────────────────────────────────────────────────────────────
class FinnhubAdapter(DataAdapter):
    """finnhub.io — real-time US + many intl; set FINNHUB_API_KEY. Free tier available."""
    name = "finnhub"

    def __init__(self, exchange_tz: str = "America/Toronto", api_key: Optional[str] = None, timeout: int = 15):
        import os, requests
        self._requests = requests
        self.exchange_tz = exchange_tz
        self.api_key = api_key or os.environ.get("FINNHUB_API_KEY")
        self.timeout = timeout
        if not self.api_key:
            raise ValueError("FinnhubAdapter requires FINNHUB_API_KEY")

    def get_quote(self, ticker: str) -> Quote:
        r = self._requests.get("https://finnhub.io/api/v1/quote",
                               params={"symbol": ticker, "token": self.api_key},
                               timeout=self.timeout)
        r.raise_for_status()
        j = r.json()
        ts = j.get("t")
        as_of = pd.Timestamp(ts, unit="s", tz="UTC").tz_convert(self.exchange_tz).to_pydatetime() if ts else None
        return Quote(
            ticker=ticker, last=_f(j.get("c")), open=_f(j.get("o")),
            high=_f(j.get("h")), low=_f(j.get("l")), prior_close=_f(j.get("pc")),
            volume=None, source=self.name, as_of=as_of,
            session_date=as_of.date() if as_of else None,
            notes=["finnhub /quote has no volume field"],
        )

    def get_intraday_bars(self, ticker: str, interval: str = "1m") -> pd.DataFrame:
        return pd.DataFrame()  # candle endpoint is premium on free tier; no fabrication

    def get_daily_bars(self, ticker: str, lookback_days: int) -> pd.DataFrame:
        return pd.DataFrame()

    def get_quote_simple(self, ticker: str) -> Quote:
        return self.get_quote(ticker)


class TwelveDataAdapter(DataAdapter):
    """twelvedata.com — real-time quote + intraday bars + volume; set TWELVEDATA_API_KEY."""
    name = "twelvedata"

    def __init__(self, exchange_tz: str = "America/Toronto", api_key: Optional[str] = None, timeout: int = 20):
        import os, requests
        self._requests = requests
        self.exchange_tz = exchange_tz
        self.api_key = api_key or os.environ.get("TWELVEDATA_API_KEY")
        self.timeout = timeout
        if not self.api_key:
            raise ValueError("TwelveDataAdapter requires TWELVEDATA_API_KEY")

    def get_quote(self, ticker: str) -> Quote:
        r = self._requests.get("https://api.twelvedata.com/quote",
                               params={"symbol": ticker, "apikey": self.api_key},
                               timeout=self.timeout)
        r.raise_for_status()
        j = r.json()
        if j.get("status") == "error":
            raise RuntimeError(f"twelvedata error: {j.get('message')}")
        ts = j.get("timestamp")
        as_of = pd.Timestamp(int(ts), unit="s", tz="UTC").tz_convert(self.exchange_tz).to_pydatetime() if ts else None
        return Quote(
            ticker=ticker, last=_f(j.get("close")), open=_f(j.get("open")),
            high=_f(j.get("high")), low=_f(j.get("low")),
            prior_close=_f(j.get("previous_close")), volume=_f(j.get("volume")),
            source=self.name, as_of=as_of,
            session_date=as_of.date() if as_of else None,
            currency=j.get("currency"),
        )

    def get_intraday_bars(self, ticker: str, interval: str = "1m") -> pd.DataFrame:
        iv = {"1m": "1min", "5m": "5min"}.get(interval, "1min")
        r = self._requests.get("https://api.twelvedata.com/time_series",
                               params={"symbol": ticker, "interval": iv,
                                       "outputsize": 390, "apikey": self.api_key},
                               timeout=self.timeout)
        r.raise_for_status()
        j = r.json()
        vals = j.get("values")
        if not vals:
            return pd.DataFrame()
        df = pd.DataFrame(vals)
        df["datetime"] = pd.to_datetime(df["datetime"])
        df = df.set_index("datetime").sort_index()
        for c in ("open", "high", "low", "close", "volume"):
            if c in df:
                df[c] = pd.to_numeric(df[c], errors="coerce")
        df = df.rename(columns={"open": "Open", "high": "High", "low": "Low",
                                "close": "Close", "volume": "Volume"})
        if df.index.tz is None:
            df.index = df.index.tz_localize(self.exchange_tz)
        return df

    def get_daily_bars(self, ticker: str, lookback_days: int) -> pd.DataFrame:
        r = self._requests.get("https://api.twelvedata.com/time_series",
                               params={"symbol": ticker, "interval": "1day",
                                       "outputsize": min(lookback_days, 5000),
                                       "apikey": self.api_key},
                               timeout=self.timeout)
        r.raise_for_status()
        vals = r.json().get("values")
        if not vals:
            return pd.DataFrame()
        df = pd.DataFrame(vals)
        df["datetime"] = pd.to_datetime(df["datetime"])
        df = df.set_index("datetime").sort_index()
        for c in ("open", "high", "low", "close", "volume"):
            if c in df:
                df[c] = pd.to_numeric(df[c], errors="coerce")
        return df.rename(columns={"open": "Open", "high": "High", "low": "Low",
                                  "close": "Close", "volume": "Volume"})

    def get_quote_simple(self, ticker: str) -> Quote:
        return self.get_quote(ticker)


# ─────────────────────────────────────────────────────────────────────────────
# Multi-source aggregator — the heart of the "use multiple data sources" ask.
#
# It serves all metrics from a PRIMARY adapter, but also fetches the same quote
# from one or more CROSS-CHECK adapters so the data-integrity guard can flag a
# SOURCE CONFLICT. Cross-check failures are recorded, never fabricated.
# ─────────────────────────────────────────────────────────────────────────────
class MultiSourceAdapter(DataAdapter):
    name = "multi"

    def __init__(self, primary: DataAdapter, cross_check: Optional[list] = None):
        self.primary = primary
        self.cross_check = cross_check or []
        self.name = f"multi[{primary.name}]"
        self.last_cross_quotes: list = []  # populated on get_quote for the guard

    def get_quote(self, ticker: str) -> Quote:
        q = self.primary.get_quote(ticker)
        self.last_cross_quotes = []
        for adp in self.cross_check:
            try:
                cq = adp.get_quote(ticker)
                if cq.last is not None:
                    self.last_cross_quotes.append(cq)
            except Exception as e:  # record, do not fabricate
                q.notes.append(f"cross-check {adp.name} failed: {e}")
        return q

    def best_cross_quote(self) -> Optional[Quote]:
        """The first cross-check quote with a usable last price (for the guard)."""
        return self.last_cross_quotes[0] if self.last_cross_quotes else None

    def get_intraday_bars(self, ticker: str, interval: str = "1m") -> pd.DataFrame:
        df = self.primary.get_intraday_bars(ticker, interval)
        if df is not None and not df.empty:
            return df
        # Fall back to the first cross-check source that actually has intraday bars.
        for adp in self.cross_check:
            try:
                alt = adp.get_intraday_bars(ticker, interval)
                if alt is not None and not alt.empty:
                    return alt
            except Exception:
                continue
        return df if df is not None else pd.DataFrame()

    def get_daily_bars(self, ticker: str, lookback_days: int) -> pd.DataFrame:
        df = self.primary.get_daily_bars(ticker, lookback_days)
        if df is not None and not df.empty:
            return df
        for adp in self.cross_check:
            try:
                alt = adp.get_daily_bars(ticker, lookback_days)
                if alt is not None and not alt.empty:
                    return alt
            except Exception:
                continue
        return df if df is not None else pd.DataFrame()

    def get_quote_simple(self, ticker: str) -> Quote:
        return self.primary.get_quote_simple(ticker)


# ─────────────────────────────────────────────────────────────────────────────
# Manual override — paste verified broker Level-1 numbers
# ─────────────────────────────────────────────────────────────────────────────
class ManualAdapter(DataAdapter):
    """
    Lets the user paste broker Level-1 numbers when the API is delayed/stale.

    WHY this exists:
        At 9:31 the free feed may be 15 min behind. A trader staring at their
        broker's live L1 can type the real numbers in. Manual input is tagged
        `source=manual` and BYPASSES the staleness fail (the human vouches for
        it) — but it is still clearly labelled so nobody mistakes it for an API
        feed. It does NOT fabricate intraday bars; those degrade gracefully.
    """

    name = "manual"

    def __init__(
        self,
        *,
        open: float,
        last: float,
        high: float,
        low: float,
        volume: float,
        prior_close: Optional[float] = None,
        exchange_tz: str = "America/Toronto",
        currency: Optional[str] = None,
    ):
        self.exchange_tz = exchange_tz
        # as_of = now, because the human is reading it live right now.
        now = pd.Timestamp.now(tz=exchange_tz).to_pydatetime()
        self._quote = Quote(
            ticker="(manual)",
            last=_f(last),
            open=_f(open),
            high=_f(high),
            low=_f(low),
            prior_close=_f(prior_close),
            volume=_f(volume),
            source=self.name,
            as_of=now,
            session_date=now.date(),
            currency=currency,
            notes=["manual broker L1 — bypasses staleness fail by user vouch"],
        )

    def get_quote(self, ticker: str) -> Quote:
        q = self._quote
        q.ticker = ticker
        return q

    def get_intraday_bars(self, ticker: str, interval: str = "1m") -> pd.DataFrame:
        # No fabricated bars. Caller must handle an empty frame gracefully.
        return pd.DataFrame()

    def get_daily_bars(self, ticker: str, lookback_days: int) -> pd.DataFrame:
        return pd.DataFrame()

    def get_quote_simple(self, ticker: str) -> Quote:
        # HONESTY: the human pasted Level-1 for ONE ticker only. We must NOT
        # echo those numbers back as if they were crude/TSX/peer quotes — that
        # would fabricate correlated data. Return an empty (unavailable) quote
        # so the brief prints "unavailable" for context in manual mode.
        return Quote(
            ticker=ticker, last=None, open=None, high=None, low=None,
            prior_close=None, volume=None, source=self.name,
            as_of=None, session_date=None,
            notes=["manual mode: no correlated data pasted -> unavailable"],
        )


# ─────────────────────────────────────────────────────────────────────────────
# Real-time upgrade stubs — documented, intentionally not implemented.
# README explains: for genuine 9:31 live decisions, prefer one of these over
# free Yahoo data.
# ─────────────────────────────────────────────────────────────────────────────
class _UnimplementedAdapter(DataAdapter):
    name = "stub"
    install_hint = ""

    def _raise(self):
        raise NotImplementedError(
            f"{self.name} adapter is a documented stub. "
            f"Implement against your real-time feed. {self.install_hint}"
        )

    def get_quote(self, ticker: str) -> Quote:
        self._raise()

    def get_intraday_bars(self, ticker: str, interval: str = "1m") -> pd.DataFrame:
        self._raise()

    def get_daily_bars(self, ticker: str, lookback_days: int) -> pd.DataFrame:
        self._raise()

    def get_quote_simple(self, ticker: str) -> Quote:
        self._raise()


class IBKRAdapter(_UnimplementedAdapter):
    """Interactive Brokers via `ib_insync`. Real-time L1 (and L2 if subscribed)."""
    name = "ibkr"
    install_hint = "pip install ib_insync; needs TWS/IB Gateway running."


class QuestradeAdapter(_UnimplementedAdapter):
    """Questrade REST API. Real-time with market-data package."""
    name = "questrade"
    install_hint = "Use Questrade OAuth refresh token; see their API docs."


class PolygonAdapter(_UnimplementedAdapter):
    """Polygon.io paid feed (US-centric; limited TSX coverage)."""
    name = "polygon"
    install_hint = "pip install polygon-api-client; set POLYGON_API_KEY."


class AlpacaAdapter(_UnimplementedAdapter):
    """Alpaca market data (US equities)."""
    name = "alpaca"
    install_hint = "pip install alpaca-py; set APCA keys."


# ─────────────────────────────────────────────────────────────────────────────
def _f(x) -> Optional[float]:
    """Coerce to float or None. Never turns a missing value into 0.0."""
    if x is None:
        return None
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    if v != v:  # NaN
        return None
    return v


def _build_single(name: str, *, exchange_tz: str, manual_kwargs: Optional[dict] = None) -> DataAdapter:
    """Build one concrete adapter by name."""
    name = (name or "yahoo_direct").lower()
    if name == "manual":
        if not manual_kwargs:
            raise ValueError("manual adapter requires pasted Level-1 numbers")
        return ManualAdapter(exchange_tz=exchange_tz, **manual_kwargs)
    if name in ("yahoo_direct", "yahoo"):   # default + back-compat: 'yahoo' -> reliable direct
        return YahooDirectAdapter(exchange_tz=exchange_tz)
    if name in ("yahoo_yf", "yfinance"):
        return YahooAdapter(exchange_tz=exchange_tz)
    if name == "stooq":
        return StooqAdapter(exchange_tz=exchange_tz)
    if name == "finnhub":
        return FinnhubAdapter(exchange_tz=exchange_tz)
    if name == "twelvedata":
        return TwelveDataAdapter(exchange_tz=exchange_tz)
    if name == "ibkr":
        return IBKRAdapter()
    if name == "questrade":
        return QuestradeAdapter()
    if name == "polygon":
        return PolygonAdapter()
    if name == "alpaca":
        return AlpacaAdapter()
    raise ValueError(f"unknown adapter: {name}")


def build_adapter(name: str, *, exchange_tz: str, manual_kwargs: Optional[dict] = None,
                  cross_check: Optional[list] = None) -> DataAdapter:
    """
    Factory used by the CLI.

    If `cross_check` (a list of source names) is provided and the primary is not
    manual, the primary is wrapped in a MultiSourceAdapter so the data-integrity
    guard gets independent quotes to compare. Cross-check sources that can't be
    built (e.g. missing API key) are skipped with a note rather than failing.
    """
    primary = _build_single(name, exchange_tz=exchange_tz, manual_kwargs=manual_kwargs)
    if name == "manual" or not cross_check:
        return primary
    built = []
    for cc in cross_check:
        if cc and cc.lower() != name.lower():
            try:
                built.append(_build_single(cc, exchange_tz=exchange_tz))
            except Exception:
                pass  # missing key / unavailable source — skip, don't fabricate
    if not built:
        return primary
    return MultiSourceAdapter(primary, built)
