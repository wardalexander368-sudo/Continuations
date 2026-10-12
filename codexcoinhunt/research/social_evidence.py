#!/usr/bin/env python3
"""Conservative offline join of social coverage, promotion and buyer clocks."""
import argparse
import datetime as dt
import json
from pathlib import Path
import re

MINT = "2j5SaS7xy776qCBpyPQbZjyQSAtKiFgrwjfErthnW2ZM"
POOL = "Fe7bpDYCs74GqiCUF14HwgUMToPKV1d9mDYVX5BTohFr"
CHAIN = "solana"


def parse_time(value):
    if isinstance(value, (int, float)):
        value = value / 1000 if value > 10_000_000_000 else value
        return dt.datetime.fromtimestamp(value, tz=dt.timezone.utc)
    if not isinstance(value, str):
        raise ValueError("timestamp must be text or epoch")
    parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("timestamp must include an offset")
    return parsed.astimezone(dt.timezone.utc)


def iso(value):
    return value.astimezone(dt.timezone.utc).isoformat()


def normalize_text(value):
    if not isinstance(value, str):
        return ""
    return " ".join(re.sub(r"[^a-z0-9]+", " ", value.lower()).split())


def mentions_exact_mint(text, links=()):
    haystack = " ".join([text or "", *[str(link) for link in links]])
    return MINT in haystack


def post_rows(records):
    by_uri = {}
    for record in records:
        response = record.get("response")
        if record.get("error") is not None or not isinstance(response, dict):
            continue
        for post in response.get("posts", []):
            if not isinstance(post, dict) or not isinstance(post.get("uri"), str):
                continue
            author = post.get("author") if isinstance(post.get("author"), dict) else {}
            value = post.get("record") if isinstance(post.get("record"), dict) else {}
            text = value.get("text") if isinstance(value.get("text"), str) else ""
            facets = value.get("facets") if isinstance(value.get("facets"), list) else []
            links = []
            for facet in facets:
                for feature in facet.get("features", []) if isinstance(facet, dict) else []:
                    if isinstance(feature, dict) and isinstance(feature.get("uri"), str):
                        links.append(feature["uri"])
            row = {
                "uri": post["uri"], "author_did": author.get("did"), "text": text,
                "normalized_text": normalize_text(text), "links": sorted(set(links)),
                "created_at_utc": value.get("createdAt"), "indexed_at_utc": post.get("indexedAt"),
                "received_at_utc": record.get("received_at_utc"),
                "exact_mint_mentioned": mentions_exact_mint(text, links),
                "name_only_family_match": "claudia" in normalize_text(text) and not mentions_exact_mint(text, links),
            }
            by_uri[post["uri"]] = row
    return [by_uri[key] for key in sorted(by_uri)]


def author_copy_clusters(posts):
    """Union posts by same DID or exact normalized text; returns descriptive clusters."""
    parents = list(range(len(posts)))
    def find(i):
        while parents[i] != i:
            parents[i] = parents[parents[i]]
            i = parents[i]
        return i
    def union(a, b):
        a, b = find(a), find(b)
        if a != b:
            parents[b] = a
    for i, left in enumerate(posts):
        for j in range(i):
            right = posts[j]
            same_author = left.get("author_did") and left.get("author_did") == right.get("author_did")
            same_copy = left.get("normalized_text") and left.get("normalized_text") == right.get("normalized_text")
            if same_author or same_copy:
                union(i, j)
    groups = {}
    for index, post in enumerate(posts):
        groups.setdefault(find(index), []).append(post)
    return list(groups.values())


def exact_identity_order(item):
    return isinstance(item, dict) and item.get("chainId") == CHAIN and item.get("tokenAddress") == MINT


def read_jsonl(path):
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def dex_context(records):
    by_id = {row.get("request_id"): row for row in records}
    pair_record = by_id.get("exact_token_pairs", {})
    pairs = pair_record.get("response") if isinstance(pair_record.get("response"), list) else []
    exact_pairs = [p for p in pairs if isinstance(p, dict) and p.get("chainId") == CHAIN and (p.get("baseToken") or {}).get("address") == MINT]
    canonical = [p for p in exact_pairs if p.get("pairAddress") == POOL]
    urls = set()
    positives = 0
    for pair in exact_pairs:
        if ((pair.get("boosts") or {}).get("active") or 0) > 0:
            positives += 1
        info = pair.get("info") if isinstance(pair.get("info"), dict) else {}
        for item in [*info.get("websites", []), *info.get("socials", [])]:
            if isinstance(item, dict) and isinstance(item.get("url"), str):
                urls.add(item["url"])
    def target_rows(request_id):
        response = by_id.get(request_id, {}).get("response")
        if not isinstance(response, list): return 0
        return sum(exact_identity_order(item) for item in response)
    return {
        "exact_pair_response_at_utc": pair_record.get("received_at_utc"),
        "exact_mint_pair_rows": len(exact_pairs), "canonical_pair_rows": len(canonical),
        "top_list_target_rows": target_rows("top_boosts"),
        "latest_list_target_rows": target_rows("latest_boosts"),
        "bounded_list_absence_proves_no_boost": False,
        "positive_active_boost_pair_rows": positives,
        "deduplicated_profile_urls": sorted(urls),
        "top_list_target_received_at_utc": by_id.get("top_boosts", {}).get("received_at_utc"),
        "latest_list_target_received_at_utc": by_id.get("latest_boosts", {}).get("received_at_utc"),
    }


