"""Evidence gates are tested offline, with fake scorer subprocesses and disposable inputs."""
import datetime as dt
import hashlib
import importlib.util
import json
import subprocess
from pathlib import Path

import pytest

from handoff.experiments import scoring_receipts as receipts

ROOT = Path(__file__).resolve().parents[1]
FINITE_REPORT = "2 weeks, mean +0.00%, 90% CI [+0.00, +0.00]\n"
PRIMARY_OUTPUT = FINITE_REPORT + "SUCCESS\n"
spec = importlib.util.spec_from_file_location("receipt_final_scores", ROOT / "handoff/experiments/final_scores.py")
fs = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fs)


def digest(data):
    return hashlib.sha256(data).hexdigest()


@pytest.fixture
def study(tmp_path, monkeypatch):
    root = tmp_path / "repo"
    pre = root / "handoff/preregistration/example"
    pre.mkdir(parents=True)
    (root / "handoff/scoring").mkdir()
    (root / "handoff/experiments").mkdir()
    frozen = pre / "SPEC.md"
    frozen.write_bytes(b"locked protocol\n")
    manifest = root / "handoff/preregistration/FROZEN.sha256"
    manifest.write_text(f"{digest(frozen.read_bytes())}  example/SPEC.md\n")
    sources = ["handoff/experiments/final_scores.py", "handoff/experiments/scoring_receipts.py",
               "handoff/experiments/primary.py", "handoff/experiments/secondary.py", "handoff/experiments/local_math.py"]
    for rel in sources:
        (root / rel).write_text(f"# source {rel}\n")
    commands = [[sources[2], "{cache}", "--final"], [sources[3], "{cache}", "--no-fetch"]]
    lock = {"schema_version": 1, "identity_scope": "prospective-only", "baseline_commit": "a" * 40,
            "captured_at": "2026-10-13T00:00:00+00:00", "execution_sources": sources[:2],
            "source_sha256": {rel: digest((root / rel).read_bytes()) for rel in sources},
            "frozen_manifest_sha256": digest(manifest.read_bytes()),
            "registrations": {"example": {"commands": commands, "sources": sources[2:],
                "packages": ["package-that-is-deliberately-not-installed"],
                "window": {"start": "2019-01-01", "end": "2019-12-31"},
                "inputs": [{"scope": "cache", "path": ".", "kind": "directory", "suffix": ".csv"}],
                "acquisition_provenance": {"status": "unknown", "reason": "no response manifest"}}}}
    lock_path = root / fs.LOCK_REL
    lock_path.write_text(json.dumps(lock))
    monkeypatch.setattr(fs, "ROOT", root)
    monkeypatch.setattr(fs, "PRE", root / "handoff/preregistration")
    monkeypatch.setattr(fs, "RECEIPTS", root / "handoff/scoring/receipts")
    monkeypatch.setattr(fs, "TESTS", [("Example", "example", "2020-01-01", 0, *commands)])
    monkeypatch.setattr(fs.sys, "argv", ["final_scores.py", "--today", "2020-01-01"])
    monkeypatch.setattr(receipts, "git_value", lambda root, *args: {"status": "known", "commit": "b" * 40})
    return root, pre, lock_path, lock


def fake_runner(monkeypatch, behavior=None):
    calls = []
    caches = []

    def run(argv, **kwargs):
        calls.append(argv)
        cache = Path(argv[2])
        caches.append(cache)
        (cache / "BTC.csv").write_bytes(b"day,close,volume\n2020-01-01,100,200\n")
        if behavior:
            result = behavior(argv, len(calls))
            if result is not None:
                return result
        return subprocess.CompletedProcess(argv, 0, PRIMARY_OUTPUT if len(calls) == 1 else "informative output\n", "")

    monkeypatch.setattr(fs.subprocess, "run", run)
    return calls, caches


def evidence(root):
    paths = list((root / "handoff/scoring/receipts").glob("*.json"))
    assert len(paths) == 1
    return json.loads(paths[0].read_text())


