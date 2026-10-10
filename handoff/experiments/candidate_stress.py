"""Pre-live stress test of a perps-momentum candidate from the agent's search (tartar/autotrade/search.py).

    python3 handoff/experiments/candidate_stress.py [--lookback 21 --quant 10 --scaled 1 --weekday 0 --lag 2]

Same engine, data and funding cache as the search. Prints the rule under higher costs, without funding, a
day slower, on neighbouring signal days / lookbacks / quantiles, and how concentrated its return is (legs
per side, a trimmed mean dropping each side's best and worst leg every week, the median leg, long vs
short side, its best and worst weeks). Informative only: the candidate's verdict is its paper test.
"""
import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

import httpx
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from tartar.autotrade import hl_data, search  # noqa: E402
from tartar.autotrade.strategies.xs_momentum import rank_signal  # noqa: E402


def stats(s, label):
    r = np.array([v for _, v in s])
    b = r[search.block_means(len(r), B=5000)].mean(1)
    lo, hi = np.quantile(b, [0.05, 0.95])
    yrs = {}
    for d, v in s:
        yrs.setdefault(d.year, []).append(v)
    print(f"{label:34s} {len(r)} wk  mean {100 * r.mean():+.2f}%/wk [{100 * lo:+.2f}, {100 * hi:+.2f}]  worst {100 * r.min():+.1f}%  "
          + " ".join(f"{y}:{100 * np.mean(v):+.2f}" for y, v in sorted(yrs.items())))


def legs(P, p):
    out = []
    L, Q, lag = p["lookback"], p["quant"], p["lag_days"]
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
        ret, fund = P.Cf[x] / P.C[e] - 1, P.fund_cum[x] - P.fund_cum[e]
        out.append((q, ret[order[-q:]] - fund[order[-q:]], -ret[order[:q]] + fund[order[:q]]))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--lookback", type=int, default=21)
    ap.add_argument("--quant", type=int, default=10)
    ap.add_argument("--scaled", type=int, default=1)
    ap.add_argument("--weekday", type=int, default=0)
    ap.add_argument("--lag", type=int, default=2)
    a = ap.parse_args()
    cand = {"lookback": a.lookback, "quant": a.quant, "scaled": bool(a.scaled), "signal_weekday": a.weekday, "lag_days": a.lag}
    today = datetime.now(timezone.utc).date()
    days, coins, C, V, _ = hl_data.load_daily(httpx.Client(timeout=60), today)
    F = hl_data.load_funding(Path("autotrade/search/funding_daily.csv"))
    P = search.Panel(days, coins, C, V, F)
    print(f"candidate {search.name_of(cand)} (net of costs and funding unless noted; $1 per leg, long + short)\n")
    stats(search.backtest(P, cand), "as queued (20 bps/side)")
    for cost in (0.004, 0.006):
        stats(search.backtest(P, cand, cost=cost), f"costs {int(cost * 1e4)} bps/side")
    stats(search.backtest(P, cand, funding=False), "no funding")
    stats(search.backtest(P, {**cand, "lag_days": cand["lag_days"] + 1}), "one day slower")
    for wd in sorted({(cand["signal_weekday"] + k) % 7 for k in (1, 2, 4)}):
        stats(search.backtest(P, {**cand, "signal_weekday": wd}), f"signal weekday {wd}")
    for L in (cand["lookback"] - 3, cand["lookback"] + 3):
        stats(search.backtest(P, {**cand, "lookback": L}), f"lookback {L}")
    for q in (cand["quant"] - 2, cand["quant"] + 2):
        stats(search.backtest(P, {**cand, "quant": q}), f"quant {q}")
    print()
    for name, p in [("candidate", cand), ("vol_momentum", search.REGISTERED["vol_momentum"]), ("xs_momentum", search.REGISTERED["xs_momentum"])]:
        W = legs(P, p)
        qs = [q for q, _, _ in W]
        full = np.array([l.mean() + s.mean() for _, l, s in W])
        trim = np.array([np.sort(l)[1:-1].mean() + np.sort(s)[1:-1].mean() for q, l, s in W if q >= 3])
        med = np.array([np.median(l) + np.median(s) for _, l, s in W])
        srt = np.sort(full)
        print(f"{name}: legs/side median {int(np.median(qs))} (min {min(qs)}, max {max(qs)}); gross {100 * full.mean():+.2f}%/wk; "
              f"trimmed {100 * trim.mean():+.2f}% ({len(trim)} wk); median leg {100 * med.mean():+.2f}%; long side "
              f"{100 * np.mean([l.mean() for _, l, _ in W]):+.2f}%, short side {100 * np.mean([s.mean() for _, _, s in W]):+.2f}%; "
              f"without its 5 best weeks {100 * srt[:-5].mean():+.2f}%")


if __name__ == "__main__":
    main()
