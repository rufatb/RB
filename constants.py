#!/usr/bin/env python3
"""
constants.py — provenance for every published number, and a diff when one moves.

THE PROBLEM, stated as a count. Five numbers that were shipping in the morning
report have been retracted in eleven days, and in every case the retraction came
from someone re-deriving them by hand, never from the code noticing:

    day-74  approvals 334 -> 977          a classifier bug
    day-79  put fair value 2.37% -> 6.04% counting only one branch
    day-81  event multiple 1.54/2.29/2.91 -> one number, 2.45x
    day-81  the tercile ladder            withdrawn as underpowered
    day-81  fair value vs its own CI      point and bracket from different samples

A constant that changes silently is worse than one that is wrong, because the
report keeps its authority while its basis moves underneath it. This file makes
three things checkable that were previously only knowable by reading the diff.

1. PROVENANCE. Every published number is classified by where it comes from:

    MEASURED   derived from data in this repo, by a NAMED script that can
               re-derive it. If the script is missing the number is a claim,
               not a measurement — day-79's constants had no script for two
               days and could not be checked until one was written.
    CITED      taken from an outside source. Legitimate, but it did not come
               from this harness and no positive control here defends it.
    DESIGN     a threshold someone chose. Not measurable and not in need of a
               script — but it must not be presented as measured.

2. DRIFT. Values are snapshotted to data/constants.json. Any change against the
   snapshot prints, with old and new, on the next report.

3. TENSION. Two constants that describe the same quantity must agree, and the
   registry states which pairs those are. This is the check that found the
   contradiction documented below, which had been shipping since day-54.

WHAT THIS DOES NOT DO. It cannot tell whether a number is right — only whether
it moved, where it came from, and whether it contradicts another number in the
same report. A wrong constant with a script and a stable value passes cleanly.
"""

from __future__ import annotations

import argparse
import datetime as dt
import importlib
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

REPO = os.path.dirname(os.path.abspath(__file__))
SNAPSHOT = os.path.join(REPO, "data", "constants.json")

MEASURED, CITED, DESIGN = "MEASURED", "CITED", "DESIGN"


class Const:
    __slots__ = ("kind", "script", "day", "n", "note")

    def __init__(self, kind, script=None, day=None, n=None, note=""):
        self.kind, self.script, self.day, self.n, self.note = (
            kind, script, day, n, note)


# ── the registry ────────────────────────────────────────────────────────────
# Only PUBLISHED numbers: things that reach the report and carry a claim about
# the world. Paths, user agents and cache locations are not here.

