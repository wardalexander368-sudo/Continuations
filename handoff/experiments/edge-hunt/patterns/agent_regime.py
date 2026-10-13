"""Agent-surge regime check (2026-10-13, exploratory; see handoff/reviews/agent-surge-2026-10-13.md).

    python3 handoff/experiments/edge-hunt/patterns/agent_regime.py /mnt/project-files/data/coinbase-hourly

Has CAPIT (Z=4 H=24) changed over time? Crash days, sharpness and bounce by half-year.
Hourly closes from the 21-coin cache; entry at the next hourly close (~60 min, between the
registered 30 min and the real ~90 min), exit 24 h later, 0.39%/side. "worsthr/24h" = worst single-hour return over the
24-hour log drop at the signal (higher = sharper, more one-hour crashes). daymean = mean of per-day means."""
import json, sys, datetime as dt, numpy as np
from collections import defaultdict
D = sys.argv[1]
COINS = "BTC ETH SOL XRP DOGE ADA AVAX LINK LTC BCH DOT AAVE UNI SHIB CRV GRT XTZ BAT SUSHI YFI PEPE".split()
COST = 0.0039
per = defaultdict(lambda: dict(days=set(), rets=[], sharp=[], dayrets=defaultdict(list)))
def period(h):
    d = dt.datetime.fromtimestamp(h*3600, dt.timezone.utc)
    return f"{d.year}H{1 if d.month<=6 else 2}", d.date().isoformat()
for c in COINS:
    raw = json.load(open(f"{D}/{c}.json"))
    hs = np.array(sorted(int(k) for k in raw)); h0 = hs[0]; n = hs[-1]-h0+1
    C = np.full(n, np.nan); C[hs-h0] = [raw[str(h)][0] for h in hs]
    R = np.full(n, np.nan); R[1:] = C[1:]/C[:-1]-1
    S = np.full(n, np.nan)
    for i in range(169, n):
        w = R[i-168:i]
        if not np.isnan(w).any(): S[i] = w.std()
    r24 = np.full(n, np.nan); r24[24:] = C[24:]/C[:-24]-1
    sig = r24 <= -4*S*np.sqrt(24)
    busy = -1
    for i in np.nonzero(sig)[0]:
        e, x = i+1, i+25
        if i < busy or x >= n or np.isnan(C[e]) or np.isnan(C[x]): continue
        p, day = period(h0+i)
        r = C[x]/C[e]-1-2*COST
        P = per[p]; P["days"].add(day); P["rets"].append(r); P["dayrets"][day].append(r)
        w = R[i-23:i+1]
        if not np.isnan(w).any(): P["sharp"].append(np.min(w)/np.log1p(r24[i]) if r24[i] < 0 else np.nan)
        busy = i+25
print(f"{'period':8} {'crashdays':>9} {'trades':>6} {'mean%':>7} {'daymean%':>8} {'worsthr/24h':>11}")
allday = []
for p in sorted(per):
    P = per[p]; dm = [np.mean(v) for v in P["dayrets"].values()]; allday += dm
    print(f"{p:8} {len(P['days']):9d} {len(P['rets']):6d} {100*np.mean(P['rets']):7.2f} {100*np.mean(dm):8.2f} {np.nanmean(P['sharp']):11.2f}")
