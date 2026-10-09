import numpy as np, datetime as dt
D = np.load("dl/SOL_1m.npz"); m = D["m"]; lc = np.log(D["c"]) * 1e4; N = len(m)
def ep(y, mo, d=1): return int(dt.datetime(y, mo, d, tzinfo=dt.timezone.utc).timestamp() // 60)
P = {"train": (m[0], ep(2024, 1)), "valid": (ep(2024, 1), ep(2025, 7)), "test": (ep(2025, 7), m[-1] + 1)}
r1 = np.zeros(N); r1[1:] = np.diff(lc)
# trailing vol: rms of 1m returns over previous 240 min (excluding current)
cs = np.concatenate([[0], np.cumsum(r1 ** 2)])
W = 240
vol = np.full(N, np.nan); vol[W + 1:] = np.sqrt((cs[W + 1: N + 1 - 1 + 1][:N - W - 1] - cs[1: N - W]) / W) if False else np.nan
idx = np.arange(N); ok = idx > W
vol[ok] = np.sqrt((cs[idx[ok]] - cs[idx[ok] - W]) / W)  # r1[t-W .. t-1]
def fwd(a, b):
    out = np.full(N, np.nan); out[: N - b] = lc[b:] - lc[a: N - b + a]; return out
COST = 1.5  # bps round trip (0.5/fill x2 + slack)
for k in [1, 5, 15]:
    past = np.full(N, np.nan); past[k:] = lc[k:] - lc[:-k]
    z = past / (vol * np.sqrt(k))
    for skip in [0, 1]:
        for H in [5, 15, 60]:
            y = fwd(skip, skip + H)
            row = []
            for name, (a, b) in P.items():
                for th in [4, 6]:
                    sel = (m >= a) & (m < b) & np.isfinite(z) & np.isfinite(y) & (np.abs(z) >= th)
                    # de-cluster: keep first event in each 60-minute block
                    ii = np.where(sel)[0]
                    if len(ii) == 0: row.append(f"{name} z>={th}: none"); continue
                    keep = np.concatenate([[True], np.diff(ii) > 60]); ii = ii[keep]
                    rev = -np.sign(z[ii]) * y[ii]  # reversal P&L before cost
                    row.append(f"{name} z>={th}: n={len(ii)} rev {rev.mean():+.1f}±{rev.std()/np.sqrt(len(ii)):.1f}")
            print(f"k={k:2d}m skip={skip} H={H:2d}m | " + " | ".join(row))
