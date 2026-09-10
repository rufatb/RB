#!/usr/bin/env python3
"""pairs.py — day-96. Intraday relative-value pairs, formed point-in-time.

Pre-registered in PREREGISTER_day96.md (committed at cac0666, before any
outcome was computed). SHADOW RESEARCH: imported by nothing in the daily
report path, and nothing here places, sizes or cancels an order.

WHAT THIS IS. Form a spread between two co-moving names on a TRAILING window,
enter at the session open when the spread has diverged, exit at that session's
close. One round trip, no overnight carry.

WHAT MAKES IT DIFFERENT FROM THE PUBLIC IMPLEMENTATIONS.

1. FORMATION IS POINT-IN-TIME. The hedge ratio and the spread's mean and sd
   come from a window ending strictly BEFORE the traded session. A full-sample
   hedge ratio leaks the entire panel into every row, and it is the most
   common defect in public pairs backtests.

2. THE STATISTIC IS PLACEBO-MAX OVER THE PAIR GRID. 578 names is 166,753
   candidate pairs. At p<0.01 uncorrected, roughly 1,600 of those test as
   cointegrated on pure noise. Selecting the best and backtesting it on the
   same data measures the selection, not the strategy. So the best REAL pair
   is scored against the distribution of the best PLACEBO pair (house rule 5),
   never against zero.

3. COST IS SUBTRACTED, NOT CLIPPED. `validate_us.net_of_cost` is a legacy
   diagnostic whose own docstring says new strategy P&L must subtract costs
   "without this clipping" -- clipping at zero hides losses. A pairs trade is
   a fixed-orientation position, so cost comes straight off the return.

THE ENGLE-GRANGER STATISTIC WITHOUT statsmodels. statsmodels is not installed,
and materialising a residual series per pair would be 166,753 x 252 floats per
refit. It is unnecessary: the Dickey-Fuller regression on the residual is
bilinear in the data, so every quantity it needs comes from three NxN
cross-moment matrices. See `formation_scores`. This is the exact DF(0)
t-statistic, computed for all pairs at once.

DAILY-BAR PROXY. Entry is the OPEN, not 09:46, so `intraday` (open->close)
contains 09:30-09:46 -- sixteen minutes the live engine does not see. Nothing
here certifies the 09:46->15:59 contract.
"""

from __future__ import annotations

import argparse
import os
import sys

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "data")

# Registered in PREREGISTER_day96.md. These do not move.
FORM_WINDOW = 252          # trailing sessions used to form a pair
MIN_OVERLAP = 200          # sessions both names must actually have
REFIT_EVERY = 21           # ~monthly, Gatev's formation/trading split
TOP_K = 20                 # pairs traded per refit (Gatev convention)
THRESHOLDS = (1.5, 2.0, 2.5)
METHODS = ("distance", "cointegration")
SPREAD_BPS = 5.0           # per leg, round trip
LEGS = 2
COST_PCT = LEGS * SPREAD_BPS / 100.0     # 0.10% per pair round trip
BOOT = 2000
SEED = 96
ADOPT_T = 3.0
BLOCKS = 4
SIZE_RATIO_MAX = 2.0


# ── loading ────────────────────────────────────────────────────────────────

def load_wide(path: str) -> dict:
    """Panel -> aligned date x ticker matrices.

    Names are kept only where the FULL history is present. A name that appears
    part-way through is not a name that was absent from the market, it is a
    name this file does not know about, and letting it in would silently
    change the candidate set from one refit to the next.
    """
    df = pd.read_csv(path)
    need = {"t", "date", "open", "close", "intraday", "volume"}
    missing = need - set(df.columns)
    if missing:
        raise ValueError(f"{path} lacks {sorted(missing)}")

    close = df.pivot(index="date", columns="t", values="close").sort_index()
    full = close.columns[close.notna().all(axis=0)]
    dropped = len(close.columns) - len(full)

    out = {"dates": np.asarray(close.index),
           "tickers": np.asarray(full),
           "dropped_incomplete": int(dropped)}
    for field in ("close", "open", "intraday", "volume"):
        m = df.pivot(index="date", columns="t", values=field).sort_index()
        out[field] = m[full].to_numpy(dtype=float)
    return out


# ── formation, vectorised over every pair at once ──────────────────────────

