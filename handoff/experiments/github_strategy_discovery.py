#!/usr/bin/env python3
"""Bounded public GitHub intake; downloaded material is untrusted, inert data.

This tool queues pinned revisions for human review. It neither imports downloaded
code nor establishes reuse permission, a tradable edge, novelty, or US eligibility.
Only public unauthenticated HTTPS GETs to api.github.com are implemented.
"""
from __future__ import annotations

import argparse
import base64
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import tempfile
from typing import Callable, Mapping
from urllib.error import HTTPError
from urllib.parse import quote, urlencode, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener
import uuid

API = "https://api.github.com"
SCHEMA = 1
EXCLUDED_REPOSITORIES = frozenset({"wardalexander368-sudo/continuations", "ajw9991/crypto-trading-system", "wardalexander368-sudo/crypto-trading-system"})
MAX_RESPONSE_BYTES = 2 * 1024 * 1024
MAX_FILE_BYTES = 512 * 1024
MAX_RUN_BYTES = 16 * 1024 * 1024
TIMEOUT_SECONDS = 15
SAFE_HEADERS = frozenset({"etag", "last-modified", "content-type", "content-length", "x-github-request-id", "x-ratelimit-limit", "x-ratelimit-remaining", "x-ratelimit-reset", "x-ratelimit-resource", "retry-after"})
PERMISSIVE = frozenset({"MIT", "Apache-2.0", "BSD-2-Clause", "BSD-3-Clause", "ISC", "0BSD", "Unlicense", "CC0-1.0", "Zlib", "BSL-1.0"})
COPYLEFT = frozenset({"GPL-2.0", "GPL-3.0", "AGPL-3.0", "LGPL-2.1", "LGPL-3.0", "MPL-2.0", "EPL-1.0", "EPL-2.0", "OSL-3.0"})
REPO_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,99}/[A-Za-z0-9][A-Za-z0-9_.-]{0,99}\Z")
SHA_RE = re.compile(r"[0-9a-fA-F]{40}\Z")


class IntakeError(ValueError):
    pass


class RateLimit(IntakeError):
    pass


class RequestCap(IntakeError):
    pass


class ByteCap(IntakeError):
    pass


@dataclass(frozen=True)
class Response:
    status: int
    headers: Mapping[str, str]
    body: bytes


Transport = Callable[[str, Mapping[str, str], int, int], Response]


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def public_get(url: str, headers: Mapping[str, str], timeout: int, max_bytes: int) -> Response:
    """Do not inherit auth, proxies, cookies, or redirects from an HTTP session."""
    parsed = urlsplit(url)
    if parsed.scheme != "https" or parsed.netloc != "api.github.com" or parsed.username or parsed.password or parsed.fragment:
        raise IntakeError("only the public GitHub API host is allowed")
    # No auth header can be supplied even when this helper is called directly.
    if set(headers) - {"Accept", "User-Agent", "X-GitHub-Api-Version", "If-None-Match"}:
        raise IntakeError("unsupported request header")
    # Disable environment proxy routing and redirects; never forward credentials.
    from urllib.request import ProxyHandler
    opener = build_opener(ProxyHandler({}), NoRedirect())
    request = Request(url, headers=dict(headers), method="GET")
    try:
        response = opener.open(request, timeout=timeout)
    except HTTPError as error:
        response = error
    with response:
        return Response(response.code, dict(response.headers), response.read(max_bytes + 1))


def utc(now: datetime | None = None) -> datetime:
    value = now or datetime.now(timezone.utc)
    if value.tzinfo is None:
        raise IntakeError("timestamp must have a timezone")
    return value.astimezone(timezone.utc)


def timestamp(now: datetime) -> str:
    return utc(now).isoformat(timespec="seconds").replace("+00:00", "Z")


def parse_time(value: str) -> datetime:
    if not isinstance(value, str):
        raise IntakeError("invalid saved timestamp")
    try:
        return utc(datetime.fromisoformat(value.replace("Z", "+00:00")))
    except (ValueError, TypeError) as error:
        raise IntakeError("invalid saved timestamp") from error


def repo_name(value: str) -> str:
    if not isinstance(value, str) or not REPO_RE.fullmatch(value) or any(part in {".", ".."} for part in value.split("/")):
        raise IntakeError("repository must be owner/repo using simple GitHub names")
    return value.lower()


