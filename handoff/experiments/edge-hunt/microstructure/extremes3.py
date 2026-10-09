import numpy as np, datetime as dt
exec(open("extremes2.py").read().split("grid = list")[0])
from scipy.stats import trim_mean
def show(k, th, side, H, skip=0):
    for name, (a, b) in P.items():
        ii, pnl = events(k, th, side, skip, H, a, b)
        miss = np.array([(~present[i - k:i + skip + H + 1]).sum() for i in ii])
        print(f"  {name}: n={len(pnl)} mean {pnl.mean():+.1f} median {np.median(pnl):+.1f} trim10% {trim_mean(pnl, 0.1):+.1f} | w/o top3 {np.sort(pnl)[:-3].mean():+.1f} | events touching missing minutes: {np.sum(miss>0)}")
print("k=30 z>=5 down H=60:"); show(30, 5, "down", 60)
print("k=30 z>=4 down H=30:"); show(30, 4, "down", 30)
print("k=30 z>=3 down H=30:"); show(30, 3, "down", 30)
print("k=15 z>=4 down H=30:"); show(15, 4, "down", 30)
ii, pnl = events(30, 5, "down", 0, 60, *P["test"])
o = np.argsort(pnl)
print("test top/bottom contributors (k30 z5 down H60):")
for j in list(o[-5:][::-1]) + list(o[:3]):
    i = ii[j]; print("   ", dt.datetime.fromtimestamp(int(m[i]) * 60, dt.timezone.utc).strftime("%Y-%m-%d %H:%M"), f"drop30m {lc[i]-lc[i-30]:+.0f} bps, vol {vol[i]:.1f}, fwd net {pnl[j]:+.0f}, price {np.exp(lc[i]/1e4):.2f}")