def test_success_preserves_order_output_and_hashes_cache_before_cleanup(study, monkeypatch):
    root, pre, _, _ = study
    original = (pre / "SPEC.md").read_bytes()
    calls, caches = fake_runner(monkeypatch)
    assert fs.main() == 0
    assert [Path(a[1]).name for a in calls] == ["primary.py", "secondary.py"]
    assert all(not p.exists() for p in caches)
    rec = evidence(root)
    assert rec["status"] == "RESULT_RECORDED"
    assert rec["before"]["head"]["commit"] == "b" * 40
    assert rec["before"]["registration_commit"]["commit"] == "b" * 40
    assert rec["before"]["historical_registered_source_identity"]["status"] == "unknown"
    assert rec["before"]["dependencies"]["package-that-is-deliberately-not-installed"]["status"] == "unknown"
    assert rec["inputs_after_before_cleanup"]["files"][0]["sha256"] == digest(b"day,close,volume\n2020-01-01,100,200\n")
    assert rec["runs"][0]["stdout"] == PRIMARY_OUTPUT
    assert (pre / "SPEC.md").read_bytes() == original
    body = (pre / "RESULT-auto-2020-01-01.md").read_text()
    assert "```\n" + PRIMARY_OUTPUT.strip() + "\n```" in body
    assert "Secondary (informative)" in body and "informative output\n```" in body
    assert "`python3 handoff/experiments/primary.py CACHE --final`" in body


@pytest.mark.parametrize("rel", ["handoff/experiments/primary.py", "handoff/experiments/local_math.py",
                                  "handoff/preregistration/example/SPEC.md", "handoff/preregistration/FROZEN.sha256"])
def test_before_drift_blocks_execution_without_repinning(study, monkeypatch, rel):
    root, pre, lock_path, _ = study
    original_lock = lock_path.read_bytes()
    with (root / rel).open("ab") as f:
        f.write(b"unexpected change\n")
    calls, _ = fake_runner(monkeypatch)
    assert fs.main() == 1
    assert calls == []
    assert not list(pre.glob("RESULT*"))
    assert evidence(root)["status"] == "INVALID/PROTOCOL_DRIFT"
    assert lock_path.read_bytes() == original_lock


def test_missing_lock_is_unknown_and_blocks_execution(study, monkeypatch):
    root, pre, lock_path, _ = study
    lock_path.unlink()
    calls, _ = fake_runner(monkeypatch)
    assert fs.main() == 1
    assert calls == [] and not list(pre.glob("RESULT*"))
    assert evidence(root)["before"]["source_lock"]["status"] == "missing"


@pytest.mark.parametrize("failed_run", [1, 2])
def test_failed_primary_or_secondary_retains_outputs_and_can_retry(study, monkeypatch, failed_run):
    root, pre, _, _ = study

    def fail(argv, n):
        if n == failed_run:
            return subprocess.CompletedProcess(argv, 2, "partial output\n", "network failure\n")

    calls, _ = fake_runner(monkeypatch, fail)
    assert fs.main() == 1
    assert len(calls) == 2
    assert not list(pre.glob("RESULT*"))
    rec = evidence(root)
    assert rec["status"] == "FAILED_EXECUTION"
    assert rec["runs"][failed_run - 1]["stderr"] == "network failure\n"
    assert fs.due(dt.date(2020, 1, 2))[0][3] is False
    fake_runner(monkeypatch)
    assert fs.main() == 0
    attempts = list((root / "handoff/scoring/receipts").glob("*.json"))
    assert len(attempts) == 2  # retry preserves the failed attempt
    assert {json.loads(p.read_text())["status"] for p in attempts} == {"FAILED_EXECUTION", "RESULT_RECORDED"}


def test_timeout_keeps_partial_evidence_and_cache(study, monkeypatch):
    root, pre, _, _ = study

    def timeout(argv, n):
        if n == 1:
            raise subprocess.TimeoutExpired(argv, 3000, output=b"partial HTTP output\n", stderr=b"timed out\n")

    fake_runner(monkeypatch, timeout)
    assert fs.main() == 1 and not list(pre.glob("RESULT*"))
    rec = evidence(root)
    assert rec["runs"][0]["failure"] == "TIMEOUT"
    assert rec["runs"][0]["stdout"] == "partial HTTP output\n"
    assert rec["inputs_after_before_cleanup"]["files"][0]["status"] == "hashed"


