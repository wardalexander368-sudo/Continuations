"""Offline acquisition tests; no service requests or project files are touched."""
import dataclasses
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

import importlib.util
import sys

_REPO_SCRIPT = Path(__file__).resolve().parents[1] / "handoff/experiments/edge-hunt/patterns/rebuild_capit_cache.py"
_SPEC = importlib.util.spec_from_file_location("rebuild_capit_cache", _REPO_SCRIPT)
assert _SPEC is not None and _SPEC.loader is not None
cache = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = cache  # dataclasses resolve annotations through this registry.
_SPEC.loader.exec_module(cache)


def body_at(hours, volume=1.0):
    return json.dumps([[hour, 9.0, 11.0, 10.0, 10.5, volume] for hour in hours]).encode()


class ChunkValidationTests(unittest.TestCase):
    def setUp(self):
        self.chunk = cache.Chunk("BTC", cache.START, cache.START + 3 * 3600)

    def test_unsorted_candles_and_documented_before_start_are_normalized(self):
        result = cache.validate_body(body_at([cache.START + 7200, cache.START - 3600, cache.START]), self.chunk)
        self.assertEqual(list(result.values), [cache.START, cache.START + 7200])
        self.assertEqual(result.ignored_before_start, 1)
        self.assertNotIn(cache.START + 3600, result.values)

    def test_duplicates_and_end_overrun_are_rejected(self):
        for timestamps in ([cache.START, cache.START], [self.chunk.end]):
            with self.subTest(timestamps=timestamps), self.assertRaises(cache.ValidationError):
                cache.validate_body(body_at(timestamps), self.chunk)

    def test_non_integer_misaligned_nonfinite_and_negative_volume_are_rejected(self):
        good = [cache.START, 9.0, 11.0, 10.0, 10.5, 1.0]
        bad = [
            [float(cache.START), *good[1:]], [True, *good[1:]], [cache.START + 1, *good[1:]],
            [cache.START, float("nan"), *good[2:]], [*good[:5], -1.0],
            [cache.START, 0, *good[2:]], [cache.START, 9, 10, 10, 10.5, 1],
        ]
        for row in bad:
            with self.subTest(row=row), self.assertRaises(cache.ValidationError):
                cache.validate_body(json.dumps([row]).encode(), self.chunk)

    def test_empty_response_is_valid_missing_history(self):
        result = cache.validate_body(b"[]", self.chunk)
        self.assertEqual(result.values, {})

    def test_default_plan_is_fixed_and_every_chunk_is_at_most_300_hours(self):
        plan = cache.Plan()
        self.assertEqual(cache.iso(plan.start), "2023-01-01T00:00:00Z")
        self.assertEqual(cache.iso(plan.end), "2026-10-10T00:00:00Z")
        self.assertEqual(plan.coins, ("BTC", "ETH", "SOL", "XRP", "DOGE", "ADA", "AVAX", "LINK", "LTC", "BCH", "DOT",
            "AAVE", "UNI", "SHIB", "CRV", "GRT", "XTZ", "BAT", "SUSHI", "YFI", "PEPE"))
        self.assertEqual(len(plan.chunks()), 2331)
        for coin in plan.coins:
            chunks = [chunk for chunk in plan.chunks() if chunk.coin == coin]
            self.assertEqual(chunks[0].start, plan.start)
            self.assertEqual(chunks[-1].end, plan.end)
            self.assertTrue(all((c.end - c.start) // 3600 <= 300 for c in chunks))
            self.assertTrue(all(left.end == right.start for left, right in zip(chunks, chunks[1:])))


class ResumeTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.plan = cache.Plan(coins=("BTC", "ETH"), start=cache.START, end=cache.START + 5 * 3600, max_rows=3)
        self.requests = []
        self.sleep_calls = []

    def fetch(self, url, params):
        self.requests.append((url, params))
        start = int(cache.dt.datetime.fromisoformat(params["start"].replace("Z", "+00:00")).timestamp())
        end = int(cache.dt.datetime.fromisoformat(params["end"].replace("Z", "+00:00")).timestamp())
        # Deliberately omit one requested hour; gaps must survive normalization.
        return 200, body_at([hour for hour in range(start, end + 1, 3600) if hour != cache.START + 3600])

    def acquire(self, **kwargs):
        return cache.run_cache(self.root, plan=self.plan, fetch=kwargs.pop("fetch", self.fetch),
            emit=lambda _: None, sleep=self.sleep_calls.append, monotonic=lambda: 0.0, **kwargs)

    def test_partial_pilot_has_no_analysis_manifest_and_resume_reuses_chunks(self):
        first = self.acquire(max_requests=1)
        self.assertEqual(first["status"], "partial")
        self.assertFalse(first["analysis_ready"])
        self.assertFalse((self.root / "analysis_manifest.json").exists())
        self.assertEqual(first["http_requests_this_run"], 1)
        self.assertEqual(first["start_hour"], cache.START // 3600)
        self.assertEqual(first["end_hour_exclusive"], self.plan.end // 3600)
        self.assertEqual(first["coins"]["BTC"]["file"], "BTC.json")
        btc = first["per_coin"]["BTC"]
        self.assertEqual(btc["validated_requested_hours"], 3)
        self.assertEqual(btc["missing_requested_hours"], 1)
        self.assertEqual(btc["unrequested_hours"], 2)
        first_chunk = self.root / self.plan.chunks()[0].relative_path
        original_bytes = first_chunk.read_bytes()
        second = self.acquire()
        self.assertEqual(second["status"], "complete")
        self.assertEqual(second["reused_chunks_this_run"], 1)
        self.assertEqual(second["http_requests_this_run"], 3)
        self.assertEqual(first_chunk.read_bytes(), original_bytes)
        self.assertTrue((self.root / "analysis_manifest.json").exists())
        normalized = json.loads((self.root / "BTC.json").read_bytes())
        self.assertNotIn(str(cache.START // 3600 + 1), normalized)
        self.assertEqual(len(normalized), 4)
        self.assertIn(str(cache.START // 3600), normalized)
        self.assertNotIn(str(cache.START), normalized)
        self.assertEqual(second["coins"]["BTC"]["rows"], 4)
        self.assertEqual(second["coins"]["BTC"]["sha256"], hashlib.sha256((self.root / "BTC.json").read_bytes()).hexdigest())
        self.assertEqual(second["per_coin"]["BTC"]["missing_requested_intervals"], [[cache.START + 3600, cache.START + 7200]])
        for name, digest in second["sha256"].items():
            self.assertEqual(hashlib.sha256((self.root / name).read_bytes()).hexdigest(), digest)
        self.assertFalse(list(self.root.rglob(".*.json.*")))

    def test_corrupt_cached_raw_body_fails_without_redownload_and_withdraws_readiness(self):
        self.acquire()
        path = self.root / self.plan.chunks()[0].relative_path
        envelope = json.loads(path.read_bytes())
        envelope["response"]["body_utf8"] += " "
        path.write_text(json.dumps(envelope))
        before = len(self.requests)
        with self.assertRaisesRegex(cache.ValidationError, "hash_or_status"):
            self.acquire()
        self.assertEqual(len(self.requests), before)
        self.assertFalse((self.root / "analysis_manifest.json").exists())
        self.assertFalse((self.root / "manifest.json").exists())

    def test_request_metadata_tampering_fails_without_network(self):
        self.acquire(max_requests=1)
        path = self.root / self.plan.chunks()[0].relative_path
        envelope = json.loads(path.read_bytes())
        envelope["request"]["product"] = "BTC-USDT"
        path.write_text(json.dumps(envelope))
        before = len(self.requests)
        with self.assertRaisesRegex(cache.ValidationError, "request_mismatch"):
            self.acquire()
        self.assertEqual(len(self.requests), before)

    def test_two_retries_then_error_preserves_partial_manifest_and_failure_bodies(self):
        attempts = []
        def failing(url, params):
            attempts.append((url, params))
            return 503, b'{"message":"unavailable"}'
        with self.assertRaisesRegex(cache.DownloadError, "after_3_attempts"):
            self.acquire(fetch=failing)
        self.assertEqual(len(attempts), 3)
        self.assertEqual(len(list(self.root.glob("failures/BTC/*.json"))), 3)
        manifest = json.loads((self.root / "cache_manifest.json").read_bytes())
        self.assertEqual(manifest["status"], "partial")
        self.assertEqual(manifest["validated_chunks"], 0)
        self.assertEqual(manifest["stop_reason"], "download_failed")
        self.assertFalse((self.root / "analysis_manifest.json").exists())

    def test_pilot_budget_counts_retry_attempts(self):
        attempts = []
        def transient(url, params):
            attempts.append((url, params))
            return 429, b'[]'
        manifest = self.acquire(max_requests=2, fetch=transient)
        self.assertEqual(len(attempts), 2)
        self.assertEqual(manifest["http_requests_this_run"], 2)
        self.assertEqual(manifest["status"], "partial")
        self.assertFalse(manifest["analysis_ready"])
        self.assertEqual(len(list(self.root.glob("failures/BTC/*.json"))), 2)

    def test_keyboard_interrupt_saves_partial_then_resume_avoids_prior_request(self):
        count = 0
        def interrupted(url, params):
            nonlocal count
            count += 1
            if count == 2:
                raise KeyboardInterrupt
            return self.fetch(url, params)
        with self.assertRaises(KeyboardInterrupt):
            self.acquire(fetch=interrupted)
        manifest = json.loads((self.root / "cache_manifest.json").read_bytes())
        self.assertEqual(manifest["validated_chunks"], 1)
        self.assertEqual(manifest["stop_reason"], "interrupted")
        result = self.acquire()
        self.assertEqual(result["reused_chunks_this_run"], 1)
        self.assertEqual(result["http_requests_this_run"], 3)

    def test_spacing_and_full_resume_no_requests(self):
        self.acquire()
        self.assertGreaterEqual(self.sleep_calls.count(cache.MIN_REQUEST_SPACING), 3)
        before = len(self.requests)
        result = self.acquire()
        self.assertEqual(len(self.requests), before)
        self.assertEqual(result["http_requests_this_run"], 0)
        self.assertEqual(result["reused_chunks_this_run"], 4)

    def test_conflicting_plan_fails_without_fetch(self):
        self.acquire(max_requests=1)
        changed = dataclasses.replace(self.plan, end=self.plan.end + 3600)
        before = len(self.requests)
        with self.assertRaisesRegex(cache.ValidationError, "plan_mismatch"):
            cache.run_cache(self.root, plan=changed, fetch=self.fetch, emit=lambda _: None)
        self.assertEqual(len(self.requests), before)


if __name__ == "__main__":
    unittest.main()
