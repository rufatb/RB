#!/usr/bin/env python3
"""
Research comparison of fixed learners on historical bar-to-close labels.

This is exploratory model evaluation, not an executable strategy backtest or
proof of an information-theoretic ceiling. Current-constituent pools can bias
both absolute performance AND relative model comparisons; paired rows do not
remove survivorship bias. Hourly pools do not represent the 09:46 entry, and
none of this harness's labels include spreads, borrow, fees or a market index.

The day-43 output and rejected studies remain historical records. The original
"knn (shipped)" implementation was not the shipped calculation: it used a
training-base-rate prior, unnormalised weighted pseudo-counts, population SD,
and omitted rounding and clipping. It is retained as legacy_knn_scores for
reproducibility. knn_scores now matches the live scorer's default arithmetic;
that does not make this harness's feature engineering or training windows a
replay of production. In particular, vp here is a lagged expanding median,
whereas the live pipeline normalises its training window at the decision date.

Folds split whole sessions chronologically. Inference aggregates AUC influence
values within session instead of treating ticker-rows as independent. Its
normal approximation assumes independent sessions and does not account for
serial dependence, parameter selection or previously inspected data. Reported
MDE is an AUC difference, never a P&L or hit-rate MDE. Finite-study failure to
detect an effect is not proof that no learner or future information can work.
"""

from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from validate_exit import SCRATCH  # noqa: E402

FEATS = ["r0", "gap", "vp"]
KNN_NAME = "knn (parity math)"
MIN_CLUSTERS = 20


# --------------------------------------------------------------- data
def add_vp(df: pd.DataFrame) -> pd.DataFrame:
    """Volume pace = entry-bar volume vs that name's own recent normal.

    Uses an EXPANDING median that is shifted one session back, so a row's vp
    never sees its own volume or any later session's. A plain groupby-median
    would leak the whole sample into every row and quietly inflate every model
    below — the exact mistake this script exists to rule out.
    """
    df = df.sort_values(["t", "date"]).copy()
    med = (df.groupby("t")["v15"]
             .apply(lambda s: s.shift(1).expanding(min_periods=20).median())
             .reset_index(level=0, drop=True))
    df["vp"] = df["v15"] / med.replace(0, np.nan)
    return df


def usable_feats(df: pd.DataFrame, max_zero: float = 0.25) -> list:
    """Which feature columns have usable observations in the supplied sample.

    DAY-43: `vp` is not computable on the 1-hour panel, and the reason is
    specific enough that it was missed twice in opposite directions. Yahoo
    zeroes the volume on ~86% of FIRST hourly bars of a session while later
    bars are ~0.1% zeroed, so the all-bars rate is ~12.5% — a number that looks
    survivable and is, for anything except the entry bar. The 1h pool's entry
    IS the first bar, so 86% of its `v15` values are zero. Measured here rather
    than assumed, and the feature is DROPPED WITH A NOTICE rather than silently
    NaN-ing out its rows (which deleted 145,201 of 145,228 rows on the first
    run of this script) or silently becoming a constant (which is what
    `v15 / (median or 1)` does when the median is itself zero).
    """
    out = []
    for f in FEATS:
        if f == "vp":
            z = float((df["v15"].fillna(0) == 0).mean())
            if z > max_zero:
                print(f"    ! dropping 'vp': {z:.0%} of entry bars have ZERO volume "
                      "in this pool")
                continue
        out.append(f)
    return out


