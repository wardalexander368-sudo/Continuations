"""Adverse synthetic accounting cases. No observed market outcomes or profit tests."""
import copy
import datetime as dt
import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from campaign_controller import Campaign, money, iso, UTC
from screen import BOOLEAN_FIELDS

CONFIG = json.loads((Path(__file__).resolve().parents[1] / "strategy.json").read_text())
MINT = "2j5SaS7xy776qCBpyPQbZjyQSAtKiFgrwjfErthnW2ZM"
SECOND_MINT = "So11111111111111111111111111111111111111112"
EVIDENCE = "SYNTHETIC ACCOUNTING FIXTURE; not observed token/wallet/market evidence"


def identity(mint=MINT, pool="synthetic_pool"):
    return {"chain": "solana", "mint": mint, "venue": "synthetic_venue",
            "pool": pool, "route": "synthetic_pumpportal_local"}


def record(now, mint=MINT, pool="synthetic_pool"):
    values = {name: True for name in BOOLEAN_FIELDS}
    values.update(token_age_hours=24, liquidity_usd=50000,
                  previous_wave_author_clusters=30, cooldown_minutes=90,
                  cooldown_attention_fraction=0.4, current_author_clusters_10m=20,
                  attention_multiple=3, new_audience_fraction=0.8, new_communities=3,
                  mint_agreement_fraction=0.9, seasoned_new_buyer_clusters_5m=10,
                  cluster_coverage_fraction=0.9, related_buy_fraction=0.1,
                  net_buy_usd_5m=100, prior_sell_usd_5m=100, sell_flow_fraction=0.4,
                  price_return_10m=0.05, top10_holder_fraction=0.3,
                  creator_linked_fraction=0.05, roundtrip_cost_fraction=0.05,
                  quote_age_seconds=0, feature_latency_seconds=60,
                  confirmation_seconds=999999)
    return {"mint": mint, "identity": identity(mint, pool), "decision_at": iso(now),
            "features": {name: {"value": value, "available_at": iso(now), "evidence": EVIDENCE}
                         for name, value in values.items()}}


class Fixture:
    def __init__(self, start="2026-10-12T00:00:00Z", config=None):
        self.config = copy.deepcopy(config or CONFIG)
        self.c = Campaign(self.config, start, "synthetic-engineering-campaign")
        self.now = self.c.started
        self.n = 0

    def send(self, kind, *, advance=0, at=None, **fields):
        self.now = at or self.now + dt.timedelta(seconds=advance)
        self.n += 1
        return self.c.process({"event_id": "fixture-" + str(self.n), "kind": kind,
                               "at": iso(self.now), "evidence": EVIDENCE, **fields})

    def quote(self, value, *, buy=False, qty=None, mint=None, pool="synthetic_pool", rent="0", gas="5"):
        if mint is None:
            mint = self.c.position["identity"]["mint"] if self.c.position else MINT
        if qty is None:
            qty = self.c.position["remaining"] if self.c.position else money("1")
        q = {"quote_id": "synthetic-q-" + str(self.n + 1) + "-" + str(qty),
             "identity": identity(mint, pool), "source_at": iso(self.now),
             "available_at": iso(self.now), "evidence": EVIDENCE,
             "side": "buy" if buy else "sell", "quantity": str(qty), "costs_complete": True}
        if buy:
            q.update(all_in_debit_usd=str(value), required_remaining_gas_usd=gas,
                     rent_lock_usd=rent, rent_id="rent-" + str(self.n + 1),
                     usable_liquidity_usd="50000", liquidity_metric="synthetic_comparable_capacity",
                     included_cost_ids=["entry-included-fee-" + str(self.n + 1)])
        else:
            q["net_credit_usd"] = str(value)
        return q

    def candidate(self, *, advance=0, quote=None, mint=MINT, pool="synthetic_pool"):
        self.now += dt.timedelta(seconds=advance)
        fields = {"record": record(self.now, mint, pool)}
        if quote is not None:
            fields["entry_quote"] = quote
        return self.send("candidate", **fields)

    def open(self, *, mint=MINT, rent="0", gas="5"):
        self.candidate(mint=mint)
        self.now += dt.timedelta(seconds=60)
        debit = self.c.net_cash() * money("0.14")
        self.candidate(mint=mint, quote=self.quote(debit, buy=True, mint=mint, rent=rent, gas=gas))
        intent = self.c.pending
        if not intent:
            return None
        self.send("fill", advance=1, mode="paper", action_id=intent["action_id"],
                  identity=intent["identity"], position_id="p-" + str(self.n),
                  quantity=str(intent["quantity"]), all_in_debit_usd=str(debit), costs_complete=True)
        return self.c.position

    def close(self, credit):
        p = self.c.position
        self.send("liquidity", identity=p["identity"], available_at=iso(self.now), usable_liquidity_usd="40000", liquidity_metric="synthetic_comparable_capacity")
        intent = self.c.pending
        return self.send("fill", mode="paper", action_id=intent["action_id"],
                         identity=p["identity"], position_id=p["position_id"],
                         quantity=str(p["remaining"]), net_credit_usd=str(credit), costs_complete=True)

    def recovery_check(self, value=None):
        return self.send("settlement_check", net_recoverable_usd=str(value or self.c.net_cash()),
                         all_costs_verified=True, funding_and_conversion_verified=True,
                         no_other_inventory_verified=True)


