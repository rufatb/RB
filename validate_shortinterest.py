#!/usr/bin/env python3
"""
validate_shortinterest.py — day-84. Does short interest improve selection?

Pre-registered in PREREGISTER_day84.md. Bars were fixed there before any
outcome was computed and are not restated loosely here: |t| >= 3 on
TIDE-RELATIVE capture, session-clustered, AND the same sign in all four
quarters. Both, not either.

THE PANEL is validate_twins: hourly bars for the 20 US dual-listings, entry at
the first hourly close (10:30). It carries that module's standing caveat and it
is not weakened here — this is a MECHANISM sample and can never certify live
9:45 levels. What it gains for THIS study is that FINRA measures the US line
and the panel prices the US line, so the feature and the return come from one
population (rule 7). At the live `.TO` book the feed is a proxy again.

THE THREE ARMS, never pooled across sides, because the proposed mechanism is
asymmetric: a crowded short can squeeze, a crowded long has no counterpart.

  H1  level     — does days-to-cover separate tide-relative capture?
  H2  exclusion — does dropping the most-shorted name from the SHORT side help?
  H3  flow      — does the CHANGE in short position carry what the level does not?

WHAT DECIDES IS TIDE-RELATIVE CAPTURE, not hit rate. A hit rate can rise while
capture falls; day-38 and day-51 both found an apparent gain that was market
drift. Hit rate is printed beside it and does not decide.

POINT-IN-TIME. The join uses `publish_date` and never `settlement_date`. A
report becomes visible ~9 business days after settlement; using the settlement
date as the availability date manufactures a look-ahead edge that looks real.
`--lag` re-runs at a wider value so the verdict can be shown not to depend on
that constant.
"""

from __future__ import annotations

import argparse
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import validate_twins as T  # noqa: E402
from dashboard import load_config  # noqa: E402

BOOT = 4000
SEED = 0
ADOPT_T = 3.0
QUARTERS = 4
PERSIST_RHO = 0.90          # pre-registered feasibility gate
SI_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                       "data", "short_interest.csv")


# ── the feature, joined point-in-time ───────────────────────────────────────

def load_si(path: str = SI_PATH) -> pd.DataFrame:
    if not os.path.exists(path):
        raise FileNotFoundError(
            f"{path} not found — run `python build_shortinterest.py` first. "
            f"This study cannot substitute a default for a missing feature.")
    df = pd.read_csv(path)
    for c in ("si", "si_prev", "adv", "dtc", "change_pct"):
        df[c] = pd.to_numeric(df[c], errors="coerce")
    return df.sort_values(["tsx", "publish_date"]).reset_index(drop=True)


def as_of(si: pd.DataFrame, tsx: str, date: str) -> dict | None:
    """The latest report ALREADY PUBLISHED on `date`. Never a later one."""
    sub = si[(si["tsx"] == tsx) & (si["publish_date"] <= date)]
    if sub.empty:
        return None
    return sub.iloc[-1].to_dict()


def attach(legs: list, si: pd.DataFrame) -> tuple:
    """Join the feature onto legs. Names with no published report are dropped
    and COUNTED — an absent short interest is UNKNOWN, never zero (rule 2)."""
    out, unknown = [], 0
    for leg in legs:
        row = as_of(si, leg["t"], leg["date"])
        if row is None or not np.isfinite(row.get("dtc", np.nan)):
            unknown += 1
            continue
        out.append({**leg, "dtc": float(row["dtc"]),
                    "change_pct": (float(row["change_pct"])
                                   if np.isfinite(row.get("change_pct", np.nan))
                                   else None),
                    "si_date": row["settlement_date"],
                    "si_pub": row["publish_date"]})
    return out, unknown


# ── the panel of legs, with the tide removed ───────────────────────────────

def legs_from_panel(df: pd.DataFrame, cfg: dict) -> list:
    """Every qualified leg the engine would have taken, with tide-relative
    capture attached. `capt_rel` is the deciding column."""
    tide = df.dropna(subset=["r1"]).groupby("date")["r1"].median()
    legs = []
    for day in T.walk_forward(df, cfg):
        m = float(tide.get(day["date"], np.nan))
        for side, group in (("LONG", day["longs"]), ("SHORT", day["shorts"])):
            for b in group:
                raw = b["capt"]
                rel = (raw - m) if side == "LONG" else (raw + m)
                legs.append({**b, "capt_rel": rel if np.isfinite(m) else None})
    return [l for l in legs if l["capt_rel"] is not None]


# ── statistics: session-clustered, because legs share a day's move ─────────

