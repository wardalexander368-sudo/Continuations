#!/usr/bin/env python3
"""Read-only, fixed-universe DEX Screener sampler. Does not place trades."""
import argparse
import datetime as dt
import json
import pathlib
import time
import urllib.error
import urllib.request

API = "https://api.dexscreener.com"
DISCOVERY = {
    "profiles": "/token-profiles/latest/v1",
    "boosts_latest": "/token-boosts/latest/v1",
    "boosts_top": "/token-boosts/top/v1",
    "takeovers": "/community-takeovers/latest/v1",
}


def now():
    return dt.datetime.now(dt.timezone.utc).isoformat()


def get(path):
    request = urllib.request.Request(API + path, headers={"User-Agent": "Resolant-Research/0.1", "Accept": "application/json"})
    started = now()
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            data = json.load(response)
        return {"requested_at": started, "received_at": now(), "path": path, "ok": True, "data": data}
    except (urllib.error.URLError, TimeoutError, ValueError) as exc:
        return {"requested_at": started, "received_at": now(), "path": path, "ok": False, "error": str(exc)}


def append(path, row):
    with path.open("a") as file:
        file.write(json.dumps(row, separators=(",", ":")) + "\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", default="data/session")
    parser.add_argument("--minutes", type=float, default=10)
    parser.add_argument("--interval", type=float, default=30)
    parser.add_argument("--max-tokens", type=int, default=90)
    args = parser.parse_args()
    if args.minutes <= 0 or args.interval < 10 or not 1 <= args.max_tokens <= 300:
        parser.error("minutes must be positive, interval >=10 seconds, max-tokens in 1..300")
    out = pathlib.Path(args.output)
    out.mkdir(parents=True, exist_ok=True)
    if (out / "universe.json").exists():
        parser.error("choose a new output directory: existing universe must not be overwritten")
    universe = {}
    for label, path in DISCOVERY.items():
        row = get(path)
        append(out / "discovery.jsonl", {"source": label, **row})
        if row["ok"] and isinstance(row["data"], list):
            for item in row["data"]:
                if item.get("chainId") == "solana" and item.get("tokenAddress"):
                    mint = item["tokenAddress"]
                    universe.setdefault(mint, {"mint": mint, "first_observed_at": row["received_at"], "sources": []})["sources"].append(label)
    selected = list(universe.values())[:args.max_tokens]
    meta = {"started_at": now(), "chain": "solana", "selection": "API response order; frozen before future prices; visibility-biased, NOT a launch census", "max_tokens": args.max_tokens, "discovered_count": len(universe), "tokens": selected, "status": "data collection only; no social or wallet independence inferred"}
    (out / "universe.json").write_text(json.dumps(meta, indent=2) + "\n")
    mints = [item["mint"] for item in selected]
    if not mints:
        print(json.dumps({"status": "no_universe", "output": str(out)}), flush=True)
        return
    started = time.monotonic()
    seq = 0
    while time.monotonic() - started < args.minutes * 60:
        cycle_start = time.monotonic()
        for offset in range(0, len(mints), 30):
            group = mints[offset:offset + 30]
            row = get("/tokens/v1/solana/" + ",".join(group))
            append(out / "snapshots.jsonl", {"sequence": seq, "requested_mints": group, **row})
        print(json.dumps({"cycle": seq, "received_at": now(), "tokens": len(mints), "output": str(out)}), flush=True)
        seq += 1
        remaining = min(args.interval - (time.monotonic() - cycle_start), args.minutes * 60 - (time.monotonic() - started))
        if remaining > 0:
            time.sleep(remaining)
    (out / "collection_summary.json").write_text(json.dumps({"completed_at": now(), "cycles": seq, "universe_tokens": len(mints), "elapsed_seconds": time.monotonic() - started, "trades": 0}, indent=2) + "\n")


if __name__ == "__main__":
    main()
