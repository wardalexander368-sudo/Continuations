#!/usr/bin/env python3
"""Decode retained PumpSwap events and reconcile fees to exact token movement.

Offline and paper-only: this reads saved public responses and cannot create,
sign, simulate or send a transaction.
"""
import argparse
import collections
import hashlib
import json
from decimal import Decimal
from pathlib import Path

from buyer_enrichment import event_payloads
from buyer_probe import BUY_DISC, SELL_DISC, b58, utc

EXPECTED_IDL_SHA256 = "b7d8c57a4d9c4dd0109a9ab893052352333252d4eedced10ac091d4d66cab89b"


def event_fields(idl, name):
    matches = [row for row in idl.get("types", []) if row.get("name") == name]
    if len(matches) != 1 or (matches[0].get("type") or {}).get("kind") != "struct":
        raise ValueError(f"missing unique {name} struct in IDL")
    return matches[0]["type"]["fields"]


def decode_event(raw, fields):
    """Decode the supported primitive Borsh types and require full consumption."""
    if len(raw) < 8:
        raise ValueError("missing event discriminator")
    offset = 8
    result = {}
    widths = {"u64": 8, "i64": 8, "i128": 16, "bool": 1, "pubkey": 32}
    for field in fields:
        name, kind = field["name"], field["type"]
        if kind == "string":
            if offset + 4 > len(raw):
                raise ValueError(f"truncated string length for {name}")
            size = int.from_bytes(raw[offset:offset + 4], "little")
            offset += 4
            if offset + size > len(raw):
                raise ValueError(f"truncated string body for {name}")
            result[name] = raw[offset:offset + size].decode("utf-8")
            offset += size
            continue
        if kind not in widths:
            raise ValueError(f"unsupported IDL field type for {name}: {kind!r}")
        width = widths[kind]
        if offset + width > len(raw):
            raise ValueError(f"truncated {kind} field {name}")
        body = raw[offset:offset + width]
        offset += width
        if kind == "pubkey":
            result[name] = b58(body)
        elif kind == "bool":
            if body[0] not in (0, 1):
                raise ValueError(f"noncanonical bool for {name}")
            result[name] = bool(body[0])
        else:
            result[name] = int.from_bytes(body, "little", signed=kind in ("i64", "i128"))
    if offset != len(raw):
        raise ValueError(f"IDL decoded {offset} of {len(raw)} bytes")
    return result


def fee_semantics(event, side):
    lp = event["lp_fee"]
    protocol = event["protocol_fee"]
    creator = event["coin_creator_fee"]
    fee_sum = lp + protocol + creator
    if side == "buy":
        instruction = event.get("ix_name")
        if instruction in ("buy_exact_quote_in", "buy_exact_quote_in_v2", "buy_exact_quote_in_v3"):
            net_quote = event["user_quote_amount_in"]
            gross_debit = event["quote_amount_in"]
            semantic_rule = "exact_quote_in: quote_amount_in is gross debit; user_quote_amount_in is curve input"
        elif instruction in ("buy", "buy_v2", "buy_v3"):
            net_quote = event["quote_amount_in"]
            gross_debit = event["user_quote_amount_in"]
            semantic_rule = "buy: user_quote_amount_in is gross debit; quote_amount_in is curve input"
        else:
            raise ValueError(f"unsupported buy instruction semantic: {instruction!r}")
        bridge_exact = event["quote_amount_in_with_lp_fee"] == net_quote + lp
        gross_field = "quote_amount_in" if instruction.startswith("buy_exact_quote_in") else "user_quote_amount_in"
        net_field = "user_quote_amount_in" if instruction.startswith("buy_exact_quote_in") else "quote_amount_in"
    else:
        instruction = event.get("ix_name")
        net_quote = event["user_quote_amount_out"]
        gross_debit = event["quote_amount_out"]
        semantic_rule = "sell: quote_amount_out is pre-fee pool output; user_quote_amount_out is net user receipt"
        bridge_exact = event["quote_amount_out_without_lp_fee"] == gross_debit - lp
        gross_field, net_field = "quote_amount_out", "user_quote_amount_out"
    buyback_expected = protocol * event.get("buyback_fee_basis_points", 0) // 10_000
    holder = event.get("holder_rewards", 0)
    cashback = event.get("cashback", 0)
    nominal_bps = (event["lp_fee_basis_points"] + event["protocol_fee_basis_points"]
                   + event["coin_creator_fee_basis_points"])
    return {
        "instruction": instruction,
        "semantic_rule": semantic_rule,
        "gross_quote_field": gross_field,
        "net_quote_field": net_field,
        "gross_quote_raw": str(gross_debit),
        "net_quote_raw": str(net_quote),
        "lp_fee_raw": str(lp),
        "protocol_fee_raw": str(protocol),
        "coin_creator_fee_raw": str(creator),
        "fee_sum_raw": str(fee_sum),
        "gross_minus_net_raw": str(gross_debit - net_quote),
        "fee_decomposition_exact": gross_debit - net_quote == fee_sum,
        "intermediate_lp_bridge_exact": bridge_exact,
        "nominal_fee_basis_points": nominal_bps,
        "effective_fee_fraction_of_net": str(Decimal(fee_sum) / Decimal(net_quote)) if net_quote else None,
        "buyback_fee_basis_points_of_protocol": event.get("buyback_fee_basis_points"),
        "buyback_fee_raw": str(event.get("buyback_fee", 0)),
        "buyback_expected_from_protocol_raw": str(buyback_expected),
        "buyback_is_protocol_suballocation": event.get("buyback_fee", 0) == buyback_expected,
        "cashback_raw": str(cashback),
        "cashback_not_added_again": cashback <= creator,
        "holder_rewards_raw": str(holder),
        "holder_rewards_not_added_again": holder <= creator,
        "creator_fee_unclaimed_is_accumulator_not_trade_fee_raw": str(event.get("creator_fee_unclaimed", 0)),
    }


