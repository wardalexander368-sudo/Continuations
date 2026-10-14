"""Offline adversarial funding, source, evidence and coverage checks."""
import copy
import hashlib
import json
from pathlib import Path

import pytest

from handoff.experiments import github_strategy_preflight as preflight


def sha(data):
    return hashlib.sha256(data).hexdigest()


@pytest.fixture
def setup(tmp_path):
    root = tmp_path.resolve()
    sources, cache, evidence = root / "sources", root / "cache", root / "evidence"
    for path in (sources, cache, evidence):
        path.mkdir()
    foreign = b"raise RuntimeError('foreign code must never execute')\n"
    license_body = b"MIT license fixture; reviewed attestation only\n"
    (sources / "grid.py").write_bytes(foreign)
    (sources / "LICENSE").write_bytes(license_body)
    (cache / "BTC.json").write_text(json.dumps({str(h): [50000, 1] for h in range(4)}))
    profile = {
        "schema_version": 1, "candidate_id": "source-default-preflight",
        "source": {"repo_url": "https://github.com/example/grid", "commit": "a" * 40,
                   "files": [{"path": "grid.py", "sha256": sha(foreign)}], "license_spdx": "MIT",
                   "license_file": "LICENSE", "license_sha256": sha(license_body)},
        "review": {"reviewer": "offline fixture", "transcription_checked": True, "license_checked": True,
                   "closed_lane_checked": True, "mechanism_note": "Reviewed old source defaults, not current venue rules."},
        "method": {"adapter": preflight.ADAPTER, "base_symbol": "BTC", "quote_symbol": "USD", "target_base_weight": 0.5,
                   "minimum_base_units": 0.1, "buy_step_factor": 1.05, "sell_step_factor": 1.05,
                   "cold_base_units": 0, "cold_quote_units": 0, "reserve_base_units": 0, "reserve_quote_units": 0,
                   "source_simulated_fee_bps": 5, "units_interpretation_checked": True,
                   "source_configuration": "code-defaults-actual-config-unknown"},
        "protocol": {"capital_quote_units": 1000, "start_hour": 0, "end_hour": 3,
                     "evidence_class": "static-preflight", "planned_at": "2024-01-01T00:00:00Z"},
        "execution_evidence": {kind: [] for kind in preflight.EVIDENCE_KINDS},
    }
    profile_path = root / "profile.json"
    profile_path.write_text(json.dumps(profile))
    return root, sources, cache, evidence, profile_path, profile


def run_fixture(setup, profile=None):
    root, sources, cache, evidence, path, original = setup
    path.write_text(json.dumps(original if profile is None else profile))
    return preflight.run_preflight(path, cache, sources, root / "attempt", evidence)


def prices(setup, values):
    (setup[2] / "BTC.json").write_text(json.dumps({str(h): [value, 1] for h, value in enumerate(values)}))


def test_source_minimum_versus_1000_account_has_static_funding_failure(setup):
    result = run_fixture(setup)
    assert result["status"] == "NOT_SCREENABLE"
    assert result["simulation_executed"] is result["validated_profitability"] is result["screenable"] is False
    first = result["funding"]["first_reference"]
    assert first["starting_base_units"] == pytest.approx(0.01)
    assert first["starting_cash_quote_units"] == 500
    assert first["source_sell_units_after_minimum_clamp"] == 0.1
    assert first["source_buy_units_after_minimum_clamp"] == 0.1
    assert first["minimum_capital_sell_inventory_bound"] == 10000
    assert first["minimum_capital_buy_pre_fee_grid_bound"] == pytest.approx(10000 / 1.05)
    assert result["funding"]["references_with_insufficient_sell_inventory"] == 4
    assert "STATIC_FUNDING_INSUFFICIENT" in result["blocking_conditions"]
    assert result["current_venue_minimum_and_fees"] == "UNKNOWN"


@pytest.mark.parametrize("price,expected", [(4999.9999, True), (5000, True), (5000.0001, False)])
def test_exact_source_inventory_funding_boundary(setup, price, expected):
    prices(setup, [price] * 4)
    result = run_fixture(setup)
    first = result["funding"]["first_reference"]
    assert first["sell_inventory_sufficient"] is expected
    assert result["funding"]["status"] == ("STATIC_FUNDING_FITS_BEFORE_FEES" if expected else "STATIC_FUNDING_INSUFFICIENT")
    assert result["status"] == "NOT_SCREENABLE"  # missing execution evidence even if funded


