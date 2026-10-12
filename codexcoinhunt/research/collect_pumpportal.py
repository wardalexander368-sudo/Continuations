#!/usr/bin/env python3
"""Optional raw PumpPortal data recorder. Metered subscriptions incur costs.

No transaction creation, signing, or order API exists in this module.
Raw payloads are retained without inventing undocumented trade fields.
"""
import argparse
import asyncio
import datetime as dt
import json
import os
import pathlib


async def collect(args):
    try:
        import websockets
    except ImportError:
        raise RuntimeError("Install websockets in your own research virtual environment") from None
    key = os.environ.get("PUMPPORTAL_API_KEY", "")
    if not key:
        raise RuntimeError("PUMPPORTAL_API_KEY must be set locally; do not put credentials in project files")
    mints = []
    if args.mints_file:
        mints = [line.strip() for line in pathlib.Path(args.mints_file).read_text().splitlines() if line.strip()]
    if len(mints) > 20:
        raise RuntimeError("Subscribe only the shortlisted mints; this recorder caps a session at 20")
    destination = pathlib.Path(args.output)
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        raise RuntimeError("Choose a new output file to preserve session identity")
    uri = "wss://pumpportal.fun/api/data?api-key=" + key
    start = asyncio.get_running_loop().time()
    messages = 0
    async with websockets.connect(uri, ping_interval=20, max_size=2**20) as socket:
        for method in ("subscribeNewToken", "subscribeMigration"):
            await socket.send(json.dumps({"method": method}))
        if mints:
            await socket.send(json.dumps({"method": "subscribeTokenTrade", "keys": mints}))
        with destination.open("x") as file:
            while messages < args.max_messages:
                remaining = args.minutes * 60 - (asyncio.get_running_loop().time() - start)
                if remaining <= 0:
                    break
                try:
                    message = await asyncio.wait_for(socket.recv(), timeout=min(remaining, 30))
                except asyncio.TimeoutError:
                    continue
                clean_message = message.decode() if isinstance(message, bytes) else message
                clean_message = clean_message.replace(key, "[REDACTED]")
                row = {"received_at": dt.datetime.now(dt.timezone.utc).isoformat(), "sequence": messages, "provider": "PumpPortal", "raw_payload": json.loads(clean_message)}
                file.write(json.dumps(row) + "\n")
                file.flush()
                messages += 1
    print(json.dumps({"recorded_messages": messages, "metered_token_subscriptions": len(mints), "output": str(destination), "billing_note": "Provider charges apply to trade streams; count limit is not a billing guarantee"}))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mints-file", help="Optional newline-delimited shortlist; enabling this uses metered trade data")
    parser.add_argument("--output", default="data/pumpportal_raw.jsonl")
    parser.add_argument("--minutes", type=float, default=30)
    parser.add_argument("--max-messages", type=int, default=9000)
    args = parser.parse_args()
    if args.minutes <= 0 or args.max_messages <= 0:
        parser.error("minutes and max-messages must be positive")
    try:
        asyncio.run(collect(args))
    except KeyboardInterrupt:
        print("Recorder interrupted; existing raw evidence remains available")
    except Exception as exc:
        # Do not print websocket exception details: an endpoint can contain a key.
        print("Recorder stopped: " + type(exc).__name__ + ". Check local configuration and provider access.")
        raise SystemExit(1)


if __name__ == "__main__":
    main()
