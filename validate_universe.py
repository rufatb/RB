#!/usr/bin/env python3
"""
validate_universe.py — day-14: should the universe grow from 21 to 61 names?

VERDICT: NO — expansion tested and REJECTED. Keep for re-runs; any future
expansion proposal must beat these results under the deep four-quarter
protocol (validate_deep.py) before touching config.

RESULTS (2026-07-16):
  61-name RAW:        densest legs 40.7/50.0/50.0/30.8% by block, capture
                      negative in 3/4. Mechanism identified: low-volatility
                      utilities/telecoms (EMA, BCE, T, L, H...) sit at the
                      center of the pooled feature space EVERY day, so they
                      hijack the density selection — permanently "familiar",
                      no signal, tiny moves. Liquidity was NOT the issue
                      (all 61 passed a $10M/day median screen).
  61-name NORMALIZED: per-name feature scaling does not rescue it
                      (46.4/42.9/46.4/26.9%).
  YEAR/20 NORMALIZED: per-name scaling also BREAKS the one validated claim
                      on the year-long data (47.4% in Q2, capture negative
                      in Q4 — fails the all-quarters rule the global-scaled
                      version passed). Do not change the scaling either.
CONCLUSION: the familiarity edge lives in a compact, homogeneous, liquid
universe. Breadth dilutes it. "Better picks outside the radar" was tested
and does not exist for this machine.

(1) Which names dominate densest legs in the wide universe?
(2) Does per-name feature normalization fix expansion? Tested on the 60d
61-name window AND (normalization alone) on the year-long 20-name data."""
import sys, json, os
sys.path.insert(0, "/home/user/RB")
import numpy as np
import pandas as pd
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from adapters import YahooDirectAdapter
import r945, validate_pair as vp, validate_deep as vd
from dashboard import load_config

cfg = load_config("/home/user/RB/config.yaml")
NEW = ['AC.TO','RY.TO','TD.TO','BNS.TO','BMO.TO','CM.TO','ENB.TO','TRP.TO','CNQ.TO','SU.TO',
 'CVE.TO','CP.TO','CNR.TO','SHOP.TO','ABX.TO','AEM.TO','NTR.TO','MFC.TO','SLF.TO','BCE.TO',
 'T.TO','NA.TO','GWO.TO','IFC.TO','POW.TO','BN.TO','BAM.TO','FFH.TO','IMO.TO','TOU.TO',
 'PPL.TO','ARX.TO','CCO.TO','TECK-B.TO','FM.TO','K.TO','WPM.TO','FNV.TO','ATD.TO','DOL.TO',
 'L.TO','MRU.TO','QSR.TO','SAP.TO','MG.TO','WCN.TO','TFII.TO','WSP.TO','STN.TO','EMA.TO',
 'FTS.TO','H.TO','CU.TO','CSU.TO','GIB-A.TO','OTEX.TO','RCI-B.TO','TRI.TO','QBR-B.TO',
 'CTC-A.TO','X.TO']

