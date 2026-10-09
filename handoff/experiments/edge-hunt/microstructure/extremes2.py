import numpy as np, datetime as dt, itertools
D = np.load("dl/SOL_1m.npz"); m = D["m"]; lc = np.log(D["c"]) * 1e4; N = len(m); present = D["present"]
def ep(y, mo, d=1): return int(dt.datetime(y, mo, d, tzinfo=dt.timezone.utc).timestamp() // 60)
P = {"train": (m[0], ep(2024, 1)), "valid": (ep(2024, 1), ep(2025, 7)), "test": (ep(2025, 7), m[-1] + 1)}
r1 = np.zeros(N); r1[1:] = np.diff(lc)
cs = np.concatenate([[0], np.cumsum(r1 ** 2)]); W = 240
vol = np.full(N, np.nan); idx = np.arange(N); ok = idx > W
vol[ok] = np.sqrt((cs[idx[ok]] - cs[idx[ok] - W]) / W)
def fwd(a, b):
    out = np.full(N, np.nan); out[: N - b] = lc[b:] - lc[a: N - b + a]; return out
COST = 1.5
def events(k, th, side, skip, H, a, b):
    past = np.full(N, np.nan); past[k:] = lc[k:] - lc[:-k]
    z = past / (vol * np.sqrt(k))
    y = fwd(skip, skip + H)
    with np.errstate(invalid="ignore"):
        cond = np.isfinite(z) & np.isfinite(y) & (m >= a) & (m < b) & (vol > 0)
        if side == "down": cond &= z <= -th
        elif side == "up": cond &= z >= th
        else: cond &= np.abs(z) >= th
    ii = np.where(cond)[0]
    if len(ii) == 0: return ii, np.array([])
    # one position at a time: next event only after the previous hold ended
    keep = []; nxt = -1
    for i in ii:
        if i >= nxt: keep.append(i); nxt = i + skip + H + 1
    ii = np.array(keep)
    return ii, -np.sign(z[ii]) * y[ii] - COST
grid = list(itertools.product([5, 15, 30, 60], [3, 4, 5], ["both", "down", "up"], [5, 15, 30, 60]))
res = []
for k, th, side, H in grid:
    ii, pnl = events(k, th, side, 0, H, *P["train"])
    if len(pnl) < 100: continue
    res.append((pnl.mean() / (pnl.std() / np.sqrt(len(pnl))), pnl.mean(), len(pnl), k, th, side, H))
res.sort(reverse=True)
print("top 8 on TRAIN by t (net of 1.5 bps):")
for r in res[:8]: print("  t=%.2f mean %+.2f n=%d | k=%dm z>=%d side=%s H=%dm" % r)
print("bottom 3:"); [print("  t=%.2f mean %+.2f n=%d | k=%dm z>=%d side=%s H=%dm" % r) for r in res[-3:]]
print("share of 144 train cells with t>0: %.2f" % np.mean([r[0] > 0 for r in res]))
best = res[0]; k, th, side, H = best[3:]
for skip in [0, 1, 2]:
    out = []
    for name, (a, b) in P.items():
        ii, pnl = events(k, th, side, skip, H, a, b)
        lo, hi = np.quantile([np.mean(np.random.default_rng(s).choice(pnl, len(pnl))) for s in range(400)], [0.05, 0.95])
        out.append(f"{name}: n={len(pnl)} net {pnl.mean():+.2f} [{lo:+.2f},{hi:+.2f}] win {np.mean(pnl>0):.2f}")
    print(f"chosen k={k} z>={th} {side} H={H} skip={skip}m: " + " | ".join(out))
# per year for chosen, skip 0
ii, pnl = events(k, th, side, 0, H, m[0], m[-1] + 1)
yrs = np.array([dt.datetime.fromtimestamp(int(x) * 60, dt.timezone.utc).year for x in m[ii]])
print("per year:", " ".join(f"{y}: {pnl[yrs==y].mean():+.1f} (n={np.sum(yrs==y)})" for y in sorted(set(yrs))))
# robustness: how do validation means look across the top-20 train cells?
print("top-20 train cells -> valid / test mean net:")
for r in res[:20]:
    k2, th2, side2, H2 = r[3:]
    v = events(k2, th2, side2, 0, H2, *P["valid"])[1]; te = events(k2, th2, side2, 0, H2, *P["test"])[1]
    print(f"  k={k2} z>={th2} {side2:4s} H={H2}: train {r[1]:+.1f} | valid {v.mean():+.1f} (n={len(v)}) | test {te.mean():+.1f} (n={len(te)})")
