import numpy as np, datetime as dt
exec(open("extremes2.py").read().split("grid = list")[0])
from scipy.stats import trim_mean
yrs = {"train": 3.33, "valid": 1.5, "test": 1.25}
def boot(x, B=2000):
    r = np.random.default_rng(1); b = [r.choice(x, len(x)).mean() for _ in range(B)]; return np.quantile(b, [0.05, 0.95])
for k, th, H in [(15, 3, 15), (15, 4, 30), (30, 3, 30), (30, 4, 30), (30, 4, 60), (30, 5, 60)]:
    for skip in [1]:
        out = []
        for name, (a, b) in P.items():
            ii, pnl = events(k, th, "down", skip, H, a, b)
            lo, hi = boot(pnl)
            out.append(f"{name}: {len(pnl)/yrs[name]:.0f}/yr mean {pnl.mean():+.1f} [{lo:+.1f},{hi:+.1f}] med {np.median(pnl):+.1f} sd {pnl.std():.0f}")
        print(f"k={k} z<=-{th} H={H} skip={skip}m | " + " | ".join(out))
# stress cost sensitivity for one rule: subtract extra cost
ii, pnl = events(30, 4, "down", 1, 30, *P["test"])
for extra in [0, 5, 10, 20]:
    print(f"k30 z4 H30 skip1 test with extra {extra} bps stress cost: mean {pnl.mean()-extra:+.1f}")
