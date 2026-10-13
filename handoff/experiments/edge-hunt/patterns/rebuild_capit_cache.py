#!/usr/bin/env python3
"""One-time, resumable public hourly Coinbase Exchange history acquisition.

CLI history is fixed: 21 USD products, [2023-01-01, 2026-10-10) UTC.
Each chunk atomically stores the exact UTF-8 response body, its SHA-256, and
request metadata. Existing chunks are revalidated, never silently repaired.
Missing candles remain missing: Coinbase may omit intervals with no ticks.
"""

from __future__ import annotations

import argparse
import contextlib
import dataclasses
import datetime as dt
import fcntl
import hashlib
import json
import math
import os
from pathlib import Path
import tempfile
import time
from typing import Callable

ORIGINAL_COINS = ("BTC", "ETH", "SOL", "XRP", "DOGE", "ADA", "AVAX", "LINK", "LTC", "BCH", "DOT")
EXTRA_COINS = ("AAVE", "UNI", "SHIB", "CRV", "GRT", "XTZ", "BAT", "SUSHI", "YFI", "PEPE")
COINS = ORIGINAL_COINS + EXTRA_COINS
START = 1672531200  # 2023-01-01T00:00:00Z
END = 1791590400  # 2026-10-10T00:00:00Z; exclusive
GRANULARITY = 3600
MAX_ROWS = 300
MIN_REQUEST_SPACING = 0.35
MAX_RETRIES = 2
MAX_BODY_BYTES = 1_000_000
ENDPOINT = "https://api.exchange.coinbase.com/products/{product}/candles"
SCHEMA = "coinbase-hourly-cache-v1"


class CacheError(Exception):
    """Existing cache is inconsistent or a chunk cannot be acquired safely."""


class ValidationError(CacheError):
    pass


class DownloadError(CacheError):
    pass


class PilotLimitReached(Exception):
    pass


def iso(timestamp: int) -> str:
    return dt.datetime.fromtimestamp(timestamp, dt.timezone.utc).isoformat().replace("+00:00", "Z")


def now_utc() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z")


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def json_bytes(value: object) -> bytes:
    return (json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False, separators=(",", ":")) + "\n").encode("utf-8")


def atomic_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary: str | None = None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent, prefix=f".{path.name}.", delete=False) as handle:
            temporary = handle.name
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        temporary = None
    finally:
        if temporary is not None:
            with contextlib.suppress(FileNotFoundError):
                os.unlink(temporary)


@dataclasses.dataclass(frozen=True)
class Plan:
    coins: tuple[str, ...] = COINS
    start: int = START
    end: int = END
    granularity: int = GRANULARITY
    max_rows: int = MAX_ROWS

    def descriptor(self) -> dict:
        return {
            "schema": SCHEMA, "coins": list(self.coins), "start_inclusive": self.start,
            "end_exclusive": self.end, "granularity": self.granularity,
            "max_rows_per_chunk": self.max_rows, "endpoint": ENDPOINT,
            "missing_candles": "not_synthesized",
        }

    def chunks(self) -> list[Chunk]:
        if (self.granularity <= 0 or self.max_rows <= 0 or self.start >= self.end
                or self.start % self.granularity or self.end % self.granularity):
            raise ValueError("unaligned_or_invalid_plan")
        return [Chunk(coin, start, min(start + self.max_rows * self.granularity, self.end), self.granularity)
                for coin in self.coins
                for start in range(self.start, self.end, self.max_rows * self.granularity)]


@dataclasses.dataclass(frozen=True)
class Chunk:
    coin: str
    start: int
    end: int
    granularity: int = GRANULARITY

    @property
    def relative_path(self) -> str:
        return f"chunks/{self.coin}/{self.start}-{self.end}.json"

    def request(self) -> dict:
        return {
            "coin": self.coin, "product": f"{self.coin}-USD",
            "url": ENDPOINT.format(product=f"{self.coin}-USD"),
            "start_inclusive": self.start, "end_exclusive": self.end,
            # Match wide_coins' original request convention: end names the
            # start of the final requested hourly bucket (not the next chunk).
            "params": {"start": iso(self.start), "end": iso(self.end - self.granularity),
                       "granularity": self.granularity},
        }


@dataclasses.dataclass
class ValidatedRows:
    values: dict[int, list[float]]
    ignored_before_start: int


