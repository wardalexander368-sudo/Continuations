"""Hourly SOL/ETH/BTC candles from Coinbase (public, no key) for the JLP hedge stress test.

    python3 handoff/experiments/edge-hunt/jlp_stress_fetch.py   -> data/jlp-stress/cb_<COIN>-USD_1h.json (not in git)
"""
import json
import time
from datetime import datetime, timezone
from pathlib import Path

import httpx

OUT = Path("data/jlp-stress")
START = datetime(2021, 7, 1, tzinfo=timezone.utc).timestamp()
c = httpx.Client(timeout=30)


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    end = time.time()
    for coin in ("SOL", "ETH", "BTC"):
        rows, t = {}, START
        while t < end:
            t1 = min(t + 300 * 3600, end)
            q = {"granularity": 3600, "start": datetime.fromtimestamp(t, timezone.utc).isoformat(),
                 "end": datetime.fromtimestamp(t1, timezone.utc).isoformat()}
            for i in range(6):
                r = c.get(f"https://api.exchange.coinbase.com/products/{coin}-USD/candles", params=q)
                if r.status_code == 200:
                    break
                time.sleep(2 * (i + 1))
            for x in r.json():  # [time, low, high, open, close, volume]
                rows[int(x[0])] = x[1:5]
            t = t1
            time.sleep(0.35)
        (OUT / f"cb_{coin}-USD_1h.json").write_text(json.dumps(sorted(rows.items())))
        print(coin, len(rows), flush=True)


if __name__ == "__main__":
    main()
