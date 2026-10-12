"""Financial accounting and anti-leakage checks; not profitability evidence."""
import json
import math
import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from audit_ledger import reconcile
from economics import CASES, Costs, campaign_probability, gross_needed, net_multiple
from screen import BOOLEAN_FIELDS, evaluate

CONFIG = json.loads((pathlib.Path(__file__).resolve().parents[1] / "strategy.json").read_text())


def valid_record():
    values = {name: True for name in BOOLEAN_FIELDS}
    values.update(token_age_hours=24, liquidity_usd=50000, previous_wave_author_clusters=30, cooldown_minutes=90, cooldown_attention_fraction=0.4, current_author_clusters_10m=20, attention_multiple=3, new_audience_fraction=0.8, new_communities=3, mint_agreement_fraction=0.9, seasoned_new_buyer_clusters_5m=10, cluster_coverage_fraction=0.9, related_buy_fraction=0.1, net_buy_usd_5m=100, prior_sell_usd_5m=100, sell_flow_fraction=0.4, price_return_10m=0.05, top10_holder_fraction=0.3, creator_linked_fraction=0.05, roundtrip_cost_fraction=0.05, quote_age_seconds=1, feature_latency_seconds=60, confirmation_seconds=60)
    return {"mint": "SYNTHETIC_FIXTURE_NOT_A_TOKEN", "decision_at": "2026-10-12T00:00:00Z", "features": {name: {"value": value, "available_at": "2026-10-11T23:59:59Z", "evidence": "synthetic test fixture, not real market evidence"} for name, value in values.items()}}


class EconomicsTests(unittest.TestCase):
    def test_break_even_and_2x_inverse(self):
        for costs in CASES:
            for target in (1, 2):
                self.assertAlmostEqual(net_multiple(7, gross_needed(7, target, costs), costs), target)

    def test_two_x_chart_is_less_than_two_x_net(self):
        self.assertLess(net_multiple(7, 2, CASES[0]), 2)

    def test_zero_price_no_recovery(self):
        self.assertEqual(net_multiple(7, 0, CASES[0]), 0)

    def test_path_mass_conserved(self):
        r = campaign_probability(0.3, 0.05)
        self.assertAlmostEqual(sum(r[key] for key in ("target_hit_fraction", "stop_hit_fraction", "30_trade_timeout_fraction")), 1)

    def test_no_wins_cannot_double(self):
        self.assertEqual(campaign_probability(0, 0.1)["target_hit_fraction"], 0)

    def test_three_wins_exactly_2x_not_strict_target(self):
        winner = 1 + (2 ** (1 / 3) - 1) / 0.14
        self.assertEqual(campaign_probability(1, 0, winner_net=winner, trades=3)["target_hit_fraction"], 0)
        self.assertEqual(campaign_probability(1, 0, winner_net=winner, trades=4)["target_hit_fraction"], 1)


class GateTests(unittest.TestCase):
    def test_complete_fixture_is_paper_eligible(self):
        self.assertEqual(evaluate(valid_record(), CONFIG)["status"], "PAPER_ELIGIBLE")

    def test_future_information_rejected(self):
        r = valid_record()
        r["features"]["new_communities"]["available_at"] = "2026-10-12T00:01:00Z"
        self.assertIn("future_information:new_communities", evaluate(r, CONFIG)["reasons"])

    def test_missing_data_not_filled_in(self):
        r = valid_record()
        del r["features"]["related_buy_fraction"]
        self.assertIn("missing:related_buy_fraction", evaluate(r, CONFIG)["reasons"])

    def test_nonfinite_data_rejected(self):
        r = valid_record()
        r["features"]["net_buy_usd_5m"]["value"] = float("nan")
        self.assertIn("invalid_number:net_buy_usd_5m", evaluate(r, CONFIG)["reasons"])

    def test_quote_timestamp_freshness_enforced(self):
        r = valid_record()
        r["features"]["quote_age_seconds"]["available_at"] = "2026-10-11T23:59:00Z"
        self.assertIn("stale_quote_timestamp", evaluate(r, CONFIG)["reasons"])

    def test_paid_or_unknown_attention_rejected(self):
        r = valid_record()
        r["features"]["organic_attention_verified"]["value"] = False
        self.assertIn("failed:organic_attention_verified", evaluate(r, CONFIG)["reasons"])


