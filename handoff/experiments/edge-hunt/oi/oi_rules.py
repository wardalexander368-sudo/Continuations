"""Open-interest rules on Hyperliquid perps (OI study, pre-registered in `handoff/preregistration/oi-study/SPEC.md`).

    python3 handoff/experiments/edge-hunt/oi/oi_rules.py --cost-bps 20 --lag 1 --funding --funding-dir handoff/data/edge-hunt/oi-funding

Prices, universe, splits, costs, funding and the weekly backtest come from the perps lane harness
(`perps/perp_rules.py`, same as D and VMOM). OI is OKX's daily OI per coin (`fetch_okx_oi.py`),
because Hyperliquid keeps none. A signal on day i only uses OKX's row for day i-1 (OKX publishes a
day's row within ~4 h of its end; one extra day of slack). Execution is one day after the signal
(--lag 1), so the earliest trade is ~2 days after the last OI value used.

Families (16 rules, all counted; a family's rule is chosen on train, kept only if validation is also
positive, and test is read for kept rules only):
* OIC   weekly quintiles of the L-day % change in OI (coins), L = 3/7/14, both signs (6)
* CONF  momentum confirmed by OI: rank(L-day return) + rank(L-day OI change), L = 7/14 (2)
* DIV   price-OI divergence: rank(L-day return) - rank(L-day OI change), L = 7/14, both signs (4)
* OIZ   OI stretch: log(OI / its 30-day mean), weekly quintiles, both signs (2)
* MAJ   BTC/ETH/SOL daily: a 1-day OI jump > 2 std (vs 30 days) -> fade that day's price move
        (crowding in); an OI drop > 2 std (a flush) -> follow it; hold H = 1/3 days (2)
"""
from __future__ import annotations

import csv
import importlib.util
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("perp_rules", HERE.parent / "perps" / "perp_rules.py")
pr = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pr)  # reads --cost-bps / --lag / --funding / --funding-dir from argv

OI_DIR = Path("handoff/data/edge-hunt/okx-oi")
days, coins, C, R = pr.days, pr.coins, pr.C, pr.R
O = np.full_like(C, np.nan)
for j, c in enumerate(coins):
    f = OI_DIR / f"{c}.csv"
    if not f.exists():
        continue
    for r in csv.DictReader(f.open()):
        i = pr.idx.get(r["day"])
        if i is not None and float(r["oi_ccy"]) > 0:
            O[i, j] = float(r["oi_ccy"])
START = pr.idx["2024-02-05"]  # first Monday with 30+ days of OKX OI (history starts 2024-01-01)
MONDAYS = [i for i in pr.MONDAYS if i >= START]
DAILY = [i for i in pr.DAILY if i >= START]


def doi(i, L):
    """L-day OI change known at day i's close: OKX rows i-1-L .. i-1."""
    return O[i - 1] / O[i - 1 - L] - 1


def ok_oi(i, L):
    return pr.universe(i) & ~np.isnan(O[i - 1 - L: i]).any(axis=0)


def rank(a, ok):
    return np.where(ok, np.argsort(np.argsort(np.where(ok, a, np.inf))).astype(float), np.nan)


def oic(L, sign):
    return pr.backtest(lambda i: pr.quintile_weights(doi(i, L), ok_oi(i, L), sign=sign), MONDAYS)


def conf(L):
    def w(i):
        ok = ok_oi(i, L) & ~np.isnan(C[i - L])
        return pr.quintile_weights(rank(C[i] / C[i - L] - 1, ok) + rank(doi(i, L), ok), ok)
    return pr.backtest(w, MONDAYS)


def div(L, sign):
    def w(i):
        ok = ok_oi(i, L) & ~np.isnan(C[i - L])
        return pr.quintile_weights(rank(C[i] / C[i - L] - 1, ok) - rank(doi(i, L), ok), ok, sign=sign)
    return pr.backtest(w, MONDAYS)


def oiz(sign):
    def w(i):
        ok = ok_oi(i, 30)
        return pr.quintile_weights(np.log(O[i - 1] / np.nanmean(O[i - 30: i], axis=0)), ok, sign=sign)
    return pr.backtest(w, MONDAYS)


