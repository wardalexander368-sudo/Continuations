"""Trading graduated pump.fun tokens on PumpSwap: do simple entry rules beat the costs? (queue 11a)

    python3 handoff/experiments/pumpswap_study.py DIR [DIR...] [--latency 1] [--size 0.1] [--split 0.6] [--show-test]

Data: recorder directories with PumpSwap swaps (`tartar record --pumpswap-hours N`), each one
timeline. Every graduated SOL pool counts from its `graduate` event; nothing about a pool's
fate decides whether it is included (profitability.md 3.10 lesson). A signal is excluded only
when the *recorder* was down during its trade (a gap of more than 30 s in the event stream, or
the recording ended first). After a pool goes 30 min without a swap the recorder stops watching
it; its price is then taken as unchanged (no trades seen for 30 min, i.e. dead).

Fills: on the pool's reserves after the last recorded swap before execution (decision + latency;
before the first swap, the first swap's pre-trade reserves), constant product, with PumpSwap's
fee for the pool's market cap at that moment (profitability.md 3.13: 1.25% below ~420 SOL,
1.20% to ~1,150, then falling) and 0.0002 SOL network per transaction. Our own buy's effect on
the exit price is ignored (slightly conservative). Prices from the public RPC are exact at each
recorded swap, but a share of swaps is missed, so a price can be stale between recorded swaps.

Rules (one trade per pool per rule), all decided from data up to the decision time:
* grad:   buy `delay` s after graduation, hold H
* mom:    at `at` s after graduation, buy if the price is up more than k since graduation, hold H
* dip:    same, buy if down more than k
* active: at `at` s after graduation, buy if the pool had at least n recorded swaps in the last
          5 min (a survivor with flow), hold H

Selection: pools ordered by graduation time; the best rule per family (mean net, at least
MIN_TRADES trades) is chosen on the first `split` share of pools (validation) and reported once
on the rest (test), with a 90% interval from a bootstrap over pools. `--show-test` prints the
test results; without it only validation is shown (for development on old data).
"""
import argparse
import bisect
import gzip
import json
from pathlib import Path

import numpy as np

SUPPLY = 1e9
GAP = 30.0
MIN_TRADES = 20
HOLDS = (60, 300, 900, 3600)
GRID = (
    [("grad", {"delay": d}) for d in (5, 30, 60, 300)]
    + [("mom", {"at": a, "k": k}) for a in (60, 300, 900) for k in (0.2, 0.5, 1.0)]
    + [("dip", {"at": a, "k": k}) for a in (60, 300, 900) for k in (0.2, 0.4, 0.6)]
    + [("active", {"at": a, "n": n}) for a in (900, 1800, 3600) for n in (10, 50)]
)
TIERS = ((420, 0.0125), (1150, 0.012), (4400, 0.0105), (8000, 0.010), (15000, 0.0095), (23000, 0.009), (30000, 0.008), (40000, 0.0075), (100000, 0.006))


def fee(mcap_sol: float) -> float:
    for edge, f in TIERS:
        if mcap_sol < edge:
            return f
    return 0.003


class Pool:
    def __init__(self, mint: str, pool: str, t_grad: float):
        self.mint, self.pool, self.t_grad = mint, pool, t_grad
        self.ts: list[float] = []
        self.tok: list[float] = []
        self.sol: list[float] = []
        self.init: tuple[float, float] | None = None  # (tok, sol) before the first recorded swap

    def add(self, e: dict) -> None:
        if not self.ts:
            buy = e["side"] == "b"
            self.init = (e["tok_after"] + e["tok"], e["sol_after"] - e["sol"]) if buy else (e["tok_after"] - e["tok"], e["sol_after"] + e["sol"])
        self.ts.append(e["t"])
        self.tok.append(e["tok_after"])
        self.sol.append(e["sol_after"])

    def reserves(self, t: float) -> tuple[float, float] | None:
        i = bisect.bisect_right(self.ts, t) - 1
        if i < 0:
            return self.init
        return self.tok[i], self.sol[i]

    def price(self, t: float) -> float | None:
        r = self.reserves(t)
        return r[1] / r[0] if r and r[0] > 0 and r[1] > 0 else None

    def swaps_between(self, a: float, b: float) -> int:
        return bisect.bisect_right(self.ts, b) - bisect.bisect_right(self.ts, a)


