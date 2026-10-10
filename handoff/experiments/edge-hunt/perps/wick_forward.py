"""Forward scorer for the pre-registered wick-bounce rule (`handoff/preregistration/wick-bounce/SPEC.md`).

    python3 handoff/experiments/edge-hunt/perps/wick_forward.py --update     # append new HL 1h candles
    python3 handoff/experiments/edge-hunt/perps/wick_forward.py [--from 2026-10-12 --to 2027-10-11] [--final]

Hyperliquid's candle API keeps only ~5,000 bars, so `--update` (run by the `perps-ctx` Action every
4 hours) appends each coin's closed 1h candles to handoff/data/edge-hunt/hl-1h/<COIN>.csv.
Scoring reproduces `intraday.py`'s WICK BOUNCE Z=6 H=4 exactly, on Hyperliquid's own candles.
"""
from __future__ import annotations

import csv
import datetime as dt
import sys
import time
from collections import defaultdict
from pathlib import Path

import numpy as np

COINS = ["ADA", "APT", "ARB", "AVAX", "BCH", "BNB", "BTC", "DOGE", "DOT", "ETH", "INJ", "LINK", "LTC",
         "NEAR", "OP", "SEI", "SOL", "SUI", "TIA", "XRP"]
DIR = Path("handoff/data/edge-hunt/hl-1h")
Z, HOLD, WIN, COST = 6.0, 4, 168, 0.00085
START, END = "2026-10-12", "2027-10-11"


def arg(name, default):
    return sys.argv[sys.argv.index(name) + 1] if name in sys.argv else default


def update():
    import httpx
    DIR.mkdir(parents=True, exist_ok=True)
    now_h = int(time.time()) // 3600
    for c in COINS:
        f = DIR / f"{c}.csv"
        last = int(f.read_text().strip().splitlines()[-1].split(",")[0]) if f.exists() and f.stat().st_size else (now_h - 4900) * 3600
        rows = []
        for i in range(4):
            try:
                r = httpx.post("https://api.hyperliquid.xyz/info", timeout=30, json={"type": "candleSnapshot", "req": {
                    "coin": c, "interval": "1h", "startTime": (last + 3600) * 1000, "endTime": now_h * 3600 * 1000}})
                r.raise_for_status()
                rows = r.json()
                break
            except Exception:
                time.sleep(3 * (i + 1))
        new = [x for x in rows if x["t"] // 1000 > last and x["T"] // 1000 < now_h * 3600 + 3600 and x["t"] // 1000 < now_h * 3600]
        with f.open("a") as fh:
            for x in new:
                fh.write(f"{x['t'] // 1000},{x['o']},{x['h']},{x['l']},{x['c']}\n")
        time.sleep(1.5)  # a first backfill is ~100 weight per coin; stay under 1200 per minute per IP
    print(f"hl-1h: updated {len(COINS)} coins to hour {now_h}")


def score(a, b):
    trades = []
    for c in COINS:
        f = DIR / f"{c}.csv"
        if not f.exists():
            continue
        rows = {int(r[0]) // 3600: tuple(map(float, r[1:5])) for r in csv.reader(f.open())}
        if not rows:
            continue
        h0, h1 = min(rows), max(rows)
        n = h1 - h0 + 1
        O, Hi, Lo, C = (np.full(n, np.nan) for _ in range(4))
        for h, (o, hi, lo, cl) in rows.items():
            O[h - h0], Hi[h - h0], Lo[h - h0], C[h - h0] = o, hi, lo, cl
        R = np.full(n, np.nan); R[1:] = C[1:] / C[:-1] - 1
        busy = -1
        for i in range(WIN + 1, n - HOLD):
            d = dt.datetime.fromtimestamp((h0 + i) * 3600, dt.timezone.utc).date().isoformat()
            if not (a <= d <= b) or i < busy:
                continue
            w = R[i - WIN: i]
            if np.isnan(w).any() or np.isnan(C[i + HOLD]) or np.isnan(O[i]):
                continue
            sig = np.sqrt(max(np.mean(w * w) - np.mean(w) ** 2, 0))
            if sig == 0:
                continue
            lw = (min(O[i], C[i]) - Lo[i]) / O[i] / sig
            uw = (Hi[i] - max(O[i], C[i])) / O[i] / sig
            s = int(lw >= Z) - int(uw >= Z)
            if s:
                trades.append((d, c, s * (C[i + HOLD] / C[i] - 1) - 2 * COST))
                busy = i + HOLD
    return trades


if __name__ == "__main__":
    if "--update" in sys.argv:
        update(); sys.exit()
    a, b = arg("--from", START), arg("--to", END)
    tr = score(a, b)
    if len(tr) < 2:
        print(f"{a}..{b}: {len(tr)} trades"); sys.exit()
    by = defaultdict(list)
    for d, _, r in tr:
        by[d].append(r)
    keys = list(by)
    s = np.array([sum(by[k]) for k in keys]); n = np.array([len(by[k]) for k in keys])
    pick = np.random.default_rng(1).integers(0, len(keys), (10000, len(keys)))
    lo, hi = np.percentile(s[pick].sum(axis=1) / n[pick].sum(axis=1), [5, 95])
    m = float(np.mean([r for _, _, r in tr]))
    print(f"{a}..{b}: {len(tr)} trades on {len(keys)} days, mean {m * 1e4:+.1f} bp/trade after 8.5 bp/side, 90% CI [{lo * 1e4:+.1f}, {hi * 1e4:+.1f}]")
    if "--final" in sys.argv:
        print("SUCCESS" if m > 0 and lo > 0 else "FAIL")
