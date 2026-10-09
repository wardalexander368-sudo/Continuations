import numpy as np
S = np.load("dl/SOLUSDT_1s.npz"); B = np.load("dl/BTCUSDT_1s.npz")
ls = np.log(S["c"]) * 1e4; lb = np.log(B["c"]) * 1e4; N = len(ls); half = N // 2
def back(x, w):
    o = np.full(N, np.nan); o[w:] = x[w:] - x[:-w]; return o
def fwd(x, a, b):
    o = np.full(N, np.nan); o[: N - b] = x[b:] - x[a: N - b + a]; return o
X = np.column_stack([back(lb, 1), back(lb, 3), back(lb, 10), back(lb, 30), back(ls, 1), back(ls, 3), back(ls, 10), back(ls, 30)])
for L in [0, 1, 2, 3]:
    for H in [5, 30]:
        y = fwd(ls, L, L + H)
        ok = np.isfinite(y) & np.isfinite(X).all(1)
        tr = ok.copy(); tr[half:] = False; te = ok.copy(); te[:half] = False
        Xa = np.column_stack([np.ones(N), X])
        beta, *_ = np.linalg.lstsq(Xa[tr][::3], y[tr][::3], rcond=None)
        p = Xa @ beta
        r2 = 1 - np.sum((y[te] - p[te]) ** 2) / np.sum((y[te] - y[te].mean()) ** 2)
        q = np.quantile(np.abs(p[te]), 0.999); sel = te & (np.abs(p) >= q)
        g = np.sign(p[sel]) * y[sel]
        q2 = np.quantile(np.abs(p[te]), 0.99); sel2 = te & (np.abs(p) >= q2)
        g2 = np.sign(p[sel2]) * y[sel2]
        print(f"L={L}s H={H:2d}s: OOS R2 {r2*100:+.3f}% | top 1% |pred|: gross {g2.mean():+.2f} bps (pred {np.abs(p[sel2]).mean():.2f}) | top 0.1%: gross {g.mean():+.2f} bps n={sel.sum()}")
