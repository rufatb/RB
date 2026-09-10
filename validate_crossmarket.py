#!/usr/bin/env python3
"""
validate_crossmarket.py — day-94 Arm B: cross-market overnight state.

Pre-registered in PREREGISTER_day94.md (committed before any outcome was
computed). SHADOW RESEARCH: nothing here is imported by r945, scan or the
published report, and no outcome of this harness adopts anything.

QUESTION. Does the PRIOR completed session of US market/sector/macro proxies
(SPY, XLF, USO, USDCAD) carry out-of-sample information about same-day TSX
large-cap open-to-close direction, beyond the day-91 parity k-NN on
[r0, gap]? Exactly three fixed arms, no parameter search:

  B1: + SPY prior-session close-to-close return
  B2: + sector-matched proxy prior-session return (SECTOR_PROXY, fixed below)
  B3: + USDCAD and USO prior-session returns jointly

DAILY-BAR PROXY, stated first. At 09:46 ET the knowable state is the proxy's
prior completed session, which is exactly what these features use. But the
only label free daily bars support is same-day open->close, which contains
09:30-09:46 — sixteen minutes the real engine does not see. Every result is
labelled DAILY-BAR PROXY and cannot certify the 09:46-15:59 contract whatever
the point estimates say. Daily-bar adaptation of the established definitions
(build_pool.py / validate_twins.py / validate_ceiling.py): gap = (open /
prior own-session close - 1) * 100, unchanged; r0 = open -> entry return is
IDENTICALLY ZERO because the registered entry stand-in is the session open —
the column is kept (a constant contributes zero to the parity k-NN's
standardized distance) so the degeneracy is explicit, never silently dropped;
the label is the direction of the same-day open->close return.

METHOD (day-91/day-93 corrected harness). Baseline: validate_ceiling.knn_scores
(r945 parity arithmetic, K/M/HARD_CAP imported, not reimplemented). Whole-session
chronological walk-forward folds, paired AUC influence differences aggregated
within session (day-91 correction), deterministic circular block bootstrap
(20-session blocks, 2,000 draws, seed 94), MDE80 = (3.5 + 0.8416212336) * SE in
AUC points printed ALWAYS (rule 10), four chronological development blocks all
printed, Holm across the 3 arms, a planted +2 AUC-point control measured as
edge/SE against the SAME arm unplanted (never (mean+edge)/SE), a zero-mean
session sign-flip placebo the estimate must beat at its 95th percentile, and a
confirmation block 2026-01-01 -> last complete session.

DATA. Stooq daily CSV primary (TSX symbols probed as lowercase `ry.to` form;
the form that works is recorded), Yahoo chart API fallback with granularity
asserted and the adjclose/close ratio as the documented auto_adjust
equivalent. Sessions missing any name or any required proxy observation are
REJECTED AND COUNTED, never bridged (rule 2). The 21 names are today's
surviving mega-caps; delisting bias is DISCLOSED, not assumed away.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import io
import json
import math
import os
import sys
import time
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
import pandas_market_calendars as mcal
import requests
import yaml
from scipy.stats import norm

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from validate_ceiling import add_control, auc_influence, knn_scores  # noqa: E402

# Registered constants (PREREGISTER_day94.md). These do not move.
SEED = 94
DRAWS = 2000
BLOCK = 20                      # bootstrap block length, in sessions
DEV_START = "2015-01-01"
DEV_END = "2025-12-31"
CONF_START = "2026-01-01"
MIN_TRAIN = 120                 # sessions before the first OOS fold
FOLDS = 5                       # development walk-forward folds
CONTROL_EDGE = 0.02             # planted +2 AUC-point synthetic edge
MDE_Z = 3.5                     # registered one-sided critical value
POWER_Z = 0.8416212336          # z(80% power)
PLACEBO_Q = 0.95

PROXIES = {  # stooq symbol, yahoo symbol
    "SPY": ("spy.us", "SPY"), "XLF": ("xlf.us", "XLF"), "XLE": ("xle.us", "XLE"),
    "USO": ("uso.us", "USO"), "USDCAD": ("usdcad", "USDCAD=X"),
}

# B2 mapping, fixed here per the registration: XLF for financials, USO for
# energy producers, SPY otherwise. Financials and energy are the repo's own
# peer_groups (config.yaml); pipelines are grouped with producers because the
# repo's energy group has always included them. Everything else takes SPY.
SECTOR_PROXY = {
    "RY.TO": "XLF", "TD.TO": "XLF", "BNS.TO": "XLF", "BMO.TO": "XLF",
    "CM.TO": "XLF", "MFC.TO": "XLF", "SLF.TO": "XLF",
    "CNQ.TO": "USO", "SU.TO": "USO", "CVE.TO": "USO", "ENB.TO": "USO",
    "TRP.TO": "USO",
}

ARMS = {"B1": ["r0", "gap", "x_spy"],
        "B2": ["r0", "gap", "x_sector"],
        "B3": ["r0", "gap", "x_usdcad", "x_uso"]}
BASELINE = ["r0", "gap"]

UA = {"User-Agent": "Mozilla/5.0 (day-94 cross-market study; research)"}


class GranularityError(ValueError):
    """The source answered with non-daily bars (rule 9). Never downgraded."""


class FetchError(RuntimeError):
    """A fetch that exhausted its retries; .cls is the underlying error class."""

    def __init__(self, cls: str, msg: str):
        super().__init__(msg)
        self.cls = cls


def error_class(exc: BaseException) -> str:
    if isinstance(exc, requests.HTTPError) and exc.response is not None:
        return f"HTTP_{exc.response.status_code}"
    if isinstance(exc, requests.Timeout):
        return "TIMEOUT"
    if isinstance(exc, requests.ConnectionError):
        return "CONNECTION"
    if isinstance(exc, (json.JSONDecodeError, ValueError)):
        return "DECODE"
    return type(exc).__name__.upper()


def get_bytes(url: str, session=None, timeout=30.0, tries=3, params=None) -> bytes:
    http = session or requests
    last = None
    for attempt in range(max(1, tries)):
        try:
            r = http.get(url, headers=UA, timeout=timeout, params=params)
            r.raise_for_status()
            return r.content
        except Exception as e:                      # noqa: BLE001 — re-raised
            last = e
            if attempt + 1 < tries:
                time.sleep(1.0 * (attempt + 1))
    raise FetchError(error_class(last),
                     f"{error_class(last)} after {max(1, tries)} tries: {url}")


def _check_daily(index: pd.DatetimeIndex, symbol: str) -> None:
    """Rule 9: assert the bars we GOT are daily, not the bars we asked for."""
    if len(index) < 10:
        raise GranularityError(f"{symbol}: only {len(index)} bars")
    if index.duplicated().any():
        raise GranularityError(f"{symbol}: duplicate session bars")
    gaps = index.to_series().diff().dt.days.dropna()
    if float(gaps.median()) > 3.0 or float(gaps.max()) > 11.0:
        raise GranularityError(
            f"{symbol}: spacing median {gaps.median()}d / max {gaps.max()}d "
            "is not a daily series")


def parse_stooq(raw: bytes, symbol: str) -> pd.DataFrame:
    text = raw.decode("utf-8", "replace")
    if "Exceeded the daily hits limit" in text:
        raise ValueError("stooq daily hits limit")
    df = pd.read_csv(io.StringIO(text))
    if df.empty or not {"Date", "Open", "High", "Low", "Close"} <= set(df.columns):
        raise ValueError(f"{symbol}: unexpected stooq schema {list(df.columns)}")
    df["date"] = pd.to_datetime(df["Date"], format="%Y-%m-%d", errors="raise")
    df = df.set_index("date").sort_index()
    _check_daily(df.index, symbol)
    out = df[["Open", "High", "Low", "Close"]].astype(float)
    if not np.isfinite(out.to_numpy()).all() or (out <= 0).any().any():
        raise ValueError(f"{symbol}: nonpositive/nonfinite stooq rows")
    return out.rename(columns=str.lower)


def parse_yahoo(payload: dict, symbol: str) -> pd.DataFrame:
    """Yahoo chart API daily bars. auto_adjust equivalent, documented: OHLC are
    rescaled by adjclose/close, so close-to-close and open/prior-close returns
    match a split- and dividend-adjusted series. Granularity asserted (rule 9).
    """
    result = (payload.get("chart") or {}).get("result") or []
    if not result:
        err = (payload.get("chart") or {}).get("error")
        raise ValueError(f"{symbol}: no chart result ({err!r})")
    res = result[0]
    returned = ((res.get("meta") or {}).get("symbol") or "").upper()
    if returned != symbol.upper():
        raise ValueError(f"asked for {symbol}, yahoo returned {returned!r}")
    ts = res.get("timestamp") or []
    q = (res.get("indicators", {}).get("quote") or [{}])[0]
    adj = (res.get("indicators", {}).get("adjclose") or [{}])[0].get("adjclose")
    if not ts or adj is None:
        raise ValueError(f"{symbol}: missing timestamps or adjclose")
    idx = pd.DatetimeIndex(pd.to_datetime(ts, unit="s", utc=True)
                           .tz_convert("America/New_York").normalize()
                           .tz_localize(None))
    df = pd.DataFrame({"open": q.get("open"), "high": q.get("high"),
                       "low": q.get("low"), "close": q.get("close"),
                       "adj": adj}, index=idx).dropna()
    df = df.groupby(level=0).last().sort_index()
    _check_daily(df.index, symbol)
    factor = df["adj"] / df["close"]
    out = df[["open", "high", "low", "close"]].multiply(factor, axis=0)
    if not np.isfinite(out.to_numpy()).all() or (out <= 0).any().any():
        raise ValueError(f"{symbol}: nonpositive/nonfinite yahoo rows")
    return out


def stooq_url(sym: str, d1: str, d2: str) -> str:
    return (f"https://stooq.com/q/d/l/?s={sym}"
            f"&d1={d1.replace('-', '')}&d2={d2.replace('-', '')}&i=d")


def yahoo_url(symbol: str, d1: str, d2: str) -> tuple:
    p1 = int(pd.Timestamp(d1, tz="UTC").timestamp())
    p2 = int((pd.Timestamp(d2, tz="UTC") + pd.Timedelta(days=1)).timestamp())
    return (f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}",
            {"period1": p1, "period2": p2, "interval": "1d",
             "events": "div,split"})


def fetch_one(label: str, stooq_sym: str | None, yahoo_sym: str, d1: str,
              d2: str, session=None, timeout: float = 30.0,
              tries: int = 3) -> tuple:
    """(df, provenance) or (None, failures). Stooq primary, Yahoo fallback."""
    failures = []
    if stooq_sym:
        url = stooq_url(stooq_sym, d1, d2)
        try:
            raw = get_bytes(url, session=session, timeout=timeout, tries=tries)
            df = parse_stooq(raw, stooq_sym)
            return df, {"source": "stooq", "url": url, "rows": int(len(df)),
                        "sha256": hashlib.sha256(raw).hexdigest()}
        except Exception as e:                      # noqa: BLE001 — recorded
            failures.append({"source": "stooq", "url": url,
                             "error": getattr(e, "cls", error_class(e)),
                             "detail": str(e)[:200]})
    url, params = yahoo_url(yahoo_sym, d1, d2)
    try:
        raw = get_bytes(url, session=session, params=params,
                        timeout=timeout, tries=tries)
        df = parse_yahoo(json.loads(raw), yahoo_sym)
        return df, {"source": "yahoo", "url": url,
                    "params": {k: str(v) for k, v in params.items()},
                    "rows": int(len(df)),
                    "sha256": hashlib.sha256(raw).hexdigest(),
                    "adjustment": "adjclose/close ratio (auto_adjust equivalent)"}
    except Exception as e:                          # noqa: BLE001 — recorded
        failures.append({"source": "yahoo", "url": url,
                         "error": getattr(e, "cls", error_class(e)),
                         "detail": str(e)[:200]})
    return None, failures


def universe_from_config(path: str) -> list:
    with open(path) as f:
        cfg = yaml.safe_load(f)
    return sorted(set((cfg.get("scan") or {}).get("universe") or [])
                  | {cfg.get("ticker")})


def fetch_all(names: list, d1: str, d2: str, session=None,
              delay: float = 0.5, timeout: float = 30.0, tries: int = 3) -> dict:
    """Every required series. Probe records which stooq TSX form works."""
    frames, provenance, failures = {}, {}, {}
    probe = {"symbol_form": None, "verified": False, "note": None}
    todo = [(t, t.split(".")[0].lower() + ".to", t) for t in names]
    todo += [(p, s, y) for p, (s, y) in PROXIES.items()]
    for i, (label, ssym, ysym) in enumerate(todo):
        df, info = fetch_one(label, ssym, ysym, d1, d2, session=session,
                             timeout=timeout, tries=tries)
        if df is None:
            failures[label] = info
            print(f"  [{i + 1:2d}/{len(todo)}] {label:8s} FAILED "
                  f"({'; '.join(f['source'] + ':' + f['error'] for f in info)})",
                  flush=True)
        else:
            frames[label] = df
            provenance[label] = info
            print(f"  [{i + 1:2d}/{len(todo)}] {label:8s} {info['source']:6s} "
                  f"{info['rows']:5d} rows", flush=True)
            if label == names[0]:
                probe.update(symbol_form=ssym, verified=info["source"] == "stooq",
                             note=None if info["source"] == "stooq"
                             else "stooq TSX form unavailable here; yahoo fallback")
        if i + 1 < len(todo):
            time.sleep(delay)
    if not probe["verified"] and names[0] in frames:
        pass                                        # note already set
    elif not probe["verified"]:
        probe["note"] = "stooq probe failed; recorded, fallback attempted"
    return {"frames": frames, "provenance": provenance,
            "failures": failures, "probe": probe}


# ---------------------------------------------------------------- panel
def build_panel(name_frames: dict, proxy_frames: dict,
                dev_start=DEV_START, last_complete: str | None = None,
                name_calendar="TSX", proxy_calendar="NYSE") -> tuple:
    """Per name/session rows [r0, gap, y] plus prior-session proxy returns.

    A session enters the panel only if EVERY name has a bar on it and on the
    prior own-calendar session (gap), and every proxy has bars on the last two
    proxy-calendar sessions strictly before it. Violations are rejected and
    counted by cause — never bridged, never interpolated (rule 2).
    """
    last_complete = last_complete or default_last_complete()
    ncal = mcal.get_calendar(name_calendar).schedule(
        start_date=dev_start, end_date=last_complete)
    pcal = mcal.get_calendar(proxy_calendar).schedule(
        start_date=dev_start, end_date=last_complete)
    n_sessions = pd.DatetimeIndex(ncal.index).tz_localize(None)
    p_sessions = pd.DatetimeIndex(pcal.index).tz_localize(None)
    names, proxies = sorted(name_frames), sorted(proxy_frames)
    nf = {t: name_frames[t] for t in names}
    pf = {p: proxy_frames[p] for p in proxies}
    counters = {"rejected_missing_name": 0, "rejected_missing_proxy": 0,
                "warmup_first_session": 0, "rows": 0}
    rejected_examples = []
    rows = []
    for i, d in enumerate(n_sessions):
        if i == 0:
            counters["warmup_first_session"] += 1
            continue
        prev = n_sessions[i - 1]
        if any(d not in nf[t].index or prev not in nf[t].index for t in names):
            counters["rejected_missing_name"] += 1
            if len(rejected_examples) < 10:
                rejected_examples.append(
                    {"date": str(d.date()), "cause": "missing_name_bar"})
            continue
        earlier = p_sessions[p_sessions < d]
        if len(earlier) < 2:
            counters["warmup_first_session"] += 1
            continue
        p1, p2 = earlier[-1], earlier[-2]
        if any(p1 not in pf[p].index or p2 not in pf[p].index for p in proxies):
            counters["rejected_missing_proxy"] += 1
            if len(rejected_examples) < 10:
                rejected_examples.append(
                    {"date": str(d.date()), "cause": "missing_proxy_bar"})
            continue
        xret = {p: float((pf[p].loc[p1, "close"] / pf[p].loc[p2, "close"]
                         - 1) * 100) for p in proxies}
        if not all(math.isfinite(v) for v in xret.values()):
            counters["rejected_missing_proxy"] += 1
            continue
        for t in names:
            o = float(nf[t].loc[d, "open"])
            c = float(nf[t].loc[d, "close"])
            pc = float(nf[t].loc[prev, "close"])
            rows.append({"t": t, "date": str(d.date()),
                         "r0": 0.0,                  # daily-bar adaptation
                         "gap": (o / pc - 1) * 100,
                         "y": int(c > o),
                         "x_sector_basis": SECTOR_PROXY.get(t, "SPY"),
                         **{f"x_{p.lower()}": v for p, v in xret.items()}})
        counters["rows"] += len(names)
    df = pd.DataFrame(rows)
    counters["sessions"] = int(df["date"].nunique()) if not df.empty else 0
    return df, counters, rejected_examples


def add_arm_features(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["x_sector"] = [row[f"x_{p.lower()}"]
                      for row, p in zip(df.to_dict("records"),
                                        df["x_sector_basis"])]
    return df


# ---------------------------------------------------------------- harness
def walk_forward(df: pd.DataFrame, feats: list, dev_sessions: list,
                 conf_sessions: list, min_train=MIN_TRAIN,
                 folds=FOLDS) -> dict:
    """Whole-session chronological folds; parity k-NN on identical rows."""
    out = {}
    splits = []
    edges = np.linspace(min_train, len(dev_sessions), folds + 1).astype(int)
    for a, b in zip(edges[:-1], edges[1:]):
        splits.append(("dev", dev_sessions[:a], dev_sessions[a:b]))
    if conf_sessions:
        splits.append(("conf", dev_sessions, conf_sessions))
    for part, tr_sess, te_sess in splits:
        if not te_sess:
            continue
        tr = df[df["date"].isin(tr_sess)]
        te = df[df["date"].isin(te_sess)]
        s = knn_scores(tr[feats].to_numpy(float), tr["y"].to_numpy(int),
                       te[feats].to_numpy(float))
        if not np.isfinite(s).all():
            raise ValueError("parity k-NN abstained or returned nonfinite scores")
        acc = out.setdefault(part, {"y": [], "s": [], "date": []})
        acc["y"].append(te["y"].to_numpy(int))
        acc["s"].append(s)
        acc["date"].append(te["date"].to_numpy())
    return {k: tuple(np.concatenate(v) for v in
                     (part["y"], part["s"], part["date"]))
            for k, part in out.items()}


def paired_session_diff(y, s_arm, s_base, dates) -> tuple:
    """Paired AUC difference and its per-session influence sums (day-91)."""
    a_val, a_inf = auc_influence(y, s_arm)
    b_val, b_inf = auc_influence(y, s_base)
    groups = pd.Series(a_inf - b_inf).groupby(dates, sort=True).sum()
    return a_val - b_val, groups.to_numpy(), groups.index.to_numpy()


def bootstrap(session_vals: np.ndarray, point: float, seed=SEED,
              draws=DRAWS, block=BLOCK) -> dict:
    """Deterministic circular block bootstrap over SESSION influence sums.

    The paired AUC estimate is a SUM-type statistic: its sandwich SE is
    sqrt(sum of squared session sums) (validate_ceiling.clustered_se), so the
    bootstrap resamples session sums in 20-session blocks and takes the SUM of
    each resample as the null noise around the point estimate — never the
    mean, which would shrink the SE by a factor of n_sessions.
    """
    x = np.asarray(session_vals, dtype=float)
    n = len(x)
    if n < 2 or not np.isfinite(x).all():
        raise ValueError("bootstrap needs >= 2 finite session values")
    rng = np.random.default_rng(seed)
    starts = rng.integers(0, n, size=(draws, math.ceil(n / block)))
    idx = ((starts[:, :, None] + np.arange(block)) % n).reshape(draws, -1)[:, :n]
    d = point + x[idx].sum(axis=1)
    se = float(d.std(ddof=1))
    se_sandwich = float(np.sqrt(n / (n - 1) * np.square(x).sum()))
    if se <= 1e-15:
        return {"point": point, "se": None, "ci95": None, "mde80": None,
                "z": None, "p": None, "se_sandwich": se_sandwich,
                "status": "DEGENERATE_INFERENCE"}
    z = point / se
    return {"point": float(point), "se": se, "se_sandwich": se_sandwich,
            "ci95": [float(q) for q in np.quantile(d, [0.025, 0.975])],
            "mde80": (MDE_Z + POWER_Z) * se, "z": float(z),
            "p": float(2 * norm.sf(abs(z))), "status": "OK"}


def placebo_q95(session_vals: np.ndarray, seed=SEED, draws=DRAWS) -> float:
    """95th percentile of |noise| under zero-mean per-session sign flips.

    Same sum-type scale as the point estimate: a placebo draw is the SUM of
    sign-flipped session influence sums, matching the sandwich SE's scale.
    """
    x = np.asarray(session_vals, dtype=float) - np.mean(session_vals)
    rng = np.random.default_rng([seed, 7])
    signs = rng.choice([-1.0, 1.0], size=(draws, len(x)))
    return float(np.quantile(np.abs(signs @ x), PLACEBO_Q))


def holm(pvals: list) -> list:
    """Holm-adjusted p-values, input order preserved; None stays None."""
    order = sorted((p, i) for i, p in enumerate(pvals) if p is not None)
    out, running, m = [None] * len(pvals), 0.0, len(order)
    for rank, (p, i) in enumerate(order):
        running = max(running, min(1.0, (m - rank) * p))
        out[i] = running
    return out


def block_deltas(y, s_arm, s_base, dates, blocks=4) -> list:
    """Paired AUC diff within each of `blocks` chronological session blocks."""
    sess = np.array(sorted(pd.unique(dates)))
    out = []
    for chunk in np.array_split(sess, blocks):
        m = np.isin(dates, chunk)
        if m.sum() == 0:
            out.append(None)
            continue
        a, _ = auc_influence(y[m], s_arm[m])
        b, _ = auc_influence(y[m], s_base[m])
        out.append(float(a - b))
    return out


def evaluate(df: pd.DataFrame, seed=SEED, draws=DRAWS, min_train=MIN_TRAIN,
             folds=FOLDS, conf_start=CONF_START) -> dict:
    """The full registered evaluation on a built panel. Pure given the panel."""
    df = add_arm_features(df)
    sessions = sorted(df["date"].unique())
    dev_sessions = [s for s in sessions if s < conf_start]
    conf_sessions = [s for s in sessions if s >= conf_start]
    if len(dev_sessions) < min_train + folds:
        return {"status": "BLOCKED",
                "reason": f"only {len(dev_sessions)} development sessions; "
                          f"the harness requires >= {min_train + folds}"}
    scores = {"baseline": walk_forward(df, BASELINE, dev_sessions,
                                       conf_sessions, min_train, folds)}
    for arm, feats in ARMS.items():
        scores[arm] = walk_forward(df, feats, dev_sessions, conf_sessions,
                                   min_train, folds)
    ctrl_df = add_control(df, CONTROL_EDGE, seed=seed)
    scores["B1+ctrl"] = walk_forward(ctrl_df, ARMS["B1"] + ["ctrl"],
                                     dev_sessions, conf_sessions,
                                     min_train, folds)

    def paired_in(part, arm):
        y, s, d = scores[arm][part]
        yb, sb, db = scores["baseline"][part]
        if not (np.array_equal(y, yb) and np.array_equal(d, db)):
            raise ValueError("paired comparison does not share identical rows")
        return paired_session_diff(y, s, sb, d)

    result = {"status": "OK", "arms": {}, "sessions": {
        "development_oos": int(len(np.unique(scores['baseline']['dev'][2]))),
        "confirmation": int(len(conf_sessions))}}
    pvals = []
    for arm in ARMS:
        delta, svals, _ = paired_in("dev", arm)
        boot = bootstrap(svals, delta, seed=seed, draws=draws)
        y, s, d = scores[arm]["dev"]
        sb = scores["baseline"]["dev"][1]
        pq95 = placebo_q95(svals, seed=seed, draws=draws)
        entry = {"delta_auc": boot["point"],
                 "delta_points": boot["point"] * 100,
                 "se_points": (boot["se"] or float("nan")) * 100,
                 "ci95_points": [v * 100 for v in boot["ci95"]]
                 if boot["ci95"] else None,
                 "mde80_points": (boot["mde80"] or float("nan")) * 100,
                 "z": boot["z"], "p": boot["p"],
                 "placebo_q95_points": pq95 * 100,
                 "beats_placebo": bool(boot["ci95"]
                                       and abs(boot["point"]) > pq95),
                 "block_deltas_points": [None if v is None else v * 100 for v in
                                         block_deltas(y, s, sb, d)]}
        if "conf" in scores[arm] and result["sessions"]["confirmation"] >= 20:
            cdelta, cvals, _ = paired_in("conf", arm)
            cboot = bootstrap(cvals, cdelta, seed=seed, draws=draws)
            entry["confirmation"] = {
                "delta_points": cboot["point"] * 100,
                "ci95_points": [v * 100 for v in cboot["ci95"]]
                if cboot["ci95"] else None,
                "se_points": (cboot["se"] or float("nan")) * 100}
        pvals.append(boot["p"])
        result["arms"][arm] = entry
    for arm, hp in zip(ARMS, holm(pvals)):
        result["arms"][arm]["holm_p"] = hp

    # Positive control: planted +2 AUC-point edge on B1's features, measured
    # as edge/SE against the SAME arm unplanted — never (mean+edge)/SE.
    cdelta_c, cvals_c, _ = paired_in("dev", "B1+ctrl")
    cdelta_b, cvals_b, _ = paired_in("dev", "B1")
    control_edge = cdelta_c - cdelta_b
    cboot = bootstrap(cvals_c - cvals_b, control_edge, seed=seed, draws=draws)
    # Detection is the registered edge/SE form: the planted edge's paired
    # interval must exclude zero. The measured size is printed beside the
    # plant so dilution by the parity k-NN is visible, not hidden.
    detected = bool(cboot["ci95"] and cboot["ci95"][0] > 0)
    result["control"] = {"planted_points": CONTROL_EDGE * 100,
                         "measured_points": cboot["point"] * 100,
                         "edge_over_se": cboot["z"], "detected": detected,
                         "form": "edge/SE vs the same arm unplanted"}
    if not detected:
        result["verdict"] = "UNDERPOWERED"
        result["verdict_note"] = ("the planted +2 AUC-point control was not "
                                  "detected as edge/SE; no null here is "
                                  "evidence of no signal (rule 10)")
        return result
    survivors = []
    for arm, e in result["arms"].items():
        screen = (e["ci95_points"] and e["ci95_points"][0] > 0
                  and e["holm_p"] is not None and e["holm_p"] < 0.05
                  and e["beats_placebo"])
        conf = e.get("confirmation")
        replicated = bool(screen and conf and conf["ci95_points"]
                          and conf["ci95_points"][0] > 0)
        e["development_screen"] = bool(screen)
        e["confirmation_replicated"] = replicated
        if replicated:
            survivors.append(arm)
    if survivors:
        result["verdict"] = "POSITIVE_DAILY_BAR_PROXY_LIMITS"
        result["verdict_note"] = (
            f"{survivors} survive Holm, placebo and confirmation ON A "
            "DAILY-BAR PROXY. This licenses only a registered replication "
            "with intraday proxy state at 09:46 — which day-93 showed is not "
            "available free. NO ADOPTION of anything.")
    else:
        result["verdict"] = "NULL_WITH_MDE"
        result["verdict_note"] = ("no arm clears the registered bars; MDEs "
                                  "above bound what this panel could resolve")
    return result


def default_last_complete() -> str:
    today = dt.datetime.now(ZoneInfo("America/New_York")).date()
    sched = mcal.get_calendar("TSX").schedule(
        start_date=str(today - dt.timedelta(days=10)), end_date=str(today))
    days = [d.date() for d in pd.DatetimeIndex(sched.index) if d.date() < today]
    if not days:
        raise ValueError("no completed TSX session in the last 10 days")
    return str(days[-1])


def print_report(res: dict) -> None:
    print("\n" + "=" * 74)
    print("DAY-94 ARM B — cross-market overnight state (DAILY-BAR PROXY)")
    print("=" * 74)
    if res.get("status") != "OK":
        print(f"  STATUS: {res.get('status')} — {res.get('reason') or res.get('note')}")
        return
    print(f"  dev OOS sessions: {res['sessions']['development_oos']}  "
          f"confirmation sessions: {res['sessions']['confirmation']}")
    print(f"  {'arm':<5}{'dAUC(pts)':>11}{'CI95 lo':>9}{'CI95 hi':>9}"
          f"{'SE':>7}{'MDE80':>8}{'z':>7}{'holm_p':>9}{'placebo95':>11}")
    for arm, e in res["arms"].items():
        ci = e["ci95_points"] or [float("nan"), float("nan")]
        hp = e.get("holm_p")
        print(f"  {arm:<5}{e['delta_points']:>11.3f}{ci[0]:>9.3f}{ci[1]:>9.3f}"
              f"{e['se_points']:>7.3f}{e['mde80_points']:>8.3f}"
              f"{(e['z'] if e['z'] is not None else float('nan')):>7.2f}"
              f"{(hp if hp is not None else float('nan')):>9.3f}"
              f"{e['placebo_q95_points']:>11.3f}")
        print(f"        blocks: {['None' if b is None else round(b, 3) for b in e['block_deltas_points']]}"
              + (f"  confirmation dAUC={e['confirmation']['delta_points']:.3f} pts"
                 if e.get("confirmation") else ""))
    c = res["control"]
    print(f"\n  CONTROL: planted +{c['planted_points']:.0f} pts, measured "
          f"{c['measured_points']:+.3f} pts, edge/SE={c['edge_over_se']:.2f} "
          f"-> {'DETECTED' if c['detected'] else 'NOT DETECTED'}")
    print(f"  VERDICT: {res['verdict']} — {res['verdict_note']}")
    print("  DAILY-BAR PROXY: not evidence about the 09:46 execution contract. "
          "No adoption.")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--config", default=os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "config.yaml"))
    ap.add_argument("--out", default=os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "data",
        "day94_crossmarket_results.json"))
    ap.add_argument("--as-of", default=None,
                    help="last complete session YYYY-MM-DD (default: derived "
                         "from the TSX calendar)")
    ap.add_argument("--seed", type=int, default=SEED)
    ap.add_argument("--draws", type=int, default=DRAWS)
    ap.add_argument("--timeout", type=float, default=30.0)
    ap.add_argument("--tries", type=int, default=3)
    a = ap.parse_args(argv)

    last_complete = a.as_of or default_last_complete()
    names = universe_from_config(a.config)
    print(f"fetching {len(names)} TSX names + {len(PROXIES)} proxies, "
          f"{DEV_START}..{last_complete} (stooq primary, yahoo fallback)",
          flush=True)
    got = fetch_all(names, DEV_START, last_complete,
                    timeout=a.timeout, tries=a.tries)

    record = {"registration": "PREREGISTER_day94.md",
              "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
              "seed": a.seed, "draws": a.draws, "block_sessions": BLOCK,
              "window": {"development": [DEV_START, DEV_END],
                         "confirmation": [CONF_START, last_complete]},
              "label": "DAILY-BAR PROXY; SHADOW RESEARCH; NO ADOPTION",
              "survivorship_disclosure": "the 21 names are today's surviving "
              "mega-caps; delisting bias is small but DISCLOSED, not removed",
              "probe": got["probe"], "provenance": got["provenance"],
              "fetch_failures": got["failures"]}

    missing = sorted((set(names) | set(PROXIES)) - set(got["frames"]))
    if missing:
        record.update(status="BLOCKED",
                      reason="required series could not be fetched; fail "
                             "closed (rule 2), nothing computed",
                      missing_series=missing,
                      verdict="BLOCKED",
                      verdict_note="data acquisition failed with the recorded "
                                   "error classes; no panel, no inference, "
                                   "no fabrication")
        print(f"\n  BLOCKED — missing series: {', '.join(missing)}")
        print("  error classes:",
              {k: [f["source"] + ":" + f["error"] for f in v]
               for k, v in got["failures"].items()})
    else:
        df, counters, rejected_examples = build_panel(
            {t: got["frames"][t] for t in names},
            {p: got["frames"][p] for p in PROXIES},
            last_complete=last_complete)
        record["coverage"] = {**counters, "rejected_examples": rejected_examples}
        print(f"panel: {counters['sessions']} sessions, {counters['rows']} rows; "
              f"rejected missing-name={counters['rejected_missing_name']} "
              f"missing-proxy={counters['rejected_missing_proxy']}")
        res = evaluate(df, seed=a.seed, draws=a.draws)
        record.update(res)
        print_report(res)

    os.makedirs(os.path.dirname(a.out), exist_ok=True)
    with open(a.out, "w") as f:
        json.dump(record, f, indent=2, sort_keys=True)
    print(f"\n  wrote {a.out}")
    return 3 if record.get("verdict") == "BLOCKED" or record.get("status") == "BLOCKED" else 0


if __name__ == "__main__":
    raise SystemExit(main())
