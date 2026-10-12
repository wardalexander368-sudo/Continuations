#!/usr/bin/env python3
"""Bounded finalized-chain PumpSwap buyer-event capture. No credentials or orders."""
import argparse
import base64
import datetime as dt
import hashlib
import json
import pathlib
import re
import time
import urllib.error
import urllib.request

PUMP_AMM = "pAMMBay6oceH9fJKBRHGP5D4bD4sWpmSwMn52FMfXEA"
WSOL = "So11111111111111111111111111111111111111112"
ALPHABET = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
BUY_DISC = bytes([103, 244, 82, 31, 44, 245, 119, 119])
SELL_DISC = bytes([62, 47, 55, 10, 165, 3, 220, 42])


def b58(data):
    number = int.from_bytes(data, "big")
    encoded = ""
    while number:
        number, digit = divmod(number, 58)
        encoded = ALPHABET[digit] + encoded
    zeros = len(data) - len(data.lstrip(b"\0"))
    return "1" * zeros + encoded


def utc():
    return dt.datetime.now(dt.timezone.utc).isoformat()


def rpc(url, method, params, path):
    request = {"jsonrpc": "2.0", "id": 1, "method": method, "params": params}
    record = {"requested_at_utc": utc(), "url": url, "request": request}
    try:
        req = urllib.request.Request(url, data=json.dumps(request).encode(), headers={"Content-Type": "application/json", "User-Agent": "ResolantPaperResearch/0.3"})
        with urllib.request.urlopen(req, timeout=20) as response:
            record.update(http_status=response.status, body=json.loads(response.read()))
    except Exception as error:
        record.update(http_status=getattr(error, "code", None), error=type(error).__name__, message=str(error))
        if isinstance(error, urllib.error.HTTPError):
            record["error_response"] = error.read().decode(errors="replace")
    record["received_at_utc"] = utc()
    with path.open("a") as handle:
        handle.write(json.dumps(record) + "\n")
    return record


def swap_events(transaction, signature, pool):
    """Decode the stable prefix only, while the executing program is PumpSwap.

    The first 14 scalar fields and 7 pubkeys are identical in BuyEvent/SellEvent.
    Required prefix truncation fails; later appended fields are not invented.
    """
    meta = transaction.get("meta") or {}
    if meta.get("err") is not None:
        return [], ["failed transaction"]
    if meta.get("logMessages") is None:
        return [], ["logs unavailable"]
    stack = []
    events = []
    errors = []
    for index, line in enumerate(meta["logMessages"]):
        match = re.match(r"Program (\S+) invoke \[\d+\]", line)
        if match:
            stack.append(match.group(1))
            continue
        match = re.match(r"Program (\S+) (success|failed:.*)$", line)
        if match:
            if stack and stack[-1] == match.group(1):
                stack.pop()
            else:
                stack = []
            continue
        if not (line.startswith("Program data: ") and stack and stack[-1] == PUMP_AMM):
            continue
        try:
            raw = base64.b64decode(line[14:], validate=True)
            if raw[:8] not in (BUY_DISC, SELL_DISC):
                continue
            if len(raw) < 344:
                raise ValueError("truncated stable swap event prefix")
            values = [int.from_bytes(raw[8+i*8:16+i*8], "little", signed=i == 0) for i in range(14)]
            pubkeys = [b58(raw[120+i*32:152+i*32]) for i in range(7)]
            if pubkeys[0] != pool:
                continue
            side = "B" if raw[:8] == BUY_DISC else "S"
            events.append({
                "event_id": signature + ":log:" + str(index), "signature": signature, "log_index": index,
                "pool": pool, "user": pubkeys[1], "side": side, "event_unix_time": values[0],
                "base_amount_raw": str(values[1]), "curve_quote_raw": str(values[7]),
                "user_quote_raw": str(values[13]), "lp_fee_raw": str(values[9]),
                "protocol_fee_raw": str(values[11]),
                "pool_base_after_raw": str(values[5]), "pool_quote_after_raw": str(values[6]),
                "base_token_account": pubkeys[2], "quote_token_account": pubkeys[3],
                "coin_creator": pubkeys[6], "slot": transaction.get("slot"),
                "block_time": transaction.get("blockTime"), "network_fee_lamports": meta.get("fee"),
                "account_mint_reconciled": any(x.get("mint") == transaction.get("_target_mint") for x in meta.get("preTokenBalances", []) + meta.get("postTokenBalances", [])),
            })
        except Exception as error:
            errors.append({"log_index": index, "error": str(error)})
    return events, errors