def load(directory: str) -> tuple[list[Pool], list[tuple[float, float]], float]:
    pools: dict[str, Pool] = {}
    times: list[float] = []
    files = sorted(Path(directory).glob("*.jsonl*"))
    for path in files:
        opener = gzip.open if path.suffix == ".gz" else open
        with opener(path, "rt") as f:
            for line in f:
                try:
                    e = json.loads(line)
                except json.JSONDecodeError:
                    continue  # a file still being written can end mid-line
                t = e.get("t")
                if t is None:
                    continue
                times.append(t)
                kind = e.get("e")
                if kind == "graduate" and e.get("pool") and e["pool"] not in pools:
                    pools[e["pool"]] = Pool(e["mint"], e["pool"], t)
                elif kind == "swap" and e.get("pool") in pools and e.get("tok_after") and e.get("sol_after"):
                    pools[e["pool"]].add(e)
    times.sort()
    gaps = [(a, b) for a, b in zip(times, times[1:]) if b - a > GAP]
    silent = [p for p in pools.values() if not p.init]
    if silent:
        print(f"{directory}: {len(silent)} graduated SOL pools without a recorded swap are left out (no price)")
    return [p for p in pools.values() if p.init], gaps, times[-1] if times else 0.0


def trade(pool: Pool, decide: float, hold: float, latency: float, size: float, network: float) -> float | None:
    """Net return of buying `size` SOL at decide + latency and selling at decide + hold + latency."""
    r0 = pool.reserves(decide + latency)
    r1 = pool.reserves(decide + hold + latency)
    if not r0 or not r1 or min(r0 + r1) <= 0:
        return None
    tok_r, sol_r = r0
    q = size / (1 + fee(SUPPLY * sol_r / tok_r))  # net SOL into the curve; fees on top
    tokens = tok_r * q / (sol_r + q)
    tok_r, sol_r = r1
    gross = sol_r * tokens / (tok_r + tokens)
    proceeds = gross * (1 - fee(SUPPLY * sol_r / tok_r))
    return (proceeds - network) / (size + network) - 1


def signal(pool: Pool, family: str, p: dict) -> float | None:
    """Decision time for this rule on this pool, or None if it doesn't fire."""
    if family == "grad":
        return pool.t_grad + p["delay"]
    t = pool.t_grad + p["at"]
    if family in ("mom", "dip"):
        p0, p1 = pool.price(pool.t_grad), pool.price(t)
        if not p0 or not p1:
            return None
        move = p1 / p0 - 1
        return t if (move > p["k"] if family == "mom" else move < -p["k"]) else None
    if family == "active":
        return t if pool.swaps_between(t - 300, t) >= p["n"] else None
    raise ValueError(family)


def run_rules(pools, gaps, end, latency, size, network):
    """{(family, params, hold): [(pool index, net), ...]} over every rule in the grid."""
    results = {}
    for family, params in GRID:
        for hold in HOLDS:
            key = (family, json.dumps(params, sort_keys=True), hold)
            rows = []
            for i, pool in enumerate(pools):
                t = signal(pool, family, params)
                if t is None:
                    continue
                t0, t1 = t, t + hold + latency
                if t1 > end or any(a < t1 and b > t0 for a, b in gaps):
                    continue  # the recorder was down: outcome unknown (decided by the recorder alone)
                net = trade(pool, t, hold, latency, size, network)
                if net is not None:
                    rows.append((i, net))
            results[key] = rows
    return results


