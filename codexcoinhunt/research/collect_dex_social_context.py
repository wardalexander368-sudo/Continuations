#!/usr/bin/env python3
"""Collect three bounded, unauthenticated DEX context responses."""
import argparse
import datetime as dt
import json
from pathlib import Path
import urllib.error
import urllib.request

MINT = "2j5SaS7xy776qCBpyPQbZjyQSAtKiFgrwjfErthnW2ZM"
REQUESTS = [
    ("exact_token_pairs", f"https://api.dexscreener.com/token-pairs/v1/solana/{MINT}"),
    ("top_boosts", "https://api.dexscreener.com/token-boosts/top/v1"),
    ("latest_boosts", "https://api.dexscreener.com/token-boosts/latest/v1"),
]


def now():
    return dt.datetime.now(dt.timezone.utc).isoformat()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", type=Path, required=True)
    args = parser.parse_args()
    raw_path = args.data / "raw_dex.jsonl"
    summary_path = args.data / "dex_collection_summary.json"
    if raw_path.exists() or summary_path.exists():
        raise SystemExit("refusing to overwrite DEX context evidence")
    records = []
    for request_id, url in REQUESTS:
        requested = now()
        status = None
        response = None
        error = None
        try:
            request = urllib.request.Request(url, headers={"Accept": "application/json", "User-Agent": "ResolantResearch/0.1"})
            with urllib.request.urlopen(request, timeout=10) as handle:
                status = handle.status
                response = json.loads(handle.read().decode("utf-8", errors="replace"))
        except urllib.error.HTTPError as exc:
            status = exc.code
            error = {"type": "HTTPError", "message": str(exc), "body": exc.read().decode("utf-8", errors="replace")}
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            error = {"type": type(exc).__name__, "message": str(exc)}
        records.append({"request_id": request_id, "requested_at_utc": requested, "received_at_utc": now(), "url": url, "http_status": status, "response": response, "error": error})
    raw_path.write_text("".join(json.dumps(row, separators=(",", ":")) + "\n" for row in records))
    summary = {"completed_at_utc": now(), "planned_requests": 3, "completed_requests": len(records), "successful_responses": sum(r["error"] is None for r in records), "error_responses": sum(r["error"] is not None for r in records), "paid_data_usd": 0, "authentication_used": False, "orders_or_wallet_actions": 0}
    summary_path.write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