def retained_transactions(path):
    result = {}
    for line in path.read_text().splitlines():
        row = json.loads(line)
        request = row.get("request") or {}
        params = request.get("params") or []
        body = (row.get("body") or {}).get("result")
        if request.get("method") == "getTransaction" and params and isinstance(body, dict):
            result[params[0]] = row
    return result


def route_audits(path):
    rows = [json.loads(line) for line in path.read_text().splitlines() if line]
    return {(row["signature"], row["user"]): row for row in rows
            if row.get("status") == "exact_buy_and_quote_route_audited"}


def representation_groups(tx):
    records, errors = event_payloads(tx)
    grouped = collections.defaultdict(lambda: {"raw": None, "sources": collections.defaultdict(list)})
    for source, location, raw in records:
        if raw[:8] not in (BUY_DISC, SELL_DISC):
            continue
        digest = hashlib.sha256(raw).hexdigest()
        grouped[digest]["raw"] = raw
        grouped[digest]["sources"][source].append(str(location))
    result = []
    for digest, group in grouped.items():
        occurrences = max(len(paths) for paths in group["sources"].values())
        for occurrence in range(occurrences):
            paths = {source: values[occurrence] for source, values in group["sources"].items()
                     if occurrence < len(values)}
            result.append((digest, occurrence, group["raw"], paths))
    return result, errors


