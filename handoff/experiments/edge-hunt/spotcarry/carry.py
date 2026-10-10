"""E3 spot-perp funding carry backtest (handoff/preregistration/spot-carry/SPEC.md).

    python3 handoff/experiments/edge-hunt/spotcarry/carry.py     -> handoff/data/edge-hunt/spotcarry/result.json
"""
import bisect
import csv
import gzip
import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

D = Path("handoff/data/edge-hunt/spotcarry")
H, DAY = 3_600_000, 86_400_000
A = ("2026-03-16", "2026-07-01")
B = ("2026-07-01", "2026-10-08")
GRID = [(L, E) for L in (1, 3, 7) for E in (None, 0.0, 0.15, 0.30)]
SPOT_FRAC, LEV, LIQ_MOVE, LIQ_PENALTY, BLOCK = 2 / 3, 2.0, 0.45, 0.015, 7


def ms(d):
    return int(datetime.fromisoformat(d).replace(tzinfo=timezone.utc).timestamp() * 1000)


data = json.loads(gzip.decompress((D / "data.json.gz").read_bytes()))
pairs = data["pairs"]
usdc = {}
with open("handoff/data/edge-hunt/carry_daily.csv") as fh:
    for r in csv.DictReader(fh):
        usdc[ms(r[""])] = float(r["usdc"] or 0)
for p in pairs:
    p["S"] = {r[0]: r for r in p["spot_candles"]}
    p["P"] = {r[0]: r for r in p["perp_candles"]}
    p["F"] = {int(t) // H * H: v for t, v in p["funding"]}
    for k in ("S", "P"):  # forward-filled closes: an hour without trades keeps the last price (no fake P&L)
        p[k + "t"] = sorted(p[k])


def last_close(p, k, t):
    """Close of the latest candle that ended by time t (candles start at their key and last an hour)."""
    ts = p[k + "t"]
    i = bisect.bisect_right(ts, t - H) - 1
    return p[k][ts[i]][4] if i >= 0 else None


def signal(p, t, L):
    xs = [p["F"][h] for h in range(t - L * DAY, t, H) if h in p["F"]]
    return np.mean(xs) * 8760 if len(xs) >= 12 * L else None


def run(L, E, d0, d1, coin=None):
    """Daily excess returns over Kamino USDC for the 8-slot book (or one coin's slot alone)."""
    ps = [p for p in pairs if coin is None or p["perp"] == coin]
    n = len(ps)
    on = {p["perp"]: None for p in ps}  # perp -> {"units", "p0"} while on
    out, liq, gross_f, costs = [], 0, 0.0, 0.0
    for t in range(ms(d0), ms(d1), DAY):
        u = usdc.get(t, 0.0)
        day_ret = 0.0
        for p in ps:
            c, slot = p["perp"], 1.0 / n
            s0, p0 = last_close(p, "S", t), last_close(p, "P", t)
            if not s0 or not p0:
                day_ret += slot * u
                continue
            sig = signal(p, t, L)
            pos = on[c]
            want = (E is None) or (sig is not None and (sig > E if pos is None else sig >= E / 2))
            sc, pc = p["spot_cost_side"], p["perp_cost_side"]
            pnl = 0.0
            if want and pos is None:
                notional = slot * SPOT_FRAC
                pos = on[c] = {"units": notional / s0, "notional": notional}
                pnl -= notional * (sc + pc)
                costs += notional * (sc + pc)
            elif not want and pos is not None:
                pnl -= pos["notional"] * (sc + pc)
                costs += pos["notional"] * (sc + pc)
                on[c] = pos = None
            if pos is None:
                day_ret += pnl + slot * u
                continue
            q = pos["units"]
            hours = [h for h in range(t, t + DAY, H)]
            prev_close = p0
            liquidated = False
            for h in hours:
                pr = p["P"].get(h)
                rate = p["F"].get(h, 0.0)
                if pr:
                    if pr[2] / prev_close - 1 > LIQ_MOVE:
                        liquidated = True
                    f = q * pr[4] * rate
                    pnl += f
                    gross_f += f
            s_close, p_close = last_close(p, "S", t + DAY), last_close(p, "P", t + DAY)
            perp_pnl = -q * (p_close - p0)
            pnl += q * (s_close - s0) + perp_pnl
            top_up = abs(perp_pnl) * sc  # move the perp's P&L between margin and spot
            pnl -= top_up
            costs += top_up
            if liquidated:
                liq += 1
                pnl -= pos["notional"] * LIQ_PENALTY
                on[c] = None
            # cash in the slot not in spot (margin) earns nothing; the rest of the slot is the position
            day_ret += pnl
        out.append(day_ret - u)
    return np.array(out), liq, gross_f, costs


def block_ci(x, n=4000, seed=0):
    rng, k = np.random.default_rng(seed), int(np.ceil(len(x) / BLOCK))
    m = [x[np.concatenate([np.arange(s, s + BLOCK) % len(x) for s in rng.integers(0, len(x), k)])[:len(x)]].mean() for _ in range(n)]
    return [float(v) * 365 for v in np.percentile(m, [5, 95])]


def main():
    res = {"A": []}
    for L, E in GRID:
        x, liq, gf, co = run(L, E, *A)
        res["A"].append({"L": L, "E": E, "excess_apr": float(x.mean() * 365), "liq": liq, "funding": gf, "costs": co})
        print(f"A  L={L} E={E}: excess {100 * x.mean() * 365:+.2f}% APR  liq {liq}  funding {gf:.4f} costs {co:.4f}")
    best = max(res["A"], key=lambda r: r["excess_apr"])
    L, E = best["L"], best["E"]
    x, liq, gf, co = run(L, E, *B)
    lo, hi = block_ci(x)
    res["B"] = {"L": L, "E": E, "excess_apr": float(x.mean() * 365), "ci90_apr": [lo, hi], "liq": liq, "funding_gross": gf,
                "costs": co, "days": len(x), "holds": bool(lo > 0 and liq == 0)}
    months = {}
    for i, t in enumerate(range(ms(B[0]), ms(B[1]), DAY)):
        months.setdefault(datetime.fromtimestamp(t / 1000, timezone.utc).strftime("%Y-%m"), []).append(x[i])
    res["B"]["by_month_apr"] = {m: float(np.mean(v) * 365) for m, v in months.items()}
    res["B_per_coin_always_on"] = {}
    for p in pairs:
        xc, lc, gfc, coc = run(1, None, *B, coin=p["perp"])
        res["B_per_coin_always_on"][p["perp"]] = {"excess_apr": float(xc.mean() * 365), "liq": lc}
    print(json.dumps(res["B"], indent=1))
    print(json.dumps(res["B_per_coin_always_on"], indent=1))
    (D / "result.json").write_text(json.dumps(res, indent=1))


if __name__ == "__main__":
    main()
