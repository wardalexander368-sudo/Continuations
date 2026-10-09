"""Take-profit / hold / stop-loss grid for the live skip-flag policy on dev launches (exit_study.py pickles).

    python3 handoff/experiments/exit_tp_grid.py OUT.pkl [OUT.pkl ...]
"""
import sys
import numpy as np
sys.path.insert(0, "."); sys.path.insert(0, "handoff/experiments")
from exit_study import FILTERS, TEST_FROM, Window, exit_time, fmt, load, stats
launches = load(sys.argv[1:])
f = FILTERS["live skip flags"]
for size, fee, net, name in ((0.02, 0.0125, 0.000011, "Jupiter 0.02 SOL"), (0.1, 0.0125, 0.0002, "paper model 0.1 SOL")):
    W = [(L, Window(L, size, fee, net, 1.0)) for L in launches if f(L)]
    W = [(L, w) for L, w in W if w.tokens is not None]
    print(f"\n### {name}")
    for tp in (0.5, 1.0, 1.5, 2.0, 3.0, 5.0):
        for hold in (600, 1800):
            for sl in (None, 0.5):
                r = {"hold": hold, "tp": tp, "sl": sl}
                dv = np.array([x for x in (w.exit_at(exit_time(w, r), 1.0, w.entry_t + r["hold"]) for L, w in W if L["created"] < TEST_FROM) if x is not None])
                print(f"  TP {tp:4g} hold {hold:5d} SL {sl}: dev {fmt(stats(dv))}")