def boot_diff(rows: list, field: str, n: int = BOOT, seed: int = SEED) -> tuple:
    """Mean of `field` with a SESSION-clustered 95% interval."""
    by = {}
    for r in rows:
        by.setdefault(r["date"], []).append(r)
    dates = sorted(by)
    if len(dates) < 20:
        return (None, None, None)
    vals = [r[field] for r in rows if r[field] is not None]
    if not vals:
        return (None, None, None)
    rng = np.random.default_rng(seed)
    draws = []
    for _ in range(n):
        pick = rng.integers(0, len(dates), size=len(dates))
        d = [r[field] for i in pick for r in by[dates[i]] if r[field] is not None]
        if d:
            draws.append(float(np.mean(d)))
    if not draws:
        return (None, None, None)
    return (float(np.mean(vals)), float(np.quantile(draws, 0.025)),
            float(np.quantile(draws, 0.975)))


def se_of(lo, hi):
    return None if lo is None else (hi - lo) / (2 * 1.96)


def t_of(m, lo, hi):
    se = se_of(lo, hi)
    return None if not se else m / se


def power(rows: list, field: str, edge: float, seed: int = SEED + 7):
    """POSITIVE CONTROL. edge / sd, never (mean + edge) / sd — the day-56 error."""
    _, lo, hi = boot_diff(rows, field, n=1500, seed=seed)
    sd = se_of(lo, hi)
    if not sd:
        return None
    return edge / sd


def quarters(rows: list, field: str, k: int = QUARTERS) -> list:
    """Mean per contiguous calendar block. A claim must hold in ALL of them."""
    dates = sorted({r["date"] for r in rows})
    if len(dates) < k * 5:
        return []
    edges = np.array_split(np.array(dates), k)
    out = []
    for block in edges:
        s = set(block.tolist())
        v = [r[field] for r in rows if r["date"] in s and r[field] is not None]
        out.append(float(np.mean(v)) if v else float("nan"))
    return out


def consistent(qs: list) -> bool:
    return bool(qs) and all(np.isfinite(q) for q in qs) and (
        all(q > 0 for q in qs) or all(q < 0 for q in qs))


# ── the arms ───────────────────────────────────────────────────────────────

def tercile_split(legs: list, key: str) -> tuple:
    """Top and bottom tercile BY THE SESSION'S OWN cross-section.

    Cuts are the session's 1/3 and 2/3 quantiles, fixed in the
    pre-registration and not chosen after seeing results.
    """
    top, bot = [], []
    by = {}
    for l in legs:
        if l.get(key) is not None:
            by.setdefault(l["date"], []).append(l)
    for _, group in by.items():
        if len(group) < 3:
            continue
        vals = np.array([g[key] for g in group], dtype=float)
        lo, hi = np.quantile(vals, 1 / 3), np.quantile(vals, 2 / 3)
        for g in group:
            if g[key] >= hi:
                top.append(g)
            elif g[key] <= lo:
                bot.append(g)
    return top, bot


def paired_gap(legs: list, key: str, field: str = "capt_rel") -> list:
    """Per session: mean(top tercile) - mean(bottom tercile).

    Differencing WITHIN a session removes the day's move before any average is
    taken, so the statistic cannot pick up the tide a second time.
    """
    by = {}
    for l in legs:
        if l.get(key) is not None and l.get(field) is not None:
            by.setdefault(l["date"], []).append(l)
    out = []
    for date, group in sorted(by.items()):
        if len(group) < 3:
            continue
        vals = np.array([g[key] for g in group], dtype=float)
        lo, hi = np.quantile(vals, 1 / 3), np.quantile(vals, 2 / 3)
        t = [g[field] for g in group if g[key] >= hi]
        b = [g[field] for g in group if g[key] <= lo]
        if t and b:
            out.append({"date": date, "gap": float(np.mean(t) - np.mean(b)),
                        "n_top": len(t), "n_bot": len(b)})
    return out


def placebo_gap(legs: list, key: str, n: int = 200, seed: int = SEED + 31,
                field: str = "capt_rel") -> tuple:
    """The same arithmetic with the feature SHUFFLED across names within each
    session. If this reproduces the effect, the effect is the arithmetic."""
    rng = np.random.default_rng(seed)
    means = []
    for _ in range(n):
        shuffled = []
        by = {}
        for l in legs:
            by.setdefault(l["date"], []).append(l)
        for _, group in by.items():
            vals = [g.get(key) for g in group]
            rng.shuffle(vals)
            for g, v in zip(group, vals):
                shuffled.append({**g, key: v})
        g = paired_gap(shuffled, key, field)
        if g:
            means.append(float(np.mean([x["gap"] for x in g])))
    if not means:
        return (None, None)
    return (float(np.quantile(means, 0.025)), float(np.quantile(means, 0.975)))


