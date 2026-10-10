import numpy as np
S = np.load("dl/SOLUSDT_1s.npz"); B = np.load("dl/BTCUSDT_1s.npz")
assert (S["t"] == B["t"]).all()
t = S["t"]; ls = np.log(S["c"]) * 1e4; lb = np.log(B["c"]) * 1e4
N = len(t); half = N // 2
L = 2  # seconds from decision to fill
def fwd(x, a, b):  # return from t+a to t+b
    out = np.full(N, np.nan); out[: N - b] = x[b:] - x[a: N - b + a]; return out
def back(x, w):
    out = np.full(N, np.nan); out[w:] = x[w:] - x[:-w]; return out
print("SOL 1s ret sd %.2f bps, 60s sd %.2f, BTC 60s sd %.2f" % (np.nanstd(back(ls,1)), np.nanstd(back(ls,60)), np.nanstd(back(lb,60))))
# sample every 5 s to cut overlap a bit
for H in [5, 10, 30, 60, 300]:
    y = fwd(ls, L, L + H)
    for name, sig in [("SOL past 1s", back(ls, 1)), ("SOL past 10s", back(ls, 10)), ("SOL past 60s", back(ls, 60)), ("SOL past 300s", back(ls, 300)),
                      ("BTC past 1s", back(lb, 1)), ("BTC past 10s", back(lb, 10)), ("BTC past 60s", back(lb, 60)),
                      ("BTC-SOL gap 10s", back(lb, 10) - back(ls, 10)), ("BTC-SOL gap 60s", back(lb, 60) - back(ls, 60))]:
        res = []
        for part in [slice(0, half), slice(half, N)]:
            yy = y[part][::5]; xx = sig[part][::5]; ok = np.isfinite(yy) & np.isfinite(xx)
            yy, xx = yy[ok], xx[ok]
            c = np.corrcoef(xx, yy)[0, 1]
            q = np.quantile(np.abs(xx), 0.99)
            sel = np.abs(xx) >= max(q, 1e-9)
            cm = np.mean(np.sign(xx[sel]) * yy[sel]); se = np.std(np.sign(xx[sel]) * yy[sel]) / np.sqrt(sel.sum())
            res.append(f"corr {c:+.4f} | top1% |x|>={q:.1f}: signed fwd {cm:+.2f}±{se:.2f} bps n={sel.sum()}")
        print(f"H={H:3d}s {name:16s} " + " || ".join(res))