def formation_scores(logp: np.ndarray) -> dict:
    """Score EVERY pair (i, j) on one trailing window. logp is (W, N).

    Returns, each (N, N) with entry [i, j] describing the spread
    e = logp_i - beta_ij * logp_j:

        ssd      normalised-price distance (Gatev). Lower is closer.
        beta     OLS hedge ratio of i on j.
        df_t     Dickey-Fuller t-statistic on the residual. More negative is
                 more stationary.
        mean/sd  the spread's own trailing mean and sd, for the z-score.

    WHY THERE IS NO LOOP OVER PAIRS. The DF regression is bilinear in the
    data, so every sum it needs is an entry of a cross-moment matrix:

        e_t      = x_i,t - b x_j,t                       (demeaned)
        S[i,j]   = sum_t x_i,t x_j,t
        L[i,j]   = sum_t x_i,t x_j,t-1
        D[i,j]   = sum_t dx_i,t dx_j,t

    so sum(e_t e_{t-1}), sum(e_{t-1}^2) and sum((de_t)^2) are all quadratic
    forms in b built from S, L and D. 166,753 pairs resolve in three matrix
    multiplies instead of 166,753 regressions.
    """
    W, N = logp.shape
    x = logp - logp.mean(axis=0, keepdims=True)

    S = x.T @ x                              # contemporaneous
    var_j = np.diag(S)
    with np.errstate(divide="ignore", invalid="ignore"):
        beta = S / var_j[None, :]            # beta[i,j] = cov(i,j)/var(j)

    # Normalised-price distance (Gatev): both series scaled to start at 1.
    norm = np.exp(logp - logp[0:1, :])
    G = norm.T @ norm
    g = np.diag(G)
    ssd = g[:, None] + g[None, :] - 2.0 * G

    # Lagged and differenced cross-moments, on the SAME rows so the three
    # matrices are conformable: t = 1..W-1.
    a, b_ = x[1:], x[:-1]
    dx = a - b_
    S1 = b_.T @ b_                           # sum e_{t-1} e_{t-1}
    L1 = dx.T @ b_                           # sum de_t   e_{t-1}
    D1 = dx.T @ dx                           # sum de_t   de_t

    def quad(M, transpose_mixed=True):
        """[i,j] entry of the quadratic form for e = x_i - b x_j."""
        Mii = np.diag(M)[:, None]
        Mjj = np.diag(M)[None, :]
        Mij = M
        Mji = M.T if transpose_mixed else M
        return Mii - beta * Mij - beta * Mji + beta * beta * Mjj

    den = quad(S1)                           # sum e_{t-1}^2
    num = quad(L1, transpose_mixed=True)     # sum de_t e_{t-1}
    dd = quad(D1)                            # sum de_t^2

    with np.errstate(divide="ignore", invalid="ignore"):
        gamma = num / den                    # DF slope; rho - 1
        rss = dd - gamma * gamma * den       # residual sum of squares
        n_obs = W - 1
        sigma2 = rss / max(n_obs - 1, 1)
        se = np.sqrt(sigma2 / den)
        df_t = gamma / se

    spread_var = quad(S) / max(W - 1, 1)
    sd = np.sqrt(np.maximum(spread_var, 0.0))
    # e is built from DEMEANED logs, so its window mean is zero by
    # construction; the z-score below re-centres on the same basis.
    return {"ssd": ssd, "beta": beta, "df_t": df_t, "sd": sd,
            "centre": logp.mean(axis=0)}


def choose_pairs(scores: dict, method: str, k: int,
                 min_sd: float = 1e-6) -> list:
    """The k best pairs by the method's own score, i < j, finite only."""
    key = {"distance": "ssd", "cointegration": "df_t"}[method]
    M = np.array(scores[key], dtype=float)
    N = M.shape[0]
    iu = np.triu_indices(N, k=1)
    vals = M[iu]
    sd = scores["sd"][iu]
    ok = np.isfinite(vals) & np.isfinite(sd) & (sd > min_sd)
    if not ok.any():
        return []
    idx = np.argsort(vals[ok])               # both scores: smaller is better
    ii, jj = iu[0][ok][idx], iu[1][ok][idx]
    return list(zip(ii[:k].tolist(), jj[:k].tolist()))


# ── the trade ──────────────────────────────────────────────────────────────

def session_signals(pairs, scores, log_open_row, threshold):
    """Which trades the open's spread deviation calls for, at one session.

    SIGNAL ONLY -- it deliberately does not look at the outcome. Which trades
    are taken is identical under the placebo (pairs are still chosen by real
    co-movement, and the z-score still comes from real prices); only WHOSE
    return each leg earns changes. Separating the two lets one expensive
    signal pass serve every placebo replicate, which is what makes a
    placebo-max over 166,753 candidate pairs affordable at all.
    """
    out = []
    beta, sd, centre = scores["beta"], scores["sd"], scores["centre"]
    for i, j in pairs:
        b, s = beta[i, j], sd[i, j]
        if not np.isfinite(b) or not np.isfinite(s) or s <= 0:
            continue
        oi, oj = log_open_row[i], log_open_row[j]
        if not (np.isfinite(oi) and np.isfinite(oj)):
            continue
        # Spread at the open, on the same demeaned basis as formation.
        z = ((oi - centre[i]) - b * (oj - centre[j])) / s
        if z <= -threshold:
            side = +1          # spread is low: long i, short j
        elif z >= threshold:
            side = -1          # spread is high: short i, long j
        else:
            continue
        out.append({"i": int(i), "j": int(j), "z": float(z), "side": side})
    return out


