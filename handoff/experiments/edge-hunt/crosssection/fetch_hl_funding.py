"""Hourly funding history for every Hyperliquid perp (cache: handoff/data/edge-hunt/hl-funding/<coin>.json).

    python3 handoff/experiments/edge-hunt/crosssection/fetch_hl_funding.py

Same cache format as xs_funding.py ({hour index: rate}); coins already cached are skipped.
"""
import json, time
from pathlib import Path
import httpx

HL = "https://api.hyperliquid.xyz/info"
CACHE = Path("handoff/data/edge-hunt/hl-funding"); CACHE.mkdir(parents=True, exist_ok=True)
c = httpx.Client(timeout=60)
coins = [u["name"] for u in json.loads(Path("handoff/data/edge-hunt/hl-daily/meta.json").read_text())]
todo = [x for x in coins if not (CACHE / f"{x}.json").exists()]
for k, coin in enumerate(todo):
    out, s = {}, 1685577600000      # 2023-06-01
    while True:
        for i in range(8):
            try:
                r = c.post(HL, json={"type": "fundingHistory", "coin": coin, "startTime": s})
                if r.status_code == 200: break
            except httpx.HTTPError:
                pass
            time.sleep(3 * (i + 1))
        part = r.json()
        if not part: break
        for x in part: out[x["time"] // 3600_000] = float(x["fundingRate"])
        s = part[-1]["time"] + 1
        if len(part) < 500: break
        time.sleep(0.25)
    (CACHE / f"{coin}.json").write_text(json.dumps(out))
    print(f"{k + 1}/{len(todo)} {coin}: {len(out)} hours", flush=True)
