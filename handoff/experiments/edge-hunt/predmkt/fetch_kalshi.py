"""Settled Kalshi markets and their hourly bid/ask before close (public API, no key).

    python3 handoff/experiments/edge-hunt/predmkt/fetch_kalshi.py CACHE_DIR [--per-series 1500]

Step 1: every settled market of each series below (live list ~2 months, older ones from
/historical/markets) (ticker, event, close time, result, volume) to
CACHE_DIR/markets.jsonl. Step 2: for a random sample (seed 1) of up to N markets per series with
volume >= 1,000 contracts, the hourly candles for the 26 hours before close (yes bid/ask/last) to
CACHE_DIR/candles/<ticker>.json, resuming.
"""
from __future__ import annotations

import datetime as dt
import json
import random
import sys
import time
from pathlib import Path

import httpx

B = "https://api.elections.kalshi.com/trade-api/v2"
SERIES = ["KXMLBGAME", "KXNBAGAME", "KXNFLGAME", "KXNHLGAME", "KXNCAAFGAME", "KXNCAAMBGAME", "KXEPLGAME",
          "KXHIGHNY", "KXHIGHCHI", "KXHIGHMIA", "KXHIGHAUS", "KXFED", "KXCPIYOY"]
# (the hourly crypto / index strike ladders, KXBTCD and friends, have ~10^5 markets each; left out)
cache = Path(sys.argv[1]); (cache / "candles").mkdir(parents=True, exist_ok=True)
N = int(sys.argv[sys.argv.index("--per-series") + 1]) if "--per-series" in sys.argv else 1500
c = httpx.Client(timeout=30)


def get(path, params):
    for i in range(8):
        try:
            r = c.get(B + path, params=params)
            if r.status_code == 200:
                return r.json()
            if r.status_code == 429:
                time.sleep(2 + 2 * i); continue
            if r.status_code in (400, 404):
                return None
        except (httpx.HTTPError, ValueError):
            pass
        time.sleep(2 * (i + 1))
    return None


mfile = cache / "markets.jsonl"
if not mfile.exists():
    rows = []
    for s, path in ((s, path) for s in SERIES for path in ("/markets", "/historical/markets")):
        cur, n = None, 0
        while True:
            p = {"series_ticker": s, "limit": 1000}
            if path == "/markets":
                p["status"] = "settled"
            if cur:
                p["cursor"] = cur
            d = get(path, p)
            if not d:
                break
            for m in d["markets"]:
                if m.get("market_type") != "binary" or m.get("result") not in ("yes", "no"):
                    continue
                rows.append({"t": m["ticker"], "s": s, "e": m["event_ticker"], "close": m["close_time"],
                             "open": m.get("open_time"), "res": m["result"], "vol": float(m.get("volume_fp") or m.get("volume") or 0)})
                n += 1
            cur = d.get("cursor")
            if not cur:
                break
            time.sleep(0.1)
        print(f"{s} {path}: {n} settled", flush=True)
    seen = set()
    rows = [r for r in rows if not (r["t"] in seen or seen.add(r["t"]))]
    mfile.write_text("".join(json.dumps(r) + "\n" for r in rows))
markets = [json.loads(l) for l in mfile.read_text().splitlines()]
by = {}
for m in markets:
    if m["vol"] >= 1000:
        by.setdefault(m["s"], []).append(m)
todo = []
for s, ms in by.items():
    random.Random(1).shuffle(ms)
    todo += ms[:N]
print(f"{len(todo)} markets for candles", flush=True)
for k, m in enumerate(todo):
    f = cache / "candles" / f"{m['t']}.json"
    if f.exists():
        continue
    end = int(dt.datetime.fromisoformat(m["close"].replace("Z", "+00:00")).timestamp())
    q = {"start_ts": end - 26 * 3600, "end_ts": end, "period_interval": 60}
    d = get(f"/series/{m['s']}/markets/{m['t']}/candlesticks", q) if m["close"] >= "2026-08" else None
    if not (d or {}).get("candlesticks"):  # archived markets: the historical endpoint, keys without "_dollars"
        d = get(f"/historical/markets/{m['t']}/candlesticks", q)
    out = []
    for x in (d or {}).get("candlesticks", []):
        g = lambda k2: (x.get(k2) or {}).get("close_dollars", (x.get(k2) or {}).get("close"))
        out.append([x["end_period_ts"], g("yes_bid"), g("yes_ask"), g("price"), x.get("volume_fp", x.get("volume"))])
    f.write_text(json.dumps(out))
    time.sleep(0.08)
    if k % 500 == 0:
        print(f"candles {k}/{len(todo)}", flush=True)
print("done", flush=True)