def historical_snapshots(root):
    rows = []
    for path in sorted(root.glob("results/quote_probe_20261012_pass*/dex_evidence.json")):
        for request in json.loads(path.read_text()):
            body = request.get("response_body") if isinstance(request.get("response_body"), dict) else {}
            pairs = body.get("pairs") if isinstance(body.get("pairs"), list) else []
            for pair in pairs:
                if pair.get("chainId") == CHAIN and pair.get("pairAddress") == POOL and (pair.get("baseToken") or {}).get("address") == MINT:
                    active = (pair.get("boosts") or {}).get("active")
                    if isinstance(active, (int, float)):
                        rows.append({"evidence": str(path.relative_to(root)), "received_at_utc": request.get("received_at_utc"), "active_boosts": active})
    return rows


def buy_events(root):
    rows = []
    for row in read_jsonl(root / "data/buyer_probe_20261012/events.jsonl"):
        if row.get("side") == "B" and row.get("mint") == MINT and row.get("pool") == POOL:
            rows.append(row)
    return rows


def analyze(root, data):
    social_records = read_jsonl(data / "raw.jsonl")
    posts = post_rows(social_records)
    clusters = author_copy_clusters(posts)
    successful = sum(row.get("error") is None and isinstance(row.get("response"), dict) for row in social_records)
    issues = [{"query_id": row.get("query_id"), "reason": "source_response_unavailable", "http_status": row.get("http_status"), "received_at_utc": row.get("received_at_utc")} for row in social_records if row.get("error") is not None]
    exact_clusters = sum(any(post["exact_mint_mentioned"] for post in group) for group in clusters)
    family_clusters = sum(any(post["name_only_family_match"] for post in group) for group in clusters)
    paid_record = json.loads((data / "raw_paid_order.json").read_text())
    response = paid_record.get("response") if isinstance(paid_record.get("response"), dict) else {}
    orders = [dict(item, payment_at_utc=iso(parse_time(item["paymentTimestamp"]))) for item in response.get("orders", []) if exact_identity_order(item)]
    boosts = [dict(item, payment_at_utc=iso(parse_time(item["paymentTimestamp"]))) for item in response.get("boosts", []) if exact_identity_order(item)]
    snapshots = historical_snapshots(root)
    buys = buy_events(root)
    first_buy = min((parse_time(row["event_unix_time"]) for row in buys), default=None)
    latest_active = max((parse_time(row["received_at_utc"]) for row in snapshots if row["active_boosts"] > 0), default=None)
    latest_payment = max((parse_time(row["paymentTimestamp"]) for row in boosts), default=None)
    paid_confounder = bool(boosts and latest_active and first_buy and latest_active < first_buy)
    direct = dex_context(read_jsonl(data / "raw_dex.jsonl"))
    return posts, {
        "id": "SOCIAL-COVERAGE-0.1-AUDIT", "completed_at_utc": iso(dt.datetime.now(dt.timezone.utc)),
        "exact_identity": {"chain": CHAIN, "mint": MINT, "pool": POOL, "name": "Claudia", "symbol": "CLAUDIA"},
        "social_search": {
            "planned_queries": 3, "completed_responses": len(social_records), "successful_responses": successful,
            "source_status": "available" if successful else "unavailable", "unique_posts": len(posts),
            "unique_author_dids": len({p["author_did"] for p in posts if p.get("author_did")}),
            "descriptive_author_copy_clusters": len(clusters), "descriptive_meme_family_clusters": family_clusters,
            "descriptive_exact_mint_clusters": exact_clusters,
            "descriptive_mint_agreement_fraction": (exact_clusters / len(clusters)) if clusters else None,
            "history_complete": False, "decision_time_available": False, "zero_results_proves_quiet": False,
            "community_clusters_verified": 0, "issues": issues,
        },
        "paid_visibility": {
            "exact_paid_endpoint": {"available": paid_record.get("error") is None, "received_at_utc": paid_record.get("received_at_utc"), "orders": orders, "boosts": boosts},
            "direct_current_context": direct, "pre_buy_active_snapshots": snapshots,
            "first_sample_buy_at_utc": iso(first_buy) if first_buy else None,
            "last_active_snapshot_to_first_buy_seconds": (first_buy - latest_active).total_seconds() if first_buy and latest_active else None,
            "latest_boost_payment_to_first_buy_seconds": (first_buy - latest_payment).total_seconds() if first_buy and latest_payment else None,
            "paid_visibility_confounder_verified": paid_confounder, "paid_only_push_verified": False,
            "boost_caused_buys_verified": False, "bounded_list_absence_proves_no_boost": False,
        },
        "interpretation": {
            "organic_attention_verified": False, "historical_slr_eligibility_promoted": False,
            "attention_control_available": False, "same_five_development_buys_not_new_opportunities": len(buys),
            "opportunity_frequency_estimate": None, "closed_strategy_positions_added": 0,
            "matched_net_account_comparisons_added": 0, "recoverable_usd_profit_outcomes_added": 0,
            "doubling_campaigns_added": 0,
            "note": "Paid-visibility chronology disqualifies this sample as evidence of independently verified organic attention. It does not establish causation or profitability."
        }
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists() and any(args.output.iterdir()):
        raise SystemExit("refusing to overwrite analysis output")
    args.output.mkdir(parents=True, exist_ok=True)
    root = Path(__file__).resolve().parent
    posts, summary = analyze(root, args.data)
    (args.output / "posts.jsonl").write_text("".join(json.dumps(row, separators=(",", ":")) + "\n" for row in posts))
    (args.output / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
