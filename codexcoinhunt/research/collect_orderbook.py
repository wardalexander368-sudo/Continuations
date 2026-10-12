#!/usr/bin/env python3
"""Bounded public Alpaca REST capture; paper research only, no credentials/orders."""
import argparse
import concurrent.futures
import datetime as dt
import json
import pathlib
import time
import urllib.error
import urllib.parse
import urllib.request


def utc():
    return dt.datetime.now(dt.timezone.utc).isoformat()


def get_record(url, cycle, kind):
    record = {"cycle": cycle, "kind": kind, "url": url, "requested_at_utc": utc()}
    try:
        request = urllib.request.Request(url, headers={"User-Agent": "ResolantPaperResearch/0.3"})
        with urllib.request.urlopen(request, timeout=20) as response:
            raw = response.read()
            record.update(http_status=response.status, headers=dict(response.headers), body=json.loads(raw))
    except Exception as error:
        record.update(http_status=getattr(error, "code", None), error=type(error).__name__, message=str(error))
        if isinstance(error, urllib.error.HTTPError):
            record["error_response"] = error.read().decode(errors="replace")
    record["received_at_utc"] = utc()
    return record


def collect(output, minutes, interval, config_path):
    output.mkdir(parents=True, exist_ok=False)
    config = json.loads(config_path.read_text())
    symbols = ",".join(x["symbol"] for x in config["instruments"])
    base = "https://data.alpaca.markets/v1beta3/crypto/us/"
    start = utc()
    (output / "collection_plan.json").write_text(json.dumps({"started_at_utc": start, "minutes": minutes, "interval": interval, "config": config, "mode": "public read-only; no account/API keys"}, indent=2) + "\n")
    end_clock = time.monotonic() + minutes * 60
    previous_end = dt.datetime.now(dt.timezone.utc) - dt.timedelta(seconds=65)
    count = 0
    requests = 0
    errors = 0
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
        while time.monotonic() < end_clock:
            cycle_clock = time.monotonic()
            current_end = dt.datetime.now(dt.timezone.utc)
            params = {"symbols": symbols, "start": previous_end.isoformat(), "end": current_end.isoformat(), "limit": 10000, "sort": "asc"}
            jobs = [("books", base + "latest/orderbooks?" + urllib.parse.urlencode({"symbols": symbols})), ("trades", base + "trades?" + urllib.parse.urlencode(params))]
            futures = [executor.submit(get_record, url, count, kind) for kind, url in jobs]
            results = [future.result() for future in futures]
            with (output / "raw.jsonl").open("a") as handle:
                for record in results:
                    record["complete_page"] = not record.get("body", {}).get("next_page_token")
                    handle.write(json.dumps(record) + "\n")
                    requests += 1
                    errors += record.get("http_status") != 200
            # Overlap by 3 seconds so trades arriving on interval boundaries can be de-duplicated.
            previous_end = current_end - dt.timedelta(seconds=3)
            count += 1
            if count % 6 == 0:
                print(json.dumps({"cycles": count, "http_requests": requests, "errors": errors, "at_utc": utc()}), flush=True)
            delay = min(end_clock - time.monotonic(), interval - (time.monotonic() - cycle_clock))
            if delay > 0:
                time.sleep(delay)
    summary = {"started_at_utc": start, "completed_at_utc": utc(), "cycles": count, "http_requests": requests, "http_errors": errors, "continuous_monitor": False}
    (output / "collection_summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps(summary), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=pathlib.Path, required=True)
    parser.add_argument("--minutes", type=float, default=12)
    parser.add_argument("--interval", type=float, default=10)
    parser.add_argument("--config", type=pathlib.Path, default=pathlib.Path(__file__).with_name("orderbook_config.json"))
    args = parser.parse_args()
    if not (0 < args.minutes <= 30 and args.interval >= 10):
        parser.error("bounded collector supports 0–30 minutes and interval >=10 seconds")
    collect(args.output, args.minutes, args.interval, args.config)
