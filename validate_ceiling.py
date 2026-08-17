#!/usr/bin/env python3
"""
validate_ceiling.py — is the ceiling the MODEL or the FEATURES?

Thirty tested changes have been rejected (day-14 through day-40). Every one of
them varied the WRAPPER around the prediction: which leg to pick, when to enter,
when to exit, how long to hold, how many names to scan, how many picks to take,
what bar to qualify at, how to size. Not one varied the INFORMATION the
prediction is computed from — the engine has always used exactly three features
(r0, gap, vp), and no experiment ever asked whether those three carry any signal
at all.

That is the question this script answers, and it is the only one left that can
change the answer to "how do we improve accuracy". If the features are
informative and the k-NN is simply too weak to extract it, a stronger learner
finds it and accuracy improves. If the features carry ~nothing, then no model,
no selector, and no amount of wrapper tuning can help — and the thirty
rejections stop looking like thirty unlucky draws and start looking like one
fact observed thirty times.

METHOD
  Target      sign(r1), the move from the entry bar's close to the session close.
  Split       walk-forward by SESSION, never by row: every test fold is strictly
              later than its training data, and no session is ever split across
              the boundary (two legs of the same day share market direction, so
              a row-wise split leaks).
  Models      majority-class baseline, the shipped k-NN, logistic regression,
              and gradient boosting — capacity spanning ~2 orders of magnitude.
  Metric      AUC first, accuracy second. Accuracy on a near-50/50 target moves
              for reasons that have nothing to do with skill (day-35: 11% of
              legs finish inside +/-0.10%); AUC is threshold-free and is what a
              selector actually needs, since the engine RANKS names and takes
              the top one per side.

POSITIVE CONTROL — the part that makes a null result trustworthy.
  This project's history is a history of false POSITIVES: a 60-day window
  manufactures an effect, it gets shipped, and a wider sample kills it. A
  ceiling test has the opposite failure mode — concluding "no signal" when the
  harness is simply broken, which would be indistinguishable from the real
  thing by eye. So every run also fits the identical pipeline to a synthetic
  feature built to carry a KNOWN, deliberately weak edge (`--control-edge`,
  default 0.02 = a 52% coin). If the control does not light up, the null result
  on the real features means nothing and the script says so rather than
  reporting a verdict.

SURVIVORSHIP: build_pool.py applies today's TSX Composite list backwards, so
delisted names are missing. That inflates absolute returns. It does not bias a
comparison BETWEEN MODELS on the same rows, which is all this script does.
"""

from __future__ import annotations

import argparse
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from validate_exit import SCRATCH  # noqa: E402

