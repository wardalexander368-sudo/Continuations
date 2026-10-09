"""Score direction-probability variants on blend_calibration.py output (trading candles; --all for every candle).

    python3 handoff/experiments/blend_calibration_variants.py FILE.jsonl [--all]
"""
import json, sys, math, numpy as np, datetime
rows=[json.loads(l) for l in open(sys.argv[1])]
tr=[r for r in rows if r["trading"]] if "--all" not in sys.argv else rows
def h(r): return datetime.datetime.fromtimestamp(r["t"], datetime.UTC).hour
lg=lambda p: math.log(p/(1-p)); sg=lambda x: 1/(1+math.exp(-x))
def final_q(r): return r["p_up"]/max(r["p_up"]+r["p_down"],1e-12)
def slope(r):
    qr=min(max(r["q_raw"],1e-9),1-1e-9); qf=min(max(final_q(r),1e-9),1-1e-9)
    return lg(qf)/lg(qr) if abs(lg(qr))>1e-6 else 1.0
def online_share(r):
    a=1+(slope(r)-1)*(1-r["w"]); qr=min(max(r["q_raw"],1e-9),1-1e-9); return sg(a*lg(qr))
def score(sub, qfun):
    m=np.array([r["p_flat"] for r in sub]); q=np.array([qfun(r) for r in sub])
    P=np.stack([(1-m)*q,(1-m)*(1-q),m],1); call=P.argmax(1); conf=P.max(1)
    act=np.array([{"up":0,"down":1,"flat":2}[r["actual"]] for r in sub])
    ll=-np.mean(np.log(np.clip(P[np.arange(len(act)),act],1e-12,1)))
    return (call==act).mean(), conf.mean(), ll
V={"current": final_q, "calibrator x (1-w)": online_share, "no calibrator": lambda r: r["q_raw"],
   "global q only": lambda r: r["g_up"] if r["g_up"] is not None else r["q_raw"]}
hours=sorted({h(r) for r in tr})
print(f"{len(tr)} candles;", "variant".ljust(20), "hit/stated gap  logloss", " ".join(f"h{x:>2}" for x in hours))
for name,f in V.items():
    hit,conf,ll=score(tr,f)
    per=[score([r for r in tr if h(r)==x],f) for x in hours]
    print(" "*12, name.ljust(20), f"{hit:.3f}/{conf:.3f} {hit-conf:+.3f}  {ll:.4f}", " ".join(f"{a-b:+.3f}" for a,b,_ in per))
