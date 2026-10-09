"""Score the rolling dip pre-registration on data after each cohort's registration (no choices left).

    python3 handoff/experiments/established_prereg_eval.py [handoff/preregistration/dip-rolling]

Fetches 5-minute OHLCV (USD) from GeckoTerminal for every registered pool, keeps only bars at or
after its cohort's `registered_at`, and applies SPEC.json's rule, costs and success criteria.
Pools that died or lost liquidity count like any other (their history stays available). Candles
are cached per run hour in data/prereg/.

Secondary (ADDENDUM-2026-10-09-fees.md, declared before any scoring; not a success criterion):
if fees-measured.json exists, mean net is also reported with each pool's PumpSwap fee as
measured on-chain (pumpswap_fees.py --save), since the registered 0.5%/side understates it.
"""
import json
import sys
import time
from datetime import datetime
from pathlib import Path

import httpx
import numpy as np

DIR = Path(sys.argv[1] if len(sys.argv) > 1 else "handoff/preregistration/dip-rolling")
spec = json.loads((DIR / "SPEC.json").read_text())
rule, costs = spec["rule"], spec["costs"]
cohorts = sorted((json.loads(f.read_text()) for f in DIR.glob("cohort-*.json")), key=lambda c: c["registered_at"])
registered = []  # (pool, registered_at timestamp): a token counts from its first cohort only
seen_tokens = set()
for cohort in cohorts:
    t = datetime.fromisoformat(cohort["registered_at"].replace("Z", "+00:00")).timestamp()
    for pool in cohort["pools"]:
        if pool["token"] not in seen_tokens:
            seen_tokens.add(pool["token"])
            registered.append((pool, t))
cache = Path("data/prereg") / DIR.name / time.strftime("%Y%m%d-%H", time.gmtime())  # fresh data each run hour
cache.mkdir(parents=True, exist_ok=True)
BASE = "https://api.geckoterminal.com/api/v2/networks/solana"
client = httpx.Client(timeout=30, headers={"accept": "application/json"})
last = 0.0


def get(path, **params):
    global last
    for attempt in range(12):
        wait = 2.2 - (time.time() - last)
        if wait > 0:
            time.sleep(wait)
        last = time.time()
        r = client.get(BASE + path, params=params)
        if r.status_code == 429:
            time.sleep(min(10 * (attempt + 1), 60))
            continue
        if r.status_code == 404:
            return None
        r.raise_for_status()
        return r.json()
    raise RuntimeError("rate limited")


def candles(pool, t_reg):
    path = cache / f"{pool}.json"
    if path.exists():
        return json.loads(path.read_text())
    rows, before = {}, None
    while True:
        params = {"aggregate": 5, "limit": 1000, "currency": "usd"}
        if before:
            params["before_timestamp"] = before
        data = get(f"/pools/{pool}/ohlcv/minute", **params)
        batch = (data or {}).get("data", {}).get("attributes", {}).get("ohlcv_list") or []
        for t, o, h, l, c, v in batch:
            if t >= t_reg:
                rows[int(t)] = [int(t), float(o), float(h), float(l), float(c), float(v)]
        if not batch or min(r[0] for r in batch) <= t_reg or len(batch) < 1000:
            break
        before = min(r[0] for r in batch)
    out = [rows[t] for t in sorted(rows)]
    path.write_text(json.dumps(out))
    return out


BAR = rule["bar_seconds"]
L, drop, H = rule["lookback_bars"], rule["drop"], rule["hold_bars"]
fee, size, network = costs["fee_per_side"], costs["size_usd"], costs["network_usd_per_tx"]


measured_path = DIR / "fees-measured.json"
measured = json.loads(measured_path.read_text()) if measured_path.exists() else {}


def net(entry, exit_, impact, fee=fee):
    return (exit_ / entry) * (1 - fee) ** 2 * (1 - impact) ** 2 - 1 - 2 * network / size


per_pool, per_pool_measured, empty = [], [], []
t_first = min(t for _, t in registered)
latest = t_first
for p, t_reg in registered:
    rows = candles(p["pool"], t_reg)
    if rows:
        latest = max(latest, rows[-1][0])
    if len(rows) < L + H + 2:
        empty.append(p["name"])
        continue
    grid = np.arange(rows[0][0], rows[-1][0] + BAR, BAR)
    by_t = {r[0]: r for r in rows}
    o, c = np.empty(len(grid)), np.empty(len(grid))
    prev = rows[0][4]
    for i, t in enumerate(grid):
        r = by_t.get(int(t))
        o[i], c[i] = (prev, prev) if r is None else (r[1], r[4])
        prev = c[i]
    impact = size / max(p["liquidity_usd"] / 2.0, 1.0)
    base = float(np.mean(net(o[1 : len(c) - H], c[H:-1], impact)))  # every entry bar i: open i+1, close i+H
    pool_fee = measured.get(p["pool"], {}).get("fee_per_side", fee)
    trades, trades_measured, busy = [], [], -1
    for i in range(L, len(c) - H - 1):
        if i > busy and c[i] / c[i - L] - 1 < -drop:
            trades.append(net(o[i + 1], c[i + H], impact))
            trades_measured.append(net(o[i + 1], c[i + H], impact, pool_fee))
            busy = i + H
    if trades:
        per_pool.append((p["name"], np.array(trades), base))
        per_pool_measured.append(np.array(trades_measured))

days = (latest - t_first) / 86400
print(f"{len(cohorts)} cohort(s), {len(registered)} registered pools; ~{days:.1f} days since the first registration")
if not per_pool:
    print(f"no trades yet; pools without enough data: {len(empty)}")
    raise SystemExit(0)
allr = np.concatenate([tr for _, tr, _ in per_pool]) if per_pool else np.array([])
excess = np.concatenate([tr - b for _, tr, b in per_pool]) if per_pool else np.array([])
rng = np.random.default_rng(0)
boots_e, boots_m = [], []
for _ in range(2000):
    pick = [per_pool[i] for i in rng.integers(0, len(per_pool), len(per_pool))]
    boots_e.append(np.concatenate([tr - b for _, tr, b in pick]).mean())
    boots_m.append(np.concatenate([tr for _, tr, _ in pick]).mean())
lo_e, hi_e = np.quantile(boots_e, [0.05, 0.95])
lo_m, hi_m = np.quantile(boots_m, [0.05, 0.95])
print(f"trades {len(allr)} in {len(per_pool)} pools; pools without enough data: {len(empty)} {empty[:5]}")
print(f"mean net per trade {100 * allr.mean():+.2f}% [{100 * lo_m:+.2f}, {100 * hi_m:+.2f}]")
print(f"PRIMARY excess over random entries {100 * excess.mean():+.2f}% [{100 * lo_e:+.2f}, {100 * hi_e:+.2f}]")
ok = lo_e > 0 and allr.mean() > 0
print("RESULT:", "SUCCESS (both criteria met)" if ok else "NOT CONFIRMED")
if measured:
    allm = np.concatenate(per_pool_measured)
    boots = [np.concatenate([per_pool_measured[i] for i in rng.integers(0, len(per_pool), len(per_pool))]).mean() for _ in range(2000)]
    lo, hi = np.quantile(boots, [0.05, 0.95])
    covered = sum(p["pool"] in measured for p, _ in registered)
    print(f"secondary (addendum 2026-10-09): mean net at measured PumpSwap fees {100 * allm.mean():+.2f}% [{100 * lo:+.2f}, {100 * hi:+.2f}] ({covered}/{len(registered)} pools measured; others at the registered fee)")
