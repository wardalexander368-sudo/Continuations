"""Resolved Polymarket binary markets with daily price histories (prediction-market study).

    python3 handoff/experiments/edge-hunt/predmkt/fetch_polymarket.py CACHE_DIR [MIN_VOLUME] [--hist-min-vol V] [--hist-sample N]

Step 1: every closed market from gamma-api (paged), kept if it has two outcomes, resolved to
exactly 1/0, an end date 2023-01-01 .. 2026-09-30 and volume >= MIN_VOLUME (default $50k).
Step 2: the first outcome token's daily price history (clob `prices-history`, interval max,
fidelity 1440 minutes), for markets with volume >= V (default MIN_VOLUME), at most N of them
drawn at random (seed 1; default all). Cache: CACHE_DIR/markets.jsonl, CACHE_DIR/hist/<market id>.json.
"""
import json
import sys
import time
from pathlib import Path

import httpx

cache = Path(sys.argv[1]); (cache / "hist").mkdir(parents=True, exist_ok=True)
min_vol = float(sys.argv[2]) if len(sys.argv) > 2 and not sys.argv[2].startswith("--") else 5e4
hist_min_vol = float(sys.argv[sys.argv.index("--hist-min-vol") + 1]) if "--hist-min-vol" in sys.argv else min_vol
hist_n = int(sys.argv[sys.argv.index("--hist-sample") + 1]) if "--hist-sample" in sys.argv else None
c = httpx.Client(timeout=60)


def get(url, params):
    for i in range(8):
        try:
            r = c.get(url, params=params)
            if r.status_code == 200:
                return r.json()
        except (httpx.HTTPError, ValueError):
            pass
        time.sleep(2 * (i + 1))
    return None


mfile = cache / "markets.jsonl"
if not mfile.exists():
    import datetime as dt

    rows, seen = [], set()
    windows, d = [], dt.date(2023, 1, 1)
    while d < dt.date(2026, 10, 1):  # gamma caps offset at 2100, so page within half-month windows
        e = d + dt.timedelta(days=15) if d.day == 1 else (d.replace(day=28) + dt.timedelta(days=4)).replace(day=1)
        windows.append((d, min(e, dt.date(2026, 10, 1))))
        d = e
    for w0, w1 in windows:
      off = 0
      while off <= 2000:
        part = get("https://gamma-api.polymarket.com/markets", {"closed": "true", "limit": 100, "offset": off, "end_date_min": w0.isoformat(), "end_date_max": w1.isoformat(), "volume_num_min": min_vol})
        if not part or not isinstance(part, list):
            break
        for m in part:
            if m["id"] in seen:
                continue
            seen.add(m["id"])
            try:
                outs, prices, toks = json.loads(m["outcomes"]), json.loads(m["outcomePrices"]), json.loads(m["clobTokenIds"])
            except (KeyError, TypeError, ValueError):
                continue
            if len(outs) != 2 or sorted(prices) != ["0", "1"]:
                continue
            ev = (m.get("events") or [{}])[0]
            rows.append({"id": m["id"], "q": m["question"], "end": m.get("endDate"), "closed": m.get("closedTime"), "vol": m.get("volumeNum"),
                         "yes_won": prices[0] == "1", "token": toks[0], "event": ev.get("id"), "negRisk": m.get("negRisk"),
                         "fees": m.get("feesEnabled"), "cat": m.get("category") or ev.get("category"), "outcomes": outs})
        off += len(part)
        time.sleep(0.3)
        if len(part) < 100:
            break
      print(f"markets: window {w0}, kept {len(rows)}", flush=True)
    mfile.write_text("".join(json.dumps(r) + "\n" for r in rows))
markets = [json.loads(l) for l in mfile.read_text().splitlines()]
markets = [m for m in markets if (m.get("vol") or 0) >= hist_min_vol]
if hist_n is not None and len(markets) > hist_n:
    import random

    random.Random(1).shuffle(markets)
    markets = markets[:hist_n]
print(f"{len(markets)} markets for price history", flush=True)
for k, m in enumerate(markets):
    f = cache / "hist" / f"{m['id']}.json"
    if f.exists():
        continue
    h = get("https://clob.polymarket.com/prices-history", {"market": m["token"], "interval": "max", "fidelity": 1440})
    f.write_text(json.dumps((h or {}).get("history", [])))
    time.sleep(0.15)
    if k % 200 == 0:
        print(f"history {k}/{len(markets)}", flush=True)
print("done", flush=True)
