"""Chart patterns on a US venue, entered ~30 minutes after the signal candle (exploratory).

    python3 handoff/experiments/edge-hunt/patterns/patterns.py CACHE_DIR [--cost 0.0062] [--delay-bars 2]

Coinbase 15-minute candles (fetch_coinbase.py) for 11 coins are rolled into hourly bars. A signal
is read at an hourly close; the agent runs once an hour and starts 14-26 minutes after it, so the
entry is the close of the 15-minute bar ending 30 minutes after the signal (--delay-bars 2; 1 = 15
minutes), and the exit is the same delay after the exit hour. Spot is long only. Cost per side
default 0.62% (Coinbase Exchange's published taker fee below $10k a month, 0.60%, plus ~2 bps of
spread; Kraken's lowest tier is worse, 0.80%); --cost 0.0042 for maker-only. One position per coin
at a time. Splits by entry day: train 2020-01..2023-12, validation 2024, test 2025-01..2026-10;
mean return per trade, 90% CI by bootstrap over days. Each family's rule is chosen on train;
test is read only if validation agrees. Every rule is counted.

Families (sigma = std of the previous 168 hourly returns):
* WICK     lower wick >= Z sigma (the registered HL rule's long half), hold H hours
* BREAKOUT close above the highest high of the previous N hours, hold H
* VOLSPIKE hourly volume >= K x its 7-day mean and the hour closed up >= 1 sigma, hold H
* CAPIT    capitulation: 24-hour return <= -Z sigma*sqrt(24), hold H
* OVERSOLD 14-hour RSI falls below X, hold H
* SQUEEZE  20-hour Bollinger width in the lowest P% of the last 90 days, then a close above the
           upper band, hold H
"""
from __future__ import annotations

import csv
import datetime as dt
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np

D = Path(sys.argv[1])
COST = float(sys.argv[sys.argv.index("--cost") + 1]) if "--cost" in sys.argv else 0.0062
DELAY = int(sys.argv[sys.argv.index("--delay-bars") + 1]) if "--delay-bars" in sys.argv else 2
SPLITS = {"train": ("2020-01-01", "2023-12-31"), "val": ("2024-01-01", "2024-12-31"), "test": ("2025-01-01", "2026-10-31")}
COINS = ["BTC", "ETH", "SOL", "XRP", "DOGE", "ADA", "AVAX", "LINK", "LTC", "BCH", "DOT"]