class CampaignTests(unittest.TestCase):
    def test_asserted_confirmation_cannot_skip_real_wait(self):
        f = Fixture()
        first = f.candidate(quote=f.quote("7", buy=True))
        self.assertEqual(first["actions"][0]["kind"], "AWAIT_CONFIRMATION")
        f.now += dt.timedelta(seconds=59)
        second = f.candidate(quote=f.quote("7", buy=True))
        self.assertEqual(second["actions"][0]["kind"], "AWAIT_CONFIRMATION")
        f.now += dt.timedelta(seconds=1)
        third = f.candidate(quote=f.quote("7", buy=True))
        self.assertEqual(third["actions"][0]["kind"], "ENTRY_READY")
        self.assertEqual(f.c.cash, money(50))
        self.assertEqual(len(f.c.entry_times), 0)

    def test_identity_change_and_long_gap_restart_confirmation(self):
        f = Fixture()
        f.candidate()
        result = f.candidate(advance=60, pool="different_pool")
        self.assertEqual(result["actions"][0]["kind"], "AWAIT_CONFIRMATION")
        result = f.candidate(advance=301, pool="different_pool")
        self.assertEqual(result["actions"][0]["kind"], "AWAIT_CONFIRMATION")

    def test_repackaging_first_dynamic_feature_does_not_confirm(self):
        f = Fixture()
        first_time = f.now
        f.candidate()
        f.now += dt.timedelta(seconds=60)
        r = record(f.now)
        r["features"]["net_buy_usd_5m"]["available_at"] = iso(first_time)
        result = f.send("candidate", record=r, entry_quote=f.quote("7", buy=True))
        self.assertEqual(result["actions"][0]["kind"], "CONFIRMATION_REFRESH_REQUIRED")
        self.assertIn("net_buy_usd_5m", result["actions"][0]["features"])
        self.assertIsNone(f.c.pending)

    def test_unknown_or_false_us_eligibility_rejects(self):
        f = Fixture()
        r = record(f.now)
        r["features"]["spot_us_access_verified"]["value"] = False
        result = f.send("candidate", record=r)
        self.assertIn("failed:spot_us_access_verified", result["actions"][0]["reasons"])
        self.assertIsNone(f.c.pending)

    def test_stale_and_future_quote_are_atomic_errors(self):
        for offset in (-3, 1):
            with self.subTest(offset=offset):
                f = Fixture(); f.candidate(); f.now += dt.timedelta(seconds=60)
                q = f.quote("7", buy=True)
                q["source_at"] = iso(f.now + dt.timedelta(seconds=offset))
                before = f.c.summary()
                with self.assertRaises(ValueError):
                    f.candidate(quote=q)
                self.assertEqual(f.c.summary(), before)

    def test_required_gas_can_exceed_nominal_reserve(self):
        f = Fixture()
        self.assertIsNone(f.open(gas="45"))
        self.assertEqual(f.c.cash, money(50))
        self.assertIsNone(f.c.pending)

    def test_rent_is_locked_cash_until_evidenced_refund(self):
        f = Fixture(); f.open(rent="0.30")
        self.assertEqual(f.c.cash, money("42.70"))
        self.assertEqual(sum(f.c.rent.values()), money("0.30"))
        rent_id = next(iter(f.c.rent))
        f.close("7")
        self.assertEqual(f.c.net_cash(), money("49.70"))
        f.send("rent_refund", rent_id=rent_id, net_refund_usd="0.30")
        self.assertEqual(f.c.net_cash(), money(50))
        with self.assertRaises(ValueError):
            f.send("rent_refund", rent_id=rent_id, net_refund_usd="0.30")

    def test_fee_accrual_settlement_is_not_double_cost(self):
        f = Fixture()
        f.send("cost_accrual", cost_id="deferred-fee", net_usd_cost="0.20")
        self.assertEqual(f.c.cash, money(50))
        self.assertEqual(f.c.net_cash(), money("49.80"))
        f.send("cost_settlement", cost_id="deferred-fee", net_usd_cost="0.25")
        self.assertEqual(f.c.net_cash(), money("49.75"))
        self.assertEqual(sum(f.c.day_pnl.values()), money("-0.25"))
        with self.assertRaises(ValueError):
            f.send("cost", cost_id="deferred-fee", net_usd_cost="0.25")

    def test_fee_already_in_net_fill_cannot_be_charged_again(self):
        f = Fixture(); f.open()
        fee = next(iter(f.c.cost_ids))
        with self.assertRaises(ValueError):
            f.send("cost_accrual", cost_id=fee, net_usd_cost="0.10")

    def test_cost_after_entry_quote_invalidates_original_allocation(self):
        f = Fixture(); f.candidate(); f.now += dt.timedelta(seconds=60)
        f.candidate(quote=f.quote("7", buy=True))
        intent = f.c.pending.copy()
        f.send("cost", cost_id="new-data-cost", net_usd_cost="0.50")
        with self.assertRaises(ValueError):
            f.send("fill", mode="paper", action_id=intent["action_id"], identity=intent["identity"],
                   position_id="p", quantity="1", all_in_debit_usd="7", costs_complete=True)
        self.assertEqual(f.c.cash, money("49.50"))
        self.assertEqual(len(f.c.entry_times), 0)

    def test_failed_entry_pays_cost_but_uses_no_quota_or_cooldown(self):
        f = Fixture(); f.candidate(); f.now += dt.timedelta(seconds=60)
        f.candidate(quote=f.quote("7", buy=True))
        intent = f.c.pending.copy()
        f.send("failure", action_id=intent["action_id"], cost_id="failed-entry-gas", net_usd_cost="0.03")
        self.assertEqual(f.c.cash, money("49.97"))
        self.assertEqual(f.c.entry_times, [])
        self.assertEqual(f.c.last_mint_entry, {})

    def test_three_entries_rolling_limit_and_exact_boundary(self):
        f = Fixture()
        for index in range(3):
            f.open(mint=(MINT, SECOND_MINT, "11111111111111111111111111111111")[index])
            f.close("7")
        result = f.candidate(mint="TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA")
        self.assertIn("rolling_entry_limit", result["actions"][0]["reasons"])
        f.now = f.c.entry_times[0] + dt.timedelta(hours=24)
        result = f.candidate()
        self.assertEqual(result["actions"][0]["kind"], "AWAIT_CONFIRMATION")

    def test_same_mint_cooldown_requires_24_hours(self):
        f = Fixture(); f.open(); f.close("7")
        result = f.candidate(advance=1)
        self.assertIn("same_mint_cooldown", result["actions"][0]["reasons"])

    def test_session_cost_loss_resets_at_chicago_midnight(self):
        f = Fixture()
        f.send("cost", at=dt.datetime(2026, 10, 12, 4, 59, 50, tzinfo=UTC), cost_id="data", net_usd_cost="5")
        result = f.candidate()
        self.assertIn("session_loss_limit", result["actions"][0]["reasons"])
        f.now = dt.datetime(2026, 10, 12, 5, 0, 0, tzinfo=UTC)
        result = f.candidate()
        self.assertEqual(result["actions"][0]["kind"], "AWAIT_CONFIRMATION")
        self.assertEqual(f.c.cash, money(45))

    def test_calendar_deadline_is_local_30_days_across_dst(self):
        f = Fixture()
        self.assertEqual(iso(f.c.deadline), "2026-11-11T01:00:00+00:00")
        self.assertEqual((f.c.deadline - f.c.started).total_seconds(), 721 * 3600)
        f.send("heartbeat", at=f.c.deadline)
        self.assertEqual(f.c.summary()["status"], "failed_calendar_timeout")
        self.assertFalse(f.c.target_verified)
        self.assertEqual(f.c.cash, money(50))

    def test_stop_request_cannot_book_a_threshold_fill(self):
        f = Fixture(); f.open()
        result = f.send("position_quote", quote=f.quote("5.60"))
        self.assertEqual(result["actions"][0]["kind"], "EXIT_REQUEST")
        self.assertEqual(f.c.cash, money(43))
        self.assertEqual(f.c.closed, [])
        intent = f.c.pending.copy(); p = f.c.position
        f.send("fill", mode="paper", action_id=intent["action_id"], identity=p["identity"],
               position_id=p["position_id"], quantity="1", net_credit_usd="0.50", costs_complete=True)
        self.assertEqual(f.c.cash, money("43.50"))
        self.assertEqual(f.c.closed[0]["net_pnl_usd"], money("-6.50"))

    def test_retries_are_initial_plus_two_then_unresolved(self):
        f = Fixture(); f.open(); f.send("position_quote", quote=f.quote("5.50"))
        for index in range(3):
            f.send("failure", action_id=f.c.pending["action_id"], cost_id="exit-fee-" + str(index), net_usd_cost="0.03")
        self.assertEqual(f.c.cash, money("42.91"))
        self.assertTrue(f.c.position["unresolved"])
        self.assertEqual(f.c.position["failed_exits"], 3)
        self.assertEqual(f.c.closed, [])
        self.assertIsNone(f.c.pending)
        self.assertFalse(f.c.summary()["conditional_target_met"])

    def test_size_specific_partial_recovery_then_runner_trail(self):
        f = Fixture(); f.open()
        f.send("position_quote", quote=f.quote("14.20"), expected_remaining_exit_cost_usd="0.02",
               partial_quotes=[f.quote("6.99", qty="0.50"), f.quote("7.03", qty="0.51"), f.quote("8.00", qty="0.60")])
        intent = f.c.pending.copy(); p = f.c.position
        self.assertEqual(intent["quantity"], money("0.51"))
        f.send("fill", mode="paper", action_id=intent["action_id"], identity=p["identity"],
               position_id=p["position_id"], quantity="0.51", net_credit_usd="7.03", costs_complete=True)
        self.assertTrue(f.c.position["recovered"])
        self.assertEqual(f.c.cash, money("50.03"))
        f.send("position_quote", quote=f.quote("8"))
        result = f.send("position_quote", quote=f.quote("6"))
        self.assertEqual(result["actions"][0]["reason"], "runner_trailing_stop")
        self.assertEqual(f.c.cash, money("50.03"))

    def test_recovery_slippage_below_target_is_not_recovered(self):
        f = Fixture(); f.open()
        f.send("position_quote", quote=f.quote("14.20"), expected_remaining_exit_cost_usd="0.02",
               partial_quotes=[f.quote("7.03", qty="0.51")])
        p = f.c.position; intent = f.c.pending.copy()
        f.send("fill", mode="paper", action_id=intent["action_id"], identity=p["identity"],
               position_id=p["position_id"], quantity="0.51", net_credit_usd="6.90", costs_complete=True)
        self.assertFalse(f.c.position["recovered"])

    def test_90_minute_missing_quote_requests_valuation(self):
        f = Fixture(); f.open()
        result = f.send("heartbeat", advance=90 * 60)
        self.assertIn("FRESH_LIQUIDATION_QUOTE_REQUIRED", [a["kind"] for a in result["actions"]])
        self.assertIsNone(f.c.pending)
        self.assertEqual(f.c.cash, money(43))
        result = f.send("position_quote", quote=f.quote("8"))
        self.assertEqual(result["actions"][0]["reason"], "stalled_90_minutes")

    def test_strengthened_thesis_defers_90_minute_exit(self):
        f = Fixture(); f.open(); f.now += dt.timedelta(seconds=90 * 60)
        f.send("position_quote", quote=f.quote("8"), thesis_strengthened={"value":True,"available_at":iso(f.now),"evidence":EVIDENCE})
        self.assertIsNone(f.c.pending)

    def test_runtime_gap_records_lateness_without_backdating_fill(self):
        f = Fixture(); f.open()
        result = f.send("heartbeat", advance=6 * 3600 + 125)
        self.assertEqual(result["actions"][0]["reason"], "maximum_hold")
        self.assertEqual(f.c.policy_breaches[0]["lateness_seconds"], 125)
        self.assertEqual(f.c.closed, [])
        self.assertEqual(f.c.cash, money(43))

    def test_maximum_hold_supersedes_unfilled_partial_intent(self):
        f = Fixture(); f.open()
        f.send("position_quote", quote=f.quote("14.20"), expected_remaining_exit_cost_usd="0.02",
               partial_quotes=[f.quote("7.03", qty="0.51")])
        self.assertEqual(f.c.pending["kind"], "RECOVER_CAPITAL")
        f.send("heartbeat", advance=6 * 3600)
        self.assertEqual(f.c.pending["kind"], "EXIT_REQUEST")
        self.assertEqual(f.c.pending["quantity"], money(1))

    def test_stall_windows_must_be_complete_consecutive_distinct_and_exact_pool(self):
        f = Fixture(); p = f.open(); start = f.now
        fields = {"identity":p["identity"],"position_id":p["position_id"],"verified_new_buyer_flow_stalled":True}
        f.send("buyer_flow_window", advance=300, window_start=iso(start), window_end=iso(start+dt.timedelta(seconds=300)), **fields)
        with self.assertRaises(ValueError):
            f.send("buyer_flow_window", window_start=iso(start), window_end=iso(start+dt.timedelta(seconds=300)), **fields)
        result = f.send("buyer_flow_window", advance=300, window_start=iso(start+dt.timedelta(seconds=300)), window_end=iso(start+dt.timedelta(seconds=600)), **fields)
        self.assertEqual(result["actions"][0]["reason"], "two_complete_new_buyer_stall_windows")

    def test_exact_dust_remainder_stays_open(self):
        f = Fixture(); p = f.open()
        f.send("liquidity", identity=p["identity"], available_at=iso(f.now), usable_liquidity_usd="40000", liquidity_metric="synthetic_comparable_capacity")
        intent = f.c.pending.copy()
        f.send("fill", mode="paper", action_id=intent["action_id"], identity=p["identity"],
               position_id=p["position_id"], quantity="0.999999999", net_credit_usd="57.10", costs_complete=True)
        self.assertEqual(f.c.position["remaining"], money("0.000000001"))
        self.assertEqual(f.c.closed, [])
        with self.assertRaises(ValueError):
            f.recovery_check()

    def test_exact_100_is_not_success_and_unpaid_fees_prevent_certification(self):
        for credit, expected in (("57", False), ("57.10", True)):
            with self.subTest(credit=credit):
                f = Fixture(); f.open(); f.close(credit)
                self.assertFalse(f.c.target_verified)
                f.recovery_check()
                self.assertEqual(f.c.target_verified, expected)
        f = Fixture(); f.open(); f.close("57.10")
        f.send("cost_accrual", cost_id="not-posted", net_usd_cost="0.20")
        self.assertEqual(f.c.net_cash(), money("99.90"))
        with self.assertRaises(ValueError):
            f.recovery_check()

    def test_post_target_cost_revokes_claim_until_reconciled(self):
        f = Fixture(); f.open(); f.close("57.10"); f.recovery_check()
        self.assertTrue(f.c.target_verified)
        f.send("cost", cost_id="late-conversion", net_usd_cost="0.20")
        self.assertFalse(f.c.target_verified)
        self.assertEqual(f.c.net_cash(), money("99.90"))
        result = f.candidate(mint=SECOND_MINT)
        self.assertIn("campaign_halted",result["actions"][0]["reasons"])

    def test_campaign_floor_is_not_a_guaranteed_fill_price(self):
        f = Fixture(); p = f.open()
        f.send("writeoff",identity=p["identity"],position_id=p["position_id"],quantity="1",documented_zero_recovery=True)
        f.now += dt.timedelta(hours=24)
        p = f.open()
        f.send("writeoff",identity=p["identity"],position_id=p["position_id"],quantity="1",documented_zero_recovery=True)
        self.assertEqual(f.c.cash,money("36.98"))
        self.assertEqual(f.c.halt,"campaign_floor")
        self.assertEqual(f.c.summary()["status"],"failed_campaign_floor")

    def test_missing_costs_or_comparable_liquidity_prevent_entry(self):
        for field in ("costs_complete", "liquidity_metric"):
            with self.subTest(field=field):
                f = Fixture(); f.candidate(); f.now += dt.timedelta(seconds=60)
                q = f.quote("7",buy=True); del q[field]
                with self.assertRaises(ValueError):
                    f.candidate(quote=q)
                self.assertIsNone(f.c.pending)

    def test_liquidity_metric_cannot_switch_from_capacity_to_total_tvl(self):
        f = Fixture(); p = f.open()
        with self.assertRaises(ValueError):
            f.send("liquidity",identity=p["identity"],available_at=iso(f.now),usable_liquidity_usd="40000",liquidity_metric="synthetic_other_total_tvl")
        self.assertIsNone(f.c.pending)

    def test_30th_position_can_qualify_but_no_31st_entry(self):
        f = Fixture()
        for index in range(30):
            f.now = f.c.started + dt.timedelta(days=index)
            p = f.open(mint=MINT if index % 2 == 0 else SECOND_MINT)
            f.close("57.10" if index == 29 else p["debit"])
        self.assertEqual(len(f.c.closed), 30)
        self.assertEqual(f.c.halt, "completed_trade_limit")
        f.recovery_check()
        self.assertTrue(f.c.target_verified)
        result = f.candidate(mint=SECOND_MINT)
        self.assertIn("campaign_halted", result["actions"][0]["reasons"])

    def test_late_recovery_after_calendar_timeout_cannot_be_success(self):
        f = Fixture(); p = f.open()
        f.send("heartbeat", at=f.c.deadline)
        intent = f.c.pending.copy()
        f.send("fill", mode="paper", action_id=intent["action_id"], identity=p["identity"],
               position_id=p["position_id"], quantity="1", net_credit_usd="57.10", costs_complete=True)
        f.recovery_check()
        self.assertEqual(f.c.cash, money("100.10"))
        self.assertFalse(f.c.target_verified)
        self.assertEqual(f.c.summary()["status"], "failed_calendar_timeout")

    def test_duplicate_or_nonchronological_events_cannot_mutate_balances(self):
        f = Fixture()
        event={"event_id":"same","kind":"cost","at":iso(f.now),"evidence":EVIDENCE,"cost_id":"cost","net_usd_cost":"0.10"}
        f.c.process(event); before=f.c.summary()
        with self.assertRaises(ValueError):
            f.c.process(event)
        event.update(event_id="earlier",cost_id="earlier",at=iso(f.now-dt.timedelta(seconds=1)))
        with self.assertRaises(ValueError):
            f.c.process(event)
        self.assertEqual(f.c.summary(),before)

    def test_documented_writeoff_is_required_for_zero_recovery(self):
        f = Fixture(); p = f.open()
        fields={"identity":p["identity"],"position_id":p["position_id"],"quantity":"1"}
        with self.assertRaises(ValueError):
            f.send("writeoff",documented_zero_recovery=False,**fields)
        f.send("writeoff",documented_zero_recovery=True,**fields)
        self.assertEqual(f.c.cash,money(43))
        self.assertEqual(f.c.closed[0]["net_multiple"],money(0))


if __name__ == "__main__":
    unittest.main()