def validate_body(body: bytes, chunk: Chunk) -> ValidatedRows:
    if len(body) > MAX_BODY_BYTES:
        raise ValidationError("response_too_large")
    try:
        rows = json.loads(body.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise ValidationError("response_not_utf8_json") from exc
    if not isinstance(rows, list):
        raise ValidationError("response_not_array")
    values: dict[int, list[float]] = {}
    seen: set[int] = set()
    ignored = 0
    for row in rows:
        if not isinstance(row, list) or len(row) != 6:
            raise ValidationError("candle_shape")
        timestamp = row[0]
        if type(timestamp) is not int or timestamp % chunk.granularity:
            raise ValidationError("timestamp_not_aligned_integer")
        if timestamp in seen:
            raise ValidationError("duplicate_timestamp")
        seen.add(timestamp)
        numbers = row[1:]
        if any(type(number) not in (int, float) or not math.isfinite(number) for number in numbers):
            raise ValidationError("nonfinite_or_nonnumeric_ohlcv")
        low, high, opening, close, volume = numbers
        if min(low, high, opening, close) <= 0 or volume < 0:
            raise ValidationError("nonpositive_price_or_negative_volume")
        if low > high or not low <= opening <= high or not low <= close <= high:
            raise ValidationError("inconsistent_ohlc")
        if timestamp >= chunk.end:
            raise ValidationError("timestamp_at_or_after_end")
        if timestamp < chunk.start:
            # Coinbase documents occasional candles preceding requested start.
            ignored += 1
            continue
        values[timestamp] = [close, volume]
    return ValidatedRows(dict(sorted(values.items())), ignored)


def chunk_envelope(chunk: Chunk, body: bytes, rows: ValidatedRows, attempts: int) -> dict:
    return {
        "schema": SCHEMA, "request": chunk.request(), "fetched_at_utc": now_utc(),
        "attempts": attempts, "response": {"status_code": 200, "body_bytes": len(body),
            "body_sha256": sha256(body), "body_utf8": body.decode("utf-8")},
        "validation": {"rows_retained": len(rows.values), "rows_before_start_ignored": rows.ignored_before_start},
    }


def load_chunk(path: Path, chunk: Chunk) -> ValidatedRows:
    try:
        envelope = json.loads(path.read_bytes())
        if envelope["schema"] != SCHEMA or envelope["request"] != chunk.request():
            raise ValidationError("cached_request_mismatch")
        response = envelope["response"]
        body = response["body_utf8"].encode("utf-8")
        if (response["status_code"] != 200 or response["body_bytes"] != len(body)
                or response["body_sha256"] != sha256(body)):
            raise ValidationError("cached_body_hash_or_status_mismatch")
        rows = validate_body(body, chunk)
        if envelope["validation"] != {"rows_retained": len(rows.values), "rows_before_start_ignored": rows.ignored_before_start}:
            raise ValidationError("cached_validation_mismatch")
        return rows
    except ValidationError:
        raise
    except (OSError, KeyError, TypeError, ValueError, AttributeError) as exc:
        raise ValidationError("cached_chunk_malformed") from exc


def intervals(hours: list[int], granularity: int) -> list[list[int]]:
    """Compact a sorted hour list into inclusive-start/exclusive-end intervals."""
    result: list[list[int]] = []
    for hour in hours:
        if result and result[-1][1] == hour:
            result[-1][1] = hour + granularity
        else:
            result.append([hour, hour + granularity])
    return result


def snapshot(cache: Path, plan: Plan, chunks: list[Chunk], loaded: dict[str, ValidatedRows],
             *, requests_run: int, reused_chunks: int, stop_reason: str) -> dict:
    """Rebuild normalized files exclusively from all validated planned chunks."""
    per_coin: dict[str, dict] = {}
    hashes: dict[str, str] = {}
    for coin in plan.coins:
        coin_chunks = [chunk for chunk in chunks if chunk.coin == coin]
        acquired = [chunk for chunk in coin_chunks if chunk.relative_path in loaded]
        values: dict[int, list[float]] = {}
        missing: list[int] = []
        for chunk in acquired:
            rows = loaded[chunk.relative_path].values
            values.update(rows)
            missing.extend(hour for hour in range(chunk.start, chunk.end, plan.granularity) if hour not in rows)
            hashes[chunk.relative_path] = sha256((cache / chunk.relative_path).read_bytes())
        # wide_coins consumes Unix HOURS, while the service/raw envelopes use
        # Unix seconds. Keep that conversion explicit at this single boundary.
        normalized = json_bytes({str(timestamp // plan.granularity): value for timestamp, value in sorted(values.items())})
        name = f"{coin}.json"
        atomic_write(cache / name, normalized)
        hashes[name] = sha256(normalized)
        requested = sum((chunk.end - chunk.start) // plan.granularity for chunk in acquired)
        planned = (plan.end - plan.start) // plan.granularity
        per_coin[coin] = {
            "status": "complete" if len(acquired) == len(coin_chunks) else "partial",
            "planned_chunks": len(coin_chunks), "validated_chunks": len(acquired),
            "planned_hours": planned, "validated_requested_hours": requested,
            "unrequested_hours": planned - requested, "observed_hours": len(values),
            "missing_requested_hours": len(missing),
            "missing_requested_intervals": intervals(sorted(missing), plan.granularity),
            "missing_hour_intervals": [[start // plan.granularity, end // plan.granularity]
                for start, end in intervals(sorted(missing), plan.granularity)],
            "interval_timestamp_unit": "unix_seconds",
            "unrequested_intervals": intervals(sorted(hour for chunk in coin_chunks
                if chunk.relative_path not in loaded
                for hour in range(chunk.start, chunk.end, plan.granularity)), plan.granularity),
            "rows_before_start_ignored": sum(loaded[chunk.relative_path].ignored_before_start for chunk in acquired),
            "normalized_path": name,
            "file": name, "sha256": hashes[name], "rows": len(values),
            "missing_hours": len(missing), "planned_requests": len(coin_chunks),
            "completed_requests": len(acquired),
        }
    complete = len(loaded) == len(chunks)
    hashes["cache_metadata.json"] = sha256((cache / "cache_metadata.json").read_bytes())
    manifest = {
        **plan.descriptor(), "status": "complete" if complete else "partial",
        "start_hour": plan.start // plan.granularity, "end_hour_exclusive": plan.end // plan.granularity,
        "start_timestamp": plan.start, "end_timestamp_exclusive": plan.end,
        "requested_coins": list(plan.coins), "coins": per_coin,
        "analysis_ready": complete, "snapshot_at_utc": now_utc(),
        "planned_chunks": len(chunks), "validated_chunks": len(loaded),
        "planned_requests": len(chunks), "completed_requests": len(loaded),
        "http_requests_this_run": requests_run, "reused_chunks_this_run": reused_chunks,
        "stop_reason": stop_reason, "per_coin": per_coin, "sha256": dict(sorted(hashes.items())),
        "coverage_warning": "Complete acquisition does not guarantee uninterrupted candles; absent hours are never synthesized.",
        "normalized_key_unit": "unix_hours",
    }
    atomic_write(cache / "cache_manifest.json", json_bytes(manifest))
    atomic_write(cache / "manifest.json", json_bytes(manifest))
    if complete:
        atomic_write(cache / "analysis_manifest.json", json_bytes(manifest))
    else:
        (cache / "analysis_manifest.json").unlink(missing_ok=True)
    return manifest


Fetch = Callable[[str, dict], tuple[int, bytes]]


def run_cache(cache: Path, *, max_requests: int | None = None, fetch: Fetch,
              plan: Plan = Plan(), sleep: Callable[[float], None] = time.sleep,
              monotonic: Callable[[], float] = time.monotonic,
              emit: Callable[[str], None] = print) -> dict:
    """Acquire fixed chunks; injectable fetch/clock permit fully offline tests."""
    if max_requests is not None and max_requests < 1:
        raise ValueError("max_requests_must_be_positive")
    chunks = plan.chunks()
    cache.mkdir(parents=True, exist_ok=True)
    with (cache / ".cache.lock").open("a") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise CacheError("another_cache_writer_is_running") from exc
        # A readiness file from an earlier run is withdrawn until all raw
        # chunks and hashes have been checked again under this writer lock.
        (cache / "analysis_manifest.json").unlink(missing_ok=True)
        (cache / "manifest.json").unlink(missing_ok=True)
        (cache / "cache_manifest.json").unlink(missing_ok=True)
        metadata = cache / "cache_metadata.json"
        if metadata.exists():
            try:
                if json.loads(metadata.read_bytes()) != plan.descriptor():
                    raise ValidationError("cache_plan_mismatch")
            except (OSError, ValueError) as exc:
                raise ValidationError("cache_metadata_malformed") from exc
        else:
            atomic_write(metadata, json_bytes(plan.descriptor()))
        loaded: dict[str, ValidatedRows] = {}
        for chunk in chunks:
            path = cache / chunk.relative_path
            if path.exists():
                loaded[chunk.relative_path] = load_chunk(path, chunk)
        reused = len(loaded)
        requests_run = 0
        last_request_started: float | None = None
        stop_reason = "all_planned_chunks_validated"
        error: BaseException | None = None
        last_coin: str | None = None
        try:
            for chunk in chunks:
                if chunk.relative_path in loaded:
                    continue
                if last_coin is not None and chunk.coin != last_coin:
                    emit(f"coin={last_coin} validated_chunks={sum(c.coin == last_coin and c.relative_path in loaded for c in chunks)} http_requests_run={requests_run}")
                last_coin = chunk.coin
                for attempt in range(1, MAX_RETRIES + 2):
                    if max_requests is not None and requests_run >= max_requests:
                        raise PilotLimitReached
                    if last_request_started is not None:
                        delay = MIN_REQUEST_SPACING - (monotonic() - last_request_started)
                        if delay > 0:
                            sleep(delay)
                    last_request_started = monotonic()
                    requests_run += 1
                    status: int | None = None
                    body: bytes | None = None
                    try:
                        request = chunk.request()
                        status, body = fetch(request["url"], request["params"])
                        if status != 200:
                            raise DownloadError(f"http_status_{status}")
                        rows = validate_body(body, chunk)
                        atomic_write(cache / chunk.relative_path, json_bytes(chunk_envelope(chunk, body, rows, attempt)))
                        loaded[chunk.relative_path] = rows
                        if requests_run % 25 == 0:
                            emit(f"coin={chunk.coin} http_requests_run={requests_run} validated_chunks={len(loaded)}/{len(chunks)}")
                        break
                    except (OSError, DownloadError, ValidationError) as exc:
                        failure = {"schema": SCHEMA, "request": chunk.request(), "attempt": attempt,
                            "recorded_at_utc": now_utc(), "error": str(exc) if isinstance(exc, CacheError) else type(exc).__name__,
                            "response": None if body is None else {"status_code": status, "body_bytes": len(body),
                                "body_sha256": sha256(body), "body_utf8": body.decode("utf-8", errors="replace")}}
                        # Failed/non-UTF8 responses also carry exact original bytes.
                        if body is not None:
                            import base64
                            failure["response"]["body_base64"] = base64.b64encode(body).decode("ascii")
                        failure_name = f"failures/{chunk.coin}/{chunk.start}-{chunk.end}-request-{time.time_ns()}.json"
                        atomic_write(cache / failure_name, json_bytes(failure))
                        if attempt > MAX_RETRIES:
                            raise DownloadError(f"chunk_failed_after_{attempt}_attempts:{chunk.coin}:{chunk.start}") from exc
                        sleep(0.5 * attempt)
        except PilotLimitReached:
            stop_reason = "pilot_request_limit_reached"
        except KeyboardInterrupt as exc:
            stop_reason, error = "interrupted", exc
        except BaseException as exc:
            stop_reason, error = "download_failed", exc
        if last_coin is not None:
            emit(f"coin={last_coin} validated_chunks={sum(c.coin == last_coin and c.relative_path in loaded for c in chunks)} http_requests_run={requests_run}")
        manifest = snapshot(cache, plan, chunks, loaded, requests_run=requests_run,
                            reused_chunks=reused, stop_reason=stop_reason)
        emit(f"status={manifest['status']} validated_chunks={len(loaded)}/{len(chunks)} http_requests_run={requests_run} reused_chunks={reused}")
        if error is not None:
            raise error
        return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cache", type=Path, required=True)
    parser.add_argument("--max-requests", type=int, default=None, help="Bound total HTTP attempts, including retries; incomplete pilots cannot be analysis-ready.")
    args = parser.parse_args()
    if args.max_requests is not None and args.max_requests < 1:
        parser.error("--max-requests must be positive")
    import httpx
    try:
        with httpx.Client(timeout=20.0, follow_redirects=False, trust_env=False,
                          headers={"User-Agent": "Continuations-bounded-historical-research/1.0"}) as client:
            def fetch(url: str, params: dict) -> tuple[int, bytes]:
                try:
                    response = client.get(url, params=params)
                except httpx.HTTPError as exc:
                    # No body, URL, key, or environment values in exception output.
                    raise DownloadError(type(exc).__name__) from exc
                return response.status_code, response.content
            run_cache(args.cache, max_requests=args.max_requests, fetch=fetch)
    except KeyboardInterrupt:
        print("stopped=interrupted; cache remains partial unless every planned chunk was already validated")
        return 130
    except (CacheError, OSError, ValueError) as exc:
        print(f"stopped={type(exc).__name__}:{str(exc) if isinstance(exc, CacheError) else 'local_error'}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