REGISTRY = {
    # fair value — re-measured day-81, script committed
    "fairvalue.EVENT_MULT_POINT": Const(
        MEASURED, "validate_eventmult.py", 81, 605,
        "event put payoff as a multiple of the name's own 3d put value"),
    "fairvalue.EVENT_MULT_CI": Const(
        MEASURED, "validate_eventmult.py", 81, 605,
        "95%, bootstrap resampling NAMES not events"),
    "fairvalue.TERCILE_OBSERVED": Const(
        MEASURED, "validate_eventmult.py", 81, 605,
        "printed as an open question; NOT priced in — underpowered"),
    "fairvalue.TERCILE_EDGES": Const(
        MEASURED, "validate_eventmult.py", 81, 605, "sample terciles of own3"),
    "fairvalue.TERCILE_MDE": Const(
        MEASURED, "validate_eventmult.py", 81, 605,
        "smallest tercile gap this sample can resolve"),
    "fairvalue.N_EVENTS": Const(MEASURED, "validate_eventmult.py", 81, 605),
    "fairvalue.N_NAMES": Const(MEASURED, "validate_eventmult.py", 81, 184),
    "fairvalue.N_RANDOM": Const(
        MEASURED, None, 79, 7440,
        "NO SCRIPT re-derives this; day-79's random-window count"),
    "fairvalue.DISAGREE_TOL": Const(
        DESIGN, None, 81, None, "pre-registered, PREREGISTER_day81.md"),
    "fairvalue.DRIFT_TOL": Const(
        DESIGN, None, 81, None, "pre-registered from planted controls"),
    "fairvalue.TAIL_TOL": Const(
        DESIGN, None, 81, None, "pre-registered from planted controls"),

    # the event study — day-68, re-cut day-77
    "catalyst.CRL_MEDIAN": Const(MEASURED, "validate_catalyst.py", 77, 71),
    "catalyst.CRL_MEAN": Const(MEASURED, "validate_catalyst.py", 77, 71),
    "catalyst.CRL_P10": Const(MEASURED, "validate_catalyst.py", 77, 71),
    "catalyst.CRL_WORST": Const(MEASURED, "validate_catalyst.py", 77, 71),
    "catalyst.CRL_WORSE_THAN_18": Const(MEASURED, "validate_catalyst.py", 77, 71),
    "catalyst.CRL_WORSE_THAN_40": Const(MEASURED, "validate_catalyst.py", 77, 71),
    "catalyst.CRL_N": Const(MEASURED, "validate_catalyst.py", 77, 71),
    "catalyst.CRL_VS_RANDOM_PP": Const(MEASURED, "validate_catalyst.py", 77, 71),
    "catalyst.CRL_T": Const(MEASURED, "validate_catalyst.py", 77, 71),
    "catalyst.APPROVAL_MEDIAN": Const(MEASURED, "validate_catalyst.py", 77, 534),
    "catalyst.APPROVAL_MEAN": Const(MEASURED, "validate_catalyst.py", 77, 534),
    "catalyst.APPROVAL_VS_RANDOM_PP": Const(
        MEASURED, "validate_catalyst.py", 77, 534,
        "REJECTION #37 — positive but below the pre-registered bar"),
    "catalyst.APPROVAL_T": Const(MEASURED, "validate_catalyst.py", 77, 534),
    "catalyst.APPROVAL_N": Const(MEASURED, "validate_catalyst.py", 77, 534),
    "catalyst.APPROVAL_RANDOM": Const(MEASURED, "validate_catalyst.py", 77, 534),
    "catalyst.ADOPT_T": Const(
        DESIGN, None, 54, None, "the pre-registered adoption bar, |t| >= 3"),
    "catalyst.GAP_WARN": Const(DESIGN, None, 54, None),
    "catalyst.BASE_RATE_FIRST_CYCLE": Const(
        CITED, None, 54, None,
        "FDA first-cycle review data, NOT measured here — see TENSIONS"),

    # accuracy definitions — day-82, ACCURACY.md
    "ledger.DECISIVE_PCT": Const(
        DESIGN, None, 82, None,
        "|capture| below this is a scratch, excluded from the decisive hit "
        "rate and counted (ACCURACY.md §1); sets the number printed beside "
        "every pick"),
    "cost.TYPICAL_MOVE_PCT": Const(
        MEASURED, None, 72, None,
        "typical intraday move used to express spread as a share of it; NO "
        "SCRIPT re-derives it"),

    # the measured base rate — day-71
    "baserate.SERIAL_MIN": Const(DESIGN, None, 71, None),
    "baserate.SINGLE_MAX": Const(DESIGN, None, 71, None),

    # the plausibility gate — day-81
    "sanity.MAX_DAILY_GAP": Const(
        DESIGN, None, 81, None,
        "calibrated: real daily bars max out at a 4-day gap, weekly is 7"),
    "sanity.MAX_PUT_PCT": Const(DESIGN, None, 81, None, "arithmetic"),
    "sanity.MAX_SANE_PUT_PCT": Const(DESIGN, None, 81, None),
    "sanity.MAX_VOL": Const(DESIGN, None, 81, None),

    # data hygiene — day-72
    "validate_catalyst.LOOKBACK_DAYS": Const(
        DESIGN, None, 72, None,
        "largest range Yahoo still serves as true daily bars"),
    "validate_catalyst.MAX_GAP_DAYS": Const(DESIGN, None, 72, None),
    "resolved.LOOK_DAYS": Const(DESIGN, None, 75, None),
}


def source_value(mod_name: str, attr: str):
    """The value as written in the SOURCE TEXT, parsed, never imported.

    A SECOND INDEPENDENT READING, for the same reason fair value has one: the
    imported attribute can be stale. CPython invalidates bytecode on the source
    file's mtime-TO-THE-SECOND plus its size, so editing a constant to another
    literal of the same length within the same second leaves the old .pyc in
    place and `import` quietly returns the OLD value. Caught here by doing
    exactly that — 2.45 -> 1.54 is the same number of characters.

    That is vanishingly unlikely in a morning run, where nothing has been
    edited for hours. But this file's one job is to say "nothing moved", and a
    false "nothing moved" is the precise failure it exists to prevent, so the
    claim is not left resting on the bytecode cache.

    Returns None when the name is not a module-level literal — a computed
    constant is a legitimate miss, not a disagreement.
    """
    import ast
    path = os.path.join(REPO, *mod_name.split(".")) + ".py"
    if not os.path.exists(path):
        return None
    try:
        with open(path) as f:
            tree = ast.parse(f.read(), filename=path)
    except (OSError, SyntaxError):
        return None
    found = None
    for node in tree.body:                      # module level only
        targets = (node.targets if isinstance(node, ast.Assign)
                   else [node.target] if isinstance(node, ast.AnnAssign)
                   else [])
        for t in targets:
            if isinstance(t, ast.Name) and t.id == attr and node.value:
                try:
                    found = ast.literal_eval(node.value)
                except (ValueError, TypeError, SyntaxError):
                    return None                 # computed, not a literal
    return found


