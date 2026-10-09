"""How many of a pool's PumpSwap swaps did the recorder capture? (public RPC drops notifications)

    python3 handoff/experiments/pumpswap_capture.py RAW_DIR POOL[:SLOTS] [POOL[:SLOTS] ...]

For each pool: the slot range of its recorded swaps (or the first SLOTS slots of it), every
transaction touching the pool in that range (getSignaturesForAddress, paginated), each decoded
for that pool's Buy/SellEvents, compared with the recorded swaps in the same slots.
"""
import gzip
import json
import sys
import time
from pathlib import Path

import httpx

sys.path.insert(0, ".")
from tartar.feeds.pumpswap import swap_events_from_logs, SwapTrade  # noqa: E402

RPC = "https://api.mainnet-beta.solana.com"
client = httpx.Client(timeout=30)


def rpc(method, params):
    for attempt in range(10):
        r = client.post(RPC, json={"jsonrpc": "2.0", "id": 1, "method": method, "params": params})
        if r.status_code == 429:
            time.sleep(2.0 * (attempt + 1))
            continue
        r.raise_for_status()
        body = r.json()
        if "error" in body:
            raise RuntimeError(body["error"])
        return body["result"]
    raise RuntimeError("rate limited")


def recorded(raw_dir, pool):
    slots = []
    for path in sorted(Path(raw_dir).glob("*.jsonl*")):
        opener = gzip.open if path.suffix == ".gz" else open
        with opener(path, "rt") as f:
            for line in f:
                if pool in line and '"swap"' in line:
                    try:
                        e = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if e.get("pool") == pool and e.get("slot"):
                        slots.append(e["slot"])
    return sorted(slots)


def onchain(pool, lo, hi):
    swaps, txs, before = 0, 0, None
    while True:
        params = {"limit": 1000} | ({"before": before} if before else {})
        sigs = rpc("getSignaturesForAddress", [pool, params])
        if not sigs:
            break
        for s in sigs:
            if s["slot"] > hi or s.get("err"):
                continue
            if s["slot"] < lo:
                return swaps, txs
            tx = rpc("getTransaction", [s["signature"], {"encoding": "json", "maxSupportedTransactionVersion": 1, "commitment": "confirmed"}])
            logs = ((tx or {}).get("meta") or {}).get("logMessages") or []
            n = sum(1 for e in swap_events_from_logs(logs) if isinstance(e, SwapTrade) and e.pool == pool)
            swaps += n
            txs += n > 0
            time.sleep(0.12)
        before = sigs[-1]["signature"]
        if sigs[-1]["slot"] < lo:
            break
    return swaps, txs


def main():
    raw_dir, specs = sys.argv[1], sys.argv[2:]
    total_rec = total_chain = 0
    for spec in specs:
        pool, _, span = spec.partition(":")
        slots = recorded(raw_dir, pool)
        if not slots:
            print(f"{pool[:8]}: no recorded swaps")
            continue
        lo, hi = slots[0], slots[-1]
        if span:
            hi = min(hi, lo + int(span))
        rec = sum(1 for s in slots if lo <= s <= hi)
        chain, txs = onchain(pool, lo, hi)
        total_rec += rec
        total_chain += chain
        print(f"{pool[:8]} slots {lo}..{hi} ({hi - lo}): recorded {rec}, on-chain {chain} swaps in {txs} txs -> captured {100 * rec / max(chain, 1):.1f}%")
    if total_chain:
        print(f"all: recorded {total_rec} of {total_chain} on-chain swaps = {100 * total_rec / total_chain:.1f}%")


if __name__ == "__main__":
    main()
