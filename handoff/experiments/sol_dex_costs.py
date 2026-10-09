"""What does a $1,000 SOL-USD round trip cost on-chain? Measured against Coinbase's book.

    python3 handoff/experiments/sol_dex_costs.py sample [--minutes 60] [--every 30] [--size 1000] [--delays 1,2,5] [--out data/sol-dex-costs.jsonl]
    python3 handoff/experiments/sol_dex_costs.py summary [--out data/sol-dex-costs.jsonl]

For the user's jevtrader (SOL-USD on Coinbase, 90 bps taker; day-28 break-even fees f*_X per
fill): is there a venue where an arm's break-even fee is reachable? Each sample, at one moment:

* Jupiter (lite-api.jup.ag) quote: `size` USDC -> SOL (the buy), then exactly that SOL -> USDC
  (the sell). The shortfall `1 - usdc_back / size` is the full on-chain round trip: both legs'
  pool fees and price impact, no reference price needed.
* Coinbase SOL-USD best bid/ask: the buy leg's price vs the ask and the sell leg vs the bid show
  whether on-chain fills track the venue jevtrader marks against.

**Quote decay** (`--delays`, since 2026-10-09 04:10): a quote is not a fill. A swap built from
the quote at decision time lands ~1-2 s later and executes against the pools' state then (prop
AMMs reprice every slot), or fails if that is worse than the slippage limit. So each sample
re-quotes the same buy (same USDC) and the same sell (same SOL) after each delay, with Coinbase's
book at that moment too. The summary reports, per delay: how far the quote moved (decay), how
much of that is the market moving (Coinbase mid), how often a 50 bps slippage limit would have
failed, and the per-fill cost of filling at the later quote, measured against Coinbase's mid at
decision time (what jevtrader's fee columns are charged against).

Network costs are added in the summary: `--tx-usd` per transaction (default $0.05, generous:
current priority fees on Jupiter's program are near zero). MEV (sandwiching) is not measured;
small size with tight slippage limits it, and it is noted in the summary, not priced.
Per-fill cost = half the round trip, comparable to jevtrader's FEE_BPS_COLUMNS (per fill).
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
SLIPPAGE_BPS = 50

parser = argparse.ArgumentParser()
parser.add_argument("mode", choices=("sample", "summary"))
parser.add_argument("--minutes", type=float, default=60.0)
parser.add_argument("--every", type=float, default=30.0)
parser.add_argument("--size", type=float, default=1000.0, help="USD per trade (jevtrader's liq walks $1,000)")
parser.add_argument("--delays", default="1,2,5", help="seconds after the first quote to re-quote both legs ('' = off)")
parser.add_argument("--tx-usd", type=float, default=0.05)
parser.add_argument("--out", default="data/sol-dex-costs.jsonl")
args = parser.parse_args()
out = Path(args.out)


def quote(client, input_mint, output_mint, amount):
    r = client.get(JUP, params={"inputMint": input_mint, "outputMint": output_mint, "amount": int(amount), "slippageBps": SLIPPAGE_BPS, "restrictIntermediateTokens": "true"})
    r.raise_for_status()
    q = r.json()
    reliable = [int(v) for v in ((q.get("mostReliableAmmsQuoteReport") or {}).get("info") or {}).values()]
    return {
        "out": int(q["outAmount"]),
        "route": [p["swapInfo"].get("label") for p in q.get("routePlan", [])],
        "impact": float(q.get("priceImpactPct") or 0),
        "slot": q.get("contextSlot"),
        "reliable": max(reliable) if reliable else None,  # best quote among Jupiter's "most reliable" AMMs
    }


def book(client):
    b = client.get(CB).json()
    return float(b["bids"][0][0]), float(b["asks"][0][0])


def sample():
    out.parent.mkdir(parents=True, exist_ok=True)
    client = httpx.Client(timeout=15)
    delays = [float(d) for d in args.delays.split(",") if d.strip()]
    end = time.time() + args.minutes * 60
    n = 0
    while time.time() < end:
        started = time.time()
        try:
            bid, ask = book(client)
            buy = quote(client, USDC, SOL, args.size * 1e6)
            sell = quote(client, SOL, USDC, buy["out"])
            t0 = time.time()
            row = {
                "t": datetime.now(timezone.utc).isoformat(timespec="seconds"), "size": args.size,
                "cb_bid": bid, "cb_ask": ask, "sol_out": buy["out"] / 1e9, "usdc_back": sell["out"] / 1e6,
                "buy_route": buy["route"], "sell_route": sell["route"], "buy_impact": buy["impact"], "sell_impact": sell["impact"],
                "slot": buy["slot"], "buy_reliable": buy["reliable"] and buy["reliable"] / 1e9,
                "sell_reliable": sell["reliable"] and sell["reliable"] / 1e6, "later": [],
            }  # fmt: skip
            for delay in delays:
                time.sleep(max(0.0, t0 + delay - time.time()))
                t1 = time.time()
                bid1, ask1 = book(client)
                buy1 = quote(client, USDC, SOL, args.size * 1e6)
                sell1 = quote(client, SOL, USDC, buy["out"])  # the same SOL as the first sell: same trade, later
                row["later"].append({
                    "delay": delay, "dt": round(t1 - t0, 3), "cb_bid": bid1, "cb_ask": ask1,
                    "sol_out": buy1["out"] / 1e9, "usdc_back": sell1["out"] / 1e6,
                    "slot_buy": buy1["slot"], "slot_sell": sell1["slot"], "buy_route": buy1["route"],
                })  # fmt: skip
            with out.open("a") as f:
                f.write(json.dumps(row) + "\n")
            n += 1
        except (httpx.HTTPError, KeyError, ValueError, IndexError) as exc:
            print(f"skip: {type(exc).__name__}: {exc}"[:200], file=sys.stderr)
        time.sleep(max(0.0, args.every - (time.time() - started)))
    print(f"{n} samples written to {out}")


def q(v):
    v = np.asarray(v, dtype=float)
    return f"median {np.median(v):+.2f}, mean {v.mean():+.2f}, p10 {np.quantile(v, 0.1):+.2f}, p90 {np.quantile(v, 0.9):+.2f}"


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
    tx_bps = 1e4 * args.tx_usd / size
    routes = {}
    for r in rows:
        key = "+".join(r["buy_route"])
        routes[key] = routes.get(key, 0) + 1
    hours = {}
    for r, cost in zip(rows, rt_net):
        hours.setdefault(r["t"][:13], []).append(cost)
    print(f"{len(rows)} samples, {rows[0]['t']} .. {rows[-1]['t']}, ${size[0]:,.0f} per trade")
    print(f"on-chain round trip, bps (fees + impact, both legs):      {q(rt)}")
    print(f"  + network ${args.tx_usd}/tx x 2:                            {q(rt_net)}")
    print(f"  => per fill (half), comparable to jevtrader's columns: median {np.median(rt_net) / 2:.2f} bps, p90 {np.quantile(rt_net, 0.9) / 2:.2f} bps")
    print(f"buy leg vs Coinbase ask, bps (+ = worse than the ask):   {q(buy_vs_ask)}")
    print(f"sell leg vs Coinbase bid, bps (+ = worse than the bid):  {q(sell_vs_bid)}")
    print(f"Coinbase half-spread, bps:                               {q(cb_half_spread)}")
    print(f"Coinbase retail round trip at 90 bps taker: {2 * 90 + 2 * np.median(cb_half_spread):.1f} bps (2 x 90 + spread)")
    print(f"buy routes: {dict(sorted(routes.items(), key=lambda kv: -kv[1])[:5])}")
    rel = [(r["sol_out"], r["buy_reliable"]) for r in rows if r.get("buy_reliable")]
    if rel:
        print(f"buy quote vs Jupiter's 'most reliable' AMMs, bps (+ = best route better): {q([1e4 * (a / b - 1) for a, b in rel])}")
    print("per UTC hour, round trip incl. network, median bps: " + ", ".join(f"{h[11:13]}h {np.median(c):.2f} (n={len(c)})" for h, c in sorted(hours.items())))

    later = [r for r in rows if r.get("later")]
    if later:
        print(f"\nquote decay: {len(later)} samples re-quoted; slippage limit {SLIPPAGE_BPS} bps")
        print("  decay = how much worse the same trade's quote got (bps, + = worse); market = Coinbase mid move against the trade")
        print("  fill cost = per-fill cost of filling at the later quote, vs Coinbase mid at decision time, incl. network")
        for delay in sorted({lt["delay"] for r in later for lt in r["later"]}):
            pairs = [(r, lt) for r in later for lt in r["later"] if lt["delay"] == delay]
            buy_decay = np.array([1e4 * (1 - lt["sol_out"] / r["sol_out"]) for r, lt in pairs])
            sell_decay = np.array([1e4 * (1 - lt["usdc_back"] / r["usdc_back"]) for r, lt in pairs])
            mid0 = np.array([(r["cb_bid"] + r["cb_ask"]) / 2 for r, _ in pairs])
            mid1 = np.array([(lt["cb_bid"] + lt["cb_ask"]) / 2 for _, lt in pairs])
            move = 1e4 * (mid1 / mid0 - 1)  # + = SOL got dearer: bad for a buy, good for a sell
            buy_fill = 1e4 * ((np.array([r["size"] for r, _ in pairs]) / np.array([lt["sol_out"] for _, lt in pairs])) / mid0 - 1) + tx_bps
            sell_fill = 1e4 * (1 - (np.array([lt["usdc_back"] for _, lt in pairs]) / np.array([r["sol_out"] for r, _ in pairs])) / mid0) + tx_bps
            slots = np.array([lt["slot_buy"] - r["slot"] for r, lt in pairs if lt.get("slot_buy") and r.get("slot")])
            dt = np.median([lt["dt"] for _, lt in pairs])
            print(f"  +{delay:g} s (median {dt:.2f} s, {np.median(slots) if len(slots) else float('nan'):.0f} slots), n={len(pairs)}:")
            print(f"    buy decay {q(buy_decay)};  market {q(move)};  beyond market {q(buy_decay - move)}")
            print(f"    sell decay {q(sell_decay)};  market {q(-move)};  beyond market {q(sell_decay + move)}")
            fails = np.mean(buy_decay > SLIPPAGE_BPS) * 100, np.mean(sell_decay > SLIPPAGE_BPS) * 100
            print(f"    |decay| p90 buy {np.quantile(np.abs(buy_decay), 0.9):.2f} / sell {np.quantile(np.abs(sell_decay), 0.9):.2f} bps; would fail at {SLIPPAGE_BPS} bps: buy {fails[0]:.1f}%, sell {fails[1]:.1f}%")
            print(f"    fill cost per fill, bps: buy {q(buy_fill)}; sell {q(sell_fill)}; mean of both {np.mean((buy_fill + sell_fill) / 2):+.2f}")
    print("not priced: MEV/sandwich risk (limit with small size and tight slippage), failed transactions, USDC/USD basis")


sample() if args.mode == "sample" else summary()
