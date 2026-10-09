import numpy as np, datetime as dt
D = np.load("dl/SOL_1m.npz"); m = D["m"]; c = D["c"]; lc = np.log(c) * 1e4
def ep(y, mo, d=1): return int(dt.datetime(y, mo, d, tzinfo=dt.timezone.utc).timestamp() // 60)
periods = {"train 2020-09..2023-12": (m[0], ep(2024, 1)), "valid 2024-01..2025-06": (ep(2024, 1), ep(2025, 7)), "test 2025-07..2026-09": (ep(2025, 7), m[-1] + 1)}
# hourly returns (close-to-close, hour h = return from h:00 to h+1:00)
hstart = (m % 60 == 0)
hidx = np.where(hstart)[0]; hidx = hidx[hidx + 60 < len(m)]
hret = lc[hidx + 60] - lc[hidx]; hour = (m[hidx] // 60) % 24; hm = m[hidx]
means = {}
for name, (a, b) in periods.items():
    sel = (hm >= a) & (hm < b)
    mu = np.array([hret[sel & (hour == h)].mean() for h in range(24)])
    se = np.array([hret[sel & (hour == h)].std() / np.sqrt((sel & (hour == h)).sum()) for h in range(24)])
    means[name] = mu
    print(name, "n days ~", (sel & (hour == 0)).sum())
    print("  hour mean bps:", " ".join(f"{h:02d}:{mu[h]:+.1f}" for h in range(24)))
    print("  |t|>2 hours:", [(h, round(mu[h] / se[h], 1)) for h in range(24) if abs(mu[h] / se[h]) > 2], " typical se %.1f" % se.mean())
from scipy.stats import spearmanr
k = list(means)
for i in range(3):
    for j in range(i + 1, 3):
        print(f"spearman hour-of-day means {k[i][:5]} vs {k[j][:5]}: {spearmanr(means[k[i]], means[k[j]]).correlation:+.2f}")
# Strategy "long the hours that were positive in train with t>?": evaluate in valid/test (sign rule)
tr = means[k[0]]
for name in k[1:]:
    a, b = periods[name]; sel = (hm >= a) & (hm < b)
    sgn = np.sign(tr)[hour[sel]]
    pnl = sgn * hret[sel] - 1.0  # 1 bps round trip per hour traded
    print(f"trade every hour in train-sign direction, {name}: mean {pnl.mean():+.2f} bps/h, se {pnl.std()/np.sqrt(len(pnl)):.2f}")
# funding windows: 5-min and 30-min return before/after 00/08/16 UTC
mod = m % 480  # minutes since last funding (00,08,16 UTC)
for name, (a, b) in periods.items():
    sel = (m >= a) & (m < b - 60)
    out = []
    for lo, hi, lab in [(-30, 0, "30m before"), (-5, 0, "5m before"), (0, 5, "5m after"), (0, 30, "30m after"), (0, 60, "60m after")]:
        idx = np.where(sel & (mod == (lo % 480)))[0]
        r = lc[idx + (hi - lo)] - lc[idx]
        out.append(f"{lab}: {r.mean():+.2f}±{r.std()/np.sqrt(len(r)):.2f}")
    print("funding", name[:5], " | ".join(out))
# minute of hour: first 5 minutes of each hour vs others
for name, (a, b) in periods.items():
    sel = (m >= a) & (m < b - 60)
    out = []
    for mm in [55, 58, 59, 0, 1, 2, 30]:
        idx = np.where(sel & (m % 60 == mm))[0]
        r = lc[idx + 1] - lc[idx]
        out.append(f"min{mm:02d}: {r.mean():+.2f}±{r.std()/np.sqrt(len(r)):.2f}")
    print("minute-of-hour 1m ret", name[:5], " | ".join(out))
# day of week, 24h close-to-close from 00 UTC
d0 = np.where(m % 1440 == 0)[0]; d0 = d0[d0 + 1440 < len(m)]
dr = lc[d0 + 1440] - lc[d0]; dow = ((m[d0] // 1440) + 3) % 7  # 1970-01-01 was Thursday -> 0=Mon
for name, (a, b) in periods.items():
    sel = (m[d0] >= a) & (m[d0] < b)
    print("dow", name[:5], " ".join(f"{['Mo','Tu','We','Th','Fr','Sa','Su'][d]}:{dr[sel & (dow==d)].mean():+.0f}" for d in range(7)), " se~%.0f" % (dr[sel].std() / np.sqrt(sel.sum() / 7)))
