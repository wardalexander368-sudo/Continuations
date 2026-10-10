"""Weekend "CME gap" rules on BTC, ETH, SOL (trading-skills thread, round 3), exploratory.

    python3 handoff/experiments/edge-hunt/perps/weekend_gap.py DIR_OF_BINANCE_1H_ZIPS [--cost-bps 10]

Hourly Binance spot klines (data.binance.vision, monthly zips of BTCUSDT/ETHUSDT/SOLUSDT 1h) stand
in for Hyperliquid perp prices, which track them. The weekend move g = close of Sunday 21:00-22:00
UTC / close of Friday 20:00-21:00 UTC - 1 (CME bitcoin futures stop Friday 21:00 and reopen Sunday
22:00 UTC in summer). If |g| >= X, enter at that Sunday close against the move (FADE, "the gap
fills") or with it (FOLLOW), and hold H hours. Cost per side (default 10 bps, ~Hyperliquid taker
4.5 bps plus slippage), funding ignored (~1 bp a day either way). 12 rules, counted.
Splits by the Sunday: train 2020-01..2023-12, validation 2024, test 2025-01..2026-09; mean return
per trade, 90% CI by bootstrap over weeks (the three coins' trades in one week move together).
The rule is chosen on train; test is read only if validation agrees in sign.
"""
from __future__ import annotations

import csv
import datetime as dt
import io
import sys
import zipfile
from collections import defaultdict
from pathlib import Path

import numpy as np

D = Path(sys.argv[1])
COST = float(sys.argv[sys.argv.index("--cost-bps") + 1]) / 1e4 if "--cost-bps" in sys.argv else 0.0010
SPLITS = {"train": ("2020-01-01", "2023-12-31"), "val": ("2024-01-01", "2024-12-31"), "test": ("2025-01-01", "2026-09-30")}

close = defaultdict(dict)  # symbol -> {hour start (s): close}
for f in sorted(D.glob("*.zip")):
    sym = f.name.split("-")[0]
    with zipfile.ZipFile(f) as z:
        for row in csv.reader(io.TextIOWrapper(z.open(z.namelist()[0]))):
            if not row[0].isdigit():
                continue
            t = int(row[0])
            t = t // 1_000_000 if t > 1e14 else t // 1000  # 2025+ files are in microseconds
            close[sym][t] = float(row[4])
print({s: len(v) for s, v in close.items()})


def trades(X, H, sign):
    out = []
    for sym, c in close.items():
        for t in c:
            d = dt.datetime.fromtimestamp(t, dt.timezone.utc)
            if d.weekday() != 6 or d.hour != 21:
                continue
            t_fri = t - 2 * 86400 - 3600  # Friday 20:00 bar (closes at 21:00)
            t_out = t + H * 3600
            if t_fri not in c or t_out not in c:
                continue
            g = c[t] / c[t_fri] - 1
            if abs(g) < X:
                continue
            side = -np.sign(g) * sign
            r = side * (c[t_out] / c[t] - 1) - 2 * COST
            out.append((d.date().isoformat(), r))
    return out


def stats(tr):
    if len(tr) < 10:
        return np.nan, (np.nan, np.nan), len(tr)
    by = defaultdict(list)
    for w, r in tr:
        by[w].append(r)
    keys = list(by)
    s = np.array([sum(by[k]) for k in keys]); n = np.array([len(by[k]) for k in keys])
    pick = np.random.default_rng(1).integers(0, len(keys), (4000, len(keys)))
    bs = s[pick].sum(axis=1) / n[pick].sum(axis=1)
    return float(np.mean([r for _, r in tr])), tuple(np.percentile(bs, [5, 95])), len(tr)


def split(tr, s):
    a, b = SPLITS[s]
    return [x for x in tr if a <= x[0] <= b]


def fmt(t):
    m, ci, n = t
    return f"{m * 100:+.2f}% [{ci[0] * 100:+.2f},{ci[1] * 100:+.2f}] n{n}" if n >= 10 else f"- n{n}"


res, n_rules = [], 0
for name, sign in (("FADE", 1), ("FOLLOW", -1)):
    for X in (0.01, 0.02, 0.04):
        for H in (24, 72):
            tr = trades(X, H, sign)
            n_rules += 1
            a, b = stats(split(tr, "train")), stats(split(tr, "val"))
            res.append(((name, X, H), tr, a, b))
            print(f"  {name:6s} |gap|>={X:.0%} hold {H:2d}h: train {fmt(a)}  val {fmt(b)}", flush=True)
key, tr, a, b = max(res, key=lambda x: x[2][0])
if a[0] > 0 and b[0] > 0:
    print(f"-> chosen {key}: TEST {fmt(stats(split(tr, 'test')))}")
else:
    print(f"-> chosen {key}: validation disagrees or train <= 0; test not read")
print(f"rules tried: {n_rules}, cost {COST * 1e4:g} bps/side")
