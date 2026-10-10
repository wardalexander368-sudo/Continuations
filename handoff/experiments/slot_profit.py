"""How fast must a launch buy land to make money? Round trips timed in slots, not receive time.

    python3 handoff/experiments/slot_profit.py handoff/data/raw-slots [--size 0.1] [--fee 0.0125] [--tip 0.001]

For each SOL-quoted launch with a slot-annotated create, a buy lands k slots after
the create's slot and is sold `hold` seconds later (converted to slots with the
recording's own seconds-per-slot). Within a slot the order of trades is rebuilt by
chaining reserves (a trade's pre-trade SOL reserve is the previous trade's post-trade
reserve), and the fill is bounded two ways:

* first: the buy is the first transaction in its slot (the state at the end of slot k-1);
* last:  the buy is the last transaction in its slot (the state at the end of slot k).

k = 0 "first" is the price right after the create (and its creator buy): only a
transaction bundled with the creation itself can get it.

Costs: the bonding-curve fee per side, network fee per transaction, and a priority tip on
the buy (landing within a few slots means outbidding other bots; set `--tip`). Exits are
not time-critical and pay the network fee only.
"""
import argparse
import collections
import math
import sys

import numpy as np

sys.path.insert(0, ".")
from tartar.data.rawlog import raw_files, read_events  # noqa: E402
from tartar.profit import buy_tokens, sell_sol  # noqa: E402

parser = argparse.ArgumentParser()
parser.add_argument("raw", nargs="+")
parser.add_argument("--size", type=float, default=0.1)
parser.add_argument("--fee", type=float, default=0.0125)
parser.add_argument("--network", type=float, default=0.000005 + 0.0001)
parser.add_argument("--tip", type=float, default=0.001, help="SOL paid to land the buy fast (Jito tip / priority fee)")
parser.add_argument("--holds", default="10,30,60,180")
args = parser.parse_args()

events = [e for d in args.raw for e in read_events(raw_files(d)) if e.get("slot") is not None]
creates = {e["mint"]: e for e in events if e["e"] == "create" and not e.get("quote")}
trades = collections.defaultdict(list)
for e in events:
    if e["e"] == "trade" and e["mint"] in creates and not e.get("quote") and e.get("vsol"):
        trades[e["mint"]].append(e)
last_slot = max(e["slot"] for e in events)
# seconds per slot, from receive times (median of consecutive-slot differences, robust to delivery jitter)
by_slot = collections.defaultdict(list)
for e in events:
    by_slot[e["slot"]].append(e["t"])
slots = sorted(by_slot)
med = {s: float(np.median(by_slot[s])) for s in slots}
pairs = [(b - a, med[b] - med[a]) for a, b in zip(slots, slots[1:]) if 0 < b - a <= 50]
sec_per_slot = float(np.median([dt / ds for ds, dt in pairs if dt > 0]))
print(f"{len(creates)} SOL launches with slots, {sum(len(v) for v in trades.values())} trades; ~{sec_per_slot:.3f} s per slot")


def pre_vsol(e):
    sol = e.get("sol") or 0.0
    return e["vsol"] - sol if e.get("side") == "b" else e["vsol"] + sol


def slot_states(mint):
    """{slot: (vsol, price) at the end of that slot}, from reserve chaining within each slot."""
    out = {}
    create = creates[mint]
    group = collections.defaultdict(list)
    for e in trades[mint]:
        group[e["slot"]].append(e)
    for slot, es in group.items():
        pres = [pre_vsol(e) for e in es]
        ends = [e for e in es if not any(abs(e["vsol"] - p) <= 1e-7 * e["vsol"] for p in pres)]
        last = max(ends or es, key=lambda e: e["t"])
        out[slot] = (last["vsol"], last["vsol"] / last["vtok"])
    if create.get("vsol") and create.get("vtok"):
        out.setdefault(create["slot"], (create["vsol"], create["vsol"] / create["vtok"]))
    return out


def state_at_end(states, ordered, slot, create_state):
    """End-of-slot state for `slot` (the latest slot <= it that had a trade)."""
    i = np.searchsorted(ordered, slot, side="right") - 1
    if i < 0:
        return create_state
    return states[ordered[i]]


holds = [float(h) for h in args.holds.split(",")]
K = [0, 1, 2, 3, 5, 10, 20, 50, 100]
results = {(h, k, b): [] for h in holds for k in K for b in ("first", "last")}
skipped = 0
for mint, create in creates.items():
    if not create.get("vsol"):
        skipped += 1  # no first buy in the create: no price until someone trades
        continue
    states = slot_states(mint)
    ordered = np.array(sorted(states))
    s0 = create["slot"]
    after_create = (create["vsol"], create["vsol"] / create["vtok"])
    for h in holds:
        h_slots = int(round(h / sec_per_slot))
        for k in K:
            if s0 + k + h_slots > last_slot - 5:
                continue  # the recording ends before the exit
            exit_state = state_at_end(states, ordered, s0 + k + h_slots, after_create)
            for bound in ("first", "last"):
                if k == 0 and bound == "first":
                    entry = after_create
                else:
                    entry = state_at_end(states, ordered, s0 + k - (1 if bound == "first" else 0), after_create)
                vsol, price = entry
                tokens = buy_tokens(vsol, vsol / price, args.size, args.fee)
                xv, xp = exit_state
                proceeds = sell_sol(xv, xv / xp, tokens, args.fee)
                pnl = proceeds - args.size - 2 * args.network - args.tip
                results[(h, k, bound)].append(pnl / args.size)
print(f"skipped {skipped} launches with no creator buy (no price at creation)")
print(f"size {args.size} SOL, fee {100 * args.fee:.2f}%/side, network {args.network} SOL/tx, tip {args.tip} SOL on the buy\n")
rng = np.random.default_rng(0)
for h in holds:
    print(f"hold {h:g} s ({int(round(h / sec_per_slot))} slots)        mean net   [90% CI]           median    win")
    for k in K:
        line = f"  land at slot +{k:<3d} "
        for bound in ("first", "last"):
            r = np.array(results[(h, k, bound)])
            if not len(r):
                line += f"  {bound}: no data"
                continue
            boots = r[rng.integers(0, len(r), (2000, len(r)))].mean(axis=1)
            lo, hi = np.quantile(boots, [0.05, 0.95])
            line += f"  {bound:5s} {100 * r.mean():+6.2f}% [{100 * lo:+6.2f},{100 * hi:+6.2f}] {100 * np.median(r):+6.2f}% {100 * (r > 0).mean():4.1f}%"
        print(line + f"  (n={len(results[(h, k, 'last')])})")
    print()