def collect(output, pool, mint, url, limit):
    output.mkdir(parents=True, exist_ok=False)
    raw_path = output / "rpc.jsonl"
    plan = {"started_at_utc": utc(), "pool": pool, "mint": mint, "quote_mint": WSOL, "selection": "first fixed PumpSwap prefilter pool; independent of subsequent returns", "signature_limit": 30, "transaction_limit": limit, "commitment": "finalized", "funding_clusters": "unavailable; never inferred independent from different wallets"}
    (output / "plan.json").write_text(json.dumps(plan, indent=2) + "\n")
    account = rpc(url, "getAccountInfo", [pool, {"commitment": "finalized", "encoding": "base64"}], raw_path)
    value = account.get("body", {}).get("result", {}).get("value")
    valid = False
    if value and value.get("owner") == PUMP_AMM:
        data = base64.b64decode(value["data"][0])
        valid = len(data) >= 107 and b58(data[43:75]) == mint and b58(data[75:107]) == WSOL
    if not valid:
        (output / "summary.json").write_text(json.dumps({"status": "rejected pool owner/mint identity or unavailable account", "plan": plan}, indent=2) + "\n")
        return
    signatures = rpc(url, "getSignaturesForAddress", [pool, {"limit": 30, "commitment": "finalized"}], raw_path)
    rows = signatures.get("body", {}).get("result") or []
    decoded = []
    outcomes = []
    for row in rows[:limit]:
        if row.get("err") is not None:
            outcomes.append({"signature": row["signature"], "status": "failed_transaction", "err": row["err"]})
            continue
        time.sleep(2.5)
        response = rpc(url, "getTransaction", [row["signature"], {"commitment": "finalized", "encoding": "jsonParsed", "maxSupportedTransactionVersion": 1}], raw_path)
        tx = response.get("body", {}).get("result")
        if not tx:
            outcomes.append({"signature": row["signature"], "status": "transaction_unavailable", "http_status": response.get("http_status"), "rpc_error": response.get("body", {}).get("error")})
            continue
        tx["_target_mint"] = mint
        # Import here to keep the older log-only parser reproducible for archived evidence.
        from buyer_enrichment import enriched_events
        events, errors = enriched_events(tx, row["signature"], pool, mint, response["received_at_utc"])
        for event in events:
            event.update(mint=mint, available_at_utc=response["received_at_utc"], finalized=True)
        decoded.extend(events)
        outcomes.append({"signature": row["signature"], "status": "decoded" if events else "no_matching_swap_event", "events": len(events), "parse_errors": errors})
    ids = set()
    unique_events = []
    for event in decoded:
        if event["event_id"] not in ids:
            ids.add(event["event_id"]); unique_events.append(event)
    buys = [e for e in unique_events if e["side"] == "B"]
    sells = [e for e in unique_events if e["side"] == "S"]
    buyer_notional = {}
    for event in buys:
        buyer_notional[event["user"]] = buyer_notional.get(event["user"], 0) + int(event["user_quote_raw"])
    times = [r["blockTime"] for r in rows if r.get("blockTime") is not None]
    summary = {"status": "bounded finalized swap-event subset, not complete interval or independent-human buyers", "completed_at_utc": utc(), "plan": plan,
        "pool_owner_and_exact_mint_verified": valid, "listed_signatures": len(rows), "transactions_attempted": len(outcomes),
        "listed_signature_time_span_seconds": max(times)-min(times) if times else None,
        "decoded_swap_events": len(unique_events), "buy_events": len(buys), "sell_events": len(sells),
        "unique_buy_event_users": len(buyer_notional), "buy_quote_lamports": sum(int(e["user_quote_raw"]) for e in buys),
        "sell_user_receipts_lamports": sum(int(e["user_quote_raw"]) for e in sells),
        "largest_buyer_notional_fraction": max(buyer_notional.values())/sum(buyer_notional.values()) if buyer_notional else None,
        "apparently_unrelated_seasoned_buyer_clusters": None, "new_to_mint_verified_buyers": None,
        "wallet_funding_provenance_coverage": None, "strategy_entry": "REJECT_MISSING_BUYER_HISTORY_FUNDING_SOCIAL_SAFETY", "outcomes": outcomes}
    (output / "events.jsonl").write_text("".join(json.dumps(e)+"\n" for e in unique_events))
    (output / "summary.json").write_text(json.dumps(summary, indent=2)+"\n")
    print(json.dumps({k:v for k,v in summary.items() if k != "outcomes"},indent=2))


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--output", type=pathlib.Path, required=True)
    p.add_argument("--pool", default="Fe7bpDYCs74GqiCUF14HwgUMToPKV1d9mDYVX5BTohFr")
    p.add_argument("--mint", default="2j5SaS7xy776qCBpyPQbZjyQSAtKiFgrwjfErthnW2ZM")
    p.add_argument("--rpc", default="https://api.mainnet-beta.solana.com")
    p.add_argument("--transactions", type=int, default=12)
    a = p.parse_args()
    if not 1 <= a.transactions <= 30: p.error("bounded transaction count must be 1–30")
    collect(a.output, a.pool, a.mint, a.rpc, a.transactions)
