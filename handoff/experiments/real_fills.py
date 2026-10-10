"""Real fills through PumpPortal's Lightning API: measure what a round trip really costs.

    python3 handoff/experiments/real_fills.py probe
    python3 handoff/experiments/real_fills.py roundtrip --mint MINT --real [--size 0.01] [--trips 2]
        [--hold 30] [--slippage 5] [--priority 0.00002] [--pool pump-amm] [--out data/real-fills/fills.jsonl]
    python3 handoff/experiments/real_fills.py summary [--out data/real-fills/fills.jsonl]

REAL MONEY. The user funded the PumpPortal Lightning wallet (~0.05 SOL) and asked for cost
measurements first (STATUS, 2026-10-09 ~17:05 UTC). Only the clever session sends trades
(STATUS). The API key comes from the environment variable PUMPPORTAL_API_KEY (an environment
secret; never printed or logged). The cloud proxy's PumpPortal injection did not reach
/api/trade when tested (403 "Must supply a valid API key", 2026-10-09 17:15 UTC).

Each leg records: the Jupiter quote just before sending (the market reference), the request and
response times, when the transaction confirmed (slot and wall time), and from the confirmed
transaction itself: the wallet's SOL change, its token change, the network fee (base + priority)
and any token-account rent. Net cost of a round trip = SOL in - SOL back, in bps of SOL in;
the breakdown against the quotes separates fees from slippage.

`probe` asks PumpPortal to sell a token this wallet does not hold, with simulation on: it cannot
execute, and the error shows whether the API key reached PumpPortal.

Caps: at most 0.02 SOL per buy and 5 round trips per run; `--real` is required to send anything.
"""
import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import httpx

TRADE = "https://pumpportal.fun/api/trade"
JUP = "https://lite-api.jup.ag/swap/v1/quote"
RPC = os.environ.get("SOLANA_RPC_HTTP", "https://api.mainnet-beta.solana.com")
SOL = "So11111111111111111111111111111111111111112"
MAX_SIZE, MAX_TRIPS = 0.02, 5
PROBE_MINT = "HXqxTwCzREUXNK4CbNDgNEUEh2jLzFKdC4tvTuojpump"  # any token the wallet does not hold

ap = argparse.ArgumentParser()
ap.add_argument("mode", choices=("probe", "roundtrip", "summary", "buy", "sell", "record"))
ap.add_argument("--sig", help="record: signature of a leg that was sent but not logged")
ap.add_argument("--leg", choices=("buy", "sell"), help="record: which leg --sig was")
ap.add_argument("--mint")
ap.add_argument("--size", type=float, default=0.01, help="SOL per buy")
ap.add_argument("--trips", type=int, default=2)
ap.add_argument("--hold", type=float, default=30.0, help="seconds between buy confirmation and sell")
ap.add_argument("--slippage", type=float, default=5.0, help="percent")
ap.add_argument("--priority", type=float, default=0.00002, help="SOL priority fee per transaction")
ap.add_argument("--pool", default="pump-amm")
ap.add_argument("--real", action="store_true", help="required to send real trades")
ap.add_argument("--out", default="data/real-fills/fills.jsonl")
args = ap.parse_args()
client = httpx.Client(timeout=30)


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def rpc(method: str, params: list):
    for wait in (1, 2, 4, 8, 16, 0):  # the public RPC rate-limits (429); a crash mid-trip leaves tokens held
        r = client.post(RPC, json={"jsonrpc": "2.0", "id": 1, "method": method, "params": params})
        if r.status_code != 429 or not wait:
            break
        time.sleep(wait)
    r.raise_for_status()
    body = r.json()
    if body.get("error"):
        raise RuntimeError(f"{method}: {body['error']}")
    return body.get("result")


def quote(input_mint: str, output_mint: str, amount: int) -> dict | None:
    try:
        r = client.get(JUP, params={"inputMint": input_mint, "outputMint": output_mint, "amount": amount, "slippageBps": 50})
        r.raise_for_status()
        q = r.json()
        return {"out": int(q["outAmount"]), "route": [p["swapInfo"].get("label") for p in q.get("routePlan", [])], "slot": q.get("contextSlot")}
    except (httpx.HTTPError, KeyError, ValueError) as exc:
        return {"error": str(exc)[:200]}


def trade(action: str, amount, denominated_in_sol: bool, skip_preflight: bool = False) -> tuple[dict, float, float]:
    payload = {
        "action": action, "mint": args.mint or PROBE_MINT, "amount": amount, "denominatedInSol": "true" if denominated_in_sol else "false",
        "slippage": args.slippage, "priorityFee": args.priority, "pool": args.pool, "skipPreflight": "true" if skip_preflight else "false",
    }  # fmt: skip
    key = os.environ.get("PUMPPORTAL_API_KEY")
    t0 = time.time()
    r = client.post(TRADE, params={"api-key": key} if key else None, data=payload)
    t1 = time.time()
    try:
        body = r.json()
    except ValueError:
        body = {"status": r.status_code, "text": r.text[:500]}
    body["http_status"] = r.status_code
    return body, t0, t1