def test_inputs_before_are_durable_when_subprocess_starts(study, monkeypatch):
    root, _, _, _ = study

    def observe(argv, n):
        rec = evidence(root)
        assert "inputs_before" in rec
        assert rec["status"] == "RUNNING"

    fake_runner(monkeypatch, observe)
    assert fs.main() == 0


def test_launch_error_retains_attempt_and_retries(study, monkeypatch):
    root, pre, _, _ = study

    def fail(argv, n):
        if n == 1:
            raise OSError("synthetic launch error")

    fake_runner(monkeypatch, fail)
    assert fs.main() == 1 and not list(pre.glob("RESULT*"))
    assert evidence(root)["runs"][0]["failure"] == "EXECUTION_ERROR"


def test_unhashable_declared_input_prevents_official_result(study, monkeypatch):
    root, pre, _, _ = study
    outside = root / "outside.csv"
    outside.write_text("fixture only")

    def symlink(argv, n):
        if n == 2:
            (Path(argv[2]) / "link.csv").symlink_to(outside)

    fake_runner(monkeypatch, symlink)
    assert fs.main() == 1 and not list(pre.glob("RESULT*"))
    assert evidence(root)["status"] == "INVALID/INPUT_PROVENANCE"


def test_empty_required_cache_cannot_be_recorded_even_when_scorers_exit_zero(study, monkeypatch):
    root, pre, _, _ = study
    calls = []

    def empty_cache(argv, **kwargs):
        calls.append(argv)
        return subprocess.CompletedProcess(argv, 0, "SUCCESS\n", "")

    monkeypatch.setattr(fs.subprocess, "run", empty_cache)
    assert fs.main() == 1
    assert len(calls) == 2 and not list(pre.glob("RESULT*"))
    assert fs.due(dt.date(2020, 1, 2))[0][3] is False
    rec = evidence(root)
    assert rec["before"]["status"] == "PROSPECTIVE_SOURCE_MATCH"
    assert rec["status"] == "INVALID/INPUT_PROVENANCE"
    assert all(run["returncode"] == 0 and run["stdout"] == "SUCCESS\n" for run in rec["runs"])
    assert rec["inputs_after_before_cleanup"]["status"] == "unknown_or_incomplete"
    assert rec["inputs_after_before_cleanup"]["files"] == []
    assert rec["inputs_after_before_cleanup"]["issues"][0]["status"] == "empty"
    assert all(not Path(call[2]).exists() for call in calls)


def test_deliberate_no_local_inputs_keeps_acquisition_provenance_unknown(study, monkeypatch):
    root, pre, lock_path, lock = study
    lock["registrations"]["example"]["inputs"] = []
    lock_path.write_text(json.dumps(lock))
    fake_runner(monkeypatch)
    assert fs.main() == 0 and list(pre.glob("RESULT*"))
    rec = evidence(root)
    assert rec["inputs_after_before_cleanup"]["status"] == "no_declared_local_inputs"
    assert rec["inputs_after_before_cleanup"]["files"] == []
    assert rec["before"]["acquisition_provenance"]["status"] == "unknown"


def test_zero_exit_partial_acquisition_warning_is_not_scored(study, monkeypatch):
    root, pre, _, _ = study
    fake_runner(monkeypatch, lambda argv, n: subprocess.CompletedProcess(argv, 0, "BTC: gave up at 12345\nSUCCESS\n", "") if n == 1 else None)
    assert fs.main() == 1 and not list(pre.glob("RESULT*"))
    assert evidence(root)["runs"][0]["acquisition_failure_evidence"] == ["BTC: gave up at 12345"]


