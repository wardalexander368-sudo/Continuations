#!/usr/bin/env python3
"""Reconcile timestamped, net USD paper fills. Never infer fills from a chart."""
import argparse
import csv
import datetime as dt
import json
import math
import pathlib


def parse_time(text):
    stamp = dt.datetime.fromisoformat(text.replace("Z", "+00:00"))
    if stamp.tzinfo is None:
        raise ValueError("ledger timestamps must include a timezone")
    return stamp


def reconcile(rows, start=50.0, position_fraction=0.14, reserve=5.0):
    cash = start
    positions = {}
    seen = set()
    closed = []
    cash_curve = []
    previous = None
    additional_costs = 0
    for row in rows:
        event_id = row["event_id"]
        if not event_id or event_id in seen:
            raise ValueError("missing or duplicated event_id")
        seen.add(event_id)
        stamp = parse_time(row["occurred_at"])
        if previous and stamp < previous:
            raise ValueError("ledger is not chronological")
        previous = stamp
        if not row.get("evidence"):
            raise ValueError("each fill/cost needs evidence")
        delta = float(row["usd_delta"])
        quantity = float(row.get("quantity") or 0)
        if not math.isfinite(delta) or not math.isfinite(quantity):
            raise ValueError("nonfinite cash or token quantity")
        kind = row["kind"]
        identifier = row.get("position_id")
        if kind == "buy":
            if positions:
                raise ValueError("one-position limit or no-averaging-down rule violated")
            if delta >= 0 or quantity <= 0 or not identifier or not row.get("mint"):
                raise ValueError("invalid buy")
            if -delta > min(cash * position_fraction, cash - reserve) + 1e-9:
                raise ValueError("position or gas reserve limit exceeded")
            positions[identifier] = {"position_id": identifier, "mint": row["mint"], "entry_at": row["occurred_at"], "debit_usd": -delta, "original_quantity": quantity, "remaining_quantity": quantity, "credit_usd": 0.0}
        elif kind == "sell":
            if identifier not in positions or delta < 0 or quantity <= 0:
                raise ValueError("sell without a valid open position")
            position = positions[identifier]
            if row.get("mint") != position["mint"]:
                raise ValueError("sell mint differs from position mint")
            if quantity > position["remaining_quantity"] + 1e-9:
                raise ValueError("cannot sell more tokens than owned")
            position["remaining_quantity"] -= quantity
            position["credit_usd"] += delta
            if position["remaining_quantity"] <= 1e-9:
                position.update({"exit_at": row["occurred_at"], "pnl_usd": position["credit_usd"] - position["debit_usd"], "net_multiple": position["credit_usd"] / position["debit_usd"]})
                closed.append(position.copy())
                del positions[identifier]
        elif kind == "writeoff":
            if identifier not in positions or quantity < 0 or delta != 0:
                raise ValueError("invalid writeoff")
            position = positions.pop(identifier)
            if row.get("mint") != position["mint"]:
                raise ValueError("writeoff mint differs from position mint")
            if quantity and abs(quantity - position["remaining_quantity"]) > 1e-9:
                raise ValueError("writeoff must cover the entire remainder")
            position.update({"exit_at": row["occurred_at"], "pnl_usd": position["credit_usd"] - position["debit_usd"], "net_multiple": position["credit_usd"] / position["debit_usd"], "terminal_reason": "documented unsellability or zero recoverable value"})
            closed.append(position.copy())
        elif kind == "cost":
            if delta > 0 or quantity != 0:
                raise ValueError("invalid external cost")
            additional_costs -= delta
        else:
            raise ValueError("unknown ledger kind")
        cash += delta
        if cash < -1e-9:
            raise ValueError("negative cash: ledger requires outside capital")
        cash_curve.append({"at": row["occurred_at"], "cash_usd": cash, "open_positions": len(positions), "equity_verified_without_mark_estimates": not positions})
    settled = not positions
    pnl = cash - start if settled else None
    return {"status": "no_fills" if not rows else "fully_settled" if settled else "open_positions_excluded_from_performance_claim", "starting_usd": start, "ending_cash_usd": cash, "realized_account_pnl_usd": pnl, "withdrawable_cash_multiple": cash / start if settled else None, "target_met": bool(rows and settled and cash > 2 * start), "closed_positions": len(closed), "open_positions": list(positions.values()), "external_costs_usd": additional_costs, "positions": closed, "cash_curve": cash_curve, "note": "Net USD-equivalent inputs must include execution fees and actual conversion cost; SOL price or dust marks are not evidence of withdrawable USD"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("ledger", help="CSV of net buy/sell/cost/writeoff events")
    parser.add_argument("--output", default="results/ledger_audit.json")
    args = parser.parse_args()
    with pathlib.Path(args.ledger).open() as file:
        rows = list(csv.DictReader(file))
    result = reconcile(rows)
    out = pathlib.Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps({key: result[key] for key in ("status", "ending_cash_usd", "closed_positions", "target_met")}))


if __name__ == "__main__":
    main()
