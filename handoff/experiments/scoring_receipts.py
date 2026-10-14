"""Prospective execution evidence; never import or change registered scorer code."""
from __future__ import annotations

import datetime as dt
import hashlib
import importlib.metadata
import json
import os
import platform
import re
import stat
import subprocess
import uuid
from pathlib import Path, PurePosixPath

MAX_FILE_BYTES = 512 * 1024 * 1024
MAX_INPUT_FILES = 128
HEX = re.compile(r"[0-9a-f]{64}\Z")
COMMIT = re.compile(r"[0-9a-f]{40,64}\Z")


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def _parts(rel: str) -> tuple[str, ...]:
    p = PurePosixPath(rel)
    if not rel or p.is_absolute() or any(x in (".", "..") for x in rel.split("/")) or "\\" in rel:
        raise ValueError("unsafe relative path")
    return p.parts


def _open_dir(base: Path, parts=()) -> int:
    """Walk only the declared root, with no symlink following, including ancestors."""
    absolute = base.absolute()
    fd = os.open(absolute.anchor, os.O_RDONLY | os.O_DIRECTORY)
    try:
        for part in (*absolute.parts[1:], *parts):
            next_fd = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            os.close(fd)
            fd = next_fd
        return fd
    except Exception:
        os.close(fd)
        raise


def file_record(base: Path, rel: str, *, normalized: bool = False) -> dict:
    """Hash a regular declared file, bounded in size, without reading symlink targets."""
    out = {"path": rel, "status": "unknown"}
    fd = parent = None
    try:
        parts = _parts(rel)
        parent = _open_dir(base, parts[:-1])
        fd = os.open(parts[-1], os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=parent)
        before = os.fstat(fd)
        if not stat.S_ISREG(before.st_mode):
            raise ValueError("not a regular file")
        if before.st_size > MAX_FILE_BYTES:
            raise ValueError("file size limit exceeded")
        raw = hashlib.sha256()
        norm = hashlib.sha256()
        total, tail = 0, b""
        while chunk := os.read(fd, 1024 * 1024):
            total += len(chunk)
            if total > MAX_FILE_BYTES:
                raise ValueError("file size limit exceeded")
            raw.update(chunk)
            if normalized:
                chunk = tail + chunk
                tail = b"\r" if chunk.endswith(b"\r") else b""
                norm.update((chunk[:-1] if tail else chunk).replace(b"\r\n", b"\n"))
        if normalized:
            norm.update(tail)
        after = os.fstat(fd)
        if (before.st_size, before.st_mtime_ns, before.st_ctime_ns) != (after.st_size, after.st_mtime_ns, after.st_ctime_ns):
            raise ValueError("file changed while hashing")
        out.update(status="hashed", sha256=raw.hexdigest(), bytes=total, mtime_ns=after.st_mtime_ns)
        if normalized:
            out["crlf_normalized_sha256"] = norm.hexdigest()
    except FileNotFoundError:
        out.update(status="missing", reason="declared file absent")
    except (OSError, ValueError) as exc:
        out["reason"] = f"{type(exc).__name__}: {exc}"
    finally:
        if fd is not None:
            os.close(fd)
        if parent is not None:
            os.close(parent)
    return out


def _read_small(base: Path, rel: str) -> bytes:
    parts = _parts(rel)
    parent = _open_dir(base, parts[:-1])
    fd = None
    try:
        fd = os.open(parts[-1], os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=parent)
        if not stat.S_ISREG(os.fstat(fd).st_mode):
            raise ValueError("not a regular file")
        out = bytearray()
        while chunk := os.read(fd, 65536):
            out.extend(chunk)
            if len(out) > 1024 * 1024:
                raise ValueError("manifest size limit exceeded")
        return bytes(out)
    finally:
        if fd is not None:
            os.close(fd)
        os.close(parent)


def git_value(root: Path, *args: str) -> dict:
    try:
        p = subprocess.run(["git", *args], cwd=root, capture_output=True, text=True, timeout=30)
        value = p.stdout.strip()
        if p.returncode == 0 and COMMIT.fullmatch(value):
            return {"status": "known", "commit": value}
        return {"status": "unknown", "reason": "git history unavailable or ambiguous"}
    except (OSError, subprocess.TimeoutExpired):
        return {"status": "unknown", "reason": "git history unavailable"}


