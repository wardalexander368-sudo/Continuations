"""Every Hyperliquid vault's history, closed vaults included (vault-following study).

    python3 handoff/experiments/edge-hunt/vaults/fetch_vaults.py CACHE_DIR [MIN_ABS_PNL]

The vault list (with closed vaults) comes from stats-data.hyperliquid.xyz/Mainnet/vaults; a vault
is fetched (info `vaultDetails`: allTime account value and PnL history, leader commission, create
time) if its all-time PnL path ever reached MIN_ABS_PNL dollars in absolute value (default 1000),
so a filter on size, not on sign. Cache: CACHE_DIR/list.json and CACHE_DIR/<address>.json.
"""
import json
import sys
import time
from pathlib import Path

import httpx

cache = Path(sys.argv[1]); cache.mkdir(parents=True, exist_ok=True)
min_pnl = float(sys.argv[2]) if len(sys.argv) > 2 else 1000.0
c = httpx.Client(timeout=60)
lst = cache / "list.json"
if not lst.exists():
    lst.write_text(c.get("https://stats-data.hyperliquid.xyz/Mainnet/vaults").text)
vaults = json.loads(lst.read_text())
todo = [v["summary"]["vaultAddress"] for v in vaults if max(abs(float(x)) for x in dict(v["pnls"])["allTime"]) >= min_pnl]
print(f"{len(todo)} of {len(vaults)} vaults to fetch", flush=True)
for k, addr in enumerate(todo):
    f = cache / f"{addr}.json"
    if f.exists():
        continue
    for i in range(8):
        try:
            r = c.post("https://api.hyperliquid.xyz/info", json={"type": "vaultDetails", "vaultAddress": addr})
            if r.status_code == 200:
                d = r.json()
                keep = {k2: d.get(k2) for k2 in ("name", "vaultAddress", "leader", "leaderCommission", "leaderFraction", "isClosed", "allowDeposits")}
                keep["portfolio"] = {n: p for n, p in d["portfolio"] if n == "allTime"}
                f.write_text(json.dumps(keep))
                break
        except (httpx.HTTPError, ValueError):
            pass
        time.sleep(3 * (i + 1))
    time.sleep(0.3)
    if k % 100 == 0:
        print(f"{k}/{len(todo)}", flush=True)
print("done", flush=True)
