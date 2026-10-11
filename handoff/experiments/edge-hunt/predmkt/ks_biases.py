"""Favourite-longshot pricing on Kalshi (US, CFTC-regulated), after its fee and the spread (exploratory).

    python3 handoff/experiments/edge-hunt/predmkt/ks_biases.py CACHE_DIR    # from fetch_kalshi.py

Entry K hours before a market's close, at that hour's closing quote: buying YES pays the yes ask,
buying NO pays 1 - yes bid (so the spread is paid). Kalshi's taker fee is 0.07 x price x (1 - price)
per contract (rounded up per order, ignored here: it matters only for tiny orders). Held to
settlement: return per $ = win / q - 1 - fee / q. Quotes older than 2 hours, or a missing side,
skip the market.
Rules: FAV (buy the side priced in [.5,.7) [.7,.85) [.85,.95) [.95,.99)) and LONG (buy the side
priced in (.01,.05] (.05,.15] (.15,.3] (.3,.5)), K = 2, 6, 24 hours: 24 rules. Splits by close date
(set from the data: train = first 60%, validation = next 20%, test = last 20% of days). Mean
return per $ staked, 90% CI by bootstrap over events. Each family's rule chosen on train (>= 100
trades), test read only if validation agrees.
"""
from __future__ import annotations

import json
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np

cache = Path(sys.argv[1])
markets = []
for l in (cache / "markets.jsonl").read_text().splitlines():
    m = json.loads(l)
    f = cache / "candles" / f"{m['t']}.json"
    if not f.exists():
        continue
    cs = json.loads(f.read_text())
    if not cs:
        continue
    m["c"] = cs
    m["day"] = m["close"][:10]
    markets.append(m)
days = sorted({m["day"] for m in markets})
cut1, cut2 = days[int(len(days) * 0.6)], days[int(len(days) * 0.8)]
SPLITS = {"train": (days[0], cut1), "val": (cut1, cut2), "test": (cut2, "9999")}
print(f"{len(markets)} markets with candles, {days[0]}..{days[-1]}; train <{cut1}, val <{cut2}, test after")


def quote(m, k):
    import datetime as dt
    end = dt.datetime.fromisoformat(m["close"].replace("Z", "+00:00")).timestamp()
    te = end - k * 3600
    best = None
    for ts, bid, ask, last, vol in m["c"]:
        if te - 7200 <= ts <= te:
            best = (bid, ask)
    if not best or best[0] is None or best[1] is None:
        return None
    bid, ask = float(best[0]), float(best[1])
    if not (0 < bid < ask < 1):
        return None
    return bid, ask


def trades(fam, lo, hi, k):
    out = []
    for m in markets:
        q = quote(m, k)
        if q is None:
            continue
        bid, ask = q
        for side_yes, price in ((True, ask), (False, 1 - bid)):
            inband = (lo <= price < hi) if fam == "FAV" else (lo < price <= hi)
            if not inband:
                continue
            win = (m["res"] == "yes") == side_yes
            fee = 0.07 * price * (1 - price)
            out.append((m["day"], m["e"], (1.0 if win else 0.0) / price - 1 - fee / price, m["s"]))
    return out


def stats(tr):
    if len(tr) < 20:
        return np.nan, (np.nan, np.nan), len(tr)
    by = defaultdict(list)
    for _, e, r, _ in tr:
        by[e].append(r)
    k = list(by); s = np.array([sum(by[x]) for x in k]); n = np.array([len(by[x]) for x in k])
    pick = np.random.default_rng(1).integers(0, len(k), (3000, len(k)))
    bs = s[pick].sum(1) / n[pick].sum(1)
    return float(np.mean([x[2] for x in tr])), tuple(np.percentile(bs, [5, 95])), len(tr)


def split(tr, s):
    a, b = SPLITS[s]
    return [x for x in tr if a <= x[0] < b]


def fmt(t):
    m, ci, n = t
    return f"{m * 100:+.2f}% [{ci[0] * 100:+.2f},{ci[1] * 100:+.2f}] n{n}" if n >= 20 else f"- n{n}"


FAMILIES = {
    "FAV": [((.5, .7), k) for k in (2, 6, 24)] + [((.7, .85), k) for k in (2, 6, 24)] + [((.85, .95), k) for k in (2, 6, 24)] + [((.95, .99), k) for k in (2, 6, 24)],
    "LONG": [((.01, .05), k) for k in (2, 6, 24)] + [((.05, .15), k) for k in (2, 6, 24)] + [((.15, .3), k) for k in (2, 6, 24)] + [((.3, .5), k) for k in (2, 6, 24)],
}
n_rules = 0
for fam, rules in FAMILIES.items():
    res = []
    for (lo, hi), k in rules:
        tr = trades(fam, lo, hi, k)
        n_rules += 1
        a, b = stats(split(tr, "train")), stats(split(tr, "val"))
        res.append(((lo, hi, k), tr, a, b))
        print(f"  {fam:4s} band {lo:.2f}-{hi:.2f} K={k:2d}h  train {fmt(a)}  val {fmt(b)}", flush=True)
    cand = [x for x in res if x[2][2] >= 100]
    key, tr, a, b = max(cand, key=lambda x: x[2][0])
    if a[0] > 0 and b[0] > 0:
        te = split(tr, "test")
        print(f"  -> {fam} chosen {key}: TEST {fmt(stats(te))}", flush=True)
        by = defaultdict(list)
        for x in te:
            by[x[3]].append(x[2])
        print("     test by series: " + ", ".join(f"{s} {np.mean(v) * 100:+.1f}% n{len(v)}" for s, v in sorted(by.items())))
    else:
        print(f"  -> {fam} chosen {key}: validation disagrees or train <= 0; test not read", flush=True)
print(f"rules tried: {n_rules}")