def dependencies(packages: list[str]) -> dict:
    out = {"python": {"version": platform.python_version(), "implementation": platform.python_implementation()}}
    for package in packages:
        try:
            out[package] = {"status": "known", "version": importlib.metadata.version(package)}
        except importlib.metadata.PackageNotFoundError:
            out[package] = {"status": "unknown", "reason": "distribution metadata unavailable"}
    return out


def verify(root: Path, lock_rel: str, registration: str, commands: list[list[str]]) -> dict:
    """Verify the explicit baseline; never create or re-pin it during execution."""
    out = {"checked_at": utc_now(), "status": "INVALID/PROTOCOL_DRIFT", "issues": [],
           "source_lock": file_record(root, lock_rel), "head": git_value(root, "rev-parse", "HEAD")}
    try:
        lock_bytes = _read_small(root, lock_rel)
        if hashlib.sha256(lock_bytes).hexdigest() != out["source_lock"].get("sha256"):
            raise ValueError("source lock changed while reading")
        lock = json.loads(lock_bytes)
        entry = lock["registrations"][registration]
        if lock["schema_version"] != 1 or lock["identity_scope"] != "prospective-only":
            raise ValueError("unsupported source-lock schema/identity scope")
        if not COMMIT.fullmatch(lock["baseline_commit"]):
            raise ValueError("invalid baseline commit")
        if commands != entry["commands"]:
            out["issues"].append("invocation differs from prospective lock")
        sources = list(dict.fromkeys([*lock["execution_sources"], *entry["sources"]]))
        required = {"handoff/experiments/final_scores.py", "handoff/experiments/scoring_receipts.py", *(c[0] for c in commands)}
        if not required.issubset(sources):
            raise ValueError("source lock omits a named scorer or execution wrapper")
        out["baseline"] = {k: lock[k] for k in ("baseline_commit", "captured_at", "identity_scope")}
        out["historical_registered_source_identity"] = {"status": "unknown", "reason": "prospective hashes do not establish registration-time scorer bytes"}
        out["window"] = entry["window"]
        out["declared_inputs"] = entry["inputs"]
        out["acquisition_provenance"] = entry["acquisition_provenance"]
        out["dependencies"] = dependencies(entry["packages"])
        spec_rel = f"handoff/preregistration/{registration}/SPEC.md"
        out["registration_commit"] = git_value(root, "log", "--diff-filter=A", "--format=%H", "-1", lock["baseline_commit"], "--", spec_rel)
        out["sources"] = []
        for rel in sources:
            expected = lock["source_sha256"][rel]
            if not HEX.fullmatch(expected):
                raise ValueError("invalid source digest")
            rec = file_record(root, rel)
            rec["expected_sha256"] = expected
            out["sources"].append(rec)
            if rec.get("sha256") != expected:
                out["issues"].append(f"source drift or unavailable: {rel}")
        frozen_rel = "handoff/preregistration/FROZEN.sha256"
        frozen = _read_small(root, frozen_rel)
        out["frozen_manifest"] = {"path": frozen_rel, "sha256": hashlib.sha256(frozen).hexdigest(),
                                  "expected_sha256": lock["frozen_manifest_sha256"]}
        if out["frozen_manifest"]["sha256"] != lock["frozen_manifest_sha256"]:
            out["issues"].append("frozen manifest drift")
        out["frozen_files"] = []
        pins = {}
        for line in frozen.decode().splitlines():
            digest, rel = line.split("  ", 1)
            if rel in pins or not HEX.fullmatch(digest):
                raise ValueError("invalid frozen manifest entry")
            pins[rel] = digest
            rec = file_record(root, f"handoff/preregistration/{rel}", normalized=True)
            rec["expected_crlf_normalized_sha256"] = digest
            out["frozen_files"].append(rec)
            if rec.get("crlf_normalized_sha256") != digest:
                out["issues"].append(f"frozen file drift or unavailable: {rel}")
        if f"{registration}/SPEC.md" not in pins:
            out["issues"].append("registration SPEC absent from frozen manifest")
        out["status"] = "PROSPECTIVE_SOURCE_MATCH" if not out["issues"] else "INVALID/PROTOCOL_DRIFT"
    except (OSError, ValueError, KeyError, TypeError, IndexError) as exc:
        out["issues"].append(f"baseline verification unavailable: {type(exc).__name__}: {exc}")
    return out