def exclusion_effect(legs: list, key: str = "dtc",
                     field: str = "capt_rel") -> list:
    """H2: per session, the SHORT side's mean capture with and without its
    highest days-to-cover name. Positive means the exclusion helped."""
    by = {}
    for l in legs:
        if l["side"] == "SHORT" and l.get(key) is not None and l[field] is not None:
            by.setdefault(l["date"], []).append(l)
    out = []
    for date, group in sorted(by.items()):
        if len(group) < 2:
            continue
        worst = max(group, key=lambda g: g[key])
        kept = [g for g in group if g is not worst]
        if not kept:
            continue
        out.append({"date": date,
                    "gap": float(np.mean([g[field] for g in kept])
                                 - np.mean([g[field] for g in group]))})
    return out


def placebo_exclusion(legs: list, n: int = 200, seed: int = SEED + 41,
                      field: str = "capt_rel") -> tuple:
    """Drop a RANDOM short leg instead of the most-shorted one. Any exclusion
    of one leg from a small set moves the mean; this is how much."""
    rng = np.random.default_rng(seed)
    by = {}
    for l in legs:
        if l["side"] == "SHORT" and l[field] is not None:
            by.setdefault(l["date"], []).append(l)
    usable = {d: g for d, g in by.items() if len(g) >= 2}
    if not usable:
        return (None, None)
    means = []
    for _ in range(n):
        gaps = []
        for _, group in usable.items():
            drop = rng.integers(0, len(group))
            kept = [g for i, g in enumerate(group) if i != drop]
            gaps.append(float(np.mean([g[field] for g in kept])
                              - np.mean([g[field] for g in group])))
        if gaps:
            means.append(float(np.mean(gaps)))
    return (float(np.quantile(means, 0.025)), float(np.quantile(means, 0.975)))


# ── the pre-registered feasibility gate: FEATURE only, no outcomes ─────────

def rank_persistence(si: pd.DataFrame) -> float | None:
    """Spearman rho of days-to-cover ranks across consecutive reports.

    rho >= PERSIST_RHO means the sort is effectively a permanent name label,
    and any effect would be a name fixed effect wearing a short-interest
    costume. Registered in advance; touches no outcome.
    """
    wide = si.pivot_table(index="settlement_date", columns="tsx", values="dtc")
    wide = wide.dropna(axis=0, thresh=5)
    if len(wide) < 3:
        return None
    r = wide.rank(axis=1)
    rhos = [r.iloc[i].corr(r.iloc[i + 1], method="spearman")
            for i in range(len(r) - 1)]
    rhos = [x for x in rhos if np.isfinite(x)]
    return float(np.median(rhos)) if rhos else None


def demean(legs: list, key: str) -> list:
    """Each name against its own trailing median, so a permanent level cannot
    masquerade as a signal. Used when the persistence gate demands it."""
    out = []
    hist: dict = {}
    for l in sorted(legs, key=lambda x: x["date"]):
        if l.get(key) is None:
            continue
        past = hist.setdefault(l["t"], [])
        v = l[key] - float(np.median(past)) if len(past) >= 3 else None
        past.append(l[key])
        if v is not None:
            out.append({**l, key: v})
    return out


# ── reporting ──────────────────────────────────────────────────────────────

def verdict(m, lo, hi, qs, plo, phi) -> str:
    if m is None:
        return "NOT COMPUTABLE"
    t = t_of(m, lo, hi)
    mde = ADOPT_T * se_of(lo, hi)
    if t is None:
        return "NOT COMPUTABLE"
    if abs(t) < ADOPT_T and abs(m) < mde:
        return f"UNDERPOWERED — cannot resolve an effect below {mde:.3f}%/leg"
    if abs(t) < ADOPT_T:
        return f"BELOW the bar (|t|={abs(t):.2f} < {ADOPT_T:.0f})"
    if not consistent(qs):
        return (f"FAILS four-quarter consistency (|t|={abs(t):.2f} clears, "
                f"but the sign flips across blocks)")
    if plo is not None and plo <= m <= phi:
        return (f"INSIDE the placebo band [{plo:+.3f}, {phi:+.3f}] — the "
                f"arithmetic reproduces it")
    return f"CLEARS the bar (|t|={abs(t):.2f}, consistent, outside placebo)"