def test_post_execution_source_drift_blocks_result(study, monkeypatch):
    root, pre, _, _ = study

    def drift(argv, n):
        if n == 2:
            (root / "handoff/experiments/local_math.py").write_text("changed during execution")

    fake_runner(monkeypatch, drift)
    assert fs.main() == 1 and not list(pre.glob("RESULT*"))
    assert evidence(root)["status"] == "INVALID/PROTOCOL_DRIFT"


def test_repin_during_execution_is_still_drift(study, monkeypatch):
    root, pre, lock_path, lock = study

    def repin(argv, n):
        if n == 2:
            rel = "handoff/experiments/local_math.py"
            (root / rel).write_text("replacement implementation")
            lock["source_sha256"][rel] = digest((root / rel).read_bytes())
            lock_path.write_text(json.dumps(lock))

    fake_runner(monkeypatch, repin)
    assert fs.main() == 1 and not list(pre.glob("RESULT*"))
    assert "prospective source lock changed during execution" in evidence(root)["after"]["issues"]


@pytest.mark.parametrize("mode", ["--dry", "not_due", "already_scored"])
def test_skips_write_no_official_files_or_receipts(study, monkeypatch, mode):
    root, pre, _, _ = study
    if mode == "--dry":
        fs.sys.argv.append("--dry")
    elif mode == "not_due":
        fs.sys.argv[-1] = "2019-12-31"
    else:
        (pre / "RESULT-owner.md").write_text("existing owner result")
    before = {p.relative_to(root): p.read_bytes() for p in root.rglob("*") if p.is_file()}
    calls, _ = fake_runner(monkeypatch)
    assert fs.main() == 0 and calls == []
    assert not (root / "handoff/scoring/receipts").exists()
    assert {p.relative_to(root): p.read_bytes() for p in root.rglob("*") if p.is_file()} == before


def test_inventory_never_reads_symlink_targets_and_is_bounded(tmp_path, monkeypatch):
    scope = tmp_path / "scope"
    scope.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "private.csv").write_text("must not read")
    (scope / "link.csv").symlink_to(outside / "private.csv")
    rec = receipts.inventory(scope, scope, [{"scope": "repo", "path": ".", "kind": "directory", "suffix": ".csv"}])
    assert rec["files"][0]["status"] == "unknown"
    assert "sha256" not in rec["files"][0]
    (scope / "dir").symlink_to(outside, target_is_directory=True)
    assert receipts.file_record(scope, "dir/private.csv")["status"] == "unknown"
    monkeypatch.setattr(receipts, "MAX_FILE_BYTES", 1)
    (scope / "big.csv").write_text("too big")
    assert receipts.file_record(scope, "big.csv")["status"] == "unknown"
    assert receipts.file_record(scope, "../outside/private.csv")["status"] == "unknown"
    monkeypatch.setattr(receipts, "MAX_INPUT_FILES", 1)
    rec = receipts.inventory(scope, scope, [{"scope": "repo", "path": ".", "kind": "directory", "suffix": ".csv"}])
    assert rec["files"] == []
    assert rec["issues"][0]["status"] == "unknown"


def test_declared_directory_requires_matching_files_without_recursing(tmp_path):
    (tmp_path / "unrelated.txt").write_text("fixture only")
    (tmp_path / "nested").mkdir()
    (tmp_path / "nested/hidden.csv").write_text("not a declared shallow input")
    rec = receipts.inventory(tmp_path, tmp_path, [{"scope": "repo", "path": ".", "kind": "directory", "suffix": ".csv"}])
    assert rec["status"] == "unknown_or_incomplete" and rec["files"] == []
    assert rec["issues"][0]["status"] == "empty"
    assert receipts.inventory(tmp_path, tmp_path, [])["status"] == "no_declared_local_inputs"


def test_frozen_normalization_records_raw_bytes(study):
    root, pre, _, lock = study
    (pre / "SPEC.md").write_bytes(b"locked protocol\r\n")
    rec = receipts.verify(root, fs.LOCK_REL, "example", lock["registrations"]["example"]["commands"])
    assert rec["status"] == "PROSPECTIVE_SOURCE_MATCH"
    file = rec["frozen_files"][0]
    assert file["sha256"] == digest(b"locked protocol\r\n")
    assert file["crlf_normalized_sha256"] == digest(b"locked protocol\n")


