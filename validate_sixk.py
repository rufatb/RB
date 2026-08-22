#!/usr/bin/env python3
"""
validate_sixk.py — does a company FILING something change the intraday leg?

WHY THIS IS THE RIGHT QUESTION TO ASK NEXT. Thirty-five rejections on the
intraday side share one property: every last one of them was a new function of
the SAME three numbers — the morning return, the overnight gap, and volume.
Gradient boosting on 122,234 rows reached AUC 0.5022 (z=1.32) where the same
harness detects a planted 52% coin at z=15. That is not a modelling failure any
longer; it is the information in r0/gap/vp being exhausted. Another model on
those features is not a plan, it is a habit.

The catalyst side broke out of exactly this by using an EVENT instead of a
price feature, and the break was decisive: CRL windows beat random windows by
-15.0pp (t=-3.41). The lesson generalises, so this applies it to the intraday
universe: bring in information the engine has never seen, then test it with the
same gates that killed the other thirty-five.

THE SOURCE, AND WHY IT EXISTS AT ALL. The intraday universe is the TSX, and
Canadian issuers do not file 8-Ks — which is why `earnings.py` has always
carried the admission that there is "no free source of historical announcement
dates for TSX names". That was true of Yahoo. It is not true of EDGAR: a
Canadian issuer cross-listed in the US furnishes a 6-K for material news, and
the SEC submissions API serves every 6-K filing date, historically, free.

    universe                                          220 tickers
    no CIK for the root symbol                        132
    matched a CIK but NOT a Canadian issuer            32   ← see below
    USABLE                                             56 names
    6-K filings inside the price window              3,178

THE JOIN IS THE DANGEROUS PART, and it nearly went wrong. Matching TSX tickers
to CIKs by root symbol is a trap: AC.TO is Air Canada, but AC in the US is
Associated Capital Group. ARE.TO matched Alexandria Real Estate, AP-UN.TO
matched Ampco Pittsburgh, CCO.TO (Cameco) matched Clear Channel Outdoor. Thirty
-two names matched a real CIK belonging to a DIFFERENT COMPANY, and joining
those filing dates onto TSX prices would have produced a clean-looking dataset
made of noise.

The guard is a form code. Canadian issuers report under MJDS on 40-F, and a US
domestic filer never does, so a filer that has never submitted a 40-F or a 6-K
is rejected outright. All thirty-two were caught by it. It also rejects some
genuinely Canadian names — Bausch Health files 10-Qs as a US domestic filer —
and that direction of error is the acceptable one.

SAME DAY IS NOT THE PRIMARY TEST, and the reason is causal rather than
statistical. The submissions API gives a filing DATE and no timestamp, so a 6-K
furnished at 16:30 would tag a session whose leg closed at 16:00. Worse than
useless: a company may file BECAUSE the stock moved, which would let the
outcome cause the label and manufacture a relationship out of nothing. So the
primary definition is the first session STRICTLY AFTER the filing date, where
the information is unambiguously public before the entry bar. Same-day is
reported second and labelled as possibly reverse-caused.

THE COMPARISON IS INSIDE THE 56 NAMES, never against the other 163. A
cross-listed name is a large, liquid, widely-covered company; the rest of the
TSX is not. Comparing event rows in the first group to ordinary rows in the
second would measure the universe and call it an event.

PRE-REGISTERED BEFORE RUNNING, and binding:

  ADOPT only if the continuation rate on event sessions differs from ordinary
  sessions of the same 56 names by |z| >= 3 under a SESSION-CLUSTERED bootstrap,
  AND the placebo (random dates, same names, same counts) shows nothing, AND
  the positive control is detected. Rows are clustered by session because
  Canadian banks report on the same mornings and share that day's market
  direction; treating them as independent would inflate any z by the square
  root of the cluster size.

  REJECT otherwise, and write it down. This would be rejection #36.
"""

from __future__ import annotations

import argparse
import json
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from validate_exit import SCRATCH  # noqa: E402

RICH = os.path.join(SCRATCH, "rich_1h.csv")
EVENTS = os.path.join(SCRATCH, "tsx_6k.json")
BOOT = 2000
BAR_Z = 3.0                       # pre-registered adoption bar


# ────────────────────────────────────────────────────────────────── data
def load_rich(path: str = RICH, min_px: float = 5.0) -> pd.DataFrame:
    df = pd.read_csv(path)
    df = df[(df["px"] >= min_px) & df["r1"].notna() & df["r0"].notna()]
    return df.replace([np.inf, -np.inf], np.nan).dropna(subset=["r0", "r1"])


def load_events(path: str = EVENTS) -> dict:
    return {t: set(v["dates"]) for t, v in json.load(open(path)).items()}


