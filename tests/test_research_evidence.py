"""Synthetic integrity cases; no market/network/account data or orders."""

from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
import importlib.util
import json
from pathlib import Path
import subprocess
import sys

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "handoff/experiments/research_evidence.py"
spec = importlib.util.spec_from_file_location("research_evidence", SCRIPT)
evidence = importlib.util.module_from_spec(spec)
spec.loader.exec_module(evidence)
H = "a" * 64
PLAN_TIME = "2026-10-01T10:00:00Z"
FREEZE_TIME = "2026-10-01T11:00:00Z"
ACCESS_TIME = "2026-10-04T10:00:00Z"


def plan(evidence_class="synthetic"):
    return {"lineage_id": "trial-1", "parent_trial_id": None, "revision": 1,
            "hypothesis": "Synthetic control only", "proposer": "synthetic-reviewer", "model_version": "not-used",
            "cost_model": "synthetic fixed dollars", "universe": "synthetic fixtures", "controls": "cash",
            "regimes": "all fixtures", "readout_schedule": "once after window", "feature_availability": "fixture time",
            "owner": "synthetic-reviewer", "economic_mechanism": "synthetic null fixture; no economic claim",
            "decision": "reject fixture on failed integrity check", "stop_schedule": "stop at fixed window end",
            "alternatives": ["null control"],
            "primary_metric": "net_account_pnl_usd", "baselines": ["cash"],
            "windows": {"development": {"start_utc": "2026-09-01T00:00:00Z", "end_utc": "2026-10-01T00:00:00Z"},
                        "outcome": {"start_utc": "2026-10-02T00:00:00Z", "end_utc": "2026-10-03T00:00:00Z"}},
            "evidence_class": evidence_class, "hashes": {"prompt": None, "code": H, "config": H, "data": H},
            "registration_hash": H if evidence_class == "registered-final" else None}


def event(kind, payload, at=ACCESS_TIME, event_id=None, trial_id="trial-1"):
    return {"event_id": event_id or kind, "utc": at, "kind": kind, "trial_id": trial_id, "payload": payload}


def prepared(tmp_path, evidence_class="synthetic"):
    ledger = tmp_path / "evidence.jsonl"
    planned = evidence.append(ledger, event("plan", plan(evidence_class), PLAN_TIME))
    evidence.append(ledger, event("freeze", {"plan_hash": planned["hash"]}, FREEZE_TIME))
    evidence.append(ledger, event("access", {"first_access_utc": ACCESS_TIME, "artifact_hash": H,
                                             "purpose": "synthetic fixture"}))
    return ledger


def metrics(empty=False):
    return {"status": "not-estimable" if empty else "estimated", "opportunities": 0 if empty else 3, "fills": 0 if empty else 6,
            "executed_sides": 0 if empty else 4, "round_trips": 0 if empty else 2,
            "days": 0 if empty else 2, "episodes": 0 if empty else 1,
            "net_account_pnl_usd": None if empty else 4.0, "max_drawdown_usd": None if empty else 2.0}


def receipt(component_id="pool-fee", amount=1.0, **overrides):
    return dict({"component_id": component_id, "amount_usd": amount, "basis": "per-side",
                 "size": {"value": 100.0, "unit": "USD"}, "route": "synthetic-route",
                 "source": "https://example.invalid/synthetic-receipt", "source_hash": H,
                 "valid_from_utc": "2026-10-01T00:00:00Z", "valid_until_utc": "2026-10-05T00:00:00Z",
                 "evidence_class": "synthetic", "payer": "trader", "trader_charge": True,
                 "included_in": None}, **overrides)


def outcome(evidence_class="synthetic", attempt_id="attempt-1"):
    return {"attempt_id": attempt_id, "evidence_class": evidence_class,
            "metrics": metrics(), "costs": [receipt()]}


def rechain(rows):
    head = evidence.ZERO
    plans = {}
    for index, row in enumerate(rows, 1):
        row["seq"], row["prev_hash"] = index, head
        if row["kind"] == "freeze":
            row["payload"]["plan_hash"] = plans[row["trial_id"]]
        row["hash"] = evidence.digest({k: v for k, v in row.items() if k != "hash"})
        if row["kind"] in {"plan", "revision"}:
            plans[row["trial_id"]] = row["hash"]
        head = row["hash"]
    return rows


@pytest.mark.parametrize("evidence_class", sorted(evidence.EVIDENCE))
def test_usable_receipts_keep_evidence_separate_from_order_authorization(tmp_path, evidence_class):
    ledger = prepared(tmp_path, evidence_class)
    before = ledger.read_bytes()
    evidence.append(ledger, event("result", outcome(evidence_class)))
    evidence.append(ledger, event("rejection", {"attempt_id": "attempt-2", "reason": "unavailable fixture"}))
    assert ledger.read_bytes().startswith(before)
    report = evidence.report(evidence.load(ledger))
    assert report["order_authorization"] is False
    assert report["attempts"] == {"result": 1, "rejection": 1}
    assert report["evidence_classes"] == {evidence_class: 1}
    assert report["results"][0]["metrics"]["fills"] == 6
    assert report["results"][0]["metrics"]["round_trips"] == 2


