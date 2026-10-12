#!/usr/bin/env python3
"""Reproduce a chronological, costed mark-path challenger test.

These inputs are aggregator observations. Outputs are explicitly NOT fills,
owner-independence evidence, an all-launch census, or proven account growth.
"""
import argparse
import bisect
import csv
import datetime as dt
import gzip
import hashlib
import io
import json
import math
import pathlib
import random
import statistics
import zipfile
from collections import Counter, defaultdict

from economics import CASES, net_multiple

FIELDS = ("event_id", "sample_id", "mint", "rejectReason", "sampleTs_utc_ms", "rejectTs_utc_ms", "priceUsd", "liquidity", "volume24h", "priceChange5m", "priceChange1h", "priceChange24h", "dexId", "pairAddress")


def iso(ms):
    return dt.datetime.fromtimestamp(ms / 1000, dt.timezone.utc).isoformat()


def milliseconds(value):
    return int(dt.datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp() * 1000)


def valid_number(value, positive=False):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) and (not positive or value > 0)


def capacity_multiple(budget, gross_price_multiple, entry_liquidity, exit_liquidity):
    """Conservative two-sided constant-product depth approximation, not a quote.

    Assumes a balanced USD-valued pool and ordinary fees. Each snapshot-side
    impact is modeled separately; real reserve imbalance, our own reserve
    changes, token extensions and concentrated liquidity are not inferred.
    """
    if min(entry_liquidity, exit_liquidity) <= 0:
        return 0
    entry_impact_retention = 1 / (1 + 2 * budget / entry_liquidity)
    exit_gross_notional = budget * gross_price_multiple
    exit_impact_retention = 1 / (1 + 2 * exit_gross_notional / exit_liquidity)
    return net_multiple(budget, gross_price_multiple * entry_impact_retention * exit_impact_retention, CASES[0])


def source_rows(path):
    if path.suffix == ".zip":
        with zipfile.ZipFile(path) as archive, archive.open("data/rejection_outcomes_corrected_v2.jsonl.gz") as compressed, gzip.GzipFile(fileobj=compressed) as source:
            for line in source:
                yield json.loads(line)
    else:
        with gzip.open(path, "rt") as source:
            for row in csv.DictReader(source):
                for name in ("sampleTs_utc_ms", "rejectTs_utc_ms", "priceUsd", "liquidity", "volume24h", "priceChange5m", "priceChange1h", "priceChange24h"):
                    row[name] = float(row[name]) if row.get(name) not in (None, "") else None
                yield row


def prepare(path, compact_path):
    grouped = defaultdict(list)
    rows = 0
    all_mints = set()
    invalid = Counter()
    source_events = set()
    seen_samples = set()
    write_compact = not compact_path.exists()
    compact_path.parent.mkdir(parents=True, exist_ok=True)
    output = gzip.open(compact_path, "wt", newline="") if write_compact else None
    writer = csv.DictWriter(output, fieldnames=FIELDS) if output else None
    if writer:
        writer.writeheader()
    try:
        for raw in source_rows(path):
            rows += 1
            if writer:
                writer.writerow({name: raw.get(name) for name in FIELDS})
            all_mints.add(raw.get("mint"))
            source_events.add(raw.get("event_id"))
            if raw.get("sample_id") in seen_samples:
                invalid["duplicate_sample_id"] += 1
                continue
            seen_samples.add(raw.get("sample_id"))
            if not all(valid_number(raw.get(name), positive=True) for name in ("sampleTs_utc_ms", "rejectTs_utc_ms", "priceUsd", "liquidity")):
                invalid["missing_or_invalid_time_price_liquidity"] += 1
                continue
            if not raw.get("pairAddress") or not raw.get("dexId"):
                invalid["unidentified_pool"] += 1
                continue
            grouped[raw["event_id"]].append({name: raw.get(name) for name in FIELDS})
    finally:
        if output:
            output.close()
    frozen = {}
    pool_switch_samples = 0
    for event, observations in grouped.items():
        observations.sort(key=lambda row: (row["sampleTs_utc_ms"], row["sample_id"]))
        first = observations[0]
        same = [row for row in observations if (row["dexId"], row["pairAddress"]) == (first["dexId"], first["pairAddress"])]
        pool_switch_samples += len(observations) - len(same)
        frozen[event] = same
    return frozen, {"raw_rows": rows, "source_events": len(source_events), "source_mints": len(all_mints), "events_with_usable_initial_pool": len(frozen), "excluded_samples": dict(invalid), "different_pool_samples_excluded": pool_switch_samples, "compact_file": str(compact_path)}