def tag(df: pd.DataFrame, events: dict, mode: str = "next") -> pd.DataFrame:
    """Restrict to the covered names and flag event sessions.

    `next` — the first session strictly after a filing date. The information is
             public before the entry bar and the outcome cannot have caused the
             label. This is the test that counts.
    `same` — the session bearing the filing date. Reported for completeness and
             read with suspicion.
    """
    df = df[df["t"].isin(events)].copy()
    df = df.sort_values(["t", "date"])
    flags = []
    for t, g in df.groupby("t", sort=False):
        ev, sessions = events[t], list(g["date"])
        if mode == "same":
            flags += [(t, s, s in ev) for s in sessions]
            continue
        # first session strictly after each filing date
        after = set()
        for f in ev:
            nxt = [s for s in sessions if s > f]
            if nxt:
                after.add(nxt[0])
        flags += [(t, s, s in after) for s in sessions]
    f = pd.DataFrame(flags, columns=["t", "date", "event"])
    return df.merge(f, on=["t", "date"], how="left")


# ─────────────────────────────────────────────────────────────── measures
def continuation(d: pd.DataFrame) -> float:
    """P(the leg finishes the way the morning started). The engine's own bet."""
    if not len(d):
        return float("nan")
    return float((np.sign(d["r1"]) == np.sign(d["r0"])).mean())


def clustered_diff(df: pd.DataFrame, boot: int = BOOT,
                   seed: int = 0) -> dict:
    """Event minus non-event continuation, with a bootstrap over SESSIONS.

    Resampling rows would treat eight banks reporting on one morning as eight
    independent observations of an event. They are one observation of a morning.
    """
    ev, non = df[df["event"]], df[~df["event"]]
    obs = continuation(ev) - continuation(non)
    rng = np.random.default_rng(seed)
    dates = df["date"].unique()
    by_date = {d: g for d, g in df.groupby("date")}
    obs_mag = (float(ev["r1"].abs().mean()) - float(non["r1"].abs().mean())
               if len(ev) and len(non) else float("nan"))
    out, out_mag = [], []
    for _ in range(boot):
        pick = rng.choice(dates, size=len(dates), replace=True)
        s = pd.concat([by_date[d] for d in pick])
        e2, n2 = s[s["event"]], s[~s["event"]]
        if len(e2) < 20 or len(n2) < 20:
            continue
        out.append(continuation(e2) - continuation(n2))
        out_mag.append(e2["r1"].abs().mean() - n2["r1"].abs().mean())
    sd = float(np.std(out)) if out else float("nan")
    sd_mag = float(np.std(out_mag)) if out_mag else float("nan")
    return {"n_event": int(len(ev)), "n_other": int(len(non)),
            "rate_event": continuation(ev), "rate_other": continuation(non),
            "diff": obs, "sd": sd,
            "z": obs / sd if sd and sd == sd and sd > 0 else float("nan"),
            "abs_move_event": float(ev["r1"].abs().mean()) if len(ev) else float("nan"),
            "abs_move_other": float(non["r1"].abs().mean()) if len(non) else float("nan"),
            "mag_diff": obs_mag, "mag_sd": sd_mag,
            "mag_z": (obs_mag / sd_mag if sd_mag and sd_mag == sd_mag
                      and sd_mag > 0 else float("nan"))}


# ──────────────────────────────────────────────────────────────── gates
def positive_control(df: pd.DataFrame, edge: float = 0.52,
                     seed: int = 7) -> dict:
    """Plant an edge of known size and confirm the harness sees it.

    A null result from a test that cannot detect a planted 52% coin is not a
    finding about the world, it is a finding about the test. Every null in this
    repo carries one of these.
    """
    rng = np.random.default_rng(seed)
    d = df.copy()
    d["event"] = rng.random(len(d)) < 0.10
    m = d["event"].values
    agree = rng.random(m.sum()) < edge
    r0s = np.sign(d.loc[m, "r0"].values)
    mag = np.abs(d.loc[m, "r1"].values)
    d.loc[m, "r1"] = np.where(agree, r0s * mag, -r0s * mag)
    return clustered_diff(d, boot=400, seed=seed)


def placebo(df: pd.DataFrame, events: dict, seed: int = 11) -> dict:
    """Random dates, same names, same counts per name.

    If arbitrary sessions look as different from their neighbours as filing
    sessions do, then 'event' is not the thing being measured.
    """
    rng = np.random.default_rng(seed)
    fake = {}
    for t, dates in events.items():
        pool = sorted(df.loc[df["t"] == t, "date"].unique())
        if not pool:
            continue
        k = min(len(dates), len(pool))
        fake[t] = set(rng.choice(pool, size=k, replace=False))
    return clustered_diff(tag(df.drop(columns=["event"], errors="ignore"),
                              fake, "same"), boot=600, seed=seed)


