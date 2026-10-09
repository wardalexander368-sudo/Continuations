import zipfile, io, numpy as np, glob
ts, op, cl, vo = [], [], [], []
for f in sorted(glob.glob("dl/k1m/SOLUSDT-1m-*.zip")):
    z = zipfile.ZipFile(f); n = z.namelist()[0]
    a = np.loadtxt(io.TextIOWrapper(z.open(n)), delimiter=",", usecols=(0, 1, 4, 7), dtype=np.float64)
    if not np.isfinite(a[0, 0]): a = a[1:]
    t = a[:, 0]; t = np.where(t > 1e14, t / 1e6, t / 1e3)
    ts.append((t // 60).astype(np.int64)); op.append(a[:, 1]); cl.append(a[:, 2]); vo.append(a[:, 3])
m = np.concatenate(ts); o = np.concatenate(op); c = np.concatenate(cl); v = np.concatenate(vo)
grid = np.arange(m.min(), m.max() + 1)
idx = np.searchsorted(m, grid, side="right") - 1
present = np.isin(grid, m)
np.savez("dl/SOL_1m.npz", m=grid, c=c[idx], o=o[idx], v=np.where(present, v[idx], 0.0), present=present)
print(len(grid), present.mean(), grid[0] * 60, grid[-1] * 60)
