import numpy as np, datetime as dt
exec(open("extremes2.py").read().split("grid = list")[0])
# control: mean forward H-min return of all minutes in the same period whose trailing vol is in the same vol decile (decile edges per period)
def excess(k, th, side, H, skip=0):
    out = []
    for name, (a, b) in P.items():
        ii, pnl = events(k, th, side, skip, H, a, b)
        y = fwd(skip, skip + H)
        sel = (m >= a) & (m < b) & np.isfinite(y) & np.isfinite(vol) & (vol > 0)
        edges = np.quantile(vol[sel], np.linspace(0, 1, 21))
        dec_all = np.clip(np.searchsorted(edges, vol[sel]) - 1, 0, 19)
        means = np.array([y[sel][dec_all == d].mean() for d in range(20)])
        dec_ev = np.clip(np.searchsorted(edges, vol[ii]) - 1, 0, 19)
        sgn = -1 if side == "up" else 1
        gross = pnl + COST
        ex = gross - sgn * means[dec_ev]
        rng = np.random.default_rng(0)
        bs = [rng.choice(ex, len(ex)).mean() for _ in range(1000)]
        lo, hi = np.quantile(bs, [0.05, 0.95])
        out.append(f"{name}: n={len(ex)} excess {ex.mean():+.1f} [{lo:+.1f},{hi:+.1f}] (regime drift {np.mean(sgn*means[dec_ev]):+.1f})")
    print(f"k={k} z>={th} {side} H={H} skip={skip}: " + " | ".join(out))
for args in [(30, 5, "down", 60), (30, 4, "down", 30), (30, 3, "down", 30), (15, 4, "down", 30), (15, 3, "down", 15)]:
    excess(*args)
print("momentum after up-spikes (pnl = buy after up move):")
for k, th, H in [(5, 3, 15), (5, 3, 60), (15, 3, 30), (30, 3, 30), (30, 4, 30)]:
    out = []
    for name, (a, b) in P.items():
        ii, pnl = events(k, th, "up", 0, H, a, b)
        mom = -(pnl + COST) - COST
        out.append(f"{name}: n={len(mom)} {mom.mean():+.1f}±{mom.std()/np.sqrt(len(mom)):.1f}")
    print(f"  k={k} z>={th} H={H}: " + " | ".join(out))
