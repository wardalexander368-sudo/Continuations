"""How to put the live perps book together: sleeve weights and caps, backtested (paper only, no orders).

    python3 handoff/experiments/momentum_audit.py panel   # once: daily closes cache (data/momentum-audit/panel.pkl)
    python3 handoff/experiments/perps_book.py

Sleeves (weekly, aligned by signal week): xs_momentum, vol_momentum, the search winner
cand-xsm-L21-q10-vol-mon-lag2 (legs, costs and funding exactly as tartar/autotrade/search.backtest), and
HLP holding (vault allTime history: each ~13-day interval's PnL / account value, spread evenly over
its days). Book return = sum over coins of exposure x (coin return - funding) minus each sleeve's
turnover cost, so a coin held by several sleeves is netted and can be capped across the book.

Weightings compared (all use only data before the week they weight):
  equal         1/4 per sleeve (what autotrade does now: equal dollars per strategy)
  inv_vol       risk parity: weight 1/sigma of each sleeve's trailing 26 weekly returns
  vol_target    equal weights scaled so the book's trailing 13-week vol hits 2.5%/week (x0.5 .. x1.5)
  inv_vol_vt    risk parity, then the same vol target
Caps: per coin (|net exposure| <= cap x book across all sleeves; excess scaled down) and a floor on
coins per side in the winner (its deciles hold ~4-5 coins a side; the floor widens to the top/bottom n).
Stops (simulated, not enforced in the backtest unless said): weekly loss limit -12% of the book, and a
35% drawdown stop from the equity peak.
"""
import json
import pickle
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import httpx
import numpy as np

sys.path.insert(0, ".")
from tartar.autotrade import hl_data  # noqa: E402
from tartar.autotrade.search import COST, Panel  # noqa: E402
from tartar.autotrade.strategies.xs_momentum import MIN_HIST, rank_signal  # noqa: E402

HLP = "0xdfc24b077bc1425ad1dea75bcb6f8158e10df303"
RULES = {
    "xs_momentum": {"lookback": 14, "quant": 5, "scaled": False, "signal_weekday": 0, "lag_days": 1},
    "vol_momentum": {"lookback": 14, "quant": 5, "scaled": True, "signal_weekday": 0, "lag_days": 1},
    "cand": {"lookback": 21, "quant": 10, "scaled": True, "signal_weekday": 0, "lag_days": 2},
}
SLEEVES = list(RULES) + ["hlp"]
WEEK_LOSS, DD_STOP = -0.12, 0.35
WEIGHTS: list[dict] = []


