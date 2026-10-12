#!/usr/bin/env python3
"""Replay existing incomplete candidate evidence; not a new market campaign."""
import argparse
import datetime as dt
import hashlib
import json
from pathlib import Path

from audit_ledger import reconcile
from campaign_controller import Campaign, iso, timestamp


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, help="new directory")
    args = parser.parse_args()
    root = Path(__file__).resolve().parent
    output = root / args.output
    output.mkdir(parents=True, exist_ok=False)
    source = root / "journal/observed_features.jsonl"
    config = json.loads((root / "strategy.json").read_text())
    universe = json.loads((root / "data/2026-10-11_first_observation/universe.json").read_text())
    collection = json.loads((root / "data/2026-10-11_first_observation/collection_summary.json").read_text())
    records = [(number, json.loads(line)) for number, line in enumerate(source.read_text().splitlines(), 1) if line.strip()]
    records.sort(key=lambda item: (timestamp(item[1]["decision_at"]), item[0]))
    c = Campaign(config, universe["started_at"], "existing-incomplete-records-retrospective-audit")
    inputs, decisions = [], []
    for number, record in records:
        event = {"event_id": "observed-feature-line-" + str(number), "kind": "candidate",
                 "at": record["decision_at"], "record": record,
                 "evidence": "journal/observed_features.jsonl:line-" + str(number)}
        inputs.append(event)
        decisions.append(c.process(event))
    for name, rows in (("input_events.jsonl", inputs), ("decision_journal.jsonl", decisions)):
        (output / name).write_text("".join(json.dumps(row, allow_nan=False) + "\n" for row in rows))
    summary = c.summary()
    summary.update({"evidence_type": "Retrospective policy audit of previously saved incomplete real candidate records; no new market observations",
                    "replayed_at_utc": iso(dt.datetime.now(dt.timezone.utc)),
                    "source_sha256": sha(source), "strategy_sha256": sha(root / "strategy.json"),
                    "controller_sha256": sha(root / "campaign_controller.py"),
                    "source_market_capture_started_utc": universe["started_at"],
                    "source_market_capture_completed_utc": collection["completed_at"],
                    "source_market_capture_elapsed_seconds": collection["elapsed_seconds"],
                    "replayed_candidate_endpoint_first_utc": records[0][1]["decision_at"],
                    "replayed_candidate_endpoint_last_utc": records[-1][1]["decision_at"],
                    "rejected_incomplete_candidates": len(records), "evidence_complete_entries": 0,
                    "unfunded_budget_only": True, "funding_conversion_and_cost_recovery_verified": False,
                    "new_forward_campaigns": 0, "calendar_timeout_observed": False,
                    "daily_opportunity_rate_estimate": None,
                    "matched_controls": {"random": "not_run_no_evidence_complete_strategy_opportunity",
                                         "attention": "unavailable_social_evidence_missing",
                                         "momentum": "earlier_separate_challenger_results_retained_not_a_matched_full_campaign"},
                    "matched_net_account_comparison": None,
                    "coverage_note": "Only saved endpoint decisions were replayed. No intervening continuous monitoring, new live capture, funding, cost settlement or complete thirty-day campaign is inferred."})
    (output / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    counterexamples = json.loads((root / "results/campaign_legacy_counterexamples.json").read_text())
    corrected = [{"cost_usd": case["cost_usd"], "corrected_audit": reconcile(case["rows"])}
                 for case in counterexamples["boundary_cases"]]
    dust = reconcile(counterexamples["dust_case"]["rows"])
    fixes = {"evidence_type": "synthetic engineering regression replay, not market observations",
             "source_sha256": sha(root / "results/campaign_legacy_counterexamples.json"),
             "ledger_sha256": sha(root / "audit_ledger.py"), "false_boundary_cases_corrected": corrected,
             "dust_case_corrected": dust, "all_expected_false_successes_rejected":
             all(not row["corrected_audit"]["target_met"] for row in corrected) and not dust["target_met"]}
    (output / "legacy_corrections.json").write_text(json.dumps(fixes, indent=2) + "\n")
    print(json.dumps({"replayed_existing_candidates": len(records), "paper_entries": len(c.entry_times),
                      "new_observations": 0, "conditional_unspent_budget_usd": summary["cash_usd"],
                      "boundary_false_successes_fixed": len(corrected), "remaining_dust_kept_open": bool(dust["open_positions"])}))


if __name__ == "__main__":
    main()