def test_checked_in_lock_covers_real_scorers_without_executing(monkeypatch):
    monkeypatch.setattr(receipts, "git_value", lambda root, *args: {"status": "known", "commit": "b" * 40})
    for name, registration, first, grace, cmd, *extra in fs.TESTS:
        check = receipts.verify(ROOT, fs.LOCK_REL, registration, [cmd, *extra])
        assert check["status"] == "PROSPECTIVE_SOURCE_MATCH", check["issues"]
        assert check["historical_registered_source_identity"]["status"] == "unknown"


@pytest.mark.parametrize("payload", [b"", b"day,close,volume\n", b"\n timestamp,close,volume\n\n", b"close,volume\n", b"garbage\n", b"2020-01-01,nan,2\n"])
def test_required_empty_header_only_or_unsupported_csv_blocks_result(study, monkeypatch, payload):
    root, pre, _, _ = study
    def missing_records(argv, **kwargs):
        (Path(argv[2]) / "BTC.csv").write_bytes(payload)
        return subprocess.CompletedProcess(argv, 0, "SUCCESS\n", "")
    monkeypatch.setattr(fs.subprocess, "run", missing_records)
    assert fs.main() == 1 and not list(pre.glob("RESULT*"))
    record = evidence(root)
    assert record["status"] == "INVALID/INPUT_PROVENANCE"
    assert record["inputs_after_before_cleanup"]["files"][0]["content"]["status"] == "incomplete"
    assert fs.due(dt.date(2020, 1, 2))[0][3] is False


@pytest.mark.parametrize("text", ["2026-10-12..2027-10-11: 0 weeks\n", "1 complete week: nothing to score yet\n", "0 trades\nSUCCESS\n", "4 daily excess returns: too few for a CI\n", "NOT-ESTIMABLE\n", "INCONCLUSIVE\n", "", "mean +100% without a final disposition\n"])
def test_zero_exit_unestimable_or_unsupported_output_is_incomplete(study, monkeypatch, text):
    root, pre, _, _ = study
    fake_runner(monkeypatch, lambda argv, n: subprocess.CompletedProcess(argv, 0, text, "") if n == 1 else None)
    assert fs.main() == 1 and not list(pre.glob("RESULT*"))
    record = evidence(root)
    assert record["status"] == "INCOMPLETE/SCORER_OUTPUT"
    assert record["output_disposition"]["status"] == "INCOMPLETE"
    assert record["runs"][0]["stdout"] == text
    assert fs.due(dt.date(2020, 1, 2))[0][3] is False


def test_empty_informative_secondary_is_incomplete_and_preserved(study, monkeypatch):
    root, pre, _, _ = study
    fake_runner(monkeypatch, lambda argv, n: subprocess.CompletedProcess(argv, 0, "", "") if n == 2 else None)
    assert fs.main() == 1 and not list(pre.glob("RESULT*"))
    record = evidence(root)
    assert record["status"] == "INCOMPLETE/SCORER_OUTPUT"
    assert record["runs"][1]["stdout"] == ""


@pytest.mark.parametrize("marker", ["SUCCESS", "FAIL"])
def test_reported_final_success_and_failure_are_both_complete(study, monkeypatch, marker):
    root, pre, _, _ = study
    fake_runner(monkeypatch, lambda argv, n: subprocess.CompletedProcess(argv, 0, FINITE_REPORT + marker + "\n", "") if n == 1 else None)
    assert fs.main() == 0 and list(pre.glob("RESULT*"))
    record = evidence(root)
    assert record["status"] == "RESULT_RECORDED"
    assert record["output_disposition"]["status"] == "REPORTED_FINAL_DISPOSITION"
    assert record["output_disposition"]["profitability"] == "not_inferred"
    assert record["result_publication"]["durability"] == "file_and_directory_synced"


