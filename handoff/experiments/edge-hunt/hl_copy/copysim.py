"""E2 copy simulation on period B (handoff/preregistration/hl-copy/SPEC.md).

    python3 handoff/experiments/edge-hunt/hl_copy/copysim.py score [--cost 0.001] [--extra-delay 0]

Needs selection.json (pick.py final) and the fills/portfolios in the cache; fetches 15-minute candles and
hourly funding per coin into the cache. Writes result.json (the registered numbers with the default flags).
"""
import argparse
import gzip
import json
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from fetch import CACHE, post
from pick import OUT, interp

B0 = int(datetime(2026, 8, 20, tzinfo=timezone.utc).timestamp() * 1000)
B1 = int(datetime(2026, 10, 9, tzinfo=timezone.utc).timestamp() * 1000)
Q = 15 * 60 * 1000
DELAY, MIN_DW, MAX_LEV, BLOCK = 2 * 60 * 1000, 0.02, 3.0, 5


def universe():
    p = CACHE / "meta.json"
    if not p.exists():
        p.write_text(json.dumps(post({"type": "meta"})))
    return {u["name"] for u in json.loads(p.read_text())["universe"]}


def candles(coin):
    p = CACHE / "candles15" / f"{coin}.json"
    if not p.exists():
        p.parent.mkdir(parents=True, exist_ok=True)
        rows = post({"type": "candleSnapshot", "req": {"coin": coin, "interval": "15m", "startTime": B0 - Q, "endTime": B1 + Q}}) or []
        p.write_text(json.dumps({str(r["t"]): [float(r["o"]), float(r["c"])] for r in rows}))
        time.sleep(1)
    return {int(k): v for k, v in json.loads(p.read_text()).items()}


def funding(coin):
    p = CACHE / "funding" / f"{coin}.json"
    if not p.exists():
        p.parent.mkdir(parents=True, exist_ok=True)
        out, s = {}, B0
        while s < B1:
            part = post({"type": "fundingHistory", "coin": coin, "startTime": s, "endTime": B1}) or []
            out.update({str(x["time"]): float(x["fundingRate"]) for x in part})
            if len(part) < 500:
                break
            s = part[-1]["time"] + 1
            time.sleep(1)
        p.write_text(json.dumps(out))
        time.sleep(1)
    return {int(k): v for k, v in json.loads(p.read_text()).items()}


def load(addr):
    fills = json.loads(gzip.decompress((CACHE / "fills" / f"{addr}.json.gz").read_bytes()))
    port = dict(json.loads(gzip.decompress((CACHE / "portfolio" / f"{addr}.json.gz").read_bytes())))
    return sorted(fills, key=lambda f: (f["time"], f.get("tid", 0))), port["allTime"]["accountValueHistory"]


def follow(addr, cost, extra_delay, uni):
    fills, avh = load(addr)
    fills = [f for f in fills if f["coin"] in uni]
    pos, px_last = {}, {}
    i = 0
    while i < len(fills) and fills[i]["time"] < B0:  # positions held at the start of B
        f = fills[i]
        pos[f["coin"]] = float(f["startPosition"]) + (float(f["sz"]) if f["side"] == "B" else -float(f["sz"]))
        i += 1
    coins = {c for c, p in pos.items() if abs(p) > 0} | {f["coin"] for f in fills[i:] if f["time"] < B1}
    cs = {c: candles(c) for c in coins}
    fu = {c: funding(c) for c in coins}
    eq, units, days = 1.0, {}, {}
    pending = set(c for c, p in pos.items() if abs(p) > 0)  # set the initial book at the first candle
    turnover = 0.0
    last_av = None
    for t in range(B0, B1, Q):
        cutoff = t - DELAY - extra_delay * Q
        while i < len(fills) and fills[i]["time"] <= cutoff:
            f = fills[i]
            pos[f["coin"]] = float(f["startPosition"]) + (float(f["sz"]) if f["side"] == "B" else -float(f["sz"]))
            pending.add(f["coin"])
            i += 1
        opens = {c: cs[c][t][0] for c in coins if t in cs[c]}
        if pending:
            av = interp(avh, t) or last_av
            last_av = av
            if av and av > 0:
                want = {c: pos.get(c, 0.0) * opens[c] / av for c in pending if c in opens}
                gross_other = sum(abs(u * opens[c]) / eq for c, u in units.items() if c in opens and c not in want)
                gross = gross_other + sum(abs(w) for w in want.values())
                scale = min(1.0, MAX_LEV / gross) if gross > 0 else 1.0
                for c, w in want.items():
                    w *= scale
                    cur = units.get(c, 0.0) * opens[c] / eq
                    if abs(w - cur) >= MIN_DW or (w == 0 and cur != 0):
                        dn = abs(w - cur) * eq
                        eq -= cost * dn
                        turnover += dn
                        units[c] = w * eq / opens[c]
                pending = {c for c in pending if c not in opens}
        for c, u in list(units.items()):
            if not u or t not in cs[c]:
                continue
            o, cl = cs[c][t]
            eq += u * (cl - o)
            for ft, rate in fu[c].items():
                if t < ft <= t + Q:
                    eq -= u * cl * rate
        if eq <= 0:
            eq = 0.0
            units = {}
        if (t + Q) % 86_400_000 == 0:
            days[t + Q] = eq
        if eq == 0:
            break
    eqs = [1.0] + [days[k] for k in sorted(days)]
    rets = [b / a - 1 if a > 0 else 0.0 for a, b in zip(eqs, eqs[1:])]
    rets += [0.0] * (49 - len(rets))  # a wiped-out follower stays flat
    return {"addr": addr, "rets": rets, "final": eqs[-1], "turnover": turnover, "coins": len(coins)}


