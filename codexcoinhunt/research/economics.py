#!/usr/bin/env python3
"""Explicit fee arithmetic and hypothetical campaign sensitivity, NOT a backtest."""
import argparse
import csv
import json
import math
import pathlib
from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class Costs:
    name: str
    buy_rate: float
    sell_rate: float
    buy_slippage: float = 0.005
    sell_slippage: float = 0.005
    buy_fixed_usd: float = 0.02
    sell_fixed_usd: float = 0.02
    allocated_data_usd: float = 0.05


CASES = [
    Costs("PumpPortal Local + conservative 1.25% pool", 0.0175, 0.0175),
    Costs("PumpPortal Lightning + conservative 1.25% pool", 0.0225, 0.0225),
    Costs("PumpPortal Local + verified 0.30% pool", 0.008, 0.008),
    Costs("Alpaca taker; listed assets only", 0.0025, 0.0025, 0.0025, 0.0025, 0, 0, 0),
]


def proportional_factor(budget, costs):
    if budget <= costs.buy_fixed_usd + costs.allocated_data_usd:
        raise ValueError("position too small for fixed costs")
    rates = [costs.buy_rate, costs.sell_rate, costs.buy_slippage, costs.sell_slippage]
    if any(not 0 <= x < 1 for x in rates):
        raise ValueError("invalid fee or slippage fraction")
    return (1 - (costs.buy_fixed_usd + costs.allocated_data_usd) / budget) * math.prod(1 - x for x in rates)


def net_multiple(budget, gross_price_multiple, costs):
    if gross_price_multiple < 0:
        raise ValueError("price multiple cannot be negative")
    # Terminal unsellability is a separate zero-return outcome, not a normal fill.
    return max(0, gross_price_multiple * proportional_factor(budget, costs) - costs.sell_fixed_usd / budget)


def gross_needed(budget, target_net_multiple, costs):
    return (target_net_multiple + costs.sell_fixed_usd / budget) / proportional_factor(budget, costs)


def campaign_probability(p_win, p_rug, winner_net=3.0, loser_net=0.8, fraction=0.14, trades=30):
    """Exact path-dependent hitting probability under assumed IID outcomes.

    Outcomes already include all costs. Ordinary losses assume a filled exit;
    rugs explicitly lose the entire allocation. No daily/session or elapsed-time
    rules are simulated. This is an optimistic feasibility sensitivity only.
    """
    if min(p_win, p_rug) < 0 or p_win + p_rug > 1:
        raise ValueError("invalid outcome probabilities")
    probabilities = [p_win, 1 - p_win - p_rug, p_rug]
    multipliers = [1 + fraction * (winner_net - 1), 1 + fraction * (loser_net - 1), 1 - fraction]
    states = {(0, 0): 1.0}
    hit, stopped = 0.0, 0.0
    for n in range(trades):
        following = {}
        for (wins, rugs), probability in states.items():
            for outcome, p in enumerate(probabilities):
                if p == 0:
                    continue
                w, r = wins + (outcome == 0), rugs + (outcome == 2)
                losses = n + 1 - w - r
                equity = 50 * multipliers[0] ** w * multipliers[1] ** losses * multipliers[2] ** r
                branch = probability * p
                if equity > 100 + 1e-9:
                    hit += branch
                elif equity <= 40:
                    stopped += branch
                else:
                    following[(w, r)] = following.get((w, r), 0) + branch
        states = following
    timed_out = sum(states.values())
    return {"assumed_p_win": p_win, "assumed_p_total_loss": p_rug, "assumed_winner_net_multiple": winner_net, "assumed_normal_loser_net_multiple": loser_net, "target_hit_fraction": hit, "stop_hit_fraction": stopped, "30_trade_timeout_fraction": timed_out}


def wilson_lower(successes, total, z=1.959963984540054):
    if total < 1 or not 0 <= successes <= total:
        raise ValueError("invalid binomial sample")
    p = successes / total
    denominator = 1 + z * z / total
    return (p + z * z / (2 * total) - z * math.sqrt(p * (1 - p) / total + z * z / (4 * total * total))) / denominator


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", default="results")
    args = parser.parse_args()
    out = pathlib.Path(args.output)
    out.mkdir(parents=True, exist_ok=True)
    fee_rows = []
    for case in CASES:
        fee_rows.append({**asdict(case), "budget_usd": 7, "gross_break_even": gross_needed(7, 1, case), "gross_for_net_position_2x": gross_needed(7, 2, case), "net_proceeds_if_gross_price_2x_usd": 7 * net_multiple(7, 2, case), "net_proceeds_if_gross_price_3x_usd": 7 * net_multiple(7, 3, case)})
    sensitivity = [campaign_probability(p, q, winner_net=w) for w in (1.5, 2.0, 3.0) for q in (0.0, 0.05, 0.10) for p in (0.2, 0.3, 0.4, 0.5)]
    payload = {"status": "hypothetical arithmetic, no observed trading probabilities", "fee_model": "percentage costs approximated as deductions; obtain actual account deltas/size-specific quotes for fills; pool rates can change between entry and exit", "fixed_costs_slippage_and_data_costs_are_assumptions": True, "rent_note": "refundable rent not charged as an expense here; must be funded separately and excluded from withdrawable target until reclaimed", "campaign_model_limits": "IID full-position terminal outcomes; no elapsed time, daily standdowns, or full runner exit logic; cannot certify strategy performance", "fees": fee_rows, "sensitivity": sensitivity, "campaign_confirmation": {"27_of_30_wilson_lower": wilson_lower(27, 30), "26_of_30_wilson_lower": wilson_lower(26, 30)}}
    (out / "economics.json").write_text(json.dumps(payload, indent=2) + "\n")
    with (out / "hypothetical_sensitivity.csv").open("w", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=list(sensitivity[0]))
        writer.writeheader()
        writer.writerows(sensitivity)
    print(json.dumps({"fees": fee_rows, "sample_sensitivity": [x for x in sensitivity if x["assumed_p_total_loss"] == 0.05 and x["assumed_winner_net_multiple"] == 3.0], "confirmation": payload["campaign_confirmation"]}, indent=2))


if __name__ == "__main__":
    main()
