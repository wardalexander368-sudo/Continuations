"""PumpSwap fees per side, from recorded swaps of graduated pump.fun tokens.

    python3 handoff/experiments/pumpswap_fees.py handoff/data/raw-pumpswap [more dirs...]
    python3 handoff/experiments/pumpswap_fees.py --cohort handoff/preregistration/dip-rolling/cohort-*.json [--tx 40]
    python3 handoff/experiments/pumpswap_fees.py --pools POOL1,POOL2 [--tx 40]
    ... --cohort FILE --save handoff/preregistration/dip-rolling/fees-measured.json   # merge per-pool fees into FILE

With `--cohort` or `--pools`, the latest `--tx` transactions of each pool are fetched over
public RPC and the fee basis points the program writes into each BuyEvent/SellEvent (LP,
protocol, coin creator) are tabulated per pool, with its market cap in SOL.

Each `swap` event (tartar/data/rawlog.py) carries the SOL that moved through the pool
(`sol`), what the trader paid or received with every fee (`paid`), and the pool's effective
reserves after the trade (`tok_after`, `sol_after`). That is enough to recover each fee
without the program's fee fields:

* pre-trade reserves: buy (tok_after + tok, sol_after - sol); sell (tok_after - tok, sol_after + sol)
* the constant-product amount, before any fee: buy  q = sol_pre * tok / tok_after
                                               sell q = sol_pre * tok / tok_after
* buy:  sol  = q + LP fee;            paid = q + LP + protocol + creator
* sell: sol  = q - LP fee (leaves);   paid = q - LP - protocol - creator

So LP = |sol - q|, protocol + creator = |paid - sol|, all as a share of q. Rounding makes
tiny swaps noisy, so only swaps of at least 0.05 SOL are summarized. Market cap is
price x 1e9 tokens (pump.fun supply), in SOL.
"""
import argparse
import gzip
import json
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np

sys.path.insert(0, ".")

MIN_SOL = 0.05
SUPPLY = 1e9


def swaps(dirs):
    for d in dirs:
        for path in sorted(Path(d).glob("*.jsonl*")):
            opener = gzip.open if path.suffix == ".gz" else open
            with opener(path, "rt") as f:
                for line in f:
                    if '"swap"' in line:
                        e = json.loads(line)
                        if e.get("e") == "swap":
                            yield e


def fee_rows(dirs):
    for e in swaps(dirs):
        tok, sol, paid, ta, sa = e["tok"], e["sol"], e["paid"], e["tok_after"], e["sol_after"]
        if not (tok and sol and paid and ta and sa) or sol < MIN_SOL:
            continue
        buy = e["side"] == "b"
        sol_pre = sa - sol if buy else sa + sol
        q = sol_pre * tok / ta
        if q <= 0:
            continue
        lp = (sol - q) / q if buy else (q - sol) / q
        other = (paid - sol) / q if buy else (sol - paid) / q
        yield {"buy": buy, "lp": lp, "other": other, "total": lp + other, "mcap": SUPPLY * sa / ta, "pool": e["pool"], "sol": sol}


def main(dirs):
    rows = list(fee_rows(dirs))
    if not rows:
        print("no swaps")
        return
    pools = {r["pool"] for r in rows}
    print(f"{len(rows)} swaps of >= {MIN_SOL} SOL in {len(pools)} pools")
    pct = lambda v: f"median {100 * np.median(v):.3f}%  p10 {100 * np.quantile(v, 0.1):.3f}%  p90 {100 * np.quantile(v, 0.9):.3f}%"  # noqa: E731
    for side in (True, False):
        sel = [r for r in rows if r["buy"] == side]
        if not sel:
            continue
        print(f"\n{'buys' if side else 'sells'} (n={len(sel)}):")
        for key in ("lp", "other", "total"):
            print(f"  {key:>6}: {pct([r[key] for r in sel])}")
    print("\nby market cap (SOL), total fee per side, median [p10, p90], swaps / pools:")
    edges = [0, 300, 500, 750, 1000, 2000, 5000, 1e12]
    buckets = defaultdict(list)
    for r in rows:
        i = np.searchsorted(edges, r["mcap"], side="right") - 1
        buckets[i].append(r)
    for i in sorted(buckets):
        sel = buckets[i]
        tot = [r["total"] for r in sel]
        lp = [r["lp"] for r in sel]
        print(
            f"  {edges[i]:>6.0f}-{edges[i + 1]:<6.0f} total {100 * np.median(tot):.3f}% [{100 * np.quantile(tot, 0.1):.3f}, {100 * np.quantile(tot, 0.9):.3f}]"
            f"  lp {100 * np.median(lp):.3f}%  ({len(sel)} / {len({r['pool'] for r in sel})})"
        )
    # Distinct fee levels: rounded to 0.01%, the most common values of the total
    levels = defaultdict(int)
    for r in rows:
        levels[round(100 * r["total"], 2)] += 1
    print("\nmost common total fee levels (%): " + ", ".join(f"{k:.2f}: {v}" for k, v in sorted(levels.items(), key=lambda kv: -kv[1])[:8]))


