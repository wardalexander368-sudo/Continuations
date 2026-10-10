"""What does each way of sending a swap charge on top of the pool? Read-only, no keys, no SOL. (§3.19)

    python3 handoff/experiments/execution_routes.py --mint MINT [--pool pump-amm|pump] [--size 0.1]
        [--wallet PUBKEY] [--out handoff/data/exec-routes/routes.jsonl]

For one buy of `size` SOL it asks each route for a ready transaction, then has the public RPC
*simulate* it (sigVerify off, recent blockhash replaced) as if `wallet` had sent it. Nothing is
signed or sent: `wallet` is any account holding enough SOL (default: a large exchange wallet),
whose key we never have. Route fees paid in SOL show as top-level System transfers;
fees taken inside a program (Jupiter Ultra's) show as fewer tokens. From each simulation it reads the tokens the wallet would receive and
every lamport that leaves the wallet, split into the pool/curve, rent, network fee and transfers to
third parties (route fees, tips). Routes:

* `pumpportal-local`: PumpPortal's Local Transaction API (`/api/trade-local`), which returns an
  unsigned transaction we would sign ourselves. Not `/api/trade` (Lightning), which executes.
* `jupiter-metis`: Jupiter's Swap API (`lite-api.jup.ag/swap/v1`, quote + swap transaction).
* `jupiter-ultra`: Jupiter Ultra (`lite-api.jup.ag/ultra/v1/order`), when it returns a transaction
  for the wallet; its `feeBps` is recorded too.

Tokens received per SOL that left the wallet for the swap and its fees (system and wSOL transfers,
from the simulation's inner instructions; rent and network fee excluded), against the best route, is the comparison that counts: a route that
skims a fee or routes worse gives fewer tokens for the same SOL. Lightning (`/api/trade`) cannot be
simulated; its fee is 1% per trade (pumpportal.fun/fees) and the real fills measured it
(STATUS REAL MONEY entry, 2026-10-09).
"""
import argparse
import base64
import json
import os
import sys
import time
from datetime import datetime, timezone

import httpx
from solders.pubkey import Pubkey
from solders.transaction import VersionedTransaction

RPC = os.environ.get("SOLANA_RPC_HTTP", "https://api.mainnet-beta.solana.com")
SOL = "So11111111111111111111111111111111111111112"
JUP = "https://lite-api.jup.ag"
WALLET = "9WzDXwBbmkg8ZTbNMqUxvQRAyrZzDsGYdLVL9zYtAWWM"  # a large, rarely active wallet: only simulated as

ap = argparse.ArgumentParser()
ap.add_argument("--mint", required=True)
ap.add_argument("--pool", default="pump-amm", help="PumpPortal pool name: pump (curve), pump-amm, auto")
ap.add_argument("--size", type=float, default=0.1)
ap.add_argument("--wallet", default=WALLET)
ap.add_argument("--priority", type=float, default=0.00002)
ap.add_argument("--out", default="handoff/data/exec-routes/routes.jsonl")
args = ap.parse_args()
http = httpx.Client(timeout=30)
TOKEN = Pubkey.from_string("TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA")
ATA = Pubkey.from_string("ATokenGPvbdJVxr1b9hDzBu1ufbCrzRaH3RNe1g3K2e7")
WSOL_ATA = str(Pubkey.find_program_address(
    [bytes(Pubkey.from_string(args.wallet)), bytes(TOKEN), bytes(Pubkey.from_string(SOL))], ATA)[0])
# accounts that received PumpPortal's 0.5% in these simulations (one per pool type, it seems)
PUMPPORTAL_FEE = {"7FeFBYbewCqXG7LP6gC8Fnqzk7hmQFMtntXVRqnXi4g6", "FgX1cdFq7khWeivEfHCULBA6ovtSr9djdAfJ9r3LvNST"}
lamports = int(round(args.size * 1e9))


def rpc(method, params):
    for attempt in range(5):
        r = http.post(RPC, json={"jsonrpc": "2.0", "id": 1, "method": method, "params": params})
        if r.status_code == 429:
            time.sleep(2 ** attempt)
            continue
        out = r.json()
        if "error" in out:
            raise RuntimeError(out["error"])
        return out["result"]
    raise RuntimeError("rate limited")


