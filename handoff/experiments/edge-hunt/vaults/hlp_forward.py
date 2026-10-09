"""Scorer for the pre-registered HLP holding test (handoff/preregistration/hlp-hold/SPEC.md).

    python3 handoff/experiments/edge-hunt/vaults/hlp_forward.py [--final]

Reads HLP's account value and PnL history from Hyperliquid's public info API (`vaultDetails`,
allTime, points about every 14 days) at scoring time; nothing is recorded live. Return per
interval = PnL change / account value at the interval's start (time-weighted, what a depositor
earned; HLP takes no leader commission). Window: points from 2026-10-12 to 2027-04-10.
"""
import argparse
import datetime as dt

import httpx
import numpy as np

HLP = "0xdfc24b077bc1425ad1dea75bcb6f8158e10df303"
START, END = dt.datetime(2026, 10, 12, tzinfo=dt.timezone.utc), dt.datetime(2027, 4, 10, tzinfo=dt.timezone.utc)
HURDLE_APR = 0.05  # USDC lending stand-in: HLP must beat 5% a year
BLOCK, BOOT, SEED = 2, 10_000, 1


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--final", action="store_true")
    a = p.parse_args()
    d = httpx.post("https://api.hyperliquid.xyz/info", json={"type": "vaultDetails", "vaultAddress": HLP}, timeout=60).json()
    port = dict((n, x) for n, x in d["portfolio"])["allTime"]
    av = [(t, float(v)) for t, v in port["accountValueHistory"]]
    pnl = dict((t, float(v)) for t, v in port["pnlHistory"])
    s, e = START.timestamp() * 1000, END.timestamp() * 1000
    pts = [(t, v) for t, v in av if s <= t <= e]
    if len(pts) < 3:
        print(f"{len(pts)} points in the window so far: nothing to score")
        return
    r = np.array([(pnl[t1] - pnl[t0]) / v0 for (t0, v0), (t1, _) in zip(pts, pts[1:])])
    days = (pts[-1][0] - pts[0][0]) / 86400e3
    per_day = np.log1p(r).sum() / days
    excess = np.expm1(per_day * 365) - HURDLE_APR
    dts = np.diff([t for t, _ in pts]) / 86400e3
    rng = np.random.default_rng(SEED)
    n = len(r)
    boots = []
    for _ in range(BOOT):
        idx = np.concatenate([np.arange(k, k + BLOCK) % n for k in rng.integers(0, n, n // BLOCK + 1)])[:n]
        boots.append(np.expm1(np.log1p(r[idx]).sum() / dts[idx].sum() * 365) - HURDLE_APR)
    lo, hi = np.percentile(boots, [5, 95])
    print(f"{n} intervals, {days:.0f} days: HLP {np.expm1(per_day * 365) * 100:+.1f}% a year, minus the {HURDLE_APR * 100:g}% hurdle {excess * 100:+.1f} points, 90% CI [{lo * 100:+.1f}, {hi * 100:+.1f}]")
    if a.final:
        print("RESULT: " + ("SUCCESS" if excess > 0 and lo > 0 else "FAIL") + " (registered: excess > 0 and CI lower bound > 0)")
    else:
        print("interim: not the registered result")


if __name__ == "__main__":
    main()
