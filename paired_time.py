#!/usr/bin/env python3
"""PAIRED test: 9:40 vs 9:45 decision. Where both times pick the SAME
ticker+side on the same session, the only difference is the entry price —
a high-power paired comparison. Also measures how often selection differs."""
import sys, os
sys.path.insert(0, "/home/user/RB")
import numpy as np, pandas as pd
import validate_deep as vd, validate_pair as vp, validate_time_deep as vtd
from dashboard import load_config

cfg = load_config("/home/user/RB/config.yaml")
raw=[vd.load_bars(os.path.join(vd.require_data(),f)) for f in sorted(os.listdir(vd.require_data())) if f.endswith(".json")]

def legs_at(i):
    rows=[]
    for tsx,bars in raw: rows += vtd.session_rows_at(bars,tsx,i)
    df=pd.DataFrame(rows)
    day_log=vp.walk_forward(df,cfg)
    out={}
    for dl in day_log:
        for side in ("longs","shorts"):
            if dl[side]:
                lg=min(dl[side],key=lambda b:b["nd"])
                out[(dl["date"],side)]=lg
    return out

A=legs_at(1)   # 9:40
B=legs_at(2)   # 9:45
keys=set(A)&set(B)
same=[k for k in keys if A[k]["t"]==B[k]["t"]]
diff=[k for k in keys if A[k]["t"]!=B[k]["t"]]
print(f"sessions/sides where both times qualified: {len(keys)}")
print(f"  SAME name+side: {len(same)} ({len(same)/len(keys)*100:.0f}%)   different name: {len(diff)}")

d=[A[k]["capt"]-B[k]["capt"] for k in same]
print(f"\nPAIRED (same pick, entry 5 min earlier): mean diff {np.mean(d):+.4f}%  "
      f"median {np.median(d):+.4f}%  std {np.std(d):.3f}%")
se=np.std(d)/np.sqrt(len(d)); print(f"  t = {np.mean(d)/se:+.2f}  (n={len(d)} paired legs)")
print(f"  9:40 better on {sum(1 for x in d if x>0)}/{len(d)} legs")

print(f"\nWhere the two times pick DIFFERENT names (n={len(diff)}):")
print(f"  9:40 pick capture {np.mean([A[k]['capt'] for k in diff]):+.3f}%  hit {np.mean([A[k]['hit'] for k in diff])*100:.0f}%")
print(f"  9:45 pick capture {np.mean([B[k]['capt'] for k in diff]):+.3f}%  hit {np.mean([B[k]['hit'] for k in diff])*100:.0f}%")
