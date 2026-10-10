"""Intraday timing rules on liquid perps (trading-skills thread, round 4), exploratory.

    python3 handoff/experiments/edge-hunt/perps/intraday.py DIR_OF_BINANCE_1H_ZIPS [--cost-bps 8.5]

Hourly Binance spot klines (data.binance.vision monthly 1h zips) for 20 coins that are liquid
Hyperliquid perps stand in for HL prices (HL's own candle API keeps only ~5,000 bars). Cost per
side: 8.5 bps by default (HL taker 4.5 bps + ~4 bps to fill $5k on a typical coin, measured by the
Jev cost session from 92 HL books on 2026-10-10); run again with --cost-bps 1.5 for maker-only
(HL's base maker fee, and assumes every passive order fills, which flatters it). Funding ignored
(holds are hours). Splits by entry day: train 2020-01..2023-12, validation 2024, test
2025-01..2026-09; mean return per trade, 90% CI by bootstrap over days.

Families (every rule counted; one position per coin at a time):
* BIG    after an hourly close-to-close move of at least Z sigma (sigma = std of the previous 168
         hourly returns), enter at that close against the move (REV) or with it (MOM), hold H hours.
* WICK   after an hour whose lower (upper) wick is at least Z sigma of price, go long (short) at
         the close (the bounce continues, "BOUNCE") or the other way ("FADE"), hold H hours.
* HOD    BTC, ETH, SOL equal weight: hold through each UTC hour whose train-period mean return has
         |t| > 2, in its sign (Binance funding hours 00/08/16 included). One composite rule.
"""
from __future__ import annotations

import csv
import datetime as dt
import io
import sys
import zipfile
from collections import defaultdict
from pathlib import Path

import numpy as np

D = Path(sys.argv[1])
COST = float(sys.argv[sys.argv.index("--cost-bps") + 1]) / 1e4 if "--cost-bps" in sys.argv else 0.00085
SPLITS = {"train": ("2020-01-01", "2023-12-31"), "val": ("2024-01-01", "2024-12-31"), "test": ("2025-01-01", "2026-09-30")}

