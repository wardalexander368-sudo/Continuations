"""Real fills through Jupiter's Swap API, signed by our own key: no Lightning 1%/side fee. (§3.19)

    python3 handoff/experiments/jupiter_fills.py dry --mint MINT [--size 0.01]
    python3 handoff/experiments/jupiter_fills.py roundtrip --mint MINT --real [--size 0.01] [--trips 2]
        [--hold 30] [--slippage-bps 300] [--priority 0.00002] [--out data/real-fills/jupiter.jsonl]
    python3 handoff/experiments/real_fills.py summary --out data/real-fills/jupiter.jsonl   # same log format

`dry` needs no key and sends nothing: it builds the buy for a stand-in wallet and has the RPC simulate
it (as execution_routes.py does). `roundtrip` is REAL MONEY: it needs the user's go-ahead in STATUS,
the wallet's base58 secret key in the environment variable TARTAR_WALLET_KEY (an environment secret,
never in chat, the repo or logs), and `--real`. Caps as in real_fills.py: at most 0.02 SOL per buy and
5 round trips per run.

Route: Jupiter Swap API v1 quote + swap transaction (no platform fee; fees are the pool's own), signed
locally with solders and sent through the RPC (`SOLANA_RPC_HTTP`, default the public endpoint). Set
`JUPITER_API_KEY` to use api.jup.ag (free tier 1 request/s); without it the keyless lite-api host is used,
which Jupiter is phasing out.
"""
import argparse
import base64
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import httpx
from solders.hash import Hash
from solders.instruction import AccountMeta, Instruction
from solders.keypair import Keypair
from solders.message import MessageV0
from solders.pubkey import Pubkey
from solders.transaction import VersionedTransaction

RPC = os.environ.get("SOLANA_RPC_HTTP", "https://api.mainnet-beta.solana.com")
JUP_KEY = os.environ.get("JUPITER_API_KEY")
JUP = "https://api.jup.ag" if JUP_KEY else "https://lite-api.jup.ag"
SOL = "So11111111111111111111111111111111111111112"
STAND_IN = "9WzDXwBbmkg8ZTbNMqUxvQRAyrZzDsGYdLVL9zYtAWWM"  # dry runs simulate as this wallet; we never hold its key
MAX_SIZE, MAX_TRIPS = 0.02, 5

ap = argparse.ArgumentParser()
ap.add_argument("mode", choices=("dry", "roundtrip"))
ap.add_argument("--mint", required=True)
ap.add_argument("--size", type=float, default=0.01, help="SOL per buy")
ap.add_argument("--trips", type=int, default=2)
ap.add_argument("--hold", type=float, default=30.0)
ap.add_argument("--slippage-bps", type=int, default=300)
ap.add_argument("--priority", type=float, default=0.00002, help="SOL priority fee per transaction")
ap.add_argument("--real", action="store_true")
ap.add_argument("--out", default="data/real-fills/jupiter.jsonl")
args = ap.parse_args()
client = httpx.Client(timeout=30, headers={"x-api-key": JUP_KEY} if JUP_KEY else None)
rpc_client = httpx.Client(timeout=30)


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def rpc(method: str, params: list):
    for wait in (1, 2, 4, 8, 16, 0):
        r = rpc_client.post(RPC, json={"jsonrpc": "2.0", "id": 1, "method": method, "params": params})
        if r.status_code != 429 or not wait:
            break
        time.sleep(wait)
    r.raise_for_status()
    body = r.json()
    if body.get("error"):
        raise RuntimeError(f"{method}: {body['error']}")
    return body.get("result")