class LedgerTests(unittest.TestCase):
    def row(self, event, kind, delta, qty, minute=0, position="p1", mint="SYNTHETIC"):
        return {"event_id": event, "occurred_at": f"2026-10-12T00:{minute:02}:00Z", "kind": kind, "position_id": position, "mint": mint, "quantity": qty, "usd_delta": delta, "evidence": "synthetic accounting check"}

    def test_partial_exit_and_extra_cost_reconcile(self):
        result = reconcile([self.row("1", "buy", -7, 10), self.row("2", "sell", 7, 5, 1), self.row("3", "sell", 10, 5, 2), self.row("4", "cost", -0.2, 0, 3)])
        self.assertAlmostEqual(result["ending_cash_usd"], 59.8)
        self.assertEqual(result["closed_positions"], 1)
        self.assertAlmostEqual(result["realized_account_pnl_usd"], 9.8)

    def test_one_rug_is_full_position_loss(self):
        result = reconcile([self.row("1", "buy", -7, 10), self.row("2", "writeoff", 0, 10, 1)])
        self.assertEqual(result["ending_cash_usd"], 43)
        self.assertEqual(result["positions"][0]["net_multiple"], 0)

    def test_open_position_not_a_return_claim(self):
        result = reconcile([self.row("1", "buy", -7, 10)])
        self.assertIsNone(result["withdrawable_cash_multiple"])
        self.assertFalse(result["target_met"])

    def test_overlapping_positions_rejected(self):
        with self.assertRaises(ValueError):
            reconcile([self.row("1", "buy", -7, 10), self.row("2", "buy", -6, 10, 1, "p2")])

    def test_overselling_rejected(self):
        with self.assertRaises(ValueError):
            reconcile([self.row("1", "buy", -7, 10), self.row("2", "sell", 10, 11, 1)])

    def test_position_limit_rejected(self):
        with self.assertRaises(ValueError):
            reconcile([self.row("1", "buy", -8, 10)])

    def test_duplicate_settlement_rejected(self):
        with self.assertRaises(ValueError):
            reconcile([self.row("1", "buy", -7, 10), self.row("1", "sell", 8, 10, 1)])

    def test_cost_only_ledger_is_account_loss(self):
        result = reconcile([self.row("1", "cost", -1, 0)])
        self.assertEqual(result["realized_account_pnl_usd"], -1)
        self.assertFalse(result["target_met"])

    def test_exact_decimal_100_boundary_not_false_success(self):
        from decimal import Decimal
        for cents in range(1, 100):
            cost = Decimal(cents) / 100
            rows = [self.row("1", "buy", "-7", "1"),
                    self.row("2", "sell", str(57 + cost), "1", 1),
                    self.row("3", "cost", str(-cost), "0", 2)]
            result = reconcile(rows)
            self.assertFalse(result["target_met"], msg=f"exact $100 with {cost} cost")
            self.assertEqual(Decimal(result["ending_cash_usd_exact"]), Decimal(100))

    def test_one_base_unit_of_dust_remains_open(self):
        result = reconcile([self.row("1", "buy", "-7", "1"),
                            self.row("2", "sell", "57.10", "0.999999999", 1)])
        self.assertFalse(result["target_met"])
        self.assertEqual(result["closed_positions"], 0)
        self.assertEqual(result["open_positions"][0]["remaining_quantity_exact"], "1E-9")

    def test_writeoff_of_wrong_mint_rejected(self):
        with self.assertRaises(ValueError):
            reconcile([self.row("1", "buy", -7, 10), self.row("2", "writeoff", 0, 10, 1, mint="OTHER")])

    def test_unverified_graduation_rejected(self):
        r = valid_record()
        r["features"]["graduated_pool_verified"]["value"] = False
        self.assertIn("failed:graduated_pool_verified", evaluate(r, CONFIG)["reasons"])


if __name__ == "__main__":
    unittest.main()
