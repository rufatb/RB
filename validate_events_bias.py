"""Is the gap-down bounce REAL, or is it survivorship bias + market beta?

Two discriminating tests:
 A) LIQUIDITY/SIZE SPLIT. Survivorship bias needs delistings. In the largest,
    most liquid names delisting is near-zero, so if the effect is bias it should
    WEAKEN or vanish there and be concentrated in the smaller names.
 B) IDIOSYNCRATIC vs MARKET-DAY. If gap-downs cluster on market-wide down days,
    the 'bounce' is just high-beta names recovering with the tape. Split by
    whether the MARKET fell that day.
"""
import pandas as pd, numpy as np
df=pd.read_csv("daily.csv").sort_values(["t","date"]).reset_index(drop=True)
g=df.groupby("t",group_keys=False)
df["prev_c"]=g["c"].shift(1); df["gap"]=(df.o/df.prev_c-1)*100
df["ret_d"]=(df.c/df.prev_c-1)*100
for n in (5,10): df[f"f{n}"]=(g["c"].shift(-n)/df.c-1)*100
mkt=df.groupby("date")[["ret_d","f5","f10"]].median(); mkt.columns=["m_ret","m5","m10"]
df=df.join(mkt,on="date")
for n in (5,10): df[f"r{n}"]=df[f"f{n}"]-df[f"m{n}"]
df["dv"]=df.c*df.v                                   # dollar volume
med_dv=df.groupby("t")["dv"].median()
df["size_q"]=df.t.map(pd.qcut(med_dv,4,labels=[1,2,3,4]).astype(int))
dates=sorted(df.date.unique()); blocks=np.array_split(np.array(dates),5)
bo={d:i for i,b in enumerate(blocks) for d in b}; df["blk"]=df.date.map(bo)

ev=df[(df.gap<=-5)&(df.gap>-10)].dropna(subset=["r5"])
print(f"EVENT: gap -5% to -10%,  n={len(ev)} over 10y\n")
print("A) BY LIQUIDITY QUARTILE (4 = largest/most liquid; bias needs delistings)")
for q in (1,2,3,4):
    s=ev[ev.size_q==q]
    if len(s)<60: print(f"   Q{q} n={len(s)} too few"); continue
    sg=[np.sign(s[s.blk==b]["r5"].mean()) if len(s[s.blk==b])>=15 else 0 for b in range(5)]
    cons=all(x>0 for x in sg if x!=0) or all(x<0 for x in sg if x!=0)
    print(f"   Q{q}  n={len(s):>4}  rel-5d {s['r5'].mean():+.3f}%  rel-10d {s['r10'].mean():+.3f}%  "
          f"win5 {100*(s['r5']>0).mean():.0f}%  blocks {'CONSISTENT' if cons else 'FLIP'} {[int(x) for x in sg]}")
print("\nB) WAS IT A MARKET-WIDE DOWN DAY? (beta-bounce check)")
for lab,sub in (("market DOWN that day",ev[ev.m_ret<0]),("market UP that day",ev[ev.m_ret>=0])):
    if len(sub)<60: continue
    sg=[np.sign(sub[sub.blk==b]["r5"].mean()) if len(sub[sub.blk==b])>=15 else 0 for b in range(5)]
    cons=all(x>0 for x in sg if x!=0) or all(x<0 for x in sg if x!=0)
    print(f"   {lab:<22} n={len(sub):>4}  rel-5d {sub['r5'].mean():+.3f}%  "
          f"win5 {100*(sub['r5']>0).mean():.0f}%  blocks {'CONSISTENT' if cons else 'FLIP'} {[int(x) for x in sg]}")
print("\nC) MEDIAN vs MEAN (a few huge rebounds can carry a mean)")
print(f"   rel-5d  mean {ev['r5'].mean():+.3f}%   MEDIAN {ev['r5'].median():+.3f}%   "
      f"win rate {100*(ev['r5']>0).mean():.1f}%")
print(f"   rel-10d mean {ev['r10'].mean():+.3f}%   MEDIAN {ev['r10'].median():+.3f}%   "
      f"win rate {100*(ev['r10']>0).mean():.1f}%")
