"""Funding for the cross-sectional rule chosen on train (L=14 momentum), from Hyperliquid history.

    python3 handoff/experiments/edge-hunt/crosssection/xs_funding.py

Re-runs xs_rules.run(14, +1) keeping each week's legs, fetches hourly funding for every coin
ever held (cached in handoff/data/edge-hunt/hl-funding/), and reports the weekly return after
funding: a long pays the hourly rate, a short receives it (equal weight per leg).
"""
import importlib.util, json, sys, time
from datetime import datetime, timezone
from pathlib import Path
import httpx, numpy as np

spec = importlib.util.spec_from_file_location("xs", Path(__file__).with_name("xs_rules.py"))
xs = importlib.util.module_from_spec(spec); spec.loader.exec_module(xs)
CACHE = Path("handoff/data/edge-hunt/hl-funding"); CACHE.mkdir(parents=True, exist_ok=True)
c = httpx.Client(timeout=60)

def ms(day): return int(datetime.fromisoformat(day).replace(tzinfo=timezone.utc).timestamp() * 1000)

def funding(coin):
    f = CACHE / f"{coin}.json"
    if f.exists(): return {int(k): v for k, v in json.loads(f.read_text()).items()}
    out, s = {}, ms("2023-06-01")
    while True:
        for i in range(6):
            r = c.post("https://api.hyperliquid.xyz/info", json={"type": "fundingHistory", "coin": coin, "startTime": s})
            if r.status_code == 200: break
            time.sleep(3 * (i + 1))
        part = r.json()
        if not part: break
        for x in part: out[x["time"] // 3600_000] = float(x["fundingRate"])
        s = part[-1]["time"] + 1
        if len(part) < 500: break
        time.sleep(0.25)
    f.write_text(json.dumps(out))
    return out

rs = xs.run(14, +1)
held = sorted({c for r in rs for c in r[2] + r[3]})
F = {}
for k, coin in enumerate(held):
    F[coin] = funding(coin)
    if k % 20 == 0: print(f"funding {k}/{len(held)}", flush=True)

def leg_funding(coins, d0, d1):
    h0, h1 = ms(d0) // 3600_000, ms(d1) // 3600_000
    return np.mean([sum(F[c].get(h, 0.0) for h in range(h0, h1)) for c in coins])

net = [(d, r - leg_funding(L, d, d1) + leg_funding(S, d, d1), r) for d, r, L, S, d1 in rs if not np.isnan(r)]
for s, (a0, a1) in xs.SPLITS.items():
    part = [x for x in net if a0 <= x[0] <= a1]
    m, ci, n = xs.stats([(d, r) for d, r, _ in part])
    gross = np.mean([g for _, _, g in part])
    print(f"{s}: before funding {gross*100:+.2f}%/wk; after funding {m*100:+.2f}%/wk [{ci[0]*100:+.2f}, {ci[1]*100:+.2f}] n{n}")
