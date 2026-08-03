#!/usr/bin/env python3
"""
r945.py — the 9:45→close engine (run at/after 9:45 ET).

WHY THIS EXISTS: the user's actual trade is "enter ~9:45, exit by close", so
the prediction must be P(close > price@9:45) conditioned on what the first 15
minutes DID — not open→close conditioned on yesterday. Built on 60 days of
5-minute bars pooled across the whole universe (~1,240 ticker-sessions) and
validated WALK-FORWARD on a blind holdout before shipping:

    baseline P(rest-of-day up): 48.6%  (true coin flip)
    model @0.55 bar:  ~53-55% hit on ~40% of days   Brier ≈0.250
    REFUTED (day-14 deep validation): "ramps >+0.5% fade 61%" did NOT hold
    on 1 year of US-twin data — fade rate was 42.7-50.5% across all four
    independent quarters (ramps mildly CONTINUE). Another 60d-window mirage.
    The 0.55 qualification bar itself is UNPROVEN at the pool level: the
    qualified pool beat its naive-side base in only 3 of 4 quarters (and
    LOST to it in one). Do not quote a pool-level edge.
    WALKED BACK (day-6 replication): an early "≥0.60 signals hit ~67%" read
    did NOT replicate (n=9-18 bucket flipped 67%→44% across splits). There is
    NO reliable hit-rate gradient above the 0.55 bar — treat every qualified
    signal as the same ~53-55% lean; do not overweight the "strongest" pick.
    Shorts hit slightly less often but capture ~2.7x more per win (asymmetric
    down-moves). DAY-22 CORRECTION: this asymmetry is NOT present at scale.
    On 809 walk-forward pair legs (2yr/20 US twin lines) the avg-win/avg-loss
    ratio is 1.00x for shorts and 0.98x for longs, and per-quarter capture
    flips sign on both sides. The 2.7x was another 60-day artifact — do not
    size, select, or justify a leg with it.

    DAY-22 (validate_twins.py — the deep set is now FREE and 2x bigger):
    a 2-year / 20-US-twin / 9,651-ticker-session dataset is rebuildable from
    Yahoo hourly bars with no paid key, replacing the TwelveData dependency.
    Its entry is 10:30 (first hourly bar), so it PROXIES the mechanism and
    cannot certify 9:45 levels. On it, NO selector separates from placebo
    (densest 50.1%, max-P 48.3%, 2nd-densest 50.7%, random 50.2% — all inside
    one standard error), and four further candidate edges were REJECTED:
    beta-matched pairing, a tide-removed (cross-sectional) training target,
    the two combined, and a one-legged-day penalty. Cross-sectional reversal
    measured corr -0.11 on 60 days and -0.016 on 486 sessions with quarters
    flipping sign — the sixth independent confirmation that a 60-day window
    manufactures effects that do not exist. The pair is ALREADY ~tide-neutral
    (beta +0.12 to the cross-sectional median; calm vs windy days differ by
    0.02%), so the misses are idiosyncratic, not market exposure: there is
    nothing left for a smarter selector to remove.

    DAY-9 (validate_pair.py): the densest estimate (smallest k-NN neighbour
    distance) beat every top-1 selector on every split — 68.0%/69.2%
    chronological, 70.5%/66.7% odd/even, placebo 53.9%, "p≈0.0007".
    DAY-12 WALKBACK (re-run after the 60d window rolled by just THREE
    sessions): densest collapsed to 52.7% full-period (z=0.21, p=0.42),
    the placebo beat it on two splits, and max-P was equally unstable
    (50%/68% odd/even). The original significance was inflated: legs are
    serially correlated (two per day, shared market direction) and every
    "independent" split shared the same training window — the effective
    sample was far smaller than n=89. CONCLUSION (mirrors day-6): there is
    NO validated gradient among qualified picks. Densest is retained as the
    deterministic tie-break (some rule must pick the leg; its live PAIR
    ledger record keeps accruing either way) — but the stated expectation
    is the qualified-pick base rate ~52-56%, NOT 68%. Do not restore the
    old claim without it surviving a WINDOW-ROLL test, not just a split.
    CROWDING (>=3 same-group same-direction picks): 44%/33% on day-9 splits,
    44% (8/18) on the day-12 window, 61% (11/18) one session later (day-13)
    — unstable at these sample sizes; the warning stays printed, gates
    nothing.

    DAY-14 DEEP VALIDATION (validate_deep.py, 1 yr / 20 US twins / 5,160
    ticker-sessions, pre-registered all-four-quarters rule): the ONE claim
    that survived is the densest pair leg — it beat both the qualified pool
    and max-P in ALL FOUR quarters: 54.7/54.3/56.0/52.9% hit, capture
    positive every quarter, pooled 239/439 = 54.4% (z=1.86, p≈0.03),
    weighted capture +0.094%/leg PRE-COST (≈$23/leg/day at $25k). That is
    the honest ceiling of this machine on this data: a real, thin,
    barely-significant edge that costs can plausibly halve. Everything
    stronger that was ever claimed here is dead; do not resurrect it.

HONESTY (do not strip): pooled k-NN + Beta smoothing, presentation bar
inherited from report.min_sided_p, hard [0.35,0.65] clamp on stated numbers,
sample sizes shown, STAND DOWN when nothing clears. These are modest, measured
edges — selectivity is the edge; nothing here exceeds the honest ceiling.
"""

from __future__ import annotations

import argparse
import datetime as dt
from concurrent.futures import ThreadPoolExecutor
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

from adapters import YahooDirectAdapter, build_adapter
from dashboard import load_config, parse_hhmm

FEATS = ["r0", "gap", "vp"]
K, M = 60, 20                       # neighbours / Beta-prior strength
HARD_FLOOR, HARD_CAP = 0.35, 0.65