@pytest.mark.parametrize("marker", ["CONFIRMED", "NOT CONFIRMED"])
def test_pumpflow_report_contract_preserves_existing_disposition(marker):
    runs = [{"stdout": "3 trades 2026-10-10..2026-10-14 (long 0%)\nmean net per trade +0.000%  90% CI [+0.000%, +0.000%]  total +0.0%\ntiming part +0.000%  90% CI [+0.000%, +0.000%]   buy-and-hold +0.000%/trade\n" + marker + "\n", "stderr": ""}]
    assert receipts.output_disposition("pumpflow", runs)["status"] == "REPORTED_FINAL_DISPOSITION"


def test_us_patterns_contract_requires_both_fixed_rule_dispositions():
    good = "CAPIT Z=4 H=24: 2 trades on 1 days, mean +0.00%/trade after 0.62%/side, 90% CI [-1.00, +1.00]  FAIL\nVOLSPIKE K=10 H=72: 3 trades on 2 days, mean +0.00%/trade after 0.62%/side, 90% CI [-1.00, +1.00]  SUCCESS\n"
    assert receipts.output_disposition("us-patterns", [{"stdout": good, "stderr": ""}])["status"] == "REPORTED_FINAL_DISPOSITION"
    incomplete = good.splitlines()[0] + "\nVOLSPIKE K=10 H=72: 0 trades in 2026..2027\n"
    assert receipts.output_disposition("us-patterns", [{"stdout": incomplete, "stderr": ""}])["status"] == "INCOMPLETE"
    assert receipts.output_disposition("us-patterns", [{"stdout": good.splitlines()[0], "stderr": ""}])["status"] == "INCOMPLETE"


def test_ambiguous_multiple_primary_final_tokens_are_not_published():
    result = receipts.output_disposition("example", [{"stdout": "SUCCESS\nFAIL\n", "stderr": ""}])
    assert result["status"] == "INCOMPLETE"


def test_partial_temporary_payload_write_leaves_no_result_and_retry_works(study, monkeypatch):
    root, pre, _, _ = study
    fake_runner(monkeypatch)
    original = receipts.os.fdopen
    class BrokenPayloadWriter:
        def __init__(self, stream):
            self.stream = stream
        def __enter__(self):
            return self
        def __exit__(self, *args):
            self.stream.close()
        def write(self, payload):
            self.stream.write(payload[:15])
            self.stream.flush()
            raise OSError("injected write failure after a partial temporary payload")
    def partial(fd, mode, *args, **kwargs):
        stream = original(fd, mode, *args, **kwargs)
        return BrokenPayloadWriter(stream) if mode == "wb" else stream
    monkeypatch.setattr(receipts.os, "fdopen", partial)
    assert fs.main() == 1
    record = evidence(root)
    assert record["status"] == "FAILED_RESULT_WRITE"
    assert record["result_publication"]["published"] is False
    assert not list(pre.glob("RESULT*")) and not list(pre.glob(".result-pending-*"))
    assert fs.due(dt.date(2020, 1, 2))[0][3] is False
    monkeypatch.setattr(receipts.os, "fdopen", original)
    fake_runner(monkeypatch)
    assert fs.main() == 0
    assert {json.loads(path.read_text())["status"] for path in (root / "handoff/scoring/receipts").glob("*.json")} == {"FAILED_RESULT_WRITE", "RESULT_RECORDED"}


@pytest.mark.parametrize("failed_step", [1, 2])
def test_fsync_failure_before_publication_leaves_no_recognized_marker(study, monkeypatch, failed_step):
    root, pre, _, _ = study
    fake_runner(monkeypatch)
    original = receipts.os.fsync
    count = 0
    def failed(fd):
        nonlocal count
        count += 1
        if count == failed_step:
            raise OSError("injected pre-publication sync failure")
        return original(fd)
    monkeypatch.setattr(receipts.os, "fsync", failed)
    assert fs.main() == 1 and not list(pre.glob("RESULT*"))
    assert evidence(root)["status"] == "FAILED_RESULT_WRITE"
    assert fs.due(dt.date(2020, 1, 2))[0][3] is False