def load(coin):
    rows = [list(map(float, r)) for r in csv.reader((D / f"{coin}.csv").open())]
    t = np.array([r[0] for r in rows], dtype=np.int64)
    q0 = t[0] // 3600 * 3600
    n = (t[-1] - q0) // 900 + 1
    a = np.full((n, 5), np.nan)
    a[(t - q0) // 900] = np.array([r[1:6] for r in rows])
    return q0, a  # 15m bars: open high low close volume


DATA = {}
for c in COINS:
    if not (D / f"{c}.csv").exists():
        continue
    q0, a = load(c)
    nh = len(a) // 4
    b = a[: nh * 4].reshape(nh, 4, 5)
    with np.errstate(all="ignore"):
        O, Hh, L, C, V = b[:, 0, 0], np.nanmax(b[:, :, 1], 1), np.nanmin(b[:, :, 2], 1), b[:, 3, 3], np.nansum(b[:, :, 4], 1)
    bad = np.isnan(b[:, :, 3]).any(1)
    O[bad] = Hh[bad] = L[bad] = C[bad] = np.nan
    C15 = a[:, 3]
    days = np.array([dt.datetime.fromtimestamp(q0 + 3600 * i, dt.timezone.utc).date().isoformat() for i in range(nh)])
    R = np.full(nh, np.nan); R[1:] = C[1:] / C[:-1] - 1
    s = np.full(nh, np.nan)
    for i in range(169, nh):
        w = R[i - 168: i]
        if not np.isnan(w).any():
            s[i] = w.std()
    DATA[c] = dict(O=O, H=Hh, L=L, C=C, V=V, C15=C15, days=days, R=R, S=s, n=nh)
print(f"{len(DATA)} coins; cost {COST * 100:.2f}%/side; entry {15 * DELAY} min after the signal close")


def run(sigfn, hold):
    out = []
    for c, d in DATA.items():
        sig = sigfn(d)
        busy = -1
        for i in np.nonzero(sig)[0]:
            # signal at the close of hour i (bar i ends at 15m index 4(i+1)); entry DELAY 15m bars later
            e, x = 4 * (i + 1) + DELAY - 1, 4 * (i + 1 + hold) + DELAY - 1
            if i < busy or x >= len(d["C15"]) or np.isnan(d["C15"][e]) or np.isnan(d["C15"][x]):
                continue
            out.append((d["days"][i], d["C15"][x] / d["C15"][e] - 1 - 2 * COST))
            busy = i + hold + 1
    return out


def wick(Z):
    return lambda d: (np.minimum(d["O"], d["C"]) - d["L"]) / d["O"] >= Z * d["S"]


def breakout(N):
    def f(d):
        hh = np.full(d["n"], np.nan)
        H = d["H"]
        for i in range(N, d["n"]):
            hh[i] = np.nanmax(H[i - N: i])
        return d["C"] > hh
    return f


def volspike(K):
    def f(d):
        V = np.nan_to_num(d["V"]); cs = np.concatenate([[0], np.cumsum(V)])
        m = np.full(d["n"], np.nan); i = np.arange(168, d["n"]); m[i] = (cs[i] - cs[i - 168]) / 168
        return (d["V"] >= K * m) & (d["R"] >= d["S"])
    return f


def capit(Z):
    def f(d):
        r24 = np.full(d["n"], np.nan); r24[24:] = d["C"][24:] / d["C"][:-24] - 1
        return r24 <= -Z * d["S"] * np.sqrt(24)
    return f


def oversold(X):
    def f(d):
        R = np.nan_to_num(d["R"]); up, dn = np.maximum(R, 0), np.maximum(-R, 0)
        rsi = np.full(d["n"], np.nan); au = ad = None
        for i in range(1, d["n"]):
            if au is None:
                if i >= 14:
                    au, ad = up[i - 13: i + 1].mean(), dn[i - 13: i + 1].mean()
                continue
            au, ad = (13 * au + up[i]) / 14, (13 * ad + dn[i]) / 14
            rsi[i] = 100 - 100 / (1 + au / ad) if ad > 0 else 100
        prev = np.concatenate([[np.nan], rsi[:-1]])
        return (rsi < X) & (prev >= X)
    return f


def squeeze(P):
    def f(d):
        C = d["C"]; n = d["n"]
        m = np.full(n, np.nan); sd = np.full(n, np.nan)
        for i in range(20, n):
            w = C[i - 19: i + 1]; m[i], sd[i] = w.mean(), w.std()
        bw = 4 * sd / m
        out = np.zeros(n, bool)
        for i in range(2160, n):
            past = bw[i - 2160: i]; past = past[~np.isnan(past)]
            if len(past) > 1000 and not np.isnan(bw[i - 1]) and bw[i - 1] <= np.percentile(past, P) and C[i] > m[i] + 2 * sd[i]:
                out[i] = True
        return out
    return f


def stats(tr):
    if len(tr) < 15:
        return np.nan, (np.nan, np.nan), len(tr)
    by = defaultdict(list)
    for d, r in tr:
        by[d].append(r)
    k = list(by); s = np.array([sum(by[x]) for x in k]); n = np.array([len(by[x]) for x in k])
    pick = np.random.default_rng(1).integers(0, len(k), (3000, len(k)))
    bs = s[pick].sum(1) / n[pick].sum(1)
    return float(np.mean([r for _, r in tr])), tuple(np.percentile(bs, [5, 95])), len(tr)


def split(tr, s):
    a, b = SPLITS[s]
    return [x for x in tr if a <= x[0] <= b]


def fmt(t):
    m, ci, n = t
    return f"{m * 100:+.2f}% [{ci[0] * 100:+.2f},{ci[1] * 100:+.2f}] n{n}" if n >= 15 else f"- n{n}"


FAMILIES = {
    "WICK": [(f"Z={Z} H={h}", wick(Z), h) for Z in (4, 6) for h in (4, 24)],
    "BREAKOUT": [(f"N={N} H={h}", breakout(N), h) for N in (72, 168) for h in (24, 72)],
    "VOLSPIKE": [(f"K={K} H={h}", volspike(K), h) for K in (5, 10) for h in (24, 72)],
    "CAPIT": [(f"Z={Z} H={h}", capit(Z), h) for Z in (3, 4) for h in (24, 72)],
    "OVERSOLD": [(f"X={X} H={h}", oversold(X), h) for X in (20, 15) for h in (24, 72)],
    "SQUEEZE": [(f"P={P} H={h}", squeeze(P), h) for P in (5, 10) for h in (24, 72)],
}
if __name__ == "__main__":
    n_rules = 0
    for fam, rules in FAMILIES.items():
        res = []
        for name, fn, h in rules:
            tr = run(fn, h)
            n_rules += 1
            a, b = stats(split(tr, "train")), stats(split(tr, "val"))
            res.append((name, tr, a, b))
            print(f"  {fam:8s} {name:10s} train {fmt(a)}  val {fmt(b)}", flush=True)
        name, tr, a, b = max(res, key=lambda x: x[2][0] if not np.isnan(x[2][0]) else -9)
        if a[0] > 0 and b[0] > 0:
            print(f"  -> {fam} chosen {name}: TEST {fmt(stats(split(tr, 'test')))}", flush=True)
        else:
            print(f"  -> {fam} chosen {name}: validation disagrees or train <= 0; test not read", flush=True)
    print(f"rules tried: {n_rules}")