def candidate(row, previous, config, method):
    rules = config["selection"]
    if row["rejectReason"] not in rules["reject_reasons"] or row["dexId"] not in rules["dexes"]:
        return False
    age = (row["sampleTs_utc_ms"] - row["rejectTs_utc_ms"]) / 60000
    if not rules["minimum_minutes_after_rejection"] <= age <= rules["maximum_minutes_after_rejection"]:
        return False
    if row["liquidity"] < rules["minimum_current_liquidity_usd"]:
        return False
    modeled_loss = 1 - capacity_multiple(rules["position_budget_usd"], 1, row["liquidity"], row["liquidity"])
    if modeled_loss > rules["maximum_modeled_roundtrip_loss_fraction"]:
        return False
    if method == "random_universe":
        return True
    if not valid_number(row.get("priceChange5m")) or not rules["minimum_current_5m_price_change_percent"] <= row["priceChange5m"] <= rules["maximum_current_5m_price_change_percent"]:
        return False
    if method == "plain_momentum":
        return True
    if previous is None or not 0 < row["sampleTs_utc_ms"] - previous["sampleTs_utc_ms"] <= rules["maximum_gap_from_previous_sample_minutes"] * 60000:
        return False
    if not valid_number(previous.get("priceChange5m")) or not rules["minimum_previous_5m_price_change_percent"] <= previous["priceChange5m"] <= rules["maximum_previous_5m_price_change_percent"]:
        return False
    if not valid_number(row.get("priceChange1h")) or row["priceChange1h"] > rules["maximum_hour_price_change_percent"]:
        return False
    if row["liquidity"] / previous["liquidity"] < rules["minimum_liquidity_multiple_vs_previous"]:
        return False
    price_ratio = row["priceUsd"] / previous["priceUsd"]
    return rules["minimum_current_price_multiple_vs_previous"] <= price_ratio <= rules["maximum_current_price_multiple_vs_previous"]


def select_signals(groups, config, method):
    signals = []
    for event, rows in groups.items():
        for index, row in enumerate(rows):
            if candidate(row, rows[index - 1] if index else None, config, method):
                signals.append({"event_id": event, "index": index, "decision_ms": row["sampleTs_utc_ms"], "row": row})
                break
    return sorted(signals, key=lambda signal: (signal["decision_ms"], signal["event_id"]))


