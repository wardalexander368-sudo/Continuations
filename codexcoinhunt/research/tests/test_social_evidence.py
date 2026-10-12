"""Social/promotion evidence invariants; synthetic fixtures are not return evidence."""
import json
from pathlib import Path
import tempfile
import unittest

from social_evidence import (MINT, POOL, author_copy_clusters, buy_events, dex_context,
                             exact_identity_order, historical_snapshots, mentions_exact_mint,
                             normalize_text, parse_time, post_rows)


class SocialEvidenceTests(unittest.TestCase):
    def response(self, posts=None, error=None, query="q"):
        return {"query_id": query, "received_at_utc": "2026-10-12T10:00:00Z",
                "http_status": 200 if error is None else 403,
                "response": {"posts": posts or []} if error is None else None, "error": error}

    def post(self, uri, did, text, links=()):
        facets = [{"features": [{"uri": link} for link in links]}] if links else []
        return {"uri": uri, "author": {"did": did}, "record": {"text": text,
                "createdAt": "2026-10-12T09:00:00Z", "facets": facets},
                "indexedAt": "2026-10-12T09:00:01Z"}

    def test_timestamp_and_normalization_are_strict(self):
        self.assertEqual(parse_time("2026-10-12T00:00:00Z").isoformat(), "2026-10-12T00:00:00+00:00")
        with self.assertRaises(ValueError): parse_time("2026-10-12T00:00:00")
        self.assertEqual(normalize_text("  CLAUDIA!!  Solana "), "claudia solana")

    def test_exact_mint_in_text_or_link(self):
        self.assertTrue(mentions_exact_mint("buy " + MINT))
        self.assertTrue(mentions_exact_mint("Claudia", ["https://x/" + MINT]))
        self.assertFalse(mentions_exact_mint("CLAUDIA Solana"))

    def test_uri_deduplication_merges_queries(self):
        old = self.post("at://same", "did:a", "old")
        new = self.post("at://same", "did:a", MINT)
        rows = post_rows([self.response([old], query="one"), self.response([new], query="two")])
        self.assertEqual(len(rows), 1); self.assertTrue(rows[0]["exact_mint_mentioned"])

    def test_source_errors_create_no_posts(self):
        rows = post_rows([self.response(error={"type": "HTTPError"})])
        self.assertEqual(rows, [])

    def test_name_only_is_family_not_exact_address(self):
        row = post_rows([self.response([self.post("at://1", "did:a", "CLAUDIA Solana")])])[0]
        self.assertTrue(row["name_only_family_match"]); self.assertFalse(row["exact_mint_mentioned"])

    def test_same_author_posts_are_one_cluster(self):
        posts = post_rows([self.response([self.post("at://1", "did:a", "one"), self.post("at://2", "did:a", "two")])])
        self.assertEqual(len(author_copy_clusters(posts)), 1)

    def test_exact_copy_across_authors_is_one_cluster(self):
        posts = post_rows([self.response([self.post("at://1", "did:a", "Same!"), self.post("at://2", "did:b", "same")])])
        self.assertEqual(len(author_copy_clusters(posts)), 1)

    def test_distinct_authors_and_text_remain_distinct(self):
        posts = post_rows([self.response([self.post("at://1", "did:a", "one"), self.post("at://2", "did:b", "two")])])
        self.assertEqual(len(author_copy_clusters(posts)), 2)

    def test_paid_order_requires_exact_chain_and_mint(self):
        self.assertTrue(exact_identity_order({"chainId": "solana", "tokenAddress": MINT}))
        self.assertFalse(exact_identity_order({"chainId": "ethereum", "tokenAddress": MINT}))
        self.assertFalse(exact_identity_order({"chainId": "solana", "tokenAddress": "other"}))

    def test_dex_pairs_do_not_become_attention_observations(self):
        pair = {"chainId": "solana", "pairAddress": POOL, "baseToken": {"address": MINT}, "boosts": {"active": 10}}
        result = dex_context([{"request_id": "exact_token_pairs", "received_at_utc": "now", "response": [pair, dict(pair)]}])
        self.assertEqual(result["exact_mint_pair_rows"], 2)
        self.assertEqual(result["canonical_pair_rows"], 2)

    def test_profile_urls_are_deduplicated(self):
        pair = {"chainId": "solana", "pairAddress": POOL, "baseToken": {"address": MINT},
                "info": {"websites": [{"url": "https://project"}], "socials": [{"url": "https://project"}]}}
        result = dex_context([{"request_id": "exact_token_pairs", "response": [pair]}])
        self.assertEqual(result["deduplicated_profile_urls"], ["https://project"])

    def test_bounded_list_absence_never_proves_no_boost(self):
        result = dex_context([{"request_id": "top_boosts", "response": []}, {"request_id": "latest_boosts", "response": []}])
        self.assertFalse(result["bounded_list_absence_proves_no_boost"])

    def test_top_list_exact_identity_not_name(self):
        result = dex_context([{"request_id": "top_boosts", "response": [
            {"chainId": "solana", "tokenAddress": MINT}, {"chainId": "solana", "tokenAddress": "other", "description": "Claudia"}]}])
        self.assertEqual(result["top_list_target_rows"], 1)

    def test_historical_snapshot_requires_exact_pair_and_mint(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); path = root / "results/quote_probe_20261012_pass1"; path.mkdir(parents=True)
            body = [{"received_at_utc": "2026-10-12T01:00:00Z", "response_body": {"pairs": [
                {"chainId": "solana", "pairAddress": POOL, "baseToken": {"address": MINT}, "boosts": {"active": 10}},
                {"chainId": "solana", "pairAddress": POOL, "baseToken": {"address": "other"}, "boosts": {"active": 99}}]}}]
            (path / "dex_evidence.json").write_text(json.dumps(body))
            rows = historical_snapshots(root)
            self.assertEqual([r["active_boosts"] for r in rows], [10])

    def test_buyer_chronology_requires_exact_identity(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); path = root / "data/buyer_probe_20261012"; path.mkdir(parents=True)
            rows = [{"side": "B", "mint": MINT, "pool": POOL}, {"side": "B", "mint": "other", "pool": POOL}, {"side": "S", "mint": MINT, "pool": POOL}]
            (path / "events.jsonl").write_text("".join(json.dumps(x) + "\n" for x in rows))
            self.assertEqual(len(buy_events(root)), 1)


if __name__ == "__main__":
    unittest.main()
