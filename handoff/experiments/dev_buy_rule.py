"""Small creator buys as a launch screen: a grid on dev launches, the best rule once on test.

    python3 handoff/experiments/dev_buy_rule.py TABLE.pkl   # the table from mover_study.py features

Rule: the creator's own buys in the launch's first T seconds total between lo and hi SOL, and the
creator hasn't sold by then (optionally also the live skip flags, and at least `b` buyers).
Trade: buy at +T s, the paper policy's default exit (TP +100%, 30 min, no stop), Jupiter costs at
0.02 SOL (mover_study.py). Chosen on dev (created before 16:00 UTC 10-09) by mean net, at least
300 trades; reported once on test, with the excess over buying every launch in the same period.
"""
import itertools
import pickle
import sys

import numpy as np

sys.path.insert(0, ".")
sys.path.insert(0, "handoff/experiments")
from exit_study import TEST_FROM, fmt, stats  # noqa: E402

rows = pickle.load(open(sys.argv[1], "rb"))
grid = []
for T, (lo, hi), flags, b in itertools.product((20.0, 60.0), ((0.01, 0.3), (0.05, 0.3), (0.01, 0.5), (0.1, 0.5), (0.01, 0.15)), (False, True), (0, 3, 10)):
    rule = lambda r, lo=lo, hi=hi, flags=flags, b=b: lo <= r["dev_buy"] < hi and r["dev_sold"] == 0 and (r["flags_ok"] or not flags) and r["buyers"] >= b
    dev = np.array([r["ret"] for r in rows if r["T"] == T and r["created"] < TEST_FROM and rule(r)])
    grid.append((dev.mean() if len(dev) >= 300 else -9, T, lo, hi, flags, b, rule, dev))
grid.sort(key=lambda g: -g[0])
for g in grid[:8]:
    print(f"T {g[1]:g} dev_buy {g[2]}-{g[3]} flags {g[4]} buyers>={g[5]}: dev {fmt(stats(g[7]))}")
_, T, lo, hi, flags, b, rule, dev = grid[0]
test = [r for r in rows if r["T"] == T and r["created"] >= TEST_FROM]
sel = np.array([r["ret"] for r in test if rule(r)])
allr = np.array([r["ret"] for r in test])
alld = np.array([r["ret"] for r in rows if r["T"] == T and r["created"] < TEST_FROM])
print(f"\nCHOSEN T {T:g} dev_buy {lo}-{hi} flags {flags} buyers>={b}")
print(f"  dev  {fmt(stats(dev))}   (every launch {100 * alld.mean():+.2f}%)")
print(f"  TEST {fmt(stats(sel))}   (every launch {100 * allr.mean():+.2f}%)")
