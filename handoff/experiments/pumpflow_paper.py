"""pump.fun revenue surprise -> PUMP perp: the paper forward test (pre-registered, edge hunt E1).

    python3 handoff/experiments/pumpflow_paper.py snapshot            # hourly: record a newly published day
    python3 handoff/experiments/pumpflow_paper.py evaluate [--final]  # replay the registered rule

The rule, the accounting and the success criteria are in
handoff/preregistration/pumpflow/SPEC.md and are fixed by its commit. Paper only: nothing here
signs or sends anything, and no session needs a wallet or exchange account.

**Snapshots.** A paper trader who checks DefiLlama every hour: the first time a UTC day's
pump.fun + PumpSwap revenue appears there, `snapshot` records it with the moment it was seen, the
signal computed from the numbers published *at that moment* (revisions later don't leak back),
and Hyperliquid's PUMP mid and top of book. That moment is the trade: the position is the
signal's sign, held until the next day's snapshot. `evaluate` charges funding from Hyperliquid's
history between snapshots.
"""
import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import httpx
import numpy as np

OUT = Path("handoff/data/pumpflow-paper/snapshots.jsonl")
HL = "https://api.hyperliquid.xyz/info"
LLAMA = {p: f"https://api.llama.fi/summary/fees/{p}?dataType=dailyRevenue" for p in ("pump.fun", "pumpswap")}

# The registered rule (SPEC.md). Changing any of these after registration voids the test.
START = datetime(2026, 10, 10, 0, 0, tzinfo=timezone.utc)
END = datetime(2027, 4, 8, 0, 0, tzinfo=timezone.utc)       # 180 days
COIN = "PUMP"
BASE_DAYS = 7               # surprise = log(rev_d / mean(rev_{d-7..d-1}))
COST = 1e-3                 # per side per unit of turnover: taker 4.5 bps + spread and impact
MIN_TRADES = 120
BLOCK = 10                  # trades per bootstrap block


def utc(ts):
    return datetime.fromtimestamp(ts, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def post(c, body):
    for i in range(6):
        r = c.post(HL, json=body)
        if r.status_code == 200:
            return r.json()
        time.sleep(3 * (i + 1))
    r.raise_for_status()


def revenue(c):
    """{day: {"pump.fun": usd, "pumpswap": usd}} for the days DefiLlama has published."""
    out = {}
    for name, url in LLAMA.items():
        for i in range(4):
            r = c.get(url)
            if r.status_code == 200:
                break
            time.sleep(5 * (i + 1))
        r.raise_for_status()
        for ts, v in r.json()["totalDataChart"]:
            out.setdefault(utc(ts)[:10], {})[name] = float(v or 0)
    return out


def signal(rev, day):
    """Surprise for `day` from the series as given, or None if the base is missing."""
    days = sorted(d for d in rev if d < day)[-BASE_DAYS:]
    if len(days) < BASE_DAYS or day not in rev:
        return None
    x = sum(rev[day].values())
    base = float(np.mean([sum(rev[d].values()) for d in days]))
    if x <= 0 or base <= 0:
        return None
    return float(np.log(x / base)), x, base


def load():
    if not OUT.exists():
        return []
    return [json.loads(line) for line in OUT.read_text().splitlines() if line.strip()]


def snapshot(now=None):
    now = time.time() if now is None else now
    seen = {s["day"] for s in load()}
    with httpx.Client(timeout=60) as c:
        rev = revenue(c)
        # the newest day both series have published
        both = [d for d, v in rev.items() if len(v) == len(LLAMA)]
        day = max(both)
        if day in seen:
            return f"nothing new (latest {day})"
        sig = signal({d: v for d, v in rev.items() if len(v) == len(LLAMA)}, day)
        if sig is None:
            return f"{day}: base incomplete, skipped"
        mid = float(post(c, {"type": "allMids"})[COIN])
        book = post(c, {"type": "l2Book", "coin": COIN})["levels"]
    s, x, base = sig
    snap = {"t": utc(now), "day": day, "rev": rev[day], "rev_total": x, "base7": base, "signal": s,
            "position": int(np.sign(s)), "mid": mid, "bid": float(book[0][0]["px"]), "ask": float(book[1][0]["px"])}
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("a") as fh:
        fh.write(json.dumps(snap, separators=(",", ":")) + "\n")
    return f"{day}: revenue ${x:,.0f} vs 7-day ${base:,.0f}, signal {s:+.3f} -> {'long' if s > 0 else 'short'} PUMP at {mid}"


def funding(c, t0, t1):
    out, s = {}, int(t0 * 1000)
    while s < int(t1 * 1000):
        part = post(c, {"type": "fundingHistory", "coin": COIN, "startTime": s, "endTime": int(t1 * 1000)}) or []
        for x in part:
            out[x["time"] // 1000] = float(x["fundingRate"])
        if len(part) < 500:
            break
        s = part[-1]["time"] + 1
    return out


def ts(s):
    return datetime.strptime(s, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc).timestamp()


def trades(snaps, fund):
    """One trade per snapshot that has a next one: (net, gross price return, position)."""
    out, prev = [], 0
    for a, b in zip(snaps, snaps[1:]):
        p = a["position"]
        r = b["mid"] / a["mid"] - 1
        f = sum(v for t, v in fund.items() if ts(a["t"]) < t <= ts(b["t"]))
        net = p * r - p * f - COST * abs(p - prev)
        out.append((net, r - f, p))
        prev = p
    return out


def block_ci(x, n=5000, seed=0):
    rng = np.random.default_rng(seed)
    k = int(np.ceil(len(x) / BLOCK))
    means = [x[np.concatenate([np.arange(s, s + BLOCK) % len(x) for s in rng.integers(0, len(x), k)])[:len(x)]].mean()
             for _ in range(n)]
    return np.percentile(means, [5, 95])


def evaluate(final=False):
    snaps = [s for s in load() if START.timestamp() <= ts(s["t"]) < END.timestamp()]
    if len(snaps) < 3:
        return f"{len(snaps)} snapshots in the window so far; nothing to score"
    with httpx.Client(timeout=60) as c:
        fund = funding(c, ts(snaps[0]["t"]), ts(snaps[-1]["t"]))
    t = trades(snaps, fund)
    net = np.array([x[0] for x in t]); hold = np.array([x[1] for x in t]); pos = np.array([x[2] for x in t])
    timing = net - pos.mean() * hold
    lo, hi = block_ci(net)
    tlo, thi = block_ci(timing)
    lines = [f"{len(t)} trades {snaps[0]['day']}..{snaps[-1]['day']} (long {np.mean(pos > 0):.0%})",
             f"mean net per trade {net.mean():+.3%}  90% CI [{lo:+.3%}, {hi:+.3%}]  total {net.sum():+.1%}",
             f"timing part {timing.mean():+.3%}  90% CI [{tlo:+.3%}, {thi:+.3%}]   buy-and-hold {hold.mean():+.3%}/trade"]
    if final:
        ok = len(t) >= MIN_TRADES and lo > 0 and timing.mean() > 0
        lines.append("CONFIRMED" if ok else "NOT CONFIRMED")
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("snapshot")
    e = sub.add_parser("evaluate")
    e.add_argument("--final", action="store_true")
    a = ap.parse_args()
    print(snapshot() if a.cmd == "snapshot" else evaluate(a.final))


if __name__ == "__main__":
    sys.exit(main())
