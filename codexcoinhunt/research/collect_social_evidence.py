#!/usr/bin/env python3
"""Bounded, read-only public social collector with explicit failure records."""
import argparse
import datetime as dt
import json
from pathlib import Path
import urllib.error
import urllib.parse
import urllib.request


def now():
    return dt.datetime.now(dt.timezone.utc).isoformat()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", type=Path, required=True)
    args = parser.parse_args()
    plan = json.loads((args.data / "plan.json").read_text())
    raw_path = args.data / "raw.jsonl"
    summary_path = args.data / "collection_summary.json"
    if raw_path.exists() or summary_path.exists():
        raise SystemExit("refusing to overwrite social evidence")
    records = []
    consecutive_errors = 0
    stopped = None
    for query in plan["queries"]:
        cursor = None
        for page in range(plan["bounds"]["maximum_pages_per_query"]):
            parameters = {
                "q": query["q"], "sort": "latest", "since": plan["interval"]["since"],
                "until": plan["interval"]["until"], "limit": plan["bounds"]["limit_per_page"],
            }
            if cursor:
                parameters["cursor"] = cursor
            url = plan["source"] + "?" + urllib.parse.urlencode(parameters)
            requested = now()
            status = None
            response = None
            error = None
            try:
                request = urllib.request.Request(url, headers={"Accept": "application/json", "User-Agent": "ResolantResearch/0.1"})
                with urllib.request.urlopen(request, timeout=plan["bounds"]["timeout_seconds"]) as handle:
                    status = handle.status
                    body = handle.read().decode("utf-8", errors="replace")
                    response = json.loads(body)
                consecutive_errors = 0
            except urllib.error.HTTPError as exc:
                status = exc.code
                error = {"type": "HTTPError", "message": str(exc), "body": exc.read().decode("utf-8", errors="replace")}
                consecutive_errors += 1
            except (OSError, ValueError, json.JSONDecodeError) as exc:
                error = {"type": type(exc).__name__, "message": str(exc)}
                consecutive_errors += 1
            record = {
                "query_id": query["id"], "query": query["q"], "page": page + 1,
                "requested_at_utc": requested, "received_at_utc": now(), "url": url,
                "http_status": status, "response": response, "error": error,
            }
            records.append(record)
            if error:
                break
            cursor = response.get("cursor") if isinstance(response, dict) else None
            if not cursor:
                break
        if consecutive_errors >= plan["bounds"]["maximum_consecutive_errors"]:
            stopped = "maximum_consecutive_errors"
            break
    raw_path.write_text("".join(json.dumps(row, separators=(",", ":")) + "\n" for row in records))
    summary = {
        "completed_at_utc": now(), "planned_queries": len(plan["queries"]),
        "completed_responses": len(records),
        "successful_responses": sum(row["error"] is None for row in records),
        "error_responses": sum(row["error"] is not None for row in records),
        "stop_reason": stopped, "paid_data_usd": 0, "authentication_used": False,
        "orders_or_wallet_actions": 0,
    }
    summary_path.write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