def build(input_mint: str, output_mint: str, amount: int, wallet: str) -> tuple[dict, bytes]:
    """Jupiter quote and the unsigned swap transaction for `wallet`."""
    q = client.get(f"{JUP}/swap/v1/quote", params={"inputMint": input_mint, "outputMint": output_mint, "amount": amount,
                                                    "slippageBps": args.slippage_bps})
    q.raise_for_status()
    quote = q.json()
    s = client.post(f"{JUP}/swap/v1/swap", json={
        "quoteResponse": quote, "userPublicKey": wallet, "dynamicComputeUnitLimit": True,
        "prioritizationFeeLamports": int(round(args.priority * 1e9))})
    s.raise_for_status()
    return quote, base64.b64decode(s.json()["swapTransaction"])


def ref(quote: dict) -> dict:
    return {"out": int(quote["outAmount"]), "route": [p["swapInfo"].get("label") for p in quote.get("routePlan", [])],
            "slot": quote.get("contextSlot")}


def confirm(signature: str, timeout: float = 90.0):
    end = time.time() + timeout
    while time.time() < end:
        st = rpc("getSignatureStatuses", [[signature], {"searchTransactionHistory": True}])["value"][0]
        if st and st.get("confirmationStatus") in ("confirmed", "finalized"):
            seen = time.time()
            for _ in range(20):
                tx = rpc("getTransaction", [signature, {"encoding": "jsonParsed", "maxSupportedTransactionVersion": 1,
                                                        "commitment": "confirmed"}])
                if tx:
                    return tx, seen
                time.sleep(1.0)
            return None, seen
        time.sleep(0.5)
    return None, None


def effects(tx: dict, mint: str) -> dict:
    """Same fields as real_fills.py's effects(), so its summary reads this log."""
    meta, msg = tx["meta"], tx["transaction"]["message"]
    keys = [k["pubkey"] if isinstance(k, dict) else k for k in msg["accountKeys"]]
    wallet = keys[0]

    def tokens(balances):
        return sum(float(b["uiTokenAmount"]["uiAmount"] or 0) for b in balances or [] if b.get("mint") == mint and b.get("owner") == wallet)

    rent = 0.0
    for i in range(1, len(keys)):
        if meta["preBalances"][i] == 0 and meta["postBalances"][i] > 0:
            if any(b.get("accountIndex") == i and b.get("owner") == wallet for b in meta.get("postTokenBalances") or []):
                rent += meta["postBalances"][i] / 1e9
    return {"wallet": wallet, "slot": tx["slot"], "err": meta.get("err"), "fee_sol": meta["fee"] / 1e9,
            "sol_change": (meta["postBalances"][0] - meta["preBalances"][0]) / 1e9,
            "token_change": tokens(meta.get("postTokenBalances")) - tokens(meta.get("preTokenBalances")),
            "ata_rent_sol": rent, "cu": meta.get("computeUnitsConsumed")}


def log(row: dict) -> None:
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("a") as f:
        f.write(json.dumps(row) + "\n")
    print(json.dumps(row)[:600], flush=True)


def leg(kind: str, keypair: Keypair, amount: int) -> dict:
    wallet = str(keypair.pubkey())
    pair = (SOL, args.mint) if kind == "buy" else (args.mint, SOL)
    quote, raw = build(*pair, amount, wallet)
    unsigned = VersionedTransaction.from_bytes(raw)
    signed = VersionedTransaction(unsigned.message, [keypair])
    t0 = time.time()
    sig = rpc("sendTransaction", [base64.b64encode(bytes(signed)).decode(), {"encoding": "base64", "maxRetries": 5,
                                                                              "preflightCommitment": "processed"}])
    t1 = time.time()
    row = {"t": now(), "leg": kind, "route": "jupiter", "mint": args.mint, "amount": amount / 1e9 if kind == "buy" else "100%",
           "priority": args.priority, "slippage_bps": args.slippage_bps, "quote": ref(quote),
           "response": {"signature": sig}, "sent_at": t0, "answered_at": t1}
    tx, seen = confirm(sig)
    row["confirmed_at"] = seen
    if tx is not None:
        row["effects"] = effects(tx, args.mint)
        row["block_time"] = tx.get("blockTime")
    log(row)
    return row


