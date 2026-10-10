"""Rescore the perps-momentum backtests at Hyperliquid's measured execution costs, by account size.

    python3 handoff/experiments/edge-hunt/perps/rescore_costs.py [--book handoff/data/edge-hunt/hl-book]

Cost model (from hl_book_costs.py snapshots): per side = taker fee (4.5 bps, base tier) + market-order
impact from mid. Impact per order size s is fitted across coins and snapshots as
log(impact_bps) = a_s + b_s * log(24h USD volume), so it can be applied to any coin on any past week
from that coin's 30-day median volume at the time (delisted coins included); sizes between the
measured ones are interpolated in log size. Each week a coin is charged on its own traded notional
(|weight change| x capital per leg), so bigger accounts pay more per dollar.

Rules: the registered xs_momentum (edge hunt D) and vol_momentum, and the search's whole grid
(tartar/autotrade/search.py), with the search's harness, universe, funding and weeks.
"""
import argparse, json, sys, warnings
from datetime import date
from pathlib import Path

import httpx
import numpy as np

sys.path.insert(0, ".")
from tartar.autotrade import hl_data, search  # noqa: E402
from tartar.autotrade.strategies.xs_momentum import rank_signal, MIN_HIST  # noqa: E402

FEE_BPS = 4.5
CAPITAL = (1_000, 10_000, 100_000, 1_000_000)       # USD per leg


def fit(book_dir):
    rows = [json.loads(l) for f in sorted(Path(book_dir).glob("*.jsonl")) for l in f.read_text().splitlines() if l.strip()]
    sizes = sorted({int(k.split("_")[1]) for r in rows for c in r["coins"].values() for k in c if k.startswith("buy_")})
    model = {}
    for s in sizes:
        x, y = [], []
        for r in rows:
            for c in r["coins"].values():
                b, se = c.get(f"buy_{s}"), c.get(f"sell_{s}")
                if b is None or se is None or c["vol24_usd"] <= 0:
                    continue
                x.append(np.log(c["vol24_usd"])); y.append(np.log(max((b + se) / 2, 0.05)))
        A = np.c_[np.ones(len(x)), x]
        coef, *_ = np.linalg.lstsq(A, np.array(y), rcond=None)
        resid = np.array(y) - A @ coef
        model[s] = (coef, float(np.exp(resid.var() / 2)))           # lognormal mean correction
    return len(rows), sizes, model


def impact_bps(model, sizes, notional, vol):
    """Expected per-side impact for `notional` USD on a coin trading `vol` USD a day."""
    lv = np.log(max(vol, 1.0))
    pts = [(np.log(s), np.exp(model[s][0][0] + model[s][0][1] * lv) * model[s][1]) for s in sizes]
    ln = np.log(max(notional, sizes[0]))
    if ln >= pts[-1][0]:                                             # beyond the largest size: grow with sqrt(size)
        return pts[-1][1] * np.sqrt(np.exp(ln - pts[-1][0]))
    for (l0, v0), (l1, v1) in zip(pts, pts[1:]):
        if ln <= l1:
            return v0 + (v1 - v0) * (ln - l0) / (l1 - l0)


