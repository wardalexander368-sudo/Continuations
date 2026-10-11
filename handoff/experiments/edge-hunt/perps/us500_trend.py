"""Trend timing on the S&P 500 as a stand-in for Coinbase's US500 perp (exploratory).

    python3 handoff/experiments/edge-hunt/perps/us500_trend.py SPX_CHART_JSON   # Yahoo chart JSON of ^GSPC, daily

Coinbase's US500 perp (launched 2026-08, ~1 bp promo fee) tracks the S&P 500 price index. Rules on
daily closes, signal at the close, position from the next close (1-day lag), 3 bps per switch:
long when the close is above its N-day average (N = 50, 100, 200) or the 252-day return is positive,
else flat (4 rules) or short (4 rules). Measured against holding the index: daily return of the rule
minus the index's, in % a year, 90% CI by 20-day block bootstrap. Funding and collateral interest are
left out of both sides (they roughly cancel against holding). Splits: train 1950-1999, validation
2000-2012, test 2013-2026. The rule is chosen on train; test is read only if validation agrees.
"""
import datetime as dt
import json
import sys

import numpy as np

d = json.load(open(sys.argv[1]))["chart"]["result"][0]
t = np.array(d["timestamp"]); c = np.array(d["indicators"]["quote"][0]["close"], dtype=float)
ok = ~np.isnan(c); t, c = t[ok], c[ok]
days = np.array([dt.datetime.fromtimestamp(x, dt.timezone.utc).date().isoformat() for x in t])
r = np.concatenate([[0], c[1:] / c[:-1] - 1])
SPLITS = {"train": ("1950-01-01", "1999-12-31"), "val": ("2000-01-01", "2012-12-31"), "test": ("2013-01-01", "2026-12-31")}


def signal(kind, n):
    s = np.zeros(len(c))
    if kind == "MA":
        ma = np.convolve(c, np.ones(n) / n, "full")[: len(c)]
        s[n:] = c[n:] > ma[n:]
    else:
        s[n:] = c[n:] > c[:-n]
    return s


def run(kind, n, short):
    s = signal(kind, n)
    pos = np.where(s > 0, 1.0, -1.0 if short else 0.0)
    pos[: n + 1] = 1.0
    held = np.concatenate([[1.0], pos[:-1]])  # yesterday's signal held today
    sw = np.abs(np.diff(np.concatenate([[1.0], held])))
    return held * r - 0.0003 * sw - r  # rule minus holding


def stats(x):
    rng = np.random.default_rng(1); B = 20; n = len(x)
    bs = [x[np.concatenate([np.arange(s, s + B) % n for s in rng.integers(0, n, n // B + 1)])[:n]].mean() for _ in range(2000)]
    lo, hi = np.percentile(bs, [5, 95])
    return x.mean() * 252, lo * 252, hi * 252


def part(x, s):
    a, b = SPLITS[s]
    m = (days >= a) & (days <= b)
    return x[m]


res = []
for short in (False, True):
    for kind, n in (("MA", 50), ("MA", 100), ("MA", 200), ("TS", 252)):
        x = run(kind, n, short)
        name = f"{kind}{n} {'long/short' if short else 'long/flat'}"
        tr, va = stats(part(x, "train")), stats(part(x, "val"))
        res.append((name, x, tr, va))
        print(f"  {name:20s} vs holding: train {tr[0] * 100:+.2f}%/yr [{tr[1] * 100:+.2f},{tr[2] * 100:+.2f}]  val {va[0] * 100:+.2f}% [{va[1] * 100:+.2f},{va[2] * 100:+.2f}]")
name, x, tr, va = max(res, key=lambda z: z[2][0])
if tr[0] > 0 and va[0] > 0:
    te = stats(part(x, "test"))
    print(f"-> chosen {name}: TEST {te[0] * 100:+.2f}%/yr [{te[1] * 100:+.2f},{te[2] * 100:+.2f}] vs holding")
else:
    print(f"-> chosen {name}: validation disagrees or train <= 0; test not read")
print("rules tried: 8")