def held_raw(wallet: str) -> int:
    res = rpc("getTokenAccountsByOwner", [wallet, {"mint": args.mint}, {"encoding": "jsonParsed"}])["value"]
    return sum(int(a["account"]["data"]["parsed"]["info"]["tokenAmount"]["amount"]) for a in res)


def close_empty(keypair: Keypair) -> None:
    """Close the wallet's now-empty token accounts for --mint: their rent (~0.0015-0.002 SOL each) comes back.
    Lightning cannot do this (no close in its API), which is why the CATE test left 0.0015 SOL parked."""
    owner = keypair.pubkey()
    res = rpc("getTokenAccountsByOwner", [str(owner), {"mint": args.mint}, {"encoding": "jsonParsed"}])["value"]
    ixs = [Instruction(Pubkey.from_string(a["account"]["owner"]), bytes([9]),  # CloseAccount (SPL Token and Token-2022)
                       [AccountMeta(Pubkey.from_string(a["pubkey"]), False, True), AccountMeta(owner, False, True),
                        AccountMeta(owner, True, False)])
           for a in res if int(a["account"]["data"]["parsed"]["info"]["tokenAmount"]["amount"]) == 0]
    if not ixs:
        return
    blockhash = Hash.from_string(rpc("getLatestBlockhash", [{"commitment": "confirmed"}])["value"]["blockhash"])
    tx = VersionedTransaction(MessageV0.try_compile(owner, ixs, [], blockhash), [keypair])
    sig = rpc("sendTransaction", [base64.b64encode(bytes(tx)).decode(), {"encoding": "base64", "maxRetries": 5}])
    confirmed, seen = confirm(sig)
    log({"t": now(), "leg": "close", "mint": args.mint, "response": {"signature": sig}, "accounts": len(ixs),
         "effects": effects(confirmed, args.mint) if confirmed else None})


def dry() -> None:
    quote, raw = build(SOL, args.mint, int(args.size * 1e9), STAND_IN)
    res = rpc("simulateTransaction", [base64.b64encode(raw).decode(), {"encoding": "base64", "sigVerify": False,
                                                                       "replaceRecentBlockhash": True}])["value"]
    print(json.dumps({"route": ref(quote)["route"], "out": quote["outAmount"], "platformFee": quote.get("platformFee"),
                      "price_impact_pct": quote.get("priceImpactPct"), "simulation_err": res.get("err"),
                      "units": res.get("unitsConsumed"), "tx_bytes": len(raw)}))


def roundtrip() -> None:
    if not args.real:
        sys.exit("refusing: pass --real to send real trades")
    if not 0 < args.size <= MAX_SIZE or not 1 <= args.trips <= MAX_TRIPS:
        sys.exit(f"caps: size in (0, {MAX_SIZE}] SOL, trips in [1, {MAX_TRIPS}]")
    secret = os.environ.get("TARTAR_WALLET_KEY")
    if not secret:
        sys.exit("TARTAR_WALLET_KEY is not set (the wallet's base58 secret key, as an environment secret)")
    keypair = Keypair.from_base58_string(secret.strip())
    del secret
    for k in range(args.trips):
        buy = leg("buy", keypair, int(args.size * 1e9))
        eff = buy.get("effects")
        if not eff or eff.get("err") or eff["token_change"] <= 0:
            print("buy did not fill; stopping", flush=True)
            return
        time.sleep(args.hold)
        sell = leg("sell", keypair, held_raw(str(keypair.pubkey())))
        if not sell.get("effects") or sell["effects"].get("err"):
            print("sell did not confirm; stopping (tokens may still be held)", flush=True)
            return
        print(f"round trip {k + 1}: in {-eff['sol_change']:.6f} SOL, back {sell['effects']['sol_change']:.6f} SOL", flush=True)
        close_empty(keypair)
        time.sleep(5)


{"dry": dry, "roundtrip": roundtrip}[args.mode]()
