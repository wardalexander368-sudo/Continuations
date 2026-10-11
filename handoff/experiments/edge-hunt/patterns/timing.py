"""Trade timing for the two registered US-spot patterns: fill latency and exits (exploratory, research only).

    python3 handoff/experiments/edge-hunt/patterns/timing.py CACHE_DIR [--cost 0.0039]

CACHE_DIR is fetch_coinbase.py's 15-minute candles. The registered rules (preregistration/us-patterns/SPEC.md)
are unchanged; this asks two questions about them, on the same entries patterns.py trades:

1. Latency. The registration books the entry at the close of the 15-minute bar ending 30 minutes after the
   signal hour. The hourly agent starts at :21-:32 (median :22, autotrade journal 10-10..10-11), so the
   :30 bar is usually not final yet and the entry is booked on the *next* run; a real order sent then
   (the Alpaca mirror) fills ~80 minutes after the signal, not 30. Entry and exit delays of 1..8 bars
   (15..120 minutes) show what that lag costs and what acting at the first run after the signal earns.
2. Exits. Exit rules the hourly agent could run (a decision at each hourly look, filled at the :30 close
   as the registration's exit): other fixed holds, a trailing stop, take-profit, a break-even stop, and
   "hold while winning" extensions. Each is scored on the registered entries as a paired difference to
   the registered exit (same trades, so costs cancel), 90% CI by bootstrap over entry days. Selection:
   per rule the best train difference; validation must agree; test read once; a Bonferroni CI over every
   exit variant tried (both rules) is printed beside the 90% one. Splits as patterns.py.
"""
from __future__ import annotations

import sys
from collections import defaultdict
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
COST_ARG = float(sys.argv[sys.argv.index("--cost") + 1]) if "--cost" in sys.argv else 0.0039
sys.argv = [sys.argv[0], sys.argv[1]]
import patterns as P  # noqa: E402  (loads DATA from CACHE_DIR)

RULES = {"CAPIT Z=4 H=24": (P.capit(4), 24), "VOLSPIKE K=10 H=72": (P.volspike(10), 72)}


def entries(fn, hold, delay=2):
    """(coin, signal hour, entry 15m index, day) as patterns.run trades them (one position per coin)."""
    out = []
    for c, d in P.DATA.items():
        busy = -1
        for i in np.nonzero(fn(d))[0]:
            e, x = 4 * (i + 1) + delay - 1, 4 * (i + 1 + hold) + delay - 1
            if i < busy or x + 4 * 3 * hold >= len(d["C15"]) or np.isnan(d["C15"][e]) or np.isnan(d["C15"][x]):
                continue
            out.append((c, int(i), e, d["days"][i], float(d["S"][i])))
            busy = i + hold + 1
    return out


def boot(pairs, alpha=0.10, n=4000):
    """Mean and bootstrap CI over entry days of (day, value) pairs."""
    by = defaultdict(list)
    for d, r in pairs:
        by[d].append(r)
    k = list(by)
    if len(k) < 5:
        return np.nan, (np.nan, np.nan), len(pairs)
    s = np.array([sum(by[x]) for x in k]); c = np.array([len(by[x]) for x in k])
    pick = np.random.default_rng(1).integers(0, len(k), (n, len(k)))
    bs = s[pick].sum(1) / c[pick].sum(1)
    return float(np.mean([r for _, r in pairs])), tuple(np.percentile(bs, [100 * alpha / 2, 100 - 100 * alpha / 2])), len(pairs)


def fmt(t):
    m, ci, n = t
    return f"{m * 100:+.2f}% [{ci[0] * 100:+.2f},{ci[1] * 100:+.2f}] n{n}" if not np.isnan(m) else f"- n{n}"


def split(pairs, s):
    a, b = P.SPLITS[s]
    return [x for x in pairs if a <= x[0] <= b]


# ---------------------------------------------------------------- 1. latency
def latency():
    print(f"\n1. LATENCY: same signals, entry and exit D minutes after the signal / exit hour; net at {COST_ARG * 100:.2f}%/side")
    for name, (fn, hold) in RULES.items():
        print(f"  {name}")
        for delay in (1, 2, 3, 4, 5, 6, 8):
            tr = []
            for c, d in P.DATA.items():
                busy = -1
                for i in np.nonzero(fn(d))[0]:
                    e, x = 4 * (i + 1) + delay - 1, 4 * (i + 1 + hold) + delay - 1
                    if i < busy or x >= len(d["C15"]) or np.isnan(d["C15"][e]) or np.isnan(d["C15"][x]):
                        continue
                    tr.append((d["days"][i], d["C15"][x] / d["C15"][e] - 1 - 2 * COST_ARG))
                    busy = i + hold + 1
            tag = {2: "  <- registered", 6: "  <- ~what an order at the next run gets"}.get(delay, "")
            print(f"    {15 * delay:3d} min  " + "  ".join(f"{s} {fmt(boot(split(tr, s)))}" for s in P.SPLITS) +
                  f"  all {fmt(boot(tr))}{tag}")