def test_source_simulated_fee_is_descriptive_and_not_charged_as_current_cost(setup):
    prices(setup, [5000] * 4)
    result = run_fixture(setup)
    first = result["funding"]["first_reference"]
    assert first["pre_fee_pre_correction_buy_level"] == pytest.approx(5000 / 1.05)
    assert first["pre_fee_pre_correction_sell_level"] == 5250
    assert first["buy_cash_required_before_fees"] == pytest.approx(0.1 * 5000 / 1.05)
    assert result["provenance"]["method"]["source_simulated_fee_bps"] == 5
    assert result["current_venue_minimum_and_fees"] == "UNKNOWN"


def test_all_four_hash_present_flags_never_verify_fills_or_allow_screening(setup):
    prices(setup, [5000] * 4)
    profile = copy.deepcopy(setup[-1])
    for kind in preflight.EVIDENCE_KINDS:
        payload = b'{"present": true, "verified": true}'
        name = f"{kind}.json"
        (setup[3] / name).write_bytes(payload)
        profile["execution_evidence"][kind] = [{"path": name, "sha256": sha(payload)}]
    result = run_fixture(setup, profile)
    assert result["status"] == "EXECUTION_REVIEW_REQUIRED"
    assert result["screenable"] is result["real_fills_verified"] is result["source_replication_verified"] is False
    assert result["semantic_execution_review_required"] is result["protocol_review_required"] is True
    for kind in preflight.EVIDENCE_KINDS:
        assert result["execution_evidence"][kind]["nonempty_hash_present_count"] == 1
        assert result["execution_evidence"][kind]["timestamped_coverage_status"] == "UNKNOWN"
        assert result["execution_evidence"][kind]["artifacts"][0]["timestamped_coverage_verified"] is False


def test_empty_and_unknown_evidence_are_explicit(setup):
    profile = copy.deepcopy(setup[-1])
    (setup[3] / "empty-quotes.json").write_bytes(b"")
    profile["execution_evidence"]["quotes"] = [{"path": "empty-quotes.json", "sha256": sha(b"")}]
    result = run_fixture(setup, profile)
    quotes = result["execution_evidence"]["quotes"]
    assert quotes["artifacts"][0]["bytes"] == 0
    assert quotes["nonempty_hash_present_count"] == 0
    assert "NO_NONEMPTY_HASH_PINNED_QUOTES" in result["blocking_conditions"]
    assert quotes["timestamped_coverage_status"] == "UNKNOWN"


def test_uninterpreted_units_prevent_funding_arithmetic(setup):
    profile = copy.deepcopy(setup[-1])
    profile["method"]["units_interpretation_checked"] = False
    result = run_fixture(setup, profile)
    assert result["status"] == "NOT_SCREENABLE"
    assert result["funding"] == {"status": "UNINTERPRETED_UNITS", "calculations": None}


def test_non_usd_quote_is_not_assumed_from_usd_cache(setup):
    profile = copy.deepcopy(setup[-1])
    profile["method"]["quote_symbol"] = "USDT"
    result = run_fixture(setup, profile)
    assert result["funding"]["status"] == "UNINTERPRETED_CACHE_QUOTE_UNITS"
    assert result["funding"]["calculations"] is None


def test_cold_and_reserved_funds_are_not_silently_spendable(setup):
    profile = copy.deepcopy(setup[-1])
    profile["method"]["cold_base_units"] = 1
    result = run_fixture(setup, profile)
    assert result["status"] == "NOT_SCREENABLE"
    assert result["funding"]["status"] == "UNSUPPORTED_COLD_OR_RESERVE_ACCOUNTING"


def test_profile_source_code_and_inputs_hashed_before_static_arithmetic(setup, monkeypatch):
    original = preflight.static_funding
    def inspect(*args, **kwargs):
        path = setup[0] / "attempt" / "verified-inputs.json"
        assert path.exists()
        provenance = json.loads(path.read_text())
        assert provenance["simulation_executed"] is False
        assert provenance["code_sha256"] == sha(Path(preflight.__file__).read_bytes())
        assert provenance["cache_artifact"]["sha256"] == sha((setup[2] / "BTC.json").read_bytes())
        assert provenance["source_artifacts"][0]["path"] == "LICENSE"
        return original(*args, **kwargs)
    monkeypatch.setattr(preflight, "static_funding", inspect)
    result = run_fixture(setup)
    assert result["status"] == "NOT_SCREENABLE"
    assert (setup[0] / "attempt" / "REVIEW.md").exists()


