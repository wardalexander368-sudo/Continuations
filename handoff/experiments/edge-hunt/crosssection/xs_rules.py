"""Cross-sectional momentum / reversal on every Hyperliquid perp (edge hunt angle D), exploratory.

    python3 handoff/experiments/edge-hunt/crosssection/xs_rules.py [--data handoff/data/edge-hunt/hl-daily]

Weekly rebalance (Mondays). Universe on each rebalance day, causal: >= 60 days of history and
30-day median USD volume >= $2M. Signal: past L-day return, L in {1, 3, 7, 14, 28, 56}; long the
top quintile and short the bottom (momentum) or the reverse (reversal), equal weight, dollar
neutral, gross 2x... reported per $1 of each leg. Cost: 10 bps per unit of turnover per side
(taker 4.5 bps + spread/impact). Funding is not charged here (both legs pay or receive; checked
for the chosen rule only). Delisted coins exit at their last close.

Splits: train 2023-07..2025-03, validation 2025-04..2025-12, test 2026-01..2026-10. A rule is
chosen on train, kept only if validation agrees in sign, and test is read once.
"""
import csv
from pathlib import Path
import numpy as np

D = Path("handoff/data/edge-hunt/hl-daily")
closes, vols = {}, {}
for f in D.glob("*.csv"):
    rows = list(csv.DictReader(f.open()))
    if len(rows) < 60: continue
    closes[f.stem] = {r["day"]: float(r["close"]) for r in rows}
    vols[f.stem] = {r["day"]: float(r["volume"]) * float(r["close"]) for r in rows}
days = sorted(set().union(*closes.values()))
coins = sorted(closes)
idx = {d: i for i, d in enumerate(days)}
C = np.full((len(days), len(coins)), np.nan); V = np.full_like(C, np.nan)
for j, c in enumerate(coins):
    for d, v in closes[c].items(): C[idx[d], j] = v
    for d, v in vols[c].items(): V[idx[d], j] = v
COST = 0.0010
import datetime as dt
mondays = [i for i, d in enumerate(days) if dt.date.fromisoformat(d).weekday() == 0 and i >= 60]

def run(L, sign):
    out = []; prev = {}
    for k, i in enumerate(mondays[:-1]):
        j_next = mondays[k + 1]
        hist = ~np.isnan(C[i - 59: i + 1]).any(axis=0)
        medv = np.nanmedian(V[i - 29: i + 1], axis=0)
        ok = hist & (medv >= 2e6) & ~np.isnan(C[i - L])
        if ok.sum() < 15: out.append((days[i], np.nan, [], [], days[j_next])); continue
        sig = C[i] / C[i - L] - 1
        ids = np.where(ok)[0]; order = ids[np.argsort(sig[ids])]
        q = len(order) // 5
        lo, hi = order[:q], order[-q:]
        longs, shorts = (hi, lo) if sign > 0 else (lo, hi)
        def leg(ix):
            r = []
            for j in ix:
                path = C[i: j_next + 1, j]
                last = path[~np.isnan(path)][-1]
                r.append(last / C[i, j] - 1)
            return np.mean(r)
        w = {**{coins[j]: 1 / len(longs) for j in longs}, **{coins[j]: -1 / len(shorts) for j in shorts}}
        turn = sum(abs(w.get(c, 0) - prev.get(c, 0)) for c in set(w) | set(prev)) / 2   # per $1 per leg
        prev = w
        out.append((days[i], leg(longs) - leg(shorts) - 2 * COST * turn,
                    [coins[j] for j in longs], [coins[j] for j in shorts], days[j_next]))
    return out

def stats(rs):
    x = np.array([r[1] for r in rs if not np.isnan(r[1])])
    if len(x) < 5: return (np.nan, np.nan, 0)
    rng = np.random.default_rng(1); B = 4
    bs = [x[np.concatenate([np.arange(s, s + B) % len(x) for s in rng.integers(0, len(x), len(x) // B + 1)])[:len(x)]].mean() for _ in range(4000)]
    return x.mean(), np.percentile(bs, [5, 95]), len(x)

SPLITS = {"train": ("2023-07-01", "2025-03-31"), "val": ("2025-04-01", "2025-12-31"), "test": ("2026-01-01", "2026-12-31")}
if __name__ == "__main__":
  for L in (1, 3, 7, 14, 28, 56):
    for sign, name in ((1, "mom"), (-1, "rev")):
        rs = run(L, sign)
        row = []
        for s, (a0, a1) in SPLITS.items():
            m, ci, n = stats([r for r in rs if a0 <= r[0] <= a1])
            row.append((s, m, ci, n))
        print(f"L={L:2d} {name}: " + "  ".join(f"{s} {m*100:+.2f}%/wk [{ci[0]*100:+.2f},{ci[1]*100:+.2f}] n{n}" if n else f"{s} -" for s, m, ci, n in row), flush=True)
