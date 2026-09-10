#!/usr/bin/env python3
"""Day-95 H2 — tide-residualized features in the parity k-NN. SHADOW ONLY.

Registered in PREREGISTER_day95b.md (committed before any outcome was computed;
the H2 precondition check is recorded there as CLEAR). The question: replace
raw `r0`/`gap` with their index-residualized counterparts

    r0'  = r0  - beta_r0  * r0_XIU
    gap' = gap - beta_gap * gap_XIU        beta from the trailing 60 sessions

in the PARITY k-NN (validate_ceiling.knn_scores, the live arithmetic), on the
hourly two-feature pool — the set day-43 actually tested. Comparison is the
PAIRED out-of-sample AUC against the raw-feature run on identical rows.

Registered statistics, all printed always:
  - AUC influence values aggregated WITHIN session (same-session rows are not
    independent; clustered SE from validate_ceiling.clustered_se)
  - deterministic block bootstrap: 20-session blocks, 2,000 draws, seed 95
  - four chronological development blocks, delta reported per block
  - planted +2-AUC-point control, reported in edge/SE form
  - sign-flip placebo, reported at its 95th percentile
  - MDE = (3.5 + 0.8416212336) * SE  (printed always, valid or not)

This is a research harness on a proxy hourly panel. It is not the live
pipeline, not net P&L, and NO selection change is authorised by its output.
Sandbox execution is expected to be BLOCKED (no network); that is recorded in
data/day95_residual_results.json rather than hidden.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import math
import os
import sys
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from validate_ceiling import (auc_influence, clustered_se, knn_scores,  # noqa: E402
                              load_pool)
from validate_exit import SCRATCH  # noqa: E402

FEATS2 = ["r0", "gap"]
RES_FEATS = ["r0_res", "gap_res"]
SEED = 95
BETA_WINDOW = 60
BLOCK_SESSIONS = 20
BOOT_DRAWS = 2000
PLACEBO_DRAWS = 2000
FOLDS = 5
MIN_TRAIN_SESSIONS = 120
RESULTS = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                       "data", "day95_residual_results.json")


# ------------------------------------------------------------- residualization
def index_sessions(index_df: pd.DataFrame) -> pd.DataFrame:
    """Per-session index features: date -> (r0_XIU, gap_XIU)."""
    need = {"date", "r0", "gap"}
    if not need <= set(index_df.columns):
        raise ValueError(f"index frame needs {need}, got {set(index_df.columns)}")
    out = (index_df[["date", "r0", "gap"]]
           .dropna()
           .drop_duplicates("date")
           .sort_values("date")
           .reset_index(drop=True))
    if out.empty:
        raise ValueError("index frame has no usable sessions")
    return out


def residualize(df: pd.DataFrame, idx: pd.DataFrame,
                beta_window: int = BETA_WINDOW) -> pd.DataFrame:
    """r0_res/gap_res vs the index, beta from the trailing `beta_window` sessions.

    POINT-IN-TIME: a row's beta uses only sessions strictly before its date
    (the live engine could have computed exactly this on the morning in
    question). Rows with fewer than 5 overlapping trailing sessions are NaN
    and drop out downstream — counted, never back-filled (rule 2).
    """
    if beta_window < 5:
        raise ValueError("beta_window must be >= 5")
    xi = idx.set_index("date")[["r0", "gap"]]
    out = df.copy()
    out["r0_res"] = np.nan
    out["gap_res"] = np.nan
    for t, grp in out.groupby("t"):
        grp = grp.sort_values("date")
        r0 = grp["r0"].to_numpy(float)
        gap = grp["gap"].to_numpy(float)
        x_r0 = xi.reindex(grp["date"])["r0"].to_numpy(float)
        x_gap = xi.reindex(grp["date"])["gap"].to_numpy(float)
        n = len(grp)
        res_r0 = np.full(n, np.nan)
        res_gap = np.full(n, np.nan)
        for i in range(n):
            lo = max(0, i - beta_window)
            m = np.isfinite(r0[lo:i]) & np.isfinite(x_r0[lo:i])
            if m.sum() < 5:
                continue
            var = np.var(x_r0[lo:i][m])
            if var <= 0:
                continue
            beta_r0 = np.cov(r0[lo:i][m], x_r0[lo:i][m])[0, 1] / var
            if np.isfinite(x_r0[i]) and np.isfinite(r0[i]):
                res_r0[i] = r0[i] - beta_r0 * x_r0[i]
            m2 = np.isfinite(gap[lo:i]) & np.isfinite(x_gap[lo:i])
            if m2.sum() < 5:
                continue
            var2 = np.var(x_gap[lo:i][m2])
            if var2 <= 0:
                continue
            beta_gap = np.cov(gap[lo:i][m2], x_gap[lo:i][m2])[0, 1] / var2
            if np.isfinite(x_gap[i]) and np.isfinite(gap[i]):
                res_gap[i] = gap[i] - beta_gap * x_gap[i]
        out.loc[grp.index, "r0_res"] = res_r0
        out.loc[grp.index, "gap_res"] = res_gap
    return out


# ------------------------------------------------------------- walk-forward
def knn_walk_forward(df: pd.DataFrame, feats: list,
                     folds: int = FOLDS,
                     min_train: int = MIN_TRAIN_SESSIONS) -> tuple:
    """Whole-session expanding folds, parity k-NN only.

    Returns (y, scores, sessions) pooled out-of-sample — the same fold
    discipline as validate_ceiling.walk_forward, minus the other learners."""
    sess = sorted(df["date"].unique())
    if len(sess) < min_train + folds:
        raise ValueError(f"only {len(sess)} sessions — need >= {min_train + folds}")
    edges = np.linspace(min_train, len(sess), folds + 1).astype(int)
    ys, ss, ds = [], [], []
    for a, b in zip(edges[:-1], edges[1:]):
        if b <= a:
            continue
        tr = df[df["date"].isin(sess[:a])]
        te = df[df["date"].isin(sess[a:b])]
        if te.empty or len(tr) < 500:
            raise ValueError(f"fold {sess[a]}: {len(tr)} train / {len(te)} test rows")
        s = knn_scores(tr[feats].to_numpy(float), tr["y"].to_numpy(int),
                       te[feats].to_numpy(float))
        if not np.isfinite(s).all():
            raise ValueError(f"k-NN abstained on fold {sess[a]} (thin training)")
        ys.append(te["y"].to_numpy(int))
        ss.append(s)
        ds.append(te["date"].to_numpy())
    if not ys:
        raise ValueError("no evaluable out-of-sample folds")
    return np.concatenate(ys), np.concatenate(ss), np.concatenate(ds)


# ------------------------------------------------------------- registered stats
def session_deltas(y, s_test, s_ref, sessions) -> pd.DataFrame:
    """Paired AUC delta aggregated WITHIN session (chronological).

    Per-row AUC contribution is `influence + value` (single-arm influences sum
    to zero, so the raw influence DIFFERENCE would sum to zero and hide the
    delta — a subtlety day-95 caught in review). Returns a DataFrame with
    per-session contribution sums `g` and row counts `n`, so
    delta_auc = sum(g) / sum(n) == auc(y, s_test) - auc(y, s_ref) exactly."""
    v_t, i_t = auc_influence(y, s_test)
    v_r, i_r = auc_influence(y, s_ref)
    if not (np.isfinite(v_t) and np.isfinite(v_r)):
        raise ValueError("degenerate AUC (single-class scores or labels)")
    per_row = (i_t + v_t) - (i_r + v_r)
    df = pd.DataFrame({"g": per_row, "n": 1, "s": sessions})
    agg = df.groupby("s").agg(g=("g", "sum"), n=("n", "sum"))
    return agg.reindex(sorted(agg.index))


def block_bootstrap(per_session: pd.DataFrame, block: int = BLOCK_SESSIONS,
                    draws: int = BOOT_DRAWS, seed: int = SEED) -> dict:
    """Deterministic 20-session block bootstrap of the paired AUC delta."""
    g = per_session["g"].to_numpy(float)
    nrows = per_session["n"].to_numpy(float)
    n = len(g)
    if n < 2 * block:
        raise ValueError(f"{n} sessions cannot form two {block}-session blocks")
    blocks_g = [g[i:i + block] for i in range(0, n - block + 1, block)]
    blocks_n = [nrows[i:i + block] for i in range(0, n - block + 1, block)]
    nblocks = math.ceil(n / block)
    rng = np.random.default_rng(seed)
    reps = np.empty(draws)
    for i in range(draws):
        pick = rng.integers(0, len(blocks_g), size=nblocks)
        reps[i] = (np.concatenate([blocks_g[j] for j in pick]).sum()
                   / np.concatenate([blocks_n[j] for j in pick]).sum())
    return {"block_sessions": block, "draws": draws, "seed": seed,
            "ci_lo": float(np.percentile(reps, 2.5)),
            "ci_hi": float(np.percentile(reps, 97.5)),
            "replicate_mean": float(reps.mean())}


def sign_flip_placebo(per_session: pd.DataFrame, draws: int = PLACEBO_DRAWS,
                      seed: int = SEED) -> dict:
    """95th percentile of the paired delta under random per-session sign flips
    of the CENTERED session contributions (a placebo has no business keeping
    the real sign of the measured delta)."""
    g = per_session["g"].to_numpy(float)
    nrows = per_session["n"].to_numpy(float)
    centered = g - nrows * (g.sum() / nrows.sum())
    rng = np.random.default_rng(seed)
    signs = rng.choice([-1.0, 1.0], size=(draws, len(centered)))
    dist = (signs * centered).sum(axis=1) / nrows.sum()
    return {"draws": draws, "seed": seed,
            "p95": float(np.percentile(dist, 95)),
            "p99": float(np.percentile(dist, 99))}


def plant_edge(y: np.ndarray, scores: np.ndarray,
               target: float = 0.02) -> np.ndarray:
    """Deterministically shift scores to add `target` AUC (label-aligned).

    Bisection on the shift magnitude; no randomness, so the control is
    reproducible. Used ONLY for the planted positive control."""
    y = np.asarray(y, int)
    s = np.asarray(scores, float)
    direction = (2 * y - 1).astype(float)

    def lift(c):
        from validate_ceiling import auc
        return auc(y, s + c * direction) - auc(y, s)

    if lift(0) > target:
        raise ValueError("scores already exceed the planted target")
    hi = 1.0
    while lift(hi) < target:
        hi *= 2
        if hi > 1e6:
            raise ValueError("planted edge unreachable")
    lo = 0.0
    for _ in range(60):
        mid = (lo + hi) / 2
        if lift(mid) < target:
            lo = mid
        else:
            hi = mid
    # Rounded k-NN scores carry ties, so the lift is a staircase: bisection
    # converges to a step edge and the midpoint can sit well below target.
    # Take whichever endpoint lands closest to the registered +0.02.
    c = lo if abs(lift(lo) - target) <= abs(lift(hi) - target) else hi
    return s + c * direction


def four_blocks(y, s_res, s_raw, sessions) -> list:
    """Paired delta within each of four chronological OOS blocks."""
    order = sorted(pd.unique(sessions))
    edges = np.linspace(0, len(order), 5).astype(int)
    out = []
    for a, b in zip(edges[:-1], edges[1:]):
        blk = set(order[a:b])
        m = np.isin(sessions, list(blk))
        g = session_deltas(y[m], s_res[m], s_raw[m], sessions[m])
        out.append({"from": order[a], "to": order[b - 1],
                    "sessions": int(len(blk)),
                    "n_rows": int(m.sum()),
                    "delta_auc": float(g["g"].sum() / g["n"].sum()),
                    "se": float(clustered_se(auc_influence_pair(y[m], s_res[m], s_raw[m]),
                                             sessions[m])[0])})
    return out


def auc_influence_pair(y, s_test, s_ref):
    _v1, i_t = auc_influence(y, s_test)
    _v2, i_r = auc_influence(y, s_ref)
    return i_t - i_r


def paired_report(y, s_res, s_raw, sessions) -> dict:
    """All registered statistics for the residualized-vs-raw comparison."""
    from scipy.stats import norm

    g = session_deltas(y, s_res, s_raw, sessions)
    diff = auc_influence_pair(y, s_res, s_raw)
    se, n_sess = clustered_se(diff, sessions)
    estimate = float(g["g"].sum() / g["n"].sum())
    edge_over_se = estimate / se if se and np.isfinite(se) and se > 0 else float("nan")
    boot = block_bootstrap(g)
    placebo = sign_flip_placebo(g)
    critical = 3.5  # registered MDE form: (3.5 + z_0.8) * SE
    mde = (3.5 + 0.8416212336) * se if np.isfinite(se) else float("nan")
    # Planted +2-AUC-point control, edge/SE form: can this harness SEE an edge?
    s_ctl = plant_edge(y, s_res, 0.02)
    g_ctl = session_deltas(y, s_ctl, s_raw, sessions)
    se_ctl, _ = clustered_se(auc_influence_pair(y, s_ctl, s_raw), sessions)
    ctl_edge = float(g_ctl["g"].sum() / g_ctl["n"].sum())
    ctl_eos = ctl_edge / se_ctl if se_ctl and se_ctl > 0 else float("nan")
    return {"delta_auc": estimate, "se": se, "sessions": int(n_sess),
            "n_rows": int(len(y)), "edge_over_se": edge_over_se,
            "block_bootstrap": boot, "sign_flip_placebo": placebo,
            "placebo_exceeded_at_p95": bool(np.isfinite(estimate)
                                            and estimate > placebo["p95"]),
            "mde": mde, "mde_form": "(3.5 + 0.8416212336) * SE",
            "z_critical": critical,
            "planted_control": {"target_auc": 0.02, "edge": ctl_edge,
                                "edge_over_se": ctl_eos,
                                "detected": bool(np.isfinite(ctl_eos)
                                                 and ctl_eos > critical)},
            "development_blocks": four_blocks(y, s_res, s_raw, sessions)}


# ------------------------------------------------------------- acquisition
def acquire_pool(pool_path: str, as_of: str | None):
    """Load the hourly two-feature pool; build it first if absent (host only)."""
    if not os.path.exists(pool_path):
        import build_pool
        cache = os.path.dirname(pool_path) or SCRATCH
        os.makedirs(cache, exist_ok=True)
        uni = build_pool.constituents(cache)
        build_pool.build(uni, "1h", "720d", 0, 5, pool_path)
    df, feats = load_pool(pool_path, feature_train_sessions=MIN_TRAIN_SESSIONS,
                          as_of=as_of)
    for f in FEATS2:
        if f not in feats:
            raise ValueError(f"pool is missing usable '{f}' — cannot run H2")
    return df


def acquire_index(cache: str, as_of: str | None) -> pd.DataFrame:
    """XIU.TO hourly sessions as the tide leg, cached in the scratch dir."""
    path = os.path.join(cache, "xiu_1h_features.csv")
    if os.path.exists(path):
        return pd.read_csv(path)
    import build_pool
    from adapters import YahooDirectAdapter
    a = YahooDirectAdapter(exchange_tz="America/Toronto")
    bars = a._bars_df(a._chart("XIU.TO", "1h", "720d"))
    rows = build_pool.rows_at(bars, "XIU.TO", 0, 5)
    df = pd.DataFrame(rows)
    if df.empty:
        raise RuntimeError("XIU.TO hourly fetch returned no sessions")
    df.to_csv(path, index=False)
    return df


# ------------------------------------------------------------- driver
def evaluate(df: pd.DataFrame, idx: pd.DataFrame) -> dict:
    """The registered comparison on a supplied pool + index. Pure given data."""
    idx_sessions = index_sessions(idx)
    df = df[df["date"].isin(set(idx_sessions["date"]))].copy()
    if df.empty:
        raise ValueError("no pool sessions overlap the index frame")
    res = residualize(df, idx_sessions)
    before = len(res)
    res = res.dropna(subset=RES_FEATS)
    dropped = before - len(res)
    y_r, s_r, d_r = knn_walk_forward(res, RES_FEATS)
    y_w, s_w, d_w = knn_walk_forward(res, FEATS2)
    # Raw arm reuses the SAME rows (residual warm-up rows excluded from both),
    # so the paired comparison is row-for-row.
    if not (np.array_equal(y_r, y_w) and np.array_equal(d_r, d_w)):
        raise ValueError("paired arms do not share identical rows")
    out = paired_report(y_r, s_r, s_w, d_r)
    from validate_ceiling import auc
    out["auc_residualized"] = float(auc(y_r, s_r))
    out["auc_raw"] = float(auc(y_w, s_w))
    out["warmup_rows_dropped"] = int(dropped)
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--pool", default=os.path.join(SCRATCH, "pool_1h.csv"))
    ap.add_argument("--index-cache", default=SCRATCH)
    ap.add_argument("--as-of", help="exclusive completed-session cutoff YYYY-MM-DD")
    ap.add_argument("--output", default=RESULTS)
    a = ap.parse_args(argv)

    print("=" * 74)
    print("DAY-95 H2 — tide-residualized [r0, gap] vs raw, parity k-NN, hourly pool")
    print("SHADOW RESEARCH. No adoption from this output. Registration:")
    print("PREREGISTER_day95b.md (precondition: CLEAR, recorded there).")
    print("=" * 74)
    record = {"registration": "PREREGISTER_day95b.md", "seed": SEED,
              "block_sessions": BLOCK_SESSIONS, "draws": BOOT_DRAWS,
              "label": "HOURLY-PROXY SHADOW RESEARCH; NO ADOPTION",
              "generated_at": dt.datetime.now(ZoneInfo("UTC")).isoformat()}
    try:
        df = acquire_pool(a.pool, a.as_of)
        idx = acquire_index(a.index_cache, a.as_of)
    except Exception as exc:
        # Sandbox runs are expected here: record the error CLASS, never fake it.
        record.update(status="BLOCKED", verdict="BLOCKED",
                      reason="pool/index acquisition failed; fail closed "
                             "(rule 2), nothing computed",
                      errors=[{"error": type(exc).__name__,
                               "detail": str(exc)[:400]}])
        _write(a.output, record)
        print(f"BLOCKED — {type(exc).__name__}: {str(exc)[:200]}")
        print("Recorded in", a.output)
        return 3
    out = evaluate(df, idx)
    record.update(status="COMPLETE", **out)
    _write(a.output, record)
    print(f"paired delta AUC {out['delta_auc']:+.4f}  SE {out['se']:.4f}  "
          f"edge/SE {out['edge_over_se']:+.2f}")
    print(f"block bootstrap 95%% CI [{out['block_bootstrap']['ci_lo']:+.4f}, "
          f"{out['block_bootstrap']['ci_hi']:+.4f}]  "
          f"placebo p95 {out['sign_flip_placebo']['p95']:+.4f}")
    print(f"MDE (3.5 + 0.8416212336) * SE = {out['mde']:.4f}  (printed always)")
    ctl = out["planted_control"]
    print(f"planted +0.02 AUC control: edge {ctl['edge']:+.4f}, "
          f"edge/SE {ctl['edge_over_se']:+.2f} "
          f"({'DETECTED' if ctl['detected'] else 'NOT DETECTED — UNDERPOWERED'})")
    for blk in out["development_blocks"]:
        print(f"  block {blk['from']}..{blk['to']}: delta {blk['delta_auc']:+.4f}")
    if not ctl["detected"]:
        print("CONTROL FAILED: this harness cannot see a planted +2-AUC-point "
              "edge, so a null here means UNDERPOWERED, not no effect.")
        return 2
    verdict = ("SIGNAL ABOVE PLACEBO" if out["placebo_exceeded_at_p95"]
               and out["edge_over_se"] > 3.5 else "NO REGISTERED IMPROVEMENT")
    print(verdict, "— shadow research; no selection change is authorised.")
    return 0


def _write(path: str, record: dict) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as fh:
        json.dump(record, fh, indent=2, allow_nan=False, default=str)


if __name__ == "__main__":
    raise SystemExit(main())
