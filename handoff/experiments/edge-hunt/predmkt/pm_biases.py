"""Favourite-longshot bias and late drift on resolved Polymarket markets (exploratory).

    python3 handoff/experiments/edge-hunt/predmkt/pm_biases.py CACHE_DIR [--cost 0.01]

Markets and daily prices from fetch_polymarket.py. Entry time = the market's scheduled end date
minus k days (known in advance; a market that closed before then is skipped), at the last daily
price at or before it. Buying one side at price q pays 1 if it wins: return per $ = win / q - 1
- cost / q, cost = half-spread + fees per share (default 1 cent; markets with fees enabled pay
1 cent more). Held to resolution.

Rules:
* FAV  buy the favourite when its price is in a band ([.5,.7) [.7,.85) [.85,.95) [.95,.99)), k = 1/7/30 days
* LONG buy the underdog in the mirrored bands (prices (.01,.05] (.05,.15] (.15,.3] (.3,.5)), same k
* DRIFT buy the side whose price rose by >= d (0.05/0.10/0.20) over the 7 days before entry, k = 1/7/30
Splits by scheduled end date: train 2023-01..2025-06, validation 2025-07..12, test 2026-01..09 (few markets before 2025).
Mean return per $ staked, 90% CI by bootstrap over events (markets in one event are correlated).
Each family's rule chosen on train (at least 100 trades), test read only if validation agrees.
"""
from __future__ import annotations

import datetime as dt
import json
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np

cache = Path(sys.argv[1])
COST = float(sys.argv[sys.argv.index("--cost") + 1]) if "--cost" in sys.argv else 0.01
SPLITS = {"train": ("2023-01-01", "2025-06-30"), "val": ("2025-07-01", "2025-12-31"), "test": ("2026-01-01", "2026-09-30")}


def ts(s):
    if not s:
        return None
    s = s.replace("Z", "+00:00").replace(" ", "T")
    if len(s) >= 3 and s[-3] != ":" and ("+" in s[10:] or "-" in s[10:]):
        s = s + ":00"
    try:
        return dt.datetime.fromisoformat(s).timestamp()
    except ValueError:
        return None


markets = []
for line in (cache / "markets.jsonl").read_text().splitlines():
    m = json.loads(line)
    f = cache / "hist" / f"{m['id']}.json"
    if not f.exists():
        continue
    h = json.loads(f.read_text())
    end, closed = ts(m["end"]), ts(m["closed"])
    if not h or end is None:
        continue
    m["t"] = np.array([x["t"] for x in h], float)
    m["p"] = np.array([x["p"] for x in h], float)
    m["end_t"], m["closed_t"] = end, closed or end
    m["end_day"] = m["end"][:10]
    markets.append(m)
print(f"{len(markets)} markets with history; cost {COST} per share")


def entry(m, k):
    """(yes price at entry, yes price 7 days before) or None."""
    te = m["end_t"] - k * 86400
    if te >= m["closed_t"]:
        return None
    i = int(np.searchsorted(m["t"], te, side="right")) - 1
    if i < 0 or m["t"][i] < te - 2 * 86400:
        return None
    j = int(np.searchsorted(m["t"], te - 7 * 86400, side="right")) - 1
    return m["p"][i], (m["p"][j] if j >= 0 else np.nan)


def ret(m, side_yes, q):
    win = m["yes_won"] if side_yes else not m["yes_won"]
    c = COST + (0.01 if m.get("fees") else 0.0)
    return (1.0 if win else 0.0) / q - 1 - c / q


def trades(rule):
    out = []
    for m in markets:
        e = entry(m, rule["k"])
        if e is None:
            continue
        p, p7 = e
        if not (0.005 < p < 0.995):
            continue
        fam = rule["fam"]
        if fam in ("FAV", "LONG"):
            lo, hi = rule["band"]
            for side_yes, q in ((True, p), (False, 1 - p)):
                if lo <= q < hi:
                    out.append((m["end_day"], m["event"] or m["id"], ret(m, side_yes, q)))
        else:
            d = rule["d"]
            if np.isnan(p7):
                continue
            if p - p7 >= d:
                out.append((m["end_day"], m["event"] or m["id"], ret(m, True, p)))
            elif p7 - p >= d:
                out.append((m["end_day"], m["event"] or m["id"], ret(m, False, 1 - p)))
    return out


def stats(tr):
    if len(tr) < 20:
        return np.nan, (np.nan, np.nan), len(tr)
    by = defaultdict(list)
    for _, e, r in tr:
        by[e].append(r)
    keys = list(by)
    sums = np.array([sum(by[k]) for k in keys]); cnt = np.array([len(by[k]) for k in keys])
    rng = np.random.default_rng(1)
    pick = rng.integers(0, len(keys), (3000, len(keys)))
    means = sums[pick].sum(axis=1) / cnt[pick].sum(axis=1)
    return float(np.mean([r for _, _, r in tr])), tuple(np.percentile(means, [5, 95])), len(tr)


def split(tr, s):
    a0, a1 = SPLITS[s]
    return [x for x in tr if a0 <= x[0] <= a1]


def fmt(t):
    m, ci, n = t
    return f"{m * 100:+.2f}% [{ci[0] * 100:+.2f},{ci[1] * 100:+.2f}] n{n}" if n >= 20 else f"- n{n}"


FAMILIES = {
    "FAV": [{"fam": "FAV", "band": b, "k": k} for b in ((.5, .7), (.7, .85), (.85, .95), (.95, .99)) for k in (1, 7, 30)],
    "LONG": [{"fam": "LONG", "band": b, "k": k} for b in ((.01, .05), (.05, .15), (.15, .3), (.3, .5)) for k in (1, 7, 30)],
    "DRIFT": [{"fam": "DRIFT", "d": d, "k": k} for d in (0.05, 0.10, 0.20) for k in (1, 7, 30)],
}
if __name__ == "__main__":
    n_rules = 0
    for fam, rules in FAMILIES.items():
        res = []
        for r in rules:
            tr = trades(r)
            n_rules += 1
            a, b = stats(split(tr, "train")), stats(split(tr, "val"))
            res.append((r, tr, a, b))
            label = {k: v for k, v in r.items() if k != "fam"}
            print(f"  {fam:5s} {str(label):38s} train {fmt(a)}  val {fmt(b)}", flush=True)
        r, tr, a, b = max((x for x in res if x[2][2] >= 100), key=lambda x: x[2][0])
        label = {k: v for k, v in r.items() if k != "fam"}
        if a[0] > 0 and b[0] > 0:
            print(f"  -> {fam} chosen {label}: TEST {fmt(stats(split(tr, 'test')))}", flush=True)
        else:
            print(f"  -> {fam} chosen {label}: validation disagrees or train <= 0; test not read", flush=True)
    print(f"rules tried: {n_rules}")
