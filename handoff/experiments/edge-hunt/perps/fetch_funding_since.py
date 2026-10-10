"""Hourly funding since a date for the coins a set of rules held (perps lane), so candidates can be
charged funding without fetching every perp's full history.

    python3 handoff/experiments/edge-hunt/perps/fetch_funding_since.py CACHE_DIR 2025-04-01 COIN [COIN ...]

Cache: CACHE_DIR/<coin>.json, {hour index: rate}, same format as crosssection/fetch_hl_funding.py
but starting at the given date (so kept apart from that cache, which holds full histories).
"""
import datetime as dt
import json
import sys
import time
from pathlib import Path

import httpx

HL = "https://api.hyperliquid.xyz/info"
cache = Path(sys.argv[1]); cache.mkdir(parents=True, exist_ok=True)
start = int(dt.datetime.fromisoformat(sys.argv[2]).replace(tzinfo=dt.timezone.utc).timestamp() * 1000)
c = httpx.Client(timeout=60)
for k, coin in enumerate(sys.argv[3:]):
    if (cache / f"{coin}.json").exists():
        continue
    out, s = {}, start
    while True:
        r = None
        for i in range(8):
            try:
                r = c.post(HL, json={"type": "fundingHistory", "coin": coin, "startTime": s})
                if r.status_code == 200:
                    break
            except httpx.HTTPError:
                pass
            time.sleep(2 * (i + 1))
        part = r.json() if r is not None and r.status_code == 200 else []
        if not part:
            break
        for x in part:
            out[x["time"] // 3600_000] = float(x["fundingRate"])
        s = part[-1]["time"] + 1
        if len(part) < 500:
            break
        time.sleep(0.4)
    (cache / f"{coin}.json").write_text(json.dumps(out))
    print(f"{k + 1}/{len(sys.argv) - 3} {coin}: {len(out)} hours", flush=True)
