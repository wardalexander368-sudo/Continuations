"""US-expressible momentum (AJ 2026-10-11: US venues only). Long top-quintile 14-day momentum held as spot
(Coinbase-style, no shorting) and hedged with a BTC short (Coinbase's CFTC perp), vs the long-short book that needs
Hyperliquid. HL daily closes as the price proxy. Run: python3 handoff/experiments/us_momentum.py"""
import csv, numpy as np
from datetime import date, timedelta
from pathlib import Path
from tartar.autotrade.hl_data import DAILY_DIR
rows={}
for f in sorted(Path(DAILY_DIR).glob("*.csv")):
    rows[f.stem]={r["day"]:(float(r["close"]),float(r["volume"])*float(r["close"])) for r in csv.DictReader(f.open())}
days=sorted({d for r in rows.values() for d in r}); ix={d:i for i,d in enumerate(days)}
coins=sorted(rows); C=np.full((len(days),len(coins)),np.nan); V=C.copy()
for j,c in enumerate(coins):
    for d,(cl,v) in rows[c].items(): C[ix[d],j]=cl; V[ix[d],j]=v
b=coins.index("BTC")
res={}
for i in range(80,len(days)-8):
    d=date.fromisoformat(days[i])
    if d.weekday()!=0 or d<date(2023,12,1): continue
    e,x=i+1,i+8
    hist=~np.isnan(C[i-59:i+1]).any(0)
    medv=np.nanmedian(V[i-29:i+1],0)
    ok=hist&(medv>=2e6)&~np.isnan(C[x])
    sig=C[i]/C[i-14]-1
    ids=np.where(ok&np.isfinite(sig))[0]
    if len(ids)<15: continue
    o=ids[np.argsort(sig[ids])]; q=len(o)//5
    top=o[-q:]; bot=o[:q]
    rl=np.mean(C[x,top]/C[e,top]-1); rs=np.mean(C[x,bot]/C[e,bot]-1); rb=C[x,b]/C[e,b]-1
    res[d]=(rl,rs,rb,set(coins[k] for k in top))
ks=sorted(res); prev=set(); out={"ls":[], "long_hedged":[], "long_only":[], "turn":[]}
for k in ks:
    rl,rs,rb,top=res[k]
    turn=1-len(top&prev)/max(len(top),1); prev=top
    out["ls"].append(rl-rs); out["long_hedged"].append(rl-rb); out["long_only"].append(rl); out["turn"].append(turn)
n=len(ks); print("weeks",n, "mean turnover of long leg", np.mean(out["turn"]))
for name in ("ls","long_hedged","long_only"):
    x=np.array(out[name]); print(f"{name:12s} gross {100*x.mean():+.2f}%/wk  sd {100*x.std():.1f}  worst {100*x.min():+.1f}  ex-best5 {100*np.sort(x)[:-5].mean():+.2f}")
x=np.array(out["long_hedged"]); t=np.array(out["turn"])
for c in (0.001,0.002,0.004,0.006):
    net=x-2*c*t-0.0005  # spot legs' turnover cost both sides + hedge roll small
    print(f"long top-quintile, BTC-hedged, spot cost {c*1e4:.0f} bps/side: {100*net.mean():+.2f}%/wk, ex-best5 {100*np.sort(net)[:-5].mean():+.2f}")
h=n//2; print("first half", 100*x[:h].mean(), "second half", 100*x[h:].mean(), "last 26", 100*x[-26:].mean())
