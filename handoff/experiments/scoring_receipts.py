"""Prospective execution evidence; never import or change registered scorer code."""
from __future__ import annotations

import csv
import datetime as dt
import hashlib
import importlib.metadata
import io
import json
import math
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


def input_content(base: Path, rel: str, record: dict) -> dict:
    """Require actual records, without asserting complete coverage or parsing returns.

    Declared JSONL and other files must be nonempty. The existing candle CSV
    formats are headerless numeric/ISO-date records, optionally preceded by a
    header whose first field names day/date/time/timestamp/ts/hour. At least one
    nonblank, non-header row is required. This is a content-presence check only.
    """
    if record.get("status") != "hashed":
        return {"status": "unknown", "reason": "file hashing unavailable"}
    if record.get("bytes") == 0:
        return {"status": "incomplete", "reason": "required file is empty"}
    if not rel.lower().endswith(".csv"):
        return {"status": "nonempty", "coverage": "not_established"}
    parent = fd = None
    try:
        parts = _parts(rel)
        parent = _open_dir(base, parts[:-1])
        fd = os.open(parts[-1], os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=parent)
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_size > MAX_FILE_BYTES or info.st_size != record["bytes"] or info.st_mtime_ns != record["mtime_ns"]:
            raise ValueError("input changed or is not a bounded regular file")
        saw_header = False
        with os.fdopen(fd, "rb") as binary:
            fd = None
            with io.TextIOWrapper(binary, encoding="utf-8-sig", newline="") as stream:
                for row in csv.reader(stream):
                    if not row or not any(field.strip() for field in row):
                        continue
                    first = row[0].strip()
                    if first.lower() in {"day", "date", "time", "timestamp", "ts", "hour", "open", "high", "low", "close", "volume"}:
                        saw_header = True
                        continue
                    if len(row) < 2:
                        return {"status": "incomplete", "reason": "CSV has no supported candle record"}
                    try:
                        if not math.isfinite(float(first)):
                            raise ValueError("nonfinite CSV timestamp")
                    except ValueError:
                        try:
                            dt.datetime.fromisoformat(first.replace("Z", "+00:00"))
                        except ValueError:
                            return {"status": "incomplete", "reason": "CSV has no supported date/timestamp record"}
                    try:
                        if not all(math.isfinite(float(field.strip())) for field in row[1:]):
                            raise ValueError("nonfinite candle field")
                    except ValueError:
                        return {"status": "incomplete", "reason": "CSV has no finite numeric candle record"}
                    return {"status": "nonempty_records", "coverage": "not_established"}
        return {"status": "incomplete", "reason": "CSV contains only headers" if saw_header else "CSV contains no records"}
    except (OSError, ValueError, UnicodeError, csv.Error) as exc:
        return {"status": "unknown", "reason": f"{type(exc).__name__}: {exc}"}
    finally:
        if fd is not None:
            os.close(fd)
        if parent is not None:
            os.close(parent)