def backtest(P, p, model, sizes, capital):
    """search.backtest with each coin charged fee + impact on its own traded notional."""
    L, Q, lag = p["lookback"], p["quant"], p["lag_days"]
    out, prev, n = [], {}, len(P.days)
    for i, d in enumerate(P.days):
        if d.weekday() != p["signal_weekday"] or d < search.FIRST_WEEK or i < max(MIN_HIST, 30, L):
            continue
        e, x = i + lag, i + lag + 7
        if x >= n:
            break
        sig = rank_signal(P.C, i, L, p["scaled"])
        ok = P.base_ok(i) & ~np.isnan(P.C[i - L]) & ~np.isnan(P.C[e]) & np.isfinite(sig)
        ids = np.where(ok)[0]
        if len(ids) < 15:
            continue
        order = ids[np.argsort(sig[ids])]; q = len(order) // Q
        longs, shorts = order[-q:], order[:q]
        ret = P.Cf[x] / P.C[e] - 1
        fund = P.fund_cum[x] - P.fund_cum[e]
        r = np.mean(ret[longs] - fund[longs]) + np.mean(-ret[shorts] + fund[shorts])
        w = {**{int(j): 1 / q for j in longs}, **{int(j): -1 / q for j in shorts}}
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", RuntimeWarning)
            medv = np.nanmedian(P.V[i - 29: i + 1], axis=0)
        cost = 0.0
        for k in set(w) | set(prev):
            dw = abs(w.get(k, 0) - prev.get(k, 0))
            if dw:
                v = medv[k] if np.isfinite(medv[k]) else 2e6
                cost += dw * (FEE_BPS + impact_bps(model, sizes, dw * capital, v)) / 1e4
        prev = w
        out.append((d, float(r - cost)))
    return out


def summary(rs, holdout=26):
    x = np.array([r for _, r in rs])
    return x.mean() * 100, x[-holdout:].mean() * 100, len(x)


def main():
    a = argparse.ArgumentParser(); a.add_argument("--book", default="handoff/data/edge-hunt/hl-book"); a = a.parse_args()
    nsnap, sizes, model = fit(a.book)
    print(f"cost model from {nsnap} book snapshots; per-side impact at $2M / $20M / $200M daily volume:")
    for s in sizes:
        print(f"  ${s:>7,}: " + " / ".join(f"{impact_bps(model, sizes, s, v):5.1f}" for v in (2e6, 2e7, 2e8)) + " bps")
    http = httpx.Client(timeout=60)
    days, coins, C, V, _ = hl_data.load_daily(http, date.today())
    F = {}
    fdir = Path("handoff/data/edge-hunt/hl-funding")
    for c in coins:
        f = fdir / f"{c}.json"
        if f.exists():
            by = {}
            for h, rate in json.loads(f.read_text()).items():
                dd = date.fromordinal(date(1970, 1, 1).toordinal() + int(h) // 24).isoformat()
                by[dd] = by.get(dd, 0.0) + rate
            F[c] = by
    P = search.Panel(days, coins, C, V, F)
    rules = {**search.REGISTERED, **{search.name_of(p): p for p in search.grid()}}
    print("\nweekly long-short return, % ($1 per leg): all weeks / last 26 weeks")
    print(f"{'rule':38s} {'flat 20bps':>14s} " + " ".join(f"{'$' + format(c, ','):>14s}" for c in CAPITAL))
    grid_rows = []
    for name, p in rules.items():
        flat = summary(search.backtest(P, p))
        meas = [summary(backtest(P, p, model, sizes, c)) for c in CAPITAL]
        if name in search.REGISTERED:
            print(f"{name:38s} {flat[0]:+6.2f}/{flat[1]:+6.2f} " + " ".join(f"{m[0]:+6.2f}/{m[1]:+6.2f}" for m in meas))
        grid_rows.append((name, flat, meas))
    print(f"\nsearch grid ({len(grid_rows) - len(search.REGISTERED)} rules + 2 registered): mean over rules of the all-weeks mean")
    print(f"  flat 20 bps {np.mean([g[1][0] for g in grid_rows]):+.2f}; " +
          "; ".join(f"${c:,} {np.mean([g[2][k][0] for g in grid_rows]):+.2f}" for k, c in enumerate(CAPITAL)))
    best = sorted(grid_rows, key=lambda g: -g[1][0])[:5]
    print("  top 5 by flat-cost mean:")
    for name, flat, meas in best:
        print(f"  {name:38s} {flat[0]:+6.2f}/{flat[1]:+6.2f} " + " ".join(f"{m[0]:+6.2f}/{m[1]:+6.2f}" for m in meas))


if __name__ == "__main__":
    main()
