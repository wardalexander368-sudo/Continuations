"""Dip entries on the bonding curve: buy after a launch that reached X SOL falls d from its peak.

    python3 handoff/experiments/curve_dip_entry.py OUT.pkl [OUT.pkl ...]   # exit_study.py extract pickles

Signal: within 30 min of the create, the first trade at which the price is at least d (30/50/70%)
below its running peak, once the curve's real SOL has reached X (10/20/40) at that peak. Buy 1 s
later; exits, costs, split and coverage as level_entry.py.
"""
import itertools
import sys

import numpy as np

sys.path.insert(0, ".")
sys.path.insert(0, "handoff/experiments")
from exit_study import TEST_FROM, Window, exit_time, fmt, load, stats  # noqa: E402

SIZE, FEE, NET, LAT = 0.02, 0.0125, 0.000011, 1.0
launches = load(sys.argv[1:])
CASES = list(itertools.product((10, 20, 40), (0.3, 0.5, 0.7)))
signals = {c: [] for c in CASES}
for L in launches:
    a = L["path"]
    a = a[a[:, 0] <= L["created"] + 1800]
    if len(a) < 2:
        continue
    price = a[:, 1] / a[:, 2]
    rs = a[:, 1] - 30.0
    peak_i = np.zeros(len(a), int)
    best = 0
    for i in range(len(a)):
        if price[i] > price[best]:
            best = i
        peak_i[i] = best
    peak_p, peak_rs = price[peak_i], rs[peak_i]
    for X, d in CASES:
        k = np.flatnonzero((peak_rs >= X) & (price <= (1 - d) * peak_p))
        if len(k):
            signals[(X, d)].append({**L, "t": a[k[0], 0]})
grid = []
for (X, d), tp, hold in itertools.product(CASES, (None, 0.3, 1.0), (180, 600, 1800)):
    r = {"hold": hold, "tp": tp}
    out = {"dev": [], "test": []}
    for L in signals[(X, d)]:
        w = Window(L, SIZE, FEE, NET, LAT)
        if w.tokens is None:
            continue
        v = w.exit_at(exit_time(w, r), LAT, w.entry_t + hold)
        if v is not None:
            out["dev" if L["created"] < TEST_FROM else "test"].append(v)
    grid.append((X, d, tp, hold, np.array(out["dev"]), np.array(out["test"])))
    print(f"X {X:2d} dip {d} TP {tp} hold {hold:4d}: dev {fmt(stats(grid[-1][4]))}")
best = max((g for g in grid if len(g[4]) >= 200), key=lambda g: g[4].mean())
print(f"\nCHOSEN X {best[0]} dip {best[1]} TP {best[2]} hold {best[3]}: dev {fmt(stats(best[4]))}\n  TEST {fmt(stats(best[5]))}")