def output_disposition(registration: str, runs: list[dict]) -> dict:
    """Recognize existing finite reports and final tokens, never recompute verdicts.

    Primary banners alone are insufficient. Each known registration has its
    existing report grammar; explicit missing/unestimable/nonfinite diagnostics
    block publication. A reported FAIL/NOT CONFIRMED remains a completed report.
    Counts are reported observations, not inferred trades or independent samples;
    no new strategy threshold is applied. JLP's explicit liquidation FAIL needs
    its finite account report, not a CI that its scorer deliberately omits.
    """
    out = {"status": "INCOMPLETE", "issues": [], "primary_markers": [],
           "coverage": "not_established_by_output", "profitability": "not_inferred"}
    if not runs:
        out["issues"].append("no scorer runs recorded")
        return out
    unsupported = re.compile(r"\b(?:not[-_ ]estimable|incomplete|inconclusive|nan|inf(?:inity)?)\b|nothing to (?:score|evaluate)|too few", re.I)
    for index, run in enumerate(runs):
        stdout, stderr = run.get("stdout", ""), run.get("stderr", "")
        if not isinstance(stdout, str) or not isinstance(stderr, str):
            out["issues"].append(f"run {index + 1}: unsupported text output")
            continue
        if not (stdout.strip() if index == 0 else (stdout + stderr).strip()):
            out["issues"].append(f"run {index + 1}: no report output")
        for line_number, line in enumerate((stdout + "\n" + stderr).splitlines(), 1):
            if unsupported.search(line) or re.search(r"(?<![\d.])0\s+(?:complete\s+)?weeks?\b", line, re.I):
                out["issues"].append(f"run {index + 1}, line {line_number}: unestimable or nonfinite output")
    primary_stdout = runs[0].get("stdout", "")
    if not isinstance(primary_stdout, str):
        return out
    lines = [(number, line.strip()) for number, line in enumerate(primary_stdout.splitlines(), 1)]
    num = r"([+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?)"
    money = r"([+-]?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d*)?)"
    ci = r"90% CI \[" + num + r",\s*" + num + r"\]"

    def report(pattern, description):
        found = [(n, line, match) for n, line in lines if (match := re.fullmatch(pattern, line))]
        if len(found) != 1:
            out["issues"].append(f"missing or ambiguous {description}")
            return False
        try:
            finite = all(math.isfinite(float(value.replace(",", ""))) for value in found[0][2].groups() if value is not None)
        except (ValueError, OverflowError):
            finite = False
        if not finite:
            out["issues"].append(f"nonfinite {description}")
            return False
        return True

    def marker(pattern, description):
        found = [(n, line) for n, line in lines if re.fullmatch(pattern, line)]
        if len(found) != 1:
            out["issues"].append(f"missing or ambiguous {description}")
            return False
        out["primary_markers"].append({"line": found[0][0], "text": found[0][1]})
        return True

    result_token = r"RESULT:\s*(?:SUCCESS|FAIL)(?:\s+\(.*\))?"
    if registration == "us-patterns":
        out["contract"] = "finite metric report and final token for each fixed CAPIT/VOLSPIKE rule"
        for name in ("CAPIT Z=4 H=24", "VOLSPIKE K=10 H=72"):
            report(re.escape(name) + r": (\d+) trades on (\d+) days, mean " + num + r"%/trade after 0\.62%/side, " + ci + r"\s+(?:SUCCESS|FAIL)", name + " finite metric report")
            marker(re.escape(name) + r":.*\b(?:SUCCESS|FAIL)", name + " final disposition")
    elif registration == "pumpflow":
        out["contract"] = "finite net/timing reports and existing CONFIRMED/NOT CONFIRMED line"
        report(r"(\d+) trades \d{4}-\d{2}-\d{2}\.\.\d{4}-\d{2}-\d{2} \(long (\d+)%\)", "pumpflow observation report")
        report(r"mean net per trade " + num + r"%  90% CI \[" + num + r"%, " + num + r"%\]  total " + num + r"%", "pumpflow net report")
        report(r"timing part " + num + r"%  90% CI \[" + num + r"%, " + num + r"%\]   buy-and-hold " + num + r"%/trade", "pumpflow timing report")
        marker(r"(?:CONFIRMED|NOT CONFIRMED)", "pumpflow final disposition")
    elif registration == "cde-vol-momentum":
        out["contract"] = "existing finite weekly mean/CI report with final token"
        report(r"\d{4}-\d{2}-\d{2}\.\.\d{4}-\d{2}-\d{2}: (\d+) weeks, mean " + num + r"%/week after 20 bp/side, " + ci + r"\s+(?:SUCCESS|FAIL)", "CDE weekly report")
        marker(r".+\s+(?:SUCCESS|FAIL)", "CDE final disposition")
    elif registration in {"vol-momentum", "xs-momentum"}:
        out["contract"] = "existing finite weekly return/CI report and RESULT line"
        report(r"(\d+) weeks \d{4}-\d{2}-\d{2} \.\. \d{4}-\d{2}-\d{2}: mean " + num + r"% per week net of costs and funding, " + ci + r", cumulative " + num + r"% \(long-short, \$1 per leg\)", "weekly momentum report")
        marker(result_token, "momentum final disposition")
    elif registration == "wick-bounce":
        out["contract"] = "existing finite trade/CI report and final token"
        report(r"\d{4}-\d{2}-\d{2}\.\.\d{4}-\d{2}-\d{2}: (\d+) trades on (\d+) days, mean " + num + r" bp/trade after 8\.5 bp/side, " + ci, "wick-bounce report")
        marker(r"(?:SUCCESS|FAIL)", "wick-bounce final disposition")
    elif registration == "hlp-hold":
        out["contract"] = "existing finite HLP/hurdle/CI report and RESULT line"
        report(r"(\d+) intervals, " + num + r" days: HLP " + num + r"% a year, minus the " + num + r"% hurdle " + num + r" points, " + ci, "HLP report")
        marker(result_token, "HLP final disposition")
    elif registration == "jlp-hedged":
        out["contract"] = "finite account report plus excess CI or explicit registered liquidation FAIL"
        report(r"(\d+) check-ins, .+ \(" + num + r" days\); rebalances \d+, top-ups \d+, withdrawals \d+", "JLP observation report")
        report(r"equity \$" + money + r" after exit costs \(" + num + r"%\), Kamino USDC " + num + r"%", "JLP account report")
        liquidation = any(re.fullmatch(r"RESULT: FAIL \(simulated liquidation at .+\)", line) for _, line in lines)
        if not liquidation:
            report(r"excess over Kamino USDC: " + num + r"% APR, " + ci + r" \(10-day moving blocks, (\d+) days\)", "JLP excess report")
        marker(result_token, "JLP final disposition")
    else:
        out["contract"] = "finite count/mean/CI report and separate final token"
        report(r"(\d+) (?:weeks|trades|observations), mean " + num + r"%, " + ci, "generic finite metric report")
        marker(r"(?:RESULT:\s*)?(?:SUCCESS|FAIL)(?:\s+\(.*\))?", "generic final disposition")
    if not out["issues"]:
        out["status"] = "REPORTED_FINAL_DISPOSITION"
    return out