def test_atomic_link_failure_preserves_failed_attempt_and_allows_retry(study, monkeypatch):
    root, pre, _, _ = study
    fake_runner(monkeypatch)
    original = receipts.os.link
    def blocked(*args, **kwargs):
        raise OSError("injected atomic publication failure")
    monkeypatch.setattr(receipts.os, "link", blocked)
    assert fs.main() == 1 and not list(pre.glob("RESULT*"))
    assert evidence(root)["status"] == "FAILED_RESULT_WRITE"
    monkeypatch.setattr(receipts.os, "link", original)
    fake_runner(monkeypatch)
    assert fs.main() == 0


def test_publication_never_overwrites_an_existing_user_result(tmp_path):
    result = tmp_path / "RESULT-auto-existing.md"
    result.write_text("existing authoritative result\n")
    with pytest.raises(receipts.ResultPublicationError) as failure:
        receipts.publish_result(result, "replacement must not overwrite\n")
    assert failure.value.publication["published"] is False
    assert result.read_text() == "existing authoritative result\n"
    assert not list(tmp_path.glob(".result-pending-*"))


def test_post_publication_directory_sync_error_leaves_complete_file_with_explicit_uncertainty(study, monkeypatch):
    root, pre, _, _ = study
    fake_runner(monkeypatch)
    original = receipts.os.fsync
    count = 0
    def failed(fd):
        nonlocal count
        count += 1
        if count == 3:
            raise OSError("injected directory sync failure after complete publication")
        return original(fd)
    monkeypatch.setattr(receipts.os, "fsync", failed)
    assert fs.main() == 1
    record = evidence(root)
    assert record["status"] == "RESULT_RECORDED_DURABILITY_UNKNOWN"
    assert record["result_publication"]["published"] is True
    assert record["result_publication"]["durability"] == "directory_sync_unknown"
    result = next(pre.glob("RESULT*"))
    assert digest(result.read_bytes()) == record["result_publication"]["sha256"]
    assert "informative output" in result.read_text()


def test_named_required_empty_snapshot_file_has_incomplete_input_status(tmp_path):
    snapshot = tmp_path / "snapshots.jsonl"
    snapshot.write_bytes(b"")
    value = receipts.inventory(tmp_path, tmp_path, [{"scope": "repo", "path": "snapshots.jsonl", "kind": "file"}])
    assert value["status"] == "unknown_or_incomplete"
    assert value["files"][0]["content"]["status"] == "incomplete"


@pytest.mark.parametrize("text", ["2 weeks, mean nan, CI [nan,nan] FAIL\n", "2 weeks, mean inf, CI [inf,inf] SUCCESS\n"])
def test_nonfinite_reported_metrics_are_incomplete_even_with_final_token(study, monkeypatch, text):
    root, pre, _, _ = study
    fake_runner(monkeypatch, lambda argv, n: subprocess.CompletedProcess(argv, 0, text, "") if n == 1 else None)
    assert fs.main() == 1 and not list(pre.glob("RESULT*"))
    assert evidence(root)["status"] == "INCOMPLETE/SCORER_OUTPUT"


def test_unsupported_nontext_output_returns_incomplete_without_exception():
    assert receipts.output_disposition("example", [{"stdout": None, "stderr": ""}])["status"] == "INCOMPLETE"


