import zipfile, io, numpy as np, glob, os
def load(sym, d="dl/k1s"):
    ts, cl = [], []
    for f in sorted(glob.glob(f"{d}/{sym}-1s-*.zip")):
        z = zipfile.ZipFile(f); n = z.namelist()[0]
        a = np.loadtxt(io.TextIOWrapper(z.open(n)), delimiter=",", usecols=(0, 4), dtype=np.float64)
        t = a[:, 0]
        t = np.where(t > 1e14, t / 1e6, t / 1e3)  # us or ms
        ts.append(t.astype(np.int64)); cl.append(a[:, 1])
    t = np.concatenate(ts); c = np.concatenate(cl)
    grid = np.arange(t.min(), t.max() + 1)
    idx = np.searchsorted(t, grid, side="right") - 1
    return grid, c[idx]
if __name__ == "__main__":
    for s in ["SOLUSDT", "BTCUSDT"]:
        g, c = load(s); np.savez(f"dl/{s}_1s.npz", t=g, c=c); print(s, len(g), g[0], g[-1], c[:3])