def simulate(raw: bytes):
    tx = VersionedTransaction.from_bytes(raw)
    msg = tx.message
    keys = [str(k) for k in msg.account_keys]
    transfers, cu_price, cu_limit = [], 0, 200_000
    for ix in msg.instructions:
        prog, data = keys[ix.program_id_index], bytes(ix.data)
        if prog == "11111111111111111111111111111111" and data[:4] == (2).to_bytes(4, "little"):
            transfers.append((keys[ix.accounts[1]], int.from_bytes(data[4:12], "little") / 1e9))
        elif prog == "ComputeBudget111111111111111111111111111111":
            if data[0] == 3:
                cu_price = int.from_bytes(data[1:9], "little")
            elif data[0] == 2:
                cu_limit = int.from_bytes(data[1:5], "little")
    res = rpc("simulateTransaction", [base64.b64encode(raw).decode(), {
        "encoding": "base64", "sigVerify": False, "replaceRecentBlockhash": True, "commitment": "processed",
        "innerInstructions": True,
        "accounts": {"encoding": "jsonParsed", "addresses": keys[:min(len(keys), 64)]}}])
    v = res["value"]
    out = {"err": v.get("err"), "units": v.get("unitsConsumed"), "logs_tail": (v.get("logs") or [])[-3:],
           "n_accounts": len(keys), "sol_transfers": transfers,
           "priority_sol": cu_price * cu_limit / 1e15, "tx_bytes": len(raw)}
    if v.get("err") or not v.get("accounts"):
        return out
    pre = {k: a["lamports"] if a else 0 for k, a in zip(keys, rpc("getMultipleAccounts", [keys[:64], {"encoding": "base64"}])["value"])}
    post = {}
    tokens = 0.0
    owned = {WSOL_ATA}
    for k, a in zip(keys, v["accounts"]):
        if a is None or a["lamports"] == 0:
            owned.add(k)  # closed by the end of the transaction: a temporary wSOL account
            continue
        post[k] = a["lamports"]
        data = a.get("data")
        if isinstance(data, dict) and data.get("parsed", {}).get("type") == "account":
            info = data["parsed"]["info"]
            if info.get("owner") == args.wallet:
                owned.add(k)
            if info.get("mint") == args.mint and info.get("owner") == args.wallet:
                tokens = float(info["tokenAmount"]["uiAmountString"])
    deltas = {k: post.get(k, 0) - pre.get(k, 0) for k in set(pre) | set(post)}
    out["tokens"] = tokens
    # SOL leaving the wallet for the swap and its fees: system transfers to accounts that are not the
    # wallet's own wSOL account, plus wSOL token transfers out of that account (rent for new accounts
    # and the network fee are not counted)
    flows = [(d, x) for d, x in transfers if d not in owned]
    for group in v.get("innerInstructions") or []:
        for ix in group["instructions"]:
            p = ix.get("parsed")
            if not isinstance(p, dict):
                continue
            info = p.get("info", {})
            if ix.get("program") == "system" and p.get("type") == "transfer" and info.get("source") == args.wallet \
                    and info.get("destination") not in owned:
                flows.append((info["destination"], info["lamports"] / 1e9))
            elif ix.get("program") == "spl-token" and p.get("type") in ("transfer", "transferChecked") \
                    and info.get("source") in owned and info.get("destination") not in owned:
                amt = info.get("amount") or info.get("tokenAmount", {}).get("amount")
                flows.append((info["destination"], int(amt) / 1e9))
    dests = sorted({d for d, _ in flows})
    exists = {d for d, a in zip(dests, rpc("getMultipleAccounts", [dests, {"encoding": "base64", "dataSlice": {"offset": 0, "length": 0}}])["value"]) if a}
    flows = [(d, x) for d, x in flows if d in exists]  # funding an account that does not exist yet is rent, not swap cost
    out["swap_sol"] = round(sum(x for _, x in flows), 9)
    out["route_fee_sol"] = round(sum(x for d, x in flows if d in PUMPPORTAL_FEE), 9)
    out["flows"] = [(d, round(x, 9)) for d, x in flows]
    # accounts this transaction creates (rent): zero lamports before, some after
    out["new_accounts_sol"] = round(sum(post[k] for k in post if pre.get(k, 0) == 0 and k != args.wallet) / 1e9, 9)
    return out