def legs(P: Panel, p: dict, min_side: int = 0) -> dict:
    """signal Monday -> (list of (coin j, side, weight in sleeve, return, funding), sleeve cost)."""
    L, Q, lag = p["lookback"], p["quant"], p["lag_days"]
    out, prev = {}, {}
    n = len(P.days)
    for i, d in enumerate(P.days):
        if d.weekday() != p["signal_weekday"] or d < date(2023, 7, 3) or i < max(MIN_HIST, 30, L):
            continue
        e, x = i + lag, i + lag + 7
        if x >= n:
            break
        sig = rank_signal(P.C, i, L, p["scaled"])
        ok = P.base_ok(i) & ~np.isnan(P.C[i - L]) & ~np.isnan(P.C[e]) & np.isfinite(sig)
        ids = np.where(ok)[0]
        if len(ids) < 15:
            continue
        order = ids[np.argsort(sig[ids])]
        q = max(len(order) // Q, min(min_side, len(order) // 2))
        longs, shorts = order[-q:], order[:q]
        ret = P.Cf[x] / P.C[e] - 1
        fund = P.fund_cum[x] - P.fund_cum[e]
        w = {**{int(j): 1 / q for j in longs}, **{int(j): -1 / q for j in shorts}}
        turn = sum(abs(w.get(k, 0) - prev.get(k, 0)) for k in set(w) | set(prev)) / 2
        prev = w
        out[d] = ([(int(j), s, 1 / q, float(ret[j]), float(fund[j])) for j, s in [(j, 1) for j in longs] + [(j, -1) for j in shorts]],
                  2 * COST * turn)
    return out


def hlp_weekly(weeks: list[date]) -> dict:
    d = httpx.post("https://api.hyperliquid.xyz/info", json={"type": "vaultDetails", "vaultAddress": HLP}, timeout=60).json()
    at = dict(d["portfolio"])["allTime"]
    av = [(t / 1000, float(v)) for t, v in at["accountValueHistory"]]
    pn = [(t / 1000, float(v)) for t, v in at["pnlHistory"]]
    daily = {}
    for (t0, a0), (t1, _), (_, p0), (_, p1) in zip(av, av[1:], pn, pn[1:]):
        if a0 <= 0:
            continue
        r = (p1 - p0) / a0
        days = max((t1 - t0) / 86400, 1e-9)
        day = datetime.fromtimestamp(t0, timezone.utc).date()
        while datetime.combine(day, datetime.min.time(), timezone.utc).timestamp() < t1:
            daily[day] = (1 + r) ** (1 / days) - 1
            day += timedelta(days=1)
    out = {}
    for w in weeks:  # the momentum week: signal Monday + 1 day entry close .. +7 days
        rs = [daily.get(w + timedelta(days=k)) for k in range(2, 9)]
        if all(x is not None for x in rs):
            out[w] = float(np.prod([1 + x for x in rs]) - 1)
    return out


def book(sleeve_legs: dict, hlp: dict, weeks: list[date], mode: str, cap: float | None, target: float = 0.025) -> np.ndarray:
    hist = {s: [] for s in SLEEVES}  # each sleeve's own weekly return (uncapped) for weighting
    book_hist, out = [], []
    for w in weeks:
        # weights from past data only
        if mode in ("inv_vol", "inv_vol_vt") and all(len(hist[s]) >= 8 for s in SLEEVES):
            vol = {s: max(np.std(hist[s][-26:], ddof=1), 1e-4) for s in SLEEVES}
            a = {s: 1 / vol[s] for s in SLEEVES}
            tot = sum(a.values())
            a = {s: a[s] / tot for s in SLEEVES}
        elif mode in ("mom_iv", "mom_iv_vt") and all(len(hist[s]) >= 8 for s in RULES):
            vol = {s: max(np.std(hist[s][-26:], ddof=1), 1e-4) for s in RULES}  # risk parity among momentum sleeves
            tot = sum(1 / v for v in vol.values())
            a = {**{s: 0.75 * (1 / vol[s]) / tot for s in RULES}, "hlp": 0.25}
        else:
            a = {s: 1 / len(SLEEVES) for s in SLEEVES}
        if mode in ("vol_target", "inv_vol_vt", "mom_iv_vt") and len(book_hist) >= 8:
            k = float(np.clip(target / max(np.std(book_hist[-13:], ddof=1), 1e-4), 0.5, 1.5))
            a = {s: k * a[s] for s in SLEEVES}
        # coin exposures across sleeves
        expo: dict[int, list] = {}
        cost = 0.0
        for s in RULES:
            lg, c = sleeve_legs[s][w]
            cost += a[s] * c
            for j, side, wt, r, f in lg:
                expo.setdefault(j, []).append([a[s] * side * wt, r, f])
        ret = 0.0
        for j, parts in expo.items():
            net = sum(e for e, _, _ in parts)
            scale = cap / abs(net) if cap and abs(net) > cap else 1.0
            ret += sum(scale * e * (r - f) for e, r, f in parts)
        ret += a["hlp"] * hlp[w] - cost
        out.append(ret)
        book_hist.append(ret)
        WEIGHTS.append(a)
        for s in RULES:  # sleeve's own return for the weighting history
            lg, c = sleeve_legs[s][w]
            hist[s].append(sum(side * wt * (r - f) for _, side, wt, r, f in lg) - c)
        hist["hlp"].append(hlp[w])
    return np.array(out)


def summary(r: np.ndarray, weeks: list[date]) -> dict:
    eq = np.cumprod(1 + r)
    peak = np.maximum.accumulate(np.concatenate([[1.0], eq]))[1:]
    dd = 1 - eq / peak
    fires = [weeks[i].isoformat() for i in np.where(r < WEEK_LOSS)[0]]
    dd_first = next((weeks[i].isoformat() for i in range(len(dd)) if dd[i] >= DD_STOP), None)
    # how often the drawdown stop would fire if the book restarts at the stop (new peak = equity then)
    n_dd, pk, e = 0, 1.0, 1.0
    for x in r:
        e *= 1 + x
        pk = max(pk, e)
        if 1 - e / pk >= DD_STOP:
            n_dd += 1
            pk = e
    return {"mean": 100 * r.mean(), "median": 100 * np.median(r), "worst": 100 * r.min(), "maxdd": 100 * dd.max(),
            "ex_best5": 100 * np.sort(r)[:-5].mean(), "sharpe_wk": r.mean() / r.std(ddof=1), "cagr": 100 * (eq[-1] ** (52 / len(r)) - 1),
            "week_loss_fires": fires, "dd_stop_fires": n_dd, "dd_first": dd_first}


def main():
    d = pickle.loads(Path("data/momentum-audit/panel.pkl").read_bytes())
    P = Panel(d["days"], d["coins"], d["C"], d["V"], hl_data.load_funding(Path("autotrade/search/funding_daily.csv")))
    base_legs = {s: legs(P, p) for s, p in RULES.items()}
    floor_legs = dict(base_legs, cand=legs(P, RULES["cand"], min_side=8))
    weeks = sorted(set.intersection(*(set(v) for v in base_legs.values())))
    hlp = hlp_weekly(weeks)
    weeks = [w for w in weeks if w in hlp]
    print(f"{len(weeks)} common weeks {weeks[0]} .. {weeks[-1]}")
    print("Sleeves alone (100% of the book):")
    for s in SLEEVES:
        if s == "hlp":
            r = np.array([hlp[w] for w in weeks])
        else:
            r = np.array([sum(side * wt * (x - f) for _, side, wt, x, f in base_legs[s][w][0]) - base_legs[s][w][1] for w in weeks])
        m = summary(r, weeks)
        print(f"  {s:<13} mean {m['mean']:+.2f}%/wk, worst {m['worst']:+.1f}%, max DD {m['maxdd']:.1f}%, ex-best-5 {m['ex_best5']:+.2f}%, "
              f"weekly-loss fires {len(m['week_loss_fires'])}, DD-stop fires {m['dd_stop_fires']}")
    rows = []
    print("Books:")
    print(f"  HLP last 26 weeks: {100 * np.mean([hlp[w] for w in weeks[-26:]]):+.2f}%/wk")
    for mode in ("equal", "inv_vol", "vol_target", "inv_vol_vt", "mom_iv", "mom_iv_vt"):
        for cap_name, cap, lg in (("no cap", None, base_legs), ("coin cap 5%", 0.05, base_legs),
                                  ("coin cap 5% + winner >=8/side", 0.05, floor_legs), ("coin cap 3% + winner >=8/side", 0.03, floor_legs)):
            WEIGHTS.clear()
            r = book(lg, hlp, weeks, mode, cap)
            m = summary(r, weeks)
            m["avg_weights"] = {k: round(float(np.mean([x[k] for x in WEIGHTS])), 3) for k in SLEEVES}
            m["last26"] = 100 * r[-26:].mean()
            rows.append({"mode": mode, "caps": cap_name, **m})
            print(f"  {mode:<10} {cap_name:<30} mean {m['mean']:+.2f}%/wk (CAGR {m['cagr']:+.0f}%), worst {m['worst']:+.1f}%, "
                  f"max DD {m['maxdd']:.1f}%, ex-best-5 {m['ex_best5']:+.2f}%, Sharpe/wk {m['sharpe_wk']:.2f}, "
                  f"-12% weeks {len(m['week_loss_fires'])}, 35% DD stops {m['dd_stop_fires']}; last 26 wk {m['last26']:+.2f}%; "
                  f"avg weights {m['avg_weights']}")
    Path("data/perps-book").mkdir(parents=True, exist_ok=True)
    Path("data/perps-book/results.json").write_text(json.dumps(rows, indent=1))


main()