def commit_sha(value: str) -> str:
    if not isinstance(value, str) or not SHA_RE.fullmatch(value):
        raise IntakeError("a full 40-character commit SHA is required")
    return value.lower()


def relative_source_path(value: str) -> str:
    if not isinstance(value, str) or not value or len(value) > 1024 or value.startswith("/") or "\\" in value or any(ord(char) < 32 or ord(char) == 127 for char in value):
        raise IntakeError("source path must be a bounded relative file path")
    parts = value.split("/")
    if len(parts) > 64 or any(part in {"", ".", "..", ".git"} for part in parts) or any(char in value for char in "%?#"):
        raise IntakeError("source path traversal or URL syntax is forbidden")
    return value


def license_policy(spdx: str | None) -> str:
    if spdx in PERMISSIVE:
        return "permissive_candidate_review"
    base = (spdx or "").removesuffix("-only").removesuffix("-or-later")
    if base in COPYLEFT:
        return "copyleft_review"
    return "unknown_license_review"


def _private_dir(path: Path) -> Path:
    path = Path(os.path.abspath(os.fspath(path)))
    lowered_parts = [part.lower() for part in path.parts]
    if "crypto-trading-system" in lowered_parts or "autotrade" in lowered_parts or any(left == "handoff" and right == "preregistration" for left, right in zip(lowered_parts, lowered_parts[1:])):
        raise IntakeError("excluded project, owner book, or frozen registration cannot be used for intake state")
    for parent in (path, *path.parents):
        if parent.is_symlink():
            raise IntakeError("state directory and ancestors must not be symlinks")
        if parent.exists() and not parent.is_dir():
            raise IntakeError("state path ancestor is not a directory")
    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    path.chmod(0o700)
    return path


