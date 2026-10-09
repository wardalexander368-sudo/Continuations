"""Simple rules on established memecoin pools, net of DEX costs, against a survivorship-neutral baseline.

    python3 handoff/experiments/established_rules.py [--dir data/established] [--fee 0.005] [--size 200]

Data: 5-minute OHLCV in USD from established_collect.py, gaps filled flat (no trades = no move).
A signal uses only bars up to and including bar t; the trade enters at bar t+1's open and exits
at the close of bar t+H. One position per pool at a time.

Costs per round trip: the swap fee on both sides, price impact on both sides (constant product:
about size / (liquidity / 2) per side, from the pool's liquidity at collection time), and a
network fee per transaction.

Rules (fixed grid, chosen before looking at results):
* momentum:  return over the last L bars > m
* dip:       return over the last L bars < -d
* breakout:  close above the highest high of the previous N bars
with L in {3, 12} bars, m and d in {5, 10, 20}%, N in {12, 48, 288} bars, hold H in {3, 12, 48}.

Split by calendar time: the first 60% of the period picks the best configuration per family
(at least 30 trades); the last 40% is reported once. Baseline: today's liquid pools are
survivors, so each trade is compared with entering the same pool at every bar of the same
period with the same hold. "Excess" is the mean of (trade - that baseline). Intervals bootstrap
over pools.
"""
import argparse
import itertools
import json
from pathlib import Path

import numpy as np

parser = argparse.ArgumentParser()
parser.add_argument("--dir", default="data/established")
parser.add_argument("--fee", type=float, default=0.005, help="swap fee per side")
parser.add_argument("--size", type=float, default=200.0, help="USD per trade")
parser.add_argument("--network", type=float, default=0.05, help="USD per transaction")
parser.add_argument("--train", type=float, default=0.6)
args = parser.parse_args()

BAR = 300
pools = []
for path in sorted(Path(args.dir).glob("*.json")):
    p = json.loads(path.read_text())
    rows = p.get("candles") or []
    if len(rows) < 400:
        continue
    t0, t1 = rows[0][0], rows[-1][0]
    grid = np.arange(t0, t1 + BAR, BAR)
    by_t = {r[0]: r for r in rows}
    o, h, lo, c = (np.empty(len(grid)) for _ in range(4))
    prev = rows[0][4]
    for i, t in enumerate(grid):
        r = by_t.get(int(t))
        if r is None:
            o[i] = h[i] = lo[i] = c[i] = prev
        else:
            o[i], h[i], lo[i], c[i] = r[1], r[2], r[3], r[4]
            prev = r[4]
    impact = args.size / max(p["liquidity_usd"] / 2.0, 1.0)
    pools.append({"name": p["name"], "t": grid, "o": o, "h": h, "l": lo, "c": c, "impact": impact})
start = min(p["t"][0] for p in pools)
end = max(p["t"][-1] for p in pools)
cut = start + args.train * (end - start)
print(f"{len(pools)} pools, {sum(len(p['t']) for p in pools)} bars; period {(end - start) / 86400:.1f} days; "
      f"train before {np.datetime64(int(cut), 's')}; median impact per side {100 * np.median([p['impact'] for p in pools]):.2f}%")


def net(entry, exit_, impact):
    gross = exit_ / entry
    return gross * (1 - args.fee) ** 2 * (1 - impact) ** 2 - 1 - 2 * args.network / args.size


def baseline(p, H, lo_t, hi_t):
    """Mean net of entering at every bar of [lo_t, hi_t) with hold H."""
    idx = np.flatnonzero((p["t"][:-H - 1] >= lo_t) & (p["t"][:-H - 1] < hi_t))
    if not len(idx):
        return np.nan
    return float(np.mean(net(p["o"][idx + 1], p["c"][idx + H], p["impact"])))


def signals(p, family, a, b):
    c = p["c"]
    s = np.zeros(len(c), dtype=bool)
    if family == "momentum":
        r = np.full(len(c), np.nan)
        r[a:] = c[a:] / c[:-a] - 1
        s = r > b
    elif family == "dip":
        r = np.full(len(c), np.nan)
        r[a:] = c[a:] / c[:-a] - 1
        s = r < -b
    elif family == "breakout":
        hh = np.full(len(c), np.inf)
        for i in range(a, len(c)):
            hh[i] = p["h"][i - a : i].max()
        s = c > hh
    return s


def trades(p, family, a, b, H, lo_t, hi_t):
    s = signals(p, family, a, b)
    out, busy = [], -1
    for i in np.flatnonzero(s):
        if i <= busy or i + H >= len(p["c"]) or not (lo_t <= p["t"][i] < hi_t):
            continue
        out.append(net(p["o"][i + 1], p["c"][i + H], p["impact"]))
        busy = i + H
    return out


configs = (
    [("momentum", L, m, H) for L, m, H in itertools.product((3, 12), (0.05, 0.10, 0.20), (3, 12, 48))]
    + [("dip", L, d, H) for L, d, H in itertools.product((3, 12), (0.05, 0.10, 0.20), (3, 12, 48))]
    + [("breakout", N, 0, H) for N, H in itertools.product((12, 48, 288), (3, 12, 48))]
)


def evaluate(config, lo_t, hi_t):
    family, a, b, H = config
    per_pool = []
    for p in pools:
        tr = trades(p, family, a, b, H, lo_t, hi_t)
        if tr:
            base = baseline(p, H, lo_t, hi_t)
            per_pool.append((np.array(tr), base))
    if not per_pool:
        return None
    allr = np.concatenate([tr for tr, _ in per_pool])
    excess = np.concatenate([tr - base for tr, base in per_pool])
    return {"n": len(allr), "pools": len(per_pool), "mean": allr.mean(), "excess": excess.mean(), "per_pool": per_pool}


def ci(per_pool, key, rng=np.random.default_rng(0)):
    stats = []
    k = len(per_pool)
    for _ in range(2000):
        pick = [per_pool[i] for i in rng.integers(0, k, k)]
        v = np.concatenate([tr if key == "mean" else tr - base for tr, base in pick])
        stats.append(v.mean())
    return np.quantile(stats, [0.05, 0.95])


print(f"fee {100 * args.fee:.2f}%/side, ${args.size:.0f} per trade, ${args.network} per tx\n")
for family in ("momentum", "dip", "breakout"):
    best = None
    for config in (c for c in configs if c[0] == family):
        r = evaluate(config, start, cut)
        if r and r["n"] >= 30 and (best is None or r["mean"] > best[1]["mean"]):
            best = (config, r)
    if best is None:
        print(f"{family}: no configuration with 30 training trades")
        continue
    config, train = best
    test = evaluate(config, cut, end + 1)
    label = f"{family} {config[1:]}"
    print(f"{label:28s} TRAIN n={train['n']:5d} mean {100 * train['mean']:+6.2f}% excess {100 * train['excess']:+6.2f}%")
    if test:
        lo1, hi1 = ci(test["per_pool"], "mean")
        lo2, hi2 = ci(test["per_pool"], "excess")
        print(f"{'':28s} TEST  n={test['n']:5d} ({test['pools']} pools) mean {100 * test['mean']:+6.2f}% [{100 * lo1:+.2f}, {100 * hi1:+.2f}]"
              f"  excess over random entries {100 * test['excess']:+6.2f}% [{100 * lo2:+.2f}, {100 * hi2:+.2f}]")
for H in (3, 12, 48):
    b = [baseline(p, H, cut, end + 1) for p in pools]
    print(f"random entries, hold {H:2d} bars, test period: mean {100 * np.nanmean(b):+.2f}% per trade (pools averaged)")
