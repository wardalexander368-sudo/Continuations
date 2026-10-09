"""Following past-winner Hyperliquid vaults: does it beat cash after the leader's cut? (exploratory)

    python3 handoff/experiments/edge-hunt/vaults/vault_follow.py CACHE_DIR   # from fetch_vaults.py

Each vault's allTime account value and PnL history (irregular points, every few days) gives a
return per interval = PnL change / account value at the interval's start (deposits and
withdrawals are not PnL, so this is the time-weighted return a depositor earned), compounded into
calendar months. A follower pays the leader its commission (10% for almost every vault) on gains:
monthly net = r - commission * max(r, 0) (no high-water mark: slightly conservative).

Rule (at each month start): among open vaults with account value >= $50k and >= L months of
history, rank by trailing L-month net return (or its ratio to the monthly std, "sharpe"), put
equal money in the top N, hold a month. A vault that closes during the month earns its return
up to its last point, then cash. Benchmarks: cash (0%) and HLP (the protocol vault) alone.
Months by start date: train 2023-08..2024-12, validation 2025-01..06, test 2025-07..2026-09.
A rule is chosen on train by mean monthly net, test read only if validation agrees in sign.
"""
from __future__ import annotations

import datetime as dt
import json
import sys
from pathlib import Path

import numpy as np

cache = Path(sys.argv[1])
SPLITS = {"train": ("2023-08", "2024-12"), "val": ("2025-01", "2025-06"), "test": ("2025-07", "2026-09")}
MIN_AV = 5e4
HLP = "0xdfc24b077bc1425ad1dea75bcb6f8158e10df303"


def month_of(ms):
    return dt.datetime.fromtimestamp(ms / 1000, dt.timezone.utc).strftime("%Y-%m")


months = []
m = dt.date(2023, 5, 1)
while m <= dt.date(2026, 10, 1):
    months.append(m.strftime("%Y-%m"))
    m = (m.replace(day=28) + dt.timedelta(days=4)).replace(day=1)
mi = {x: i for i, x in enumerate(months)}

R = {}  # address -> monthly net return array (nan where not alive)
AV = {}  # address -> account value at each month start
for f in cache.glob("0x*.json"):
    d = json.loads(f.read_text())
    p = d["portfolio"].get("allTime")
    if not p:
        continue
    av = [(t, float(v)) for t, v in p["accountValueHistory"]]
    pnl = dict((t, float(v)) for t, v in p["pnlHistory"])
    comm = d.get("leaderCommission") or 0.0
    r = np.full(len(months), np.nan)
    a = np.full(len(months), np.nan)
    gross = {}
    for (t0, v0), (t1, v1) in zip(av, av[1:]):
        if v0 < 1000 or t0 not in pnl or t1 not in pnl:
            continue
        k = mi.get(month_of(t1))
        if k is None:
            continue
        x = (pnl[t1] - pnl[t0]) / v0
        gross[k] = (1 + gross.get(k, 0.0)) * (1 + max(x, -1.0)) - 1
    for k, x in gross.items():
        r[k] = x - comm * max(x, 0.0)
    for k, mo in enumerate(months):
        start = int(dt.datetime.fromisoformat(mo + "-01").replace(tzinfo=dt.timezone.utc).timestamp() * 1000)
        before = [v for t, v in av if t <= start]
        if before and av[-1][0] > start:
            a[k] = before[-1]
    R[d["vaultAddress"]] = r
    AV[d["vaultAddress"]] = a
addrs = sorted(R)
Rm = np.array([R[x] for x in addrs])
Am = np.array([AV[x] for x in addrs])
print(f"{len(addrs)} vaults with history")


def run(L, N, kind):
    out = []
    for k in range(L, len(months) - 1):
        hist = Rm[:, k - L: k]
        ok = (Am[:, k] >= MIN_AV) & ~np.isnan(hist).any(axis=1)
        if ok.sum() < N:
            out.append((months[k], np.nan, 0)); continue
        cum = np.prod(1 + np.nan_to_num(hist), axis=1) - 1
        sig = cum if kind == "ret" else np.nanmean(hist, axis=1) / (np.nanstd(hist, axis=1) + 1e-3)
        ids = np.where(ok)[0]
        top = ids[np.argsort(sig[ids])[-N:]]
        out.append((months[k], float(np.mean(np.nan_to_num(Rm[top, k]))), int(ok.sum())))
    return out


def stats(xs):
    x = np.array([v for v in xs if not np.isnan(v)])
    if len(x) < 3:
        return np.nan, (np.nan, np.nan), len(x)
    rng = np.random.default_rng(1)
    bs = [x[rng.integers(0, len(x), len(x))].mean() for _ in range(4000)]
    return x.mean(), tuple(np.percentile(bs, [5, 95])), len(x)


def split(rs, s):
    a0, a1 = SPLITS[s]
    return [v for mo, v, _ in rs if a0 <= mo <= a1]


def fmt(t):
    m, ci, n = t
    return f"{m * 100:+.2f}%/mo [{ci[0] * 100:+.2f},{ci[1] * 100:+.2f}] n{n}" if n >= 3 else "-"


hlp = [(mo, R[HLP][k], 0) for k, mo in enumerate(months)] if HLP in R else []
print("HLP alone: " + "  ".join(f"{s} {fmt(stats(split(hlp, s)))}" for s in SPLITS))
allv = []
for k in range(1, len(months) - 1):
    ok = (Am[:, k] >= MIN_AV)
    allv.append((months[k], float(np.mean(np.nan_to_num(Rm[ok, k]))) if ok.sum() else np.nan, int(ok.sum())))
print("every vault >= $50k, equal weight: " + "  ".join(f"{s} {fmt(stats(split(allv, s)))}" for s in SPLITS))
res, n_rules = [], 0
for kind in ("ret", "sharpe"):
    for L in (1, 3, 6):
        for N in (5, 10, 20):
            rs = run(L, N, kind)
            n_rules += 1
            tr, va = stats(split(rs, "train")), stats(split(rs, "val"))
            res.append(((kind, L, N), rs, tr, va))
            print(f"  {kind:6s} L={L} N={N:2d}: train {fmt(tr)}  val {fmt(va)}", flush=True)
(kind, L, N), rs, tr, va = max(res, key=lambda x: x[2][0] if not np.isnan(x[2][0]) else -9)
if tr[0] > 0 and va[0] > 0:
    print(f"-> chosen {kind} L={L} N={N}: TEST {fmt(stats(split(rs, 'test')))}")
else:
    print(f"-> chosen {kind} L={L} N={N}: validation disagrees or train <= 0; test not read")
print(f"rules tried: {n_rules}")
