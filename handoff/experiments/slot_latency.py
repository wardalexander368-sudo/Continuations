"""Latency in slots, from raw logs recorded with "slot" (chain recorder, 2026-10-09 on).

    python3 handoff/experiments/slot_latency.py data/raw_slots [--block-times 60]

Reports:
1. How many slots after its launch each trade lands, and the share of the first
   minute's buy volume landing in the launch's own slot, the next one, ...: how
   fast an entry must be to buy alongside the early buyers.
2. Notification delay: receive time minus the slot's block time (getBlockTime,
   whole seconds, sampled over HTTP; +/-0.5 s each, so read the median), and the
   spread of receive times within one slot.
3. Where a decision made `screen` seconds after a launch would land, in slots.
"""

import argparse
import collections
import statistics
import sys
import time

sys.path.insert(0, ".")
from tartar.data.rawlog import raw_files, read_events  # noqa: E402

parser = argparse.ArgumentParser()
parser.add_argument("raw")
parser.add_argument("--block-times", type=int, default=60, help="slots to sample for getBlockTime (0 = skip)")
parser.add_argument("--screen", type=float, default=20.0, help="seconds from launch to the decision")
args = parser.parse_args()

events = [e for e in read_events(raw_files(args.raw)) if e.get("slot") is not None]
creates = {e["mint"]: e for e in events if e["e"] == "create"}
trades = [e for e in events if e["e"] == "trade" and e["mint"] in creates]
print(f"{len(events)} events with slots: {len(creates)} launches, {len(trades)} trades on them")
if not trades:
    raise SystemExit("no slot-annotated trades")

# 1. trades by slot offset from their launch
offsets = collections.Counter()
buy_sol = collections.Counter()
first_minute_buy_sol = 0.0
for e in trades:
    d = e["slot"] - creates[e["mint"]]["slot"]
    offsets[min(d, 999)] += 1
    if e.get("side") == "b" and e["t"] - creates[e["mint"]]["t"] <= 60:
        bucket = d if d < 5 else (5 if d < 10 else (10 if d < 25 else (25 if d < 50 else 50)))
        buy_sol[bucket] += e.get("sol") or 0.0
        first_minute_buy_sol += e.get("sol") or 0.0
print("\n1. slot offset of trades after their launch (0 = same slot as the create)")
total = sum(offsets.values())
for lo, hi in ((0, 1), (1, 2), (2, 3), (3, 5), (5, 10), (10, 25), (25, 50), (50, 150), (150, 1000)):
    n = sum(v for k, v in offsets.items() if lo <= k < hi)
    print(f"   [{lo:>3}, {hi:>4}) slots: {n:6d} trades ({n / total:6.1%})")
print(f"   buy SOL in the first 60 s by slot offset (total {first_minute_buy_sol:.1f} SOL):")
for k in sorted(buy_sol):
    label = {5: "5-9", 10: "10-24", 25: "25-49", 50: "50+"}.get(k, str(k))
    print(f"     {label:>6}: {buy_sol[k]:8.2f} SOL ({buy_sol[k] / max(first_minute_buy_sol, 1e-9):6.1%})")

# 2. receive spread within a slot, and delay vs block time
by_slot = collections.defaultdict(list)
for e in events:
    if e["e"] in ("create", "trade"):
        by_slot[e["slot"]].append(e["t"])
spread = [max(ts) - min(ts) for ts in by_slot.values() if len(ts) >= 3]
print(f"\n2. slots seen: {len(by_slot)}; receive-time spread within a slot (slots with 3+ events): "
      f"median {statistics.median(spread):.2f} s, p90 {sorted(spread)[int(0.9 * len(spread))]:.2f} s" if spread else "")
slots = sorted(by_slot)
if len(slots) > 1:
    span = slots[-1] - slots[0]
    secs = min(by_slot[slots[-1]]) - min(by_slot[slots[0]])
    print(f"   {span} slots in {secs:.0f} s of receive time: {secs / max(span, 1) * 1000:.0f} ms per slot")
if args.block_times:
    import httpx

    client = httpx.Client(timeout=20)
    step = max(1, len(slots) // args.block_times)
    delays = []
    for slot in slots[::step][: args.block_times]:
        for attempt in range(5):
            r = client.post("https://api.mainnet-beta.solana.com", json={"jsonrpc": "2.0", "id": 1, "method": "getBlockTime", "params": [slot]})
            if r.status_code != 429:
                break
            time.sleep(2**attempt)
        block_time = r.json().get("result")
        if isinstance(block_time, int):
            delays.append(min(by_slot[slot]) - block_time)
        time.sleep(0.3)
    if delays:
        delays.sort()
        print(f"   first receive minus block time over {len(delays)} slots (block time in whole seconds): "
              f"median {statistics.median(delays):.2f} s, p10 {delays[len(delays) // 10]:.2f} s, p90 {delays[9 * len(delays) // 10]:.2f} s")

# 3. where a decision `screen` seconds after the launch lands
gaps = []
for mint, c in creates.items():
    later = [e for e in trades if e["mint"] == mint and e["t"] >= c["t"] + args.screen]
    if later:
        gaps.append(later[0]["slot"] - c["slot"])
if gaps:
    print(f"\n3. first trade at or after launch + {args.screen:.0f} s lands {statistics.median(gaps):.0f} slots after the create "
          f"(median over {len(gaps)} launches); a fill needs at least one more slot after the decision")
