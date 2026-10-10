"""Copy-trading Hyperliquid accounts (edge hunt E2): fetch public data.

    python3 handoff/experiments/edge-hunt/hl_copy/fetch.py pool        # leaderboard -> pool sample (seeded)
    python3 handoff/experiments/edge-hunt/hl_copy/fetch.py portfolios  # account value / pnl history per address
    python3 handoff/experiments/edge-hunt/hl_copy/fetch.py fills ADDR...  # fills since FILLS_FROM per address

Raw responses are cached under CACHE (not in git); the pool list is written to the repo.
"""
import gzip
import json
import random
import sys
import time
from pathlib import Path

import httpx

INFO = "https://api.hyperliquid.xyz/info"
LEADERBOARD = "https://stats-data.hyperliquid.xyz/Mainnet/leaderboard"
CACHE = Path("data/hl-copy")
OUT = Path("handoff/data/edge-hunt/hl-copy")
POOL_N, SEED = 1500, 20261010
VLM_MIN, VLM_MAX = 5e6, 2e9  # all-time volume: active enough to judge, not a market maker
FILLS_FROM = 1780272000000  # 2026-06-01 00:00 UTC
A1_MS = 1787184000000  # 2026-08-20 00:00 UTC, end of period A

c = httpx.Client(timeout=60)


def post(body):
    for i in range(8):
        try:
            r = c.post(INFO, json=body)
        except httpx.TransportError:
            time.sleep(2 * (i + 1))
            continue
        if r.status_code == 200:
            return r.json()
        time.sleep(min(60, 5 * 2 ** i) if r.status_code == 429 else 3)
    r.raise_for_status()


def pool():
    CACHE.mkdir(parents=True, exist_ok=True)
    p = CACHE / "leaderboard.json"
    if not p.exists():
        p.write_bytes(c.get(LEADERBOARD, timeout=180).content)
    rows = json.loads(p.read_text())["leaderboardRows"]
    elig = sorted(r["ethAddress"] for r in rows if VLM_MIN < float(dict(r["windowPerformances"])["allTime"]["vlm"]) < VLM_MAX)
    sample = random.Random(SEED).sample(elig, POOL_N)
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "pool.json").write_text(json.dumps({"leaderboard_rows": len(rows), "eligible": len(elig), "seed": SEED,
                                               "vlm": [VLM_MIN, VLM_MAX], "fetched": p.stat().st_mtime, "pool": sample}, indent=0))
    print(f"{len(rows)} rows, {len(elig)} eligible, sampled {len(sample)}")


def portfolios():
    addrs = json.loads((OUT / "pool.json").read_text())["pool"]
    d = CACHE / "portfolio"
    d.mkdir(parents=True, exist_ok=True)
    for i, a in enumerate(addrs):
        p = d / f"{a}.json.gz"
        if p.exists():
            continue
        p.write_bytes(gzip.compress(json.dumps(post({"type": "portfolio", "user": a})).encode()))
        if i % 100 == 0:
            print(i, flush=True)
        time.sleep(0.9)


def fills(addrs):
    d = CACHE / "fills"
    d.mkdir(parents=True, exist_ok=True)
    for a in addrs:
        p = d / f"{a}.json.gz"
        if p.exists():
            continue
        out, s = [], FILLS_FROM
        while True:
            part = post({"type": "userFillsByTime", "user": a, "startTime": s, "aggregateByTime": True}) or []
            out += part
            if len(part) < 2000:
                break
            if sum(1 for f in out if f["time"] < A1_MS) > 3000:  # unfollowable under the SPEC: no need for the rest
                break
            s = part[-1]["time"] + 1
            time.sleep(6)
        p.write_bytes(gzip.compress(json.dumps(out).encode()))
        print(a, len(out), flush=True)
        time.sleep(3)


if __name__ == "__main__":
    {"pool": lambda: pool(), "portfolios": lambda: portfolios(), "fills": lambda: fills(sys.argv[2:])}[sys.argv[1]]()