def session_rows(bars: pd.DataFrame, ticker: str, drop_date: str | None = None,
                 min_bars: int = 10) -> list:
    """Per-session feature/outcome rows from 5m bars. Pure given bars.

    `drop_date` (day-25, external audit): a session is only an OUTCOME once it
    has closed, but this function accepted any day with >= `min_bars` bars and
    treated its last bar as the close. Run intraday — which every research
    script does when invoked during a session — the CURRENT partial day was
    scored as a completed outcome, contaminating the training pool with a
    label that does not exist yet. The live engine filtered today by hand;
    the research scripts did not. Callers must now pass the session to drop
    (normally today) rather than remember to filter downstream."""
    rows, prev_close = [], None
    for d, day in bars.groupby(bars.index.date):
        day = day.sort_index()
        if drop_date is not None and str(d) == drop_date:
            if len(day):
                prev_close = day["Close"].iloc[-1]
            continue
        if len(day) < min_bars:
            if len(day):
                prev_close = day["Close"].iloc[-1]
            continue
        o, p945, c = day["Open"].iloc[0], day["Close"].iloc[2], day["Close"].iloc[-1]
        gap = (o / prev_close - 1) * 100 if prev_close else None
        prev_close = c
        if not o or not p945:
            continue
        # Path statistics (day-12): worst excursion each way AFTER the 9:45
        # entry. The engine predicts the destination, not the road — these
        # quantify the road so a normal mid-day swing against a correct call
        # (seen live: −1.3% dip on a leg that closed flat) reads as normal.
        after = day.iloc[3:]
        rows.append({"t": ticker, "date": str(d), "gap": gap,
                     "r0": (p945 / o - 1) * 100,
                     "v15": float(day["Volume"].iloc[:3].sum()),
                     "r1": (c / p945 - 1) * 100,
                     "mae_dn": (after["Low"].min() / p945 - 1) * 100 if len(after) else None,
                     "mae_up": (after["High"].max() / p945 - 1) * 100 if len(after) else None})
    return rows


def validate_signal_bars(tb: pd.DataFrame, open_t: dt.time, tz: str,
                         now: dt.datetime | None = None) -> tuple:
    """Are these really the completed 09:30 / 09:35 / 09:40 bars?

    DAY-25 (external audit): the engine took `tb["Close"].iloc[2]` — the third
    row bearing today's date — and called it the 9:45 print, proving nothing
    about WHICH bars those were. A halt, a missing opening bar, a provider
    gap or a duplicate silently shifts iloc[2] to a different time, and the
    whole prediction is then computed on bars the model was never validated
    on, with no visible failure. Every downstream guard (fill bound, disaster
    line, entry window) is denominated in a price that would be wrong.

    Returns (ok, reason). Checks, all fail-closed:
      * at least 3 bars for the session
      * first bar starts exactly at the open
      * the first three are on an exact 5-minute grid, sorted and unique
      * the third bar is COMPLETE (its 09:40-09:44:59 span has elapsed)
      * OHLC sanity and non-negative volume on those bars
    Pure given `now`; testable without a network."""
    if tb is None or len(tb) < 3:
        return False, f"only {0 if tb is None else len(tb)} bars for today (need 3)"
    idx = tb.index[:3]
    if list(idx) != sorted(set(idx)):
        return False, "duplicate or unsorted timestamps in the first three bars"
    first = idx[0]
    if (first.hour, first.minute) != (open_t.hour, open_t.minute):
        return False, (f"first bar is {first:%H:%M}, expected the {open_t.strftime('%H:%M')} "
                       "opening bar (missing/halted open?)")
    for i in (1, 2):
        gap_min = (idx[i] - idx[i - 1]).total_seconds() / 60.0
        if abs(gap_min - 5.0) > 1e-6:
            return False, (f"bar {i} is {gap_min:.0f} min after bar {i-1}, not 5 "
                           "(missing bar or wrong interval)")
    now = now or dt.datetime.now(ZoneInfo(tz))
    bar3_end = idx[2] + dt.timedelta(minutes=5)
    if now < bar3_end:
        return False, (f"the {idx[2]:%H:%M} bar closes at {bar3_end:%H:%M} and is still "
                       "IN PROGRESS — its close is the live price, not the 9:45 print")
    head = tb.iloc[:3]
    for col in ("Open", "High", "Low", "Close"):
        if col in head and not np.isfinite(head[col].to_numpy(dtype=float)).all():
            return False, f"non-finite {col} in the signal bars"
    if "Volume" in head and (head["Volume"].fillna(0).to_numpy() < 0).any():
        return False, "negative volume in the signal bars"
    if {"High", "Low"} <= set(head.columns) and (head["High"] < head["Low"]).any():
        return False, "High < Low in the signal bars (corrupt feed)"
    return True, "ok"


def extrapolation_check(train: pd.DataFrame, today: dict) -> tuple:
    """Is this name INSIDE the range the model has actually seen?

    DAY-26. Tomorrow's motivating case: Telus's US line closed -12.58% on the
    TSX holiday, so T.TO gaps enormously at the open. The live 60-day pool's
    largest |gap| is 6.85% and it holds ZERO rows beyond 8% — yet k-NN takes
    the 60 nearest neighbours no matter how far away they are, so it returns a
    confident-looking P for a setup it has never observed. The `sparse` tag
    hints at this but gates nothing.

    Measured: a live row outside the pool's per-feature range occurs on only
    0.82% of rows (deep set; 1.75% true set) and those rows move **1.89x**
    further by the close. Rare and violent — the exact profile where an
    unsupported extrapolation does most damage.

    HONEST SCOPE: this is NOT an accuracy claim. It has not been shown to
    raise the hit rate. It refuses to predict where the model has no basis,
    which is a data-validity guarantee like the day-25 bar checks, not alpha.
    Parameter-free by design — the bound is the training pool's own observed
    range, so there is nothing to tune or overfit. Pure + testable."""
    tr = train.dropna(subset=FEATS) if len(train) else train
    if len(tr) < 200:
        return True, "ok"
    lo, hi = tr[FEATS].min(), tr[FEATS].max()
    for f in FEATS:
        v = today.get(f)
        if v is None:
            continue
        if v < lo[f] or v > hi[f]:
            return False, (f"{f}={v:+.2f} is outside everything the 60-day pool has "
                           f"seen ([{lo[f]:+.2f}, {hi[f]:+.2f}]) — the model would be "
                           "extrapolating, not predicting")
    return True, "ok"


def coverage_ok(n_evaluated: int, universe: list, groups: dict,
                excluded: dict, min_frac: float = 0.8) -> tuple:
    """Did enough of the universe survive to make a CROSS-SECTIONAL choice?

    DAY-25 (external audit): failed downloads returned an empty frame and were
    swallowed, so the engine would happily pick 'the densest long' out of
    whatever names happened to load. This selector compares names against each
    other — changing the candidate set changes the bet, silently. Below
    `min_frac` coverage the honest output is no board at all. Pure+testable."""
    n_uni = len(universe or [])
    if not n_uni:
        return False, "empty universe"
    frac = n_evaluated / n_uni
    if frac < min_frac:
        miss = ", ".join(f"{t} ({why})" for t, why in sorted(excluded.items())[:8])
        return False, (f"only {n_evaluated}/{n_uni} names ({frac:.0%}) passed data "
                       f"validation, below the {min_frac:.0%} floor — a cross-sectional "
                       f"pick from a partial board is a different bet.\n   Missing: {miss}")
    return True, f"{n_evaluated}/{n_uni} names ({frac:.0%})"


