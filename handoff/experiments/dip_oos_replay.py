"""Replay the registered dip rule on GeckoTerminal SOL-quoted 5-minute bars, only on bars after each
cohort registered (out of sample), one position per pool. Prints gross per trade (before costs)."""
import json,time,httpx,statistics,glob
from datetime import datetime
P='handoff/preregistration/dip-rolling/'
rule=json.load(open(P+'SPEC.json'))['rule']; L,H,D=rule['lookback_bars'],rule['hold_bars'],rule['drop']
h=httpx.Client(timeout=30,headers={'accept':'application/json'})
seen=set(); pools=[]
for f in sorted(glob.glob(P+'cohort-*.json')):
    c=json.load(open(f)); reg=datetime.fromisoformat(c['registered_at'].replace('Z','+00:00')).timestamp()
    for p in c['pools']:
        if p['token'] not in seen: seen.add(p['token']); pools.append({**p,'reg':reg})
trades=[]; now=time.time()
for p in pools:
    for a in range(5):
        r=h.get(f"https://api.geckoterminal.com/api/v2/networks/solana/pools/{p['pool']}/ohlcv/minute",params={'aggregate':5,'limit':1000,'currency':'token'})
        if r.status_code==200: break
        time.sleep(10)
    rows=sorted([[int(x[0])]+[float(v) for v in x[1:]] for x in r.json()['data']['attributes']['ohlcv_list']]); time.sleep(2.3)
    rows=[x for x in rows if x[0]+300<=now]
    by={x[0]:x for x in rows}; t=list(range(rows[0][0],rows[-1][0]+300,300)); o=[];c=[];prev=rows[0][4]
    for ti in t:
        x=by.get(ti); o.append(prev if x is None else x[1]); c.append(prev if x is None else x[4]); prev=c[-1]
    busy=0
    for i in range(L,len(t)-H-1):
        if t[i]<p['reg'] or t[i]<=busy: continue
        if c[i]/c[i-L]-1<-D:
            trades.append({'name':p['name'],'t':t[i],'gross':c[i+H]/o[i+1]-1}); busy=t[i]+H*300
json.dump(trades,open('handoff/data/dip-cost/replay-oos.json','w'))
g=[x['gross'] for x in trades]
print(len(trades),'OOS rule trades (SOL-quoted bars, after each cohort registered); gross mean %+.2f%% SE %.2f median %+.2f%%'%(100*statistics.mean(g),100*statistics.stdev(g)/len(g)**.5,100*statistics.median(g)))
print('from',datetime.utcfromtimestamp(min(x['t'] for x in trades)),'to',datetime.utcfromtimestamp(max(x['t'] for x in trades)))