def load_pool(path: str, min_price: float = 5.0,
              feature_train_sessions: int = 120,
              as_of: str | None = None) -> tuple:
    """Read a unique ticker/session pool; current/future sessions are excluded.

    Feature availability is decided only on the initial training sessions.
    A pool has no exact execution timestamp, so same-date outcomes remain
    excluded even after the close. Use the following session's date for a
    completed-day evaluation. No missing or duplicate identifiers are guessed.
    """
    df = pd.read_csv(path)
    if feature_train_sessions < 1:
        raise ValueError("feature_train_sessions must be positive")
    if df[["t", "date"]].isna().any().any():
        raise ValueError("pool has missing ticker/session identifiers")
    if df.duplicated(["t", "date"]).any():
        raise ValueError("pool has duplicate ticker/session rows")
    dates = pd.to_datetime(df["date"], format="%Y-%m-%d", errors="raise")
    if not dates.dt.strftime("%Y-%m-%d").eq(df["date"]).all():
        raise ValueError("session dates must use YYYY-MM-DD")
    cutoff = as_of or datetime.now(ZoneInfo("America/New_York")).date().isoformat()
    parsed_cutoff = pd.to_datetime(cutoff, format="%Y-%m-%d", errors="raise")
    if pd.isna(parsed_cutoff) or parsed_cutoff.strftime("%Y-%m-%d") != cutoff:
        raise ValueError("as_of must be a YYYY-MM-DD session date")
    incomplete = df["date"] >= cutoff
    if incomplete.any():
        print(f"    ! excluding {int(incomplete.sum()):,} current/future rows "
              f"at session cutoff {cutoff}")
    df = df[~incomplete]
    eligible = (df["px"] >= min_price) & df["r1"].notna() & df["r0"].notna()
    if not eligible.all():
        print(f"    ! excluding {int((~eligible).sum()):,} rows below the price "
              "floor or missing an entry return/outcome")
    df = df[eligible]
    initial = sorted(df["date"].unique())[:feature_train_sessions]
    feats = usable_feats(df[df["date"].isin(initial)])
    if "vp" in feats:
        df = add_vp(df)
    before = len(df)
    df = df.replace([np.inf, -np.inf], np.nan).dropna(subset=feats + ["r1"])
    if len(df) != before:
        print(f"    ! excluding {before - len(df):,} rows with missing/nonfinite "
              "features or labels (including volume warm-up)")
    df["y"] = (df["r1"] > 0).astype(int)
    return df.sort_values("date").reset_index(drop=True), feats


# --------------------------------------------------------------- metrics
def auc(y: np.ndarray, s: np.ndarray) -> float:
    """Rank AUC; ties get the average rank (scipy-free, exact)."""
    y = np.asarray(y)
    n1, n0 = int(y.sum()), int((1 - y).sum())
    if n1 == 0 or n0 == 0:
        return float("nan")
    r = pd.Series(s).rank().to_numpy()
    return (r[y == 1].sum() - n1 * (n1 + 1) / 2) / (n1 * n0)


def brier(y: np.ndarray, p: np.ndarray) -> float:
    return float(np.mean((np.asarray(p) - np.asarray(y)) ** 2))


# --------------------------------------------------------------- models
def legacy_knn_scores(Xtr, ytr, Xte, k: int = 60, m: int = 20) -> np.ndarray:
    """Day-43 scorer retained unchanged; NOT the shipped k-NN calculation."""
    mu, sd = Xtr.mean(0), Xtr.std(0)
    sd[sd == 0] = 1
    Ztr, Zte = (Xtr - mu) / sd, (Xte - mu) / sd
    base = float(ytr.mean())
    out = np.empty(len(Zte))
    for i, z in enumerate(Zte):
        d2 = ((Ztr - z) ** 2).sum(1)
        idx = np.argpartition(d2, min(k, len(d2) - 1))[:k]
        w = 1 / (1 + np.sqrt(d2[idx]))
        out[i] = (float((w * ytr[idx]).sum()) + m * base) / (float(w.sum()) + m)
    return out


