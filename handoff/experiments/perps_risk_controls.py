"""Risk controls for the agent's perps strategies, scored on the search's backtest (paper only).

    python3 handoff/experiments/perps_risk_controls.py

For the search candidate and the two registered momentum rules, on every week since late 2023 (net of
20 bps/side turnover and funding, $1 per side):
* sizing: equal weight (as registered) vs inverse-volatility weights (30-day std) with a per-coin cap
  of ``cap`` of the side's notional;
* weekly loss limit: if the week's running P&L at a daily close is below -L of one side's notional,
  the strategy closes at that close (exit cost charged) and sits out the rest of the week;
* account drawdown stop: the drawdown from peak at which the agent would have written HALT.
Reports mean weekly return, worst week, worst 4 weeks, max drawdown (compounded at 1x), and the
return given up against the uncontrolled rule.
"""
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from tartar.autotrade import hl_data, search  # noqa: E402
from tartar.autotrade.strategies.xs_momentum import rank_signal  # noqa: E402

COST = 0.002


def run(P, p, sizing="equal", cap=1.0, stop=None):
    L, Q, lag = p["lookback"], p["quant"], p["lag_days"]
    out, prev = [], {}
    for i, d in enumerate(P.days):
        if d.weekday() != p["signal_weekday"] or d < search.FIRST_WEEK or i < 60:
            continue
        e, x = i + lag, i + lag + 7
        if x >= len(P.days):
            break
        sig = rank_signal(P.C, i, L, p["scaled"])
        ok = P.base_ok(i) & ~np.isnan(P.C[i - L]) & ~np.isnan(P.C[e]) & np.isfinite(sig)
        ids = np.where(ok)[0]
        if len(ids) < 15:
            continue
        order = ids[np.argsort(sig[ids])]
        q = len(order) // Q
        longs, shorts = order[-q:], order[:q]

        def weights(sel):
            if sizing == "equal":
                w = np.ones(len(sel))
            else:
                dr = P.C[i - 29: i + 1, sel] / P.C[i - 30: i, sel] - 1
                w = 1 / np.maximum(np.nanstd(dr, axis=0), 1e-4)
            w = w / w.sum()
            for _ in range(10):  # cap and redistribute
                over = w > cap
                if not over.any():
                    break
                w[over] = cap
                w[~over] *= (1 - w[over].sum()) / max(w[~over].sum(), 1e-12)
            return w

        wl, ws = weights(longs), weights(shorts)
        # daily path of the week: P&L at each daily close from entry, funding accrued
        pnl_path = []
        for k in range(e + 1, x + 1):
            rl = P.Cf[k, longs] / P.C[e, longs] - 1 - (P.fund_cum[k, longs] - P.fund_cum[e, longs])
            rs = -(P.Cf[k, shorts] / P.C[e, shorts] - 1) + (P.fund_cum[k, shorts] - P.fund_cum[e, shorts])
            pnl_path.append(float(wl @ rl + ws @ rs))
        w = {**{int(j): float(v) for j, v in zip(longs, wl)}, **{int(j): -float(v) for j, v in zip(shorts, ws)}}
        turn = sum(abs(w.get(k, 0) - prev.get(k, 0)) for k in set(w) | set(prev)) / 2
        r = pnl_path[-1]
        stopped = False
        if stop is not None:
            for v in pnl_path:
                if v < -stop:
                    r, stopped = v, True
                    break
        if stopped:
            out.append((d, r - 2 * COST * turn - 2 * COST * 1.0))  # entry turnover + closing everything
            prev = {}
        else:
            out.append((d, r - 2 * COST * turn))
            prev = w
    return out


def summary(s):
    r = np.array([v for _, v in s])
    eq = np.cumprod(1 + r)
    dd = 1 - eq / np.maximum.accumulate(eq)
    four = np.array([r[k:k + 4].sum() for k in range(len(r) - 3)])
    return r.mean(), r.min(), four.min(), dd.max(), r.mean() / r.std() * np.sqrt(52)


def main():
    today = datetime.now(timezone.utc).date()
    import httpx

    days, coins, C, V, _ = hl_data.load_daily(httpx.Client(timeout=60), today)
    P = search.Panel(days, coins, C, V, hl_data.load_funding(Path("autotrade/search/funding_daily.csv")))
    rules = {"candidate L21 q10 vol lag2": {"lookback": 21, "quant": 10, "scaled": True, "signal_weekday": 0, "lag_days": 2},
             "vol_momentum": search.REGISTERED["vol_momentum"], "xs_momentum": search.REGISTERED["xs_momentum"]}
    variants = [("equal, no stop", "equal", 1.0, None)]
    for cap in (0.25, 0.4):
        variants.append((f"inv-vol cap {cap:.0%}", "inv_vol", cap, None))
    for st in (0.08, 0.12, 0.2):
        variants.append((f"equal, weekly stop {st:.0%}", "equal", 1.0, st))
        variants.append((f"inv-vol cap 40%, weekly stop {st:.0%}", "inv_vol", 0.4, st))
    for name, p in rules.items():
        print(f"\n## {name}\n")
        print("| Controls | Mean/wk | Worst week | Worst 4 wk | Max drawdown | Sharpe (ann.) |")
        print("|---|---|---|---|---|---|")
        for label, sz, cap, st in variants:
            m, w1, w4, dd, sh = summary(run(P, p, sz, cap, st))
            print(f"| {label} | {100 * m:+.2f}% | {100 * w1:+.1f}% | {100 * w4:+.1f}% | {100 * dd:.0f}% | {sh:.2f} |")


if __name__ == "__main__":
    main()