def knn_probability(train: pd.DataFrame, today: dict) -> tuple:
    """Smoothed P(rest-of-day up) for today's features vs the pooled history.
    Returns (p, n_train). Same distance-weighted + Beta-smoothed machinery as
    the analog engine; clamped to the hard band."""
    tr = train.dropna(subset=FEATS + ["r1"])
    if len(tr) < 200 or any(today.get(f) is None for f in FEATS):
        return None, len(tr), None
    mu, sd = tr[FEATS].mean(), tr[FEATS].std().replace(0, 1)
    Z = ((tr[FEATS] - mu) / sd).to_numpy()
    z = ((pd.Series(today)[FEATS] - mu) / sd).to_numpy(dtype=float)
    d2 = ((Z - z) ** 2).sum(axis=1)
    idx = np.argsort(d2)[:K]
    w = 1 / (1 + np.sqrt(d2[idx]))
    y = (tr["r1"].to_numpy()[idx] > 0).astype(float)
    g = float(np.average(y, weights=w))
    p = (g * K + 0.5 * M) / (K + M)
    nd = float(np.sqrt(d2[idx]).mean())   # neighbour distance: estimate density
    return max(HARD_FLOOR, min(HARD_CAP, round(p, 3))), len(tr), nd


def allocate_book(picks: list, equity: float, max_book_pct: float,
                  min_legs: int = 2, risk_weight: bool = True,
                  weight_cap: float = 0.35) -> list:
    """Share counts for the book, total capped at max_book_pct of equity and
    divided by AT LEAST min_legs. WHY min_legs: sizing IS the entire risk
    control in the no-stop workflow — and on a one-legged day (day-18: nine
    longs, zero shorts) the missing leg must REDUCE total exposure, not double
    the surviving leg: a lone leg has no market hedge, so it gets the standard
    per-leg size and the rest of the book stays in cash.

    EQUAL-RISK WEIGHTING (day-22, the 9th candidate tested and the 2nd ever
    adopted): on a TWO-leg day the legs are weighted INVERSELY to each name's
    trailing entry->close volatility instead of equal-dollar, so a jumpy name
    cannot dominate the book's P&L. This predicts nothing new — it is a pure
    variance identity — which is why it survived where six alpha claims died.
    Validated on 333 two-legged sessions (2yr/20 US twin lines, walk-forward):
    NET std 0.587 -> 0.518 (-11.8%), LOWER IN ALL FOUR QUARTERS, worst day
    -2.22% -> -1.52%, mean return unchanged (-0.012 -> -0.005). It reduces the
    SIZE of bad days, NOT their frequency — hit rate is untouched (same picks).
    `weight_cap` bounds concentration to 35/65 so risk-weighting can never
    become a disguised single-name bet; the median split is only 58/42.
    Falls back to equal-dollar whenever vols are missing (back-compatible) or
    the book is not exactly two legs — the only case validated. Pure+testable."""
    n = len(picks)
    if n == 0 or equity <= 0:
        return picks
    book = equity * (max_book_pct / 100.0)
    slots = max(n, min_legs)
    vols = [r.get("vol") for r in picks]
    usable = (risk_weight and n == 2
              and all(v is not None and np.isfinite(v) and v > 0 for v in vols))
    if usable:
        w = np.array([1.0 / v for v in vols], dtype=float)
        w = w / w.sum()
        if weight_cap > 0:                      # bound single-leg concentration
            w = np.clip(w, weight_cap, 1 - weight_cap)
            w = w / w.sum()
        allocs = (book * n / slots) * w
    else:
        allocs = [book / slots] * n
    for r, alloc in zip(picks, allocs):
        px = r.get("last") or r.get("p945")
        r["shares"] = int(alloc // px) if px else 0
        r["alloc"] = round((r["shares"] * px) if px else 0, 0)
        r["adverse_2pct"] = round(r["alloc"] * 0.02, 0)
        r["risk_weighted"] = bool(usable)
    return picks


def density_label(nd: float, cutoffs: tuple) -> str:
    """dense/mid/sparse tag for a pick's neighbourhood. INSTRUMENTATION ONLY —
    holdout hinted dense estimates hit better (63% vs ~46%) but the pattern
    was non-monotonic on one split, so we TAG and log rather than gate. After
    ~20 live days the tag's live record decides whether it becomes a gate.
    Pre-registered hypothesis: dense > mid/sparse."""
    lo, hi = cutoffs
    return "dense" if nd <= lo else ("sparse" if nd > hi else "mid")


def late_minutes(now: dt.datetime, open_t: dt.time) -> float:
    """Minutes elapsed past the moment the 9:45 board becomes valid (open+16).
    The validation enters AT the 9:45 print — a run 20+ minutes later is a
    different, unvalidated bet (day-11 lesson: a 10:35 run showed the long
    leg +0.66%% past its print while the fresher 10:30 lens qualified NO
    longs at all). Pure + testable."""
    ready = now.replace(hour=open_t.hour, minute=open_t.minute,
                        second=0, microsecond=0) + dt.timedelta(minutes=16)
    return (now - ready).total_seconds() / 60.0


def leg_drift(side: str, p945: float, last: float, spent_pct: float = 0.3):
    """How the move since the 9:45 print changes a LATE entry on a pair leg.
    LONG: price above the print = predicted move already partly consumed.
    SHORT: price above the print = a better entry than validated (sell
    higher), and vice versa. Returns (drift_pct, verdict). Pure + testable."""
    pct = (last / p945 - 1) * 100
    spent = pct > 0 if side == "LONG" else pct < 0
    if spent and abs(pct) >= spent_pct:
        return pct, "edge partly SPENT — do not chase this leg"
    if not spent and abs(pct) >= 0.05:
        return pct, "entry better than the 9:45 print"
    return pct, "≈ unchanged from the print"


def fill_bound(side: str, decision_px: float, max_chase_pct: float = 0.04) -> float:
    """Worst acceptable fill for a pair leg, measured from the DECISION PRICE
    (the 9:45 print), never from the live market. LONG: no higher than
    decision * (1+c); SHORT: no lower than decision * (1-c). A fill past the
    bound has consumed the edge before the position opens (day-11: a CP short
    decided at 128.98 was a WINNING call — close 128.54, +0.34% — but a chased
    fill AT 128.54 captured exactly zero of it).

    DAY-25 BUG FIX (external audit): render() was passing r["last"] — the LIVE
    price — so the "bound" drifted with the market and enforced nothing. On a
    leg running away from the print it silently authorised an unbounded chase,
    which is the precise failure the bound exists to prevent. It now takes
    r["p945"].

    DAY-25 TIGHTENING: the default was 0.15%, which EXCEEDS the deep study's
    entire +0.094%/leg pre-cost edge — a fill at the old bound could pay away
    more than the edge before costs. Tolerance must be a fraction of the edge,
    not a round number, so the default is now 0.04% (under half the measured edge)
    pending a proper executable-cost study. Config `pair.max_chase_pct` still
    governs. This is deliberately fail-closed: it produces MORE no-trades.
    Pure + testable."""
    c = max_chase_pct / 100.0
    return decision_px * (1 + c) if side == "LONG" else decision_px * (1 - c)


def disaster_level(side: str, p945: float, pct: float = 2.5) -> float:
    """Price at `pct` percent against the leg from the 9:45 print. Day-16
    year-test (stop_test, four-quarter): exiting beyond -2.5% was EV-NEUTRAL
    in all four quarters (max diff 1.4bp) and cut the worst leg -3.88% ->
    -2.55%; tighter stops (-2.0%/-1.5%) FAILED (they stop out the V-day
    winners). Strictly the pre-registered adoption bar failed by 0.2bp, so
    hold-to-close stays the validated DEFAULT — this line is printed as an
    optional, exactly-quantified circuit-breaker, never a silent contract
    change. Pure + testable."""
    return p945 * (1 - pct / 100.0) if side == "LONG" else p945 * (1 + pct / 100.0)


def peer_gate(longs: list, shorts: list, groups: dict, min_opposed: int = 3):
    """Exclude any qualified pick whose direction opposes >= min_opposed
    qualified picks in its own peer group (day-8 lesson: TD short 0.55 against
    six qualified financial longs — the lone laggard got pulled up +1.22%).
    Restrictive-only: it removes picks, never adds. Pure + testable."""
    g_of = {t: g for g, members in (groups or {}).items() for t in members}
    long_n, short_n = {}, {}
    for r in longs:
        g = g_of.get(r["t"]);  long_n[g] = long_n.get(g, 0) + 1 if g else long_n.get(g, 0)
    for r in shorts:
        g = g_of.get(r["t"]); short_n[g] = short_n.get(g, 0) + 1 if g else short_n.get(g, 0)
    excluded = []

    def keep(picks, opposing):
        kept = []
        for r in picks:
            g = g_of.get(r["t"])
            n_op = opposing.get(g, 0) if g else 0
            if g and n_op >= min_opposed:
                r["excluded_reason"] = (f"contradicts {n_op} qualified {g} picks "
                                        "— lone laggard/leader in a moving sector")
                excluded.append(r)
            else:
                kept.append(r)
        return kept

    return keep(longs, short_n), keep(shorts, long_n), excluded


def group_alignment(ticker: str, same_side: list, opp_side: list,
                    groups: dict) -> tuple:
    """(n_agreeing_incl_self, n_opposing, group_size) for a ticker's peer group.
    Returns (0,0,0) when the ticker has no group. Pure + testable."""
    g_of = {t: g for g, ms in (groups or {}).items() for t in ms}
    g = g_of.get(ticker)
    if not g:
        return 0, 0, 0
    same = sum(1 for o in same_side if g_of.get(o["t"]) == g)
    opp = sum(1 for o in opp_side if g_of.get(o["t"]) == g)
    return same, opp, len((groups or {}).get(g, []))


def sector_warning(ticker: str, same_side: list, opp_side: list, groups: dict,
                   crowd_warn: int = 3) -> str | None:
    """Sector-concentration warning for a pair leg — WARNING ONLY, never a gate.

    WHY FRACTION AND NOT COUNT (day-24): the count rule needs >=3 same-group
    picks, but gold, telecom and rail have only TWO members each, so 6 of the
    21 names could never trigger any peer machinery at all. Both times a
    two-name sector moved as one it went unflagged — day-15 (BCE and T both
    long, both collapsed) and day-24 (BCE and T both SHORT, both ripped, the
    two strongest names in the universe against our short). A group that is
    100%% aligned is maximal sector concentration whatever its size.

    NOT A GATE — measured and REJECTED as one: fully-aligned legs hit 38.7%%
    vs 50.7%% (n=62, deep set) but only in 3 of 4 quarters, failing the
    pre-registered all-four bar exactly as the day-13 crowding stat did. The
    placebo grouping did NOT reproduce it (56.6%%), so the signal may be real
    — it is simply not proven, so it informs and never blocks. Pure+testable."""
    same, opp, size = group_alignment(ticker, same_side, opp_side, groups)
    if not size:
        return None
    g_of = {t: g for g, ms in (groups or {}).items() for t in ms}
    g = g_of[ticker]
    if size >= 2 and same == size and opp == 0:
        return (f"ENTIRE {g} sector ({size}/{size} names) is qualified this way — "
                f"maximal sector concentration.\n        Measured 38.7% hit vs 50.7% "
                "(n=62) but only 3 of 4 quarters — a WARNING, not a gate.")
    if same - 1 >= crowd_warn:
        return (f"{same - 1} other {g} picks point the same way — crowded "
                "sector direction hit only 44%/33% in validation")
    return None


def pair_of_day(longs: list, shorts: list, groups: dict = None,
                selector: str = "densest", crowd_warn: int = 3) -> dict:
    """THE PAIR — the single long + single short the daily workflow trades.

    SELECTION: each leg is the DENSEST qualified pick (smallest k-NN
    neighbour distance). Day-12 honesty: the day-9 evidence for this
    (68%/69% both splits) did NOT survive a 3-session window roll (52.7%,
    z=0.21) — densest is now a deterministic TIE-BREAK among equivalent
    ~52-56% leans, not a validated edge (see module header). It stays
    because a daily pair needs one reproducible rule and its live ledger
    record is accruing. Only 'densest' and 'max_p' are accepted — an
    unknown selector raises rather than silently picking something new.

    Leg quality = the pick's density tag (DENSE/MID/SPARSE), NOT its P — a
    P-based label would imply a gradient day-6/day-9 showed doesn't exist.
    A missing leg is stated as NONE — the tool never invents a leg to satisfy
    the habit. A leg with >= crowd_warn same-group same-direction picks gets
    a crowding warning (44%/33% hit in validation) — noted, not yet a gate."""
    assert selector in ("densest", "max_p"), f"unvalidated pair selector: {selector}"
    g_of = {t: g for g, ms in (groups or {}).items() for t in ms}

    def leg(picks, side, opp_picks):
        if not picks:
            return {"status": "NONE", "note": f"no qualified {side} — forcing one is a coin flip"}
        if selector == "densest":
            r = min(picks, key=lambda x: x["nd"] if x.get("nd") is not None else 9e9)
        else:
            r = picks[0]                      # lists arrive sorted by sided P
        sided = r["p_up"] if side == "LONG" else 1 - r["p_up"]
        out = {"status": (r.get("confidence") or "?").upper(), "pick": r, "sided": sided,
               "rank_by_p": 1 + sum(1 for o in picks
                                    if (o["p_up"] if side == "LONG" else 1 - o["p_up"]) > sided)}
        w = sector_warning(r["t"], picks, opp_picks, groups, crowd_warn)
        if w:
            out["warning"] = w
        return out
    return {"long": leg(longs, "LONG", shorts), "short": leg(shorts, "SHORT", longs)}


def run(cfg, workers=8):
    tz = cfg["exchange_tz"]
    now = dt.datetime.now(ZoneInfo(tz))
    # HARD too-early guard (bug found live at 9:38): between open+10 and
    # open+15 the third 5m bar EXISTS but is IN-PROGRESS — its close is the
    # live price, not the 9:45 print, so features cover ~8 of the validated 15
    # minutes. Refuse to evaluate until the bar is complete (open + 16 min).
    open_t = parse_hhmm(cfg.get("market_open", "09:30"))
    ready = now.replace(hour=open_t.hour, minute=open_t.minute, second=0,
                        microsecond=0) + dt.timedelta(minutes=16)
    if now < ready and now.date() == ready.date():
        return {"now": now.isoformat(timespec="seconds"), "n_names": 0,
                "longs": [], "shorts": [], "min_p": 0.55, "too_early": True,
                "ready_at": ready.strftime("%H:%M")}
    # DAY-25 (external audit): the 9:46 path hard-coded YahooDirectAdapter and
    # ignored `data_sources.primary` entirely, so the configured source — and
    # any paid/real-time upgrade — could never reach the one command that
    # actually places the day's bet. Honour the config, and say out loud which
    # source produced the board. Falls back only for sources that cannot serve
    # 5-minute bars, and reports that it did.
    src = (cfg.get("data_sources") or {}).get("primary", "yahoo_direct")
    src_note = ""
    try:
        a = build_adapter(src, exchange_tz=tz)
        if not hasattr(a, "_chart"):
            raise TypeError(f"{src} cannot serve 5m intraday bars")
    except Exception as e:
        a = YahooDirectAdapter(exchange_tz=tz)
        src_note = f"configured source '{src}' unusable ({e}); fell back to yahoo_direct"
        src = "yahoo_direct"
    uni = cfg.get("scan", {}).get("universe") or []
    min_p = (cfg.get("report") or {}).get("min_sided_p", 0.55)
    fetch_errors: dict = {}

    def fetch(t):
        try:
            return t, a._bars_df(a._chart(t, "5m", "60d"))
        except Exception as e:
            # Day-25: never swallow silently — a missing name changes the
            # cross-sectional choice and must be visible and counted.
            fetch_errors[t] = f"{type(e).__name__}"
            return t, pd.DataFrame()

    with ThreadPoolExecutor(max_workers=workers) as ex:
        fetched = dict(ex.map(fetch, uni))

    # Pooled history EXCLUDING today (today's close is the future — no leakage).
    today_str = str(now.date())
    hist_rows, live = [], []
    for t, bars in fetched.items():
        if bars.empty:
            continue
        rows = session_rows(bars, t)
        hist_rows += [r for r in rows if r["date"] != today_str]
        tb = bars[[str(d) == today_str for d in bars.index.date]]
        ok, why = validate_signal_bars(tb, open_t, tz, now)
        if not ok:
            fetch_errors[t] = why
        if ok:
            o = tb["Open"].iloc[0]; p945 = tb["Close"].iloc[2]
            v15 = float(tb["Volume"].iloc[:3].sum())
            prior = [r for r in rows if r["date"] != today_str]
            med_v = np.median([r["v15"] for r in prior]) if prior else None
            # Gap directly from the prior session's last close. (BUG FIX found
            # live: the old path read today's gap from session_rows, which
            # requires >=10 bars — impossible at 9:47, so every name silently
            # dropped. Post-close smoke tests couldn't catch this.)
            prev_bars = bars[[str(d) != today_str for d in bars.index.date]]
            prior_close = float(prev_bars["Close"].iloc[-1]) if len(prev_bars) else None
            gap = (o / prior_close - 1) * 100 if prior_close else None
            live.append({"t": t, "o": o, "p945": p945, "last": float(tb["Close"].iloc[-1]),
                         "r0": (p945 / o - 1) * 100, "gap": gap,
                         "vp": (v15 / med_v) if med_v else None})
    train = pd.DataFrame(hist_rows)
    train["vp"] = train.groupby("t")["v15"].transform(lambda s: s / (s.median() or 1))

    # Pooled path expectations: the normal worst swing AGAINST each side
    # between 9:45 and the close. LONG adversity = the dip (mae_dn, negative);
    # SHORT adversity = the pop (mae_up, positive). Median and worse-quartile.
    dn = train["mae_dn"].dropna() if "mae_dn" in train else pd.Series(dtype=float)
    up = train["mae_up"].dropna() if "mae_up" in train else pd.Series(dtype=float)
    path_stats = None
    if len(dn) >= 100 and len(up) >= 100:
        path_stats = {"n": int(min(len(dn), len(up))),
                      "long": (float(dn.quantile(0.5)), float(dn.quantile(0.25))),
                      "short": (float(up.quantile(0.5)), float(up.quantile(0.75)))}

    # Density cutoffs from a sample of the training rows' own neighbourhoods.
    # BUG FIX (day-22): the sampled row must be REMOVED from the training set
    # before measuring its neighbourhood. Left in, it matches itself at
    # distance 0 and drags the mean neighbour distance down — measured bias
    # -2.4%, pushing both cutoffs ~2.3% low, so LIVE picks (which never match
    # themselves) were tagged "sparse" more often than they had earned. Labels
    # only — selection compares nd between live picks and is unaffected — but
    # the dense tag is the pre-registered candidate for a future gate, so a
    # biased label would corrupt the very evidence meant to decide it.
    sample = train.dropna(subset=FEATS + ["r1"]).sample(
        n=min(120, len(train)), random_state=7) if len(train) else train
    nds = []
    for idx, row in sample.iterrows():
        res = knn_probability(train.drop(index=idx), {f: row[f] for f in FEATS})
        if res[0] is not None:
            nds.append(res[2])
    cutoffs = (float(np.quantile(nds, 0.33)), float(np.quantile(nds, 0.67))) if nds else (0.0, 9e9)

    # Per-name trailing volatility of the entry->close move, from the training
    # window only (today is excluded upstream, so this cannot peek). Feeds the
    # equal-risk leg weighting in allocate_book — see its docstring.
    vol_by_t = train.groupby("t")["r1"].std() if len(train) else pd.Series(dtype=float)

    out, extrapolated = [], []
    for r in live:
        # Day-26: refuse to predict outside the model's observed support.
        ok_x, why_x = extrapolation_check(train, r)
        if not ok_x:
            r["excluded_reason"] = why_x
            extrapolated.append(r)
            continue
        res = knn_probability(train, r)
        p, n = res[0], res[1]
        if p is None:
            continue
        v = vol_by_t.get(r["t"])
        r.update({"p_up": p, "n_train": n, "nd": res[2],
                  "vol": float(v) if v is not None and np.isfinite(v) else None,
                  "confidence": density_label(res[2], cutoffs)})
        out.append(r)
    longs = sorted([r for r in out if r["p_up"] >= min_p], key=lambda r: -r["p_up"])
    shorts = sorted([r for r in out if 1 - r["p_up"] >= min_p], key=lambda r: r["p_up"])
    longs, shorts, excluded = peer_gate(
        longs, shorts, cfg.get("peer_groups"),
        cfg.get("peer_contradiction_min", 3))
    # Day-26: names refused for extrapolation are reported alongside peer-gate
    # exclusions — a silently dropped name is how a partial board hides.
    for r in extrapolated:
        excluded.append({"t": r["t"], "excluded_reason": r["excluded_reason"]})
    # Too-early detection: no live rows because today has <3 completed 5m bars.
    too_early = (len(out) == 0 and now.time() < dt.time(9, 46))
    # Day-25 coverage gate — fail closed rather than pick from a partial board.
    cov_ok, cov_msg = coverage_ok(len(out), uni, cfg.get("peer_groups"), fetch_errors,
                                  (cfg.get("scan") or {}).get("min_coverage_frac", 0.8))
    if not cov_ok and not too_early:
        return {"now": now.isoformat(timespec="seconds"), "n_names": len(out),
                "longs": [], "shorts": [], "excluded": [], "pair": None,
                "min_p": min_p, "too_early": False, "coverage_fail": cov_msg,
                "source": src, "source_note": src_note, "fetch_errors": fetch_errors}
    pcfg = cfg.get("pair") or {}
    return {"now": now.isoformat(timespec="seconds"), "n_names": len(out),
            "longs": longs, "shorts": shorts, "excluded": excluded,
            "pair": pair_of_day(longs, shorts, cfg.get("peer_groups"),
                                pcfg.get("selector", "densest"),
                                pcfg.get("crowded_conf_warn", 3)),
            "min_p": min_p, "too_early": too_early,
            "source": src, "source_note": src_note, "fetch_errors": fetch_errors,
            "coverage": cov_msg,
            "late_min": round(late_minutes(now, open_t), 1),
            "stale_after_min": pcfg.get("stale_after_min", 20),
            "spent_drift_pct": pcfg.get("spent_drift_pct", 0.3),
            "max_chase_pct": pcfg.get("max_chase_pct", 0.15),
            "disaster_stop_pct": pcfg.get("disaster_stop_pct", 2.5),
            "entry_window_min": pcfg.get("entry_window_min", 10),
            # Anchor for the order window: the moment the 9:45 signal bar
            # became complete (open+16), NOT the moment the command was run.
            "ready_at_iso": ready.isoformat(timespec="seconds"),
            "path_stats": path_stats}


def render(res, book=False):
    print("=" * 74)
    print(f"9:45 → CLOSE ENGINE   ({res['now']})   {res['n_names']} names evaluated")
    print("=" * 74)
    if res.get("source"):
        note = f"  [{res['source_note']}]" if res.get("source_note") else ""
        print(f"source: {res['source']}   coverage: {res.get('coverage', 'n/a')}{note}")
    if res.get("too_early"):
        print(f"⏰ TOO EARLY — the engine needs the full 9:30–9:45 bars COMPLETE.")
        print(f"   Ready at {res.get('ready_at', '09:46')} ET. A run before then reads the")
        print("   in-progress bar as the 9:45 print — an unvalidated trade. REFUSING.")
        return
    if res.get("coverage_fail"):
        # Day-25: a cross-sectional pick from a partial board is a different
        # bet than the one that was validated. No board, no orders.
        print("⛔ INSUFFICIENT DATA COVERAGE — NO BOARD, NO ORDERS TODAY.")
        print(f"   {res['coverage_fail']}")
        print("   This is fail-closed by design: the pair is chosen by comparing names")
        print("   against each other, so a missing name silently changes the bet.")
        return
    print("Horizon: from the 9:45 price to the 4:00 close. Honest expectation: every")
    print("qualified pick is a ~52-56% lean; no selector gradient survived validation.")
    lr = res.get("live_record")
    if lr:
        print(f"LIVE RECORD (no hindsight): all picks {lr['all_hits']}/{lr['all_n']} "
              f"({lr['all_hits']/lr['all_n']*100:.0f}%) · PAIR {lr['pair_hits']}/{lr['pair_n']} · "
              f"last {lr['recent_n']}: {lr['recent_hits']}/{lr['recent_n']}.")
        if lr.get("short_n"):
            import ledger as _l
            for side in ("long", "short"):
                n, h = lr[f"{side}_n"], lr[f"{side}_hits"]
                if not n:
                    continue
                lo, hi = _l.wilson(h, n)
                print(f"  {side + 's':<7} {h}/{n} ({h/n*100:.0f}%)  95% CI "
                      f"{lo*100:.0f}-{hi*100:.0f}% — "
                      f"{'inside' if lo <= 0.5 <= hi else 'OUTSIDE'} a coin flip")
        if lr["all_n"] >= 30 and lr["all_hits"] / lr["all_n"] < 0.54:
            print("⚠ The live record has NOT yet demonstrated an edge over a coin flip.")
            print("  Trade the printed size or do not trade — the edge, if real, is thin.")
    pair = res.get("pair")
    late = res.get("late_min") or 0
    if late > res.get("stale_after_min", 20) and pair:
        print(f"\n  🕐 LATE RUN — this board reads the 9:45 bar but it is now {late:.0f} min")
        print("  later. The validation enters AT the 9:45 print; drift since then has")
        print("  changed each bet (day-11: a late long was +0.66% past its print while")
        print("  a fresh 10:30 read qualified NO longs). Per-leg drift:")
        for side in ("long", "short"):
            lg = pair[side]
            if lg.get("pick"):
                r = lg["pick"]
                pct, verdict = leg_drift(side.upper(), r["p945"], r["last"],
                                         res.get("spent_drift_pct", 0.3))
                print(f"      {side.upper():<6} {r['t']}: {pct:+.2f}% since the print — {verdict}")
        print("  Treat SPENT legs as NO TRADE. Next time run at 9:46.")
    if pair:
        print("\n" + "═" * 74)
        print("THE PAIR — trade these two, nothing else (one long + one short daily)")
        print("═" * 74)
        for side in ("long", "short"):
            lg = pair[side]
            if lg["status"] == "NONE":
                print(f"  {side.upper():<6}: ⛔ {lg['note']}")
                continue
            r = lg["pick"]
            print(f"  {side.upper():<6}: {r['t']}  sided-P {lg['sided']:.2f}  "
                  f"[estimate: {lg['status']}]  9:45 px {r['p945']:.2f}  last {r['last']:.2f}")
            print(f"          first-15m {r['r0']:+.2f}% · gap {r['gap']:+.2f}% · "
                  f"board rank by P: #{lg.get('rank_by_p', '?')} "
                  "(selected by DENSITY — familiarity beats extremity)")
            stale = late > res.get("stale_after_min", 20)
            if res.get("shadow"):
                # Day-26: PAPER mode. The prediction is still published and
                # scored, but no order line exists to act on. WHY a mode and
                # not a note: a printed share count IS the instruction (day-25)
                # — "paper trade this" written above a BUY line loses.
                print("      📄 SHADOW — paper only. No order, no size. "
                      "The ledger still records this leg.")
            elif stale:
                # Day-11 close: a warning banner NEXT TO a live order line loses
                # — the order line is the instruction, so on a stale board it
                # must not exist at all.
                print("      ⛔ NO ORDER — stale board: the decision price has expired.")
            elif book and r.get("shares") is not None:
                # Day-25: bound is anchored to the DECISION price (p945), never
                # the live price — see fill_bound's docstring.
                bound = fill_bound(side.upper(), r["p945"],
                                   res.get("max_chase_pct", 0.04))
                print(f"      ➤ {'BUY' if side == 'long' else 'SELL SHORT'} {r['shares']} sh "
                      f"@ market now (≈${r['alloc']:,.0f}; a 2% adverse move ≈ −${r['adverse_2pct']:,.0f})")
                if r.get("risk_weighted"):
                    print(f"      sized EQUAL-RISK (trailing vol {r['vol']:.2f}%/day): the legs hold "
                          "different\n      dollar amounts so neither name dominates the book's P&L.")
                print(f"      fill bound: {'≤' if side == 'long' else '≥'} {bound:.2f} — "
                      "past that the edge is spent before entry: NO TRADE")
                # Day-19: TIME bounds the order too — price can wander back
                # inside the bound an hour later, but that is a different,
                # unvalidated bet (a +0.06% winning call became a -0.41% ride
                # via a chased 60.92 fill during the 9:50-10:55 pop).
                ew = res.get("entry_window_min")
                if ew and res.get("ready_at_iso"):
                    # Day-25 (external audit): the window used to start at
                    # RUN time, so a first run at 09:55 minted an order valid
                    # to 10:05 — 20 minutes past the validated print, an
                    # entirely different bet (the day-11 lesson). It is now
                    # anchored to the SIGNAL BAR's availability, so running
                    # late shortens the window instead of extending it.
                    import datetime as _dt
                    t0 = _dt.datetime.fromisoformat(res["ready_at_iso"])
                    tend = t0 + _dt.timedelta(minutes=ew)
                    now_t = _dt.datetime.fromisoformat(res["now"])
                    if now_t >= tend:
                        print(f"      ⛔ ORDER WINDOW CLOSED at {tend.strftime('%H:%M')} ET "
                              f"({(now_t - tend).total_seconds()/60:.0f} min ago) — NO TRADE today.")
                    else:
                        print(f"      order window: until {tend.strftime('%H:%M')} ET "
                              f"({(tend - now_t).total_seconds()/60:.0f} min left, measured from the "
                              "9:45 print) —\n      unfilled by then (or bound broken): NO TRADE today")
                ps = res.get("path_stats")
                if ps:
                    med, worse = ps[side]
                    print(f"      normal swing AGAINST this leg before close: median {med:+.1f}% / "
                          f"worse-quartile {worse:+.1f}% (n={ps['n']} sessions).")
                    print("      A mid-day move of that size is the ROAD, not the verdict — hold to 3:55.")
                dpct = res.get("disaster_stop_pct")
                if dpct:
                    dl_px = disaster_level(side.upper(), r["p945"], dpct)
                    print(f"      disaster line {dl_px:.2f} ({'-' if side == 'long' else '+'}{dpct}% from print): "
                          "beyond it the day is a tail event. Year-tested: exiting")
                    print("      there cost ~nothing in EV and capped the worst leg at -2.6% vs -3.9%.")
                    print("      OPTIONAL circuit-breaker — the validated default is still hold to 3:55.")
            else:
                print(f"      entry ~now · flat by 3:55")
            if lg.get("warning"):
                print(f"      ⚠ {lg['warning']}")
        if pair["long"]["status"] == "NONE" or pair["short"]["status"] == "NONE":
            print("  → One leg is missing: trade the other leg ONLY. A forced leg has no edge.")
    for side, picks in (("LONG", res["longs"]), ("SHORT", res["shorts"])):
        print(f"\nCONTEXT — qualified {side}S (sided P ≥ {res['min_p']:.2f}, NOT sized, "
              "logged for learning):")
        if not picks:
            print(f"  ⛔ NO QUALIFIED {side} — do not force one.")
            continue
        for r in picks:
            sided = r["p_up"] if side == "LONG" else 1 - r["p_up"]
            print(f"  {r['t']:<9} P({'up' if side=='LONG' else 'down'}) {sided:.2f}  "
                  f"9:45 px {r['p945']:.2f}  first-15m {r['r0']:+.2f}%  gap {r['gap']:+.2f}%  "
                  f"[{r.get('confidence','?')}]")
    for r in res.get("excluded", []):
        print(f"\n  ⛔ EXCLUDED: {r['t']} — {r['excluded_reason']}")
    if book and res.get("shadow"):
        print("\n  SHADOW MODE: the board above is a PAPER record. It is published and")
        print("  scored identically to a live day, so the ledger keeps accruing toward a")
        print("  decisive sample — but no capital is at risk and no order is implied.")
        print("  Switch back by dropping --shadow. CLOSE NOTHING; there is nothing open.")
    elif book:
        print("\n  BOOK MODE: only THE PAIR is sized — one long + one short, equal-weight,")
        print("  total book capped. The pair is ~market-neutral but each leg carries full")
        print("  single-name risk with no intraday stop — sizing IS the risk control.")
        print("  THE SHARE COUNTS ARE THE RISK MODEL: trading a larger size multiplies")
        print("  every loss by the same factor and voids the stated risk numbers")
        print("  (day-13: 4x the printed size turned a ~$425 day into -$1,669).")
        print("  CLOSE BOTH BY 3:55.")
        # Day-24: the temptation to hold a losing pair overnight arrives on the
        # exact days the numbers are worst, so the measurement belongs HERE,
        # next to the order — not in a document nobody opens at 3:50.
        print("\n  WHY 3:55 AND NOT TOMORROW (439 legs, walk-forward, per quarter):")
        print("    hold to close : capture +0.094%  hit 54.4%  std 1.09%  worst leg -3.9%")
        print("    hold 1 night  : capture +0.143%  hit 53.4%  std 2.07%  worst leg -8.8%")
        print("  One night nearly DOUBLES volatility and worsens the tail 2.3x. At 5")
        print("  days longs made +0.62% while shorts made -0.39% — the multi-day gain")
        print("  is market drift, not signal: this engine's edge lasts ONE session.")
        print("  A held SHORT additionally pays borrow and carries open-ended gap")
        print("  risk, and this tool has NO earnings/dividend/news feed to price it.")
    print("\n  Modest, measured edges: a qualified leg is a ~52-56% lean (day-12 reset —")
    print("  the 68% selector claim did not survive a window roll). The ledger's PAIR")
    print("  line is the arbiter. No 5-minute outlooks — this is close-horizon only.")


def _make_output_safe() -> None:
    """Windows console default is cp1252, which raises UnicodeEncodeError on the
    arrows/box-drawing this report prints — the DAILY ENTRY POINT crashed
    outright on Windows unless PYTHONUTF8=1 was set (day-25, external audit).
    Reconfigure to UTF-8 where supported, and fall back to a replacing writer
    so the report degrades to visible placeholders instead of dying mid-order."""
    import io
    import sys as _sys
    for name in ("stdout", "stderr"):
        stream = getattr(_sys, name, None)
        if stream is None:
            continue
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            try:
                setattr(_sys, name, io.TextIOWrapper(
                    stream.buffer, encoding="utf-8", errors="replace", line_buffering=True))
            except Exception:
                pass


def main(argv=None):
    _make_output_safe()
    p = argparse.ArgumentParser(description="9:45-to-close prediction engine")
    p.add_argument("--config", default="config.yaml")
    p.add_argument("--workers", type=int, default=8)
    p.add_argument("--book", action="store_true",
                   help="once-daily workflow: exact share counts, enter at market now, flat by 3:55")
    p.add_argument("--shadow", action="store_true",
                   help="PAPER mode: publish and score the board exactly as usual, "
                        "but print NO order lines and NO share counts. The ledger "
                        "keeps accruing toward a decisive n with no money at risk.")
    args = p.parse_args(argv)
    cfg = load_config(args.config)
    res = run(cfg, args.workers)
    res["shadow"] = bool(args.shadow)
    # Accountability header: the tool faces its own live record every morning.
    try:
        import ledger
        res["live_record"] = ledger.live_summary(ledger.load())
    except Exception:
        res["live_record"] = None
    if args.book:
        rcfg = cfg.get("risk", {})
        # Day-9: only THE PAIR is sized/traded. The rest of the board is
        # context + ledger-learning material, never an order.
        pair = res.get("pair") or {}
        pair_picks = [lg["pick"] for lg in (pair.get("long"), pair.get("short"))
                      if lg and lg.get("pick")]
        pcfg = cfg.get("pair") or {}
        allocate_book(pair_picks, rcfg.get("account_equity", 0),
                      rcfg.get("max_position_pct", 50),
                      risk_weight=pcfg.get("risk_weight", True),
                      weight_cap=pcfg.get("weight_cap", 0.35))
        # Permanent learning ledger: record picks at PUBLISH time (no hindsight).
        # Pair legs get role=pair (the executed record); the remaining board is
        # role=board — kept so density/crowding instrumentation keeps learning.
        picks = res["longs"] + res["shorts"]
        if picks and not res.get("too_early"):
            import ledger
            date = res["now"][:10]
            # PUBLISH-ONCE (day-18): a re-run minutes later can see REVISED
            # early bars (seen live: SHOP's first-15m print changed between
            # 9:47 and 9:52, producing a different board). The first --book
            # run of the day is THE publication; later runs must never add
            # or alter rows — the (date,ticker) dedupe alone is not enough
            # because revised bars qualify NEW tickers.
            if any(r["date"] == date for r in ledger.load()):
                # DAY-25 (external audit): this used to call render(book=True),
                # which printed fresh share counts and "BUY n sh @ market now"
                # for a REVISED board while claiming to be informational. A
                # printed order line IS the instruction — the disclaimer above
                # it loses. A re-run is now rendered non-actionable.
                print(f"\n  [ledger: {date} already published — this re-run is "
                      "informational ONLY; the first board of the day stands.")
                print("   Order lines are SUPPRESSED: the published board is the "
                      "only tradeable one.]")
                render(res, book=False)
                return
            pair_ids = {id(r) for r in pair_picks}
            # Day-23: persist each pair leg's share of BOOK CAPACITY. Since the
            # day-22 equal-risk change the legs are deliberately different
            # sizes, so an equal-weighted capture no longer describes the book
            # (day-23: -0.156% equal-weighted vs a +$94 book). Board rows get
            # no weight — they are never traded.
            book_cap = (rcfg.get("account_equity", 0)
                        * rcfg.get("max_position_pct", 50) / 100.0)
            lrows = [{"ticker": r["t"],
                      "side": "LONG" if r["p_up"] >= 0.5 else "SHORT",
                      "p_sided": r["p_up"] if r["p_up"] >= 0.5 else 1 - r["p_up"],
                      "confidence": r.get("confidence", "n/a"),
                      "p945": r["p945"],
                      "role": "pair" if id(r) in pair_ids else "board",
                      "weight": ((r.get("alloc") or 0) / book_cap
                                 if (id(r) in pair_ids and book_cap) else None)}
                     for r in picks]
            n = ledger.append_picks(lrows, date)
            if n:
                print(f"\n  [ledger: {n} picks recorded for {date} "
                      f"({len(pair_picks)} pair / {n - len(pair_picks)} board) — score "
                      "after close with `python ledger.py --score`]")
    render(res, book=args.book)


if __name__ == "__main__":
    main()
