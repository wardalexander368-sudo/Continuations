"""Where in the block do a launch's same-slot buys sit, and are they bundled with the create? (§3.18)

    python3 handoff/experiments/same_slot_blocks.py handoff/data/same-slot/launches.jsonl.gz \
        [--dirs raw-v3,raw-clever2] [--n 150] [--out handoff/data/same-slot/blocks.jsonl]

Takes launches written by same_slot_entry.py that had at least one outside (non-creator)
trade in the creation slot, fetches each creation block from the public RPC (getBlock), and
for every transaction that touches the mint records its index in the block, fee payer,
priority fee (fee above 5,000 lamports per signature) and Jito tip (SOL received by one of
Jito's eight tip accounts). From those it classifies each outside same-slot buy:

* in the create's own transaction;
* contiguous with the create (no unrelated transaction between them): a Jito bundle is
  executed as one contiguous run, so this is the creator's bundle or something placed
  inside it;
* later in the block, with unrelated transactions in between: a buyer that reacted to the
  create inside the same slot, the entry an outsider would have to win.

Blocks are kept only as the summary lines; the public RPC keeps roughly the last few days.
"""
import argparse
import gzip
import json
import os
import random
import sys
import time
import urllib.request

RPC = os.environ.get("SOLANA_RPC_HTTP", "https://api.mainnet-beta.solana.com")
JITO_TIP = {
    "96gYZGLnJYVFmbjzopPSU6QiEV5fGqZNyN9nmNhvrZU5", "HFqU5x63VTqvQss8hp11i4wVV8bD44PvwucfZ2bU7gRe",
    "Cw8CFyM9FkoMi7K7Crf6HNQqf4uEMzpKw6QNghXLvLkY", "ADaUMid9yfUytqMBgopwjb2DTLSokTSzL1zt6iGPaS49",
    "DfXygSm4jCyNCybVYYK6DwvWqjKee8pbDmJGcLWNDXjh", "ADuUkR4vqLUMWXxW9gh6D6L8pMSawimctcNZ5pGwDcEt",
    "DttWaMuVvTiduZRnguLF7jNxTgiMBZ1hyAumKUiL2KRL", "3AVi9Tg9Uo68tJfuvoKvqKNWKkC5wPdSSdeBnizKZ6jT",
}

parser = argparse.ArgumentParser()
parser.add_argument("launches")
parser.add_argument("--dirs", default="raw-v3,raw-clever2")
parser.add_argument("--n", type=int, default=150)
parser.add_argument("--seed", type=int, default=0)
parser.add_argument("--out", default="handoff/data/same-slot/blocks.jsonl")
args = parser.parse_args()

dirs = set(args.dirs.split(","))
rows = [json.loads(line) for line in (gzip.open if args.launches.endswith(".gz") else open)(args.launches, "rt")]
pool = [r for r in rows if r["dir"] in dirs and r["complete"] and any(not x["dev"] for x in r["same_slot"])]
random.Random(args.seed).shuffle(pool)
done = set()
if os.path.exists(args.out):
    done = {json.loads(line)["mint"] for line in open(args.out)}
todo = [r for r in pool if r["mint"] not in done][: max(0, args.n - len(done))]
print(f"{len(pool)} launches with outside same-slot trades in {sorted(dirs)}; {len(done)} done, fetching {len(todo)}", file=sys.stderr)


def get_block(slot):
    body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "getBlock", "params": [slot, {
        "encoding": "json", "maxSupportedTransactionVersion": 1, "transactionDetails": "full", "rewards": False}]}).encode()
    for attempt in range(5):
        try:
            req = urllib.request.Request(RPC, body, {"content-type": "application/json"})
            out = json.loads(urllib.request.urlopen(req, timeout=90).read())
            if "result" in out:
                return out["result"]
            print(f"  slot {slot}: {out.get('error')}", file=sys.stderr)
            if out.get("error", {}).get("code") in (-32007, -32009, -32004):
                return None  # skipped / not available
        except Exception as exc:  # noqa: BLE001
            print(f"  slot {slot}: {exc}", file=sys.stderr)
        time.sleep(2 ** attempt)
    return None


def summarize(tx, i):
    msg, meta = tx["transaction"]["message"], tx["meta"]
    keys = msg["accountKeys"] + meta.get("loadedAddresses", {}).get("writable", []) + meta.get("loadedAddresses", {}).get("readonly", [])
    nsig = msg["header"]["numRequiredSignatures"]
    tip = 0
    for k, pre, post in zip(keys, meta["preBalances"], meta["postBalances"]):
        if k in JITO_TIP and post > pre:
            tip += post - pre
    return {"i": i, "payer": keys[0], "keys": set(keys), "prio": meta["fee"] - 5000 * nsig, "tip": tip,
            "err": meta["err"] is not None}


with open(args.out, "a") as f:
    for n, r in enumerate(todo):
        blk = get_block(r["slot"])
        if blk is None:
            continue
        txs = blk["transactions"]
        hits = []
        for i, tx in enumerate(txs):
            s = summarize(tx, i)
            if r["mint"] in s["keys"]:
                s.pop("keys")
                hits.append(s)
        out = {"mint": r["mint"], "slot": r["slot"], "dir": r["dir"], "creator": r["creator"], "block_txs": len(txs),
               "nonvote_txs": sum(1 for tx in txs if "Vote111111111111111111111111111111111111111" not in tx["transaction"]["message"]["accountKeys"]),
               "touching": hits, "same_slot": r["same_slot"]}
        f.write(json.dumps(out) + "\n")
        f.flush()
        print(f"  {n + 1}/{len(todo)} slot {r['slot']}: {len(hits)} txs touch the mint, indices {[h['i'] for h in hits][:12]}", file=sys.stderr)
        time.sleep(0.5)
