#!/usr/bin/env python3
"""Daily bounded screening log for trusted GitHub-method adapters, not trade routing."""
from __future__ import annotations
import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import fcntl
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sys
import uuid


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def sha(data):
    return hashlib.sha256(data).hexdigest()


def utc():
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def runtime_identity():
    return {"python": sys.version, "implementation": sys.implementation.name, "cache_tag": sys.implementation.cache_tag}


def safe_root(value):
    path = Path(value).absolute()
    if "crypto-trading-system" in [p.casefold() for p in path.parts]:
        raise ValueError("excluded project path")
    if "autotrade" in path.parts or "preregistration" in path.parts:
        raise ValueError("owner books and frozen paths are not intake storage")
    if path.is_symlink() or any(p.is_symlink() for p in path.parents):
        raise ValueError("intake paths may not use symlinks")
    return path


def trusted_screen():
    file = Path(__file__).with_name("github_strategy_screen.py")
    spec = importlib.util.spec_from_file_location("coinhunt_trusted_github_screen", file)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@contextmanager
def locked(root):
    root = safe_root(root)
    root.mkdir(parents=True, exist_ok=True)
    path = root / "screen-log.lock"
    if path.is_symlink():
        raise ValueError("lock symlink forbidden")
    with path.open("a") as handle:
        fcntl.flock(handle, fcntl.LOCK_EX)
        try:
            yield root
        finally:
            fcntl.flock(handle, fcntl.LOCK_UN)


def read_log(root):
    path = root / "screen-log.jsonl"
    if path.is_symlink():
        raise ValueError("log symlink forbidden")
    if not path.exists():
        return []
    raw = path.read_bytes()
    if raw and not raw.endswith(b"\n"):
        raise ValueError("incomplete screen log; never truncate it automatically")
    rows, previous = [], None
    for seq, line in enumerate(raw.splitlines(), 1):
        row = json.loads(line)
        supplied = row.pop("hash", None)
        if type(row.get("seq")) is not int or row.get("schema_version") != 1 or row.get("kind") not in {"started", "finished", "duplicate"} or row.get("seq") != seq or row.get("prev_hash") != previous or supplied != sha(canonical(row)):
            raise ValueError("corrupt screen log")
        row["hash"] = supplied
        rows.append(row)
        previous = supplied
    return rows


def append(root, rows, payload):
    row = {"schema_version": 1, "seq": len(rows) + 1, "utc": utc(),
           "prev_hash": rows[-1]["hash"] if rows else None, **payload}
    row["hash"] = sha(canonical(row))
    with (root / "screen-log.jsonl").open("a") as handle:
        handle.write(canonical(row).decode() + "\n")
        handle.flush()
        os.fsync(handle.fileno())
    rows.append(row)
    return row