def knn_scores(Xtr, ytr, Xte, k: int | None = None,
               m: int | None = None) -> np.ndarray:
    """Live k-NN arithmetic on supplied features; not full live-pipeline parity.

    Default K/M and clamps are read from r945. Sample standard deviations,
    argsort tie order, fixed 0.5 prior, three-place rounding and clipping match
    r945.knn_probability. A two-feature hourly panel or a synthetic-control
    feature still evaluates a research variant, not the three-feature engine.
    Missing/nonfinite arrays fail explicitly; fewer than 200 training rows
    yield NaN scores, corresponding to the live scorer's abstention.
    """
    from r945 import HARD_CAP, HARD_FLOOR, K, M

    k, m = K if k is None else k, M if m is None else m
    Xtr, Xte = np.asarray(Xtr, dtype=float), np.asarray(Xte, dtype=float)
    ytr = np.asarray(ytr, dtype=float)
    if (Xtr.ndim != 2 or Xte.ndim != 2 or ytr.ndim != 1
            or Xtr.shape[1] != Xte.shape[1] or len(Xtr) != len(ytr)
            or Xtr.shape[1] == 0):
        raise ValueError("incompatible training/target/test shapes")
    if not all(np.isfinite(x).all() for x in (Xtr, Xte, ytr)):
        raise ValueError("k-NN arrays must be finite")
    if not np.isin(ytr, [0, 1]).all():
        raise ValueError("k-NN labels must be binary")
    if (not isinstance(k, (int, np.integer)) or k < 1
            or not np.isfinite(m) or m < 0):
        raise ValueError("k must be a positive integer and m nonnegative")
    if len(Xtr) < 200:
        return np.full(len(Xte), np.nan)
    frame = pd.DataFrame(Xtr)
    mu, sd = frame.mean(), frame.std().replace(0, 1)
    Ztr = ((frame - mu) / sd).to_numpy()
    Zte = ((pd.DataFrame(Xte) - mu) / sd).to_numpy()
    out = np.empty(len(Zte))
    for i, z in enumerate(Zte):
        d2 = ((Ztr - z) ** 2).sum(axis=1)
        idx = np.argsort(d2)[:k]
        weights = 1 / (1 + np.sqrt(d2[idx]))
        vote = float(np.average(ytr[idx], weights=weights))
        p = (vote * k + 0.5 * m) / (k + m)
        out[i] = max(HARD_FLOOR, min(HARD_CAP, round(p, 3)))
    return out


def fit_models(Xtr, ytr, Xte, seed: int = 0) -> dict:
    from sklearn.ensemble import GradientBoostingClassifier
    from sklearn.linear_model import LogisticRegression
    from sklearn.preprocessing import StandardScaler

    sc = StandardScaler().fit(Xtr)
    out = {"baseline": np.full(len(Xte), float(ytr.mean())),
           KNN_NAME: knn_scores(Xtr, ytr, Xte)}
    lr = LogisticRegression(max_iter=2000).fit(sc.transform(Xtr), ytr)
    out["logistic"] = lr.predict_proba(sc.transform(Xte))[:, 1]
    gb = GradientBoostingClassifier(random_state=seed, n_estimators=300,
                                    max_depth=3, learning_rate=0.05,
                                    subsample=0.8).fit(Xtr, ytr)
    out["grad boost"] = gb.predict_proba(Xte)[:, 1]
    return out


