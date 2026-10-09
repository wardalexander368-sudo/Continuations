import zipfile, io, numpy as np, glob
def load(sym):
    T, C, V, TB = [], [], [], []
    for f in sorted(glob.glob(f"dl/k1s/{sym}-1s-*.zip")):
        z = zipfile.ZipFile(f); a = np.loadtxt(io.TextIOWrapper(z.open(z.namelist()[0])), delimiter=",", usecols=(0, 4, 5, 9))
        t = a[:, 0]; t = np.where(t > 1e14, t / 1e6, t / 1e3).astype(np.int64)
        T.append(t); C.append(a[:, 1]); V.append(a[:, 2]); TB.append(a[:, 3])
    t = np.concatenate(T); grid = np.arange(t.min(), t.max() + 1); idx = np.searchsorted(t, grid, side="right") - 1
    pres = np.isin(grid, t)
    c = np.concatenate(C)[idx]; v = np.where(pres, np.concatenate(V)[idx], 0); tb = np.where(pres, np.concatenate(TB)[idx], 0)
    return grid, c, 2 * tb - v  # signed taker volume (buy - sell)
t, c, sv = load("SOLUSDT"); _, cb, svb = load("BTCUSDT")
ls = np.log(c) * 1e4; N = len(ls); half = N // 2
csum = np.concatenate([[0], np.cumsum(sv)]); csb = np.concatenate([[0], np.cumsum(svb)])
def flow(cs, w):
    o = np.full(N, np.nan); o[w:] = cs[w + 1: N + 1] - cs[1: N - w + 1]; return o
def fwd(a, b):
    o = np.full(N, np.nan); o[: N - b] = ls[b:] - ls[a: N - b + a]; return o
for w in [5, 30, 120]:
    f = flow(csum, w); f = f / np.nanstd(f); fb = flow(csb, w); fb = fb / np.nanstd(fb)
    for name, x in [("SOL flow", f), ("BTC flow", fb)]:
        for L, H in [(2, 10), (2, 60), (2, 300)]:
            y = fwd(L, L + H); out = []
            for part in (slice(0, half), slice(half, N)):
                xx = x[part][::5]; yy = y[part][::5]; ok = np.isfinite(xx) & np.isfinite(yy); xx, yy = xx[ok], yy[ok]
                q = np.quantile(np.abs(xx), 0.99); s = np.abs(xx) >= q
                out.append(f"corr {np.corrcoef(xx, yy)[0,1]:+.4f} top1% signed {np.mean(np.sign(xx[s])*yy[s]):+.2f}")
            print(f"{name} {w:3d}s -> L={L} H={H:3d}: " + " || ".join(out))
