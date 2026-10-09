"""Buy the graduation run-up: enter when a curve has raised X SOL, exit near completion.

    python3 handoff/experiments/graduation_runup.py [dirs...] [--latency 1.0]

A pump.fun curve completes (graduates to PumpSwap) at ~85 SOL raised. Price grows with
the square of the virtual SOL reserve, so a curve that goes from X to 85 SOL raised
multiplies its price by ((30 + 85) / (30 + X))^2 on the standard curve.

Rule: the first recorded trade with real SOL raised >= X is the decision; the buy fills
`latency` seconds later on the curve (profit.round_trip semantics). Exit at the first of:
* the curve reaching E SOL raised (selling into the last buyers before completion), filled
  `latency` later;
* a stop-loss on price;
* a time limit;
* the end of the recorded window (an idle token's last price).
Entries whose whole holding window doesn't fit before a recording cut are skipped *at
entry*: dropping trades by when they end would keep quick winners and lose slow losers.
Every trade decision depends only on the curve so far. Results are by launch time
(earlier vs later half) to see whether anything holds out of sample.
"""
import argparse
import sys

import numpy as np

sys.path.insert(0, ".")
from tartar.data.dataset import load_trade_tokens  # noqa: E402
from tartar.profit import Costs, curves_for, buy_tokens, sell_sol  # noqa: E402

parser = argparse.ArgumentParser()
parser.add_argument("dirs", nargs="*", default=["handoff/data/raw", "handoff/data/raw-slots", "handoff/data/raw-slots-processed"])
parser.add_argument("--latency", type=float, default=1.0)
parser.add_argument("--size", type=float, default=0.1)
parser.add_argument("--haircut", type=float, default=0.10, help="discount on the final curve price for exits after graduation (sold on PumpSwap; not recorded)")
args = parser.parse_args()

tokens = load_trade_tokens(args.dirs, 60, min_candles=0)  # keep tokens that graduate within their first minute
curves = curves_for(tokens)
costs = Costs(size_sol=args.size, latency=args.latency)
order = np.argsort([t.created for t in tokens])
half = {int(k): (0 if i < len(order) / 2 else 1) for i, k in enumerate(order)}
raised = []
for token in tokens:
    ticks = sorted((t for g in token.ticks.values() for t, _ in g if t.virtual_sol > 0), key=lambda t: t.ts)
    raised.append((np.array([t.ts for t in ticks]), np.array([t.liquidity for t in ticks])))
print(f"{len(tokens)} tokens; {sum(1 for t in tokens if t.end_reason == 'migrated')} with a recorded migration")


def run(k: int, x: float, e: float, stop: float | None, limit: float):
    curve = curves[k]
    times, rsol = raised[k]
    hit = np.flatnonzero(rsol >= x)
    if not len(hit) or not len(curve):
        return None
    decided = times[hit[0]]
    t_in = decided + costs.latency
    i = curve.index_at(t_in)
    if i < 0:
        return None
    if curve.cut and curve.known_until < t_in + limit:
        return None  # the recording might stop before the trade ends: decide at entry, never by outcome
    completed = tokens[k].end if tokens[k].end_reason == "migrated" else None
    if completed is not None and t_in >= completed:
        return 0.0 - costs.network_sol / costs.size_sol, "missed", True  # the curve completed first: the buy fails
    vsol, vtok = curve.state(i)
    tokens_bought = buy_tokens(vsol, vtok, costs.size_sol, costs.fee)
    fill = costs.size_sol / tokens_bought
    t_exit = None
    reason = "limit"
    after = np.flatnonzero((times > t_in) & (times <= t_in + limit))
    for j in after:
        if completed is not None and times[j] >= completed:
            break
        if rsol[j] >= e:
            t_exit, reason = times[j] + costs.latency, "near_completion"
            break
        if stop is not None and curve.price[curve.index_at(times[j])] <= fill * (1 - stop):
            t_exit, reason = times[j] + costs.latency, "stop"
            break
    if t_exit is None:
        t_exit = t_in + limit
    j = curve.index_at(t_exit)
    xv, xt = curve.state(j)
    proceeds = sell_sol(xv, xt, tokens_bought, costs.fee)
    if completed is not None and t_exit >= completed:
        reason = "after_graduation"  # sold on PumpSwap: final curve price less the haircut
        proceeds *= 1.0 - args.haircut
    pnl = proceeds - costs.size_sol - 2 * costs.network_sol
    return pnl / costs.size_sol, reason, tokens[k].end_reason == "migrated"


rng = np.random.default_rng(0)
print(f"size {costs.size_sol} SOL, fee {100 * costs.fee:.2f}%/side, latency {costs.latency}s, post-graduation haircut {100 * args.haircut:.0f}%\n")
print(f"{'enter at':>9} {'exit at':>8} {'stop':>5} {'limit':>6} | {'half':>5} {'n':>4} {'mean':>8} {'90% CI':>17} {'median':>8} {'win':>5} {'grad':>5}  exits")
for x in (40, 50, 60, 70, 75):
    for e in (80, 84):
        if e <= x + 4:
            continue
        for stop in (None, 0.3):
            for limit in (1800.0,):
                res = [(half[k], r) for k in range(len(tokens)) if (r := run(k, x, e, stop, limit)) is not None]
                for h in (0, 1, None):
                    rows = [r for hh, r in res if h is None or hh == h]
                    if not rows:
                        continue
                    rets = np.array([r[0] for r in rows])
                    boots = rets[rng.integers(0, len(rets), (2000, len(rets)))].mean(axis=1)
                    lo, hi = np.quantile(boots, [0.05, 0.95])
                    reasons = {}
                    for r in rows:
                        reasons[r[1]] = reasons.get(r[1], 0) + 1
                    label = {0: "early", 1: "late", None: "all"}[h]
                    print(f"{x:>7} SOL {e:>5} SOL {('-' if stop is None else f'{stop:.0%}'):>5} {limit / 60:>4.0f}m | {label:>5} {len(rets):>4} {100 * rets.mean():+7.1f}% [{100 * lo:+6.1f},{100 * hi:+6.1f}] {100 * np.median(rets):+7.1f}% {100 * (rets > 0).mean():4.0f}% {100 * np.mean([r[2] for r in rows]):4.0f}%  {reasons}")
                print()