# --------------------------------------------------------------- harness
def walk_forward(df: pd.DataFrame, feats: list, folds: int = 5,
                 min_train: int = 120) -> dict:
    """Whole-session folds; returns {model: (y, score, session)} pooled OOS.

    This expanding-fold fit is not the live engine's rolling 60-day retraining
    schedule. Feature columns must already be point-in-time, label-free values.
    """
    if folds < 1 or min_train < 1:
        raise ValueError("folds and min_train must be positive")
    if df["date"].isna().any():
        raise ValueError("missing session identifiers")
    if not np.isfinite(df[feats + ["y"]].to_numpy(float)).all():
        raise ValueError("walk-forward data must be finite")
    if not df["y"].isin([0, 1]).all():
        raise ValueError("walk-forward labels must be binary")
    sess = sorted(df["date"].unique())
    if len(sess) < min_train + folds:
        raise SystemExit(f"only {len(sess)} sessions — need >= {min_train + folds}")
    edges = np.linspace(min_train, len(sess), folds + 1).astype(int)
    acc: dict = {}
    for a, b in zip(edges[:-1], edges[1:]):
        if b <= a:
            continue
        tr = df[df["date"].isin(sess[:a])]
        te = df[df["date"].isin(sess[a:b])]
        if te.empty or len(tr) < 500:
            raise ValueError(f"fold {sess[a]} has only {len(tr)} training rows "
                             f"and {len(te)} test rows; needs 500/nonempty")
        if tr["y"].nunique() < 2:
            raise ValueError(f"training fold ending {sess[a-1]} has one class")
        Xtr, ytr = tr[feats].to_numpy(float), tr["y"].to_numpy(int)
        Xte, yte = te[feats].to_numpy(float), te["y"].to_numpy(int)
        for name, s in fit_models(Xtr, ytr, Xte).items():
            if len(s) != len(yte) or not np.isfinite(s).all():
                raise ValueError(f"{name} produced missing/nonfinite fold scores")
            y_all, s_all, d_all = acc.setdefault(name, ([], [], []))
            y_all.append(yte)
            s_all.append(s)
            d_all.append(te["date"].to_numpy())
        print(f"    fold {sess[a]}..{sess[b-1]}  train {len(tr):,}  test {len(te):,}",
              flush=True)
    if not acc:
        raise ValueError("no evaluable out-of-sample folds")
    return {k: tuple(np.concatenate(part) for part in v) for k, v in acc.items()}


def se_auc(y: np.ndarray) -> float:
    """Legacy IID-row null SE; not valid for correlated ticker-session panels.

    Retained for historical validators. New ceiling reports use session-cluster
    influence uncertainty; importing this function does not certify inference.
    """
    n1, n0 = int(y.sum()), int((1 - y).sum())
    if n1 == 0 or n0 == 0:
        return float("nan")
    return float(np.sqrt((n1 + n0 + 1) / (12.0 * n1 * n0)))


def auc_influence(y: np.ndarray, scores: np.ndarray) -> tuple:
    """AUC and row influences, including score ties, in O(n log n).

    Influences sum to zero; summing them per session retains within-session
    dependence. This is a large-sample sandwich approximation, not exact
    finite-sample confidence and not a serial-correlation adjustment.
    """
    y, scores = np.asarray(y), np.asarray(scores, dtype=float)
    if (y.ndim != 1 or scores.ndim != 1 or len(y) != len(scores)
            or not np.isin(y, [0, 1]).all() or not np.isfinite(scores).all()):
        raise ValueError("AUC requires aligned binary labels and finite scores")
    positives, negatives = np.sort(scores[y == 1]), np.sort(scores[y == 0])
    n1, n0 = len(positives), len(negatives)
    if not n1 or not n0:
        return float("nan"), np.full(len(y), np.nan)
    p = scores[y == 1]
    p_lo = np.searchsorted(negatives, p, side="left")
    p_hi = np.searchsorted(negatives, p, side="right")
    v1 = (p_lo + 0.5 * (p_hi - p_lo)) / n0
    n = scores[y == 0]
    n_lo = np.searchsorted(positives, n, side="left")
    n_hi = np.searchsorted(positives, n, side="right")
    v0 = (n1 - n_hi + 0.5 * (n_hi - n_lo)) / n1
    value = float(v1.mean())
    influence = np.empty(len(y))
    influence[y == 1] = (v1 - value) / n1
    influence[y == 0] = (v0 - value) / n0
    return value, influence


def clustered_se(influence: np.ndarray, sessions: np.ndarray) -> tuple:
    """Session-cluster sandwich SE and number of distinct sessions."""
    influence, sessions = np.asarray(influence), np.asarray(sessions)
    if influence.ndim != 1 or sessions.ndim != 1 or len(influence) != len(sessions):
        raise ValueError("influence/session arrays must align")
    if pd.isna(sessions).any():
        raise ValueError("missing inference session identifiers")
    groups = pd.Series(influence).groupby(sessions, sort=False).sum()
    count = len(groups)
    if count < 2 or not np.isfinite(influence).all():
        return float("nan"), count
    return float(np.sqrt(count / (count - 1) * np.square(groups).sum())), count


