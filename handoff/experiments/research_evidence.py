"""Offline, append-only research receipts; evidence never authorizes orders."""

import argparse
from collections import Counter
from datetime import datetime
import fcntl
import hashlib
import json
import math
from pathlib import Path
import re
import sys

EVIDENCE = {"external/unreplicated", "hypothesis", "synthetic", "explored-history",
            "prospective-paper", "registered-final", "real-execution"}
ZERO = "0" * 64
PLAN = {"lineage_id", "parent_trial_id", "revision", "hypothesis", "alternatives",
        "primary_metric", "baselines", "windows", "evidence_class", "hashes",
        "registration_hash", "proposer", "model_version", "cost_model", "universe",
        "controls", "regimes", "readout_schedule", "feature_availability",
        "owner", "economic_mechanism", "decision", "stop_schedule"}
COUNTS = {"opportunities", "fills", "executed_sides", "round_trips", "days", "episodes"}
METRICS = COUNTS | {"status", "net_account_pnl_usd", "max_drawdown_usd"}
COST = {"component_id", "amount_usd", "basis", "size", "route", "source",
        "source_hash", "valid_from_utc", "valid_until_utc", "evidence_class",
        "payer", "trader_charge", "included_in"}
EVENT = {"event_id", "utc", "kind", "trial_id", "payload"}
ROW = EVENT | {"schema", "seq", "prev_hash", "hash"}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def fields(value, expected, where):
    require(isinstance(value, dict) and set(value) == expected,
            f"{where}: required/unknown fields (expected {sorted(expected)})")


def string(value, where):
    require(isinstance(value, str) and bool(value.strip()), f"{where}: nonempty string required")


def sha(value, where):
    require(isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value),
            f"{where}: lowercase SHA-256 required")


