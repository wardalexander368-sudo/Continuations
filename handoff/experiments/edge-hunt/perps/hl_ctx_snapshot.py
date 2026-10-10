"""One snapshot of every Hyperliquid perp's open interest, funding, mark price and 24 h volume.

    python3 handoff/experiments/edge-hunt/perps/hl_ctx_snapshot.py   # appends to handoff/data/edge-hunt/hl-ctx/<YYYY-MM>.jsonl

Hyperliquid's public API has no open-interest or liquidation history, so OI-based rules (perps
lane) can only be tested on data we record. The `perps-ctx` GitHub Action runs this every 4 hours;
no key, no session. One line per snapshot: {"t": unix seconds, "ctx": {coin: [oi_coins, funding,
mark, day_ntl_vlm, premium]}}.
"""
import datetime as dt
import json
import time
from pathlib import Path

import httpx

for i in range(5):
    try:
        r = httpx.post("https://api.hyperliquid.xyz/info", json={"type": "metaAndAssetCtxs"}, timeout=30)
        r.raise_for_status()
        break
    except httpx.HTTPError:
        time.sleep(5 * (i + 1))
meta, ctxs = r.json()
now = time.time()
row = {"t": round(now, 1), "ctx": {}}
for u, c in zip(meta["universe"], ctxs):
    f = lambda k: float(c[k]) if c.get(k) not in (None, "") else None
    row["ctx"][u["name"]] = [f("openInterest"), f("funding"), f("markPx"), f("dayNtlVlm"), f("premium")]
out = Path("handoff/data/edge-hunt/hl-ctx") / (dt.datetime.fromtimestamp(now, dt.timezone.utc).strftime("%Y-%m") + ".jsonl")
out.parent.mkdir(parents=True, exist_ok=True)
with out.open("a") as fh:
    fh.write(json.dumps(row, separators=(",", ":")) + "\n")
print(f"{out}: {len(row['ctx'])} perps")
