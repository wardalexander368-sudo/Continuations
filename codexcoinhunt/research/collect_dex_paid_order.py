#!/usr/bin/env python3
"""Collect one exact-token paid-order response; no order endpoint is invoked."""
import argparse
import datetime as dt
import json
from pathlib import Path
import urllib.error
import urllib.request


def now():
    return dt.datetime.now(dt.timezone.utc).isoformat()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", type=Path, required=True)
    args = parser.parse_args()
    raw_path = args.data / "raw_paid_order.json"
    summary_path = args.data / "paid_order_summary.json"
    if raw_path.exists() or summary_path.exists():
        raise SystemExit("refusing to overwrite paid-order evidence")
    plan = json.loads((args.data / "paid_order_plan.json").read_text())
    requested = now()
    status = None
    response = None
    error = None
    try:
        request = urllib.request.Request(plan["endpoint"], headers={"Accept": "application/json", "User-Agent": "ResolantResearch/0.1"})
        with urllib.request.urlopen(request, timeout=10) as handle:
            status = handle.status
            response = json.loads(handle.read().decode("utf-8", errors="replace"))
    except urllib.error.HTTPError as exc:
        status = exc.code
        error = {"type": "HTTPError", "message": str(exc), "body": exc.read().decode("utf-8", errors="replace")}
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        error = {"type": type(exc).__name__, "message": str(exc)}
    record = {"requested_at_utc": requested, "received_at_utc": now(), "url": plan["endpoint"], "http_status": status, "response": response, "error": error}
    raw_path.write_text(json.dumps(record, indent=2) + "\n")
    summary = {"completed_at_utc": now(), "successful_responses": int(error is None), "error_responses": int(error is not None), "paid_data_usd": 0, "authentication_used": False, "orders_or_wallet_actions": 0}
    summary_path.write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