def generate_signals(wide: dict, method: str, threshold: float) -> list:
    """Walk the panel forward once, emitting the trades the signal calls for."""
    close, op = wide["close"], wide["open"]
    T = close.shape[0]
    logc, logo = np.log(close), np.log(op)
    sigs = []
    scores = pairs = None
    for t in range(FORM_WINDOW, T):
        if (t - FORM_WINDOW) % REFIT_EVERY == 0 or scores is None:
            window = logc[t - FORM_WINDOW:t]          # strictly before t
            if not np.isfinite(window).all():
                continue
            scores = formation_scores(window)
            pairs = choose_pairs(scores, method, TOP_K)
        if not pairs:
            continue
        for g in session_signals(pairs, scores, logo[t], threshold):
            g["t"] = int(t)
            sigs.append(g)
    return sigs


def attribute_shifted(signals: list, intra: np.ndarray, shift: int) -> list:
    """The STRICTER placebo, added day-96 after the registered one proved too
    easy a bar -- disclosed as an addition, and it can only make the test
    harder, which is the one safe direction to move.

    The registered placebo permutes WHICH NAME'S returns each leg earns. That
    destroys the pairing, but it also destroys CO-MOVEMENT: a randomly matched
    pair's leg difference is a high-variance, zero-mean quantity, so after the
    10bp round trip the placebo sits near -0.10% and almost anything clears it.
    It answers "do real pairs beat random pairs", which is trivially yes and is
    not the question.

    This one keeps the pair AND its own returns, and moves only the SESSION the
    return is taken from. Co-movement, each name's return distribution and the
    selection out of 166,753 candidates all survive; the single thing destroyed
    is the link between the z-score observed at THIS open and what happened on
    THIS day. That is the strategy's actual claim.
    """
    T = intra.shape[0]
    out = []
    for s in signals:
        t = (s["t"] + shift) % T
        ri, rj = intra[t][s["i"]], intra[t][s["j"]]
        if not (np.isfinite(ri) and np.isfinite(rj)):
            continue
        gross = s["side"] * (ri - rj)
        out.append({**s, "gross": float(gross),
                    "net": float(gross - COST_PCT)})
    return out


def breakeven_bps(trades: list) -> float | None:
    """The round-trip cost at which this cell's GROSS edge is exactly consumed.

    Reported as a sensitivity, never as a rescue. Finding the cost that would
    make a rejected result profitable is not a result; it is the shape of the
    question a cheaper venue would have to answer.
    """
    if not trades:
        return None
    return float(np.mean([t["gross"] for t in trades]) * 100.0)


def attribute(signals: list, intra: np.ndarray,
              permute: np.ndarray | None = None) -> list:
    """Give each signalled trade its return.

    `permute` is the registered placebo: the pair is still chosen by real
    co-movement and the z-score is still real, but each leg earns the intraday
    return of a DIFFERENT name from the same session. That preserves every
    name's own return distribution and the day's cross-section, and destroys
    only the link between the pair selected and what it earned -- which is
    exactly the advantage that comes from getting to pick a winner out of
    166,753 candidates.

    Cost is SUBTRACTED, not clipped. See the module docstring.
    """
    out = []
    for s in signals:
        row = intra[s["t"]]
        ri = row[permute[s["i"]]] if permute is not None else row[s["i"]]
        rj = row[permute[s["j"]]] if permute is not None else row[s["j"]]
        if not (np.isfinite(ri) and np.isfinite(rj)):
            continue
        gross = s["side"] * (ri - rj)
        out.append({**s, "gross": float(gross),
                    "net": float(gross - COST_PCT)})
    return out


def run_backtest(wide: dict, method: str, threshold: float,
                 permute: np.ndarray | None = None) -> list:
    return attribute(generate_signals(wide, method, threshold),
                     wide["intraday"], permute)


# ── statistics ─────────────────────────────────────────────────────────────