def test_empty_and_unclosed_outputs_are_not_estimated():
    assert evidence.validate_metrics(metrics(True))["status"] == "not-estimable"
    partial = metrics(True)
    partial.update(fills=3, executed_sides=1, days=1, episodes=1)
    assert evidence.validate_metrics(partial)["net_account_pnl_usd"] is None
    partial["net_account_pnl_usd"] = 0
    assert evidence.validate_metrics(partial)["net_account_pnl_usd"] == 0


@pytest.mark.parametrize("key,value", [("fills", True), ("fills", -1), ("executed_sides", 7),
    ("round_trips", 3), ("days", 0), ("episodes", 0), ("net_account_pnl_usd", float("nan")),
    ("max_drawdown_usd", float("inf")), ("max_drawdown_usd", -2)])
def test_metrics_reject_misleading_sample_units_or_invalid_drawdown(key, value):
    bad = metrics()
    bad[key] = value
    with pytest.raises(ValueError):
        evidence.validate_metrics(bad)


def test_known_zero_does_not_replace_unknown_or_empty_costs():
    assert evidence.validate_costs([receipt(amount=0)])["known_trader_cost_usd"] == 0
    assert evidence.validate_costs([receipt(amount=0)])["status"] == "complete"
    unknown = evidence.validate_costs([receipt(amount=None)])
    assert unknown["known_trader_cost_usd"] is None and unknown["status"] == "unknown"
    assert unknown["unknown_components"] == ["pool-fee"]
    assert evidence.validate_costs([])["known_trader_cost_usd"] is None
    partial = evidence.validate_costs([receipt("known"), receipt("unknown", None)])
    assert partial["status"] == "partial" and partial["known_trader_cost_usd"] == 1


def test_embedded_pool_subdivisions_do_not_become_extra_trader_fees():
    costs = [receipt(), receipt("lp-share", 0.8, payer="pool", trader_charge=False, included_in="pool-fee"),
             receipt("protocol-share", 0.2, payer="protocol", trader_charge=False, included_in="pool-fee")]
    assert evidence.validate_costs(costs)["known_trader_cost_usd"] == 1.0
    bad = deepcopy(costs)
    bad[1].update(trader_charge=True, payer="trader")
    with pytest.raises(ValueError, match="subdivision"):
        evidence.validate_costs(bad)
    bad = deepcopy(costs)
    bad[2]["amount_usd"] = 0.4
    with pytest.raises(ValueError, match="exceed"):
        evidence.validate_costs(bad)


@pytest.mark.parametrize("change", [{"included_in": "missing"}, {"included_in": "lp-share"},
    {"size": {"value": 200, "unit": "USD"}}, {"basis": "round-trip"}, {"route": "different"},
    {"valid_until_utc": "2026-10-06T00:00:00Z"}, {"amount_usd": None}])
def test_subdivision_relationships_require_comparable_known_receipts(change):
    child = receipt("lp-share", 0.5, payer="pool", trader_charge=False, included_in="pool-fee")
    child.update(change)
    with pytest.raises(ValueError):
        evidence.validate_costs([receipt(), child])


@pytest.mark.parametrize("change", [{"amount_usd": float("inf")}, {"amount_usd": -1},
    {"size": {"value": 0, "unit": "USD"}}, {"source": ""}, {"payer": "pool"},
    {"valid_until_utc": "2026-09-01T00:00:00Z"}, {"basis": "bps"}, {"source_hash": "raw prompt"}])
def test_bad_cost_receipts_fail_closed(change):
    with pytest.raises(ValueError):
        evidence.validate_costs([receipt(**change)])
    with pytest.raises(ValueError, match="duplicate"):
        evidence.validate_costs([receipt(), receipt()])


def test_history_access_is_recorded_but_cannot_be_called_prospective(tmp_path):
    ledger = prepared(tmp_path, "explored-history")
    rows = evidence.load(ledger)
    rows[-1]["payload"]["first_access_utc"] = "2026-09-15T00:00:00Z"
    assert evidence.validate(rechain(rows))
    rows[0]["payload"]["evidence_class"] = "prospective-paper"
    with pytest.raises(ValueError, match="accessed before"):
        evidence.validate(rechain(rows))