def run(root, output):
    idl_path = root / "data/model_and_entry_sources_20261012/pump_amm_idl.json"
    idl_bytes = idl_path.read_bytes()
    idl_sha = hashlib.sha256(idl_bytes).hexdigest()
    if idl_sha != EXPECTED_IDL_SHA256:
        raise ValueError(f"pinned IDL hash mismatch: {idl_sha}")
    idl = json.loads(idl_bytes)
    fields = {"buy": event_fields(idl, "BuyEvent"), "sell": event_fields(idl, "SellEvent")}
    transactions = retained_transactions(root / "data/buyer_probe_20261012/rpc.jsonl")
    audits = route_audits(root / "results/quote_provenance_final_20261012/buy_route_audits.jsonl")
    decoded = []
    parse_issues = []
    for signature, response in transactions.items():
        tx = response["body"]["result"]
        groups, source_errors = representation_groups(tx)
        parse_issues.extend({"signature": signature, **row} for row in source_errors)
        for digest, occurrence, raw, paths in groups:
            side = "buy" if raw[:8] == BUY_DISC else "sell"
            try:
                event = decode_event(raw, fields[side])
                semantics = fee_semantics(event, side)
                row = {
                    "status": "complete_event_and_fee_reconciled",
                    "signature": signature,
                    "event_digest_sha256": digest,
                    "occurrence": occurrence,
                    "side": side,
                    "user": event["user"],
                    "pool": event["pool"],
                    "event_unix_time": event["timestamp"],
                    "block_time": tx.get("blockTime"),
                    "available_at_utc": response["received_at_utc"],
                    "raw_event_bytes": len(raw),
                    "representation_paths": paths,
                    "decoded_event": event,
                    "fee_reconciliation": semantics,
                    "pinned_idl_sha256": idl_sha,
                }
                audit = audits.get((signature, event["user"])) if side == "buy" else None
                if audit:
                    outflow = int(audit["verified_quote_transfer_out_raw"])
                    gross = int(semantics["gross_quote_raw"])
                    row["exact_quote_account_outflow"] = {
                        "verified_outflow_raw": str(outflow),
                        "instruction_aware_gross_raw": str(gross),
                        "instruction_aware_gross_matches_outflow": gross == outflow,
                        "stable_prefix_user_quote_raw": audit["event_reported_quote_raw"],
                        "stable_prefix_user_quote_matches_outflow": int(audit["event_reported_quote_raw"]) == outflow,
                    }
                decoded.append(row)
            except Exception as error:
                parse_issues.append({"signature": signature, "digest": digest, "error": str(error),
                                     "raw_event_bytes": len(raw), "representation_paths": paths})
    decoded.sort(key=lambda row: (row["event_unix_time"], row["signature"], row["occurrence"], row["side"]))
    buys = [row for row in decoded if row["side"] == "buy"]
    sells = [row for row in decoded if row["side"] == "sell"]
    routed = [row for row in buys if "exact_quote_account_outflow" in row]
    gross_by_user = collections.Counter()
    for row in routed:
        gross_by_user[row["user"]] += int(row["fee_reconciliation"]["gross_quote_raw"])
    funding = json.loads((root / "results/buyer_funding_reconciled_20261012/summary.json").read_text())
    returning = {row["wallet"] for row in funding["rows"] if row["new_to_mint_falsified"]}
    total_gross = sum(gross_by_user.values())
    returning_gross = sum(amount for user, amount in gross_by_user.items() if user in returning)
    summary = {
        "id": "PUMP-EVENT-FEE-RECONCILIATION-0.1",
        "completed_at_utc": utc(),
        "status": "post-observation forensic accounting correction; same fixed transactions, no return test",
        "pinned_official_idl_sha256": idl_sha,
        "retained_transaction_bodies": len(transactions),
        "complete_events_decoded": len(decoded),
        "buy_events": len(buys),
        "sell_events": len(sells),
        "parse_issues": len(parse_issues),
        "log_cpi_dual_representations": sum(set(row["representation_paths"]) == {"log", "cpi"} for row in decoded),
        "fee_decompositions_exact": sum(row["fee_reconciliation"]["fee_decomposition_exact"] for row in decoded),
        "lp_bridge_equations_exact": sum(row["fee_reconciliation"]["intermediate_lp_bridge_exact"] for row in decoded),
        "buyback_protocol_suballocations_exact": sum(row["fee_reconciliation"]["buyback_is_protocol_suballocation"] for row in decoded),
        "nominal_fee_basis_point_counts": dict(collections.Counter(str(row["fee_reconciliation"]["nominal_fee_basis_points"]) for row in decoded)),
        "buy_instruction_counts": dict(collections.Counter(row["fee_reconciliation"]["instruction"] for row in buys)),
        "buy_route_audits_reconciled": len(routed),
        "instruction_aware_gross_matches_exact_outflow": sum(row["exact_quote_account_outflow"]["instruction_aware_gross_matches_outflow"] for row in routed),
        "stable_prefix_user_quote_matches_exact_outflow": sum(row["exact_quote_account_outflow"]["stable_prefix_user_quote_matches_outflow"] for row in routed),
        "previously_unexplained_user_quote_mismatches": sum(not row["exact_quote_account_outflow"]["stable_prefix_user_quote_matches_outflow"] for row in routed),
        "previously_unexplained_mismatches_now_exactly_fee_decomposed": sum((not row["exact_quote_account_outflow"]["stable_prefix_user_quote_matches_outflow"]) and row["fee_reconciliation"]["fee_decomposition_exact"] for row in routed),
        "five_buy_gross_quote_raw": str(total_gross),
        "gross_quote_decimals": 9,
        "proven_returning_buyers_gross_quote_raw": str(returning_gross),
        "proven_returning_fraction_by_gross_debit": str(Decimal(returning_gross) / Decimal(total_gross)) if total_gross else None,
        "largest_buyer_fraction_by_gross_debit": str(Decimal(max(gross_by_user.values())) / Decimal(total_gross)) if total_gross else None,
        "historical_eligibility_changed": False,
        "strategy_or_controller_rules_changed": False,
        "new_market_observations": 0,
        "new_strategy_entries": 0,
        "new_closed_positions": 0,
        "new_matched_net_account_comparisons": 0,
        "new_doubling_campaigns": 0,
        "accounting_rule": "Use instruction-aware gross debit or exact account movement. Pool fees already embedded in a fee-aware SDK quote or net fill must not be charged again. PumpPortal, network, priority, rent, conversion and other execution costs remain separate when actually applicable.",
        "limits": [
            "This audit explains existing event fields and account transfers; it does not measure a strategy return.",
            "The fixed sample is development evidence and was selected before this forensic analysis, not an untouched cohort.",
            "A fee field identifies protocol accounting but does not prove a user's complete USD funding or recovery path.",
            "Gross-debit concentration still does not establish independent people or profitable buyer skill."
        ],
    }
    output.mkdir(parents=True, exist_ok=False)
    (output / "event_fee_rows.jsonl").write_text("".join(json.dumps(row) + "\n" for row in decoded))
    (output / "parse_issues.json").write_text(json.dumps(parse_issues, indent=2) + "\n")
    (output / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps(summary, indent=2))
    return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument("--output", type=Path, required=True)
    arguments = parser.parse_args()
    run(arguments.root, arguments.output)