def report(name: str, gaps: list, placebo: tuple, control_edge: float = 0.10) -> str:
    m, lo, hi = boot_diff(gaps, "gap")
    qs = quarters(gaps, "gap")
    plo, phi = placebo
    L = [f"▎{name}", f"   {len(gaps)} sessions"]
    if m is None:
        return "\n".join(L + ["   not computable on this sample"])
    L.append(f"   effect     {m:+7.3f}%/leg   95% [{lo:+.3f}, {hi:+.3f}]")
    if qs:
        L.append("   quarters   " + "  ".join(f"{q:+.3f}" for q in qs)
                 + f"   {'consistent' if consistent(qs) else 'SIGN FLIPS'}")
    if plo is not None:
        inside = plo <= m <= phi
        L.append(f"   placebo    [{plo:+.3f}, {phi:+.3f}] — observed is "
                 f"{'INSIDE it' if inside else 'OUTSIDE it'}")
    z = power(gaps, "gap", control_edge)
    if z is not None:
        L.append(f"   control    a planted {control_edge:.2f}%/leg edge "
                 f"registers at z={z:.2f}")
        if z > 0:
            need = int(round(len(gaps) * (ADOPT_T / z) ** 2))
            L.append(f"   power      the bar needs ~{need:,} sessions at that "
                     f"effect size (have {len(gaps)})")
    L.append(f"   -> {verdict(m, lo, hi, qs, plo, phi)}")
    return "\n".join(L)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cache", default=os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "data", "twins_panel.csv"))
    ap.add_argument("--lag", type=int, default=None,
                    help="re-derive publish_date at a wider business-day lag")
    a = ap.parse_args(argv)

    cfg = load_config(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                   "config.yaml"))
    print("building the twins panel (hourly, 720d, US lines)")
    df = T.build(a.cache)
    if df.empty:
        print("  NO PANEL — refusing to report anything.")
        return 2
    print(f"  {len(df):,} ticker-sessions, {df['date'].nunique()} sessions, "
          f"{df['t'].nunique()} names")

    si = load_si()
    if a.lag is not None:
        import build_shortinterest as B
        si["publish_date"] = [str(B.publish_date(s, a.lag).date())
                              for s in si["settlement_date"]]
        print(f"  publication lag overridden to {a.lag} business days")

    rho = rank_persistence(si)
    print(f"\n▎feasibility gate (feature only, no outcome touched)")
    print(f"   days-to-cover rank persistence across reports: rho={rho:.3f}"
          if rho is not None else "   rank persistence: not computable")
    use_demeaned = rho is not None and rho >= PERSIST_RHO
    if use_demeaned:
        print(f"   rho >= {PERSIST_RHO} — the level is a name label. The raw "
              f"level arm is ABANDONED UNRUN and only the name-demeaned form "
              f"proceeds, exactly as pre-registered.")
    else:
        print(f"   rho < {PERSIST_RHO} — both the level and the demeaned form "
              f"are admissible.")

    legs = legs_from_panel(df, cfg)
    legs, unknown = attach(legs, si)
    print(f"\n   {len(legs):,} legs carry a published report; {unknown} dropped "
          f"as UNKNOWN (absent, never zero)")
    if not legs:
        print("   no legs survive the point-in-time join — nothing to report.")
        return 2
    worst = max(l["si_pub"] for l in legs)
    assert all(l["si_pub"] <= l["date"] for l in legs), "LOOK-AHEAD in the join"
    print(f"   point-in-time verified: every report was public before its "
          f"session (latest used {worst})")

    for side in ("LONG", "SHORT"):
        sub = [l for l in legs if l["side"] == side]
        print(f"\n══ {side} legs — {len(sub):,}")
        for arm, key, label in (("H1", "dtc", "level: days-to-cover"),
                                ("H3", "change_pct", "flow: change in position")):
            src = demean(sub, key) if (use_demeaned and arm == "H1") else sub
            tag = " (name-demeaned)" if (use_demeaned and arm == "H1") else ""
            gaps = paired_gap(src, key)
            if not gaps:
                print(f"\n▎{arm} {label}{tag}\n   no usable sessions")
                continue
            print()
            print(report(f"{arm} {label}{tag} — top minus bottom tercile",
                         gaps, placebo_gap(src, key)))

    print(f"\n══ H2 exclusion rule — drop the most-shorted SHORT leg")
    ex = exclusion_effect(legs)
    if ex:
        print()
        print(report("H2 short side with the most-shorted name removed",
                     ex, placebo_exclusion(legs)))
    else:
        print("   no session had two or more short legs — not testable here")

    print("\n   ── the arms are never pooled across sides: a crowded short can")
    print("      squeeze, a crowded long has no symmetric counterpart.")
    print("   ── this is the twins panel, entry 10:30. It is a MECHANISM")
    print("      sample and certifies nothing about live 9:45 levels.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