def auc_summary(y, scores, sessions, comparisons: int = 1,
                alpha: float = 0.05, reference=None) -> dict:
    """Cluster uncertainty for AUC-.5 or paired AUC improvement over reference.

    MDE80 uses a one-sided Bonferroni critical value plus z(80% power). It is a
    local normal approximation in AUC units, not a net-return adoption gate.
    Degenerate scores or fewer than 20 sessions do not support inference.
    """
    from scipy.stats import norm

    if comparisons < 1 or not 0 < alpha < 0.5:
        raise ValueError("comparisons must be positive and 0 < alpha < .5")
    value, influence = auc_influence(y, scores)
    estimate = value - 0.5
    if reference is not None:
        ref_value, ref_influence = auc_influence(y, reference)
        estimate = value - ref_value
        influence = influence - ref_influence
    se, count = clustered_se(influence, sessions)
    critical = float(norm.isf(alpha / comparisons))
    valid = count >= MIN_CLUSTERS and np.isfinite(se) and se > 0
    return {"auc": value, "estimate": estimate, "se": se,
            "z": estimate / se if valid else float("nan"),
            "lower_bound": estimate - critical * se if valid else float("nan"),
            "mde80": (critical + float(norm.ppf(0.8))) * se if valid else float("nan"),
            "sessions": count, "n": len(y), "valid_inference": bool(valid),
            "critical_z": critical, "comparisons": comparisons}


def report(res: dict, title: str, comparisons: int = 1,
           alpha: float = 0.05) -> dict:
    print(f"\n  {title}")
    print(f"    {'model':<18}{'AUC':>8}{'z(sess)':>10}{'MDE80':>9}"
          f"{'acc':>8}{'Brier':>9}{'days':>7}{'n':>9}")
    out = {}
    for name, (y, scores, sessions) in res.items():
        result = auc_summary(y, scores, sessions, comparisons, alpha)
        accuracy = float(((scores > 0.5).astype(int) == y).mean())
        print(f"    {name:<18}{result['auc']:>8.4f}{result['z']:>10.2f}"
              f"{result['mde80']:>9.4f}{accuracy:>8.1%}{brier(y, scores):>9.4f}"
              f"{result['sessions']:>7}{len(y):>9,}")
        if not result["valid_inference"]:
            print("      ! insufficient independent-session support or degenerate "
                  "scores: no significance/MDE claim")
        out[name] = result
    print("    MDE80 is an AUC difference; costs and index-adjusted P&L are untested.")
    return out


