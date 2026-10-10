"""Scorer for the pre-registered volatility-scaled momentum forward test on Hyperliquid perps.

    python3 handoff/experiments/edge-hunt/perps/vmom_forward.py [--final]

Rule and criteria: handoff/preregistration/vol-momentum/SPEC.md (fixed by its commit). A copy of
`xs_momentum_forward.py` (edge hunt D's scorer, not modified) with one change: coins are ranked by
their 14-day return divided by the standard deviation of their last 14 daily returns. It also
prints D's plain 14-day rule on the same weeks and the weekly difference (secondary, informative). Paper only.
Everything is computed from Hyperliquid's public history at scoring time (daily candles of every
perp, delisted ones included, and hourly funding), so the test needs no live data collection.
"""
import argparse, sys, time, warnings
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import httpx
import numpy as np

HL = "https://api.hyperliquid.xyz/info"
START, END = date(2026, 10, 12), date(2027, 10, 11)   # first and last signal Monday (52 weeks)
LOOKBACK, MIN_HIST, MIN_VOL, QUANT = 14, 60, 2e6, 5
COST = 0.002                                          # per side per unit of turnover
BLOCK = 4                                             # weeks per bootstrap block


def post(c, body):
    for i in range(8):
        r = c.post(HL, json=body)
        if r.status_code == 200:
            return r.json()
        time.sleep(3 * (i + 1))
    r.raise_for_status()


def ms(d):
    return int(datetime(d.year, d.month, d.day, tzinfo=timezone.utc).timestamp() * 1000)


def load(c, through):
    coins = [u["name"] for u in post(c, {"type": "meta"})["universe"]]
    t0 = START - timedelta(days=MIN_HIST + 7)
    days = [t0 + timedelta(days=i) for i in range((through - t0).days + 1)]
    ix = {d: i for i, d in enumerate(days)}
    C = np.full((len(days), len(coins)), np.nan); V = np.full_like(C, np.nan)
    for j, coin in enumerate(coins):
        for x in post(c, {"type": "candleSnapshot", "req": {"coin": coin, "interval": "1d", "startTime": ms(t0), "endTime": ms(through + timedelta(days=1))}}) or []:
            d = datetime.fromtimestamp(x["t"] / 1000, timezone.utc).date()
            if d in ix:
                C[ix[d], j] = float(x["c"]); V[ix[d], j] = float(x["v"]) * float(x["c"])
        time.sleep(0.2)
    return days, ix, coins, C, V


def funding(c, coin, d0, d1):
    out, s = {}, ms(d0)
    while s < ms(d1):
        part = post(c, {"type": "fundingHistory", "coin": coin, "startTime": s, "endTime": ms(d1)})
        if not part:
            break
        for x in part:
            out[x["time"] // 3600_000] = float(x["fundingRate"])
        s = part[-1]["time"] + 1
        if len(part) < 500:
            break
    return out


def score(C, i, scaled):
    ret = C[i] / C[i - LOOKBACK] - 1
    if not scaled:
        return ret
    daily = C[i - LOOKBACK + 1: i + 1] / C[i - LOOKBACK: i] - 1
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        return ret / np.nanstd(daily, axis=0)


def weeks(days, ix, coins, C, V, c, scaled=True):
    """Signal at Monday's close, enter at Tuesday's close, exit at the next Tuesday's close."""
    mondays = [d for d in days if d.weekday() == 0 and START <= d <= END and d + timedelta(days=8) <= days[-1]]
    F, prev, out = {}, {}, []
    for m in mondays:
        i = ix[m]; e, x = ix[m + timedelta(days=1)], ix[m + timedelta(days=8)]
        hist = ~np.isnan(C[i - MIN_HIST + 1: i + 1]).any(axis=0)
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", RuntimeWarning)
            medv = np.nanmedian(V[i - 29: i + 1], axis=0)
        sig = score(C, i, scaled)
        ok = hist & (medv >= MIN_VOL) & ~np.isnan(C[i - LOOKBACK]) & ~np.isnan(C[e]) & np.isfinite(sig)
        ids = np.where(ok)[0]
        if len(ids) < 15:
            continue
        order = ids[np.argsort(sig[ids])]
        q = len(order) // QUANT
        longs, shorts = order[-q:], order[:q]

        def leg(sel, sign):
            r = []
            for j in sel:
                path = C[e: x + 1, j]; last = path[~np.isnan(path)][-1]       # delisted: last close
                coin = coins[j]
                if coin not in F:
                    F[coin] = funding(c, coin, START, END + timedelta(days=9))
                h0, h1 = ms(m + timedelta(days=1)) // 3600_000, ms(m + timedelta(days=8)) // 3600_000
                fund = sum(F[coin].get(h, 0.0) for h in range(h0, h1))
                r.append(sign * (last / C[e, j] - 1) - sign * fund)          # longs pay positive funding
            return np.mean(r)
        w = {**{coins[j]: 1 / q for j in longs}, **{coins[j]: -1 / q for j in shorts}}
        turn = sum(abs(w.get(k, 0) - prev.get(k, 0)) for k in set(w) | set(prev)) / 2
        prev = w
        out.append((m, leg(longs, 1) + leg(shorts, -1) - 2 * COST * turn))
    return out


def block_ci(x, n=10_000, seed=1):
    rng = np.random.default_rng(seed); m = len(x)
    means = [x[np.concatenate([np.arange(s, s + BLOCK) % m for s in rng.integers(0, m, m // BLOCK + 1)])[:m]].mean() for _ in range(n)]
    return np.percentile(means, [5, 95])


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--final", action="store_true")
    a = p.parse_args()
    today = datetime.now(timezone.utc).date() - timedelta(days=1)
    c = httpx.Client(timeout=60)
    days, ix, coins, C, V = load(c, min(today, END + timedelta(days=9)))
    rs = weeks(days, ix, coins, C, V, c)
    if len(rs) < 2:
        print(f"{len(rs)} complete weeks since {START}: nothing to score yet")
        return
    x = np.array([r for _, r in rs])
    lo, hi = block_ci(x)
    print(f"{len(x)} weeks {rs[0][0]} .. {rs[-1][0]}: mean {x.mean() * 100:+.2f}% per week net of costs and funding, "
          f"90% CI [{lo * 100:+.2f}, {hi * 100:+.2f}], cumulative {(np.prod(1 + x) - 1) * 100:+.1f}% (long-short, $1 per leg)")
    base = dict(weeks(days, ix, coins, C, V, c, scaled=False))
    d = np.array([r - base[m] for m, r in rs if m in base])
    if len(d) >= 2:
        dlo, dhi = block_ci(d)
        print(f"secondary: minus D's plain 14-day rule on the same weeks {d.mean() * 100:+.2f}% per week [{dlo * 100:+.2f}, {dhi * 100:+.2f}] (informative)")
    if a.final:
        print("RESULT: " + ("SUCCESS" if x.mean() > 0 and lo > 0 else "FAIL") + " (registered: mean > 0 and CI lower bound > 0)")
    else:
        print("interim: not the registered result")


if __name__ == "__main__":
    sys.exit(main())
