#!/usr/bin/env python3
"""
validate_events.py — the day-32 event/swing-trade study. RESULT: NO EDGE FOUND.

QUESTION ASKED: after a big overnight gap (the SLN +34% case), is there a
multi-day swing trade with better accuracy/returns than the intraday pair?

DATA: 10 years of DAILY bars, 166 liquid US names, 400,703 ticker-days. Unlike
the 9:45 engine (capped at 60 days of 5-minute bars) daily history is abundant,
so for once data was NOT the binding constraint.

VERDICT — REJECTED. Exactly one bucket passed the five-block consistency test:
gap -5%..-10%, market-relative, +0.60%% at 5d and +0.98%% at 10d, consistent in
all five two-year blocks, n=1,791. Three follow-up tests dissolved it
(validate_events_bias.py):
  * TAIL-CARRIED: mean rel-10d +0.980%% but MEDIAN +0.010%%, win rate 49.9%%.
    The typical event does nothing; a handful of huge rebounds carry the mean.
  * BETA, NOT SELECTION: the bounce exists only on market-DOWN days (+1.105%%)
    and is NEGATIVE on market-up days (-0.624%%). A high-beta name that gapped
    down mechanically out-bounces the cross-sectional median when the tape
    recovers — that is not a stock-specific edge.
  * NOT SIZE-ROBUST: flips in 3 of 4 liquidity quartiles; the smallest quartile
    is outright NEGATIVE (-0.965%%).
Every other bucket flipped sign across blocks outright.

BIG GAPS ARE UNSTUDIABLE HERE: |gap| >= 20%% occurs 141 times in 10 years across
166 names. SLN's own history has THREE such gaps in 1,255 sessions. There is no
sample with which to support an SLN-style trade.

SURVIVORSHIP BIAS (cannot be removed with free data): the universe is today's
ticker list, so names that gapped down and delisted are ABSENT — which biases
gap-down results optimistically, i.e. precisely the direction of the one
"finding". Removing it needs a point-in-time universe including dead tickers,
which is a paid data product.

Usage:
    python validate_events_build.py   # fetch 10y of daily bars -> daily.csv
    python validate_events.py         # the event study
    python validate_events_bias.py    # the three tests that killed it
"""

import pandas as pd, numpy as np
def _require_daily(path="daily.csv"):
    """The daily-bar panel, or an actionable message (day-82).

    This harness read `daily.csv` from the CURRENT WORKING DIRECTORY at import
    time and the file is not committed, so the study could not re-run and said
    so only as `FileNotFoundError: daily.csv`. It is rebuildable, unlike the
    5-minute cache, so the message names the command that rebuilds it.
    """
    import os
    if not os.path.exists(path):
        raise SystemExit(
            f"this study needs {path}, which is not committed.\n"
            f"  rebuild : python validate_events_build.py\n"
            f"  then    : re-run this script from the same directory\n"
            f"  see     : INVENTORY.md")
    return path

df=pd.read_csv(_require_daily())
df=df.sort_values(["t","date"]).reset_index(drop=True)
g=df.groupby("t",group_keys=False)
df["prev_c"]=g["c"].shift(1)
df["gap"]=(df.o/df.prev_c-1)*100
df["ret_d"]=(df.c/df.prev_c-1)*100                    # full-day return
df["intraday"]=(df.c/df.o-1)*100                      # open->close on gap day
for n in (1,3,5,10):
    df[f"f{n}"]=(g["c"].shift(-n)/df.c-1)*100         # from the CLOSE of gap day
# market = cross-sectional median that session
mkt=df.groupby("date")[["ret_d"]+[f"f{n}" for n in (1,3,5,10)]].median()
mkt.columns=["m_ret"]+[f"m{n}" for n in (1,3,5,10)]
df=df.join(mkt,on="date")
for n in (1,3,5,10):
    df[f"r{n}"]=df[f"f{n}"]-df[f"m{n}"]               # market-relative forward

dates=sorted(df.date.unique()); blocks=np.array_split(np.array(dates),5)
bo={d:i for i,b in enumerate(blocks) for d in b}; df["blk"]=df.date.map(bo)

print(f"universe {df.t.nunique()} names, {len(df):,} ticker-days, "
      f"{df.date.nunique()} sessions\n")
print("GAP EVENT FREQUENCY")
for lo,hi,lab in ((5,10,"+5..10%"),(10,20,"+10..20%"),(20,999,">+20%"),
                  (-10,-5,"-5..-10%"),(-20,-10,"-10..-20%"),(-999,-20,"<-20%")):
    n=len(df[(df.gap>lo)&(df.gap<=hi)]) if lo>=0 else len(df[(df.gap>=lo)&(df.gap<hi)])
    print(f"  {lab:>10}: {n:>6,} events")

def report(mask,lab,col_prefix="r"):
    s=df[mask].dropna(subset=[f"{col_prefix}5"])
    if len(s)<100: print(f"  {lab:<16} n={len(s)} too few"); return
    parts=[]
    for n in (1,3,5,10):
        v=s[f"{col_prefix}{n}"].dropna()
        parts.append(f"{n}d {v.mean():+6.2f}%")
    # block consistency on 5d
    sg=[]
    for b in range(5):
        sb=s[s.blk==b][f"{col_prefix}5"].dropna()
        sg.append(np.sign(sb.mean()) if len(sb)>=20 else 0)
    consistent = all(x>0 for x in sg if x!=0) or all(x<0 for x in sg if x!=0)
    print(f"  {lab:<16} n={len(s):>5}  " + "  ".join(parts)
          + f"   blocks {'CONSISTENT' if consistent else 'FLIP'} {[int(x) for x in sg]}")

for tag,pre in (("MARKET-RELATIVE forward returns (tape removed)","r"),
                ("RAW forward returns (includes market drift)","f")):
    print(f"\n{tag}:")
    report((df.gap>=20),"gap >= +20%",pre)
    report((df.gap>=10)&(df.gap<20),"gap +10..20%",pre)
    report((df.gap>=5)&(df.gap<10),"gap +5..10%",pre)
    report((df.gap<=-5)&(df.gap>-10),"gap -5..-10%",pre)
    report((df.gap<=-10)&(df.gap>-20),"gap -10..-20%",pre)
    report((df.gap<=-20),"gap <= -20%",pre)
