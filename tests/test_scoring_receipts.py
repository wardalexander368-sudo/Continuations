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
        return subprocess.CompletedProcess(argv, 0, "SUCCESS\n" if len(calls) == 1 else "informative output\n", "")

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
    assert rec["runs"][0]["stdout"] == "SUCCESS\n"
    assert (pre / "SPEC.md").read_bytes() == original
    body = (pre / "RESULT-auto-2020-01-01.md").read_text()
    assert "```\nSUCCESS\n```" in body
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