def replay(signal, groups, config, decision_override=None):
    rows = groups[signal["event_id"]]
    decision = decision_override if decision_override is not None else signal["decision_ms"]
    policy = config["replay"]
    budget = config["selection"]["position_budget_usd"]
    earliest = decision + policy["entry_latency_seconds"] * 1000
    entry = next((row for row in rows if row["sampleTs_utc_ms"] >= earliest), None)
    result = {"event_id": signal["event_id"], "mint": rows[0]["mint"], "decision_ms": decision, "decision_at": iso(decision), "source_sample_id": signal["row"]["sample_id"], "reject_reason": rows[0]["rejectReason"], "decision_liquidity_usd": signal["row"]["liquidity"], "status": "missing_entry_mark", "net_mark_multiple": None, "zero_recovery_stress_multiple": 1 - CASES[0].allocated_data_usd / budget, "is_executable_fill": False}
    if entry is None or entry["sampleTs_utc_ms"] - decision > policy["maximum_next_entry_sample_wait_minutes"] * 60000:
        return result
    if entry["liquidity"] < config["selection"]["minimum_current_liquidity_usd"] or 1 - capacity_multiple(budget, 1, entry["liquidity"], entry["liquidity"]) > config["selection"]["maximum_modeled_roundtrip_loss_fraction"]:
        result["status"] = "entry_capacity_gate_failed"
        return result
    target = entry["sampleTs_utc_ms"] + policy["hold_minutes"] * 60000
    exit_row, reason = None, None
    for row in rows:
        if row["sampleTs_utc_ms"] <= entry["sampleTs_utc_ms"]:
            continue
        if row["sampleTs_utc_ms"] > target + policy["maximum_exit_sample_delay_minutes"] * 60000:
            break
        multiple = capacity_multiple(budget, row["priceUsd"] / entry["priceUsd"], entry["liquidity"], row["liquidity"])
        if multiple <= policy["ordinary_position_stop_net_multiple"]:
            exit_row, reason = row, "observed_mark_below_stop; no guaranteed stop fill"
            break
        if row["sampleTs_utc_ms"] >= target:
            if row["sampleTs_utc_ms"] - target <= policy["maximum_exit_sample_delay_minutes"] * 60000:
                exit_row, reason = row, "first_observed_mark_after_horizon"
            break
    result.update({"entry_at": iso(entry["sampleTs_utc_ms"]), "entry_ms": entry["sampleTs_utc_ms"], "entry_delay_minutes": (entry["sampleTs_utc_ms"] - decision) / 60000, "entry_price_usd": entry["priceUsd"], "entry_liquidity_usd": entry["liquidity"], "status": "censored_exit", "zero_recovery_stress_multiple": 0})
    if exit_row is not None:
        multiple = capacity_multiple(budget, exit_row["priceUsd"] / entry["priceUsd"], entry["liquidity"], exit_row["liquidity"])
        result.update({"exit_at": iso(exit_row["sampleTs_utc_ms"]), "exit_ms": exit_row["sampleTs_utc_ms"], "exit_price_usd": exit_row["priceUsd"], "exit_liquidity_usd": exit_row["liquidity"], "gross_mark_multiple": exit_row["priceUsd"] / entry["priceUsd"], "net_mark_multiple": multiple, "zero_recovery_stress_multiple": multiple, "status": "observed_mark_exit", "exit_reason": reason})
    return result


def summarize(results):
    completed = [row for row in results if row["net_mark_multiple"] is not None]
    returns = [row["net_mark_multiple"] - 1 for row in completed]
    stress = [row["zero_recovery_stress_multiple"] - 1 for row in results]
    return {"signal_attempts": len(results), "unique_signal_events": len({row["event_id"] for row in results}), "unique_signal_mints": len({row["mint"] for row in results}), "observed_mark_paths": len(completed), "missing_entry_marks": sum(row["status"] == "missing_entry_mark" for row in results), "entry_capacity_gate_failures": sum(row["status"] == "entry_capacity_gate_failed" for row in results), "censored_exits": sum(row["status"] == "censored_exit" for row in results), "observed_only_mean_net_mark_return": statistics.mean(returns) if returns else None, "observed_only_median_net_mark_return": statistics.median(returns) if returns else None, "observed_only_positive_fraction": sum(value > 0 for value in returns) / len(returns) if returns else None, "observed_only_net_mark_2x_fraction": sum(value > 1 for value in returns) / len(returns) if returns else None, "mean_including_explicit_zero_recovery_stress": statistics.mean(stress) if stress else None, "executable_trades": 0}