# ---------------------------------------------------------------- 2. exits
def path(c, e, hours):
    """Hourly look prices after entry index e: the close 1..hours hours later (registered exit timing)."""
    C15 = P.DATA[c]["C15"]
    idx = e + 4 * np.arange(1, hours + 1)
    idx = idx[idx < len(C15)]
    return C15[idx]


def exit_fns(hold):
    """name -> f(entry price, hourly path, sigma_h) returning the exit price. All decide at hourly looks only."""
    v = {}
    for h in sorted({hold // 2, hold, 2 * hold, 3 * hold} - {hold}):
        v[f"fixed {h}h"] = (lambda h: lambda p0, px, s: px[min(h, len(px)) - 1])(h)
    for k in (1.0, 2.0, 3.0):  # trailing stop k * sigma_day under the best hourly close, max hold 2H
        def trail(p0, px, s, k=k):
            w = k * s * np.sqrt(24); peak = p0
            for p in px[: 2 * hold]:
                peak = max(peak, p)
                if p <= peak * (1 - w):
                    return p
            return px[min(2 * hold, len(px)) - 1]
        v[f"trail {k:g}sd max2H"] = trail
    for k in (1.0, 2.0):  # take profit at +k sigma_day, else the registered exit
        def tp(p0, px, s, k=k):
            for p in px[:hold]:
                if p >= p0 * (1 + k * s * np.sqrt(24)):
                    return p
            return px[hold - 1]
        v[f"take profit {k:g}sd"] = tp
    def be(p0, px, s):  # once up 1 sigma_day, a stop at the entry; else the registered exit
        armed = False
        for p in px[:hold]:
            armed |= p >= p0 * (1 + s * np.sqrt(24))
            if armed and p <= p0:
                return p
        return px[hold - 1]
    v["break-even stop"] = be
    def extend_profit(p0, px, s):  # at H: if net of costs in profit, hold H more (once more at 2H), else sell
        t = hold
        while t < 3 * hold and px[t - 1] > p0 * (1 + 2 * COST_ARG):
            t += hold
        return px[t - 1]
    v["hold on while in profit"] = extend_profit
    def extend_trend(p0, px, s):  # at H: hold H more while the last 24 h closed up
        t = hold
        while t < 3 * hold and px[t - 1] > px[t - 1 - 24]:
            t += hold
        return px[t - 1]
    v["hold on while 24h up"] = extend_trend
    def extend_trail(p0, px, s):  # at H: if in profit, switch to a 1sd trail (max 3H), else sell
        if px[hold - 1] <= p0 * (1 + 2 * COST_ARG):
            return px[hold - 1]
        w = s * np.sqrt(24); peak = max(px[:hold].max(), p0)
        for p in px[hold: 3 * hold]:
            peak = max(peak, p)
            if p <= peak * (1 - w):
                return p
        return px[min(3 * hold, len(px)) - 1]
    v["in profit at H: trail 1sd"] = extend_trail
    return v


def exits():
    print(f"\n2. EXITS: paired difference to the registered exit on the same entries (costs cancel); hourly looks only")
    fams = {name: (fn, hold, entries(fn, hold), exit_fns(hold)) for name, (fn, hold) in RULES.items()}
    M = sum(len(v[3]) for v in fams.values())
    print(f"  exit variants tried: {M} (Bonferroni CI level {100 - 10 / M:.2f}%)")
    for name, (fn, hold, ent, fns) in fams.items():
        base = {}
        for c, i, e, day, s in ent:
            px = path(c, e, 3 * hold)
            base[(c, i)] = (day, px[hold - 1] / P.DATA[c]["C15"][e] - 1 - 2 * COST_ARG)
        b = list(base.values())
        print(f"  {name}: registered exit net at {COST_ARG * 100:.2f}%/side  " + "  ".join(f"{s} {fmt(boot(split(b, s)))}" for s in P.SPLITS))
        res = []
        for vname, f in fns.items():
            diff = []
            for c, i, e, day, s in ent:
                p0 = P.DATA[c]["C15"][e]; px = path(c, e, 3 * hold)
                if np.isnan(px).any() or np.isnan(s):
                    continue
                diff.append((day, f(p0, px, s) / p0 - 1 - 2 * COST_ARG - base[(c, i)][1]))
            tr, va = boot(split(diff, "train")), boot(split(diff, "val"))
            res.append((vname, diff, tr, va))
            print(f"    {vname:26s} train {fmt(tr)}  val {fmt(va)}")
        vname, diff, tr, va = max(res, key=lambda r: r[2][0] if not np.isnan(r[2][0]) else -9)
        if tr[0] > 0 and va[0] > 0:
            te = split(diff, "test")
            print(f"    -> chosen {vname}: TEST {fmt(boot(te))}; Bonferroni {fmt(boot(te, alpha=0.10 / M, n=20000))}")
        else:
            print(f"    -> chosen {vname}: train <= 0 or validation disagrees; test not read")


if __name__ == "__main__":
    print(f"{len(P.DATA)} coins")
    latency()
    exits()