def session_block_bootstrap(trades: list, field: str = "net",
                            draws: int = BOOT, seed: int = SEED) -> dict:
    """Resample SESSIONS, not trades. Every pair open on one day shares that
    day's move, so trades within a session are not independent draws --
    resampling them individually is what turned |t|=7.15 into 2.14 on day-85.
    """
    if not trades:
        return {"mean": None, "lo": None, "hi": None, "t": None, "se": None,
                "n": 0, "sessions": 0}
    by_session: dict = {}
    for tr in trades:
        by_session.setdefault(tr["t"], []).append(tr[field])
    keys = sorted(by_session)
    sums = np.array([np.sum(by_session[k]) for k in keys], dtype=float)
    counts = np.array([len(by_session[k]) for k in keys], dtype=float)
    mean = float(sums.sum() / counts.sum())

    rng = np.random.default_rng(seed)
    n = len(keys)
    idx = rng.integers(0, n, size=(draws, n))
    boot = sums[idx].sum(axis=1) / counts[idx].sum(axis=1)
    lo, hi = np.percentile(boot, [2.5, 97.5])
    se = float(boot.std(ddof=1))
    return {"mean": mean, "lo": float(lo), "hi": float(hi),
            "se": se, "t": (mean / se if se > 0 else None),
            "n": int(counts.sum()), "sessions": n}


def mde(se: float, bar_t: float = ADOPT_T) -> float:
    """Rule 10. The smallest effect this sample could have resolved. A null
    without it is not a null, it is an unlabelled UNDERPOWERED."""
    return bar_t * se


def quarters(trades: list, field: str = "net", blocks: int = BLOCKS) -> list:
    """Chronological blocks, by session so a session never splits."""
    if not trades:
        return []
    keys = sorted({tr["t"] for tr in trades})
    cut = np.array_split(np.array(keys), blocks)
    out = []
    for c in cut:
        s = set(c.tolist())
        vals = [tr[field] for tr in trades if tr["t"] in s]
        out.append(float(np.mean(vals)) if vals else None)
    return out


def planted_control(trades: list, edge_pct: float = 0.10,
                    seed: int = SEED) -> dict:
    """Rule 10, both halves: a harness that cannot see a planted edge reports
    UNDERPOWERED, not NULL -- and the control measures `edge / sd`, NEVER
    `(mean + edge) / sd`, which would credit the real mean to the control."""
    if not trades:
        return {"detected": False, "t": None, "edge": edge_pct}
    planted = [{**tr, "net": tr["net"] + edge_pct} for tr in trades]
    b = session_block_bootstrap(planted)
    se = b["se"]
    t_edge = (edge_pct / se) if se and se > 0 else None
    return {"detected": bool(t_edge is not None and t_edge >= ADOPT_T),
            "t": t_edge, "edge": edge_pct, "se": se}


def naive_public_recipe(wide: dict, top_k: int = TOP_K) -> dict:
    """What the standard public implementation reports on the SAME data.

    Not a strawman -- this is the recipe, and it is what the search results
    describe: "examines all possible pair combinations of time-series for signs
    of cointegration and runs a trading algorithm over each cointegrated pair."
    Four defects, each of which alone is enough to manufacture a result:

      1. FULL-SAMPLE FORMATION. Hedge ratio and spread mean/sd estimated over
         the whole panel, then "backtested" on that same panel. Every trade
         knows the future.
      2. SELECT THEN TEST ON THE SAME DATA. The best pairs are chosen by a
         statistic computed on the very returns used to score them.
      3. NO COST. The 10bp round trip is simply absent.
      4. NO PLACEBO. The number is compared to zero, so the advantage of
         picking the best of hundreds of candidates is counted as edge.

    Kept in the repo, and run beside the honest number, so the gap between the
    two is a measurement rather than an assertion.
    """
    logc = np.log(wide["close"])
    logo = np.log(wide["open"])
    intra = wide["intraday"]
    scores = formation_scores(logc)                 # (1) the WHOLE panel
    chosen = choose_pairs(scores, "cointegration", top_k)   # (2) same data
    beta, sd, centre = scores["beta"], scores["sd"], scores["centre"]
    rows = []
    for t in range(logc.shape[0]):
        for i, j in chosen:
            b, s = beta[i, j], sd[i, j]
            if not np.isfinite(b) or not np.isfinite(s) or s <= 0:
                continue
            z = ((logo[t][i] - centre[i]) - b * (logo[t][j] - centre[j])) / s
            if abs(z) < 2.0:
                continue
            side = 1 if z <= 0 else -1
            ri, rj = intra[t][i], intra[t][j]
            if not (np.isfinite(ri) and np.isfinite(rj)):
                continue
            rows.append(side * (ri - rj))           # (3) no cost
    if not rows:
        return {"n": 0, "mean": None}
    arr = np.array(rows)
    return {"n": len(arr), "mean": float(arr.mean()),      # (4) vs zero
            "hit_rate": float((arr > 0).mean()),
            "t_naive_iid": float(arr.mean() / (arr.std(ddof=1) / np.sqrt(len(arr))))}
