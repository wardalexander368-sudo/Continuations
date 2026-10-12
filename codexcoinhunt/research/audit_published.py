#!/usr/bin/env python3
"""Audit an external paper-return table without treating it as funded growth."""
import argparse
import csv
import datetime as dt
import json
import math
import pathlib
import statistics


def audit(rows):
    records = []
    for row in rows:
        reported = float(row["pnl"].rstrip("%")) / 100
        exit_at = dt.datetime.fromisoformat(row["date"].replace("Z", "+00:00"))
        entry_at = exit_at - dt.timedelta(minutes=float(row["heldMin"].removesuffix("min")))
        records.append({"entry_at": entry_at, "exit_at": exit_at, "reported_return": reported, "price_return": float(row["exitPrice"]) / float(row["entryPrice"]) - 1, "sol_in": float(row["solIn"].split()[0])})
    records.sort(key=lambda record: record["entry_at"])
    overlap, last_exit = 0, None
    for row in records:
        if last_exit is not None and row["entry_at"] < last_exit:
            overlap += 1
        last_exit = max(last_exit, row["exit_at"]) if last_exit else row["exit_at"]
    returns = [record["reported_return"] for record in records]
    without_top3 = sorted(returns, reverse=True)[3:]
    mathematical_multiple = math.prod(1 + 0.14 * value for value in returns)
    cash, trades_before_floor = 50.0, 0
    for row in records:
        if cash <= 40:
            break
        cash *= 1 + 0.14 * row["reported_return"]
        trades_before_floor += 1
    return {"status": "published paper-return accounting audit; not a funded-account replication", "source": "https://zenodo.org/records/23017853", "source_version": "v1.3 2026-09-28", "trade_rows": len(rows), "sum_of_trade_returns_pct": 100 * sum(returns), "mean_trade_return_pct": 100 * statistics.mean(returns), "win_fraction": sum(value > 0 for value in returns) / len(returns), "price_return_matches_reported_return_max_abs_difference": max(abs(row["reported_return"] - row["price_return"]) for row in records), "size_weighted_paper_pnl_sol": sum(row["sol_in"] * row["reported_return"] for row in records), "sum_of_trade_notional_sol": sum(row["sol_in"] for row in records), "hypothetical_fixed14pct_account_multiple_before_further_costs": mathematical_multiple, "hypothetical_50usd_ending_before_further_costs": 50 * mathematical_multiple, "hypothetical_fixed14pct_multiple_without_top3": math.prod(1 + 0.14 * value for value in without_top3), "sum_without_top3_pct": 100 * sum(without_top3), "hypothetical_campaign_40usd_floor_hit_after_trades": trades_before_floor, "hypothetical_campaign_balance_at_floor": cash, "overlapping_reported_position_intervals": overlap, "limitations": ["Public reported returns agree with price-ratio arithmetic to rounding precision; there is no fee-debit/fill-signature ledger", "Summed trade percentages are not an account return", "Fixed-fraction examples are algebraic counterfactuals, ignoring the original sizing, overlapping positions, gas, and execution", "This external strategy does not validate SLR or REV"]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("trades_csv")
    parser.add_argument("--output", default="results/published_benchmark_audit.json")
    args = parser.parse_args()
    with pathlib.Path(args.trades_csv).open() as file:
        rows = list(csv.DictReader(file))
    result = audit(rows)
    out = pathlib.Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps({key: result[key] for key in ("trade_rows", "sum_of_trade_returns_pct", "hypothetical_50usd_ending_before_further_costs", "overlapping_reported_position_intervals")}))


if __name__ == "__main__":
    main()