def block_ci(x, n=4000, seed=0):
    x = np.asarray(x)
    rng, k = np.random.default_rng(seed), int(np.ceil(len(x) / BLOCK))
    m = [x[np.concatenate([np.arange(s, s + BLOCK) % len(x) for s in rng.integers(0, len(x), k)])[:len(x)]].mean() for _ in range(n)]
    return [float(v) for v in np.percentile(m, [5, 95])]


def btc_daily():
    c = candles("BTC")
    pts = [c[t][1] for t in range(B0, B1, Q) if (t + Q) % 86_400_000 == 0 and t in c]
    closes = [c[B0][0]] + pts
    return np.array([b / a - 1 for a, b in zip(closes, closes[1:])])


def score(cost, extra_delay):
    uni = universe()
    sel = json.loads((OUT / "selection.json").read_text())
    S = [follow(r["addr"], cost, extra_delay, uni) for r in sel["selected"]]
    P = [follow(a, cost, extra_delay, uni) for a in sel["placebo"]]
    port = np.mean([s["rets"] for s in S], axis=0)
    lo, hi = block_ci(port)
    rng = np.random.default_rng(1)
    pr = np.array([r["rets"] for r in P])
    placebo_means = [pr[rng.choice(len(P), len(S), replace=False)].mean() for _ in range(1000)]
    btc = btc_daily()[:len(port)]
    X = np.c_[np.ones(len(btc)), btc]
    alpha, beta = np.linalg.lstsq(X, port[:len(btc)], rcond=None)[0]
    res = {"cost": cost, "extra_delay_candles": extra_delay, "days": len(port), "mean": float(port.mean()), "ci90": [lo, hi],
           "placebo_p90": float(np.percentile(placebo_means, 90)), "placebo_median": float(np.median(placebo_means)),
           "alpha_btc": float(alpha), "beta_btc": float(beta), "total": float(np.prod(1 + port) - 1),
           "followers": [{k: v for k, v in s.items() if k != "rets"} | {"mean": float(np.mean(s["rets"]))} for s in S],
           "placebo_followers_mean": float(pr.mean()), "placebo_wiped": int(sum(r["final"] == 0 for r in P)),
           "selected_wiped": int(sum(s["final"] == 0 for s in S))}
    res["holds"] = bool(res["ci90"][0] > 0 and res["mean"] > res["placebo_p90"] and res["alpha_btc"] > 0)
    return res


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd")
    ap.add_argument("--cost", type=float, default=0.001)
    ap.add_argument("--extra-delay", type=int, default=0)
    a = ap.parse_args()
    r = score(a.cost, a.extra_delay)
    name = "result.json" if (a.cost, a.extra_delay) == (0.001, 0) else f"result-cost{a.cost}-delay{a.extra_delay}.json"
    (OUT / name).write_text(json.dumps(r, indent=1))
    print(json.dumps({k: v for k, v in r.items() if k != "followers"}, indent=1))