def live(registry: dict = None) -> dict:
    """Read what each constant IS right now, straight from the module.

    Reads the live attribute rather than a copy, so a typo in a source literal
    shows up here — which is the entire point.
    """
    registry = registry if registry is not None else REGISTRY
    importlib.invalidate_caches()
    out = {}
    for key in registry:
        mod_name, attr = key.rsplit(".", 1)
        try:
            mod = importlib.import_module(mod_name)
        except Exception as e:                      # never silently (rule 1)
            out[key] = {"error": f"import failed: {type(e).__name__}: {e}"}
            continue
        if not hasattr(mod, attr):
            out[key] = {"error": "MISSING from the module"}
            continue
        val = getattr(mod, attr)
        rec = {"value": val}
        src = source_value(mod_name, attr)
        # Only a disagreement counts. A computed constant parses to None and is
        # simply not double-read; asserting on that would fire constantly.
        if src is not None and _norm(src) != _norm(val):
            rec["stale"] = (f"source says {src!r} but the imported module says "
                            f"{val!r} — stale bytecode; delete __pycache__")
        out[key] = rec
    return out


def _norm(v):
    """JSON round-trips tuples to lists; compare on a common footing."""
    if isinstance(v, (list, tuple)):
        return [_norm(x) for x in v]
    if isinstance(v, dict):
        return {str(k): _norm(x) for k, x in v.items()}
    return v


def drift(now: dict, snap: dict) -> dict:
    """What moved since the snapshot. Silence here is the desired state."""
    changed, added, removed, broken = [], [], [], []
    for k, cur in now.items():
        if cur.get("error"):
            broken.append((k, cur["error"]))
            continue
        if cur.get("stale"):
            broken.append((k, cur["stale"]))
        if k not in snap:
            added.append((k, cur["value"]))
        elif _norm(snap[k]) != _norm(cur["value"]):
            changed.append((k, snap[k], cur["value"]))
    for k in snap:
        if k not in now:
            removed.append((k, snap[k]))
    return {"changed": changed, "added": added, "removed": removed,
            "broken": broken}


def unprovenanced(registry: dict = None) -> list:
    """MEASURED numbers with no script that can re-derive them.

    Day-79's constants sat here for two days. A measurement nobody can repeat
    is a claim wearing a measurement's clothes.
    """
    registry = registry if registry is not None else REGISTRY
    return [k for k, c in registry.items()
            if c.kind == MEASURED and not c.script]


# ── tensions ────────────────────────────────────────────────────────────────

def _crl_tension() -> tuple | None:
    """Two numbers in this report describe P(rejection). They disagree.

    `catalyst.BASE_RATE_FIRST_CYCLE = 0.70` is CITED from FDA first-cycle
    review data and implies P(CRL) = 30%. `baserate` MEASURES P(CRL) at 11.7%
    over single-asset sponsors, 95% [8.5%, 15.9%] — an interval that excludes
    30% outright. Both ship: the guardrails in `catalyst.assess` anchor on the
    first, and every breakeven in the screen divides by the second.

    NEITHER IS DECLARED WRONG HERE, because they are not the same population
    and the registry's job is to surface the conflict, not to settle it:

      - the measured leg counts decisions ANNOUNCED IN AN 8-K. Companies
        publicise approvals eagerly and rejections reluctantly, so the CRL
        numerator is the leg more likely to be undercounted, biasing the
        measured rate DOWN — toward the FDA figure being the more honest one.
      - the cited leg is first-cycle NME review. This harvest includes
        supplements and lower-stakes decisions, which approve at higher rates,
        biasing the measured rate down again for a second reason.
      - the measured leg has a positive control and a published interval; the
        cited one has neither, here.

    What is NOT defensible is a report that quietly uses 30% in one paragraph
    and 12% in the next. Rule 8: a rate over a population is not a forecast for
    one name, and two rates over two populations are not interchangeable.
    """
    try:
        import baserate as B
        import catalyst as C
        s = B.summary()
        if not s:
            return None
        implied = 1.0 - float(C.BASE_RATE_FIRST_CYCLE)
        lo, hi, p = float(s["lo"]), float(s["hi"]), float(s["p"])
        if lo <= implied <= hi:
            return None
        # `short` carries the same numbers, computed, for the one-screen view.
        # Retyping them there as literals would put an uncheckable copy of a
        # measured value in a second file — the defect this module exists for.
        short = (f"cited {implied:.0%} vs measured {p:.1%} "
                 f"[{lo:.1%}–{hi:.1%}]; different populations, and the "
                 f"measured leg is biased DOWN")
        return ("P(rejection)",
                f"CITED first-cycle base rate implies {implied:.0%}, but the "
                f"MEASURED rate is {p:.1%} with 95% [{lo:.1%}, {hi:.1%}] "
                f"(n={s['n']}) — the interval excludes it. Different "
                "populations (all first-cycle NME reviews vs decisions "
                "announced in an 8-K), and the measured leg is biased DOWN "
                "because rejections are announced less readily than "
                "approvals. Do not mix them in one argument.", short)
    except Exception as e:
        return ("P(rejection)", f"tension check failed: {type(e).__name__}: {e}",
                f"tension check failed: {type(e).__name__}")