def utc(value):
    require(isinstance(value, str) and re.fullmatch(
        r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?Z", value),
        "timestamp must be ISO-8601 UTC with Z")
    return datetime.fromisoformat(value[:-1] + "+00:00")


def number(value, where, minimum=None):
    require(type(value) in (int, float) and math.isfinite(value), f"{where}: finite number required")
    require(minimum is None or value >= minimum, f"{where}: must be >= {minimum}")


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def digest(value):
    return hashlib.sha256(canonical(value)).hexdigest()


def _pairs(items):
    result = {}
    for key, value in items:
        require(key not in result, f"duplicate JSON field: {key}")
        result[key] = value
    return result


def decode(value):
    return json.loads(value, object_pairs_hook=_pairs,
                      parse_constant=lambda value: (_ for _ in ()).throw(ValueError(f"nonfinite JSON: {value}")))


def validate_metrics(metrics):
    """Explicit sample units, account dollars, and positive-magnitude drawdown."""
    fields(metrics, METRICS, "metrics")
    for key in COUNTS:
        require(type(metrics[key]) is int and metrics[key] >= 0, f"{key}: nonnegative integer required")
    require(metrics["executed_sides"] <= metrics["fills"], "sides exceed fills")
    require(2 * metrics["round_trips"] <= metrics["executed_sides"], "round trips exceed completed sides")
    if metrics["round_trips"] == 0:
        require(metrics["status"] == "not-estimable", "no round trips: completed-trade inference is not-estimable")
    else:
        require(metrics["status"] == "estimated" and metrics["days"] > 0 and metrics["episodes"] > 0,
                "estimated metrics require days and episodes")
    if metrics["net_account_pnl_usd"] is not None:
        number(metrics["net_account_pnl_usd"], "net account P&L")
    if metrics["max_drawdown_usd"] is not None:
        number(metrics["max_drawdown_usd"], "drawdown magnitude", 0)
    return metrics


def validate_costs(receipts):
    """Sum comparable dollar charges once; preserve unknown separately from zero."""
    require(isinstance(receipts, list), "costs: list required")
    components = {}
    for receipt in receipts:
        fields(receipt, COST, "cost receipt")
        for key in ("component_id", "route", "source"):
            string(receipt[key], key)
        require(receipt["component_id"] not in components, "duplicate cost component_id")
        components[receipt["component_id"]] = receipt
        if receipt["amount_usd"] is not None:
            number(receipt["amount_usd"], "amount_usd", 0)
        sha(receipt["source_hash"], "cost source_hash")
        require(receipt["basis"] in {"per-side", "round-trip", "per-order", "account"}, "unknown cost basis")
        fields(receipt["size"], {"value", "unit"}, "cost size")
        number(receipt["size"]["value"], "size", 0)
        require(receipt["size"]["value"] > 0, "size must be positive")
        require(receipt["size"]["unit"] in {"USD", "SOL", "base-units", "contracts"}, "unknown size unit")
        require(utc(receipt["valid_from_utc"]) < utc(receipt["valid_until_utc"]), "empty cost validity")
        require(receipt["evidence_class"] in EVIDENCE, "unknown cost evidence class")
        require(receipt["payer"] in {"trader", "pool", "protocol", "other", "unknown"}, "unknown payer")
        require(type(receipt["trader_charge"]) is bool, "trader_charge: boolean required")
        require(not receipt["trader_charge"] or receipt["payer"] == "trader", "charge requires trader payer")
        require(receipt["payer"] != "trader" or receipt["trader_charge"] or receipt["included_in"] is not None,
                "trader-paid component cannot be omitted without an included_in parent")
        require(receipt["included_in"] is None or isinstance(receipt["included_in"], str), "invalid included_in")
    subdivisions = Counter()
    for receipt in receipts:
        parent_id = receipt["included_in"]
        if parent_id is None:
            continue
        require(parent_id in components and parent_id != receipt["component_id"], "unknown/self cost parent")
        parent = components[parent_id]
        require(not receipt["trader_charge"] and parent["included_in"] is None and parent["trader_charge"],
                "subdivision must be excluded from extra trader charges; parent must be a top-level charge")
        for key in ("basis", "size", "route", "valid_from_utc", "valid_until_utc"):
            require(receipt[key] == parent[key], f"incomparable cost subdivision: {key}")
        require(receipt["amount_usd"] is not None and parent["amount_usd"] is not None,
                "subdivision relationships require known amounts")
        subdivisions[parent_id] += receipt["amount_usd"]
        require(subdivisions[parent_id] <= parent["amount_usd"] + 1e-12, "subdivisions exceed parent charge")
    charges = [r for r in receipts if r["trader_charge"]]
    unknown = [r["component_id"] for r in receipts if r["amount_usd"] is None or r["payer"] == "unknown"]
    known = [r["amount_usd"] for r in charges if r["amount_usd"] is not None]
    total = math.fsum(known) if known else None
    if total is not None:
        number(total, "aggregate trader cost", 0)
    return {"known_trader_cost_usd": total,
            "status": "complete" if charges and not unknown else "partial" if known else "unknown",
            "unknown_components": unknown}


def _plan(payload, trial_id, trials, prior=None):
    fields(payload, PLAN, "plan")
    for key in ("lineage_id", "hypothesis", "primary_metric", "proposer", "model_version",
                "cost_model", "universe", "controls", "regimes", "readout_schedule", "feature_availability",
                "owner", "economic_mechanism", "decision", "stop_schedule"):
        string(payload[key], key)
    for key in ("alternatives", "baselines"):
        require(isinstance(payload[key], list) and bool(payload[key]), f"{key}: nonempty list required")
        for value in payload[key]:
            string(value, key)
        require(len(set(payload[key])) == len(payload[key]), f"duplicate {key}")
    require(payload["evidence_class"] in EVIDENCE, "unknown evidence class")
    fields(payload["hashes"], {"prompt", "code", "config", "data"}, "artifact hashes")
    for key, value in payload["hashes"].items():
        if key != "prompt" or value is not None:
            sha(value, key)
    if payload["registration_hash"] is not None:
        sha(payload["registration_hash"], "registration_hash")
    require(payload["evidence_class"] != "registered-final" or payload["registration_hash"] is not None,
            "registered-final requires a registration hash")
    fields(payload["windows"], {"development", "outcome"}, "windows")
    for window in payload["windows"].values():
        fields(window, {"start_utc", "end_utc"}, "window")
        require(utc(window["start_utc"]) < utc(window["end_utc"]), "empty window")
    require(utc(payload["windows"]["development"]["end_utc"]) <=
            utc(payload["windows"]["outcome"]["start_utc"]), "development overlaps outcome window")
    require(type(payload["revision"]) is int and payload["revision"] == (prior["revision"] + 1 if prior else 1),
            "revision must advance exactly once")
    parent = payload["parent_trial_id"]
    if parent is None:
        require(payload["lineage_id"] == trial_id, "root lineage_id must equal trial_id")
    else:
        require(isinstance(parent, str) and parent in trials and parent != trial_id, "unknown/self parent trial")
        require(payload["lineage_id"] == trials[parent]["plan"]["lineage_id"], "parent lineage mismatch")
    if prior:
        require(all(payload[k] == prior[k] for k in ("lineage_id", "parent_trial_id", "evidence_class")),
                "revision cannot change lineage or evidence class")


def validate(rows, expected_head=None):
    """Validate schema, chain, lineage and timing; an external head detects truncation."""
    trials, event_ids, attempts, artifact_access = {}, set(), set(), {}
    head, last_utc = ZERO, None
    for seq, row in enumerate(rows, 1):
        fields(row, ROW, "ledger row")
        require(type(row["schema"]) is int and row["schema"] == 1 and type(row["seq"]) is int
                and row["seq"] == seq, "schema/sequence mismatch")
        sha(row["hash"], "row hash")
        require(row["prev_hash"] == head and row["hash"] == digest({k: v for k, v in row.items() if k != "hash"}),
                "ledger integrity mismatch")
        for key in ("event_id", "trial_id"):
            string(row[key], key)
        require(row["event_id"] not in event_ids, "duplicate event_id")
        event_ids.add(row["event_id"])
        now = utc(row["utc"])
        require(last_utc is None or now >= last_utc, "record timestamps moved backwards")
        kind, tid, payload = row["kind"], row["trial_id"], row["payload"]
        if kind == "plan":
            require(tid not in trials, "duplicate trial plan")
            _plan(payload, tid, trials)
            trials[tid] = {"plan": payload, "plan_hash": row["hash"], "planned": now,
                           "frozen": None, "accesses": [], "attempts": 0}
        else:
            require(tid in trials, "event precedes trial plan")
            state = trials[tid]
            if kind == "revision":
                require(state["frozen"] is None and not state["accesses"] and not state["attempts"],
                        "frozen/accessed/attempted trial requires a new child trial")
                _plan(payload, tid, trials, state["plan"])
                state.update(plan=payload, plan_hash=row["hash"], planned=now)
            elif kind == "freeze":
                fields(payload, {"plan_hash"}, "freeze")
                require(state["frozen"] is None and payload["plan_hash"] == state["plan_hash"], "bad/duplicate freeze")
                state["frozen"] = now
            elif kind == "access":
                fields(payload, {"first_access_utc", "artifact_hash", "purpose"}, "access")
                sha(payload["artifact_hash"], "access artifact_hash")
                string(payload["purpose"], "access purpose")
                first = utc(payload["first_access_utc"])
                known_first = artifact_access.get(payload["artifact_hash"])
                require(known_first is None or first == known_first,
                        "artifact first access cannot reset across trials")
                artifact_access[payload["artifact_hash"]] = first
                require(state["frozen"] is not None and first <= now, "access needs freeze and cannot be future-dated")
                require(payload["artifact_hash"] not in {a["artifact_hash"] for a in state["accesses"]},
                        "duplicate first-access artifact")
                state["accesses"].append(payload)
            elif kind in {"result", "rejection"}:
                fields(payload, {"attempt_id", "reason"} if kind == "rejection" else
                       {"attempt_id", "evidence_class", "metrics", "costs"}, kind)
                string(payload["attempt_id"], "attempt_id")
                require(payload["attempt_id"] not in attempts, "duplicate attempt_id")
                attempts.add(payload["attempt_id"])
                state["attempts"] += 1
                if kind == "rejection":
                    string(payload["reason"], "rejection reason")
                else:
                    require(state["frozen"] is not None and state["accesses"], "result needs freeze and outcome access")
                    require(payload["evidence_class"] == state["plan"]["evidence_class"], "result evidence promotion")
                    validate_metrics(payload["metrics"])
                    validate_costs(payload["costs"])
            else:
                raise ValueError(f"unknown event kind: {kind}")
        state = trials[tid]
        plan = state["plan"]
        if plan["evidence_class"] in {"prospective-paper", "registered-final"}:
            start = utc(plan["windows"]["outcome"]["start_utc"])
            require(state["planned"] < start and (state["frozen"] is None or state["frozen"] < start),
                    "prospective plan/freeze must precede outcome window")
            for access in state["accesses"]:
                require(utc(access["first_access_utc"]) >= start, "outcomes accessed before prospective window")
            if plan["evidence_class"] == "registered-final" and kind == "result":
                end = utc(plan["windows"]["outcome"]["end_utc"])
                require(now >= end, "registered-final result before window closed")
        head, last_utc = row["hash"], now
    if expected_head is not None:
        sha(expected_head, "expected_head")
        require(head == expected_head, "external head mismatch (possible truncation/rewrite)")
    return trials


def _read(raw):
    require(not raw or raw.endswith(b"\n"), "incomplete final ledger line")
    return [decode(line) for line in raw.splitlines()]


def load(path, expected_head=None):
    rows = _read(Path(path).read_bytes())
    validate(rows, expected_head)
    return rows


def append(path, event, expected_head=None):
    """Lock, validate every existing receipt, then append one durable event."""
    fields(event, EVENT, "event")
    with Path(path).open("a+b") as ledger:
        fcntl.flock(ledger.fileno(), fcntl.LOCK_EX)
        ledger.seek(0)
        rows = _read(ledger.read())
        validate(rows, expected_head)
        row = dict(event, schema=1, seq=len(rows) + 1, prev_hash=rows[-1]["hash"] if rows else ZERO)
        row["hash"] = digest(row)
        validate(rows + [row])
        ledger.seek(0, 2)
        ledger.write(canonical(row) + b"\n")
        ledger.flush()
        import os
        os.fsync(ledger.fileno())
    return row


def report(rows, expected_head=None):
    trials = validate(rows, expected_head)
    return {"events": len(rows), "head": rows[-1]["hash"] if rows else ZERO,
            "order_authorization": False, "attempts": dict(Counter(r["kind"] for r in rows
                if r["kind"] in {"result", "rejection"})),
            "evidence_classes": dict(Counter(s["plan"]["evidence_class"] for s in trials.values())),
            "trials": [{"trial_id": tid, "lineage_id": s["plan"]["lineage_id"],
                        "parent_trial_id": s["plan"]["parent_trial_id"], "revision": s["plan"]["revision"],
                        "evidence_class": s["plan"]["evidence_class"], "plan_hash": s["plan_hash"],
                        "planned_utc": s["planned"].isoformat().replace("+00:00", "Z"),
                        "frozen_utc": s["frozen"].isoformat().replace("+00:00", "Z") if s["frozen"] else None,
                        "outcome_access": s["accesses"], "attempts": s["attempts"]}
                       for tid, s in trials.items()],
            "results": [{"trial_id": r["trial_id"], "attempt_id": r["payload"]["attempt_id"],
                         "evidence_class": r["payload"]["evidence_class"],
                         "metrics": r["payload"]["metrics"], "costs": validate_costs(r["payload"]["costs"])}
                        for r in rows if r["kind"] == "result"]}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("append", "validate", "report"))
    parser.add_argument("--ledger", type=Path, required=True)
    parser.add_argument("--event", type=Path, help="public-safe event JSON for append")
    parser.add_argument("--expected-head", help="previously exported SHA-256 anchor")
    args = parser.parse_args(argv)
    try:
        if args.command == "append":
            require(args.event is not None, "append requires --event")
            result = append(args.ledger, decode(args.event.read_bytes()), args.expected_head)
        else:
            require(args.event is None, "--event is only valid for append")
            rows = load(args.ledger, args.expected_head)
            result = report(rows) if args.command == "report" else {"valid": True, "events": len(rows),
                "head": rows[-1]["hash"] if rows else ZERO, "order_authorization": False}
        print(json.dumps(result, sort_keys=True, allow_nan=False))
        return 0
    except (ValueError, OSError, TypeError, OverflowError) as exc:
        print(f"research evidence refused: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
