#!/usr/bin/env python3
"""
validate_earnfilter.py — day-88. Does excluding earnings days help?

Pre-registered in PREREGISTER_day88.md. Bar: |t| >= 3 on the paired difference
AND the same sign in all four contiguous blocks.

THE QUESTION IS OLDER THAN THE DATA. `earnings.py` has warned about earnings
and deliberately never gated on them since day-53, for a stated reason:

    "there is no free source of historical announcement dates for TSX names,
     and therefore no way to measure whether excluding these rows would have
     helped."

Day-85 acquired 61,217 SEC 8-K Item 2.02 announcements across 1,857 US names,
timestamped to the minute. This is that measurement.

IT IS A FILTER, NOT A FEATURE, and that is why it does not contradict day-43's
AUC 0.5022 on 122,234 rows. Day-43 settled that r0/gap/vp cannot be rearranged
into a prediction. This asks something else: is the coin flip WORSE on days
when real information lands inside the window, and is what remains better?

THE CONTROL IS EXACT, NOT STATISTICAL. An announcement accepted AFTER 16:00
cannot move a leg that is flat by 15:55. So excluding those days must show
NOTHING. If it shows something, this study is measuring the act of dropping
rows rather than earnings, and H1 is void. That control is the reason the study
can give a usable answer instead of another underpowered shrug.

SCOPE, not weakened: entry is the first hourly close (10:30), not 9:45. A
MECHANISM sample. It can refute or support how a rule behaves; it cannot
certify live 9:46 levels. The ledger's PAIR line remains the arbiter.
"""

from __future__ import annotations

import argparse
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import validate_twins as T  # noqa: E402
import validate_us as U  # noqa: E402
from dashboard import load_config  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "data")
ADOPT_T = 3.0
IN_WINDOW = ("BEFORE_OPEN", "IN_SESSION")   # can move an open->close leg
AFTER = ("AFTER_CLOSE",)                    # cannot — the placebo arm


def load_earnings() -> pd.DataFrame:
    """Both day-85 harvests, since the hourly panel spans both universes."""
    frames = []
    for name in ("us_earnings.csv", "us_earnings_holdout.csv"):
        p = os.path.join(DATA, name)
        if os.path.exists(p):
            frames.append(pd.read_csv(p, usecols=["t", "date", "when"]))
    if not frames:
        raise FileNotFoundError(
            "no earnings feed — run `python build_us.py` first.")
    return pd.concat(frames, ignore_index=True).drop_duplicates()


def flag_sets(ern: pd.DataFrame) -> tuple:
    """(in-window, after-close) sets of (ticker, date)."""
    a = {(r.t, str(r.date)[:10]) for r in ern.itertuples()
         if r.when in IN_WINDOW}
    b = {(r.t, str(r.date)[:10]) for r in ern.itertuples()
         if r.when in AFTER}
    return a, b


def legs_with_flags(df: pd.DataFrame, cfg: dict, ern: pd.DataFrame) -> list:
    """Every qualified leg, with tide-relative capture and its earnings flags."""
    inw, aft = flag_sets(ern)
    tide = df.dropna(subset=["r1"]).groupby("date")["r1"].median()
    out = []
    for day in T.walk_forward(df, cfg):
        m = float(tide.get(day["date"], np.nan))
        if not np.isfinite(m):
            continue
        for side, group in (("LONG", day["longs"]), ("SHORT", day["shorts"])):
            for b in group:
                key = (b["t"], day["date"])
                rel = (b["capt"] - m) if side == "LONG" else (b["capt"] + m)
                out.append({"date": day["date"], "t": b["t"], "side": side,
                            "hit": b["hit"], "capt": b["capt"], "rel": rel,
                            "in_window": key in inw, "after_close": key in aft})
    return out


def paired_gap(legs: list, flag: str) -> list:
    """Per session: mean rel capture with the flagged legs REMOVED, minus the
    unfiltered mean on the same session.

    Paired because the filter and the baseline share the same days — comparing
    unpaired aggregates would measure the days, not the filter. That is exactly
    the mistake the board-vs-pair comparison made on day-87.
    """
    by: dict = {}
    for l in legs:
        by.setdefault(l["date"], []).append(l)
    out = []
    for date, group in sorted(by.items()):
        kept = [g for g in group if not g[flag]]
        if len(group) == len(kept) or not kept:
            continue                      # nothing dropped, or all dropped
        out.append({"date": date, "t": "XS",
                    "gap": float(np.mean([g["rel"] for g in kept])
                                 - np.mean([g["rel"] for g in group])),
                    "dropped": len(group) - len(kept)})
    return out


def dropped_rows(legs: list, flag: str) -> list:
    """The excluded legs themselves — H1 can only improve if these are worse."""
    return [{"date": l["date"], "t": l["t"], "rel": l["rel"], "hit": l["hit"]}
            for l in legs if l[flag]]