def matched_random(signals, groups, config):
    # Latest observed records are added only as event-time advances. Future
    # records, eventual exits and returns never determine control eligibility.
    if not signals:
        return [], 0
    observed = sorted(((row["sampleTs_utc_ms"], event, index, row) for event, rows in groups.items() for index, row in enumerate(rows)), key=lambda item: (item[0], item[1], item[2]))
    latest = {}
    cursor = 0
    rng = random.Random(config["replay"]["matched_control_seed"])
    outcomes = []
    unmatched = 0
    for signal in signals:
        time = signal["decision_ms"]
        while cursor < len(observed) and observed[cursor][0] <= time:
            at, event, index, row = observed[cursor]
            latest[event] = (index, row)
            cursor += 1
        target = signal["row"]
        bucket = int(math.log2(target["liquidity"]))
        pool = []
        for event, (index, row) in latest.items():
            if event == signal["event_id"] or row["mint"] == target["mint"]:
                continue
            if time - row["sampleTs_utc_ms"] > config["replay"]["matched_control_max_quote_age_minutes"] * 60000:
                continue
            if row["rejectReason"] != target["rejectReason"] or row["dexId"] != target["dexId"] or int(math.log2(row["liquidity"])) != bucket:
                continue
            if candidate(row, None, config, "random_universe"):
                pool.append({"event_id": event, "index": index, "decision_ms": time, "row": row})
        if not pool:
            unmatched += 1
            continue
        choice = rng.choice(sorted(pool, key=lambda item: item["event_id"]))
        outcome = replay(choice, groups, config, decision_override=time)
        outcome["matched_to_event"] = signal["event_id"]
        outcome["control_pool_count"] = len(pool)
        outcomes.append(outcome)
    return outcomes, unmatched


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", help="Original corrected-release ZIP or compact CSV gzip")
    parser.add_argument("--config", default=str(pathlib.Path(__file__).with_name("revival_config.json")))
    parser.add_argument("--output", default="results/revival_study")
    parser.add_argument("--compact", default="data/red_reject_compact.csv.gz")
    args = parser.parse_args()
    out = pathlib.Path(args.output)
    out.mkdir(parents=True, exist_ok=True)
    config = json.loads(pathlib.Path(args.config).read_text())
    source = pathlib.Path(args.source)
    if source.suffix == ".zip" and hashlib.md5(source.read_bytes()).hexdigest() != config["source_expected_md5"]:
        raise ValueError("original source checksum does not match frozen release")
    groups, quality = prepare(source, pathlib.Path(args.compact))
    print(json.dumps({"source_quality": quality}), flush=True)
    signals = select_signals(groups, config, "revival")
    momentum = select_signals(groups, config, "plain_momentum")
    outcomes = [replay(signal, groups, config) for signal in signals]
    momentum_outcomes = [replay(signal, groups, config) for signal in momentum]
    controls, unmatched = matched_random(signals, groups, config)
    momentum_controls, momentum_unmatched = matched_random(momentum, groups, config)
    summary = {"status": "retrospective chronological mark-path stress test; no executable fills", "config_sha256": hashlib.sha256(pathlib.Path(args.config).read_bytes()).hexdigest(), "source_quality": quality, "source_reference": "https://zenodo.org/records/22967373", "unmatched_revival_signals": unmatched, "unmatched_momentum_signals": momentum_unmatched, "periods": {}}
    for period, start_key, end_key in (("development", "development_start", "development_end"), ("chronological_holdout", "chronological_holdout_start", "chronological_holdout_end")):
        start, end = milliseconds(config[start_key]), milliseconds(config[end_key])
        keep = lambda rows: [row for row in rows if start <= row["decision_ms"] < end]
        summary["periods"][period] = {"revival": summarize(keep(outcomes)), "plain_momentum": summarize(keep(momentum_outcomes)), "matched_random": summarize(keep(controls)), "momentum_matched_random": summarize(keep(momentum_controls)), "calendar_days": (end - start) / 86400000}
    for name, rows in (("revival_paths", outcomes), ("momentum_paths", momentum_outcomes), ("matched_random_paths", controls), ("momentum_matched_random_paths", momentum_controls)):
        (out / (name + ".jsonl")).write_text("".join(json.dumps(row) + "\n" for row in rows))
    summary["limitations"] = config["limitations"] + ["Controls are matched by contemporaneous availability, venue, filter and liquidity bucket, not unobserved narrative or regime", "Observed-only averages have survivorship/censoring bias; zero-recovery figures are explicitly hypothetical stress bounds", "Signals from repeated events/mints are correlated and may compete for the same $50 position slot", "No autonomous account-doubling result can be inferred from per-event mark returns"]
    (out / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps(summary, indent=2), flush=True)


if __name__ == "__main__":
    main()