def inventory(root: Path, cache: Path, declarations: list[dict]) -> dict:
    """Inventory only explicitly declared files or one shallow suffix-limited directory."""
    out = {"captured_at": utc_now(), "files": [], "issues": []}
    for declaration in declarations:
        base = root if declaration["scope"] == "repo" else cache
        rel = declaration["path"]
        label = f"{declaration['scope']}:{rel}"
        if declaration["kind"] == "file":
            rec = file_record(base, rel)
            rec["path"] = label
            out["files"].append(rec)
            continue
        fd = None
        try:
            fd = _open_dir(base, () if rel == "." else _parts(rel))
            names = sorted(n for n in os.listdir(fd) if n.endswith(declaration["suffix"]))
            if not names:
                out["issues"].append({"path": label, "status": "empty", "reason": "declared directory contains no matching input files"})
            if len(names) > MAX_INPUT_FILES:
                raise ValueError("input file-count limit exceeded")
            for name in names:
                path = name if rel == "." else f"{rel}/{name}"
                rec = file_record(base, path)
                rec["path"] = f"{declaration['scope']}:{path}"
                out["files"].append(rec)
        except FileNotFoundError:
            out["issues"].append({"path": label, "status": "missing"})
        except (OSError, ValueError) as exc:
            out["issues"].append({"path": label, "status": "unknown", "reason": f"{type(exc).__name__}: {exc}"})
        finally:
            if fd is not None:
                os.close(fd)
    if not declarations:
        out["status"] = "no_declared_local_inputs"
    else:
        out["status"] = "hashed_declared_files" if not out["issues"] and all(x["status"] == "hashed" for x in out["files"]) else "unknown_or_incomplete"
    return out


def _save(path: Path, value: dict) -> None:
    """Replace this attempt only; no preregistration files or prior evidence touched."""
    payload = json.dumps(value, indent=2, sort_keys=True) + "\n"
    temp = path.with_suffix(".tmp").name
    parent = _open_dir(path.parent)
    created = False
    try:
        fd = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o644, dir_fd=parent)
        created = True
        with os.fdopen(fd, "w") as fh:
            fh.write(payload)
        os.replace(temp, path.name, src_dir_fd=parent, dst_dir_fd=parent)
    finally:
        if created:
            try:
                os.unlink(temp, dir_fd=parent)
            except FileNotFoundError:
                pass
        os.close(parent)


def start_attempt(root: Path, receipt_root: Path, registration: str, name: str, today: dt.date,
                  when: dt.date, commands: list[list[str]], before: dict) -> tuple[Path, dict]:
    parent = _open_dir(receipt_root.parent)
    try:
        try:
            os.mkdir(receipt_root.name, dir_fd=parent)
        except FileExistsError:
            pass
    finally:
        os.close(parent)
    fd = _open_dir(receipt_root)
    os.close(fd)
    path = receipt_root / f"{registration}-{dt.datetime.now(dt.timezone.utc):%Y%m%dT%H%M%S}-{uuid.uuid4().hex}.json"
    value = {"schema_version": 1, "registration": registration, "name": name, "selected_today": today.isoformat(),
             "allowed_from_with_grace": when.isoformat(), "commands": commands, "started_at": utc_now(),
             "status": "RUNNING", "before": before, "runs": [], "official_result": None}
    _save(path, value)
    return path, value


def record_inputs_before(path: Path, value: dict, inputs: dict) -> None:
    value["inputs_before"] = inputs
    _save(path, value)


def record_run(path: Path, value: dict, *, argv: list[str], started: str, ended: str,
               returncode=None, stdout="", stderr="", failure=None) -> None:
    # Partial Coinbase acquisitions report this exact warning even when their fetcher exits zero.
    warnings = [line for line in (stdout + "\n" + stderr).splitlines() if re.search(r": gave up at \d+", line)]
    value["runs"].append({"argv": argv, "started_at": started, "ended_at": ended, "returncode": returncode,
                          "stdout": stdout, "stderr": stderr, "failure": failure, "acquisition_failure_evidence": warnings})
    _save(path, value)


def finish_attempt(path: Path, value: dict, *, after: dict, inputs: dict, status: str, official_result=None) -> None:
    value.update(finished_at=utc_now(), after=after, inputs_after_before_cleanup=inputs, status=status, official_result=official_result)
    _save(path, value)
