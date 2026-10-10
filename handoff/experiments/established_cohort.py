"""Add a cohort to the rolling dip pre-registration (handoff/preregistration/dip-rolling/).

    python3 handoff/experiments/established_cohort.py

Applies SPEC.json's universe rule *now* and writes cohort-<UTC time>.json with every qualifying
pool whose token isn't in an earlier cohort. Commit and push the file right away: the git
timestamp is part of the registration. Run it about once a day (any session).
"""
import json
import time
from datetime import datetime, timezone
from pathlib import Path

import httpx

DIR = Path("handoff/preregistration/dip-rolling")
BASE = "https://api.geckoterminal.com/api/v2/networks/solana"
SKIP = {"SOL", "WSOL", "USDC", "USDT", "PYUSD", "USDS", "USD1", "USDG", "JITOSOL", "MSOL", "BSOL", "JUPSOL", "INF"}
known = {p["token"] for f in DIR.glob("cohort-*.json") for p in json.loads(f.read_text())["pools"]}
client = httpx.Client(timeout=30, headers={"accept": "application/json"})
now = time.time()
now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
pools, seen = [], set()
for page in range(1, 11):
    for attempt in range(12):
        r = client.get(BASE + "/dexes/pumpswap/pools", params={"page": page, "sort": "h24_volume_usd_desc"})
        if r.status_code == 429:
            time.sleep(min(10 * (attempt + 1), 60))
            continue
        r.raise_for_status()
        break
    time.sleep(2.2)
    for p in r.json().get("data", []):
        a = p["attributes"]
        name = a.get("name") or ""
        base, _, quote = name.partition(" / ")
        created = a.get("pool_created_at")
        age = (now - datetime.fromisoformat(created.replace("Z", "+00:00")).timestamp()) / 86400 if created else 0
        liq = float(a.get("reserve_in_usd") or 0)
        vol = float((a.get("volume_usd") or {}).get("h24") or 0)
        token = p["relationships"]["base_token"]["data"]["id"]
        if base.strip().upper() in SKIP or quote.split(" ")[0].strip().upper() not in ("SOL", "WSOL") or token in seen or token in known:
            continue
        if liq < 30_000 or vol < 100_000 or age < 1.0:
            continue
        seen.add(token)
        pools.append({"pool": a["address"], "name": name, "token": token, "dex": "pumpswap", "liquidity_usd": liq, "volume24_usd": vol, "age_days": round(age, 2)})
n = len(list(DIR.glob("cohort-*.json"))) + 1
path = DIR / f"cohort-{now_iso[:16].replace(':', '')}.json"
path.write_text(json.dumps({"registered_at": now_iso, "cohort": n, "pools": pools}, indent=2))
print(f"{path}: cohort {n}, {len(pools)} new pools: " + "; ".join(p["name"] for p in pools))
