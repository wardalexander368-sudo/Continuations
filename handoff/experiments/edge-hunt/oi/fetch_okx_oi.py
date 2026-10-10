"""Daily open-interest history from OKX for every Hyperliquid perp that has an OKX USDT swap (OI study).

    python3 handoff/experiments/edge-hunt/oi/fetch_okx_oi.py   # -> handoff/data/edge-hunt/okx-oi/<HL coin>.csv

Hyperliquid's public API keeps no OI history (only the current value, which `perps-ctx` records every
4 h from 2026-10-09). OKX's public rubik endpoint keeps daily OI from 2024-01-01, so it stands in for
market-wide positioning in each coin. Columns: day (UTC date of OKX's daily bucket), oi_ccy (OI in
coins), oi_usd. Hyperliquid's "k" coins (kPEPE = 1000 PEPE) map to the plain OKX coin; only the
percentage changes and USD values are used, so the unit does not matter. No key needed.
"""
import csv
import datetime as dt
import time
from pathlib import Path

import httpx

OKX = "https://www.okx.com/api/v5"
OUT = Path("handoff/data/edge-hunt/okx-oi")
OUT.mkdir(parents=True, exist_ok=True)
c = httpx.Client(timeout=30)


def get(path, **params):
    for i in range(6):
        try:
            r = c.get(f"{OKX}{path}", params=params)
            if r.status_code == 429:
                time.sleep(2 * (i + 1)); continue
            r.raise_for_status()
            x = r.json()
            if x.get("code") == "0":
                return x["data"]
            time.sleep(2 * (i + 1))
        except httpx.HTTPError:
            time.sleep(2 * (i + 1))
    raise RuntimeError(f"{path} {params}")


swaps = {i["instId"].split("-")[0] for i in get("/public/instruments", instType="SWAP") if i["instId"].endswith("-USDT-SWAP")}
hl = sorted(p.stem for p in Path("handoff/data/edge-hunt/hl-daily").glob("*.csv"))
pairs = []
for coin in hl:
    base = coin[1:] if coin.startswith("k") and coin[1:] in swaps else coin
    if base in swaps:
        pairs.append((coin, f"{base}-USDT-SWAP"))
print(f"{len(pairs)} of {len(hl)} Hyperliquid perps have an OKX USDT swap", flush=True)
for coin, inst in pairs:
    rows, end = {}, None
    while True:
        kw = {"instId": inst, "period": "1D", "limit": 100}
        if end:
            kw["end"] = end
        data = get("/rubik/stat/contracts/open-interest-history", **kw)
        time.sleep(0.45)  # 5 requests / 2 s
        new = [d for d in data if int(d[0]) not in rows]
        if not new:
            break
        for ts, _oi, oi_ccy, oi_usd in new:
            rows[int(ts)] = (float(oi_ccy), float(oi_usd))
        end = min(rows)
    with (OUT / f"{coin}.csv").open("w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["day", "oi_ccy", "oi_usd"])
        for ts in sorted(rows):
            w.writerow([dt.datetime.fromtimestamp(ts / 1000, dt.timezone.utc).date().isoformat(), *rows[ts]])
    print(coin, inst, len(rows), flush=True)