raw = defaultdict(dict)
for f in sorted(D.glob("*.zip")):
    sym = f.name.split("-")[0].removesuffix("USDT")
    with zipfile.ZipFile(f) as z:
        for row in csv.reader(io.TextIOWrapper(z.open(z.namelist()[0]))):
            if not row[0].isdigit():
                continue
            t = int(row[0])
            t = t // 1_000_000 if t > 1e14 else t // 1000
            raw[sym][t // 3600] = tuple(float(x) for x in row[1:5])
h0 = min(min(v) for v in raw.values()); h1 = max(max(v) for v in raw.values())
H = h1 - h0 + 1
coins = sorted(raw)
O, Hi, Lo, C = (np.full((len(coins), H), np.nan) for _ in range(4))
for j, c in enumerate(coins):
    for h, (o, hi, lo, cl) in raw[c].items():
        O[j, h - h0], Hi[j, h - h0], Lo[j, h - h0], C[j, h - h0] = o, hi, lo, cl
day = np.array([dt.datetime.fromtimestamp((h0 + i) * 3600, dt.timezone.utc).date().isoformat() for i in range(H)])
hour = (np.arange(H) + h0) % 24
R = np.full_like(C, np.nan); R[:, 1:] = C[:, 1:] / C[:, :-1] - 1
# trailing std of the previous 168 hourly returns (cumulative sums, NaN-safe enough: windows with gaps are dropped)
SIG = np.full_like(C, np.nan)
for j in range(len(coins)):
    r = R[j]
    ok = ~np.isnan(r)
    x = np.where(ok, r, 0.0); n = ok.astype(float)
    cs, cs2, cn = (np.concatenate([[0], np.cumsum(a)]) for a in (x, x * x, n))
    i = np.arange(168, H)
    s, s2, k = cs[i] - cs[i - 168], cs2[i] - cs2[i - 168], cn[i] - cn[i - 168]
    v = np.where(k == 168, s2 / 168 - (s / 168) ** 2, np.nan)
    SIG[j, i] = np.sqrt(np.maximum(v, 0))  # std of R[i-168 .. i-1]
print(f"{len(coins)} coins, {H} hours, cost {COST * 1e4:g} bps/side")


def run(signal, hold):
    """signal(j) -> array of +1/-1/0 per hour (decided at that hour's close). One position per coin."""
    out = []
    for j in range(len(coins)):
        s = signal(j)
        i, last = 0, H - hold - 1
        for i in np.nonzero(s)[0]:
            if i <= last and i >= 0 and not np.isnan(C[j, i + hold]) and not np.isnan(C[j, i]):
                if out and out[-1][2] == j and i < out[-1][3]:
                    continue
                r = s[i] * (C[j, i + hold] / C[j, i] - 1) - 2 * COST
                out.append((day[i], r, j, i + hold))
    return [(d, r) for d, r, _, _ in out]


def big(Z, hold, sign):
    def sig(j):
        z = R[j] / SIG[j]
        return np.where(np.abs(z) >= Z, -np.sign(z) * sign, 0).astype(int)
    return run(sig, hold)


def wick(Z, hold, sign):
    def sig(j):
        lw = (np.minimum(O[j], C[j]) - Lo[j]) / O[j] / SIG[j]
        uw = (Hi[j] - np.maximum(O[j], C[j])) / O[j] / SIG[j]
        s = np.where(lw >= Z, 1, 0) - np.where(uw >= Z, 1, 0)
        return (s * sign).astype(int)
    return run(sig, hold)


def hod():
    maj = [coins.index(c) for c in ("BTC", "ETH", "SOL")]
    m = np.nanmean(R[maj], axis=0)
    tr = (day >= SPLITS["train"][0]) & (day <= SPLITS["train"][1])
    sign = np.zeros(24)
    for h in range(24):
        x = m[tr & (hour == h)]; x = x[~np.isnan(x)]
        t = x.mean() / (x.std() / np.sqrt(len(x)))
        sign[h] = np.sign(t) if abs(t) > 2 else 0
    print("  HOD hours traded (UTC, sign):", {h: int(sign[h]) for h in range(24) if sign[h]})
    out = []
    for i in range(1, H):
        s = sign[hour[i]]
        if s and not np.isnan(m[i]):
            out.append((day[i - 1], s * m[i] - 2 * COST))  # entered at the previous hour's close
    return out


def stats(tr):
    if len(tr) < 20:
        return np.nan, (np.nan, np.nan), len(tr)
    by = defaultdict(list)
    for d, r in tr:
        by[d].append(r)
    keys = list(by)
    s = np.array([sum(by[k]) for k in keys]); n = np.array([len(by[k]) for k in keys])
    pick = np.random.default_rng(1).integers(0, len(keys), (3000, len(keys)))
    bs = s[pick].sum(axis=1) / n[pick].sum(axis=1)
    return float(np.mean([r for _, r in tr])), tuple(np.percentile(bs, [5, 95])), len(tr)


def split(tr, s):
    a, b = SPLITS[s]
    return [x for x in tr if a <= x[0] <= b]


def fmt(t):
    m, ci, n = t
    return f"{m * 1e4:+.1f}bp [{ci[0] * 1e4:+.1f},{ci[1] * 1e4:+.1f}] n{n}" if n >= 20 else f"- n{n}"


FAMILIES = {
    "BIG": [(f"{nm} Z={Z} H={h}", lambda Z=Z, h=h, s=s: big(Z, h, s)) for nm, s in (("REV", 1), ("MOM", -1)) for Z in (3, 4, 6) for h in (1, 4, 12)],
    "WICK": [(f"{nm} Z={Z} H={h}", lambda Z=Z, h=h, s=s: wick(Z, h, s)) for nm, s in (("BOUNCE", 1), ("FADE", -1)) for Z in (3, 6) for h in (1, 4)],
    "HOD": [("composite", hod)],
}
n_rules = 0
for fam, rules in FAMILIES.items():
    res = []
    for name, fn in rules:
        tr = fn()
        n_rules += 1
        a, b = stats(split(tr, "train")), stats(split(tr, "val"))
        res.append((name, tr, a, b))
        print(f"  {fam:4s} {name:18s} train {fmt(a)}  val {fmt(b)}", flush=True)
    name, tr, a, b = max(res, key=lambda x: x[2][0] if not np.isnan(x[2][0]) else -9)
    if a[0] > 0 and b[0] > 0:
        print(f"  -> {fam} chosen {name}: TEST {fmt(stats(split(tr, 'test')))}", flush=True)
    else:
        print(f"  -> {fam} chosen {name}: validation disagrees or train <= 0; test not read", flush=True)
print(f"rules tried: {n_rules}")
