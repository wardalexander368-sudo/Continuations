"""New rule families on Hyperliquid perps (perps lane, trading-skills thread), exploratory.

    python3 handoff/experiments/edge-hunt/perps/perp_rules.py [--cost-bps 10] [--funding]

Same data, universe, splits and cost model as edge hunt D (`crosssection/xs_rules.py`): daily
closes of every Hyperliquid perp (56 delisted included), universe = 60 days of history and 30-day
median USD volume >= $2M, train 2023-07..2025-03, validation 2025-04..2025-12, test 2026-01..10,
cost per side per unit of turnover (10 bps default, as D's exploration), funding optional (hourly
history cached by `crosssection/fetch_hl_funding.py`; longs pay, shorts receive). Every rule tried
is printed and counted. `--lag 1` executes a day after the signal (as D's registration). A family's rule is chosen on train by mean weekly return, kept only if
validation agrees in sign; test is reported for the chosen rule only (the others print "-").

Families:
* TS   time-series trend on the majors (BTC, ETH, SOL): each coin long if its L-day return > 0
       else short, equal weight, rebalanced weekly (Monday) or daily.
* XREV short-term cross-sectional reversal, rebalanced daily: long the bottom quintile of the
       last 1/2/3-day return, short the top.
* VMOM volatility-scaled momentum: L-day return / L-day daily-return std, weekly quintiles.
* RMOM residual momentum: L-day sum of residuals of daily returns on BTC (beta over 56 days).
* VLM  volume-confirmed momentum: rank of L-day return + rank of 7-day / 28-day volume ratio.
* HIGH nearness to the 90-day high (close / max close), weekly quintiles.
"""
from __future__ import annotations

import csv
import datetime as dt
import json
import sys
from pathlib import Path

import numpy as np

D = Path("handoff/data/edge-hunt/hl-daily")
FUND = Path("handoff/data/edge-hunt/hl-funding")
SPLITS = {"train": ("2023-07-01", "2025-03-31"), "val": ("2025-04-01", "2025-12-31"), "test": ("2026-01-01", "2026-12-31")}
COST = float(sys.argv[sys.argv.index("--cost-bps") + 1]) / 1e4 if "--cost-bps" in sys.argv else 0.0010
USE_FUNDING = "--funding" in sys.argv
LAG = int(sys.argv[sys.argv.index("--lag") + 1]) if "--lag" in sys.argv else 0  # days from signal to execution

closes, vols = {}, {}
for f in D.glob("*.csv"):
    rows = list(csv.DictReader(f.open()))
    if len(rows) < 60:
        continue
    closes[f.stem] = {r["day"]: float(r["close"]) for r in rows}
    vols[f.stem] = {r["day"]: float(r["volume"]) * float(r["close"]) for r in rows}
days = sorted(set().union(*closes.values()))
coins = sorted(closes)
idx = {d: i for i, d in enumerate(days)}
C = np.full((len(days), len(coins)), np.nan)
V = np.full_like(C, np.nan)
for j, c in enumerate(coins):
    for d, v in closes[c].items():
        C[idx[d], j] = v
    for d, v in vols[c].items():
        V[idx[d], j] = v
R = C[1:] / C[:-1] - 1  # R[i-1] = return from day i-1 to day i
R = np.vstack([np.full((1, len(coins)), np.nan), R])
BTC = coins.index("BTC")
weekday = np.array([dt.date.fromisoformat(d).weekday() for d in days])

FD = {}
if USE_FUNDING:
    for j, c in enumerate(coins):
        f = FUND / f"{c}.json"
        if f.exists():
            FD[c] = {int(k): v for k, v in json.loads(f.read_text()).items()}
DAY0_HOUR = int(dt.datetime.fromisoformat(days[0]).replace(tzinfo=dt.timezone.utc).timestamp()) // 3600