def screen(state_dir, spec_path, cache_dir, sources_dir, retry_reason=None):
    """Two attempts per UTC day, durable log, exact-method/data/code deduplication."""
    spec_path = safe_root(spec_path)
    cache_dir, sources_dir = safe_root(cache_dir), safe_root(sources_dir)
    module = trusted_screen()
    with locked(state_dir) as root:
        rows = read_log(root)
        # Reading these already-explored inputs is not a claim of blind access.
        raw = spec_path.read_bytes()
        spec_hash = sha(raw)
        own_code = {"screen": module.code_footprint()["sha256"], "intake": sha(Path(__file__).read_bytes()), "runtime": runtime_identity()}
        origin, preflight = None, None
        try:
            spec = module.validate_spec(module._json(raw))
            prices, hashes = module.load_inputs(spec, cache_dir, sources_dir)
            fixed_protocol = {k: v for k, v in spec["protocol"].items() if k != "planned_at"}
            for key in ("capital_usd", "side_cost_bps", "stress_side_cost_bps"):
                fixed_protocol[key] = float(fixed_protocol[key])
            normalized_method = {**spec["method"], "weights": {k: float(v) for k, v in spec["method"]["weights"].items()},
                                 "drift_band": float(spec["method"].get("drift_band", 0))}
            method_identity = sha(canonical({"method": normalized_method, "protocol": fixed_protocol}))
            used_data = sha(canonical(prices))
            fingerprint = sha(canonical({"method_identity": method_identity, "used_data": used_data, "own_code": own_code}))
            origin = {"repo_url": spec["source"]["repo_url"], "commit": spec["source"]["commit"],
                      "source_hashes": hashes["source_sha256"], "candidate_id": spec["candidate_id"]}
        except (ValueError, OSError) as error:
            preflight = type(error).__name__
            method_identity = None
            fingerprint = sha(canonical({"invalid_spec_hash": spec_hash, "own_code": own_code}))
        if retry_reason is not None and (not isinstance(retry_reason, str) or not retry_reason.strip() or len(retry_reason) > 1000):
            raise ValueError("retry reason must be nonempty bounded text")
        finished = [r for r in rows if r.get("kind") == "finished" and r.get("fingerprint") == fingerprint]
        started = [r for r in rows if r.get("kind") == "started" and r.get("fingerprint") == fingerprint]
        if started and not finished:
            prior = started[-1]
            prior_output = safe_root(root / "screens" / prior["attempt_id"])
            marker, result_file = prior_output / "attempt-events.jsonl", prior_output / "result.json"
            if marker.is_file() and not marker.is_symlink() and result_file.is_file() and not result_file.is_symlink():
                raw_marker = marker.read_bytes()
                if raw_marker.endswith(b"\n"):
                    event = json.loads(raw_marker.splitlines()[-1])
                    old_result = json.loads(result_file.read_bytes())
                    if event.get("phase") == "COMPLETED" and event.get("result_sha256") == sha(result_file.read_bytes()) and event.get("status") == old_result.get("status") and old_result.get("validated_profitability") is False:
                        recovered = append(root, rows, {"kind": "finished", "attempt_id": prior["attempt_id"], "fingerprint": fingerprint,
                                                       "status": event["status"], "result_sha256": event["result_sha256"], "output": str(prior_output),
                                                       "started_receipt_hash": prior["hash"], "recovered_completion": True, "validated_profitability": False})
                        finished = [recovered]
        if finished:
            last = finished[-1]
            if last["status"] not in {"BLOCKED", "INCOMPLETE"} or not retry_reason:
                result_file = safe_root(root / "screens" / last["attempt_id"]) / "result.json"
                if result_file.is_symlink() or not result_file.is_file() or sha(result_file.read_bytes()) != last["result_sha256"]:
                    return {"status": "PRIOR_RESULT_UNAVAILABLE", "attempt_id": last["attempt_id"], "validated_profitability": False}
                entry = append(root, rows, {"kind": "duplicate", "fingerprint": fingerprint,
                                           "origin": origin, "reused_attempt_id": last["attempt_id"]})
                return {"status": "SKIPPED_IDENTICAL_SCREEN", "reused_attempt_id": last["attempt_id"],
                        "prior_result_status": last["status"], "log_head": entry["hash"], "validated_profitability": False}
        if started and not finished and not retry_reason:
            return {"status": "INTERRUPTED_NEEDS_REVIEW", "attempt_id": started[-1]["attempt_id"],
                    "detail": "Prior synchronous run has no completion receipt; inspect its saved attempt before retrying.", "validated_profitability": False}
        today = utc()[:10]
        if sum(r.get("kind") == "started" and r["utc"][:10] == today for r in rows) >= 2:
            return {"status": "SKIPPED_DAILY_SCREEN_BUDGET", "attempts_per_utc_day": 2, "validated_profitability": False}
        attempt_id = today.replace("-", "") + "-" + uuid.uuid4().hex[:12]
        output = root / "screens" / attempt_id
        prepared = append(root, rows, {"kind": "started", "attempt_id": attempt_id, "fingerprint": fingerprint,
                                       "method_identity": method_identity, "spec_sha256": spec_hash, "own_code": own_code,
                                       "origin": origin, "preflight": preflight, "retry_reason": retry_reason,
                                       "output": str(output), "evidence_class": "explored-history"})
        result = module.run_screen(spec_path, cache_dir, sources_dir, output)
        result_hash = sha((output / "result.json").read_bytes())
        entry = append(root, rows, {"kind": "finished", "attempt_id": attempt_id, "fingerprint": fingerprint,
                                   "status": result["status"], "result_sha256": result_hash, "output": str(output),
                                   "started_receipt_hash": prepared["hash"], "validated_profitability": False})
        return {"status": result["status"], "attempt_id": attempt_id, "output": str(output),
                "result_sha256": result_hash, "log_head": entry["hash"], "validated_profitability": False}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("screen")
    for name in ("state-dir", "spec", "cache", "sources-dir"):
        p.add_argument("--" + name, required=True, type=Path)
    p.add_argument("--retry-reason")
    p = sub.add_parser("status")
    p.add_argument("--state-dir", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        if args.command == "screen":
            result = screen(args.state_dir, args.spec, args.cache, args.sources_dir, args.retry_reason)
        else:
            with locked(args.state_dir) as root:
                rows = read_log(root)
                result = {"attempts": sum(r["kind"] == "started" for r in rows),
                          "completed": sum(r["kind"] == "finished" for r in rows),
                          "duplicate_accesses": sum(r["kind"] == "duplicate" for r in rows),
                          "log_head": rows[-1]["hash"] if rows else None, "validated_profitability": False}
    except (OSError, ValueError) as error:
        parser.exit(2, f"Intake blocked: {error}\n")
    print(json.dumps(result, sort_keys=True))
    return 2 if result.get("status") in {"BLOCKED", "INCOMPLETE", "INTERRUPTED_NEEDS_REVIEW", "PRIOR_RESULT_UNAVAILABLE"} else 0


if __name__ == "__main__":
    raise SystemExit(main())