def maj(H):
    """Each day i, per major: z of the 1-day log OI change on row i-1 against rows i-31..i-2. Price
    move = return over the same day (i-1). z > 2 with the price up -> short; z > 2 with the price
    down -> long (crowding in, fade). z < -2 (a flush) -> follow the price move. Weight 1/3 per major
    with a signal, held H days; days without a signal hold nothing. Rebalanced every H days."""
    majors = [coins.index(c) for c in ("BTC", "ETH", "SOL")]
    lo = np.log(O)
    d1 = np.vstack([np.full((1, len(coins)), np.nan), lo[1:] - lo[:-1]])

    def w(i):
        out = {}
        for c in majors:
            hist = d1[i - 31: i - 1, c]
            if np.isnan(hist).any() or np.isnan(d1[i - 1, c]) or np.isnan(R[i - 1, c]):
                continue
            z = (d1[i - 1, c] - hist.mean()) / hist.std()
            mv = np.sign(R[i - 1, c])
            if z > 2:
                out[c] = -mv / 3
            elif z < -2:
                out[c] = mv / 3
        return out
    return pr.backtest(w, DAILY[::H])


FAMILIES = {
    "OIC": [(f"L={L} {'+' if s > 0 else '-'}", lambda L=L, s=s: oic(L, s), False) for L in (3, 7, 14) for s in (1, -1)],
    "CONF": [(f"L={L}", lambda L=L: conf(L), False) for L in (7, 14)],
    "DIV": [(f"L={L} {'+' if s > 0 else '-'}", lambda L=L, s=s: div(L, s), False) for L in (7, 14) for s in (1, -1)],
    "OIZ": [(f"{'+' if s > 0 else '-'}", lambda s=s: oiz(s), False) for s in (1, -1)],
    "MAJ": [(f"H={H}", lambda H=H: maj(H), True) for H in (1, 3)],
}

if __name__ == "__main__":
    print(f"cost {pr.COST * 1e4:g} bps/side, lag {pr.LAG}, funding {'on' if pr.USE_FUNDING else 'off'}, "
          f"{int((~np.isnan(O)).any(axis=0).sum())} coins with OKX OI")
    n, held, chosen = 0, set(), []
    for fam, rules in FAMILIES.items():
        res = []
        for name, fn, daily in rules:
            rs = pr.per_week(fn(), daily)
            n += 1
            tr, va = pr.stats(pr.split(rs, "train")), pr.stats(pr.split(rs, "val"))
            res.append((name, rs, tr, va))
            print(f"  {fam:5s} {name:7s} train {tr[0] * 100:+.2f}%/wk [{tr[1][0] * 100:+.2f},{tr[1][1] * 100:+.2f}] n{tr[2]}  "
                  f"val {va[0] * 100:+.2f}% [{va[1][0] * 100:+.2f},{va[1][1] * 100:+.2f}] n{va[2]}", flush=True)
        name, rs, tr, va = max(res, key=lambda x: -np.inf if np.isnan(x[2][0]) else x[2][0])
        if "--no-test" in sys.argv:
            print(f"  -> {fam} chosen {name} (train only; --no-test)")
            continue
        if va[0] > 0 and tr[0] > 0:
            te = pr.stats(pr.split(rs, "test"))
            chosen.append((fam, name, rs))
            print(f"  -> {fam} chosen {name}: TEST {te[0] * 100:+.2f}%/wk [{te[1][0] * 100:+.2f},{te[1][1] * 100:+.2f}] n{te[2]}", flush=True)
        else:
            print(f"  -> {fam} chosen {name}: validation disagrees or train <= 0; test not read", flush=True)
    print(f"rules tried: {n}")
    if chosen and "--corr" in sys.argv:
        vm = dict(pr.vol_mom(14))
        d14 = dict(pr.backtest(lambda i: pr.quintile_weights(C[i] / C[i - 14] - 1, pr.universe(i)), pr.MONDAYS))
        for fam, name, rs in chosen:
            if fam == "MAJ":
                continue  # weekly sums of a daily rule: dates are Mondays too, compared the same way
            t = [(d, r) for d, r in rs if pr.SPLITS["test"][0] <= d <= pr.SPLITS["test"][1] and not np.isnan(r)]
            for lab, ref in (("VMOM14", vm), ("D 14d", d14)):
                pairs = [(r, ref[d]) for d, r in t if d in ref and not np.isnan(ref[d])]
                if len(pairs) > 5:
                    a = np.array(pairs)
                    print(f"  corr {fam} {name} vs {lab} on test weeks: {np.corrcoef(a[:, 0], a[:, 1])[0, 1]:+.2f} (n{len(a)})")