def confirm(signature: str, timeout: float = 90.0) -> tuple[dict | None, float | None]:
    """The confirmed transaction and when it was first seen confirmed (wall time), or (None, None)."""
    end = time.time() + timeout
    while time.time() < end:
        st = rpc("getSignatureStatuses", [[signature], {"searchTransactionHistory": True}])["value"][0]
        if st and st.get("confirmationStatus") in ("confirmed", "finalized"):
            seen = time.time()
            for _ in range(20):
                tx = rpc("getTransaction", [signature, {"encoding": "jsonParsed", "maxSupportedTransactionVersion": 0, "commitment": "confirmed"}])
                if tx:
                    return tx, seen
                time.sleep(1.0)
            return None, seen
        time.sleep(0.5)
    return None, None


def effects(tx: dict, mint: str) -> dict:
    """Wallet SOL change, token change, fees and rent from a confirmed transaction (fee payer = wallet)."""
    meta, msg = tx["meta"], tx["transaction"]["message"]
    keys = [k["pubkey"] if isinstance(k, dict) else k for k in msg["accountKeys"]]
    wallet = keys[0]
    sol_change = (meta["postBalances"][0] - meta["preBalances"][0]) / 1e9

    def tokens(balances):
        return sum(float(b["uiTokenAmount"]["uiAmount"] or 0) for b in balances or [] if b.get("mint") == mint and b.get("owner") == wallet)

    created = [
        ix for ix in (msg.get("instructions") or []) + [i for g in meta.get("innerInstructions") or [] for i in g["instructions"]]
        if isinstance(ix.get("parsed"), dict) and ix["parsed"].get("type") in ("create", "createIdempotent") and ix.get("program") == "spl-associated-token-account"
    ]  # fmt: skip
    rent = 0.0
    for i, k in enumerate(keys):
        if meta["preBalances"][i] == 0 and meta["postBalances"][i] > 0 and i != 0:
            owner_tokens = [b for b in meta.get("postTokenBalances") or [] if b.get("accountIndex") == i and b.get("owner") == wallet]
            if owner_tokens:
                rent += meta["postBalances"][i] / 1e9  # a token account this transaction opened for the wallet
    return {
        "wallet": wallet, "slot": tx["slot"], "err": meta.get("err"), "fee_sol": meta["fee"] / 1e9, "sol_change": sol_change,
        "token_change": tokens(meta.get("postTokenBalances")) - tokens(meta.get("preTokenBalances")),
        "ata_rent_sol": rent, "ata_created": bool(created), "cu": meta.get("computeUnitsConsumed"),
    }  # fmt: skip


def log(row: dict) -> None:
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("a") as f:
        f.write(json.dumps(row) + "\n")
    print(json.dumps(row)[:600], flush=True)


def leg(kind: str, amount, denominated_in_sol: bool, ref: dict | None) -> dict:
    body, t0, t1 = trade(kind, amount, denominated_in_sol)
    row = {"t": now(), "leg": kind, "mint": args.mint, "pool": args.pool, "amount": amount, "priority": args.priority, "slippage": args.slippage,
           "quote": ref, "response": body, "sent_at": t0, "answered_at": t1}  # fmt: skip
    sig = body.get("signature")
    if not sig:
        row["error"] = "no signature"
        log(row)
        return row
    tx, seen = confirm(sig)
    row["confirmed_at"] = seen
    if tx is not None:
        row["effects"] = effects(tx, args.mint)
        row["block_time"] = tx.get("blockTime")
    log(row)
    return row


def roundtrip() -> None:
    if not args.real:
        sys.exit("refusing: pass --real to send real trades")
    if not args.mint:
        sys.exit("--mint is required")
    if not 0 < args.size <= MAX_SIZE or not 1 <= args.trips <= MAX_TRIPS:
        sys.exit(f"caps: size in (0, {MAX_SIZE}] SOL, trips in [1, {MAX_TRIPS}]")
    for k in range(args.trips):
        lamports = int(args.size * 1e9)
        buy = leg("buy", args.size, True, quote(SOL, args.mint, lamports))
        eff = buy.get("effects")
        if not eff or eff.get("err") or eff["token_change"] <= 0:
            print("buy did not fill; stopping", flush=True)
            return
        time.sleep(args.hold)
        held = eff["token_change"]
        decimals_probe = quote(args.mint, SOL, int(held * 1e6))  # pump tokens use 6 decimals
        sell = leg("sell", "100%", False, decimals_probe)
        if not sell.get("effects") or sell["effects"].get("err"):
            print("sell did not confirm; stopping (tokens may still be held)", flush=True)
            return
        print(f"round trip {k + 1}: in {-eff['sol_change']:.6f} SOL, back {sell['effects']['sol_change']:.6f} SOL", flush=True)
        time.sleep(5)


