"""Checks for censoring, event-time controls and bounded replay accounting."""
import json
import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from economics import CASES, net_multiple
from revival_study import capacity_multiple, matched_random, replay

CONFIG = json.loads((pathlib.Path(__file__).resolve().parents[1] / "revival_config.json").read_text())


def row(at_minute, price=1, liquidity=30000, mint="A", reason="downtrend_24h"):
    origin = 1780272000000
    return {"event_id": mint, "sample_id": mint + str(at_minute), "mint": mint, "rejectReason": reason, "sampleTs_utc_ms": origin + at_minute * 60000, "rejectTs_utc_ms": origin, "priceUsd": price, "liquidity": liquidity, "volume24h": 100000, "priceChange5m": 4, "priceChange1h": -20, "priceChange24h": -30, "dexId": "pumpswap", "pairAddress": "pool_" + mint}


def signal(record):
    return {"event_id": record["event_id"], "index": 0, "decision_ms": record["sampleTs_utc_ms"], "row": record}


class RevivalTests(unittest.TestCase):
    def test_depth_limit_converges_to_fee_arithmetic(self):
        self.assertAlmostEqual(capacity_multiple(7, 2, 1e12, 1e12), net_multiple(7, 2, CASES[0]), places=8)

    def test_thin_pool_is_costly_at_same_chart_price(self):
        self.assertLess(capacity_multiple(7, 1, 1000, 1000), capacity_multiple(7, 1, 50000, 50000))

    def test_entry_uses_next_observation_after_latency(self):
        first = row(20, 1)
        result = replay(signal(first), {"A": [first, row(25, 2), row(85, 2)]}, CONFIG)
        self.assertEqual(result["entry_price_usd"], 2)
        self.assertAlmostEqual(result["gross_mark_multiple"], 1)

    def test_censored_exit_is_not_an_observed_fill(self):
        first = row(20)
        result = replay(signal(first), {"A": [first, row(25)]}, CONFIG)
        self.assertEqual(result["status"], "censored_exit")
        self.assertIsNone(result["net_mark_multiple"])
        self.assertEqual(result["zero_recovery_stress_multiple"], 0)

    def test_late_collapsed_mark_does_not_invent_a_timely_exit(self):
        first = row(20)
        result = replay(signal(first), {"A": [first, row(25), row(240, 0.1)]}, CONFIG)
        self.assertEqual(result["status"], "censored_exit")
        self.assertIsNone(result["net_mark_multiple"])

    def test_stop_gap_uses_observed_price_instead_of_threshold(self):
        first = row(20)
        result = replay(signal(first), {"A": [first, row(25), row(30, 0.3)]}, CONFIG)
        self.assertLess(result["net_mark_multiple"], 0.3)

    def test_entry_capacity_rechecked_after_wait(self):
        first = row(20)
        result = replay(signal(first), {"A": [first, row(25, liquidity=1), row(85)]}, CONFIG)
        self.assertEqual(result["status"], "entry_capacity_gate_failed")
        self.assertIsNone(result["net_mark_multiple"])

    def test_future_control_not_in_available_universe(self):
        first = row(20, mint="A")
        controls, unmatched = matched_random([signal(first)], {"A": [first], "B": [row(30, mint="B")]}, CONFIG)
        self.assertEqual(controls, [])
        self.assertEqual(unmatched, 1)

    def test_control_does_not_select_same_mint_other_event(self):
        first = row(20, mint="A")
        another = row(20, mint="A")
        another["event_id"] = "second-event"
        controls, unmatched = matched_random([signal(first)], {"A": [first], "second-event": [another]}, CONFIG)
        self.assertEqual(controls, [])
        self.assertEqual(unmatched, 1)


if __name__ == "__main__":
    unittest.main()