def add_control(df: pd.DataFrame, edge: float, seed: int = 0) -> pd.DataFrame:
    """A synthetic feature carrying a known, weak edge on the REAL labels.

    `ctrl` is standard normal noise shifted by +/- 2.5 * edge according to
    the true outcome. Its sign matches the label with probability Phi(2.5 *
    edge), approximately 0.52 at edge=.02. This is not exactly a 52% coin,
    and P(y=1 | ctrl>0) also depends on class balance. Same rows/folds/models;
    failure to detect it limits conclusions about effects of that shape/size.
    """
    if not np.isfinite(edge) or not 0 <= edge < .5:
        raise ValueError("control edge must be finite and in [0, .5)")
    rng = np.random.default_rng(seed)
    df = df.copy()
    df["ctrl"] = rng.normal(size=len(df)) + (2 * df["y"] - 1) * edge * 2.5
    return df


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pool", default=os.path.join(SCRATCH, "pool_1h.csv"))
    ap.add_argument("--folds", type=int, default=5)
    ap.add_argument("--min-train", type=int, default=120)
    ap.add_argument("--control-edge", type=float, default=0.02)
    ap.add_argument("--alpha", type=float, default=0.05)
    ap.add_argument("--as-of", help="exclusive completed-session cutoff YYYY-MM-DD; "
                    "default current America/New_York date")
    a = ap.parse_args(argv)

    print("=" * 74)
    print("CEILING TEST — is the limit the model, or the information?")
    print("=" * 74)
    df, feats = load_pool(a.pool, feature_train_sessions=a.min_train, as_of=a.as_of)
    print(f"pool {os.path.basename(a.pool)}: {len(df):,} rows / "
          f"{df['t'].nunique()} names / {df['date'].nunique()} sessions")
    print(f"features: {'+'.join(feats)}   base rate P(up) = {df['y'].mean():.4f}")

    print("This is a research panel, not a replay of live selection or net P&L.")
    print("Session-cluster intervals assume independent days; serial dependence, "
          "survivorship and prior research reuse remain limitations.")
    print("\n  [1/2] real features " + "+".join(feats))
    real_rows = walk_forward(df, feats, a.folds, a.min_train)
    nonbaseline = [name for name in real_rows if name != "baseline"]
    # One declared family: each learned model versus chance, plus each
    # non-kNN learner versus the same-row kNN. This does not correct prior
    # studies or selection on a repeatedly inspected historical pool.
    comparisons = len(nonbaseline) + len(nonbaseline) - 1
    real = report(real_rows,
                  f"OUT-OF-SAMPLE over {a.folds} session folds (exploratory)",
                  comparisons, a.alpha)

    print(f"\n  [2/2] POSITIVE CONTROL — approximate "
          f"{50 + a.control_edge * 100:.1f}% sign classifier under balanced labels")
    ctl_rows = walk_forward(add_control(df, a.control_edge), feats + ["ctrl"],
                            a.folds, a.min_train)
    ctl = report(ctl_rows, "OUT-OF-SAMPLE, synthetic control added",
                 len(nonbaseline), a.alpha)
    control_ok = all(ctl[name]["valid_inference"]
                     and ctl[name]["lower_bound"] > 0 for name in nonbaseline)
    print("\nPAIRED COMPARISONS against kNN arithmetic (same OOS rows)")
    reference_y, reference_scores, reference_sessions = real_rows[KNN_NAME]
    paired = {}
    for name in nonbaseline:
        if name == KNN_NAME:
            continue
        y, scores, sessions = real_rows[name]
        if not (np.array_equal(y, reference_y)
                and np.array_equal(sessions, reference_sessions)):
            raise ValueError("paired model comparison does not share identical rows")
        result = auc_summary(y, scores, sessions, comparisons, a.alpha,
                             reference=reference_scores)
        paired[name] = result
        print(f"  {name}: delta AUC={result['estimate']:+.4f}, "
              f"z(session)={result['z']:.2f}, MDE80={result['mde80']:.4f}")

    print("\n" + "=" * 74)
    if not control_ok:
        print("UNDERPOWERED / INCONCLUSIVE: the synthetic control did not clear")
        print("the session-cluster test in every learner. Absence of detection")
        print("cannot establish absence of signal in this panel.")
        return 2
    winners = [name for name, result in paired.items()
               if result["valid_inference"] and result["lower_bound"] > 0
               and real[name]["valid_inference"] and real[name]["lower_bound"] > 0]
    if winners:
        print("EXPLORATORY candidates exceeding chance and same-row kNN AUC: "
              + ", ".join(winners))
        print("This establishes neither calibrated probabilities nor profitable")
        print("selection. Untouched prospective, cost-aware validation is required.")
    else:
        print("NO CORRECTED PAIRED IMPROVEMENT DETECTED in this study.")
        print("Reported MDE bounds resolution; this is not proof of a feature")
        print("ceiling, and it does not rule out smaller effects or new information.")
    print("No live strategy changes or adoption are authorised by this output.")
    print("=" * 74)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
