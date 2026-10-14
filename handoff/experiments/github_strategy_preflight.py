"""Static funding and execution-evidence preflight for reviewed public grids.

No foreign code is imported, no HTTP is performed, and no strategy returns or
fills are simulated. Saved hourly closes are reference prices only. The source
minimum is an old implementation clamp, never a current venue requirement.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
from datetime import datetime, timezone
from pathlib import Path

LICENSES = {"MIT", "Apache-2.0", "BSD-2-Clause", "BSD-3-Clause", "ISC", "Unlicense", "0BSD"}
ADAPTER = "balanced_base_quote_grid"
MAX_HOURS = 40_000
MAX_BYTES = 32 * 1024 * 1024
EVIDENCE_KINDS = ("quotes", "trades", "order_lifecycle", "paid_fees")
EXCLUDED_PARTS = {"crypto-trading-system", "autotrade", "preregistration"}
LIMITATIONS = [
    "Static starting-allocation arithmetic only; no strategy return or fill simulation.",
    "Pre-fee/pre-correction grid prices use saved closes as reference centers, never executable quotes.",
    "The source minimum is an implementation clamp; current US venue lot/min-notional rules remain unknown.",
    "The source's simulated fee is historical descriptive configuration, never a current cost estimate.",
    "Actual upstream configuration is unknown; this profile describes reviewed code defaults only.",
    "Closes cannot prove limit fills; OHLC cannot prove crossing order, queue priority or fills.",
    "Hash-present evidence files are uninterpreted artifacts; semantics, event ordering, execution and paid fees need review.",
    "No profitable edge, source performance replication or promotion is established.",
]


class PreflightBlocked(ValueError):
    def __init__(self, code, detail):
        super().__init__(detail)
        self.code, self.detail = code, detail


def _sha(data):
    return hashlib.sha256(data).hexdigest()


def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def _utc():
    return datetime.now(timezone.utc).isoformat()


def _pairs(items):
    result = {}
    for key, value in items:
        if key in result:
            raise PreflightBlocked("INVALID_JSON", f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _decode(data):
    try:
        return json.loads(data, object_pairs_hook=_pairs, parse_constant=lambda value: (_ for _ in ()).throw(
            PreflightBlocked("INVALID_JSON", f"nonfinite JSON value: {value}")))
    except PreflightBlocked:
        raise
    except (UnicodeDecodeError, ValueError, RecursionError) as exc:
        raise PreflightBlocked("INVALID_JSON", str(exc)) from exc


def _keys(obj, required, label):
    if not isinstance(obj, dict) or set(obj) != set(required):
        raise PreflightBlocked("INVALID_PROFILE", f"{label} has missing or extra fields")


def _text(value, label, maximum=2000):
    if not isinstance(value, str) or not value.strip() or len(value) > maximum:
        raise PreflightBlocked("INVALID_PROFILE", f"{label} must be bounded nonempty text")
    return value


def _number(value, label, minimum=0, maximum=1e12, positive=False):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise PreflightBlocked("INVALID_PROFILE", f"{label} must be a finite number")
    try:
        number = float(value)
    except (OverflowError, ValueError) as exc:
        raise PreflightBlocked("INVALID_PROFILE", f"{label} must be finite") from exc
    if not math.isfinite(number) or number < minimum or number > maximum or (positive and number <= minimum):
        raise PreflightBlocked("INVALID_PROFILE", f"{label} is outside its finite permitted range")
    return number


def _int(value, label, minimum=0, maximum=100_000_000):
    if type(value) is not int or not minimum <= value <= maximum:
        raise PreflightBlocked("INVALID_PROFILE", f"{label} must be a bounded integer")
    return value


def _hash(value):
    if not isinstance(value, str) or not re.fullmatch(r"[0-9a-f]{64}", value):
        raise PreflightBlocked("INVALID_PROFILE", "expected a full lowercase SHA256")
    return value


def _relative(value):
    _text(value, "artifact path", 500)
    if "\\" in value or value.startswith("/") or any(p in {"", ".", ".."} for p in value.split("/")):
        raise PreflightBlocked("UNSAFE_PATH", "artifact paths must be plain relative paths")
    if any(p.lower() in EXCLUDED_PARTS for p in value.split("/")):
        raise PreflightBlocked("EXCLUDED_PATH", "excluded repository/owner/frozen path is forbidden")
    return value.split("/")


def _safe_path(path):
    path = Path(path).absolute()
    # Lexical exclusion happens before any filesystem inspection.
    if any(p.lower() in EXCLUDED_PARTS for p in path.parts):
        raise PreflightBlocked("EXCLUDED_PATH", "excluded repository/owner/frozen path is forbidden")
    if any(part == ".." for part in path.parts):
        raise PreflightBlocked("UNSAFE_PATH", "parent traversal is forbidden")
    # Inspect ancestors from the root down; never follow an earlier symlink to
    # inspect a descendant (which could point into an excluded repository).
    current = Path(path.anchor)
    for part in path.parts[1:]:
        current /= part
        if current.is_symlink():
            raise PreflightBlocked("UNSAFE_PATH", "symlink files or ancestors are forbidden")
    return path


def _file(root, relative, maximum=MAX_BYTES):
    parts = _relative(relative)
    root = _safe_path(root)
    path = _safe_path(root.joinpath(*parts))
    if not path.is_file():
        raise PreflightBlocked("MISSING_INPUT", f"missing artifact: {relative}")
    if path.stat().st_size > maximum:
        raise PreflightBlocked("INPUT_TOO_LARGE", f"artifact is larger than the bounded limit: {relative}")
    return path


def validate_profile(profile):
    _keys(profile, {"schema_version", "candidate_id", "source", "review", "method", "protocol", "execution_evidence"}, "profile")
    if type(profile["schema_version"]) is not int or profile["schema_version"] != 1:
        raise PreflightBlocked("INVALID_PROFILE", "schema_version must be 1")
    if not isinstance(profile["candidate_id"], str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,99}", profile["candidate_id"]):
        raise PreflightBlocked("INVALID_PROFILE", "candidate_id must be a plain bounded identifier")
    source = profile["source"]
    _keys(source, {"repo_url", "commit", "files", "license_spdx", "license_file", "license_sha256"}, "source")
    if not isinstance(source["repo_url"], str) or not re.fullmatch(r"https://github\.com/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", source["repo_url"]):
        raise PreflightBlocked("INVALID_PROFILE", "repo_url must name a public GitHub repository")
    if "crypto-trading-system" in source["repo_url"].lower().split("/"):
        raise PreflightBlocked("EXCLUDED_PATH", "excluded repository sources are forbidden")
    if not isinstance(source["commit"], str) or not re.fullmatch(r"[0-9a-f]{40}", source["commit"]):
        raise PreflightBlocked("INVALID_PROFILE", "source commit must be a full lowercase 40-character SHA")
    if not isinstance(source["license_spdx"], str) or source["license_spdx"] not in LICENSES:
        raise PreflightBlocked("UNSUPPORTED_LICENSE", "license needs a separate reviewed reuse decision")
    _relative(source["license_file"])
    _hash(source["license_sha256"])
    if not isinstance(source["files"], list) or not 1 <= len(source["files"]) <= 32:
        raise PreflightBlocked("INVALID_PROFILE", "source.files requires 1 to 32 pinned artifacts")
    seen = set()
    for item in source["files"]:
        _keys(item, {"path", "sha256"}, "source file")
        _relative(item["path"])
        _hash(item["sha256"])
        if item["path"] in seen:
            raise PreflightBlocked("INVALID_PROFILE", "duplicate source artifact path")
        seen.add(item["path"])
    review = profile["review"]
    _keys(review, {"reviewer", "transcription_checked", "license_checked", "closed_lane_checked", "mechanism_note"}, "review")
    _text(review["reviewer"], "reviewer", 200)
    _text(review["mechanism_note"], "mechanism_note")
    if any(review[field] is not True for field in ("transcription_checked", "license_checked", "closed_lane_checked")):
        raise PreflightBlocked("REVIEW_REQUIRED", "source transcription, license and closed-lane checks must be explicitly reviewed")
    method = profile["method"]
    _keys(method, {"adapter", "base_symbol", "quote_symbol", "target_base_weight", "minimum_base_units", "buy_step_factor",
                   "sell_step_factor", "cold_base_units", "cold_quote_units", "reserve_base_units", "reserve_quote_units",
                   "source_simulated_fee_bps", "units_interpretation_checked", "source_configuration"}, "method")
    if method["adapter"] != ADAPTER:
        raise PreflightBlocked("UNSUPPORTED_ADAPTER", "only reviewed balanced base/quote static grids are supported")
    for field in ("base_symbol", "quote_symbol"):
        if not isinstance(method[field], str) or not re.fullmatch(r"[A-Z][A-Z0-9]{0,14}", method[field]):
            raise PreflightBlocked("INVALID_PROFILE", f"{field} must be a plain uppercase symbol")
    if method["base_symbol"] == method["quote_symbol"]:
        raise PreflightBlocked("INVALID_PROFILE", "base and quote symbols must differ")
    if _number(method["target_base_weight"], "target_base_weight", maximum=1) != 0.5:
        raise PreflightBlocked("UNSUPPORTED_PROFILE", "balance-center grid arithmetic requires a 50/50 starting allocation")
    _number(method["minimum_base_units"], "minimum_base_units", positive=True)
    for field in ("buy_step_factor", "sell_step_factor"):
        _number(method[field], field, minimum=1, maximum=10, positive=True)
    for field in ("cold_base_units", "cold_quote_units", "reserve_base_units", "reserve_quote_units"):
        _number(method[field], field)
    _number(method["source_simulated_fee_bps"], "source_simulated_fee_bps", maximum=9999)
    if type(method["units_interpretation_checked"]) is not bool:
        raise PreflightBlocked("INVALID_PROFILE", "units_interpretation_checked must be boolean")
    if method["source_configuration"] != "code-defaults-actual-config-unknown":
        raise PreflightBlocked("UNSUPPORTED_PROFILE", "this preflight describes code defaults; actual upstream configuration stays unknown")
    protocol = profile["protocol"]
    _keys(protocol, {"capital_quote_units", "start_hour", "end_hour", "evidence_class", "planned_at"}, "protocol")
    _number(protocol["capital_quote_units"], "capital_quote_units", positive=True)
    start, end = _int(protocol["start_hour"], "start_hour"), _int(protocol["end_hour"], "end_hour")
    if not 0 <= end - start < MAX_HOURS:
        raise PreflightBlocked("INVALID_PROFILE", "window requires 1 to 40000 consecutive hourly closes")
    if protocol["evidence_class"] != "static-preflight":
        raise PreflightBlocked("INVALID_EVIDENCE_CLASS", "only static-preflight evidence is permitted")
    try:
        planned = datetime.fromisoformat(_text(protocol["planned_at"], "planned_at", 100).replace("Z", "+00:00"))
        if planned.tzinfo is None or planned > datetime.now(timezone.utc):
            raise ValueError("planned_at requires a timezone and may not be in the future")
    except ValueError as exc:
        raise PreflightBlocked("INVALID_PROFILE", str(exc)) from exc
    evidence = profile["execution_evidence"]
    _keys(evidence, EVIDENCE_KINDS, "execution_evidence")
    count = 0
    paths = set()
    for kind in EVIDENCE_KINDS:
        if not isinstance(evidence[kind], list) or len(evidence[kind]) > 8:
            raise PreflightBlocked("INVALID_PROFILE", "each evidence kind needs a list of at most eight receipts")
        for item in evidence[kind]:
            _keys(item, {"path", "sha256"}, "execution evidence file")
            _relative(item["path"])
            _hash(item["sha256"])
            if item["path"] in paths:
                raise PreflightBlocked("INVALID_PROFILE", "one artifact cannot stand in for multiple evidence types")
            paths.add(item["path"])
            count += 1
    if count > 32:
        raise PreflightBlocked("INVALID_PROFILE", "execution evidence exceeds 32 artifacts")
    return profile


def static_funding(prices, method, capital_quote_units):
    """Independent hypothetical starting allocations; no evolving portfolio."""
    if method["units_interpretation_checked"] is not True:
        return {"status": "UNINTERPRETED_UNITS", "calculations": None}
    if method["quote_symbol"] != "USD":
        return {"status": "UNINTERPRETED_CACHE_QUOTE_UNITS", "calculations": None}
    if any(method[field] != 0 for field in ("cold_base_units", "cold_quote_units", "reserve_base_units", "reserve_quote_units")):
        return {"status": "UNSUPPORTED_COLD_OR_RESERVE_ACCOUNTING", "calculations": None}
    capital = float(capital_quote_units)
    weight, minimum = float(method["target_base_weight"]), float(method["minimum_base_units"])
    buy_factor, sell_factor = float(method["buy_step_factor"]), float(method["sell_step_factor"])
    rows = []
    for hour, price in sorted(prices.items()):
        cash, base_units = capital * (1 - weight), capital * weight / price
        buy, sell = price / buy_factor, price * sell_factor
        buy_units = max(minimum, (cash - base_units * buy) / (2 * buy))
        sell_units = max(minimum, (base_units * sell - cash) / (2 * sell))
        required_buy_cash = buy_units * buy
        # These are pre-fee/pre-correction static funding bounds, not execution prices.
        minimum_capital_for_sell = minimum * price / weight
        minimum_capital_for_buy = minimum * buy / (1 - weight)
        computed = (cash, base_units, buy, sell, buy_units, sell_units, required_buy_cash,
                    minimum_capital_for_sell, minimum_capital_for_buy)
        if not all(math.isfinite(value) and value >= 0 for value in computed):
            raise PreflightBlocked("NONFINITE_DERIVED_ACCOUNTING", "static funding arithmetic is not finite")
        rows.append({"hour": hour, "reference_close_quote_per_base": price,
                     "starting_cash_quote_units": cash, "starting_base_units": base_units,
                     "pre_fee_pre_correction_buy_level": buy, "pre_fee_pre_correction_sell_level": sell,
                     "source_buy_units_after_minimum_clamp": buy_units, "source_sell_units_after_minimum_clamp": sell_units,
                     "buy_cash_required_before_fees": required_buy_cash,
                     "sell_inventory_sufficient": base_units >= sell_units,
                     "buy_cash_sufficient_before_fees": cash >= required_buy_cash,
                     "minimum_capital_sell_inventory_bound": minimum_capital_for_sell,
                     "minimum_capital_buy_pre_fee_grid_bound": minimum_capital_for_buy})
    first = rows[0]
    insuff_sell = sum(not row["sell_inventory_sufficient"] for row in rows)
    insuff_buy = sum(not row["buy_cash_sufficient_before_fees"] for row in rows)
    return {"status": "STATIC_FUNDING_INSUFFICIENT" if not first["sell_inventory_sufficient"] or not first["buy_cash_sufficient_before_fees"] else "STATIC_FUNDING_FITS_BEFORE_FEES",
            "basis": "Independent fresh 50/50 starting accounts at saved reference closes; no strategy path or executable prices.",
            "capital_quote_units": capital, "source_minimum_base_units": minimum, "first_reference": first,
            "hypothetical_reference_count": len(rows), "references_with_insufficient_sell_inventory": insuff_sell,
            "references_with_insufficient_buy_cash_before_fees": insuff_buy,
            "sell_inventory_minimum_capital_bound_range": [min(r["minimum_capital_sell_inventory_bound"] for r in rows), max(r["minimum_capital_sell_inventory_bound"] for r in rows)],
            "buy_pre_fee_grid_minimum_capital_bound_range": [min(r["minimum_capital_buy_pre_fee_grid_bound"] for r in rows), max(r["minimum_capital_buy_pre_fee_grid_bound"] for r in rows)]}


def _durable(path, value):
    with path.open("x", encoding="utf-8") as handle:
        json.dump(value, handle, sort_keys=True, indent=2, allow_nan=False)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())


def _event(path, value):
    with path.open("a", encoding="utf-8") as handle:
        handle.write(_canonical(value).decode() + "\n")
        handle.flush()
        os.fsync(handle.fileno())


def run_preflight(profile_path, cache_dir, sources_dir, output_dir, evidence_dir=None):
    output = _safe_path(output_dir)
    output.mkdir(parents=True, exist_ok=False)
    provenance = {"schema_version": 1, "started_at": _utc(), "code_sha256": _sha(Path(__file__).read_bytes()),
                  "evidence_class": "static-preflight", "simulation_executed": False, "validated_profitability": False}
    _durable(output / "attempt.json", provenance)
    events = output / "attempt-events.jsonl"
    _event(events, {"phase": "STARTED", **provenance})
    try:
        path = _safe_path(profile_path)
        if not path.is_file() or path.stat().st_size > 1_000_000:
            raise PreflightBlocked("MISSING_OR_OVERSIZED_PROFILE", "profile must be a bounded regular JSON file")
        body = path.read_bytes()
        provenance["profile_sha256"] = _sha(body)
        _event(events, {"phase": "PROFILE_HASHED_BEFORE_VALIDATION", "profile_sha256": provenance["profile_sha256"]})
        profile = validate_profile(_decode(body))
        provenance.update(candidate_id=profile["candidate_id"], source=profile["source"], review=profile["review"],
                          method=profile["method"], protocol=profile["protocol"], method_sha256=_sha(_canonical(profile["method"])),
                          protocol_sha256=_sha(_canonical(profile["protocol"])))
        expected = {row["path"]: row["sha256"] for row in profile["source"]["files"]}
        license_path, license_hash = profile["source"]["license_file"], profile["source"]["license_sha256"]
        if license_path in expected and expected[license_path] != license_hash:
            raise PreflightBlocked("HASH_MISMATCH", "license hash conflicts with source pin")
        expected[license_path] = license_hash
        provenance["source_artifacts"] = []
        for relative, digest in sorted(expected.items()):
            raw = _file(sources_dir, relative, maximum=2 * 1024 * 1024).read_bytes()
            actual = _sha(raw)
            provenance["source_artifacts"].append({"path": relative, "sha256": actual, "bytes": len(raw)})
            if actual != digest:
                raise PreflightBlocked("HASH_MISMATCH", f"source artifact hash mismatch: {relative}")
        method, protocol = profile["method"], profile["protocol"]
        asset_file = f"{method['base_symbol']}.json"
        raw = _file(cache_dir, asset_file).read_bytes()
        provenance["cache_artifact"] = {"path": asset_file, "sha256": _sha(raw), "bytes": len(raw)}
        cache = _decode(raw)
        if not isinstance(cache, dict):
            raise PreflightBlocked("INVALID_CACHE", "expected an epoch-hour [close,volume] mapping")
        start, end = protocol["start_hour"], protocol["end_hour"]
        prices = {}
        for hour, row in cache.items():
            if not isinstance(hour, str) or not re.fullmatch(r"0|[1-9][0-9]{0,8}", hour):
                raise PreflightBlocked("INVALID_CACHE", "cache hour keys must be canonical integers")
            if not isinstance(row, list) or len(row) != 2:
                raise PreflightBlocked("INVALID_CACHE", "cache rows require [close,volume]")
            close = _number(row[0], "cache.close", maximum=1e300, positive=True)
            _number(row[1], "cache.volume", maximum=1e300)
            if start <= int(hour) <= end:
                prices[int(hour)] = close
        missing = [hour for hour in range(start, end + 1) if hour not in prices]
        provenance["selected_coverage"] = {"start_hour": start, "end_hour": end, "expected_hours": end - start + 1,
                                           "present_hours": len(prices), "missing_hours": len(missing), "first_missing_hours": missing[:20],
                                           "chronology": "integer-hour ascending evaluation; unsorted JSON mapping accepted",
                                           "imputation_performed": False}
        if missing:
            raise PreflightBlocked("MISSING_PRICE_COVERAGE", f"{len(missing)} selected hourly closes absent; no imputation")
        provenance["selected_reference_prices_sha256"] = _sha(_canonical(prices))
        evidence = {}
        for kind in EVIDENCE_KINDS:
            artifacts = []
            for item in profile["execution_evidence"][kind]:
                if evidence_dir is None:
                    raise PreflightBlocked("MISSING_EVIDENCE_ROOT", "declared execution receipts require --evidence-dir")
                raw = _file(evidence_dir, item["path"], maximum=2 * 1024 * 1024).read_bytes()
                actual = _sha(raw)
                if actual != item["sha256"]:
                    raise PreflightBlocked("HASH_MISMATCH", f"execution artifact hash mismatch: {item['path']}")
                artifacts.append({"path": item["path"], "sha256": actual, "bytes": len(raw), "nonempty": bool(raw),
                                  "semantics_interpreted": False, "timestamped_coverage_verified": False})
            evidence[kind] = {"artifacts": artifacts, "nonempty_hash_present_count": sum(a["nonempty"] for a in artifacts),
                              "timestamped_coverage_status": "UNKNOWN", "fills_verified": False}
        provenance["execution_artifact_receipts"] = evidence
        _durable(output / "verified-inputs.json", provenance)
        _event(events, {"phase": "INPUTS_VERIFIED_BEFORE_STATIC_ARITHMETIC", "provenance_sha256": _sha(_canonical(provenance))})
        funding = static_funding(prices, method, protocol["capital_quote_units"])
        missing_evidence = [kind for kind in EVIDENCE_KINDS if evidence[kind]["nonempty_hash_present_count"] == 0]
        blockers = []
        if funding["status"] != "STATIC_FUNDING_FITS_BEFORE_FEES":
            blockers.append(funding["status"])
        blockers += [f"NO_NONEMPTY_HASH_PINNED_{kind.upper()}" for kind in missing_evidence]
        result = {"schema_version": 1, "candidate_id": profile["candidate_id"],
                  "status": "NOT_SCREENABLE" if blockers else "EXECUTION_REVIEW_REQUIRED", "screenable": False,
                  "completed_at": _utc(), "evidence_class": "static-preflight", "simulation_executed": False,
                  "validated_profitability": False, "real_fills_verified": False, "source_replication_verified": False,
                  "funding": funding, "blocking_conditions": blockers,
                  "execution_evidence": evidence, "semantic_execution_review_required": True,
                  "protocol_review_required": True, "current_venue_minimum_and_fees": "UNKNOWN",
                  "upstream_actual_configuration": "UNKNOWN", "provenance": provenance, "limitations": LIMITATIONS}
    except PreflightBlocked as exc:
        result = {"schema_version": 1, "status": "BLOCKED", "screenable": False, "error_code": exc.code, "detail": exc.detail,
                  "completed_at": _utc(), "evidence_class": "static-preflight", "simulation_executed": False,
                  "validated_profitability": False, "provenance": provenance, "limitations": LIMITATIONS}
    except Exception as exc:
        result = {"schema_version": 1, "status": "INCOMPLETE", "screenable": False, "error_code": type(exc).__name__, "detail": str(exc),
                  "completed_at": _utc(), "evidence_class": "static-preflight", "simulation_executed": False,
                  "validated_profitability": False, "provenance": provenance, "limitations": LIMITATIONS}
    _durable(output / "result.json", result)
    _event(events, {"phase": "COMPLETED", "status": result["status"], "completed_at": result["completed_at"],
                    "result_sha256": _sha((output / "result.json").read_bytes()), "simulation_executed": False})
    lines = ["# Public strategy static preflight", "", f"Status: **{result['status']}**. Screenable: **false**.", "",
             "No return simulation or fill verification occurred. No profitability is validated.", ""]
    if "funding" in result:
        lines += [f"Funding status: {result['funding']['status']}.", ""]
        if "first_reference" in result["funding"]:
            first = result["funding"]["first_reference"]
            lines += [f"At the first saved reference close, starting base holdings are {first['starting_base_units']:.12g}; "
                      f"the source minimum is {result['funding']['source_minimum_base_units']:.12g} base units.", ""]
        lines += ["Blocking conditions: " + (", ".join(result["blocking_conditions"]) or "No static/input absence blocker; semantic execution and protocol review still required."), ""]
    else:
        lines += [f"{result['error_code']}: {result['detail']}", ""]
    lines += ["Limitations:", ""] + [f"- {item}" for item in LIMITATIONS]
    (output / "REVIEW.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    for flag in ("profile", "cache", "sources-dir", "output"):
        parser.add_argument(f"--{flag}", required=True, type=Path)
    parser.add_argument("--evidence-dir", type=Path)
    args = parser.parse_args(argv)
    try:
        result = run_preflight(args.profile, args.cache, args.sources_dir, args.output, args.evidence_dir)
    except (PreflightBlocked, OSError) as exc:
        parser.exit(2, f"Cannot create a safe durable attempt receipt: {exc}\n")
    print(json.dumps({"status": result["status"], "output": str(args.output), "simulation_executed": False,
                      "validated_profitability": False}))
    return 2 if result["status"] in {"BLOCKED", "INCOMPLETE"} else 0


if __name__ == "__main__":
    raise SystemExit(main())
