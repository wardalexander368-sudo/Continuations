"""Coinbase Exchange 15-minute candles (public API, no key) for the chart-pattern study.

    python3 handoff/experiments/edge-hunt/patterns/fetch_coinbase.py CACHE_DIR [--from 2020-01-01]

Writes CACHE_DIR/<COIN>.csv (t, open, high, low, close, volume; t = bar start, unix seconds),
resuming from the last bar. 300 bars per request, ~4 requests a second.
"""
from __future__ import annotations

import datetime as dt
import sys
import time
from pathlib import Path

import httpx

COINS = ["BTC", "ETH", "SOL", "XRP", "DOGE", "ADA", "AVAX", "LINK", "LTC", "BCH", "DOT"]
G = 900
out = Path(sys.argv[1]); out.mkdir(parents=True, exist_ok=True)
start0 = sys.argv[sys.argv.index("--from") + 1] if "--from" in sys.argv else "2020-01-01"
t_start = int(dt.datetime.fromisoformat(start0).replace(tzinfo=dt.timezone.utc).timestamp())
now = int(time.time()) // G * G
c = httpx.Client(timeout=30)
for coin in COINS:
    f = out / f"{coin}.csv"
    t = int(f.read_text().strip().splitlines()[-1].split(",")[0]) + G if f.exists() and f.stat().st_size else t_start
    n = 0
    with f.open("a") as fh:
        while t < now:
            t1 = min(t + 300 * G, now)
            rows = None
            for i in range(6):
                try:
                    r = c.get(f"https://api.exchange.coinbase.com/products/{coin}-USD/candles", params={
                        "granularity": G, "start": dt.datetime.fromtimestamp(t, dt.timezone.utc).isoformat(),
                        "end": dt.datetime.fromtimestamp(t1 - G, dt.timezone.utc).isoformat()})
                    if r.status_code == 200:
                        rows = r.json(); break
                except httpx.HTTPError:
                    pass
                time.sleep(2 * (i + 1))
            if rows is None:
                print(f"{coin}: gave up at {t}", flush=True); break
            for ts, lo, hi, op, cl, v in sorted(rows):
                if t <= ts < t1:
                    fh.write(f"{ts},{op},{hi},{lo},{cl},{v}\n"); n += 1
            t = t1
            time.sleep(0.25)
    print(f"{coin}: +{n} bars", flush=True)
print("done", flush=True)
