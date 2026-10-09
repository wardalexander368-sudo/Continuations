"""Entries triggered by curve level: buy when a launch's real SOL first reaches X (trading-skills thread).

    python3 handoff/experiments/level_entry.py OUT.pkl [OUT.pkl ...]   # exit_study.py extract pickles

Signal: the first recorded trade, within 30 min of the create, that takes the curve's real SOL to
X or more (X = 5, 10, 15, 20, 30, 40). Buy 1 s later, exit by TP (+30/+100%) or max hold (180 s,
10 min, 30 min), no stop; a position open at graduation is valued at the last curve price less 10%.
Jupiter costs at 0.02 SOL. Rule chosen on dev launches (before 16:00 UTC 10-09), test once.
A signal counts only if the recording covers its whole max hold.
"""
import itertools
import sys

import numpy as np

sys.path.insert(0, ".")
sys.path.insert(0, "handoff/experiments")
from exit_study import TEST_FROM, Window, exit_time, fmt, load, stats  # noqa: E402

SIZE, FEE, NET, LAT = 0.02, 0.0125, 0.000011, 1.0
launches = load(sys.argv[1:])
LEVELS = (5, 10, 15, 20, 30, 40)
signals = {X: [] for X in LEVELS}
for L in launches:
    a = L["path"]
    rs = a[:, 1] - 30.0
    for X in LEVELS:
        k = np.flatnonzero((rs >= X) & (a[:, 0] <= L["created"] + 1800))
        if len(k):
            t = a[k[0], 0]
            if k[0] > 0 and rs[k[0] - 1] >= X:
                continue
            signals[X].append({**L, "t": t})
grid = []
for X, tp, hold in itertools.product(LEVELS, (None, 0.3, 1.0), (180, 600, 1800)):
    r = {"hold": hold, "tp": tp}
    out = {"dev": [], "test": []}
    for L in signals[X]:
        w = Window(L, SIZE, FEE, NET, LAT)
        if w.tokens is None:
            continue
        v = w.exit_at(exit_time(w, r), LAT, w.entry_t + hold)
        if v is not None:
            out["dev" if L["created"] < TEST_FROM else "test"].append(v)
    grid.append((X, tp, hold, np.array(out["dev"]), np.array(out["test"])))
for X, tp, hold, d, _ in grid:
    print(f"X {X:2d} SOL TP {tp} hold {hold:4d}: dev {fmt(stats(d))}")
best = max((g for g in grid if len(g[3]) >= 200), key=lambda g: g[3].mean())
print(f"\nCHOSEN X {best[0]} TP {best[1]} hold {best[2]}: dev {fmt(stats(best[3]))}\n  TEST {fmt(stats(best[4]))}")