def test_registered_monitoring_access_is_retained_without_rewriting_the_plan(tmp_path):
    ledger = prepared(tmp_path, "registered-final")
    rows = evidence.load(ledger)
    rows[-1]["payload"]["first_access_utc"] = "2026-10-02T12:00:00Z"
    report = evidence.report(rechain(rows))
    assert report["trials"][0]["outcome_access"][0]["first_access_utc"] == "2026-10-02T12:00:00Z"
    assert report["trials"][0]["revision"] == 1
    assert report["order_authorization"] is False


@pytest.mark.parametrize("kind,key,value", [("plan", "utc", "2026-10-02T00:00:00Z"),
    ("freeze", "utc", "2026-10-02T00:00:00Z"), ("access", "utc", "2026-09-30T00:00:00Z"),
    ("access", "utc", "2026-10-04T10:00:00+00:00")])
def test_utc_order_and_prefreeze_constraints(tmp_path, kind, key, value):
    rows = evidence.load(prepared(tmp_path, "prospective-paper"))
    next(row for row in rows if row["kind"] == kind)[key] = value
    with pytest.raises(ValueError):
        evidence.validate(rechain(rows))


def test_revision_is_appended_then_freeze_uses_latest_hash(tmp_path):
    ledger = tmp_path / "revision.jsonl"
    first = evidence.append(ledger, event("plan", plan(), PLAN_TIME))
    revised = plan()
    revised.update(revision=2, hypothesis="New synthetic control")
    second = evidence.append(ledger, event("revision", revised, FREEZE_TIME))
    with pytest.raises(ValueError, match="freeze"):
        evidence.append(ledger, event("freeze", {"plan_hash": first["hash"]}, FREEZE_TIME))
    evidence.append(ledger, event("freeze", {"plan_hash": second["hash"]}, FREEZE_TIME))
    third = dict(revised, revision=3)
    with pytest.raises(ValueError, match="child trial"):
        evidence.append(ledger, event("revision", third, event_id="revision-3"))
    assert len(evidence.load(ledger)) == 3


def test_child_trials_preserve_lineage_and_cannot_reuse_attempt_ids(tmp_path):
    ledger = prepared(tmp_path)
    evidence.append(ledger, event("result", outcome()))
    child = plan("explored-history")
    child["parent_trial_id"] = "trial-1"
    evidence.append(ledger, event("plan", child, event_id="child-plan", trial_id="trial-2"))
    with pytest.raises(ValueError, match="attempt_id"):
        evidence.append(ledger, event("rejection", {"attempt_id": "attempt-1", "reason": "duplicate"}, trial_id="trial-2"))
    assert evidence.load(ledger)[-1]["payload"]["lineage_id"] == "trial-1"
    orphan = plan()
    orphan["parent_trial_id"] = "missing"
    with pytest.raises(ValueError, match="parent"):
        evidence.append(ledger, event("plan", orphan, event_id="orphan", trial_id="orphan"))


def test_required_unknown_fields_evidence_promotion_and_missing_access_are_refused(tmp_path):
    ledger = prepared(tmp_path)
    original = ledger.read_bytes()
    unknown = outcome()
    unknown["raw_prompt"] = "must not be written"
    promoted = outcome("registered-final")
    missing = outcome()
    del missing["costs"]
    for payload in (unknown, promoted, missing):
        with pytest.raises(ValueError):
            evidence.append(ledger, event("result", payload))
        assert ledger.read_bytes() == original
    rows = evidence.load(ledger)[:-1]
    result = dict(event("result", outcome()), schema=1, seq=3, prev_hash=rows[-1]["hash"])
    with pytest.raises(ValueError, match="outcome access"):
        evidence.validate(rechain(rows + [result]))


def test_integrity_corruption_duplicate_json_and_truncation_are_detected(tmp_path):
    ledger = prepared(tmp_path)
    rows = evidence.load(ledger)
    anchor = rows[-1]["hash"]
    changed = deepcopy(rows)
    changed[0]["payload"]["hypothesis"] = "Changed after freeze"
    with pytest.raises(ValueError, match="integrity"):
        evidence.validate(changed)
    with pytest.raises(ValueError, match="external head"):
        evidence.validate(rows[:-1], anchor)
    with pytest.raises(ValueError, match="external head"):
        evidence.validate(rechain(changed), anchor)
    with pytest.raises(ValueError, match="duplicate JSON"):
        evidence.decode('{"amount":1,"amount":2}')
    with pytest.raises(ValueError, match="nonfinite"):
        evidence.decode('{"amount":NaN}')
    ledger.write_bytes(ledger.read_bytes()[:-1])
    with pytest.raises(ValueError, match="incomplete"):
        evidence.load(ledger)


