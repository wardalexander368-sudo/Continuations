"""E1b, as registered in handoff/preregistration/revflow/SPEC.md: E1's revenue-surprise rule on 8
other buyback / revenue-share tokens' Hyperliquid perps. Fetches, caches and scores.

    python3 handoff/experiments/edge-hunt/pumpflow/revflow.py
"""
import json, time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import httpx
import numpy as np

OUT = Path("handoff/data/edge-hunt/revflow")
HL = "https://api.hyperliquid.xyz/info"
TOKENS = {"HYPE": "hyperliquid", "JUP": "jupiter", "AAVE": "aave", "DYDX": "dydx", "GMX": "gmx",
          "CAKE": "pancakeswap", "SKY": "sky", "BANANA": "banana-gun"}
FIRST, LAST = "2024-03-01", "2026-10-08"
COST, BLOCK, DRAWS = 1e-3, 10, 5000


def post(c, body):
    for i in range(8):
        try:
            r = c.post(HL, json=body)
            if r.status_code == 200:
                return r.json()
        except httpx.TransportError:
            if i == 7:
                raise
        time.sleep(3 * (i + 1))
    r.raise_for_status()


def day(ms):
    return datetime.fromtimestamp(ms / 1000, timezone.utc).date().isoformat()


def fetch():
    OUT.mkdir(parents=True, exist_ok=True)
    cache = OUT / "data.json"
    if cache.exists():
        return json.loads(cache.read_text())
    data = {}
    start = int(datetime(2024, 1, 1, tzinfo=timezone.utc).timestamp() * 1000)
    with httpx.Client(timeout=60) as c:
        for coin, slug in TOKENS.items():
            rev = {day(t * 1000): float(v or 0) for t, v in
                   c.get(f"https://api.llama.fi/summary/fees/{slug}?dataType=dailyRevenue").raise_for_status().json()["totalDataChart"]}
            candles, s = {}, start
            while True:
                part = post(c, {"type": "candleSnapshot", "req": {"coin": coin, "interval": "1d", "startTime": s, "endTime": int(time.time() * 1000)}}) or []
                for x in part:
                    candles[day(x["t"])] = float(x["c"])
                if len(part) < 500:
                    break
                s = part[-1]["t"] + 1
            fund, s = {}, start
            while True:
                part = post(c, {"type": "fundingHistory", "coin": coin, "startTime": s}) or []
                for x in part:
                    fund[day(x["time"])] = fund.get(day(x["time"]), 0.0) + float(x["fundingRate"])
                if len(part) < 500:
                    break
                s = part[-1]["time"] + 1
                time.sleep(0.2)
            data[coin] = {"rev": rev, "close": candles, "funding": fund}
    cache.write_text(json.dumps(data, sort_keys=True))
    return data


def series(d):
    """Per day: (date, position, return - funding) under the registered rule."""
    rev, close, fund = d["rev"], d["close"], d["funding"]
    first_px = min(close)
    start = max(FIRST, min(rev), (date.fromisoformat(first_px) + timedelta(days=8)).isoformat())
    out = []
    t = date.fromisoformat(start)
    while t.isoformat() <= LAST:
        k = t.isoformat(); n = (t + timedelta(days=1)).isoformat()
        base = [rev.get((t - timedelta(days=i)).isoformat()) for i in range(1, 8)]
        x = rev.get(k)
        if x and x > 0 and all(b and b > 0 for b in base) and k in close and n in close:
            s = np.log(x / np.mean(base))
            out.append((k, 1.0 if s > 0 else -1.0, close[n] / close[k] - 1 - fund.get(n, 0.0)))
        t += timedelta(days=1)
    return out


def ci(x, seed=0):
    rng = np.random.default_rng(seed)
    k = int(np.ceil(len(x) / BLOCK))
    m = [x[np.concatenate([np.arange(s, s + BLOCK) % len(x) for s in rng.integers(0, len(x), k)])[:len(x)]].mean() for _ in range(DRAWS)]
    return np.percentile(m, [5, 95])


def main():
    data = fetch()
    by_day, lines = {}, []
    for coin in TOKENS:
        rows = series(data[coin])
        days = [r[0] for r in rows]; pos = np.array([r[1] for r in rows]); rr = np.array([r[2] for r in rows])
        turn = np.abs(np.diff(np.r_[0.0, pos]))
        net = pos * rr - COST * turn
        tim = net - pos.mean() * rr
        (lo, hi), (tlo, thi) = ci(net), ci(tim)
        ok = lo > 0 and tlo > 0
        half = np.array([d < "2025-10-01" for d in days])
        lines.append(f"{coin:7s} {days[0]}..{days[-1]} n={len(rows):4d} long {np.mean(pos > 0):.0%}  net {net.mean():+.3%} [{lo:+.3%},{hi:+.3%}]  "
                     f"timing {tim.mean():+.3%} [{tlo:+.3%},{thi:+.3%}]  halves {tim[half].mean():+.3%}/{tim[~half].mean():+.3%}  {'PASS' if ok else 'fail'}")
        for d, p, r, nt, tm in zip(days, pos, rr, net, tim):
            by_day.setdefault(d, []).append((nt, tm))
    ds = sorted(by_day)
    pn = np.array([np.mean([x[0] for x in by_day[d]]) for d in ds]); pt = np.array([np.mean([x[1] for x in by_day[d]]) for d in ds])
    (lo, hi), (tlo, thi) = ci(pn), ci(pt)
    lines.append(f"FAMILY  {ds[0]}..{ds[-1]} n={len(ds)}  net {pn.mean():+.3%} [{lo:+.3%},{hi:+.3%}]  timing {pt.mean():+.3%} [{tlo:+.3%},{thi:+.3%}]  "
                 f"{'HOLDS' if tlo > 0 else 'DOES NOT HOLD'}")
    text = "\n".join(lines)
    (OUT / "result.txt").write_text(text + "\n")
    print(text)


if __name__ == "__main__":
    main()
