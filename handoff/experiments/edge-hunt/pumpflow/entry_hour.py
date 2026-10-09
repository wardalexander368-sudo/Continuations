"""E1: how late on day d+1 can the PUMP trade enter and keep the edge? (hourly HL candles, last ~208 days)

Position sign(rev_surprise_d) held 24 h from hour H of day d+1. Prints mean net and timing part.
"""
import json, time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import httpx
import numpy as np

D = Path("handoff/data/edge-hunt/pumpflow")
COST = 0.001
cache = D / "pump-1h.json"
if not cache.exists():
    with httpx.Client(timeout=60) as c:
        end = int(time.time() * 1000); out = {}
        s = end - 5000 * 3600_000
        while s < end:
            part = c.post("https://api.hyperliquid.xyz/info", json={"type": "candleSnapshot", "req": {"coin": "PUMP", "interval": "1h", "startTime": s, "endTime": end}}).json()
            if not part:
                break
            for x in part:
                out[x["t"] // 3600_000] = float(x["o"])
            s = part[-1]["t"] + 3600_000
        cache.write_text(json.dumps(out))
H = {int(k): v for k, v in json.loads(cache.read_text()).items()}
flow = json.loads((D / "flow.json").read_text())
fund = json.loads((D / "perps.json").read_text())["PUMP"]["funding"]
days = sorted(flow)
rev = np.array([(flow[d].get("pump.fun-dailyRevenue") or 0) + (flow[d].get("pumpswap-dailyRevenue") or 0) for d in days])
sig = {days[i]: np.log(rev[i] / rev[i - 7:i].mean()) for i in range(7, len(days)) if rev[i] > 0 and rev[i - 7:i].mean() > 0}
print(f"hourly opens {len(H)} from {datetime.fromtimestamp(min(H) * 3600, timezone.utc)}")
for hh in (0, 1, 2, 4, 6, 8, 12, 16):
    pos, ret = [], []
    for d, s in sig.items():
        t0 = int(datetime.fromisoformat(d).replace(tzinfo=timezone.utc).timestamp() // 3600) + 24 + hh
        if t0 in H and t0 + 24 in H:
            pos.append(np.sign(s)); ret.append(H[t0 + 24] / H[t0] - 1 - fund.get((date.fromisoformat(d) + timedelta(days=1)).isoformat(), 0))
    pos, ret = np.array(pos), np.array(ret)
    net = pos * ret - COST * np.abs(np.diff(np.r_[0, pos]))
    tim = net - pos.mean() * ret
    se = tim.std() / np.sqrt(len(tim))
    print(f"enter {hh:02d}:00 UTC d+1  n={len(pos)}  net {net.mean():+.3%}/day  timing {tim.mean():+.3%} ± {1.645 * se:.3%} (90%)")
