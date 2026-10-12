#!/usr/bin/env python3
"""Offline SLR paper-event controller. No network, orders, credentials or invented fills.

Every monetary input is an evidence-linked assertion. A quote creates an intent;
only a separate paper fill changes inventory or cash. See Campaign_Controller.md.
"""
import argparse
import copy
import datetime as dt
from decimal import Decimal, InvalidOperation
import hashlib
import json
from pathlib import Path
from zoneinfo import ZoneInfo

from screen import evaluate, timestamp

UTC = dt.timezone.utc
ZERO = Decimal("0")
BASE58 = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
CONTROLLER_ID = "SLR-CONTROLLER-0.1"
LIVE_CONFIRMATION_FIELDS = (
    "liquidity_usd", "current_author_clusters_10m", "attention_multiple",
    "new_audience_fraction", "new_communities", "mint_agreement_fraction",
    "seasoned_new_buyer_clusters_5m", "cluster_coverage_fraction", "related_buy_fraction",
    "net_buy_usd_5m", "prior_sell_usd_5m", "sell_flow_fraction", "price_return_10m",
    "top10_holder_fraction", "creator_linked_fraction", "roundtrip_cost_fraction",
    "quote_age_seconds", "organic_attention_verified", "outside_audience_evidence_verified",
)


def money(value):
    if isinstance(value, bool):
        raise ValueError("boolean is not a monetary amount")
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise ValueError("invalid decimal amount") from exc
    if not result.is_finite():
        raise ValueError("nonfinite amount")
    return result


def positive(value, *, zero=False):
    value = money(value)
    if value < 0 or (not zero and value == 0):
        raise ValueError("amount must be positive" if not zero else "amount must be nonnegative")
    return value


def iso(stamp):
    return stamp.astimezone(UTC).isoformat()