def event_bps(data: bytes):
    """(lp, protocol, creator) fee bps from a PumpSwap BuyEvent/SellEvent payload (layout: tartar/feeds/pumpswap.py)."""
    from tartar.feeds.pumpchain import _Reader

    r = _Reader(data)
    r.i64()
    for _ in range(6):
        r.u64()  # base amount, max/min quote, user base/quote reserves, pool base/quote reserves
    r.u64()  # quote amount in/out
    lp_bps = (r.u64(), r.u64())[0]
    protocol_bps = (r.u64(), r.u64())[0]
    r.u64(), r.u64()  # liquidity quote, user quote
    for _ in range(7):
        r.key()  # pool, user, 4 token accounts / fee recipient, coin creator
    creator_bps = r.u64()
    return lp_bps, protocol_bps, creator_bps


def pool_fees(pools, n_tx, rpc_url="https://api.mainnet-beta.solana.com"):
    import httpx

    from tartar.feeds.pumpchain import program_data
    from tartar.feeds.pumpswap import BUY, PUMP_AMM, SELL, decode_swap_event

    client = httpx.Client(timeout=20)

    def rpc(method, params):
        for attempt in range(8):
            r = client.post(rpc_url, json={"jsonrpc": "2.0", "id": 1, "method": method, "params": params})
            if r.status_code == 429:
                time.sleep(1.5 * (attempt + 1))
                continue
            r.raise_for_status()
            body = r.json()
            if "error" in body:
                raise RuntimeError(body["error"])
            return body["result"]
        raise RuntimeError("rate limited")

    measured = {}
    print(f"{'pool':<10} {'name':<22} {'swaps':>5} {'mcap SOL':>12} {'fee':>6}  fee bps (lp, protocol, creator): count")
    for pool, name in pools:
        sigs = rpc("getSignaturesForAddress", [pool, {"limit": n_tx}])
        levels, mcaps, totals = Counter(), [], []
        for s in sigs:
            if s.get("err"):
                continue
            tx = rpc("getTransaction", [s["signature"], {"encoding": "json", "maxSupportedTransactionVersion": 1, "commitment": "confirmed"}])
            logs = ((tx or {}).get("meta") or {}).get("logMessages") or []
            for data in program_data(logs, PUMP_AMM):
                if data[:8] not in (BUY, SELL):
                    continue
                trade = decode_swap_event(data)
                if trade is None or trade.pool != pool:
                    continue
                try:
                    bps = event_bps(data)
                except ValueError:
                    continue
                levels[bps] += 1
                if sum(bps) > 0:  # fee-exempt swaps carry zeros
                    totals.append(sum(bps))
                mcaps.append(SUPPLY * trade.price)
            time.sleep(0.15)
        mcap = f"{np.median(mcaps):,.0f}" if mcaps else "-"
        total = f"{np.median(totals) / 100:.2f}%" if totals else "-"
        print(f"{pool[:8]:<10} {name[:22]:<22} {sum(levels.values()):>5} {mcap:>12} {total:>6}  " + ", ".join(f"{k}: {v}" for k, v in levels.most_common(3)))
        if totals:
            paying = Counter({k: v for k, v in levels.items() if sum(k) > 0})
            measured[pool] = {
                "name": name, "fee_per_side": float(np.median(totals)) / 1e4, "bps_lp_protocol_creator": list(paying.most_common(1)[0][0]),
                "mcap_sol": round(float(np.median(mcaps))), "swaps": sum(levels.values()),
                "measured_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            }  # fmt: skip
    return measured


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("dirs", nargs="*")
    parser.add_argument("--cohort", nargs="*", default=[])
    parser.add_argument("--pools", default="")
    parser.add_argument("--tx", type=int, default=40)
    parser.add_argument("--save", default="", help="JSON file to merge per-pool measured fees into (pool -> fee)")
    a = parser.parse_args()
    pools = [(p, "") for p in a.pools.split(",") if p]
    for path in a.cohort:
        pools += [(p["pool"], p.get("name", "")) for p in json.loads(Path(path).read_text())["pools"]]
    if pools:
        measured = pool_fees(pools, a.tx)
        if a.save:
            path = Path(a.save)
            merged = json.loads(path.read_text()) if path.exists() else {}
            merged.update(measured)
            path.write_text(json.dumps(merged, indent=1, sort_keys=True) + "\n")
            print(f"{len(measured)} pools saved to {path}")
    else:
        main(a.dirs or ["handoff/data/raw-pumpswap"])
