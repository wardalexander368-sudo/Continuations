"""Collect 5-minute OHLCV for liquid, established Solana memecoin pools (GeckoTerminal).

    python3 handoff/experiments/established_collect.py [--out data/established] [--pages 10] [--history 2]

Universe: pools listed by 24 h volume, keeping memecoin pairs (base token not SOL or a
stablecoin) with liquidity >= $100k, 24 h volume >= $100k, and age >= 2 days. Each pool gets
`history` x 1000 five-minute candles (~3.5 days per page). The free API allows ~30 requests a
minute; requests are spaced 2.2 s apart.

Note: today's liquid pools are survivors. Studies on this data must compare against random
entries in the same pools (handoff/experiments/established_rules.py does).
"""
import argparse
import json
import time
from datetime import datetime, timezone
from pathlib import Path

import httpx

BASE = "https://api.geckoterminal.com/api/v2/networks/solana"
SKIP = {"SOL", "WSOL", "USDC", "USDT", "PYUSD", "USDS", "JITOSOL", "MSOL", "BSOL", "JUPSOL", "INF", "USD1"}

parser = argparse.ArgumentParser()
parser.add_argument("--out", default="data/established")
parser.add_argument("--pages", type=int, default=10)
parser.add_argument("--history", type=int, default=2, help="pages of 1000 five-minute candles per pool")
parser.add_argument("--min-liquidity", type=float, default=100_000)
parser.add_argument("--min-volume", type=float, default=100_000)
parser.add_argument("--min-age-days", type=float, default=2.0)
args = parser.parse_args()
out = Path(args.out)
out.mkdir(parents=True, exist_ok=True)
client = httpx.Client(timeout=30, headers={"accept": "application/json"})
last = 0.0


def get(path: str, **params):
    global last
    for attempt in range(6):
        wait = 2.2 - (time.time() - last)
        if wait > 0:
            time.sleep(wait)
        last = time.time()
        r = client.get(BASE + path, params=params)
        if r.status_code == 429:
            time.sleep(10 * (attempt + 1))
            continue
        r.raise_for_status()
        return r.json()
    raise RuntimeError(f"rate limited: {path}")


now = time.time()
pools = []
for page in range(1, args.pages + 1):
    data = get("/pools", page=page, sort="h24_volume_usd_desc")
    for p in data.get("data", []):
        a = p["attributes"]
        name = a.get("name") or ""
        base, _, quote = name.partition(" / ")
        created = a.get("pool_created_at")
        age = (now - datetime.fromisoformat(created.replace("Z", "+00:00")).timestamp()) / 86400 if created else 0
        liq = float(a.get("reserve_in_usd") or 0)
        vol = float((a.get("volume_usd") or {}).get("h24") or 0)
        if base.strip().upper() in SKIP or quote.split(" ")[0].strip().upper() not in ("SOL", "USDC", "WSOL"):
            continue
        if liq < args.min_liquidity or vol < args.min_volume or age < args.min_age_days:
            continue
        pools.append({"pool": a["address"], "name": name, "dex": p["relationships"]["dex"]["data"]["id"], "liquidity_usd": liq, "volume24_usd": vol, "created": created, "age_days": age})
print(f"{len(pools)} pools pass the filters")
for i, pool in enumerate(pools):
    path = out / f"{pool['pool']}.json"
    if path.exists():
        continue
    candles = {}
    before = None
    for _ in range(args.history):
        params = {"aggregate": 5, "limit": 1000, "currency": "usd"}
        if before:
            params["before_timestamp"] = before
        rows = get(f"/pools/{pool['pool']}/ohlcv/minute", **params)["data"]["attributes"]["ohlcv_list"]
        if not rows:
            break
        for t, o, h, l, c, v in rows:
            candles[int(t)] = [int(t), float(o), float(h), float(l), float(c), float(v)]
        before = min(int(r[0]) for r in rows)
        if len(rows) < 1000:
            break
    pool["candles"] = [candles[t] for t in sorted(candles)]
    pool["fetched"] = datetime.now(timezone.utc).isoformat()
    path.write_text(json.dumps(pool))
    print(f"[{i + 1}/{len(pools)}] {pool['name'][:30]:30s} {pool['dex']:22s} liq ${pool['liquidity_usd']:,.0f}  {len(pool['candles'])} candles", flush=True)