def walk_forward_norm(df, cfg, normalize):
    """vp.walk_forward with optional per-name feature scaling (train-only stds)."""
    groups = cfg.get("peer_groups") or {}
    g_of = {t: g for g, ms in groups.items() for t in ms}
    min_opp = cfg.get("peer_contradiction_min", 3)
    day_log = []
    for d in sorted(df["date"].unique()):
        train = df[df["date"] < d].copy()
        if len(train.dropna(subset=["r0", "gap", "v15", "r1"])) < 200:
            continue
        med = train.groupby("t")["v15"].median()
        if normalize:
            sd = train.groupby("t")[["r0", "gap"]].std().clip(lower=1e-6)
        train["vp"] = train.apply(lambda r: r["v15"] / med[r["t"]] if med.get(r["t"]) else None, axis=1)
        if normalize:
            train["r0"] = train.apply(lambda r: r["r0"] / sd.loc[r["t"], "r0"] if r["t"] in sd.index else None, axis=1)
            train["gap"] = train.apply(lambda r: r["gap"] / sd.loc[r["t"], "gap"] if r["t"] in sd.index else None, axis=1)
        board = []
        for _, row in df[df["date"] == d].iterrows():
            t = row["t"]
            if t not in med or not med[t]:
                continue
            r0, gap = row["r0"], row["gap"]
            if normalize:
                if t not in sd.index: continue
                r0 = r0 / sd.loc[t, "r0"] if r0 is not None else None
                gap = gap / sd.loc[t, "gap"] if gap is not None else None
            p, n, nd = r945.knn_probability(train, {"r0": r0, "gap": gap, "vp": row["v15"] / med[t]})
            if p is None: continue
            side = "LONG" if p >= 0.55 else ("SHORT" if 1 - p >= 0.55 else None)
            if side is None: continue
            board.append({"date": d, "t": t, "side": side, "nd": nd,
                          "sided": p if side == "LONG" else 1 - p,
                          "hit": int(row["r1"] > 0) if side == "LONG" else int(row["r1"] < 0),
                          "capt": row["r1"] if side == "LONG" else -row["r1"]})
        longs = [b for b in board if b["side"] == "LONG"]
        shorts = [b for b in board if b["side"] == "SHORT"]
        ln, sn = {}, {}
        for b in longs:  g = g_of.get(b["t"]); ln[g] = ln.get(g, 0) + 1 if g else 0
        for b in shorts: g = g_of.get(b["t"]); sn[g] = sn.get(g, 0) + 1 if g else 0
        longs = [b for b in longs if not (g_of.get(b["t"]) and sn.get(g_of[b["t"]], 0) >= min_opp)]
        shorts = [b for b in shorts if not (g_of.get(b["t"]) and ln.get(g_of[b["t"]], 0) >= min_opp)]
        day_log.append({"date": d, "longs": longs, "shorts": shorts})
    return day_log

def densest_stats(day_log, label, blocks=4):
    days = [dl["date"] for dl in day_log]
    splits = np.array_split(np.array(days), blocks)
    blk = {d: i for i, s in enumerate(splits) for d in s}
    names = Counter()
    print(label)
    for i in range(blocks):
        legs = []
        for dl in day_log:
            if blk[dl["date"]] != i: continue
            for side in ("longs", "shorts"):
                if dl[side]:
                    leg = min(dl[side], key=lambda b: b["nd"])
                    legs.append(leg); names[leg["t"]] += 1
        if legs:
            print(f"  B{i+1}: hit {np.mean([b['hit'] for b in legs])*100:4.1f}%  "
                  f"capt {np.mean([b['capt'] for b in legs]):+.3f}%  (n={len(legs)})")
    print(f"  most-picked legs: {names.most_common(8)}")

# 60d / 61-name data
a = YahooDirectAdapter(exchange_tz=cfg["exchange_tz"])
def fetch(t):
    try: return t, a._bars_df(a._chart(t, "5m", "60d"))
    except Exception: return t, pd.DataFrame()
with ThreadPoolExecutor(max_workers=8) as ex:
    fetched = dict(ex.map(fetch, NEW))
rows = []
for t, b in fetched.items():
    if not b.empty: rows += r945.session_rows(b, t)
df61 = pd.DataFrame(rows)

densest_stats(walk_forward_norm(df61, cfg, normalize=False), "\n61-name RAW (who gets picked?)")
densest_stats(walk_forward_norm(df61, cfg, normalize=True),  "\n61-name PER-NAME NORMALIZED")

# year-long 20-name data: does normalization preserve the validated edge?
rows = []
for f in sorted(os.listdir(vd.require_data())):
    if f.endswith(".json"):
        tsx, bars = vd.load_bars(os.path.join(vd.require_data(), f))
        rows += r945.session_rows(bars, tsx)
dfyear = pd.DataFrame(rows)
densest_stats(walk_forward_norm(dfyear, cfg, normalize=True), "\nYEAR/20-name NORMALIZED (4 quarters — must stay >=50% in all)")
