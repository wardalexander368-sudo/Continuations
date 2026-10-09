"""What does a $1,000 SOL-USD round trip cost on-chain? Measured against Coinbase's book.

    python3 handoff/experiments/sol_dex_costs.py sample [--minutes 60] [--every 30] [--size 1000] [--out data/sol-dex-costs.jsonl]
    python3 handoff/experiments/sol_dex_costs.py summary [--out data/sol-dex-costs.jsonl]
    python3 handoff/experiments/sol_dex_costs.py decay [--minutes 60] [--every 20] [--out data/sol-dex-decay.jsonl]
    python3 handoff/experiments/sol_dex_costs.py decay-summary [--out data/sol-dex-decay.jsonl]

For the user's jevtrader (SOL-USD on Coinbase, 90 bps taker; day-28 break-even fees f*_X per
fill): is there a venue where an arm's break-even fee is reachable? Each sample, at one moment:

* Jupiter (lite-api.jup.ag) quote: `size` USDC -> SOL (the buy), then exactly that SOL -> USDC
  (the sell). The shortfall `1 - usdc_back / size` is the full on-chain round trip: both legs'
  pool fees and price impact, no reference price needed.
* Coinbase SOL-USD best bid/ask: the buy leg's price vs the ask and the sell leg vs the bid show
  whether on-chain fills track the venue jevtrader marks against.

Network costs are added in the summary: `--tx-usd` per transaction (default $0.05, generous:
current priority fees on Jupiter's program are near zero). MEV (sandwiching) is not measured;
small size with tight slippage limits it, and it is noted in the summary, not priced.
Per-fill cost = half the round trip, comparable to jevtrader's FEE_BPS_COLUMNS (per fill).

Quote decay (`decay`): a quote is not a fill. A decision taken on a quote lands a second or
two later, at whatever the pools quote then (within the slippage limit). Each decay sample
takes the buy quote (`size` USDC -> SOL) and the sell quote (that SOL -> USDC), then re-takes
the very same quotes 1, 2 and 4 s later. The change is what acting on the first quote would
cost or save by landing later: + = worse for the trader.
"""
import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import httpx
import numpy as np

SOL = "So11111111111111111111111111111111111111112"
USDC = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"
JUP = "https://lite-api.jup.ag/swap/v1/quote"
CB = "https://api.exchange.coinbase.com/products/SOL-USD/book?level=1"

parser = argparse.ArgumentParser()
parser.add_argument("mode", choices=("sample", "summary", "decay", "decay-summary"))
parser.add_argument("--minutes", type=float, default=60.0)
parser.add_argument("--every", type=float, default=30.0)
parser.add_argument("--size", type=float, default=1000.0, help="USD per trade (jevtrader's liq walks $1,000)")
parser.add_argument("--tx-usd", type=float, default=0.05)
parser.add_argument("--out", default="data/sol-dex-costs.jsonl")
args = parser.parse_args()
out = Path(args.out)


def quote(client, input_mint, output_mint, amount):
    r = client.get(JUP, params={"inputMint": input_mint, "outputMint": output_mint, "amount": int(amount), "slippageBps": 50, "restrictIntermediateTokens": "true"})
    r.raise_for_status()
    q = r.json()
    return int(q["outAmount"]), [p["swapInfo"].get("label") for p in q.get("routePlan", [])], float(q.get("priceImpactPct") or 0)


def sample():
    out.parent.mkdir(parents=True, exist_ok=True)
    client = httpx.Client(timeout=15)
    end = time.time() + args.minutes * 60
    n = 0
    while time.time() < end:
        started = time.time()
        try:
            book = client.get(CB).json()
            bid, ask = float(book["bids"][0][0]), float(book["asks"][0][0])
            sol_out, buy_route, buy_impact = quote(client, USDC, SOL, args.size * 1e6)
            usdc_back, sell_route, sell_impact = quote(client, SOL, USDC, sol_out)
            row = {
                "t": datetime.now(timezone.utc).isoformat(timespec="seconds"), "size": args.size,
                "cb_bid": bid, "cb_ask": ask, "sol_out": sol_out / 1e9, "usdc_back": usdc_back / 1e6,
                "buy_route": buy_route, "sell_route": sell_route, "buy_impact": buy_impact, "sell_impact": sell_impact,
            }  # fmt: skip
            with out.open("a") as f:
                f.write(json.dumps(row) + "\n")
            n += 1
        except (httpx.HTTPError, KeyError, ValueError, IndexError) as exc:
            print(f"skip: {type(exc).__name__}: {exc}"[:200], file=sys.stderr)
        time.sleep(max(0.0, args.every - (time.time() - started)))
    print(f"{n} samples written to {out}")


