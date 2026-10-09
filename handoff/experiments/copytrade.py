"""Copy-trading on pump.fun curves: follow the buys of wallets whose buys paid off earlier.

    python3 handoff/experiments/copytrade.py DIR [DIR...]                       # development split
    python3 handoff/experiments/copytrade.py --learn DIR[,DIR] --apply DIR \\
        --min-buys N --min-score S --exit E                                     # forward test, fixed rule

A *follow trade* copies one buy: our buy of `size` SOL lands `latency` seconds after the wallet's
buy was received, on the curve state then (constant product, 1.25% fee from the input), and is
sold after a fixed hold or `latency` after the wallet's own next sell of that token ("mirror",
capped at 10 min). Fills match `tartar profit`: the state of the last recorded trade at or
before each fill time; 0.0002 SOL per transaction.

A wallet's score is the mean net return of following its buys during the learning period, shrunk
toward zero (sum / (n + 5)). A rule follows wallets with at least `min_buys` learning buys and a
score above `min_score`; on each token it enters once, on the first qualifying buy.

Honesty rules (profitability.md): the learning, validation and test periods are consecutive in
time (by buy time); a follow trade is excluded only when the recorder was down during it (event
gap > 30 s or recording end); only buys within 45 minutes of a token's creation are followed (the
recorder tracks a token for 60 minutes); the creator's own buys are not followed; tokens seen by
two recorders are taken from the first directory only. Exits after the curve completed are
valued at the final curve price less 10% (PumpSwap isn't priced here). Intervals bootstrap over
tokens.
"""
import argparse
import bisect
import gzip
import json
from collections import defaultdict
from pathlib import Path

import numpy as np

FEE, NETWORK, SIZE, LATENCY = 0.0125, 0.0002, 0.1, 1.0
MAX_AGE = 45 * 60.0
MIRROR_CAP = 600.0
EXITS = ("30", "120", "600", "mirror")
SHRINK = 5.0
GAP = 30.0


class Token:
    __slots__ = ("mint", "created", "creator", "ts", "vsol", "vtok", "completed")

    def __init__(self, mint, created, creator):
        self.mint, self.created, self.creator = mint, created, creator
        self.ts, self.vsol, self.vtok = [], [], []
        self.completed = None

    def state(self, t):
        i = bisect.bisect_right(self.ts, t) - 1
        return None if i < 0 else (self.vsol[i], self.vtok[i])


def load(dirs):
    """Tokens, buys and sells over every directory; each directory is its own timeline (gaps, end)."""
    tokens, buys, sells, downtime = {}, [], defaultdict(list), []
    for d in dirs:
        times, mine = [], set()
        for path in sorted(Path(d).glob("*.jsonl*")):
            opener = gzip.open if path.suffix == ".gz" else open
            with opener(path, "rt") as f:
                for line in f:
                    try:
                        e = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    t = e.get("t")
                    if t is None:
                        continue
                    times.append(t)
                    kind, mint = e.get("e"), e.get("mint")
                    if e.get("quote") or kind not in ("create", "trade", "migrate"):
                        continue
                    if kind == "create":
                        if mint in tokens:
                            continue  # seen by an earlier recorder
                        tokens[mint] = Token(mint, t, e.get("creator") or "")
                        mine.add(mint)
                    if mint not in mine:
                        continue
                    tok = tokens[mint]
                    if kind == "migrate":
                        tok.completed = tok.completed or t
                        continue
                    if e.get("vsol") and e.get("vtok"):
                        tok.ts.append(t)
                        tok.vsol.append(e["vsol"])
                        tok.vtok.append(e["vtok"])
                    if kind == "trade" and e.get("trader"):
                        if e.get("side") == "b":
                            buys.append((t, e["trader"], mint, len(downtime)))
                        else:
                            sells[(e["trader"], mint)].append(t)
        times.sort()
        downtime.append(([(a, b) for a, b in zip(times, times[1:]) if b - a > GAP], times[-1] if times else 0.0))
    buys.sort()
    return tokens, buys, sells, downtime


def follow(tok, t, exit_rule, wallet_sells, gaps, end):
    """Net return of following a buy received at t, or None if unknown (recorder down) or unfillable."""
    t_in = t + LATENCY
    if exit_rule == "mirror":
        later = [s for s in wallet_sells if s > t]
        t_out = min(later[0], t + MIRROR_CAP) + LATENCY if later else t + MIRROR_CAP + LATENCY
    else:
        t_out = t + float(exit_rule) + LATENCY
    if t_out > end or any(a < t_out and b > t for a, b in gaps):
        return None
    if tok.completed is not None and t_in >= tok.completed:
        return None  # the curve completed before our buy landed: no trade (one wasted tx ignored)
    s0, s1 = tok.state(t_in), tok.state(t_out)
    if s0 is None or s1 is None:
        return None
    vsol, vtok = s0
    sol_in = SIZE * (1 - FEE)
    tokens = vtok * sol_in / (vsol + sol_in)
    vsol, vtok = s1
    proceeds = vsol * tokens / (vtok + tokens) * (1 - FEE)
    if tok.completed is not None and t_out >= tok.completed:
        proceeds *= 0.9
    return (proceeds - SIZE - 2 * NETWORK) / SIZE


def outcomes(tokens, buys, sells, downtime, exit_rule):
    """Per followable buy: (t, wallet, mint, net) with net None when unknown."""
    out = []
    for t, wallet, mint, d in buys:
        tok = tokens.get(mint)
        if tok is None or wallet == tok.creator or t - tok.created > MAX_AGE:
            continue
        gaps, end = downtime[d]
        out.append((t, wallet, mint, follow(tok, t, exit_rule, sells.get((wallet, mint), ()), gaps, end)))
    return out