REPORT_EXAMPLES = {
    "cde-vol-momentum": "2026-10-12..2027-10-11: 52 weeks, mean -0.10%/week after 20 bp/side, 90% CI [-1.00, +1.00]  FAIL\n",
    "vol-momentum": "52 weeks 2026-10-12 .. 2027-10-11: mean -0.10% per week net of costs and funding, 90% CI [-1.00, +1.00], cumulative -2.0% (long-short, $1 per leg)\nRESULT: FAIL (registered: mean > 0 and CI lower bound > 0)\n",
    "xs-momentum": "52 weeks 2026-10-12 .. 2027-10-11: mean -0.10% per week net of costs and funding, 90% CI [-1.00, +1.00], cumulative -2.0% (long-short, $1 per leg)\nRESULT: FAIL (registered: mean > 0 and CI lower bound > 0)\n",
    "hlp-hold": "20 intervals, 180 days: HLP +0.0% a year, minus the 5% hurdle -5.0 points, 90% CI [-6.0, -4.0]\nRESULT: FAIL (registered: excess > 0 and CI lower bound > 0)\n",
    "wick-bounce": "2026-10-12..2027-10-11: 4 trades on 2 days, mean -1.0 bp/trade after 8.5 bp/side, 90% CI [-2.0, +1.0]\nFAIL\n",
    "jlp-hedged": "100 check-ins, 2026-10-10T00:00:00Z .. 2027-01-08T00:00:00Z (90.0 days); rebalances 5, top-ups 0, withdrawals 0\nequity $1,000.00 after exit costs (+0.00%), Kamino USDC +1.00%\nexcess over Kamino USDC: -1.00% APR, 90% CI [-2.00, +1.00] (10-day moving blocks, 90 days)\nRESULT: FAIL (registered: mean > 0, CI lower bound > 0, no liquidation)\n",
    "pumpflow": "3 trades 2026-10-10..2026-10-14 (long 0%)\nmean net per trade +0.000%  90% CI [+0.000%, +0.000%]  total +0.0%\ntiming part +0.000%  90% CI [+0.000%, +0.000%]   buy-and-hold +0.000%/trade\nNOT CONFIRMED\n",
    "us-patterns": "CAPIT Z=4 H=24: 2 trades on 1 days, mean +0.00%/trade after 0.62%/side, 90% CI [-1.00, +1.00]  FAIL\nVOLSPIKE K=10 H=72: 3 trades on 2 days, mean +0.00%/trade after 0.62%/side, 90% CI [-1.00, +1.00]  FAIL\n",
}


@pytest.mark.parametrize("registration", sorted(REPORT_EXAMPLES))
def test_existing_registered_finite_failure_reports_are_complete(registration):
    result = receipts.output_disposition(registration, [{"stdout": REPORT_EXAMPLES[registration], "stderr": ""}])
    assert result["status"] == "REPORTED_FINAL_DISPOSITION", result["issues"]
    assert result["profitability"] == "not_inferred"
    assert result["coverage"] == "not_established_by_output"


@pytest.mark.parametrize("registration", sorted(REPORT_EXAMPLES))
def test_known_registration_banners_without_finite_reports_never_complete(registration):
    banner = "NOT CONFIRMED\n" if registration == "pumpflow" else "RESULT: SUCCESS\n"
    result = receipts.output_disposition(registration, [{"stdout": banner, "stderr": ""}])
    assert result["status"] == "INCOMPLETE"


def test_covered_observation_report_with_no_executed_strategy_trades_can_report_fail():
    text = "52 observations, mean +0.00%, 90% CI [+0.00, +0.00]\n0 executed trades\nFAIL\n"
    assert receipts.output_disposition("example", [{"stdout": text, "stderr": ""}])["status"] == "REPORTED_FINAL_DISPOSITION"


def test_registered_jlp_liquidation_failure_preserves_no_ci_exception():
    text = "3 check-ins, 2026-10-10T00:00:00Z .. 2026-10-10T04:00:00Z (0.2 days); rebalances 0, top-ups 0, withdrawals 0\nequity $750.00 after exit costs (-25.00%), Kamino USDC +0.02%\nRESULT: FAIL (simulated liquidation at 2026-10-10T04:00:00Z)\n"
    result = receipts.output_disposition("jlp-hedged", [{"stdout": text, "stderr": ""}])
    assert result["status"] == "REPORTED_FINAL_DISPOSITION", result["issues"]
    missing_account = text.splitlines()[0] + "\n" + text.splitlines()[2]
    assert receipts.output_disposition("jlp-hedged", [{"stdout": missing_account, "stderr": ""}])["status"] == "INCOMPLETE"


def test_matched_numeric_syntax_with_overflow_is_not_finite_evidence():
    text = "2 observations, mean +1e9999%, 90% CI [+0.00, +1.00]\nSUCCESS\n"
    assert receipts.output_disposition("example", [{"stdout": text, "stderr": ""}])["status"] == "INCOMPLETE"