FEATS = ["r0", "gap", "vp"]


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
    """Which of r0/gap/vp actually carry information in THIS pool.

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


def load_pool(path: str, min_price: float = 5.0) -> tuple:
    df = pd.read_csv(path)
    df = df[(df["px"] >= min_price) & df["r1"].notna() & df["r0"].notna()]
    feats = usable_feats(df)
    if "vp" in feats:
        df = add_vp(df)
    df = df.replace([np.inf, -np.inf], np.nan).dropna(subset=feats + ["r1"])
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
def knn_scores(Xtr, ytr, Xte, k: int = 60, m: int = 20) -> np.ndarray:
    """The SHIPPED model: standardise, k nearest by Euclidean distance,
    distance-weighted vote, Beta-smoothed toward the training base rate."""
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


def fit_models(Xtr, ytr, Xte, seed: int = 0) -> dict:
    from sklearn.ensemble import GradientBoostingClassifier
    from sklearn.linear_model import LogisticRegression
    from sklearn.preprocessing import StandardScaler

    sc = StandardScaler().fit(Xtr)
    out = {"baseline": np.full(len(Xte), float(ytr.mean())),
           "knn (shipped)": knn_scores(Xtr, ytr, Xte)}
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
    """Chronological session folds. Returns {model: (y, score)} pooled OOS."""
    sess = sorted(df["date"].unique())
    if len(sess) < min_train + folds:
        raise SystemExit(f"only {len(sess)} sessions — need > {min_train + folds}")
    edges = np.linspace(min_train, len(sess), folds + 1).astype(int)
    acc: dict = {}
    for a, b in zip(edges[:-1], edges[1:]):
        if b <= a:
            continue
        tr = df[df["date"].isin(sess[:a])]
        te = df[df["date"].isin(sess[a:b])]
        if te.empty or len(tr) < 500:
            continue
        Xtr, ytr = tr[feats].to_numpy(float), tr["y"].to_numpy(int)
        Xte, yte = te[feats].to_numpy(float), te["y"].to_numpy(int)
        for name, s in fit_models(Xtr, ytr, Xte).items():
            y_all, s_all = acc.setdefault(name, ([], []))
            y_all.append(yte)
            s_all.append(s)
        print(f"    fold {sess[a]}..{sess[b-1]}  train {len(tr):,}  test {len(te):,}",
              flush=True)
    return {k: (np.concatenate(v[0]), np.concatenate(v[1])) for k, v in acc.items()}


def se_auc(y: np.ndarray) -> float:
    """Standard error of AUC under the null (Hanley-McNeil at AUC=0.5)."""
    n1, n0 = int(y.sum()), int((1 - y).sum())
    if n1 == 0 or n0 == 0:
        return float("nan")
    return float(np.sqrt((n1 + n0 + 1) / (12.0 * n1 * n0)))


def report(res: dict, title: str) -> dict:
    print(f"\n  {title}")
    print(f"    {'model':<16}{'AUC':>8}{'z':>7}{'acc':>8}{'Brier':>9}{'n':>9}")
    out = {}
    for name, (y, s) in res.items():
        a, z = auc(y, s), (auc(y, s) - 0.5) / se_auc(y)
        ac = float(((s > 0.5).astype(int) == y).mean())
        print(f"    {name:<16}{a:>8.4f}{z:>7.2f}{ac:>8.1%}{brier(y, s):>9.4f}{len(y):>9,}")
        out[name] = (a, z)
    return out


def add_control(df: pd.DataFrame, edge: float, seed: int = 0) -> pd.DataFrame:
    """A synthetic feature carrying a known, weak edge on the REAL labels.

    `ctrl` is standard noise nudged by the row's true outcome, so P(y=1 | ctrl
    high) is about 0.5 + edge. Everything downstream is untouched: same rows,
    same folds, same models. If the pipeline cannot see a 52% coin at this
    sample size, it cannot be trusted to report a null on the real features.
    """
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
    a = ap.parse_args(argv)

    print("=" * 74)
    print("CEILING TEST — is the limit the model, or the information?")
    print("=" * 74)
    df, feats = load_pool(a.pool)
    print(f"pool {os.path.basename(a.pool)}: {len(df):,} rows / "
          f"{df['t'].nunique()} names / {df['date'].nunique()} sessions")
    print(f"features: {'+'.join(feats)}   base rate P(up) = {df['y'].mean():.4f}")

    print("\n  [1/2] real features " + "+".join(feats))
    real = report(walk_forward(df, feats, a.folds, a.min_train),
                  f"OUT-OF-SAMPLE, walk-forward over {a.folds} session folds")

    print(f"\n  [2/2] POSITIVE CONTROL — same pipeline, synthetic feature "
          f"with a {50 + a.control_edge * 100:.0f}% edge")
    ctl = report(walk_forward(add_control(df, a.control_edge), feats + ["ctrl"],
                              a.folds, a.min_train),
                 "OUT-OF-SAMPLE, control feature added")

    best = max(v[0] for k, v in real.items() if k != "baseline")
    bestz = max(v[1] for k, v in real.items() if k != "baseline")
    cz = max(v[1] for k, v in ctl.items() if k != "baseline")
    print("\n" + "=" * 74)
    if cz < 3:
        print(f"INCONCLUSIVE — the positive control only reached z={cz:.2f}.")
        print("The harness cannot reliably detect a known edge at this sample")
        print("size, so its null on the real features proves nothing. Do not")
        print("quote this run as evidence of anything.")
        return 2
    print(f"positive control detected at z={cz:.2f} — the harness WORKS.")
    print(f"best real-feature AUC = {best:.4f} (z={bestz:.2f})")
    if bestz < 2:
        print("\nVERDICT: the features, not the model, are the ceiling.")
        print("Gradient boosting has ~100x the capacity of the shipped k-NN and")
        print("extracts no more signal, while the same pipeline lights up on a")
        print("planted 52% coin. r0/gap/vp do not carry a usable edge, so no")
        print("selector, bar, or sizing rule built on them can add accuracy.")
    else:
        print("\nVERDICT: signal IS present that the shipped model is missing.")
        print("A stronger learner beats k-NN out of sample — this is the first")
        print("accuracy lever found. Pre-register and re-test before shipping.")
    print("=" * 74)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
