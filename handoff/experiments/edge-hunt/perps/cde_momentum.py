"""Do the registered perps momentum rules survive on the coins Coinbase lists as US perps? (exploratory)

    python3 handoff/experiments/edge-hunt/perps/cde_momentum.py [--cost-bps 20] [--lag 1] [--funding --funding-dir DIR]

AJ's rule (2026-10-11): live venues must be US-accessible. Coinbase Financial Markets lists
perpetual-style futures ("-CDE", 5-year expiry, hourly funding, published taker fee from 0.02%) on
~24 coins; the 22 crypto ones with Hyperliquid history are below (PAXG and the index perps left out).
Same data, splits, cost model and bootstrap as `perp_rules.py`, universe cut to these coins.
No new selection: the two rules are the registered ones, D (14-day return) and D3 (14-day return /
14-day daily std), weekly quintiles (4-5 coins a leg here). Caveat: the list is today's, so the
universe has look-ahead (coins that grew big enough to be listed).
"""
from __future__ import annotations

import sys

import numpy as np

sys.path.insert(0, __file__.rsplit("/", 1)[0])
import perp_rules as P  # noqa: E402

CDE = ["BTC", "ETH", "SOL", "XRP", "ADA", "AVAX", "LINK", "LTC", "DOT", "DOGE", "BCH", "NEAR", "SUI", "HYPE",
       "BNB", "AAVE", "ONDO", "XLM", "ENA", "HBAR", "kPEPE", "kSHIB", "ZEC"]
MASK = np.array([c in CDE for c in P.coins])
base_universe = P.universe
P.universe = lambda i: base_universe(i) & MASK


def mom(i):
    return P.quintile_weights(P.C[i] / P.C[i - 14] - 1, P.universe(i))


def vmom(i):
    sig = (P.C[i] / P.C[i - 14] - 1) / np.nanstd(P.R[i - 13: i + 1], axis=0)
    return P.quintile_weights(sig, P.universe(i))


if __name__ == "__main__":
    print(f"{MASK.sum()} CDE coins with HL history; cost {P.COST * 1e4:g} bps/side, lag {P.LAG}, funding {'on' if P.USE_FUNDING else 'off'}")
    for name, fn in (("D  14-day momentum", mom), ("D3 vol-scaled 14-day", vmom)):
        rs = P.backtest(fn, P.MONDAYS)
        print(f"  {name}: " + "  ".join(
            f"{s} {t[0] * 100:+.2f}%/wk [{t[1][0] * 100:+.2f},{t[1][1] * 100:+.2f}] n{t[2]}"
            for s in P.SPLITS for t in [P.stats(P.split(rs, s))]))