def funding_cost(w: dict, i0: int, i1: int) -> float:
    """Funding paid by weights `w` (coin index -> signed weight) held from day i0's close to i1's."""
    if not USE_FUNDING:
        return 0.0
    h0, h1 = DAY0_HOUR + 24 * i0 + 24, DAY0_HOUR + 24 * i1 + 24  # closes are end of day UTC
    tot = 0.0
    for j, wt in w.items():
        fd = FD.get(coins[j])
        if fd:
            tot += wt * sum(fd.get(h, 0.0) for h in range(h0, h1))
    return tot


def universe(i: int) -> np.ndarray:
    hist = ~np.isnan(C[i - 59: i + 1]).any(axis=0)
    medv = np.nanmedian(V[i - 29: i + 1], axis=0)
    return hist & (medv >= 2e6)


def backtest(weights_fn, rebal_days, hold_to_next=True):
    """Generic: on each rebalance day i, weights_fn(i) -> {coin index: weight} (sum |w| = 2 for a
    long-short book, $1 per leg). Return over to the next rebalance day, minus costs and funding."""
    out, prev = [], {}
    for k, i in enumerate(rebal_days[:-1]):
        j = rebal_days[k + 1]
        w = weights_fn(i)
        if w is None or j + LAG >= len(days):
            out.append((days[i], np.nan)); prev = {}; continue
        ret = 0.0
        a, b = i + LAG, j + LAG
        for c, wt in w.items():
            path = C[a: b + 1, c]
            path = path[~np.isnan(path)]
            if len(path) == 0:
                continue  # delisted before the lagged entry: no position
            ret += wt * (path[-1] / path[0] - 1)
        turn = sum(abs(w.get(c, 0) - prev.get(c, 0)) for c in set(w) | set(prev)) / 2
        prev = w
        out.append((days[i], ret - 2 * COST * turn - funding_cost(w, a, b)))
    return out


def quintile_weights(sig: np.ndarray, ok: np.ndarray, sign: int = 1):
    ok = ok & ~np.isnan(sig)
    if ok.sum() < 15:
        return None
    ids = np.where(ok)[0]
    order = ids[np.argsort(sig[ids])]
    q = len(order) // 5
    lo, hi = order[:q], order[-q:]
    longs, shorts = (hi, lo) if sign > 0 else (lo, hi)
    return {**{int(c): 1 / len(longs) for c in longs}, **{int(c): -1 / len(shorts) for c in shorts}}


MONDAYS = [i for i in range(len(days)) if weekday[i] == 0 and i >= 120]
DAILY = [i for i in range(120, len(days))]


