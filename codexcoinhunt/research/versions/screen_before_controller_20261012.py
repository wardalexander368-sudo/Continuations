#!/usr/bin/env python3
"""Audit candidate feature records against SLR-0.2. No trading endpoints or keys."""
import argparse
import datetime as dt
import json
import math
import pathlib


def timestamp(value):
    result = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    if result.tzinfo is None:
        raise ValueError("timestamps must include a timezone")
    return result


BOOLEAN_FIELDS = ("spot_us_access_verified", "venue_support_verified", "graduated_pool_verified", "mint_identity_verified", "previous_wave_verified", "liquidity_custody_verified", "mint_authority_disabled", "freeze_authority_disabled", "unsupported_extensions_absent", "outside_audience_evidence_verified", "organic_attention_verified", "required_gas_and_rent_funded", "confirmation_passed")


def evaluate(record, config):
    reasons = []
    values = {}
    try:
        decision_at = timestamp(record["decision_at"])
    except (KeyError, TypeError, ValueError):
        return {"status": "REJECT", "reasons": ["invalid_decision_timestamp"], "mint": record.get("mint")}
    features = record.get("features", {})
    rules = {
        "token_age_hours": (config["entry"]["minimum_token_age_hours"], config["entry"]["maximum_token_age_hours"]),
        "liquidity_usd": (config["entry"]["minimum_liquidity_usd"], None),
        "previous_wave_author_clusters": (config["entry"]["minimum_previous_wave_author_clusters"], None),
        "cooldown_minutes": (config["entry"]["minimum_cooldown_minutes"], None),
        "cooldown_attention_fraction": (0, config["entry"]["maximum_cooldown_attention_fraction"]),
        "current_author_clusters_10m": (config["entry"]["minimum_current_wave_author_clusters_10m"], None),
        "attention_multiple": (config["entry"]["minimum_attention_multiple_vs_prior_30m"], None),
        "new_audience_fraction": (config["entry"]["minimum_new_audience_fraction"], 1),
        "new_communities": (config["entry"]["minimum_new_communities"], None),
        "mint_agreement_fraction": (config["entry"]["minimum_mint_agreement_fraction"], 1),
        "seasoned_new_buyer_clusters_5m": (config["entry"]["minimum_new_to_mint_seasoned_buyer_clusters_5m"], None),
        "cluster_coverage_fraction": (config["entry"]["minimum_cluster_coverage_fraction"], 1),
        "related_buy_fraction": (0, config["entry"]["maximum_suspected_related_buy_fraction"]),
        "net_buy_usd_5m": (config["entry"]["minimum_net_buy_usd_5m"], None),
        "prior_sell_usd_5m": (config["entry"]["minimum_prior_sell_usd_5m"], None),
        "sell_flow_fraction": (0, config["entry"]["maximum_current_vs_prior_sell_fraction"]),
        "price_return_10m": (config["entry"]["minimum_10m_price_return"], config["entry"]["maximum_10m_price_return"]),
        "top10_holder_fraction": (0, config["entry"]["maximum_top10_holder_fraction_ex_pool"]),
        "creator_linked_fraction": (0, config["entry"]["maximum_creator_linked_holder_fraction"]),
        "roundtrip_cost_fraction": (0, config["entry"]["maximum_roundtrip_cost_fraction"]),
        "quote_age_seconds": (0, config["entry"]["maximum_quote_age_seconds"]),
        "feature_latency_seconds": (0, config["entry"]["maximum_discovery_to_feature_latency_seconds"]),
        "confirmation_seconds": (config["entry"]["confirmation_wait_seconds"], None),
    }
    for name in (*BOOLEAN_FIELDS, *rules):
        feature = features.get(name)
        if not isinstance(feature, dict) or feature.get("value") is None:
            reasons.append("missing:" + name)
            continue
        if not feature.get("evidence"):
            reasons.append("no_evidence:" + name)
        try:
            available_at = timestamp(feature["available_at"])
            if available_at > decision_at:
                reasons.append("future_information:" + name)
            if name not in ("previous_wave_verified", "previous_wave_author_clusters", "cooldown_minutes", "cooldown_attention_fraction", "token_age_hours") and (decision_at - available_at).total_seconds() > 300:
                reasons.append("stale_feature:" + name)
            if name == "quote_age_seconds" and (decision_at - available_at).total_seconds() > config["entry"]["maximum_quote_age_seconds"]:
                reasons.append("stale_quote_timestamp")
        except (KeyError, TypeError, ValueError):
            reasons.append("invalid_available_at:" + name)
        value = feature["value"]
        values[name] = value
        if name in BOOLEAN_FIELDS:
            if value is not True:
                reasons.append("failed:" + name)
        else:
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
                reasons.append("invalid_number:" + name)
                continue
            lower, upper = rules[name]
            if lower is not None and value < lower or upper is not None and value > upper:
                reasons.append("out_of_range:" + name)
            if name in ("previous_wave_author_clusters", "current_author_clusters_10m", "new_communities", "seasoned_new_buyer_clusters_5m") and (value != int(value)):
                reasons.append("noninteger_count:" + name)
    if values.get("net_buy_usd_5m") == 0:
        reasons.append("no_positive_net_buy_flow")
    return {"strategy_id": config["strategy_id"], "mint": record.get("mint"), "decision_at": record.get("decision_at"), "status": "REJECT" if reasons else "PAPER_ELIGIBLE", "reasons": reasons, "note": "Input evidence is asserted by the operator, not verified by this gate; no live order is generated"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", help="JSONL feature records")
    parser.add_argument("--config", default=str(pathlib.Path(__file__).with_name("strategy.json")))
    parser.add_argument("--output", default="journal/decisions.jsonl")
    args = parser.parse_args()
    config = json.loads(pathlib.Path(args.config).read_text())
    output = pathlib.Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with pathlib.Path(args.input).open() as source, output.open("a") as destination:
        for line in source:
            if line.strip():
                destination.write(json.dumps(evaluate(json.loads(line), config), allow_nan=False) + "\n")
                count += 1
    print(json.dumps({"records_audited": count, "output": str(output), "mode": "paper_only"}))


if __name__ == "__main__":
    main()
