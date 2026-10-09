import json, sys, numpy as np
rows = [json.loads(l) for f in sys.argv[1:] for l in open(f)]
bn = sorted([(r["tl"], (r["b"] + r["a"]) / 2) for r in rows if r["k"] == "bn" and r["s"] == "SOLUSDT"])
bt = np.array([x[0] for x in bn]); bm = np.log(np.array([x[1] for x in bn])) * 1e4
cbr = sorted([(r["tl"], (r["b"] + r["a"]) / 2) for r in rows if r["k"] == "cb"])
ct = np.array([x[0] for x in cbr]); cm = np.log(np.array([x[1] for x in cbr])) * 1e4
sl = {}
for r in rows:
    if r["k"] == "sl": sl.setdefault(r["slot"], r["tl"])
q = []
for r in rows:
    if r["k"] in ("jb", "js"):
        px = 1000 / (r["out"] / 1e9) if r["k"] == "jb" else (r["out"] / 1e6) / 9.0
        ts = sl.get(r["slot"])
        q.append((r["t1"], r["t0"], ts, r["k"], np.log(px) * 1e4, r["slot"]))
q.sort()
print(f"binance updates {len(bt)}, coinbase {len(ct)}, jupiter quotes {len(q)}, span {(q[-1][0]-q[0][0])/60:.1f} min, quotes with slot time {sum(x[2] is not None for x in q)}")
def at(t, T, M):
    i = np.searchsorted(T, t, side="right") - 1
    return M[np.clip(i, 0, len(M) - 1)]
qt1 = np.array([x[0] for x in q]); qt0 = np.array([x[1] for x in q]); side = np.array([x[3] for x in q]); lp = np.array([x[4] for x in q])
qts = np.array([x[2] if x[2] is not None else np.nan for x in q])
print("slot-notification time minus request start: median %.3f s (quote state time vs our request)" % np.nanmedian(qts - qt0))
# side offsets vs binance at request time
for s in ("jb", "js"):
    d = lp[side == s] - at(qt0[side == s], bt, bm)
    print(s, "jup - binance mid at request: median %.2f bps sd %.2f" % (np.median(d), d.std()))
off = {s: np.median(lp[side == s] - at(qt0[side == s], bt, bm)) for s in ("jb", "js")}
jm = lp - np.array([off[s] for s in side])  # side-adjusted jupiter mid estimate
# which binance time does the quote match best? scan delta relative to request start t0
print("var(jup_mid - binance(t0+delta)) by delta (s): smaller = quote reflects binance at that time")
for d in [-3, -2, -1.5, -1, -0.6, -0.4, -0.2, 0, 0.2, 0.4, 0.6, 1, 2]:
    e = jm - at(qt0 + d, bt, bm); e = e - np.median(e)
    print(f"  delta {d:+.1f}: sd {e.std():.3f} bps")
print("same vs Coinbase:")
for d in [-2, -1, -0.5, 0, 0.5, 1, 2]:
    e = jm - at(qt0 + d, ct, cm); e = e - np.median(e)
    print(f"  delta {d:+.1f}: sd {e.std():.3f} bps")
# tradeable check: at each quote i (decision at its response t1), gap = binance(t1) - jm_i. Fill at next quote of the right side requested >= t1 + L, exit at Binance mid at fill + H (mark), report gross in bps beyond the side-offset
for L in [0.0, 1.0, 2.0]:
    for H in [2, 5, 15]:
        gains = []; gaps = []
        for i in range(len(q) - 4):
            gap = at(qt1[i], bt, bm) - jm[i]
            gaps.append(gap)
            if abs(gap) < 1.0: continue
            want = "jb" if gap > 0 else "js"
            j = next((k for k in range(i + 1, min(i + 8, len(q))) if side[k] == want and qt0[k] >= qt1[i] + L), None)
            if j is None: continue
            fill = lp[j] - off[want]  # fill relative to mid-equivalent
            exitm = at(qt0[j] + H, bt, bm)
            g = (exitm - fill) if want == "jb" else (fill - exitm)
            gains.append(g)
        g = np.array(gains)
        if len(g): print(f"L={L:.0f}s H={H:2d}s: |binance - jup| >= 1 bps at decision: n={len(g)}, gross vs mid-equivalent {g.mean():+.2f} ± {g.std()/np.sqrt(len(g)):.2f} bps (cost to beat ~0.5-1 bps per side beyond offset)")
gaps = np.array(gaps); print("decision gap |binance - jup| distribution: p50 %.2f p90 %.2f p99 %.2f bps" % tuple(np.quantile(np.abs(gaps), [0.5, 0.9, 0.99])))
