"""F1, as registered in handoff/preregistration/listing-fade/SPEC.md: short newly listed Hyperliquid
perps. Fetches (cached), chooses on train, reads validation, and reads test only if allowed.

    python3 handoff/experiments/edge-hunt/listings/listing_fade.py [--read-test]
"""
import argparse, json, time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import httpx
import numpy as np

OUT = Path("handoff/data/edge-hunt/listings")
HL = "https://api.hyperliquid.xyz/info"
FIRST_L, LAST_DAY = date(2023, 9, 1), date(2026, 10, 8)
KS, HS = (1, 3), (7, 14, 28)
COST, DRAWS = 2e-3, 5000
TRAIN_END, VAL_END = date(2025, 1, 1), date(2026, 1, 1)


def post(c, body):
    for i in range(8):
        try:
            r = c.post(HL, json=body)
            if r.status_code == 200:
                return r.json()
        except httpx.TransportError:
            pass
        time.sleep(3 * (i + 1))
    raise RuntimeError(f"HL failed: {body}")


def d_of(ms):
    return datetime.fromtimestamp(ms / 1000, timezone.utc).date()


def fetch():
    OUT.mkdir(parents=True, exist_ok=True)
    cache = OUT / "data.json"
    if cache.exists():
        return json.loads(cache.read_text())
    data = {}
    t0 = int(datetime(2023, 1, 1, tzinfo=timezone.utc).timestamp() * 1000)
    now = int(time.time() * 1000)
    with httpx.Client(timeout=60) as c:
        uni = post(c, {"type": "meta"})["universe"]
        for u in uni + [{"name": "BTC"}]:
            coin = u["name"]
            if coin in data:
                continue
            bars = post(c, {"type": "candleSnapshot", "req": {"coin": coin, "interval": "1d", "startTime": t0, "endTime": now}}) or []
            closes = {d_of(x["t"]).isoformat(): float(x["c"]) for x in bars}
            entry = {"close": closes, "delisted": bool(u.get("isDelisted")), "funding": {}}
            if closes and coin != "BTC":
                L = date.fromisoformat(min(closes))
                if L >= FIRST_L:
                    s, e = L, L + timedelta(days=3 + 28 + 2)
                    ms = int(datetime(s.year, s.month, s.day, tzinfo=timezone.utc).timestamp() * 1000)
                    me = int(datetime(e.year, e.month, e.day, tzinfo=timezone.utc).timestamp() * 1000)
                    while ms < me:
                        part = post(c, {"type": "fundingHistory", "coin": coin, "startTime": ms, "endTime": me}) or []
                        for x in part:
                            k = d_of(x["time"]).isoformat()
                            entry["funding"][k] = entry["funding"].get(k, 0.0) + float(x["fundingRate"])
                        if len(part) < 500:
                            break
                        ms = part[-1]["time"] + 1
            data[coin] = entry
            time.sleep(0.15)
    cache.write_text(json.dumps(data, sort_keys=True))
    return data


def trades(data, k, H):
    """Per listing: (L, net short, net short hedged with BTC, had funding)."""
    btc = data["BTC"]["close"]
    out = []
    for coin, e in data.items():
        cl = e["close"]
        if coin == "BTC" or not cl:
            continue
        L = date.fromisoformat(min(cl))
        if L < FIRST_L:
            continue
        a, b = L + timedelta(days=k), L + timedelta(days=k + H)
        if b > LAST_DAY or a.isoformat() not in cl:
            continue
        held = [d for d in sorted(cl) if a.isoformat() < d <= b.isoformat()]
        if not held:
            continue
        exit_day = b.isoformat() if b.isoformat() in cl else held[-1]   # delisted: last close
        r = cl[exit_day] / cl[a.isoformat()] - 1
        f = sum(e["funding"].get(d, 0.0) for d in held if d <= exit_day)
        net = -r + f - 2 * COST
        rb = btc[exit_day] / btc[a.isoformat()] - 1 if exit_day in btc and a.isoformat() in btc else 0.0
        out.append((L, net, net + rb - 2 * COST, bool(e["funding"])))
    return out


def ci(rows, seed=0):
    by = {}
    for L, v in rows:
        by.setdefault((L.year, L.month), []).append(v)
    groups = list(by.values())
    rng = np.random.default_rng(seed)
    means = []
    for _ in range(DRAWS):
        pick = [groups[i] for i in rng.integers(0, len(groups), len(groups))]
        flat = [v for g in pick for v in g]
        means.append(np.mean(flat))
    return np.percentile(means, [5, 95])


def summary(rows, col=1):
    v = [(r[0], r[col]) for r in rows]
    x = np.array([t[1] for t in v])
    lo, hi = ci(v)
    return f"n={len(x):3d} mean {x.mean():+.2%} [{lo:+.2%},{hi:+.2%}] median {np.median(x):+.2%} win {np.mean(x > 0):.0%}", x.mean()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--read-test", action="store_true")
    a = ap.parse_args()
    data = fetch()
    lines = []
    best = None
    for k in KS:
        for H in HS:
            t = [r for r in trades(data, k, H) if r[0] < TRAIN_END]
            s, m = summary(t)
            lines.append(f"train k={k} H={H:2d}: {s}")
            if best is None or m > best[0]:
                best = (m, k, H)
    _, k, H = best
    lines.append(f"chosen on train: k={k} H={H}")
    allr = trades(data, k, H)
    val = [r for r in allr if TRAIN_END <= r[0] < VAL_END]
    s, vm = summary(val)
    lines.append(f"validation: {s}")
    lines.append(f"validation, BTC-hedged (secondary): {summary(val, 2)[0]}")
    lines.append(f"listings without funding history (train+val): {sum(1 for r in allr if r[0] < VAL_END and not r[3])}")
    if vm > 0 and a.read_test:
        te = [r for r in allr if r[0] >= VAL_END]
        s, _ = summary(te)
        lines.append(f"TEST: {s}")
        lines.append(f"TEST, BTC-hedged (secondary): {summary(te, 2)[0]}")
    elif vm <= 0:
        lines.append("validation mean <= 0: test not read (F1 closed)")
    text = "\n".join(lines)
    (OUT / ("result-test.txt" if a.read_test else "result-trainval.txt")).write_text(text + "\n")
    print(text)


if __name__ == "__main__":
    main()