def test_concurrent_appends_preserve_every_attempt_and_chain(tmp_path):
    ledger = prepared(tmp_path)
    def append_rejection(index):
        return evidence.append(ledger, event("rejection", {"attempt_id": f"attempt-{index}", "reason": "synthetic"},
                                             event_id=f"reject-{index}"))
    with ThreadPoolExecutor(max_workers=4) as executor:
        results = list(executor.map(append_rejection, range(8)))
    assert len({r["hash"] for r in results}) == 8
    assert evidence.report(evidence.load(ledger))["attempts"] == {"rejection": 8}


def test_cli_append_validate_report_and_refusal(tmp_path):
    ledger = tmp_path / "cli.jsonl"
    fixture = tmp_path / "plan.json"
    fixture.write_text(json.dumps(event("plan", plan(), PLAN_TIME)))
    command = [sys.executable, str(SCRIPT)]
    appended = subprocess.run(command + ["append", "--ledger", str(ledger), "--event", str(fixture)], capture_output=True, text=True)
    assert appended.returncode == 0, appended.stderr
    anchor = json.loads(appended.stdout)["hash"]
    checked = subprocess.run(command + ["validate", "--ledger", str(ledger), "--expected-head", anchor], capture_output=True, text=True)
    assert checked.returncode == 0 and json.loads(checked.stdout)["valid"] is True
    reported = subprocess.run(command + ["report", "--ledger", str(ledger)], capture_output=True, text=True)
    assert reported.returncode == 0 and json.loads(reported.stdout)["order_authorization"] is False
    refused = subprocess.run(command + ["append", "--ledger", str(ledger), "--event", str(fixture)], capture_output=True, text=True)
    assert refused.returncode == 2 and "duplicate" in refused.stderr


@pytest.mark.parametrize("pnl,dd", [(-1.0,1.0),(0.0,0.0),(None,None),(-20.0,20.0)])
def test_no_completed_trades_preserve_known_account_changes(pnl,dd):
    value=metrics(True)
    value.update(net_account_pnl_usd=pnl,max_drawdown_usd=dd)
    assert evidence.validate_metrics(value)["net_account_pnl_usd"] == pnl

def test_known_trader_paid_component_cannot_be_silently_excluded():
    with pytest.raises(ValueError,match="cannot be omitted"):
        evidence.validate_costs([receipt(),receipt("omitted",10.0,trader_charge=False)])

def test_first_access_cannot_be_restarted_in_another_trial(tmp_path):
    path=prepared(tmp_path,"explored-history")
    child=plan("registered-final")
    child.update(lineage_id="trial-1",parent_trial_id="trial-1")
    child["windows"]["development"]["end_utc"]="2026-10-04T11:00:00Z"
    child["windows"]["outcome"]={"start_utc":"2026-10-05T00:00:00Z","end_utc":"2026-10-06T00:00:00Z"}
    x=evidence.append(path,event("plan",child,"2026-10-04T11:00:00Z","child-plan","child"))
    evidence.append(path,event("freeze",{"plan_hash":x["hash"]},"2026-10-04T12:00:00Z","child-freeze","child"))
    with pytest.raises(ValueError,match="first access cannot reset"):
        evidence.append(path,event("access",{"first_access_utc":"2026-10-06T01:00:00Z","artifact_hash":H,"purpose":"final scoring"},"2026-10-06T01:00:00Z","child-access","child"))

def test_registered_monitoring_does_not_amend_frozen_rule_but_final_waits(tmp_path):
    path=tmp_path/"registered.jsonl"
    x=evidence.append(path,event("plan",plan("registered-final"),PLAN_TIME))
    evidence.append(path,event("freeze",{"plan_hash":x["hash"]},FREEZE_TIME))
    during="2026-10-02T12:00:00Z"
    evidence.append(path,event("access",{"first_access_utc":during,"artifact_hash":H,"purpose":"fixed-rule paper monitoring"},during))
    with pytest.raises(ValueError,match="result before window closed"):
        evidence.append(path,event("result",outcome("registered-final"),during))
    evidence.append(path,event("result",outcome("registered-final"),ACCESS_TIME))
    assert evidence.report(evidence.load(path))["order_authorization"] is False


@pytest.mark.parametrize("key", ["proposer", "model_version", "cost_model", "universe",
                                 "controls", "regimes", "readout_schedule", "feature_availability",
                                 "owner", "economic_mechanism", "decision", "stop_schedule"])
@pytest.mark.parametrize("omission", ["missing", "blank"])
def test_required_plan_metadata_cannot_be_omitted_or_blank(tmp_path, key, omission):
    ledger = prepared(tmp_path)
    original = ledger.read_bytes()
    incomplete = plan()
    incomplete["lineage_id"] = "incomplete-trial"
    if omission == "missing":
        del incomplete[key]
    else:
        incomplete[key] = " \t "
    with pytest.raises(ValueError):
        evidence.append(ledger, event("plan", incomplete, event_id="incomplete-plan", trial_id="incomplete-trial"))
    assert ledger.read_bytes() == original
