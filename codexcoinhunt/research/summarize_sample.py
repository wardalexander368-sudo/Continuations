#!/usr/bin/env python3
"""Describe frozen-pool quotes without claiming execution or strategy returns."""
import argparse
import csv
import datetime as dt
import json
import pathlib
import statistics


def read_time(value):
    return dt.datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("session")
    parser.add_argument("--output", default="results")
    args = parser.parse_args()
    session = pathlib.Path(args.session)
    out = pathlib.Path(args.output)
    out.mkdir(parents=True, exist_ok=True)
    universe = json.loads((session / "universe.json").read_text())
    requests = [json.loads(line) for line in (session / "snapshots.jsonl").read_text().splitlines()]
    cycles = {}
    for row in requests:
        cycles.setdefault(row["sequence"], []).append(row)
    first, last = min(cycles), max(cycles)
    allowed_mints = {row["mint"] for row in universe["tokens"]}
    pools = {}
    for request in cycles[first]:
        if request.get("ok"):
            for pair in request["data"]:
                mint = pair.get("baseToken", {}).get("address")
                if mint in allowed_mints and (mint not in pools or (pair.get("liquidity", {}).get("usd") or 0) > (pools[mint][0].get("liquidity", {}).get("usd") or 0)):
                    pools[mint] = pair, request["received_at"]
    paths = {mint: [] for mint in pools}
    cycle_quotes = {}
    for sequence, batch in sorted(cycles.items()):
        cycle_quotes[sequence] = {}
        for request in batch:
            if not request.get("ok"):
                continue
            for pair in request["data"]:
                mint = pair.get("baseToken", {}).get("address")
                if mint in pools and pair.get("pairAddress") == pools[mint][0].get("pairAddress"):
                    try:
                        price = float(pair["priceUsd"])
                    except (KeyError, ValueError, TypeError):
                        continue
                    if price > 0:
                        paths[mint].append((sequence, price, request["received_at"]))
                        cycle_quotes[sequence][mint] = price
    rows = []
    for mint in allowed_mints:
        baseline, received = pools.get(mint, ({}, None))
        path = paths.get(mint, [])
        initial = next((q for q in path if q[0] == first), None)
        ending = next((q for q in reversed(path) if q[0] == last), None)
        p0 = initial[1] if initial else None
        age = (read_time(received) - baseline["pairCreatedAt"] / 1000) / 3600 if received and baseline.get("pairCreatedAt") else None
        liquidity = baseline.get("liquidity", {}).get("usd")
        rows.append({"mint": mint, "symbol": baseline.get("baseToken", {}).get("symbol"), "fixed_pool_address": baseline.get("pairAddress"), "dex": baseline.get("dexId"), "first_received_at": received, "last_cycle_received_at": ending[2] if ending else None, "first_liquidity_usd": liquidity, "pool_age_hours_at_first_quote": age, "initial_price_usd": p0, "last_price_usd": ending[1] if ending else None, "endpoint_chart_return": ending[1] / p0 - 1 if p0 and ending else None, "observed_peak_chart_multiple": max(q[1] for q in path) / p0 if p0 and path else None, "observed_min_chart_multiple": min(q[1] for q in path) / p0 if p0 and path else None, "cycles_with_valid_price": len({q[0] for q in path}), "pool_liquidity_age_prefilter_only": bool(liquidity is not None and liquidity >= 25000 and age is not None and 6 <= age <= 168), "strategy_eligible": "UNKNOWN: social, mint-age, wallet, custody and executable-quote inputs missing"})
    rows.sort(key=lambda row: row["mint"])
    with (out / "first_market_sample.csv").open("w", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    returns = [row["endpoint_chart_return"] for row in rows if row["endpoint_chart_return"] is not None]
    summary = {"status": "development observation; not a backtest or recommendation", "first_observation_utc": min(row["received_at"] for row in requests), "last_observation_utc": max(row["received_at"] for row in requests), "unique_discovered_tokens": universe["discovered_count"], "selected_tokens": len(allowed_mints), "cycles": len(cycles), "snapshot_requests": len(requests), "failed_snapshot_requests": sum(not row.get("ok") for row in requests), "initial_pool_quotes": len(pools), "valid_endpoint_pairs": len(returns), "missing_endpoint_pairs": len(rows) - len(returns), "initial_liquidity_at_least_25k": sum((row["first_liquidity_usd"] or 0) >= 25000 for row in rows), "pool_age_liquidity_prefilter": sum(row["pool_liquidity_age_prefilter_only"] for row in rows), "median_endpoint_chart_return": statistics.median(returns) if returns else None, "minimum_endpoint_chart_return": min(returns) if returns else None, "maximum_endpoint_chart_return": max(returns) if returns else None, "endpoint_chart_2x_count": sum(value >= 1 for value in returns), "observed_peak_chart_2x_count": sum((row["observed_peak_chart_multiple"] or 0) >= 2 for row in rows), "forward_strategy_positions": 0, "executed_trades": 0, "data_gaps": ["This is a small visibility-biased API universe, not all launched tokens", "Pool age is not mint age", "DEX prices are marks, not executable size-specific swap quotes", "No complete social-author/attention or wallet funding history", "No validated independent strategy signals or account-doubling campaigns"]}
    (out / "first_market_sample_summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