def test_unsorted_hour_mapping_is_evaluated_chronologically(setup):
    (setup[2] / "BTC.json").write_text(json.dumps({"3": [4000, 1], "2": [3000, 1], "1": [2000, 1], "0": [1000, 1]}))
    result = run_fixture(setup)
    assert result["funding"]["first_reference"]["hour"] == 0
    assert result["funding"]["first_reference"]["reference_close_quote_per_base"] == 1000
    assert result["provenance"]["selected_coverage"]["present_hours"] == 4


def test_missing_hour_blocks_and_preserves_coverage_receipt(setup):
    (setup[2] / "BTC.json").write_text(json.dumps({str(h): [5000, 1] for h in (0, 1, 3)}))
    result = run_fixture(setup)
    assert result["status"] == "BLOCKED" and result["error_code"] == "MISSING_PRICE_COVERAGE"
    assert result["provenance"]["selected_coverage"]["first_missing_hours"] == [2]
    assert result["provenance"]["selected_coverage"]["imputation_performed"] is False
    assert not (setup[0] / "attempt" / "verified-inputs.json").exists()


@pytest.mark.parametrize("section,field,value,code", [
    ("source", "license_spdx", "GPL-3.0", "UNSUPPORTED_LICENSE"),
    ("source", "commit", "a" * 7, "INVALID_PROFILE"),
    ("source", "license_sha256", "a" * 63, "INVALID_PROFILE"),
    ("method", "minimum_base_units", 0, "INVALID_PROFILE"),
    ("method", "minimum_base_units", True, "INVALID_PROFILE"),
    ("method", "buy_step_factor", 1, "INVALID_PROFILE"),
    ("method", "sell_step_factor", -1, "INVALID_PROFILE"),
    ("method", "source_simulated_fee_bps", -1, "INVALID_PROFILE"),
    ("method", "target_base_weight", 0.6, "UNSUPPORTED_PROFILE"),
    ("method", "base_symbol", "../BTC", "INVALID_PROFILE"),
    ("method", "units_interpretation_checked", "yes", "INVALID_PROFILE"),
    ("method", "source_configuration", "current-live-config", "UNSUPPORTED_PROFILE"),
    ("protocol", "capital_quote_units", -1000, "INVALID_PROFILE"),
    ("protocol", "start_hour", 0.0, "INVALID_PROFILE"),
    ("protocol", "end_hour", 40000, "INVALID_PROFILE"),
    ("protocol", "evidence_class", "untouched-holdout", "INVALID_EVIDENCE_CLASS"),
    ("protocol", "planned_at", "2024-01-01", "INVALID_PROFILE"),
])
def test_invalid_profile_fields_block(setup, section, field, value, code):
    profile = copy.deepcopy(setup[-1])
    profile[section][field] = value
    result = run_fixture(setup, profile)
    assert result["status"] == "BLOCKED" and result["error_code"] == code


@pytest.mark.parametrize("field", ["transcription_checked", "license_checked", "closed_lane_checked"])
def test_missing_source_review_blocks(setup, field):
    profile = copy.deepcopy(setup[-1])
    profile["review"][field] = False
    result = run_fixture(setup, profile)
    assert result["status"] == "BLOCKED" and result["error_code"] == "REVIEW_REQUIRED"


def test_extra_boolean_evidence_flags_are_rejected(setup):
    profile = copy.deepcopy(setup[-1])
    profile["execution_evidence"]["fills_verified"] = True
    result = run_fixture(setup, profile)
    assert result["status"] == "BLOCKED" and result["error_code"] == "INVALID_PROFILE"


def test_duplicate_profile_json_is_rejected_with_durable_failed_receipt(setup):
    setup[4].write_text('{"schema_version":1,"schema_version":1}')
    result = preflight.run_preflight(setup[4], setup[2], setup[1], setup[0] / "attempt")
    assert result["status"] == "BLOCKED" and result["error_code"] == "INVALID_JSON"
    assert result["provenance"]["profile_sha256"] == sha(setup[4].read_bytes())


@pytest.mark.parametrize("value", [float("nan"), float("inf"), -float("inf")])
def test_nonfinite_fields_are_rejected(setup, value):
    profile = copy.deepcopy(setup[-1])
    profile["protocol"]["capital_quote_units"] = value
    result = run_fixture(setup, profile)
    assert result["status"] == "BLOCKED" and result["error_code"] == "INVALID_JSON"


