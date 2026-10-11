"""D3 on Coinbase's US perps in whole contracts at a given account size, plus Hyperliquid funding as a proxy.

    python3 handoff/experiments/edge-hunt/perps/cde_rounding.py DAILY_DIR [--funding-dir DIR] [--from D --to D]

Same rule and data as `xs_coinbase.py` (D3 long-short, 20 bps/side). Each leg of L dollars is split
equally over its coins and rounded to whole contracts at the execution-day price (contract sizes from
Coinbase's product list, 2026-10-11). Return is P&L divided by L (the units of `xs_coinbase.py`: per $1 a leg). Costs on rounded turnover. --funding-dir: subtract Hyperliquid's hourly
funding (cache of `fetch_hl_funding.py` / `fetch_funding_since.py`, coin -> {hour: rate}) as a
stand-in for Coinbase's US perp funding, which has no public history; longs pay positive rates.
"""
from __future__ import annotations

import datetime as dt
import json
import sys
from pathlib import Path

import numpy as np

SIZE = {"BTC": 0.01, "ETH": 0.1, "SOL": 5, "XRP": 500, "ADA": 1000, "AVAX": 10, "LINK": 50, "LTC": 5, "DOT": 100,
        "DOGE": 5000, "BCH": 1, "NEAR": 500, "SUI": 500, "HYPE": 10, "BNB": 1, "AAVE": 5, "ONDO": 1000, "XLM": 5000,
        "ENA": 5000, "HBAR": 5000, "PEPE": 1e8, "SHIB": 1e7, "ZEC": 1}
HLNAME = {"PEPE": "kPEPE", "SHIB": "kSHIB"}
FD = Path(sys.argv[sys.argv.index("--funding-dir") + 1]) if "--funding-dir" in sys.argv else None
WIN = (sys.argv[sys.argv.index("--from") + 1], sys.argv[sys.argv.index("--to") + 1]) if "--from" in sys.argv else None
sys.argv = sys.argv[:2]
sys.path.insert(0, str(Path(__file__).resolve().parent))
import xs_coinbase as X  # noqa: E402

if WIN:
    X.SPLITS.clear(); X.SPLITS["window"] = WIN

fund = {}
if FD:
    for c in X.coins:
        f = FD / f"{HLNAME.get(c, c)}.json"
        if f.exists():
            fund[c] = {int(k): v for k, v in json.loads(f.read_text()).items()}


def hour_of(day):
    return int(dt.datetime.fromisoformat(day).replace(tzinfo=dt.timezone.utc).timestamp()) // 3600 + 24  # day's close


def run(leg, cost=0.0020, use_funding=False):
    out, prev = [], {}
    cov = []
    for k, i in enumerate(X.MON[:-1]):
        j = X.MON[k + 1]
        w = X.book(X.sig_vmom(i), i, "ls")
        if w is None:
            prev = {}; continue
        a, b = i + 1, j + 1
        pos = {}  # coin -> signed dollars at entry, whole contracts
        for c, wt in w.items():
            px = X.C[a, c]
            if np.isnan(px):
                continue
            want = wt * (leg or 1)  # wt = +-1/q
            pos[c] = want if leg is None else np.sign(want) * round(abs(want) / (px * SIZE[X.coins[c]])) * px * SIZE[X.coins[c]]
        cov.append(sum(abs(v) for v in pos.values()) / (2 * (leg or 1)))
        pnl = sum(v * (X.C[b, c] / X.C[a, c] - 1) for c, v in pos.items() if not np.isnan(X.C[b, c]))
        if use_funding:
            h0, h1 = hour_of(X.days[a]), hour_of(X.days[b])
            for c, v in pos.items():
                fd = fund.get(X.coins[c])
                if fd:
                    pnl -= v * sum(fd.get(h, 0.0) for h in range(h0, h1))
        turn = sum(abs(pos.get(c, 0) - prev.get(c, 0)) for c in set(pos) | set(prev))
        prev = pos
        out.append((X.days[i], (pnl - cost * turn) / (leg or 1)))
    return out, float(np.mean(cov))


def show(name, rs, cov):
    parts = []
    for s, (lo, hi) in X.SPLITS.items():
        m, ci, n = X.stats([x for x in rs if lo <= x[0] <= hi])
        parts.append(f"{s} {m * 100:+.2f}%/wk [{ci[0] * 100:+.2f},{ci[1] * 100:+.2f}] n{n}")
    print(f"  {name:30s} built {cov * 100:3.0f}% of target  " + "  ".join(parts), flush=True)


if __name__ == "__main__":
    show("unrounded (registered)", *run(None))
    for leg in (500, 1000, 2000, 5000):
        show(f"${leg} a leg, whole contracts", *run(leg))
    if fund:
        print(f"  funding: Hyperliquid hourly rates for {len(fund)} coins (missing coins/hours count as 0)")
        show("unrounded, with HL funding", *run(None, use_funding=True))
        show("$1000 a leg, with HL funding", *run(1000, use_funding=True))
