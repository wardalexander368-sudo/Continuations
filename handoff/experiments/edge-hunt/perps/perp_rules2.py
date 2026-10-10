"""More untested rule families on Hyperliquid perps (trading-skills thread, round 3), exploratory.

    python3 handoff/experiments/edge-hunt/perps/perp_rules2.py [--cost-bps 10] [--lag 1] [--funding --funding-dir DIR]

Same data, universe, splits, cost model and bootstrap as `perp_rules.py` (imported). Every rule
tried is printed and counted; a family's rule is chosen on train by mean weekly return, kept only
if validation agrees in sign, and only then is test read.

Families:
* DOW   calendar: long (or short) the equal-weight majors (BTC, ETH, SOL) for one UTC day of the
        week (close to close), flat otherwise; 7 days x 2 signs. Plus WKND: Friday close to Sunday
        close, long or short. Pays 2 x cost a week on $1.
* MAX   lottery: weekly quintiles by the largest daily return of the last L days; long the lowest.
* IVOL  idiosyncratic volatility: std of residuals on BTC (beta over L days); long the lowest.
* BETA  betting against beta, dollar neutral: long the lowest-beta quintile, short the highest.
* SKEW  skewness of the last L daily returns; long the lowest.
"""
from __future__ import annotations

import sys

import numpy as np

sys.path.insert(0, __file__.rsplit("/", 1)[0])
import perp_rules as P  # noqa: E402

MAJ = [P.coins.index(c) for c in ("BTC", "ETH", "SOL")]


def dow(day: int, sign: int):
    """Hold the majors through UTC weekday `day` (0 = Monday): entered at the previous close."""
    out = []
    for i in range(120, len(P.days)):
        if P.weekday[i] != day:
            continue
        r = P.R[i, MAJ]
        ok = ~np.isnan(r)
        if not ok.any():
            continue
        w = {int(c): sign / ok.sum() for c, k in zip(MAJ, ok) if k}
        out.append((P.days[i], sign * float(np.mean(r[ok])) - 2 * P.COST - P.funding_cost(w, i - 1, i)))
    return out


def weekend(sign: int):
    out = []
    for i in range(120, len(P.days)):
        if P.weekday[i] != 6 or P.weekday[i - 2] != 4:
            continue
        r = P.C[i, MAJ] / P.C[i - 2, MAJ] - 1
        ok = ~np.isnan(r)
        w = {int(c): sign / ok.sum() for c, k in zip(MAJ, ok) if k}
        out.append((P.days[i - 2], sign * float(np.mean(r[ok])) - 2 * P.COST - P.funding_cost(w, i - 2, i)))
    return out


def betas(i: int, L: int):
    x = P.R[i - L + 1: i + 1, P.BTC]
    Y = P.R[i - L + 1: i + 1]
    ok = ~np.isnan(Y).any(axis=0) & ~np.isnan(x).any()
    xm = x - x.mean()
    b = np.where(ok, (xm[:, None] * (Y - np.nanmean(Y, axis=0))).sum(axis=0) / (xm ** 2).sum(), np.nan)
    return b, Y, x, ok


def max_ret(L):
    return P.backtest(lambda i: P.quintile_weights(np.nanmax(P.R[i - L + 1: i + 1], axis=0), P.universe(i), sign=-1), P.MONDAYS)


def ivol(L):
    def w(i):
        b, Y, x, ok = betas(i, L)
        res = Y - b[None, :] * x[:, None]
        return P.quintile_weights(np.nanstd(res, axis=0), P.universe(i) & ok, sign=-1)
    return P.backtest(w, P.MONDAYS)


def bab(L):
    def w(i):
        b, _, _, ok = betas(i, L)
        return P.quintile_weights(b, P.universe(i) & ok, sign=-1)
    return P.backtest(w, P.MONDAYS)


def skew(L):
    def w(i):
        X = P.R[i - L + 1: i + 1]
        m, s = np.nanmean(X, axis=0), np.nanstd(X, axis=0)
        sk = np.nanmean((X - m) ** 3, axis=0) / np.where(s > 0, s ** 3, np.nan)
        return P.quintile_weights(sk, P.universe(i) & ~np.isnan(X).any(axis=0), sign=-1)
    return P.backtest(w, P.MONDAYS)


NAMES = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
FAMILIES = {
    "DOW": [(f"{'long' if s > 0 else 'short'} {NAMES[d]}", lambda d=d, s=s: dow(d, s), False) for d in range(7) for s in (1, -1)]
    + [(f"{'long' if s > 0 else 'short'} wknd", lambda s=s: weekend(s), False) for s in (1, -1)],
    "MAX": [(f"L={L}", lambda L=L: max_ret(L), False) for L in (7, 28)],
    "IVOL": [(f"L={L}", lambda L=L: ivol(L), False) for L in (28, 56)],
    "BETA": [(f"L={L}", lambda L=L: bab(L), False) for L in (28, 56)],
    "SKEW": [(f"L={L}", lambda L=L: skew(L), False) for L in (28, 56)],
}

if __name__ == "__main__":
    only = sys.argv[sys.argv.index("--family") + 1] if "--family" in sys.argv else None
    n_rules = 0
    print(f"cost {P.COST * 1e4:g} bps/side, lag {P.LAG}, funding {'on' if P.USE_FUNDING else 'off'}")
    for fam, rules in FAMILIES.items():
        if only and fam != only:
            continue
        res = []
        for name, fn, daily in rules:
            rs = fn()
            n_rules += 1
            tr, va = P.stats(P.split(rs, "train")), P.stats(P.split(rs, "val"))
            res.append((name, rs, tr, va))
            print(f"  {fam:5s} {name:10s} train {tr[0] * 100:+.2f}%/wk [{tr[1][0] * 100:+.2f},{tr[1][1] * 100:+.2f}] n{tr[2]}  val {va[0] * 100:+.2f}% [{va[1][0] * 100:+.2f},{va[1][1] * 100:+.2f}]", flush=True)
        name, rs, tr, va = max(res, key=lambda x: x[2][0])
        if va[0] > 0 and tr[0] > 0:
            te = P.stats(P.split(rs, "test"))
            print(f"  -> {fam} chosen {name}: TEST {te[0] * 100:+.2f}%/wk [{te[1][0] * 100:+.2f},{te[1][1] * 100:+.2f}] n{te[2]}", flush=True)
        else:
            print(f"  -> {fam} chosen {name}: validation disagrees or train <= 0; test not read", flush=True)
    print(f"rules tried: {n_rules}")