def _write_bytes(path: Path, data: bytes) -> None:
    _private_dir(path.parent)
    if path.is_symlink() or (path.exists() and not path.is_file()):
        raise IntakeError("artifact target must be an ordinary file")
    fd, temp_name = tempfile.mkstemp(prefix=".atomic-", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(temp_name, 0o600)
        os.replace(temp_name, path)
    finally:
        if os.path.exists(temp_name):
            os.unlink(temp_name)


def _write_json(path: Path, value: object) -> None:
    _write_bytes(path, (json.dumps(value, indent=2, sort_keys=True, ensure_ascii=True, allow_nan=False) + "\n").encode())


def _json_loads(body: bytes) -> object:
    def unique_keys(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise IntakeError("duplicate JSON key")
            result[key] = value
        return result
    def reject_constant(value):
        raise IntakeError("non-finite JSON constant")
    return json.loads(body, object_pairs_hook=unique_keys, parse_constant=reject_constant)


def _read_json(path: Path) -> object:
    if path.is_symlink() or not path.is_file() or path.stat().st_size > 8 * 1024 * 1024:
        raise IntakeError("saved JSON is missing, linked, or oversized")
    try:
        return _json_loads(path.read_bytes())
    except (UnicodeError, ValueError) as error:
        raise IntakeError("saved JSON is corrupt") from error


@contextmanager
def state_lock(state_dir: Path):
    root = _private_dir(state_dir)
    lock = root / ".lock"
    fd = os.open(lock, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
    try:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error:
            raise IntakeError("another intake process holds the global state lock") from error
        yield root
    finally:
        os.close(fd)


def load_state(root: Path) -> dict:
    path = root / "state.json"
    if not path.exists() and not path.is_symlink():
        return {"schema": SCHEMA, "last_discovery_started_at": None, "queue": {}, "cache": {}}
    state = _read_json(path)
    if not isinstance(state, dict) or set(state) != {"schema", "last_discovery_started_at", "queue", "cache"} or (type(state.get("schema")) is not int or state["schema"] != SCHEMA) or not isinstance(state["queue"], dict) or not isinstance(state["cache"], dict):
        raise IntakeError("unsupported or corrupt intake state")
    if state["last_discovery_started_at"] is not None:
        parse_time(state["last_discovery_started_at"])
    for key, candidate in state["queue"].items():
        if not isinstance(candidate, dict) or key != f"{repo_name(candidate.get('repo'))}@{commit_sha(candidate.get('commit'))}":
            raise IntakeError("corrupt queued revision")
        if candidate["repo"] in EXCLUDED_REPOSITORIES:
            raise IntakeError("excluded repository in saved queue")
        parse_time(candidate.get("first_seen_at"))
        if not isinstance(candidate.get("snapshots"), dict) or candidate.get("intake_status") not in {"PENDING_SOURCE_SNAPSHOTS", "QUEUED_FOR_REVIEW"} or candidate.get("license_policy") not in {"permissive_candidate_review", "copyleft_review", "unknown_license_review"}:
            raise IntakeError("corrupt queued snapshots or review policy")
        _candidate_tree(root, candidate)
        for kind, saved in candidate["snapshots"].items():
            if not isinstance(kind, str) or saved is None and kind not in {"license", "readme"}:
                raise IntakeError("corrupt snapshot key")
            if saved is not None:
                if not isinstance(saved, dict) or saved.get("pinned_commit") != candidate["commit"] or not re.fullmatch(r"[0-9a-f]{64}", str(saved.get("sha256"))) or not isinstance(saved.get("bytes"), int) or not 0 <= saved["bytes"] <= MAX_FILE_BYTES:
                    raise IntakeError("corrupt snapshot metadata")
                relative_source_path(saved.get("path"))
                commit_sha(saved.get("git_blob_sha"))
                _local_path(root, saved.get("artifact_path"))
                _local_path(root, saved.get("receipt_path"))
    for url, cached in state["cache"].items():
        _validate_url(url)
        if not isinstance(cached, dict) or set(cached) != {"etag", "body_path", "body_sha256", "receipt_path"} or not isinstance(cached["etag"], str) or not re.fullmatch(r"[0-9a-f]{64}", str(cached["body_sha256"])):
            raise IntakeError("corrupt response cache")
        _local_path(root, cached["body_path"])
        _local_path(root, cached["receipt_path"])
    return state


def _local_path(root: Path, value: str) -> Path:
    safe = relative_source_path(value)
    target = root / safe
    for item in (target, *target.parents):
        if item == root.parent:
            break
        if item.is_symlink():
            raise IntakeError("saved artifact may not follow a symlink")
    return target


def _validate_url(url: str) -> None:
    parsed = urlsplit(url)
    if parsed.scheme != "https" or parsed.netloc != "api.github.com" or parsed.fragment or not (parsed.path == "/search/repositories" or parsed.path.startswith("/repos/")):
        raise IntakeError("invalid GitHub API URL")


class Client:
    def __init__(self, root: Path, state: dict, run_id: str, now: datetime, transport: Transport = public_get, request_cap: int = 24):
        if isinstance(request_cap, bool) or not isinstance(request_cap, int) or not 1 <= request_cap <= 24:
            raise IntakeError("request cap must be between 1 and 24")
        self.root, self.state, self.run_id, self.now = root, state, run_id, utc(now)
        self.transport, self.request_cap, self.count = transport, request_cap, 0
        self.response_bytes = 0
        self.receipts: list[str] = []
        self.run_dir = _private_dir(root / "runs" / run_id)

    def save_state(self):
        _write_json(self.root / "state.json", self.state)

    def get(self, path: str, params: Mapping[str, str | int] | None = None, *, optional: bool = False) -> tuple[object | None, str]:
        if not path.startswith("/") or "?" in path or "#" in path:
            raise IntakeError("API path must be generated separately from parameters")
        url = API + path + (("?" + urlencode(params)) if params else "")
        _validate_url(url)
        if self.count >= self.request_cap:
            raise RequestCap("bounded request cap reached")
        if self.response_bytes >= MAX_RUN_BYTES:
            raise ByteCap("bounded aggregate HTTP body byte cap reached")
        request_byte_limit = min(MAX_RESPONSE_BYTES, MAX_RUN_BYTES - self.response_bytes)
        headers = {"Accept": "application/vnd.github+json", "User-Agent": "CoinHunt-public-strategy-intake/1", "X-GitHub-Api-Version": "2022-11-28"}
        cached = self.state["cache"].get(url)
        cached_bytes = None
        if cached:
            body_path = _local_path(self.root, cached["body_path"])
            if not body_path.is_file() or body_path.stat().st_size > MAX_RESPONSE_BYTES:
                raise IntakeError("cached response is missing or oversized")
            cached_bytes = body_path.read_bytes()
            if hashlib.sha256(cached_bytes).hexdigest() != cached["body_sha256"]:
                raise IntakeError("cached response bytes do not match saved hash")
            if not cached["etag"] or any(ord(char) < 32 or ord(char) == 127 for char in cached["etag"]):
                raise IntakeError("invalid cached ETag")
            headers["If-None-Match"] = cached["etag"]
        self.count += 1
        prefix = f"http-{self.count:02d}"
        receipt_path = self.run_dir / f"{prefix}.json"
        relative_receipt = str(receipt_path.relative_to(self.root))
        receipt = {"schema": SCHEMA, "requested_at": timestamp(self.now), "url": url, "method": "GET", "unauthenticated": True, "external_text_trust": "untrusted_data", "max_response_bytes": request_byte_limit, "max_run_bytes": MAX_RUN_BYTES, "timeout_seconds": TIMEOUT_SECONDS}
        try:
            response = self.transport(url, headers, TIMEOUT_SECONDS, request_byte_limit)
            if not isinstance(response, Response) or not isinstance(response.body, bytes) or not isinstance(response.status, int):
                raise IntakeError("invalid transport response")
        except Exception as error:
            receipt.update({"status": None, "transport_error_type": type(error).__name__, "complete_response": False})
            _write_json(receipt_path, receipt)
            self.receipts.append(relative_receipt)
            raise IntakeError("public GET failed; retained failure receipt") from error
        safe_headers = {str(key).lower(): str(value) for key, value in response.headers.items() if str(key).lower() in SAFE_HEADERS}
        raw_path = self.run_dir / f"{prefix}.body"
        raw = response.body[:request_byte_limit + 1]
        self.response_bytes += len(raw)
        _write_bytes(raw_path, raw)
        receipt.update({"status": response.status, "headers": safe_headers, "body_path": str(raw_path.relative_to(self.root)), "body_sha256": hashlib.sha256(raw).hexdigest(), "body_bytes": len(raw), "complete_response": len(response.body) <= request_byte_limit})
        if response.status == 304:
            if cached_bytes is None:
                _write_json(receipt_path, receipt)
                self.receipts.append(relative_receipt)
                raise IntakeError("304 without an intact cached response")
            receipt["effective_body_path"] = cached["body_path"]
            receipt["effective_body_sha256"] = cached["body_sha256"]
        _write_json(receipt_path, receipt)
        self.receipts.append(relative_receipt)
        if not receipt["complete_response"]:
            if request_byte_limit < MAX_RESPONSE_BYTES:
                raise ByteCap("response exceeds remaining aggregate HTTP body byte budget")
            raise IntakeError("response exceeds the bounded byte limit")
        if response.status in {403, 429}:
            raise RateLimit(f"HTTP {response.status}; stopped with partial receipts")
        if response.status == 404 and optional:
            return None, relative_receipt
        if response.status not in {200, 304}:
            raise IntakeError(f"HTTP {response.status}; response retained")
        body = cached_bytes if response.status == 304 else raw
        if response.status == 200 and safe_headers.get("etag"):
            etag = safe_headers["etag"]
            if any(ord(char) < 32 or ord(char) == 127 for char in etag):
                raise IntakeError("invalid server ETag")
            self.state["cache"][url] = {"etag": etag, "body_path": receipt["body_path"], "body_sha256": receipt["body_sha256"], "receipt_path": relative_receipt}
            self.save_state()
        try:
            data = _json_loads(body)
        except (ValueError, UnicodeError, TypeError) as error:
            raise IntakeError("invalid GitHub JSON response") from error
        if safe_headers.get("x-ratelimit-remaining") == "0":
            raise RateLimit("public API rate limit exhausted; response retained")
        return data, relative_receipt


def _metadata(data: object, expected_repo: str | None = None) -> dict:
    if not isinstance(data, dict):
        raise IntakeError("repository metadata is malformed")
    name = repo_name(data.get("full_name"))
    if name in EXCLUDED_REPOSITORIES:
        raise IntakeError("own or excluded repository is forbidden for source inspection")
    if expected_repo and name != expected_repo:
        raise IntakeError("repository metadata name mismatch")
    if data.get("private") is not False or data.get("fork") is not False or data.get("archived") is not False or data.get("visibility", "public") != "public":
        raise IntakeError("private, forked, or archived repositories are excluded")
    branch = data.get("default_branch")
    if not isinstance(branch, str) or not branch or len(branch) > 255 or any(ord(char) < 32 for char in branch):
        raise IntakeError("invalid default branch")
    return data


def _file(data: object) -> tuple[bytes, dict]:
    if not isinstance(data, dict) or data.get("type") != "file" or data.get("encoding") != "base64" or data.get("target") is not None or data.get("submodule_git_url") is not None:
        raise IntakeError("only ordinary base64 file snapshots are allowed")
    path = relative_source_path(data.get("path"))
    size = data.get("size")
    if isinstance(size, bool) or not isinstance(size, int) or not 0 <= size <= MAX_FILE_BYTES:
        raise IntakeError("file exceeds the bounded source byte limit")
    content = data.get("content")
    if not isinstance(content, str):
        raise IntakeError("file content is missing")
    try:
        decoded = base64.b64decode("".join(content.split()), validate=True)
    except ValueError as error:
        raise IntakeError("invalid base64 file content") from error
    if len(decoded) != size or len(decoded) > MAX_FILE_BYTES:
        raise IntakeError("file size mismatch")
    sha = commit_sha(data.get("sha"))
    actual = hashlib.sha1(b"blob " + str(len(decoded)).encode() + b"\0" + decoded).hexdigest()
    if actual != sha:
        raise IntakeError("Git blob SHA mismatch")
    return decoded, {"path": path, "git_blob_sha": sha, "sha256": hashlib.sha256(decoded).hexdigest(), "bytes": len(decoded), "external_text_trust": "untrusted_data"}


def _tree(data: object, expected_sha: str) -> dict:
    if not isinstance(data, dict) or commit_sha(data.get("sha")) != expected_sha or data.get("truncated") is not False or not isinstance(data.get("tree"), list):
        raise IntakeError("pinned tree is malformed or truncated")
    seen = set()
    for entry in data["tree"]:
        if not isinstance(entry, dict) or not isinstance(entry.get("path"), str) or not entry["path"] or entry["path"] in seen or entry.get("mode") not in {"100644", "100755", "120000", "160000", "040000"} or entry.get("type") not in {"blob", "tree", "commit"}:
            raise IntakeError("pinned tree entry is malformed")
        commit_sha(entry.get("sha"))
        seen.add(entry["path"])
    return data


def _candidate_tree(root: Path, candidate: dict) -> dict:
    saved = candidate.get("tree")
    if not isinstance(saved, dict):
        raise IntakeError("pinned source tree is missing")
    target = _local_path(root, saved.get("artifact_path"))
    if not target.is_file() or target.stat().st_size > MAX_RESPONSE_BYTES:
        raise IntakeError("pinned source tree is missing or oversized")
    body = target.read_bytes()
    if hashlib.sha256(body).hexdigest() != saved.get("sha256"):
        raise IntakeError("pinned source tree hash mismatch")
    try:
        data = _json_loads(body)
    except (ValueError, UnicodeError) as error:
        raise IntakeError("corrupt pinned source tree") from error
    return _tree(data, commit_sha(saved.get("git_tree_sha")))


def _ordinary_blob(root: Path, candidate: dict, info: dict) -> None:
    tree = _candidate_tree(root, candidate)
    entries = [entry for entry in tree["tree"] if entry["path"] == info["path"]]
    if len(entries) != 1 or entries[0]["mode"] not in {"100644", "100755"} or entries[0]["type"] != "blob" or entries[0]["sha"].lower() != info["git_blob_sha"]:
        raise IntakeError("source path is a symlink, directory, submodule, or unpinned blob")


def _save_file(client: Client, candidate: dict, kind: str, data: object, receipt: str) -> dict | None:
    if data is None:
        return None
    decoded, info = _file(data)
    _ordinary_blob(client.root, candidate, info)
    artifact = client.run_dir / "sources" / f"{candidate['repo'].replace('/', '--')}--{candidate['commit']}--{hashlib.sha256(kind.encode()).hexdigest()[:12]}.data"
    _write_bytes(artifact, decoded)
    info.update({"artifact_path": str(artifact.relative_to(client.root)), "receipt_path": receipt, "pinned_commit": candidate["commit"]})
    return info


def default_queries(now: datetime) -> list[str]:
    since = (utc(now) - timedelta(days=90)).date().isoformat()
    recent = f"fork:false archived:false pushed:>={since}"
    return [f"crypto strategy backtest in:readme language:Python license:mit {recent}",
            f"cryptocurrency backtest in:readme language:Python license:apache-2.0 {recent}",
            f"crypto arbitrage funding in:readme language:Python {recent}",
            "bitcoin rebalancing in:readme language:Python fork:false archived:false"]


def select_candidates(found: dict, queue: dict, limit: int):
    """Prefer unfinished/changed/unseen sources, so stable leaders cannot starve backlog."""
    def priority(item):
        name, result = item
        previous = [c for c in queue.values() if c["repo"] == name]
        if not previous:
            license_info = result["metadata"].get("license") or {}
            return 1 if license_info.get("spdx_id") in PERMISSIVE else 2
        latest = max(previous, key=lambda c: c["first_seen_at"])
        if latest["intake_status"] != "QUEUED_FOR_REVIEW":
            return 0
        return 3 if latest.get("pushed_at") == result["metadata"].get("pushed_at") else 1
    ordered = sorted(found.items(), key=priority)
    return ordered[:limit], [name for name, _ in ordered[limit:]]


def _begin(root: Path, state: dict, now: datetime, transport: Transport, request_cap: int, mode: str) -> tuple[Client, dict]:
    run_id = f"{utc(now).strftime('%Y%m%dT%H%M%SZ')}-{uuid.uuid4().hex[:8]}"
    client = Client(root, state, run_id, now, transport, request_cap)
    summary = {"schema": SCHEMA, "run_id": run_id, "mode": mode, "started_at": timestamp(now), "status": "RUNNING", "new_candidates": [], "resumed_candidates": [], "unchanged_revisions": [], "receipts": [], "coverage": {"complete": False, "reason": "GitHub repository keyword search is bounded and incomplete; no claim of exhaustive method coverage"}, "claims": {"profitability": "unvalidated", "novelty": "not_assessed", "reuse_permission": "requires_review"}}
    _write_json(client.run_dir / "summary.json", summary)
    return client, summary


def _finish(client: Client, summary: dict, error: Exception | None = None) -> dict:
    summary["requests_made"] = client.count
    summary["response_bytes_retained"] = client.response_bytes
    summary["max_run_response_bytes"] = MAX_RUN_BYTES
    summary["receipts"] = client.receipts
    summary["status"] = "COMPLETE" if error is None else ("PARTIAL_RATE_LIMIT" if isinstance(error, RateLimit) else "PARTIAL_REQUEST_CAP" if isinstance(error, RequestCap) else "PARTIAL_BYTE_CAP" if isinstance(error, ByteCap) else "FAILED")
    if error:
        summary["error"] = str(error)
    summary["summary_path"] = str((client.run_dir / "summary.json").relative_to(client.root))
    client.save_state()
    _write_json(client.run_dir / "summary.json", summary)
    return summary


def discover(state_dir: Path, *, now: datetime | None = None, transport: Transport = public_get, queries: list[str] | None = None, per_page: int = 10, max_repos: int = 4, request_cap: int = 24) -> dict:
    now = utc(now)
    queries = default_queries(now) if queries is None else queries
    if not isinstance(queries, list) or not 1 <= len(queries) <= 4 or any(not isinstance(q, str) or not q.strip() or len(q) > 512 or any(ord(c) < 32 for c in q) for q in queries):
        raise IntakeError("one to four bounded keyword queries are required")
    if isinstance(per_page, bool) or not isinstance(per_page, int) or not 1 <= per_page <= 10 or isinstance(max_repos, bool) or not isinstance(max_repos, int) or not 1 <= max_repos <= 4:
        raise IntakeError("per-page must be 1..10 and max-repos must be 1..4")
    with state_lock(state_dir) as root:
        state = load_state(root)
        last = state["last_discovery_started_at"]
        if last and now < parse_time(last) + timedelta(hours=24):
            return {"schema": SCHEMA, "mode": "discover", "status": "SKIPPED_24H_GUARD", "next_allowed_at": timestamp(parse_time(last) + timedelta(hours=24)), "requests_made": 0, "new_candidates": []}
        client, summary = _begin(root, state, now, transport, request_cap, "discover")
        state["last_discovery_started_at"] = timestamp(now)
        client.save_state()  # Guard unsuccessful attempts as well as successful ones.
        summary["coverage"].update({"queries": [], "per_page": per_page, "repository_snapshot_cap": max_repos, "request_cap": request_cap, "skipped_repositories": [], "excluded_repository_count": 0})
        try:
            found: dict[str, dict] = {}
            for query in queries:
                bounded_query = query + " " + " ".join(f"-repo:{name}" for name in sorted(EXCLUDED_REPOSITORIES))
                data, receipt = client.get("/search/repositories", {"q": bounded_query, "sort": "updated", "order": "desc", "per_page": per_page, "page": 1})
                if not isinstance(data, dict) or not isinstance(data.get("items"), list) or isinstance(data.get("total_count"), bool) or not isinstance(data.get("total_count"), int) or data["total_count"] < 0 or not isinstance(data.get("incomplete_results"), bool) or len(data["items"]) > per_page:
                    raise IntakeError("malformed repository search response")
                summary["coverage"]["queries"].append({"query": query, "receipt_path": receipt, "total_count": data["total_count"], "returned_count": len(data["items"]), "api_incomplete_results": data["incomplete_results"], "page_cap_truncated": data["total_count"] > len(data["items"])})
                for item in data["items"]:
                    # Names are checked before reading any other metadata or issuing
                    # repository-specific requests. Never queue an excluded source.
                    item_name = item.get("full_name") if isinstance(item, dict) else None
                    if isinstance(item_name, str) and item_name.lower() in EXCLUDED_REPOSITORIES:
                        summary["coverage"]["excluded_repository_count"] += 1
                        continue
                    try:
                        metadata = _metadata(item)
                    except IntakeError as error:
                        summary["coverage"]["skipped_repositories"].append({"reason": str(error)})
                        continue
                    name = repo_name(metadata["full_name"])
                    if name not in found:
                        found[name] = {"metadata": metadata, "contexts": []}
                    found[name]["contexts"].append({"query": query, "search_receipt_path": receipt, "first_seen_at": timestamp(now), "pushed_at": metadata.get("pushed_at")})
            summary["coverage"]["unique_eligible_repositories"] = len(found)
            summary["coverage"]["repository_cap_truncated"] = len(found) > max_repos
            selected, deferred = select_candidates(found, state["queue"], max_repos)
            summary["coverage"]["deferred_repositories"] = deferred
            for name, result in selected:
                metadata, meta_receipt = client.get(f"/repos/{name}")
                metadata = _metadata(metadata, name)
                head, head_receipt = client.get(f"/repos/{name}/commits/{quote(metadata['default_branch'], safe='')}")
                if not isinstance(head, dict):
                    raise IntakeError("malformed default-branch head response")
                sha = commit_sha(head.get("sha"))
                key = f"{name}@{sha}"
                if key in state["queue"]:
                    candidate = state["queue"][key]
                    _candidate_tree(root, candidate)
                    if candidate["intake_status"] == "QUEUED_FOR_REVIEW":
                        for saved in candidate["snapshots"].values():
                            if saved is not None:
                                target = _local_path(root, saved["artifact_path"])
                                if not target.is_file() or target.stat().st_size > MAX_FILE_BYTES or hashlib.sha256(target.read_bytes()).hexdigest() != saved["sha256"]:
                                    raise IntakeError("queued source snapshot is missing or corrupt")
                        summary["unchanged_revisions"].append(key)
                        continue
                    summary["resumed_candidates"].append(key)
                else:
                    tree_meta = head.get("commit", {}).get("tree") if isinstance(head.get("commit"), dict) else None
                    if not isinstance(tree_meta, dict):
                        raise IntakeError("default-branch commit tree is missing")
                    tree_sha = commit_sha(tree_meta.get("sha"))
                    tree_data, tree_receipt = client.get(f"/repos/{name}/git/trees/{tree_sha}", {"recursive": "1"})
                    _tree(tree_data, tree_sha)
                    tree_bytes = json.dumps(tree_data, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()
                    if len(tree_bytes) > MAX_RESPONSE_BYTES:
                        raise IntakeError("normalized pinned tree exceeds byte cap")
                    tree_path = client.run_dir / "sources" / f"{name.replace('/', '--')}--{sha}--tree.json"
                    _write_bytes(tree_path, tree_bytes)
                    candidate = {"repo": name, "commit": sha, "first_seen_at": timestamp(now), "pushed_at": metadata.get("pushed_at"), "default_branch": metadata["default_branch"], "search_context": result["contexts"], "metadata_receipt_path": meta_receipt, "head_receipt_path": head_receipt, "repo_url": f"https://github.com/{name}", "commit_url": f"https://github.com/{name}/commit/{sha}", "snapshots": {}, "tree": {"git_tree_sha": tree_sha, "artifact_path": str(tree_path.relative_to(root)), "sha256": hashlib.sha256(tree_bytes).hexdigest(), "receipt_path": tree_receipt}, "license_spdx": None, "license_policy": "unknown_license_review", "intake_status": "PENDING_SOURCE_SNAPSHOTS", "external_text_trust": "untrusted_data", "reuse_permission": "requires_review", "profitability": "unvalidated", "novelty": "not_assessed"}
                    state["queue"][key] = candidate
                    summary["new_candidates"].append(key)
                    client.save_state()
                if "license" not in candidate["snapshots"]:
                    license_data, license_receipt = client.get(f"/repos/{name}/license", {"ref": sha}, optional=True)
                    candidate["snapshots"]["license"] = _save_file(client, candidate, "license", license_data, license_receipt)
                    license_info = license_data.get("license") if isinstance(license_data, dict) else None
                    spdx = license_info.get("spdx_id") if isinstance(license_info, dict) else None
                    candidate["license_spdx"] = spdx if isinstance(spdx, str) and len(spdx) <= 100 else None
                    candidate["license_policy"] = license_policy(candidate["license_spdx"])
                    candidate["license_receipt_path"] = license_receipt
                    client.save_state()
                if "readme" not in candidate["snapshots"]:
                    readme, readme_receipt = client.get(f"/repos/{name}/readme", {"ref": sha}, optional=True)
                    candidate["snapshots"]["readme"] = _save_file(client, candidate, "readme", readme, readme_receipt)
                    candidate["readme_receipt_path"] = readme_receipt
                candidate["intake_status"] = "QUEUED_FOR_REVIEW"
                client.save_state()
            return _finish(client, summary)
        except IntakeError as error:
            return _finish(client, summary, error)


def snapshot(state_dir: Path, *, repo: str, commit: str, path: str, now: datetime | None = None, transport: Transport = public_get) -> dict:
    name, sha, source_path = repo_name(repo), commit_sha(commit), relative_source_path(path)
    if name in EXCLUDED_REPOSITORIES:
        raise IntakeError("own or excluded repository is forbidden for source inspection")
    now = utc(now)
    with state_lock(state_dir) as root:
        state = load_state(root)
        key = f"{name}@{sha}"
        if key not in state["queue"]:
            raise IntakeError("source snapshot requires an already queued pinned revision")
        candidate = state["queue"][key]
        saved = candidate["snapshots"].get(f"source:{source_path}")
        if saved:
            target = _local_path(root, saved["artifact_path"])
            if not target.is_file() or target.stat().st_size > MAX_FILE_BYTES or hashlib.sha256(target.read_bytes()).hexdigest() != saved["sha256"]:
                raise IntakeError("existing source snapshot is missing or corrupt")
            return {"schema": SCHEMA, "mode": "snapshot", "status": "UNCHANGED_SNAPSHOT", "requests_made": 0, "candidate": key, "snapshot": saved}
        client, summary = _begin(root, state, now, transport, 2, "snapshot")
        summary["candidate"] = key
        try:
            metadata, _ = client.get(f"/repos/{name}")
            _metadata(metadata, name)
            content, receipt = client.get(f"/repos/{name}/contents/{'/'.join(quote(segment, safe='') for segment in source_path.split('/'))}", {"ref": sha})
            value = _save_file(client, candidate, f"source:{source_path}", content, receipt)
            if value is None or value["path"] != source_path:
                raise IntakeError("source snapshot path mismatch")
            candidate["snapshots"][f"source:{source_path}"] = value
            summary["snapshot"] = value
            return _finish(client, summary)
        except IntakeError as error:
            return _finish(client, summary, error)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    search = commands.add_parser("discover")
    search.add_argument("--state-dir", type=Path, required=True)
    search.add_argument("--query", action="append", dest="queries")
    search.add_argument("--per-page", type=int, default=10)
    search.add_argument("--max-repos", type=int, default=4)
    search.add_argument("--request-cap", type=int, default=24)
    source = commands.add_parser("snapshot")
    source.add_argument("--state-dir", type=Path, required=True)
    source.add_argument("--repo", required=True)
    source.add_argument("--commit", required=True)
    source.add_argument("--path", required=True)
    args = vars(parser.parse_args(argv))
    command = args.pop("command")
    try:
        result = discover(**args) if command == "discover" else snapshot(**args)
    except (IntakeError, OSError) as error:
        result = {"status": "FAILED", "error": str(error)}
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["status"] in {"COMPLETE", "UNCHANGED_SNAPSHOT", "SKIPPED_24H_GUARD"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
