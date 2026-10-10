"""E1 audit: does the pumpflow edge survive DefiLlama's real publish delay?

DefiLlama publishes day d's pump.fun + PumpSwap revenue only some 25+ hours after d ends (measured
2026-10-10, see edge-hunt.md §E1 "Publish delay"). This re-scores the rule with the entry at
L hours after the end of day d, for L from 0 (the SPEC backtest's daily-close entry) to 72,
holding 24 h, 0.10%/side on turnover, funding pro-rated from Hyperliquid's daily sums.

Two views, both from cached data (handoff/data/edge-hunt/pumpflow/):
* daily closes, full history (PUMP perp from 2025-07-10): L = 0, 24, 48, split train < 2026-04-01 <= test;
* hourly opens (last ~208 days, mostly test): L = 0..72 h.

    python3 handoff/experiments/edge-hunt/pumpflow/publish_lag.py
"""
import json
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import numpy as np

D = Path("handoff/data/edge-hunt/pumpflow")
COST, SPLIT, BLOCK = 1e-3, "2026-04-01", 10
flow = json.loads((D / "flow.json").read_text())
pump = json.loads((D / "perps.json").read_text())["PUMP"]
candles, fund = pump["candles"], pump["funding"]
H = {int(k): v for k, v in json.loads((D / "pump-1h.json").read_text()).items()}
days = sorted(flow)
rev = np.array([(flow[d].get("pump.fun-dailyRevenue") or 0) + (flow[d].get("pumpswap-dailyRevenue") or 0) for d in days])
sig = {days[i]: float(np.log(rev[i] / rev[i - 7:i].mean())) for i in range(7, len(days)) if rev[i] > 0 and rev[i - 7:i].mean() > 0}


def block_ci(x, n=4000, seed=0):
    rng, k = np.random.default_rng(seed), int(np.ceil(len(x) / BLOCK))
    m = [x[np.concatenate([np.arange(s, s + BLOCK) % len(x) for s in rng.integers(0, len(x), k)])[:len(x)]].mean() for _ in range(n)]
    return np.percentile(m, [5, 95])


def score(pos, ret):
    pos, ret = np.array(pos), np.array(ret)
    net = pos * ret - COST * np.abs(np.diff(np.r_[0, pos]))
    tim = net - pos.mean() * ret
    return len(pos), net.mean(), tim.mean(), block_ci(tim)


def fund_between(t0, t1):
    """Funding over [t0, t1) in unix s, pro-rated from daily sums."""
    out, t = 0.0, t0
    while t < t1:
        day = datetime.fromtimestamp(t, timezone.utc).date()
        nxt = datetime.combine(day + timedelta(days=1), datetime.min.time(), timezone.utc).timestamp()
        out += fund.get(day.isoformat(), 0.0) * (min(nxt, t1) - t) / 86400
        t = min(nxt, t1)
    return out


def fmt(label, r):
    n, net, tim, (lo, hi) = r
    return f"{label:<34} n={n:3d}  net {100 * net:+.2f}%/day  timing {100 * tim:+.2f}% [{100 * lo:+.2f}, {100 * hi:+.2f}] (90%, blocks of {BLOCK})"


print("Daily closes: enter at the close of day d + k (k=0: SPEC backtest), hold one day")
for k in (0, 1, 2):
    for part, keep in (("train", lambda d: d < SPLIT), ("test", lambda d: d >= SPLIT)):
        pos, ret = [], []
        for d, s in sorted(sig.items()):
            a, b = (date.fromisoformat(d) + timedelta(days=k)).isoformat(), (date.fromisoformat(d) + timedelta(days=k + 1)).isoformat()
            if keep(d) and a in candles and b in candles:
                pos.append(np.sign(s))
                ret.append(candles[b]["c"] / candles[a]["c"] - 1 - fund.get(b, 0.0))
        print(fmt(f"  k={k} ({24 * k:2d} h after day end) {part}", score(pos, ret)))

print("\nHourly opens: enter L hours after day d ends, hold 24 h")
rows = {}
for L in list(range(0, 25, 4)) + [25, 26, 28, 30, 32, 36, 40, 44, 48, 60, 72]:
    pos, ret = [], []
    for d, s in sorted(sig.items()):
        t0 = int(datetime.fromisoformat(d).replace(tzinfo=timezone.utc).timestamp() // 3600) + 24 + L
        if t0 in H and t0 + 24 in H:
            pos.append(np.sign(s))
            ret.append(H[t0 + 24] / H[t0] - 1 - fund_between(t0 * 3600, (t0 + 24) * 3600))
    rows[L] = score(pos, ret)
    print(fmt(f"  L={L:2d} h", rows[L]))