TENSIONS = [_crl_tension]


def tensions() -> list:
    return [t for t in (fn() for fn in TENSIONS) if t]


# ── snapshot / report ───────────────────────────────────────────────────────

def save(now: dict = None, path: str = SNAPSHOT) -> dict:
    now = now if now is not None else live()
    vals = {k: _norm(v["value"]) for k, v in now.items() if "value" in v}
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        json.dump({"saved": dt.date.today().isoformat(), "values": vals},
                  f, indent=2, sort_keys=True)
    return vals


def load(path: str = SNAPSHOT) -> dict:
    if not os.path.exists(path):
        return {}
    with open(path) as f:
        return json.load(f).get("values", {})


def report(now: dict = None, snap: dict = None) -> str:
    now = now if now is not None else live()
    snap = snap if snap is not None else load()
    d = drift(now, snap)
    L = ["▎CONSTANTS — provenance, and anything that moved"]

    kinds = {}
    for k, c in REGISTRY.items():
        kinds.setdefault(c.kind, []).append(k)
    L.append(f"   {len(REGISTRY)} published numbers: "
             + ", ".join(f"{len(v)} {k.lower()}"
                         for k, v in sorted(kinds.items())))

    if not snap:
        L.append("   no snapshot yet — run `python constants.py --save` to "
                 "start tracking drift.")
    elif not any((d["changed"], d["added"], d["removed"], d["broken"])):
        L.append("   nothing moved since the last snapshot.")
    for k, old, new in d["changed"]:
        c = REGISTRY.get(k)
        L.append(f"   ⚠ MOVED  {k}")
        L.append(f"       {old!r}  ->  {new!r}")
        if c and c.kind == MEASURED and c.script:
            L.append(f"       re-derive with: python {c.script}")
        elif c and c.kind == MEASURED:
            L.append("       MEASURED with no script — cannot be re-derived")
    for k, v in d["added"]:
        L.append(f"   + new    {k} = {v!r}")
    for k, v in d["removed"]:
        L.append(f"   - gone   {k} (was {v!r})")
    for k, e in d["broken"]:
        L.append(f"   ⚠ BROKEN {k}: {e}")

    orphans = unprovenanced()
    if orphans:
        L.append(f"   ⚠ {len(orphans)} MEASURED number(s) with no script to "
                 "re-derive them:")
        for k in orphans:
            L.append(f"       {k} — {REGISTRY[k].note or 'no note'}")

    for what, why, _short in tensions():
        L.append(f"   ⚠ TENSION on {what}:")
        for line in _wrap(why):
            L.append(f"       {line}")

    L.append("   ── MEASURED means a named script re-derives it; CITED came "
             "from outside")
    L.append("      this repo and has no control here; DESIGN is a chosen "
             "threshold.")
    return "\n".join(L)


def _wrap(t: str, w: int = 68) -> list:
    import textwrap
    return textwrap.wrap(t, width=w)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--save", action="store_true",
                    help="record current values as the baseline")
    a = ap.parse_args(argv)
    now = live()
    print(report(now))
    if a.save:
        save(now)
        print(f"\nsnapshot written to {SNAPSHOT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