def stats(rs):
    x = np.array([r for r in rs if not np.isnan(r)])
    if len(x) < 5:
        return np.nan, (np.nan, np.nan), 0
    rng = np.random.default_rng(1)
    B = 4
    bs = [x[np.concatenate([np.arange(s, s + B) % len(x) for s in rng.integers(0, len(x), len(x) // B + 1)])[: len(x)]].mean() for _ in range(4000)]
    return x.mean(), tuple(np.percentile(bs, [5, 95])), len(x)


def per_week(rs, daily: bool):
    """Daily-rebalanced results are summed into Monday-to-Monday weeks so every family reads in %/week."""
    if not daily:
        return rs
    weeks = {}
    for d, r in rs:
        if np.isnan(r):
            continue
        day = dt.date.fromisoformat(d)
        monday = (day - dt.timedelta(days=day.weekday())).isoformat()
        weeks[monday] = weeks.get(monday, 0.0) + r
    return sorted(weeks.items())


def split(rs, name):
    a0, a1 = SPLITS[name]
    return [r for d, r in rs if a0 <= d <= a1]


# ---------------------------------------------------------------- families

def ts_trend(L, daily):
    majors = [coins.index(c) for c in ("BTC", "ETH", "SOL")]

    def w(i):
        out = {}
        for c in majors:
            if np.isnan(C[i, c]) or np.isnan(C[i - L, c]):
                continue
            out[c] = (1.0 if C[i, c] > C[i - L, c] else -1.0) / len(majors)
        return out or None
    return backtest(w, DAILY if daily else MONDAYS)


def xs_reversal(L):
    return backtest(lambda i: quintile_weights(C[i] / C[i - L] - 1, universe(i), sign=-1), DAILY)


def vol_mom(L):
    def w(i):
        sig = (C[i] / C[i - L] - 1) / np.nanstd(R[i - L + 1: i + 1], axis=0)
        return quintile_weights(sig, universe(i))
    return backtest(w, MONDAYS)


def resid_mom(L):
    def w(i):
        x = R[i - 55: i + 1, BTC]
        Y = R[i - 55: i + 1]
        ok = ~np.isnan(Y).any(axis=0) & ~np.isnan(x).any()
        xm = x - x.mean()
        beta = np.where(ok, (xm[:, None] * (Y - np.nanmean(Y, axis=0))).sum(axis=0) / (xm ** 2).sum(), np.nan)
        res = R[i - L + 1: i + 1] - beta[None, :] * R[i - L + 1: i + 1, BTC][:, None]
        return quintile_weights(res.sum(axis=0), universe(i) & ok)
    return backtest(w, MONDAYS)


def volume_mom(L):
    def w(i):
        ret = C[i] / C[i - L] - 1
        vr = np.nanmean(V[i - 6: i + 1], axis=0) / np.nanmean(V[i - 27: i + 1], axis=0)
        ok = universe(i) & ~np.isnan(ret) & ~np.isnan(vr)
        rk = lambda a: np.argsort(np.argsort(np.where(ok, a, np.inf))).astype(float)
        sig = np.where(ok, rk(ret) + rk(vr), np.nan)
        return quintile_weights(sig, ok)
    return backtest(w, MONDAYS)


def near_high(L):
    return backtest(lambda i: quintile_weights(C[i] / np.nanmax(C[i - L + 1: i + 1], axis=0), universe(i)), MONDAYS)


FAMILIES = {
    "TS weekly": [(f"L={L}", lambda L=L: ts_trend(L, False), False) for L in (7, 14, 28, 56, 112)],
    "TS daily": [(f"L={L}", lambda L=L: ts_trend(L, True), True) for L in (7, 14, 28, 56, 112)],
    "XREV daily": [(f"L={L}", lambda L=L: xs_reversal(L), True) for L in (1, 2, 3)],
    "VMOM": [(f"L={L}", lambda L=L: vol_mom(L), False) for L in (7, 14, 28)],
    "RMOM": [(f"L={L}", lambda L=L: resid_mom(L), False) for L in (7, 14, 28)],
    "VLM": [(f"L={L}", lambda L=L: volume_mom(L), False) for L in (7, 14, 28)],
    "HIGH": [(f"L={L}", lambda L=L: near_high(L), False) for L in (30, 90)],
}

if __name__ == "__main__":
    only = sys.argv[sys.argv.index("--family") + 1] if "--family" in sys.argv else None
    n_rules = 0
    print(f"cost {COST * 1e4:g} bps/side, funding {'on' if USE_FUNDING else 'off'}")
    for fam, rules in FAMILIES.items():
        if only and fam != only:
            continue
        res = []
        for name, fn, daily in rules:
            rs = per_week(fn(), daily)
            n_rules += 1
            tr, va = stats(split(rs, "train")), stats(split(rs, "val"))
            res.append((name, rs, tr, va))
            print(f"  {fam:10s} {name:6s} train {tr[0] * 100:+.2f}%/wk [{tr[1][0] * 100:+.2f},{tr[1][1] * 100:+.2f}] n{tr[2]}  val {va[0] * 100:+.2f}% [{va[1][0] * 100:+.2f},{va[1][1] * 100:+.2f}]", flush=True)
        name, rs, tr, va = max(res, key=lambda x: x[2][0])
        if va[0] > 0 and tr[0] > 0:
            te = stats(split(rs, "test"))
            print(f"  -> {fam} chosen {name}: TEST {te[0] * 100:+.2f}%/wk [{te[1][0] * 100:+.2f},{te[1][1] * 100:+.2f}] n{te[2]}", flush=True)
        else:
            print(f"  -> {fam} chosen {name}: validation disagrees or train <= 0; test not read", flush=True)
    print(f"rules tried: {n_rules}")