def serial(value):
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, dt.datetime):
        return iso(value)
    if isinstance(value, dict):
        return {key: serial(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [serial(item) for item in value]
    return value


def token_identity(record):
    identity = record.get("identity", {})
    if identity.get("chain") != "solana":
        raise ValueError("SLR controller needs a Solana identity")
    mint = identity.get("mint")
    if not isinstance(mint, str) or not mint or any(c not in BASE58 for c in mint):
        raise ValueError("invalid base58 mint")
    decoded = 0
    for char in mint:
        decoded = decoded * 58 + BASE58.index(char)
    size = (decoded.bit_length() + 7) // 8 + len(mint) - len(mint.lstrip("1"))
    if size != 32 or record.get("mint", mint) != mint:
        raise ValueError("mint must be an exact 32-byte address")
    fields = ("chain", "mint", "venue", "pool", "route")
    if any(not isinstance(identity.get(key), str) or not identity[key] for key in fields):
        raise ValueError("missing venue, pool or route identity")
    return {key: identity[key] for key in fields}


class Campaign:
    def __init__(self, config, started_at, campaign_id, *, session_timezone="America/Chicago"):
        self.config = copy.deepcopy(config)
        self.campaign_id = campaign_id
        self.zone = ZoneInfo(session_timezone)
        self.started = timestamp(started_at).astimezone(UTC)
        self.last_at = self.started
        local = self.started.astimezone(self.zone)
        self.deadline = (local + dt.timedelta(days=config["account"]["campaign_max_days"])).astimezone(UTC)
        self.cash = money(config["account"]["starting_usd"])
        self.position = None
        self.pending = None
        self.first_observations = {}
        self.entry_times = []
        self.last_mint_entry = {}
        self.day_pnl = {}
        self.rent = {}
        self.liabilities = {}
        self.cost_ids = set()
        self.event_ids = set()
        self.closed = []
        self.journal = []
        self.halt = None
        self.target_verified = False
        self.target_at = None
        self.cash_revision = 0
        self.settlement_revision = None
        self.candidate_count = 0
        self.confirmed_count = 0
        self.policy_breaches = []

    def net_cash(self):
        return self.cash - sum(self.liabilities.values(), ZERO)

    def _pnl(self, now, delta):
        day = str(now.astimezone(self.zone).date())
        self.day_pnl[day] = self.day_pnl.get(day, ZERO) + delta

    def _changed(self):
        self.cash_revision += 1
        self.settlement_revision = None
        self.target_verified = False

    def _cost(self, now, amount, cost_id):
        if not cost_id or cost_id in self.cost_ids or cost_id in self.liabilities:
            raise ValueError("missing or duplicate economic cost identity")
        self.cost_ids.add(cost_id)
        self.cash -= amount
        self._pnl(now, -amount)
        self._changed()

    def _quote(self, quote, now, identity, quantity=None, *, buy=False):
        if not isinstance(quote, dict) or not quote.get("quote_id") or not quote.get("evidence"):
            raise ValueError("missing quote identity or evidence")
        if token_identity(quote) != identity:
            raise ValueError("quote identity mismatch")
        source = timestamp(quote["source_at"])
        available = timestamp(quote["available_at"])
        if source > available or available > now:
            raise ValueError("quote uses future information")
        maximum_age = self.config["entry"]["maximum_quote_age_seconds"]
        if (now - source).total_seconds() > maximum_age or (now - available).total_seconds() > maximum_age:
            raise ValueError("quote is stale")
        if quote.get("costs_complete") is not True:
            raise ValueError("quote costs incomplete: no zero-cost default")
        if quote.get("side") != ("buy" if buy else "sell"):
            raise ValueError("quote side mismatch")
        qty = positive(quote["quantity"])
        if quantity is not None and qty != quantity:
            raise ValueError("quote must cover the exact remaining quantity")
        field = "all_in_debit_usd" if buy else "net_credit_usd"
        value = positive(quote[field], zero=not buy)
        return qty, value

    def _intent(self, event, kind, **values):
        return {"action_id": event["event_id"] + ":" + kind,
                "kind": kind, "at": event["at"], "mode": "paper_only", **values}

    def _request_exit(self, event, reason):
        if self.position is None:
            return None
        p = self.position
        if p["unresolved"]:
            return self._intent(event, "UNRESOLVED_POSITION", reason=reason)
        if self.pending is not None and self.pending["kind"] == "EXIT_REQUEST":
            return self.pending.copy()
        self.pending = self._intent(event, "EXIT_REQUEST", reason=reason,
                                    identity=p["identity"], quantity=p["remaining"],
                                    position_id=p["position_id"], quote_id=None)
        return self.pending.copy()

    def _limits(self, event, now):
        if self.target_verified:
            return []
        account = self.config["account"]
        if now >= self.deadline and self.halt is None:
            self.halt = "calendar_timeout"
        if len(self.closed) >= account["campaign_max_completed_trades"] and self.halt is None:
            self.halt = "completed_trade_limit"
        if self.position is None and self.net_cash() <= money(account["campaign_stop_usd"]) and self.halt is None:
            self.halt = "campaign_floor"
        if self.pending and self.pending["kind"] == "ENTRY_READY":
            if self.halt or now > timestamp(self.pending["expires_at"]):
                self.pending = None
        actions = []
        if self.position:
            age = (now - self.position["entry_at"]).total_seconds()
            hold_deadline = self.position["entry_at"] + dt.timedelta(minutes=self.config["exit"]["maximum_hold_minutes"])
            if now > hold_deadline and not self.position.get("late_hold_recorded"):
                self.position["late_hold_recorded"] = True
                self.policy_breaches.append({"kind": "inventory_open_after_maximum_hold",
                                             "position_id": self.position["position_id"],
                                             "deadline_at": hold_deadline, "observed_at": now,
                                             "lateness_seconds": (now - hold_deadline).total_seconds()})
            if self.halt:
                actions.append(self._request_exit(event, self.halt))
            elif age >= self.config["exit"]["maximum_hold_minutes"] * 60:
                actions.append(self._request_exit(event, "maximum_hold"))
            elif age >= self.config["exit"]["time_exit_minutes_if_net_multiple_below_1_25"] * 60:
                last_quote = self.position["last_quote"]
                if last_quote is None or (now - last_quote["at"]).total_seconds() > self.config["entry"]["maximum_quote_age_seconds"]:
                    actions.append(self._intent(event, "FRESH_LIQUIDATION_QUOTE_REQUIRED", reason="90_minute_condition_unknown"))
        return [item for item in actions if item]

    def _entry_reasons(self, now, mint):
        account = self.config["account"]
        reasons = []
        if self.halt or self.target_verified or self.target_at is not None:
            reasons.append("campaign_halted")
        if self.position or self.pending:
            reasons.append("one_position_or_pending_intent")
        day = str(now.astimezone(self.zone).date())
        if self.day_pnl.get(day, ZERO) <= -money(account["session_loss_limit_usd"]):
            reasons.append("session_loss_limit")
        rolling_start = now - dt.timedelta(hours=24)
        if sum(t > rolling_start for t in self.entry_times) >= account["max_entries_per_24h"]:
            reasons.append("rolling_entry_limit")
        previous = self.last_mint_entry.get(mint)
        if previous and now - previous < dt.timedelta(hours=account["same_mint_reentry_cooldown_hours"]):
            reasons.append("same_mint_cooldown")
        return reasons

    def _candidate(self, event, now):
        self.candidate_count += 1
        record = event["record"]
        if timestamp(record["decision_at"]) != now:
            raise ValueError("candidate decision and receipt clock differ")
        result = evaluate(record, self.config, require_confirmation=False)
        if result["status"] != "PAPER_ELIGIBLE":
            self.first_observations.pop(record.get("mint"), None)
            return [{"kind": "CANDIDATE_REJECTED", **result}]
        identity = token_identity(record)
        mint = identity["mint"]
        reasons = self._entry_reasons(now, mint)
        if reasons:
            self.first_observations.pop(mint, None)
            return [self._intent(event, "ENTRY_BLOCKED", reasons=reasons)]
        first = self.first_observations.get(mint)
        max_span = self.config["entry"]["maximum_discovery_to_feature_latency_seconds"]
        if first is None or first["identity"] != identity or (now - first["at"]).total_seconds() > max_span:
            self.first_observations[mint] = {"at": now, "identity": identity, "event_id": event["event_id"],
                                             "feature_times": {name: timestamp(record["features"][name]["available_at"])
                                                               for name in LIVE_CONFIRMATION_FIELDS}}
            return [self._intent(event, "AWAIT_CONFIRMATION", mint=mint)]
        elapsed = (now - first["at"]).total_seconds()
        if elapsed < self.config["entry"]["confirmation_wait_seconds"]:
            return [self._intent(event, "AWAIT_CONFIRMATION", mint=mint, elapsed_seconds=elapsed)]
        unrefreshed = [name for name in LIVE_CONFIRMATION_FIELDS
                       if timestamp(record["features"][name]["available_at"]) <= first["feature_times"][name]]
        if unrefreshed:
            return [self._intent(event, "CONFIRMATION_REFRESH_REQUIRED", features=unrefreshed)]
        quote = event.get("entry_quote")
        if quote is None:
            return [self._intent(event, "ENTRY_QUOTE_REQUIRED", mint=mint)]
        qty, debit = self._quote(quote, now, identity, buy=True)
        required_gas = positive(quote["required_remaining_gas_usd"], zero=True)
        rent = positive(quote["rent_lock_usd"], zero=True)
        usable_liquidity = positive(quote["usable_liquidity_usd"])
        metric = quote.get("liquidity_metric")
        if not isinstance(metric, str) or not metric:
            raise ValueError("entry needs an explicit comparable liquidity metric")
        if rent and (not quote.get("rent_id") or quote["rent_id"] in self.rent):
            raise ValueError("new rent lock needs a distinct account identity")
        reserve = max(money(self.config["account"]["minimum_gas_reserve_usd"]), required_gas)
        budget = min(self.net_cash() * money(self.config["account"]["position_fraction"]), self.net_cash() - reserve - rent)
        if debit > budget or budget <= 0:
            return [self._intent(event, "ENTRY_BLOCKED", reasons=["all_in_position_or_actual_reserve_limit"], budget_usd=budget)]
        fee_ids = quote.get("included_cost_ids", [])
        if len(set(fee_ids)) != len(fee_ids) or any(c in self.cost_ids or c in self.liabilities for c in fee_ids):
            raise ValueError("entry fee already recorded")
        self.confirmed_count += 1
        self.pending = self._intent(event, "ENTRY_READY", identity=identity, quantity=qty,
                                    maximum_debit_usd=debit, quote_id=quote["quote_id"],
                                    quote=quote, first_observation=first["event_id"],
                                    expires_at=iso(timestamp(quote["source_at"]) + dt.timedelta(seconds=self.config["entry"]["maximum_quote_age_seconds"])),
                                    entry_liquidity_usd=usable_liquidity, liquidity_metric=metric)
        self.first_observations.pop(mint, None)
        return [self.pending.copy()]

    def _fill(self, event, now):
        if event.get("mode") != "paper":
            raise ValueError("only explicit paper fills accepted")
        intent = self.pending
        if intent is None or event["action_id"] != intent["action_id"]:
            raise ValueError("fill has no matching pending intent")
        if event.get("costs_complete") is not True:
            raise ValueError("fill needs net cash and token amounts after costs")
        if token_identity(event) != intent["identity"]:
            raise ValueError("fill identity mismatch")
        qty = positive(event["quantity"])
        if intent["kind"] == "ENTRY_READY":
            quote = intent["quote"]
            self._quote(quote, now, intent["identity"], buy=True)
            debit = positive(event["all_in_debit_usd"])
            if qty != money(intent["quantity"]) or debit > money(intent["maximum_debit_usd"]):
                raise ValueError("entry exceeds quoted quantity or budget")
            reserve = max(money(self.config["account"]["minimum_gas_reserve_usd"]), money(quote["required_remaining_gas_usd"]))
            rent = money(quote["rent_lock_usd"])
            if self._entry_reasons(now, intent["identity"]["mint"]) != ["one_position_or_pending_intent"]:
                raise ValueError("entry no longer permitted")
            if self.net_cash() - debit - rent < reserve or debit > self.net_cash() * money(self.config["account"]["position_fraction"]):
                raise ValueError("cash changed after quote: reserve or allocation breach")
            self.cash -= debit + rent
            if rent:
                self.rent[quote["rent_id"]] = rent
            self.cost_ids.update(quote.get("included_cost_ids", []))
            self.position = {"position_id": event["position_id"], "identity": intent["identity"],
                             "entry_at": now, "debit": debit, "original": qty, "remaining": qty,
                             "credits": ZERO, "external_costs": ZERO, "recovered": False,
                             "runner_peak": None, "entry_liquidity": money(intent["entry_liquidity_usd"]),
                             "liquidity_metric": intent["liquidity_metric"],
                             "failed_exits": 0, "unresolved": False, "stalls": [], "last_quote": None}
            self.entry_times.append(now)
            self.last_mint_entry[intent["identity"]["mint"]] = now
        else:
            p = self.position
            if p is None or event.get("position_id") != p["position_id"]:
                raise ValueError("sell has no matching position")
            if qty > p["remaining"] or qty > money(intent["quantity"]):
                raise ValueError("oversell")
            credit = positive(event["net_credit_usd"], zero=True)
            fee_ids = event.get("included_cost_ids", [])
            if len(set(fee_ids)) != len(fee_ids) or any(c in self.cost_ids or c in self.liabilities for c in fee_ids):
                raise ValueError("sell cost already recorded")
            self.cost_ids.update(fee_ids)
            self.cash += credit
            p["remaining"] -= qty
            p["credits"] += credit
            self._pnl(now, credit - p["debit"] * qty / p["original"])
            p["last_quote"] = None
            p["runner_peak"] = None if intent["kind"] == "RECOVER_CAPITAL" else p["runner_peak"]
            if intent["kind"] == "RECOVER_CAPITAL":
                # Slippage below the requested recovery is never labelled recovered.
                p["recovered"] = p["credits"] >= money(intent["recovery_target_usd"])
            if p["remaining"] == 0:
                self._close(now, "paper_fill")
        self.pending = None
        self._changed()
        actions = [self._intent(event, "PAPER_FILL_RECONCILED")]
        if self.position and self.position["recovered"] and self.position["runner_peak"] is None:
            actions.append(self._intent(event, "POST_RECOVERY_QUOTE_REQUIRED"))
        return actions

    def _close(self, now, reason):
        p = self.position
        self.closed.append({"position_id": p["position_id"], "identity": p["identity"],
                            "entry_at": p["entry_at"], "exit_at": now,
                            "net_pnl_usd": p["credits"] - p["debit"] - p["external_costs"],
                            "net_multiple": (p["credits"] - p["external_costs"]) / p["debit"],
                            "reason": reason})
        self.position = None

    def _position_quote(self, event, now):
        p = self.position
        if p is None:
            raise ValueError("quote without open position")
        quote = event["quote"]
        _, credit = self._quote(quote, now, p["identity"], p["remaining"])
        p["last_quote"] = {"at": now, "net_credit_usd": credit}
        account = self.config["account"]
        exit_rules = self.config["exit"]
        if self.net_cash() + credit <= money(account["campaign_stop_usd"]) and self.halt is None:
            self.halt = "campaign_floor"
        reason = self.halt
        if not reason and p["recovered"]:
            peak = max(p["runner_peak"] or credit, credit)
            p["runner_peak"] = peak
            if credit <= peak * (1 - money(exit_rules["runner_trailing_drawdown_fraction"])):
                reason = "runner_trailing_stop"
        if not reason and not p["recovered"] and credit + p["credits"] - p["external_costs"] <= p["debit"] * money(exit_rules["stop_net_liquidation_multiple"]):
            reason = "net_liquidation_stop"
        age = (now - p["entry_at"]).total_seconds()
        if not reason and age >= exit_rules["time_exit_minutes_if_net_multiple_below_1_25"] * 60:
            strengthened = event.get("thesis_strengthened")
            known = isinstance(strengthened, dict) and strengthened.get("value") is True and strengthened.get("evidence")
            if known:
                available = timestamp(strengthened["available_at"])
                known = available <= now and (now - available).total_seconds() <= 300
            if credit + p["credits"] - p["external_costs"] < p["debit"] * Decimal("1.25") and not known:
                reason = "stalled_90_minutes"
        if reason:
            action = self._request_exit(event, reason)
            if self.pending and self.pending["kind"] == "EXIT_REQUEST":
                self.pending["quote_id"] = quote["quote_id"]
                action = self.pending.copy()
            return [action]
        if self.pending or p["unresolved"]:
            return []
        if not p["recovered"] and credit + p["credits"] - p["external_costs"] >= p["debit"] * money(exit_rules["recover_capital_at_net_liquidation_multiple"]):
            future = positive(event["expected_remaining_exit_cost_usd"], zero=True)
            target = max(ZERO, p["debit"] + p["external_costs"] + future - p["credits"])
            candidates = []
            for partial in event.get("partial_quotes", []):
                qty, value = self._quote(partial, now, p["identity"])
                if qty < p["remaining"] and value >= target:
                    candidates.append((qty, value, partial))
            if not candidates:
                return [self._intent(event, "RECOVERY_QUOTE_REQUIRED", target_usd=target)]
            qty, value, selected = min(candidates, key=lambda item: item[0])
            self.pending = self._intent(event, "RECOVER_CAPITAL", identity=p["identity"],
                                        quantity=qty, position_id=p["position_id"],
                                        quote_id=selected["quote_id"], net_credit_usd=value,
                                        recovery_target_usd=p["debit"] + p["external_costs"] + future,
                                        minimum_scope="smallest eligible supplied size quote; lot-minimum proof still required")
            return [self.pending.copy()]
        return []

    def _failure(self, event, now):
        intent = self.pending
        if intent is None or event["action_id"] != intent["action_id"]:
            raise ValueError("failure without matching intent")
        cost = positive(event["net_usd_cost"], zero=True)
        self._cost(now, cost, event["cost_id"])
        self.pending = None
        if intent["kind"] == "ENTRY_READY":
            return [self._intent(event, "ENTRY_FAILED_NO_QUOTA_USED")]
        p = self.position
        p["external_costs"] += cost
        p["failed_exits"] += 1
        if p["failed_exits"] > self.config["exit"]["max_failed_exit_retries"]:
            p["unresolved"] = True
            return [self._intent(event, "UNRESOLVED_POSITION", failed_exits=p["failed_exits"])]
        return [self._request_exit(event, "bounded_retry_quote_required")]

    def _stall(self, event, now):
        p = self.position
        if p is None:
            raise ValueError("flow window without position")
        if token_identity(event) != p["identity"] or event.get("position_id") != p["position_id"]:
            raise ValueError("flow window identity mismatch")
        start, end = timestamp(event["window_start"]), timestamp(event["window_end"])
        if end > now or (end - start).total_seconds() != 300 or start < p["entry_at"]:
            raise ValueError("stall needs a complete post-entry five-minute window")
        if (now - end).total_seconds() > 300:
            raise ValueError("stale flow window")
        if p["stalls"] and start < p["stalls"][-1]:
            raise ValueError("overlapping or repeated flow window")
        if event.get("verified_new_buyer_flow_stalled") is not True:
            p["stalls"] = []
            return []
        if p["stalls"] and start != p["stalls"][-1]:
            p["stalls"] = []
        p["stalls"].append(end)
        if len(p["stalls"]) >= self.config["exit"]["attention_stall_complete_5m_windows"]:
            return [self._request_exit(event, "two_complete_new_buyer_stall_windows")]
        return []

    def _apply(self, event):
        event_id = event.get("event_id")
        if not event_id or event_id in self.event_ids or not event.get("evidence"):
            raise ValueError("event needs distinct identity and evidence")
        now = timestamp(event["at"]).astimezone(UTC)
        if now < self.last_at:
            raise ValueError("receipt events must be chronological")
        if event.get("source_at") and timestamp(event["source_at"]) > now:
            raise ValueError("future event source")
        self.event_ids.add(event_id)
        self.last_at = now
        actions = self._limits(event, now)
        kind = event["kind"]
        if kind == "candidate":
            actions += self._candidate(event, now)
        elif kind == "fill":
            actions += self._fill(event, now)
        elif kind == "position_quote":
            actions += self._position_quote(event, now)
        elif kind == "failure":
            actions += self._failure(event, now)
        elif kind == "buyer_flow_window":
            actions += self._stall(event, now)
        elif kind == "liquidity":
            if not self.position:
                raise ValueError("liquidity observation without position")
            if token_identity(event) != self.position["identity"]:
                raise ValueError("liquidity observation identity mismatch")
            if event.get("liquidity_metric") != self.position["liquidity_metric"]:
                raise ValueError("liquidity metrics are not comparable")
            available = timestamp(event["available_at"])
            if available > now or (now - available).total_seconds() > 300:
                raise ValueError("stale or future liquidity observation")
            value = positive(event["usable_liquidity_usd"], zero=True)
            if value <= self.position["entry_liquidity"] * (1 - money(self.config["exit"]["liquidity_drop_fraction"])):
                actions.append(self._request_exit(event, "usable_liquidity_drop"))
        elif kind == "cost":
            self._cost(now, positive(event["net_usd_cost"], zero=True), event["cost_id"])
        elif kind == "cost_accrual":
            identifier, amount = event["cost_id"], positive(event["net_usd_cost"], zero=True)
            if not identifier or identifier in self.cost_ids or identifier in self.liabilities:
                raise ValueError("economic cost already included")
            self.liabilities[identifier] = amount
            self._pnl(now, -amount)
            self._changed()
        elif kind == "cost_settlement":
            identifier = event["cost_id"]
            if identifier not in self.liabilities:
                raise ValueError("settlement without fee reserve")
            reserved = self.liabilities.pop(identifier)
            amount = positive(event["net_usd_cost"], zero=True)
            self.cost_ids.add(identifier)
            self.cash -= amount
            self._pnl(now, reserved - amount)
            self._changed()
        elif kind == "rent_refund":
            identifier = event["rent_id"]
            amount = positive(event["net_refund_usd"], zero=True)
            if identifier not in self.rent or amount > self.rent[identifier]:
                raise ValueError("refund exceeds the unreclaimed lock")
            # Any USD difference or closure fee is a separate evidence-linked cost.
            self.cash += amount
            self.rent[identifier] -= amount
            if self.rent[identifier] == 0:
                del self.rent[identifier]
            self._changed()
        elif kind == "writeoff":
            p = self.position
            if not p or token_identity(event) != p["identity"] or event.get("position_id") != p["position_id"] or event.get("documented_zero_recovery") is not True:
                raise ValueError("writeoff requires exact-position zero-recovery evidence")
            if money(event["quantity"]) != p["remaining"]:
                raise ValueError("writeoff must cover the entire remainder")
            self._pnl(now, -p["debit"] * p["remaining"] / p["original"])
            self._close(now, "documented_zero_recovery")
            self.pending = None
            self._changed()
        elif kind == "settlement_check":
            required = ("all_costs_verified", "funding_and_conversion_verified", "no_other_inventory_verified")
            if any(event.get(key) is not True for key in required) or money(event["net_recoverable_usd"]) != self.net_cash():
                raise ValueError("recovery check incomplete or does not reconcile")
            if self.position or self.pending or self.liabilities:
                raise ValueError("cannot certify an open position, intent or unpaid fee")
            self.settlement_revision = self.cash_revision
            # The final allowed position may achieve the target; the trade cap
            # blocks another entry while its flat balance is being reconciled.
            if self.halt in (None, "completed_trade_limit") and now < self.deadline and self.net_cash() > money(self.config["account"]["campaign_target_usd_strictly_greater_than"]):
                self.target_verified = True
                self.target_at = now
                actions.append(self._intent(event, "CONDITIONAL_PAPER_TARGET_MET"))
        elif kind != "heartbeat":
            raise ValueError("unknown event kind")
        if kind == "position_quote":
            actions = [action for action in actions if action.get("kind") != "FRESH_LIQUIDATION_QUOTE_REQUIRED"]
        if self.cash < 0 or self.net_cash() < 0:
            raise ValueError("negative cash requires outside capital")
        actions += self._limits(event, now)
        # Equal repeated timer actions within one receipt are not distinct attempts.
        actions = list({item["action_id"] if "action_id" in item else "gate:" + event_id: item for item in actions if item}.values())
        result = {"event_id": event_id, "at": iso(now), "kind": kind,
                  "input_sha256": hashlib.sha256(json.dumps(event, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest(),
                  "actions": actions, "cash_usd": self.cash, "net_cash_usd": self.net_cash(),
                  "open_position": self.position is not None, "halt": self.halt}
        self.journal.append(serial(result))
        return serial(result)

    def process(self, event):
        # Malformed events cannot leave half-applied balances or consume quotas.
        staged = copy.deepcopy(self)
        result = staged._apply(copy.deepcopy(event))
        self.__dict__.update(staged.__dict__)
        return result

    def summary(self):
        if self.target_verified:
            status = "conditional_paper_target_met"
        elif self.position and self.position["unresolved"]:
            status = "unresolved_position_no_performance_claim"
        elif self.halt:
            status = "exit_pending_" + self.halt if self.position else "failed_" + self.halt
        elif self.target_at is not None:
            status = "target_revoked_pending_cost_reconciliation"
        else:
            status = "active_open_position" if self.position else "active_no_target"
        return serial({"controller_id": CONTROLLER_ID, "campaign_id": self.campaign_id,
                       "strategy_id": self.config["strategy_id"], "status": status,
                       "started_at_utc": self.started, "calendar_deadline_utc": self.deadline,
                       "last_received_at_utc": self.last_at, "session_timezone": self.zone.key,
                       "starting_usd": self.config["account"]["starting_usd"],
                       "cash_usd": self.cash, "unpaid_cost_reserves_usd": self.liabilities,
                       "locked_rent_excluded_usd": self.rent, "net_cash_usd": self.net_cash(),
                       "open_position": self.position, "pending_paper_intent": self.pending,
                       "actual_paper_entries": len(self.entry_times), "closed_paper_positions": self.closed,
                       "realized_session_pnl_usd": self.day_pnl, "candidate_records": self.candidate_count,
                       "confirmed_entry_intents": self.confirmed_count,
                       "policy_breaches": self.policy_breaches,
                       "conditional_target_met": self.target_verified,
                       "verified_real_trades": 0, "verified_real_doubling_campaigns": 0,
                       "inputs_independently_authenticated": False,
                       "note": "Quote intents and synthetic fixtures are not fills or profitability evidence. Monetary/eligibility assertions need external adapters; runtime gaps never backdate execution."})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("events", help="chronological JSONL paper receipt events")
    parser.add_argument("--started-at", required=True)
    parser.add_argument("--campaign-id", required=True)
    parser.add_argument("--config", default=str(Path(__file__).with_name("strategy.json")))
    parser.add_argument("--output", required=True, help="new output directory, never overwrite a replay")
    args = parser.parse_args()
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=False)
    campaign = Campaign(json.loads(Path(args.config).read_text()), args.started_at, args.campaign_id)
    with Path(args.events).open() as source, (output / "journal.jsonl").open("w") as journal:
        for line in source:
            if line.strip():
                journal.write(json.dumps(campaign.process(json.loads(line)), allow_nan=False) + "\n")
    (output / "summary.json").write_text(json.dumps(campaign.summary(), indent=2) + "\n")
    print(json.dumps({key: campaign.summary()[key] for key in ("status", "cash_usd", "actual_paper_entries", "conditional_target_met")}))


if __name__ == "__main__":
    main()