class ResultPublicationError(OSError):
    def __init__(self, error: OSError, publication: dict):
        super().__init__(str(error))
        self.publication = publication


def publish_result(path: Path, body: str) -> dict:
    """Write/fsync an unrecognized temp name, atomically link without overwriting.

    A failure before publication leaves no RESULT marker. A failure to sync the
    directory after publication leaves a complete file, explicitly marked with
    uncertain directory durability; it never leaves a partial official payload.
    Existing result paths and concurrent writers are never replaced or deleted.
    """
    payload = body.encode("utf-8")
    out = {"published": False, "bytes": len(payload), "sha256": hashlib.sha256(payload).hexdigest(), "durability": "not_published"}
    parent = _open_dir(path.parent)
    temp = f".result-pending-{uuid.uuid4().hex}.tmp"
    created = False
    try:
        fd = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o644, dir_fd=parent)
        created = True
        with os.fdopen(fd, "wb") as stream:
            if stream.write(payload) != len(payload):
                raise OSError("short result payload write")
            stream.flush()
            os.fsync(stream.fileno())
        os.fsync(parent)
        os.link(temp, path.name, src_dir_fd=parent, dst_dir_fd=parent, follow_symlinks=False)
        out.update(published=True, durability="directory_sync_pending")
        os.fsync(parent)
        out["durability"] = "file_and_directory_synced"
        return out
    except OSError as exc:
        if out["published"]:
            out["durability"] = "directory_sync_unknown"
        raise ResultPublicationError(exc, out) from exc
    finally:
        if created:
            try:
                os.unlink(temp, dir_fd=parent)
            except FileNotFoundError:
                pass
            except OSError as exc:
                out["temporary_cleanup_error"] = f"{type(exc).__name__}: {exc}"
        os.close(parent)


def inventory(root: Path, cache: Path, declarations: list[dict]) -> dict:
    """Inventory only explicitly declared files or one shallow suffix-limited directory."""
    out = {"captured_at": utc_now(), "files": [], "issues": []}
    for declaration in declarations:
        base = root if declaration["scope"] == "repo" else cache
        rel = declaration["path"]
        label = f"{declaration['scope']}:{rel}"
        if declaration["kind"] == "file":
            rec = file_record(base, rel)
            rec["content"] = input_content(base, rel, rec)
            if rec["content"]["status"] not in {"nonempty", "nonempty_records"}:
                out["issues"].append({"path": label, **rec["content"]})
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
                rec["content"] = input_content(base, path, rec)
                if rec["content"]["status"] not in {"nonempty", "nonempty_records"}:
                    out["issues"].append({"path": f"{declaration['scope']}:{path}", **rec["content"]})
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