def scores(rows):
    acc = defaultdict(lambda: [0.0, 0])
    for _, w, _, r in rows:
        if r is not None:
            acc[w][0] += r
            acc[w][1] += 1
    return {w: (s / (n + SHRINK), n) for w, (s, n) in acc.items()}


def trades(rows, wallet_scores, min_buys, min_score):
    """First qualifying buy per token, with a known outcome."""
    seen, out = set(), []
    for t, w, mint, r in rows:
        if mint in seen:
            continue
        sc = wallet_scores.get(w)
        if sc is None or sc[1] < min_buys or sc[0] <= min_score:
            continue
        seen.add(mint)
        if r is not None:
            out.append((t, mint, r))
    return out


def stats(rows, rng, boots=2000):
    if not rows:
        return None
    v = np.array([r for _, _, r in rows])
    means = v[rng.integers(0, len(v), (boots, len(v)))].mean(axis=1)  # one trade per token
    lo, hi = np.quantile(means, [0.05, 0.95])
    half = len(v) // 2
    return {"n": len(v), "mean": v.mean(), "lo": lo, "hi": hi, "median": float(np.median(v)), "win": float(np.mean(v > 0)), "halves": (v[:half].mean() if half else np.nan, v[half:].mean() if half else np.nan)}


def fmt(s):
    if not s:
        return "no trades"
    return f"{s['n']:>4} trades  mean {100 * s['mean']:+6.2f}% [{100 * s['lo']:+6.2f}, {100 * s['hi']:+6.2f}]  median {100 * s['median']:+6.2f}%  win {100 * s['win']:4.1f}%  halves {100 * s['halves'][0]:+.1f}% / {100 * s['halves'][1]:+.1f}%"


GRID = [(n, s) for n in (5, 10, 20) for s in (0.0, 0.02, 0.05, 0.10)]


def development(dirs, rng):
    tokens, buys, sells, downtime = load(dirs)
    times = [b[0] for b in buys]
    t1, t2 = np.quantile(times, [0.5, 0.75])
    print(f"{len(tokens)} SOL launches, {len(buys)} buys; learning < {t1:.0f} <= validation < {t2:.0f} <= test (by buy time)\n")
    best, results = None, {}
    for exit_rule in EXITS:
        rows = outcomes(tokens, buys, sells, downtime, exit_rule)
        learn = [r for r in rows if r[0] < t1 - MIRROR_CAP - 2 * LATENCY]  # outcomes known before validation starts
        sc = scores(learn)
        base_val = stats([(t, m, r) for t, w, m, r in rows if t1 <= t < t2 and r is not None], rng, boots=200)
        print(f"exit {exit_rule:>6}: every followable buy in validation (not one per token): {fmt(base_val)}")
        for n, s in GRID:
            val = trades([r for r in rows if t1 <= r[0] < t2], sc, n, s)
            st = stats(val, rng, boots=300)
            results[(exit_rule, n, s)] = (rows, sc)
            print(f"   min buys {n:>2}, score > {s:+.2f}: {fmt(st)}")
            if st and st["n"] >= 30 and (best is None or st["mean"] > best[1]["mean"]):
                best = ((exit_rule, n, s), st)
    if best is None:
        print("no rule with 30+ validation trades")
        return
    (exit_rule, n, s), _ = best
    rows, _ = results[(exit_rule, n, s)]
    learn = [r for r in rows if r[0] < t2 - MIRROR_CAP - 2 * LATENCY]  # re-learn through validation
    test = trades([r for r in rows if r[0] >= t2], scores(learn), n, s)
    print(f"\nTEST, rule chosen on validation (exit {exit_rule}, min buys {n}, score > {s:+.2f}; wallets re-learned through validation):\n  {fmt(stats(test, rng))}")


def forward(learn_dirs, apply_dir, n, s, exit_rule, rng):
    tokens, buys, sells, downtime = load(learn_dirs)
    sc = scores(outcomes(tokens, buys, sells, downtime, exit_rule))
    tokens2, buys2, sells2, downtime2 = load([apply_dir])
    rows = outcomes(tokens2, buys2, sells2, downtime2, exit_rule)
    qualified = sum(1 for w, (v, k) in sc.items() if k >= n and v > s)
    print(f"learned {len(sc)} wallets on {learn_dirs}; {qualified} qualify (>= {n} buys, score > {s:+.2f})")
    print(f"applied to {apply_dir}: {len(tokens2)} launches, {len(buys2)} buys")
    print(f"FORWARD (exit {exit_rule}): {fmt(stats(trades(rows, sc, n, s), rng))}")
    print(f"reference, every followable buy (not one per token): {fmt(stats([(t, m, r) for t, w, m, r in rows if r is not None], rng, boots=300))}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("dirs", nargs="*")
    ap.add_argument("--learn", default="")
    ap.add_argument("--apply", default="")
    ap.add_argument("--min-buys", type=int, default=10)
    ap.add_argument("--min-score", type=float, default=0.0)
    ap.add_argument("--exit", default="120")
    a = ap.parse_args()
    rng = np.random.default_rng(0)
    if a.apply:
        forward(a.learn.split(","), a.apply, a.min_buys, a.min_score, a.exit, rng)
    else:
        development(a.dirs, rng)


if __name__ == "__main__":
    main()