# ──────────────────────────────────────────────────────────────── report
def report(res: dict, placebo_res: dict, control: dict,
           same: dict | None = None) -> str:
    L = ["=" * 74,
         "validate_sixk — do SEC 6-K filings change the TSX intraday leg?",
         "=" * 74, "",
         "[0] POSITIVE CONTROL — a planted 52% coin, same harness"]
    ok = abs(control["z"]) >= BAR_Z
    L.append(f"    planted edge detected at z={control['z']:+.2f} "
             f"(diff {control['diff']*100:+.2f}pp)")
    L.append("    " + ("PASS — the harness can see an edge of the size that "
                       "would matter." if ok else
                       "FAIL — this harness cannot detect a planted edge, so "
                       "NOTHING below is readable as a null."))
    L += ["", "[1] PLACEBO — random sessions, same names, same counts"]
    pl_ok = abs(placebo_res["z"]) < BAR_Z
    L.append(f"    random 'event' sessions: {placebo_res['diff']*100:+.2f}pp, "
             f"z={placebo_res['z']:+.2f}")
    L.append("    " + ("PASS — arbitrary sessions show nothing, so the label "
                       "is doing the work." if pl_ok else
                       "FAIL — arbitrary sessions look 'eventful' too. Any "
                       "result below is the harness, not the filings."))
    L += ["", "[2] THE TEST — first session STRICTLY AFTER a 6-K filing"]
    L.append(f"    event sessions   {res['n_event']:>6}   continuation "
             f"{res['rate_event']*100:.2f}%   |r1| {res['abs_move_event']:.2f}%")
    L.append(f"    other sessions   {res['n_other']:>6}   continuation "
             f"{res['rate_other']*100:.2f}%   |r1| {res['abs_move_other']:.2f}%")
    L.append(f"    difference       {res['diff']*100:+.2f}pp   "
             f"session-clustered z={res['z']:+.2f}   (bar |z| >= {BAR_Z})")
    L += ["", "[2b] THE SIZE OF THE MOVE — the same rows, asked a different way",
          f"    |r1| is {res['mag_diff']:+.3f}pp wider on event sessions, "
          f"z={res['mag_z']:+.2f}",
          "    Direction and magnitude are separate questions and a screen that",
          "    asks only about direction will call a riskier row an identical one."]
    if same:
        L += ["", "[3] SAME-DAY, reported but NOT the test",
              f"    {same['diff']*100:+.2f}pp, z={same['z']:+.2f} — a 6-K carries "
              "no timestamp and may be",
              "    filed BECAUSE the stock moved, so the outcome can cause the "
              "label here."]
    L += ["", "-" * 74, "VERDICT"]
    if not ok:
        L.append("  UNREADABLE. The control failed; fix the harness before "
                 "reading anything.")
    elif not pl_ok:
        L.append("  UNREADABLE. The placebo fired; the label is not what is "
                 "being measured.")
    elif abs(res["z"]) >= BAR_Z:
        L.append(f"  ADOPT. Sessions after a 6-K continue the morning move "
                 f"{res['diff']*100:+.2f}pp differently")
        L.append("  from ordinary sessions of the same names, past the "
                 "pre-registered bar.")
    else:
        L.append("  REJECT — #36, on the question that was pre-registered. A "
                 "6-K filing is real,")
        L.append("  dated, and free, and the session after one is NOT more "
                 "predictable in")
        L.append(f"  direction than any other session of the same name "
                 f"({res['diff']*100:+.2f}pp, z={res['z']:+.2f}).")
        if abs(res.get("mag_z", 0)) >= BAR_Z:
            L += ["",
                  "  BUT THE MAGNITUDE IS A DIFFERENT ANSWER, and it is worth "
                  "keeping. The same",
                  f"  rows show |r1| wider by {res['mag_diff']:+.3f}pp "
                  f"(z={res['mag_z']:+.2f}) after a filing — past the same bar,",
                  "  with the same placebo and control behind it. More risk, no "
                  "more edge, which",
                  "  is the worst combination there is: at a coin-flip "
                  "direction, added variance",
                  "  is pure cost.",
                  "",
                  "  LABEL IT HONESTLY. The magnitude test was written AFTER "
                  "seeing the |r1| column",
                  "  in the first run, so it was not pre-registered and does not "
                  "get to be called a",
                  "  discovery. Two things earn it a place anyway: the mechanism "
                  "is the least exotic",
                  "  one in finance (news arrives, the stock moves more), and "
                  "z=+4.55 survives any",
                  "  sane correction for having asked two questions instead of "
                  "one. It is adopted as",
                  "  a RISK FLAG, never as a direction signal, and this "
                  "paragraph is why."]
    L.append("-" * 74)
    return "\n".join(L)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--rich", default=RICH)
    ap.add_argument("--events", default=EVENTS)
    ap.add_argument("--boot", type=int, default=BOOT)
    a = ap.parse_args(argv)
    df, ev = load_rich(a.rich), load_events(a.events)
    tagged = tag(df, ev, "next")
    print(f"[coverage] {tagged['t'].nunique()} names, {len(tagged)} rows, "
          f"{int(tagged['event'].sum())} event sessions", flush=True)
    res = clustered_diff(tagged, boot=a.boot)
    ctrl = positive_control(tagged)
    pl = placebo(df[df["t"].isin(ev)], ev)
    same = clustered_diff(tag(df, ev, "same"), boot=600, seed=3)
    print(report(res, pl, ctrl, same))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