@pytest.mark.parametrize("row", [[0, 1], [-1, 1], [10, -1], [10, True], [10], [float("inf"), 1]])
def test_invalid_cache_price_or_volume_blocks(setup, row):
    (setup[2] / "BTC.json").write_text(json.dumps({str(h): row for h in range(4)}))
    assert run_fixture(setup)["status"] == "BLOCKED"


def test_duplicate_cache_hours_block(setup):
    (setup[2] / "BTC.json").write_text('{"0":[10,1],"0":[20,1]}')
    result = run_fixture(setup)
    assert result["status"] == "BLOCKED" and result["error_code"] == "INVALID_JSON"


def test_source_hash_mismatch_blocks_inert_payload(setup):
    (setup[1] / "grid.py").write_text("raise RuntimeError('changed foreign code')")
    result = run_fixture(setup)
    assert result["status"] == "BLOCKED" and result["error_code"] == "HASH_MISMATCH"


@pytest.mark.parametrize("relative,code", [("../grid.py", "UNSAFE_PATH"), ("/grid.py", "UNSAFE_PATH"),
                                           ("x/../grid.py", "UNSAFE_PATH"), ("x\\grid.py", "UNSAFE_PATH"),
                                           ("autotrade/REPORT.md", "EXCLUDED_PATH"),
                                           ("handoff/preregistration/SPEC.md", "EXCLUDED_PATH"),
                                           ("crypto-trading-system/grid.py", "EXCLUDED_PATH")])
def test_source_traversal_owner_frozen_and_excluded_paths_block(setup, relative, code):
    profile = copy.deepcopy(setup[-1])
    profile["source"]["files"][0]["path"] = relative
    result = run_fixture(setup, profile)
    assert result["status"] == "BLOCKED" and result["error_code"] == code


def test_excluded_path_is_rejected_before_any_metadata_access(monkeypatch):
    calls = []
    monkeypatch.setattr(Path, "is_symlink", lambda self: calls.append(str(self)) or False)
    with pytest.raises(preflight.PreflightBlocked, match="excluded"):
        preflight._safe_path("/Users/alexanderward/Projects/crypto-trading-system/never-open")
    assert calls == []


def test_source_symlink_ancestor_blocks_before_descendant_inspection(setup, monkeypatch):
    link = setup[0] / "link"
    link.symlink_to(setup[1], target_is_directory=True)
    real_check = Path.is_symlink
    inspected = []
    def check(self):
        inspected.append(str(self))
        return real_check(self)
    monkeypatch.setattr(Path, "is_symlink", check)
    with pytest.raises(preflight.PreflightBlocked, match="symlink"):
        preflight._safe_path(link / "grid.py")
    assert str(link) in inspected
    assert str(link / "grid.py") not in inspected


def test_evidence_receipts_need_nonconflicting_types_and_correct_hashes(setup):
    profile = copy.deepcopy(setup[-1])
    body = b"timestamped but uninterpreted event\n"
    (setup[3] / "quotes.txt").write_bytes(body)
    profile["execution_evidence"]["quotes"] = [{"path": "quotes.txt", "sha256": "b" * 64}]
    result = run_fixture(setup, profile)
    assert result["status"] == "BLOCKED" and result["error_code"] == "HASH_MISMATCH"


def test_one_receipt_cannot_be_reused_as_all_evidence_types(setup):
    profile = copy.deepcopy(setup[-1])
    for kind in preflight.EVIDENCE_KINDS:
        profile["execution_evidence"][kind] = [{"path": "same.txt", "sha256": "b" * 64}]
    result = run_fixture(setup, profile)
    assert result["status"] == "BLOCKED" and result["error_code"] == "INVALID_PROFILE"


def test_existing_attempt_is_never_overwritten(setup):
    run_fixture(setup)
    original = (setup[0] / "attempt" / "result.json").read_bytes()
    with pytest.raises(FileExistsError):
        preflight.run_preflight(setup[4], setup[2], setup[1], setup[0] / "attempt")
    assert (setup[0] / "attempt" / "result.json").read_bytes() == original


def test_runtime_error_is_retained_as_incomplete_without_resetting_budget(setup, monkeypatch):
    def fail(*args):
        assert (setup[0] / "attempt" / "verified-inputs.json").exists()
        raise RuntimeError("injected arithmetic infrastructure failure")
    monkeypatch.setattr(preflight, "static_funding", fail)
    result = run_fixture(setup)
    assert result["status"] == "INCOMPLETE" and result["error_code"] == "RuntimeError"
    assert result["simulation_executed"] is False
    assert (setup[0] / "attempt" / "attempt-events.jsonl").exists()
