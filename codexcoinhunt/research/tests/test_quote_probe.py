import json
import pathlib
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
RESULT = ROOT / "results" / "quote_probe_20261012_pass6"


class QuoteProbeEvidenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.summary = json.loads((RESULT / "quote_results.json").read_text())

    def test_final_probe_is_bounded_and_fresh(self):
        self.assertEqual(self.summary["candidates"], 5)
        self.assertEqual(self.summary["capacity_pass_only"], 5)
        self.assertEqual(self.summary["rpc_commitment"], "processed")
        self.assertLessEqual(self.summary["state_window_ms"], self.summary["max_quote_age_ms"])

    def test_identity_and_capacity_are_explicit(self):
        for row in self.summary["results"]:
            self.assertTrue(row["exact_pool_owner_verified"])
            self.assertTrue(row["exact_base_mint_verified"])
            self.assertTrue(row["canonical_pump_pool_verified"])
            self.assertEqual(row["decision"], "CAPACITY_PASS_ONLY")
            self.assertLessEqual(row["all_in_roundtrip_cost_fraction"], 0.06)
            self.assertLessEqual(row["market_reference_age_ms"], row["max_market_reference_age_ms"])
            self.assertIn("virtual_quote_reserves", row["pool_state"])
            self.assertIn("protocol_fee_bucket", row["pool_state"])
            self.assertIn("creator_fee_bucket", row["pool_state"])

    def test_raw_rpc_is_read_only_and_timestamped(self):
        records = [json.loads(line) for line in (RESULT / "rpc_evidence.jsonl").read_text().splitlines()]
        self.assertGreaterEqual(len(records), 3)
        for record in records:
            self.assertIn("requested_at_utc", record)
            self.assertIn("received_at_utc", record)
            self.assertIn(record["request_body"]["method"], {"getSlot", "getMultipleAccounts"})

    def test_failed_freshness_attempts_are_retained(self):
        for name in ("quote_probe_20261012_pass1", "quote_probe_20261012_pass2", "quote_probe_20261012_pass3"):
            attempt = json.loads((ROOT / "results" / name / "quote_results.json").read_text())
            self.assertEqual(attempt["capacity_pass_only"], 0)
            self.assertEqual(attempt["rejected"], 5)
            self.assertGreater(attempt["state_window_ms"], attempt["max_quote_age_ms"])


if __name__ == "__main__":
    unittest.main()