def pumpportal_local():
    r = http.post("https://pumpportal.fun/api/trade-local", json={
        "publicKey": args.wallet, "action": "buy", "mint": args.mint, "amount": args.size,
        "denominatedInSol": "true", "slippage": 10, "priorityFee": args.priority, "pool": args.pool})
    if r.status_code != 200:
        return {"error": f"{r.status_code} {r.text[:200]}"}
    return simulate(r.content)


def jupiter_metis():
    q = http.get(f"{JUP}/swap/v1/quote", params={"inputMint": SOL, "outputMint": args.mint, "amount": lamports,
                                                    "slippageBps": 1000}).json()
    if "outAmount" not in q:
        return {"error": str(q)[:200]}
    s = http.post(f"{JUP}/swap/v1/swap", json={"quoteResponse": q, "userPublicKey": args.wallet,
                                                 "prioritizationFeeLamports": int(args.priority * 1e9),
                                                 "dynamicComputeUnitLimit": True}).json()
    if "swapTransaction" not in s:
        return {"error": str(s)[:200]}
    out = simulate(base64.b64decode(s["swapTransaction"]))
    out["route"] = [p["swapInfo"].get("label") for p in q.get("routePlan", [])]
    out["platform_fee"] = q.get("platformFee")
    return out


def jupiter_ultra():
    o = http.get(f"{JUP}/ultra/v1/order", params={"inputMint": SOL, "outputMint": args.mint, "amount": lamports,
                                                     "taker": args.wallet})
    try:
        o = o.json()
    except ValueError:
        return {"error": o.text[:200]}
    out = {"feeBps": o.get("feeBps"), "router": o.get("router"), "swapType": o.get("swapType"),
           "outAmount": o.get("outAmount"), "route": [p["swapInfo"].get("label") for p in o.get("routePlan") or []]}
    if o.get("transaction"):
        out.update(simulate(base64.b64decode(o["transaction"])))
    else:
        out["error"] = o.get("errorMessage") or o.get("error")
    return out


row = {"t": datetime.now(timezone.utc).isoformat(timespec="seconds"), "mint": args.mint, "pool": args.pool,
       "size": args.size, "wallet": args.wallet, "routes": {}}
for name, f in (("pumpportal-local", pumpportal_local), ("jupiter-metis", jupiter_metis), ("jupiter-ultra", jupiter_ultra)):
    try:
        row["routes"][name] = f()
    except Exception as exc:  # noqa: BLE001
        row["routes"][name] = {"error": repr(exc)[:300]}
for r in row["routes"].values():
    if r.get("tokens") and r.get("swap_sol"):
        r["tokens_per_sol"] = r["tokens"] / r["swap_sol"]
        if r.get("feeBps"):  # Ultra takes its fee inside the swap: already in fewer tokens
            pass
best = max((r.get("tokens_per_sol") or 0) for r in row["routes"].values())
for name, r in row["routes"].items():
    if r.get("tokens_per_sol"):
        r["vs_best_bps"] = round(1e4 * (r["tokens_per_sol"] / best - 1), 1)
    print(f"{name:17s} tokens {r.get('tokens')}  vs best {r.get('vs_best_bps')} bps  feeBps {r.get('feeBps')}"
          f"  err {r.get('err') or r.get('error')}  route {r.get('route')}")
    print(f"      SOL into the swap {r.get('swap_sol')} (PumpPortal fee {r.get('route_fee_sol')})  flows {r.get('flows')}")
    print(f"      SOL transfers {r.get('sol_transfers')}  priority {r.get('priority_sol')}  new accounts {r.get('new_accounts_sol')} SOL")
os.makedirs(os.path.dirname(args.out), exist_ok=True)
with open(args.out, "a") as f:
    f.write(json.dumps(row) + "\n")