def summary() -> None:
    rows = [json.loads(line) for line in Path(args.out).read_text().splitlines() if line.strip()]
    legs = [r for r in rows if r.get("effects") and not r["effects"].get("err")]
    for r in legs:
        e, q = r["effects"], r.get("quote") or {}
        lat = (r["confirmed_at"] - r["sent_at"]) if r.get("confirmed_at") and r.get("sent_at") else None
        if r["leg"] == "buy":
            spent = -e["sol_change"] - e["ata_rent_sol"]  # excluding refundable rent
            got = e["token_change"]
            q_tokens = q.get("out", 0) / 1e6 if q.get("out") else None
            shortfall = 1e4 * (1 - got / q_tokens) if q_tokens else None
            print(f"{r['t']} BUY  spent {spent:.6f} SOL (+ rent {e['ata_rent_sol']:.6f}), got {got:,.2f} tokens; "
                  f"vs Jupiter quote for {r.get("amount", "?")} SOL: {shortfall if shortfall is None else round(shortfall, 1)} bps fewer tokens; "
                  f"network fee {e['fee_sol']:.6f}; sent->confirmed {lat and round(lat, 2)} s")
        else:
            back = e["sol_change"]
            q_sol = q.get("out", 0) / 1e9 if q.get("out") else None
            shortfall = 1e4 * (1 - back / q_sol) if q_sol else None
            print(f"{r['t']} SELL got {back:.6f} SOL for {-e['token_change']:,.2f} tokens; vs Jupiter quote: "
                  f"{shortfall if shortfall is None else round(shortfall, 1)} bps less; network fee {e['fee_sol']:.6f}; sent->confirmed {lat and round(lat, 2)} s")
    buys = [r for r in legs if r["leg"] == "buy"]
    sells = [r for r in legs if r["leg"] == "sell"]
    for b, s in zip(buys, sells):
        spent = -b["effects"]["sol_change"] - b["effects"]["ata_rent_sol"]
        back = s["effects"]["sol_change"]
        print(f"round trip: {spent:.6f} -> {back:.6f} SOL: net {1e4 * (back / spent - 1):+.0f} bps (rent excluded, refundable by closing the token account)")


WALLET = "HZkGXYm2JLH8VUwqMcaVDJYFuokpQZ4vi4RDrVjBE28z"  # the Lightning wallet (public address)


def held_raw(mint: str) -> int:
    """Raw token units of --mint the wallet holds (0 if none)."""
    res = rpc("getTokenAccountsByOwner", [WALLET, {"mint": mint}, {"encoding": "jsonParsed"}])
    return sum(int(a["account"]["data"]["parsed"]["info"]["tokenAmount"]["amount"]) for a in res["value"])


def buy_one() -> None:
    """One buy of --size SOL (a strategy's entry; its exit is a separate `sell`)."""
    if not args.real or not args.mint:
        sys.exit("buy needs --real and --mint")
    if not 0 < args.size <= MAX_SIZE:
        sys.exit(f"cap: size in (0, {MAX_SIZE}] SOL")
    b = leg("buy", args.size, True, quote(SOL, args.mint, int(args.size * 1e9)))
    print("bought" if b.get("effects") and not b["effects"].get("err") else "buy did not confirm", flush=True)


def sell_held() -> None:
    """Sell 100% of --mint held (a strategy's exit, or a round trip a crash left open)."""
    if not args.real or not args.mint:
        sys.exit("sell needs --real and --mint")
    raw = held_raw(args.mint)
    if not raw:
        sys.exit("nothing held")
    sell = leg("sell", "100%", False, quote(args.mint, SOL, raw))
    print("sold" if sell.get("effects") and not sell["effects"].get("err") else "sell did not confirm", flush=True)


def record() -> None:
    """Log a leg that confirmed on chain but was never logged (no quote or send times)."""
    if not args.sig or not args.leg or not args.mint:
        sys.exit("record needs --sig, --leg and --mint")
    tx, seen = confirm(args.sig)
    if tx is None:
        sys.exit("not confirmed")
    log({"t": now(), "leg": args.leg, "mint": args.mint, "pool": args.pool, "quote": None, "response": {"signature": args.sig},
         "recorded_late": True, "effects": effects(tx, args.mint), "block_time": tx.get("blockTime")})  # fmt: skip


def probe() -> None:
    body, t0, t1 = trade("sell", "100%", False, skip_preflight=False)
    print(json.dumps({"probe_response": body, "seconds": round(t1 - t0, 2)})[:1500])


{"probe": probe, "roundtrip": roundtrip, "summary": summary, "buy": buy_one, "sell": sell_held, "record": record}[args.mode]()
