"""Append externally published baseline records without overwriting earlier values.

Only ledger.csv and universe_prints.csv are accepted. Never execute source code,
merge a branch, adopt advice, or convert recorded selections into actual holdings.
"""
import argparse
import csv
import io
import json
from pathlib import Path
import subprocess
from build_biotech import write_atomic

FILES={'ledger.csv':('date','ticker','side','role'),'universe_prints.csv':('date','ticker')}


def merge(target, incoming, fields):
    """All-or-nothing conflict check. Existing values, including blanks, immutable."""
    index={tuple(r.get(k,'') for k in fields):r for r in target}
    if len(index)!=len(target): raise ValueError('duplicate existing runtime keys')
    additions=[]
    for row in incoming:
        key=tuple(row.get(k,'') for k in fields)
        if key in index:
            if row!=index[key]: raise ValueError('conflicting published runtime record '+str(key))
        else:
            if not all(key): raise ValueError('missing runtime identity')
            index[key]=row;additions.append(row)
    return target+additions,additions


def sync(root,state,source_ref=None):
    root=Path(root);state=Path(state);state.mkdir(parents=True,exist_ok=True)
    path=state/'runtime_deltas.json'
    deltas=json.loads(path.read_text()) if path.exists() else {}
    updates={}
    for name,keys in FILES.items():
        base=list(csv.DictReader(io.StringIO((root/name).read_text())))
        fieldnames=next(csv.reader(io.StringIO((root/name).read_text())))
        hydrated,_=merge(base,deltas.get(name,[]),keys)
        if source_ref:
            raw=subprocess.run(['git','show',source_ref+':'+name],cwd=root,
                               capture_output=True,text=True,check=True).stdout
            incoming=list(csv.DictReader(io.StringIO(raw)))
            if next(csv.reader(io.StringIO(raw)))!=fieldnames: raise ValueError('runtime schema conflict')
            hydrated,added=merge(hydrated,incoming,keys)
            deltas[name]=merge(deltas.get(name,[]),added,keys)[0]
        out=io.StringIO();writer=csv.DictWriter(out,fieldnames=fieldnames)
        writer.writeheader();writer.writerows(hydrated)
        updates[name]=out.getvalue()
    for name,value in updates.items(): (root/name).write_text(value)
    if source_ref: deltas['_source_ref']=source_ref
    write_atomic(path,deltas)
    return {name:len(deltas.get(name,[])) for name in FILES}


def export(root,state):
    root=Path(root);path=Path(state)/'runtime_deltas.json'
    deltas=json.loads(path.read_text()) if path.exists() else {}
    for name,keys in FILES.items():
        raw=subprocess.run(['git','show','HEAD:'+name],cwd=root,capture_output=True,text=True,check=True).stdout
        base=list(csv.DictReader(io.StringIO(raw)))
        current=list(csv.DictReader(io.StringIO((root/name).read_text())))
        _,added=merge(base,current,keys)
        deltas[name]=merge(deltas.get(name,[]),added,keys)[0]
    write_atomic(path,deltas)
    return {name:len(deltas.get(name,[])) for name in FILES}


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--root',default='.');p.add_argument('--state-dir',required=True)
    p.add_argument('--source-ref')
    p.add_argument('--export',action='store_true')
    a=p.parse_args();print(json.dumps(export(a.root,a.state_dir) if a.export else sync(a.root,a.state_dir,a.source_ref)))