def summarise(legs: list, flag: str, label: str, placebo: bool = False) -> str:
    gaps = paired_gap(legs, flag)
    drop = dropped_rows(legs, flag)
    keep = [l for l in legs if not l[flag]]
    L = [f"▎{label}",
         f"   {len(drop):,} legs flagged of {len(legs):,} "
         f"({100 * len(drop) / max(len(legs), 1):.2f}%), "
         f"affecting {len(gaps):,} sessions"]
    if not gaps:
        return "\n".join(L + ["   no session had a flagged leg — not testable"])
    m, lo, hi = U.boot(gaps, "gap", "date")
    if m is None:
        return "\n".join(L + ["   too few sessions to bootstrap"])
    se = U.se_of(lo, hi)
    t = m / se if se else float("nan")
    bs = U.blocks(gaps, "gap")
    L.append(f"   effect     {m:+7.4f}%/leg   95% [{lo:+.4f}, {hi:+.4f}]   "
             f"|t|={abs(t):.2f}")
    if bs:
        L.append("   blocks     " + "  ".join(f"{b:+.4f}" for b in bs)
                 + f"   {'consistent' if U.consistent(bs) else 'SIGN FLIPS'}")
    if drop:
        dh = sum(d["hit"] for d in drop)
        L.append(f"   dropped    hit {dh}/{len(drop)} "
                 f"({100 * dh / len(drop):.1f}%)   "
                 f"rel capture {np.mean([d['rel'] for d in drop]):+.4f}%/leg")
    kh = sum(l["hit"] for l in keep)
    L.append(f"   kept       hit {kh}/{len(keep)} "
             f"({100 * kh / max(len(keep), 1):.1f}%)   "
             f"rel capture {np.mean([l['rel'] for l in keep]):+.4f}%/leg")
    z = U.power(gaps, "gap", "date", 0.05)
    if z:
        L.append(f"   control    a planted 0.05%/leg edge registers at z={z:.2f}")
    mde = ADOPT_T * se if se else None
    if placebo:
        # The exact control. An announcement after 16:00 cannot move a leg that
        # is flat by 15:55, so anything here is the act of dropping rows.
        if abs(t) >= ADOPT_T:
            L.append(f"   -> ⛔ PLACEBO FIRED (|t|={abs(t):.2f}). Excluding days "
                     f"whose news lands AFTER the leg is flat should do "
                     f"nothing. H1 is VOID.")
        else:
            L.append(f"   -> placebo silent (|t|={abs(t):.2f}) — dropping rows "
                     f"per se does not move the number")
    elif abs(t) >= ADOPT_T and U.consistent(bs):
        L.append(f"   -> CLEARS the bar (|t|={abs(t):.2f}, consistent)")
    elif abs(t) < ADOPT_T and mde and abs(m) < mde:
        L.append(f"   -> UNDERPOWERED — cannot resolve below {mde:.4f}%/leg")
    elif not U.consistent(bs):
        L.append(f"   -> FAILS block consistency")
    else:
        L.append(f"   -> BELOW the bar (|t|={abs(t):.2f})")
    return "\n".join(L)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--panel", default=os.path.join(DATA, "us_hourly.csv"))
    a = ap.parse_args(argv)
    if not os.path.exists(a.panel):
        print(f"{a.panel} missing — build the hourly panel first.")
        return 2
    cfg = load_config(os.path.join(HERE, "config.yaml"))
    df = pd.read_csv(a.panel)
    print(f"panel: {len(df):,} ticker-sessions, {df['t'].nunique()} names, "
          f"{df['date'].min()} .. {df['date'].max()}")
    ern = load_earnings()
    print(f"earnings: {len(ern):,} announcements, {ern['t'].nunique()} names")

    legs = legs_with_flags(df, cfg, ern)
    print(f"qualified legs: {len(legs):,} across "
          f"{len({l['date'] for l in legs}):,} sessions")
    if not legs:
        print("no legs — nothing to report.")
        return 2

    print("\n" + "=" * 68)
    print(summarise(legs, "in_window",
                    "H1/H2 — exclude BEFORE_OPEN + IN_SESSION announcements"))
    print("\n" + "=" * 68)
    print(summarise(legs, "after_close",
                    "H3 PLACEBO — exclude AFTER_CLOSE announcements",
                    placebo=True))
    print("\n" + "=" * 68)
    print("   ── an AFTER_CLOSE announcement cannot move a leg that is flat by")
    print("      15:55. The placebo is exact, not statistical: if it fires,")
    print("      H1 is measuring the act of dropping rows and is void.")
    print("   ── entry is 10:30, not 9:45. A MECHANISM sample; it certifies")
    print("      nothing about live 9:46 levels.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
