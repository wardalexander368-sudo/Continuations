"""Edge hunt E1, exploratory: does pump.fun's own activity predict Hyperliquid perps?

Signals from day d's DefiLlama totals (pump.fun launchpad + PumpSwap fees, and revenue):
  surprise = log(x_d / mean(x_{d-7..d-1})),  trend = log(mean7(x)_d / mean7(x)_{d-7}).
Target: perp return from day d's close to d+1's close (lag 0: needs the flow live, which our
decoder has) or d+1 -> d+2 (lag 1: DefiLlama's published totals). Long/short sign(signal) or
z-scored and clipped, daily rebalance, cost per side on turnover, funding charged.
Train < 2026-04-01 <= test. Prints IC (Spearman) by coin and the rule table.
"""
import json, sys
from datetime import date, timedelta
from pathlib import Path

import numpy as np

D = Path("handoff/data/edge-hunt/pumpflow")
SPLIT = "2026-04-01"
COST = float(sys.argv[1]) if len(sys.argv) > 1 else 0.001

flow = json.loads((D / "flow.json").read_text())
perps = json.loads((D / "perps.json").read_text())
days = sorted(flow)
days = [d for d in days if d >= "2024-03-01"]


def series(key_fn):
    return np.array([key_fn(flow[d]) for d in days], float)


fees = series(lambda r: (r.get("pump.fun-dailyFees") or 0) + (r.get("pumpswap-dailyFees") or 0))
rev = series(lambda r: (r.get("pump.fun-dailyRevenue") or 0) + (r.get("pumpswap-dailyRevenue") or 0))
lp = series(lambda r: r.get("pump.fun-dailyFees") or 0)


def surprise(x):
    out = np.full(len(x), np.nan)
    for i in range(7, len(x)):
        m = x[i - 7:i].mean()
        if m > 0 and x[i] > 0:
            out[i] = np.log(x[i] / m)
    return out


def trend(x):
    out = np.full(len(x), np.nan)
    for i in range(14, len(x)):
        a, b = x[i - 6:i + 1].mean(), x[i - 13:i - 6].mean()
        if a > 0 and b > 0:
            out[i] = np.log(a / b)
    return out


SIG = {"fees_surprise": surprise(fees), "fees_trend": trend(fees), "rev_surprise": surprise(rev),
       "launchpad_surprise": surprise(lp), "launchpad_trend": trend(lp)}


def returns(coin, lag):
    c, f = perps[coin]["candles"], perps[coin]["funding"]
    r = np.full(len(days), np.nan); fu = np.zeros(len(days))
    for i, d in enumerate(days):
        d0 = (date.fromisoformat(d) + timedelta(days=lag)).isoformat()
        d1 = (date.fromisoformat(d) + timedelta(days=lag + 1)).isoformat()
        if d0 in c and d1 in c:
            r[i] = c[d1]["c"] / c[d0]["c"] - 1
            fu[i] = f.get(d1, 0.0)
    return r, fu


def rank(a):
    return np.argsort(np.argsort(a))


def ic(s, r, mask):
    m = mask & ~np.isnan(s) & ~np.isnan(r)
    if m.sum() < 30:
        return np.nan, m.sum()
    return float(np.corrcoef(rank(s[m]), rank(r[m]))[0, 1]), int(m.sum())


def run(s, r, fu, mask, sign=1):
    m = mask & ~np.isnan(s) & ~np.isnan(r)
    pos = np.sign(s[m]) * sign
    pnl = pos * r[m] - pos * fu[m] - COST * np.abs(np.diff(np.r_[0, pos]))
    return pnl


def boot(p, n=2000, block=10, seed=0):
    rng = np.random.default_rng(seed)
    k = int(np.ceil(len(p) / block)); means = []
    for _ in range(n):
        idx = np.concatenate([np.arange(s, s + block) % len(p) for s in rng.integers(0, len(p), k)])[:len(p)]
        means.append(p[idx].mean())
    return np.percentile(means, [5, 95])


tr = np.array([d < SPLIT for d in days]); te = ~tr
print(f"days {days[0]}..{days[-1]}, cost {COST:.2%}/side")
for lag in (0, 1):
    print(f"\n=== lag {lag}: IC train / test (n) ===")
    print("signal".ljust(20) + "".join(c.rjust(18) for c in perps))
    for name, s in SIG.items():
        row = name.ljust(20)
        for coin in perps:
            r, _ = returns(coin, lag)
            a, na = ic(s, r, tr); b, nb = ic(s, r, te)
            row += f"{a:+.3f}/{b:+.3f}".rjust(18)
        print(row)

print("\n=== PUMP rules (mean daily net, 90% block-bootstrap CI, n) ===")
for lag in (0, 1):
    r, fu = returns("PUMP", lag)
    for name in ("rev_surprise", "fees_surprise", "launchpad_surprise"):
        s = SIG[name]
        for mode in ("long-short", "long-only"):
            out = []
            for mask in (tr, te):
                m = mask & ~np.isnan(s) & ~np.isnan(r)
                pos = np.sign(s[m]) if mode == "long-short" else (s[m] > 0).astype(float)
                p = pos * r[m] - pos * fu[m] - COST * np.abs(np.diff(np.r_[0, pos]))
                lo, hi = boot(p)
                out.append(f"{p.mean():+.3%} [{lo:+.3%},{hi:+.3%}] n={len(p)}")
            print(f"lag{lag} {name:19s} {mode:10s} train {out[0]}   test {out[1]}")
    m = te & ~np.isnan(r)
    print(f"lag{lag} buy-and-hold PUMP test {(r[m] - fu[m]).mean():+.3%}/day")
# contemporaneous: same-day flow vs same-day return (is it priced at once?)
r, _ = returns("PUMP", -1)
print("same-day IC rev_surprise vs PUMP:", ic(SIG["rev_surprise"], r, tr), ic(SIG["rev_surprise"], r, te))

print("\n=== timing vs beta (long-short sign(surprise)): mean pos, net, beta part, timing part ===")
for lag in (0, 1):
    for coin in perps:
        r, fu = returns(coin, lag)
        for name in ("rev_surprise",):
            s = SIG[name]; row = []
            for mask in (tr, te):
                m = mask & ~np.isnan(s) & ~np.isnan(r)
                pos = np.sign(s[m]); rr = r[m] - fu[m]
                net = pos * rr - COST * np.abs(np.diff(np.r_[0, pos]))
                beta = pos.mean() * rr.mean()
                tim = net - beta
                lo, hi = boot(net - pos.mean() * rr)  # timing series (beta removed day by day)
                row.append(f"long {np.mean(pos > 0):.0%} net {net.mean():+.3%} beta {beta:+.3%} timing {net.mean() - beta:+.3%} [{lo:+.3%},{hi:+.3%}]")
            print(f"lag{lag} {coin:9s} train {row[0]} | test {row[1]}")