def summarize(rows, rng, boots=2000):
    if not rows:
        return None
    idx = np.array([i for i, _ in rows])
    net = np.array([r for _, r in rows])
    by_pool = {}
    for i, r in rows:
        by_pool.setdefault(i, []).append(r)
    keys = list(by_pool)
    means = []
    for _ in range(boots):
        pick = rng.integers(0, len(keys), len(keys))
        means.append(np.mean(np.concatenate([by_pool[keys[j]] for j in pick])))
    lo, hi = np.quantile(means, [0.05, 0.95])
    lo975 = np.quantile(means, 0.0125)  # one-sided 1.25% = 5% / 4 families (Bonferroni)
    order = np.argsort(idx)
    half = len(order) // 2
    return {
        "n": len(net), "mean": net.mean(), "lo": lo, "hi": hi, "lo_bonf": lo975, "median": float(np.median(net)), "win": float(np.mean(net > 0)),
        "halves": (net[order[:half]].mean() if half else float("nan"), net[order[half:]].mean() if half else float("nan")),
    }  # fmt: skip


def fmt(s):
    if not s:
        return "no trades"
    return f"{s['n']:>4} trades  mean {100 * s['mean']:+6.2f}% [{100 * s['lo']:+6.2f}, {100 * s['hi']:+6.2f}]  median {100 * s['median']:+6.2f}%  win {100 * s['win']:4.1f}%  halves {100 * s['halves'][0]:+.2f}% / {100 * s['halves'][1]:+.2f}%"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("dirs", nargs="+")
    ap.add_argument("--latency", type=float, default=1.0)
    ap.add_argument("--size", type=float, default=0.1)
    ap.add_argument("--network", type=float, default=0.0002)
    ap.add_argument("--split", type=float, default=0.6)
    ap.add_argument("--show-test", action="store_true")
    a = ap.parse_args()
    rng = np.random.default_rng(0)

    pools, results = [], {}
    for d in a.dirs:  # each directory is one timeline; pool indices are global, in graduation order
        ps, gaps, end = load(d)
        ps.sort(key=lambda p: p.t_grad)
        offset = len(pools)
        pools += ps
        for key, rows in run_rules(ps, gaps, end, a.latency, a.size, a.network).items():
            results.setdefault(key, []).extend((offset + i, r) for i, r in rows)
    order = np.argsort([p.t_grad for p in pools], kind="stable")
    rank = {int(i): r for r, i in enumerate(order)}
    cut = int(len(pools) * a.split)
    print(f"{len(pools)} graduated SOL pools; validation = first {cut} by graduation time, test = last {len(pools) - cut}")
    print(f"costs: {a.size} SOL per entry, PumpSwap fee by market-cap tier, {a.network} SOL/tx, {a.latency} s latency\n")

    chosen = {}
    print("VALIDATION (every rule; best per family marked *):")
    for family in dict.fromkeys(f for f, _ in GRID):
        best = None
        lines = []
        for (fam, params, hold), rows in results.items():
            if fam != family:
                continue
            val = [(i, r) for i, r in rows if rank[i] < cut]
            s = summarize(val, rng, boots=300)
            lines.append((fam, params, hold, s))
            if s and s["n"] >= MIN_TRADES and (best is None or s["mean"] > best[3]["mean"]):
                best = (fam, params, hold, s)
        for fam, params, hold, s in lines:
            mark = "*" if best and (fam, params, hold) == best[:3] else " "
            print(f" {mark} {fam:<6} {params:<26} hold {hold:>4}s  {fmt(s)}")
        if best:
            chosen[family] = best[:3]
    if not a.show_test:
        print("\n(test results hidden; pass --show-test once the design is frozen)")
        return
    print("\nTEST (the rule chosen on validation, reported once):")
    for family, key in chosen.items():
        rows = [(i, r) for i, r in results[key] if rank[i] >= cut]
        s = summarize(rows, rng)
        verdict = "EDGE (Bonferroni bound > 0)" if s and s["lo_bonf"] > 0 else "no edge"
        print(f"  {family:<6} {key[1]:<26} hold {key[2]:>4}s  {fmt(s)}  bound {100 * s['lo_bonf']:+.2f}%  {verdict}" if s else f"  {family:<6} no test trades")
    base = ("grad", json.dumps({"delay": 30}), 300)
    print(f"\nreference, every pool (all, not selected): grad 30 s, hold 5 min  {fmt(summarize(results.get(base, []), rng))}")


if __name__ == "__main__":
    main()
