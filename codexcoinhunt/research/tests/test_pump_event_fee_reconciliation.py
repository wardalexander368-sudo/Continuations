import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from pump_event_fee_reconciliation import decode_event, fee_semantics, run


class EventFeeUnitTests(unittest.TestCase):
    def test_decoder_consumes_supported_primitive_fields(self):
        fields = [
            {"name": "amount", "type": "u64"},
            {"name": "flag", "type": "bool"},
            {"name": "key", "type": "pubkey"},
            {"name": "label", "type": "string"},
            {"name": "virtual", "type": "i128"},
        ]
        body = (b"12345678" + (42).to_bytes(8, "little") + b"\x01" + bytes(range(32))
                + (3).to_bytes(4, "little") + b"buy" + (-7).to_bytes(16, "little", signed=True))
        decoded = decode_event(body, fields)
        self.assertEqual(decoded["amount"], 42)
        self.assertTrue(decoded["flag"])
        self.assertEqual(decoded["label"], "buy")
        self.assertEqual(decoded["virtual"], -7)

    def test_decoder_rejects_trailing_bytes(self):
        with self.assertRaisesRegex(ValueError, "decoded"):
            decode_event(b"12345678" + (1).to_bytes(8, "little") + b"x",
                         [{"name": "amount", "type": "u64"}])

    def test_decoder_rejects_truncated_string(self):
        with self.assertRaisesRegex(ValueError, "truncated string body"):
            decode_event(b"12345678" + (5).to_bytes(4, "little") + b"no",
                         [{"name": "label", "type": "string"}])

    @staticmethod
    def buy(ix_name, quote, user, lp=20, protocol=5, creator=20):
        return {
            "ix_name": ix_name,
            "quote_amount_in": quote,
            "user_quote_amount_in": user,
            "quote_amount_in_with_lp_fee": min(quote, user) + lp,
            "lp_fee": lp,
            "protocol_fee": protocol,
            "coin_creator_fee": creator,
            "lp_fee_basis_points": 20,
            "protocol_fee_basis_points": 5,
            "coin_creator_fee_basis_points": 20,
            "buyback_fee_basis_points": 5000,
            "buyback_fee": protocol // 2,
            "cashback": 0,
            "holder_rewards": 0,
            "creator_fee_unclaimed": 99,
        }

    def test_exact_quote_instruction_uses_quote_amount_as_gross(self):
        result = fee_semantics(self.buy("buy_exact_quote_in_v2", 1045, 1000), "buy")
        self.assertEqual(result["gross_quote_raw"], "1045")
        self.assertEqual(result["net_quote_raw"], "1000")
        self.assertTrue(result["fee_decomposition_exact"])

    def test_buy_instruction_uses_user_quote_as_gross(self):
        result = fee_semantics(self.buy("buy_v2", 1000, 1045), "buy")
        self.assertEqual(result["gross_quote_raw"], "1045")
        self.assertEqual(result["net_quote_raw"], "1000")
        self.assertTrue(result["fee_decomposition_exact"])

    def test_sell_user_receipt_is_net(self):
        event = {
            "quote_amount_out": 1045,
            "user_quote_amount_out": 1000,
            "quote_amount_out_without_lp_fee": 1025,
            "lp_fee": 20,
            "protocol_fee": 5,
            "coin_creator_fee": 20,
            "lp_fee_basis_points": 20,
            "protocol_fee_basis_points": 5,
            "coin_creator_fee_basis_points": 20,
            "buyback_fee_basis_points": 5000,
            "buyback_fee": 2,
            "cashback": 0,
            "holder_rewards": 0,
        }
        result = fee_semantics(event, "sell")
        self.assertTrue(result["fee_decomposition_exact"])
        self.assertTrue(result["intermediate_lp_bridge_exact"])

    def test_buyback_is_floor_suballocation_of_protocol_fee(self):
        event = self.buy("buy_v2", 1000, 1045, protocol=5)
        result = fee_semantics(event, "buy")
        self.assertEqual(result["buyback_expected_from_protocol_raw"], "2")
        self.assertTrue(result["buyback_is_protocol_suballocation"])

    def test_unsupported_buy_semantic_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "unsupported buy instruction"):
            fee_semantics(self.buy("future_unknown_buy", 1045, 1000), "buy")


class RetainedEvidenceIntegrationTest(unittest.TestCase):
    def test_fixed_event_set_reconciles_without_changing_outcomes(self):
        root = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as directory:
            with contextlib.redirect_stdout(io.StringIO()):
                summary = run(root, Path(directory) / "result")
            saved = json.loads((Path(directory) / "result" / "summary.json").read_text())
        self.assertEqual(saved, summary)
        self.assertEqual(summary["complete_events_decoded"], 8)
        self.assertEqual(summary["buy_events"], 5)
        self.assertEqual(summary["sell_events"], 3)
        self.assertEqual(summary["fee_decompositions_exact"], 8)
        self.assertEqual(summary["instruction_aware_gross_matches_exact_outflow"], 5)
        self.assertEqual(summary["stable_prefix_user_quote_matches_exact_outflow"], 3)
        self.assertEqual(summary["previously_unexplained_mismatches_now_exactly_fee_decomposed"], 2)
        self.assertEqual(summary["nominal_fee_basis_point_counts"], {"45": 7, "50": 1})
        self.assertEqual(summary["five_buy_gross_quote_raw"], "10255334171")
        self.assertFalse(summary["historical_eligibility_changed"])


if __name__ == "__main__":
    unittest.main()
