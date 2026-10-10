"""Cross-sectional funding carry on every Hyperliquid perp (edge hunt angle D2), exploratory.

    python3 handoff/experiments/edge-hunt/crosssection/fetch_hl_funding.py   # first: funding cache
    python3 handoff/experiments/edge-hunt/crosssection/xs_carry.py

Same universe, weekly schedule, costs and splits as xs_rules.py. Signal: mean hourly funding over
the last L days (L in 1, 7, 28) up to the signal close. "carry": short the top funding quintile
and long the bottom (collect funding); "anti": the reverse. Returns include each leg's actual
funding over the hold. Rule chosen on train, read on validation, test read once.
"""
import importlib.util, json
from datetime import date
from pathlib import Path
import numpy as np

spec = importlib.util.spec_from_file_location("xs", Path(__file__).with_name("xs_rules.py"))
xs = importlib.util.module_from_spec(spec); spec.loader.exec_module(xs)
CACHE = Path("handoff/data/edge-hunt/hl-funding")
F = {c: {int(k): v for k, v in json.loads((CACHE / f"{c}.json").read_text()).items()} for c in xs.coins if (CACHE / f"{c}.json").exists()}
H = lambda d: (date.fromisoformat(d) - date(1970, 1, 1)).days * 24      # hour index of a day's 00:00 UTC


def fsum(c, h0, h1):
    f = F.get(c, {})
    return sum(f.get(h, 0.0) for h in range(h0, h1))


def run(L, sign, lag=0, cost=xs.COST):
    out, prev = [], {}
    C, V, days, coins = xs.C, xs.V, xs.days, xs.coins
    for k, i in enumerate(xs.mondays[:-1]):
        j = xs.mondays[k + 1]
        e, x = i + lag, j + lag
        if x >= len(days): break
        hist = ~np.isnan(C[i - 59: i + 1]).any(axis=0)
        with np.errstate(all="ignore"):
            medv = np.nanmedian(V[i - 29: i + 1], axis=0)
        h_sig = H(days[i]) + 24                                   # signal at day i's close
        ok = hist & (medv >= 2e6) & np.array([c in F for c in coins]) & ~np.isnan(C[e])
        ids = np.where(ok)[0]
        if len(ids) < 15: continue
        s = np.array([fsum(coins[j2], h_sig - 24 * L, h_sig) / (24 * L) for j2 in ids])
        order = ids[np.argsort(s)]; q = len(order) // 5
        hi, lo = order[-q:], order[:q]
        shorts, longs = (hi, lo) if sign > 0 else (lo, hi)
        h0, h1 = H(days[e]) + 24, H(days[x]) + 24

        def leg(sel, d):
            r = []
            for j2 in sel:
                path = C[e: x + 1, j2]; last = path[~np.isnan(path)][-1]
                r.append(d * (last / C[e, j2] - 1) - d * fsum(coins[j2], h0, h1))
            return np.mean(r)
        w = {**{coins[a]: 1 / q for a in longs}, **{coins[a]: -1 / q for a in shorts}}
        turn = sum(abs(w.get(c, 0) - prev.get(c, 0)) for c in set(w) | set(prev)) / 2
        prev = w
        out.append((days[i], leg(longs, 1) + leg(shorts, -1) - 2 * cost * turn))
    return out


if __name__ == "__main__":
    print(f"{len(F)} coins with funding")
    runs, train = {}, {}
    for L in (1, 7, 28):
        for sign, name in ((1, "carry"), (-1, "anti")):
            rs = runs[(L, name)] = run(L, sign)
            m, ci, n = xs.stats([r for r in rs if xs.SPLITS["train"][0] <= r[0] <= xs.SPLITS["train"][1]])
            train[(L, name)] = m
            print(f"L={L:2d} {name}: train {m*100:+.2f}%/wk [{ci[0]*100:+.2f},{ci[1]*100:+.2f}] n{n}", flush=True)
    best = max(train, key=train.get)
    print(f"chosen on train: L={best[0]} {best[1]}")
    for sp in ("val", "test"):
        a0, a1 = xs.SPLITS[sp]
        m, ci, n = xs.stats([r for r in runs[best] if a0 <= r[0] <= a1])
        print(f"  {sp} {m*100:+.2f}%/wk [{ci[0]*100:+.2f},{ci[1]*100:+.2f}] n{n}")
