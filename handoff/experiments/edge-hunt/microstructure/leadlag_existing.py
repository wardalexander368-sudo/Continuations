import json, sys, numpy as np
from pathlib import Path
D = Path("/home/user/TARTAR/handoff/data/sol-dex")
rows = []
for f in ["costs-20261009.jsonl", "costs-20261009-day.jsonl"]:
    for line in (D / f).read_text().splitlines():
        r = json.loads(line)
        if r.get("later") and len(r["later"]) == 3:
            rows.append(r)
print("samples with re-quotes:", len(rows))
def mids(r):
    cb = [(r["cb_bid"] + r["cb_ask"]) / 2] + [(l["cb_bid"] + l["cb_ask"]) / 2 for l in r["later"]]
    s0 = r["sol_out"]
    buy = [r["size"] / r["sol_out"]] + [r["size"] / l["sol_out"] for l in r["later"]]
    sell = [r["usdc_back"] / s0] + [l["usdc_back"] / s0 for l in r["later"]]
    jm = [np.sqrt(b * s) for b, s in zip(buy, sell)]
    return np.log(cb), np.log(jm)
CB = []; JM = []
for r in rows:
    c, j = mids(r); CB.append(c); JM.append(j)
CB = np.array(CB) * 1e4; JM = np.array(JM) * 1e4  # bps log levels, columns: 0,1,2,5 s
basis = JM - CB
print("basis jup-cb mean %.2f sd %.2f bps" % (basis[:, 0].mean(), basis[:, 0].std()))
def corr(a, b):
    return np.corrcoef(a, b)[0, 1]
def reg(y, x):
    x = x - x.mean(); y = y - y.mean()
    beta = (x * y).sum() / (x * x).sum()
    res = y - beta * x
    se = np.sqrt((res ** 2).sum() / (len(y) - 2) / (x * x).sum())
    return beta, se
dcb01 = CB[:, 1] - CB[:, 0]; djm01 = JM[:, 1] - JM[:, 0]
dcb15 = CB[:, 3] - CB[:, 1]; djm15 = JM[:, 3] - JM[:, 1]
dcb05 = CB[:, 3] - CB[:, 0]; djm05 = JM[:, 3] - JM[:, 0]
dcb12 = CB[:, 2] - CB[:, 1]; djm12 = JM[:, 2] - JM[:, 1]
dcb25 = CB[:, 3] - CB[:, 2]; djm25 = JM[:, 3] - JM[:, 2]
print("sd moves bps: cb 0-1 %.2f, jup 0-1 %.2f, cb 1-5 %.2f, jup 1-5 %.2f" % (dcb01.std(), djm01.std(), dcb15.std(), djm15.std()))
print("contemporaneous corr d(0-1): %.3f; d(1-5): %.3f; d(0-5): %.3f" % (corr(dcb01, djm01), corr(dcb15, djm15), corr(dcb05, djm05)))
for name, y, x in [
    ("jup 1-5 on cb 0-1 (cb leads?)", djm15, dcb01),
    ("cb 1-5 on jup 0-1 (jup leads?)", dcb15, djm01),
    ("jup 2-5 on cb 1-2", djm25, dcb12),
    ("cb 2-5 on jup 1-2", dcb25, djm12),
    ("jup 0-5 on basis0 (jup reverts?)", djm05, basis[:, 0]),
    ("cb 0-5 on basis0 (cb follows jup?)", dcb05, basis[:, 0]),
    ("jup 1-5 on basis1", djm15, basis[:, 1]),
    ("cb 1-5 on basis1", dcb15, basis[:, 1]),
    ("jup 1-5 on (cb0-1 - jup0-1) gap", djm15, dcb01 - djm01),
    ("jup 0-1 on basis0", djm01, basis[:, 0]),
    ("cb 0-1 on basis0", dcb01, basis[:, 0]),
]:
    b, se = reg(y, x)
    print(f"{name:40s} beta {b:+.3f} se {se:.3f} t {b/se:+.2f} corr {corr(x,y):+.3f}")
# tradeable check: when cb moved up >= th in 0-1 while jup lagged, what's jup move 1->5 (buy at jup quote at 1 s, value at jup 5s mid)?
for th in [0.5, 1, 2, 3]:
    gap = (dcb01 - djm01)
    sel = np.abs(gap) >= th
    sgn = np.sign(gap[sel])
    print(f"|cb0-1 minus jup0-1| >= {th} bps: n={sel.sum()}, mean signed jup 1-5 move {np.mean(sgn*djm15[sel]):+.3f} bps, se {np.std(sgn*djm15[sel])/np.sqrt(max(sel.sum(),1)):.3f}")
