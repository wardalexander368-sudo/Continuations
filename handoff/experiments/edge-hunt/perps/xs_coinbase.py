"""The registered momentum rules on Coinbase's US-listed coins, with Coinbase's own daily history (exploratory).

    python3 handoff/experiments/edge-hunt/perps/xs_coinbase.py DAILY_DIR

DAILY_DIR holds <COIN>.csv (day, close, USD volume) from Coinbase Exchange daily candles for the 23
crypto coins that have Coinbase US perps ("-CDE"). Spot history goes back to 2019-2021 for most,
so this gives ~4x the weeks Hyperliquid's data allows. Weekly, signal at Monday's close, executed
a day later (as D's registration); universe: 60 days of history and 30-day median volume >= $1M.
No new selection; the rules are the registered D (14-day return) and D3 (14-day return / std of
the last 14 daily returns), in two forms:
* long-short quintiles on US perps: cost 10 and 20 bps per side of turnover, funding not charged
  (Coinbase's US perp funding is hourly and small, ~+0.0008%/h today; on HL it cost D ~0.1%/week);
* long-only top quintile on US spot: 0.62% per side of turnover (Coinbase taker), against holding
  every universe coin equally (rebalanced weekly at the same cost) and against cash.
Splits: train 2020-01..2023-12, validation 2024, test 2025-01..2026-10. Weekly means with a 4-week
block bootstrap 90% CI. Caveat: today's list (look-ahead on which coins made it).
"""
from __future__ import annotations

import csv
import datetime as dt
import sys
from pathlib import Path

import numpy as np

D = Path(sys.argv[1])
SPLITS = {"train": ("2020-01-01", "2023-12-31"), "val": ("2024-01-01", "2024-12-31"), "test": ("2025-01-01", "2026-10-31")}
data = {f.stem: {r[0]: (float(r[1]), float(r[2])) for r in csv.reader(f.open())} for f in D.glob("*.csv")}
days = sorted(set().union(*data.values()))
coins = sorted(data)
ix = {d: i for i, d in enumerate(days)}
C = np.full((len(days), len(coins)), np.nan); V = np.full_like(C, np.nan)
for j, c in enumerate(coins):
    for d, (cl, v) in data[c].items():
        C[ix[d], j], V[ix[d], j] = cl, v
R = np.vstack([np.full((1, len(coins)), np.nan), C[1:] / C[:-1] - 1])
wd = np.array([dt.date.fromisoformat(d).weekday() for d in days])
MON = [i for i in range(60, len(days) - 8) if wd[i] == 0]


def universe(i):
    return ~np.isnan(C[i - 59: i + 1]).any(0) & (np.nanmedian(V[i - 29: i + 1], 0) >= 1e6)


def sig_mom(i):
    return C[i] / C[i - 14] - 1


def sig_vmom(i):
    return (C[i] / C[i - 14] - 1) / np.nanstd(R[i - 13: i + 1], axis=0)


def book(sig, i, mode):
    ok = universe(i) & np.isfinite(sig)
    ids = np.where(ok)[0]
    if len(ids) < 10:
        return None
    o = ids[np.argsort(sig[ids])]; q = len(o) // 5
    if mode == "ls":
        return {**{c: 1 / q for c in o[-q:]}, **{c: -1 / q for c in o[:q]}}
    if mode == "top":
        return {c: 1 / q for c in o[-q:]}
    return {c: 1 / len(ids) for c in ids}  # "all"


def run(sigfn, mode, cost):
    out, prev = [], {}
    for k, i in enumerate(MON[:-1]):
        j = MON[k + 1]
        w = book(sigfn(i), i, mode)
        if w is None:
            prev = {}; continue
        a, b = i + 1, j + 1  # executed a day after the signal
        r = sum(wt * (C[b, c] / C[a, c] - 1) for c, wt in w.items() if not np.isnan(C[b, c]) and not np.isnan(C[a, c]))
        turn = sum(abs(w.get(c, 0) - prev.get(c, 0)) for c in set(w) | set(prev))
        if mode == "ls":
            turn /= 2
        prev = w
        out.append((days[i], r - (2 if mode == "ls" else 1) * cost * turn))
    return out


def stats(rs):
    x = np.array([r for _, r in rs])
    if len(x) < 8:
        return np.nan, (np.nan, np.nan), len(x)
    rng = np.random.default_rng(1); B = 4
    bs = [x[np.concatenate([np.arange(s, s + B) % len(x) for s in rng.integers(0, len(x), len(x) // B + 1)])[: len(x)]].mean() for _ in range(4000)]
    return x.mean(), tuple(np.percentile(bs, [5, 95])), len(x)


def line(name, rs):
    parts = []
    for s, (a, b) in SPLITS.items():
        m, ci, n = stats([x for x in rs if a <= x[0] <= b])
        parts.append(f"{s} {m * 100:+.2f}%/wk [{ci[0] * 100:+.2f},{ci[1] * 100:+.2f}] n{n}")
    print(f"  {name:34s} " + "  ".join(parts))


if __name__ == "__main__":
    print(f"{len(coins)} coins, {days[0]}..{days[-1]}")
    for cost in (0.0010, 0.0020):
        line(f"D  long-short perps {cost * 1e4:g}bp", run(sig_mom, "ls", cost))
        line(f"D3 long-short perps {cost * 1e4:g}bp", run(sig_vmom, "ls", cost))
    line("D  long-only top quintile spot", run(sig_mom, "top", 0.0062))
    line("D3 long-only top quintile spot", run(sig_vmom, "top", 0.0062))
    line("hold all coins equally spot", run(sig_mom, "all", 0.0062))