def summary():
    rows = [json.loads(line) for line in out.read_text().splitlines() if line.strip()]
    size = np.array([r["size"] for r in rows])
    rt = 1e4 * (1 - np.array([r["usdc_back"] for r in rows]) / size)  # round trip, bps, before network fees
    rt_net = rt + 1e4 * 2 * args.tx_usd / size
    buy_px = size / np.array([r["sol_out"] for r in rows])
    ask = np.array([r["cb_ask"] for r in rows])
    bid = np.array([r["cb_bid"] for r in rows])
    mid = (ask + bid) / 2
    sell_px = np.array([r["usdc_back"] for r in rows]) / np.array([r["sol_out"] for r in rows])
    buy_vs_ask = 1e4 * (buy_px / ask - 1)
    sell_vs_bid = 1e4 * (1 - sell_px / bid)
    cb_half_spread = 1e4 * (ask - bid) / 2 / mid
    routes = {}
    for r in rows:
        key = "+".join(r["buy_route"])
        routes[key] = routes.get(key, 0) + 1
    q = lambda v: f"median {np.median(v):.2f}, p90 {np.quantile(v, 0.9):.2f}, max {v.max():.2f}"  # noqa: E731
    print(f"{len(rows)} samples, {rows[0]['t']} .. {rows[-1]['t']}, ${size[0]:,.0f} per trade")
    print(f"on-chain round trip, bps (fees + impact, both legs):      {q(rt)}")
    print(f"  + network ${args.tx_usd}/tx x 2:                            {q(rt_net)}")
    print(f"  => per fill (half), comparable to jevtrader's columns: median {np.median(rt_net) / 2:.2f} bps, p90 {np.quantile(rt_net, 0.9) / 2:.2f} bps")
    print(f"buy leg vs Coinbase ask, bps (+ = worse than the ask):   {q(buy_vs_ask)}")
    print(f"sell leg vs Coinbase bid, bps (+ = worse than the bid):  {q(sell_vs_bid)}")
    print(f"Coinbase half-spread, bps:                               {q(cb_half_spread)}")
    print(f"Coinbase retail round trip at 90 bps taker: {2 * 90 + 2 * np.median(cb_half_spread):.1f} bps (2 x 90 + spread)")
    print(f"buy routes: {dict(sorted(routes.items(), key=lambda kv: -kv[1])[:5])}")
    print("not priced: MEV/sandwich risk (limit with small size and tight slippage), failed transactions, USDC/USD basis")


DELAYS = (1.0, 2.0, 4.0)


def decay():
    out.parent.mkdir(parents=True, exist_ok=True)
    client = httpx.Client(timeout=15)
    end = time.time() + args.minutes * 60
    n = 0
    while time.time() < end:
        started = time.time()
        try:
            sol_out, buy_route, _ = quote(client, USDC, SOL, args.size * 1e6)
            usdc_back, sell_route, _ = quote(client, SOL, USDC, sol_out)
            row = {"t": datetime.now(timezone.utc).isoformat(timespec="seconds"), "size": args.size, "sol_in": sol_out / 1e9,
                   "buy": [sol_out / 1e9], "sell": [usdc_back / 1e6], "at": [0.0], "buy_route": buy_route, "sell_route": sell_route}  # fmt: skip
            for delay in DELAYS:
                time.sleep(max(0.0, started + delay - time.time()))
                at = time.time() - started
                b, _, _ = quote(client, USDC, SOL, args.size * 1e6)
                s_, _, _ = quote(client, SOL, USDC, sol_out)  # the same SOL amount as the first sell quote
                row["buy"].append(b / 1e9)
                row["sell"].append(s_ / 1e6)
                row["at"].append(round(at, 3))
            with out.open("a") as f:
                f.write(json.dumps(row) + "\n")
            n += 1
        except (httpx.HTTPError, KeyError, ValueError, IndexError) as exc:
            print(f"skip: {type(exc).__name__}: {exc}"[:200], file=sys.stderr)
        time.sleep(max(0.0, args.every - (time.time() - started)))
    print(f"{n} decay samples written to {out}")


def decay_summary():
    rows = [json.loads(line) for line in out.read_text().splitlines() if line.strip()]
    buy = np.array([r["buy"] for r in rows])  # SOL received for `size` USDC, at 0, 1, 2, 4 s
    sell = np.array([r["sell"] for r in rows])  # USDC received for the same SOL
    at = np.array([r["at"] for r in rows])
    print(f"{len(rows)} decay samples, {rows[0]['t']} .. {rows[-1]['t']}, ${rows[0]['size']:,.0f} per trade")
    print("change vs the first quote, bps (+ = worse for the trader); the same quote re-taken later")
    for k, delay in enumerate(DELAYS, start=1):
        b = 1e4 * (1 - buy[:, k] / buy[:, 0])
        s_ = 1e4 * (1 - sell[:, k] / sell[:, 0])
        both = np.concatenate([b, s_])
        paired = (b + s_) / 2  # a price move helps one side and hurts the other: the pair's mean is drift-free
        print(f"  ~{delay:.0f} s (measured {np.median(at[:, k]):.2f} s): buy mean {b.mean():+.2f} median {np.median(b):+.2f} | "
              f"sell mean {s_.mean():+.2f} median {np.median(s_):+.2f} | |change| p50 {np.median(np.abs(both)):.2f} p90 {np.quantile(np.abs(both), 0.9):.2f} max {np.abs(both).max():.2f}"
              f" | drift-free (buy+sell)/2 mean {paired.mean():+.3f} ± {1.645 * paired.std(ddof=1) / np.sqrt(len(paired)):.3f} (90% CI of the mean),"
              f" 5-95% of samples {np.quantile(paired, 0.05):+.2f} .. {np.quantile(paired, 0.95):+.2f}")
    print("Buy and sell means move opposite ways with the market; their average isolates quotes moving against the trader.")
    print("A trader with no timing edge pays the mean (≈0 if moves are symmetric) and carries the spread of |change|;")
    print("a fill is cancelled if the move passes the slippage limit (50 bps in these quotes).")


{"sample": sample, "summary": summary, "decay": decay, "decay-summary": decay_summary}[args.mode]()
