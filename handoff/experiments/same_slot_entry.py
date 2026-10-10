"""Who buys in a launch's own slot, where in the slot, and do they make money? (§3.18)

    python3 handoff/experiments/same_slot_entry.py handoff/data/raw-slots handoff/data/raw-clever ... \
        [--fee 0.0125] [--size 0.1] [--tip 0.001] [--out handoff/data/same-slot/launches.jsonl]

§3.9 found one profitable launch entry: a buy right after the create, inside the creation
slot. This script asks whether an outsider can get it. For every SOL launch with a creator
buy and a slot-annotated create, it rebuilds the order of the creation slot's trades by
chaining reserves (each trade's pre-trade virtual SOL equals the previous trade's
post-trade virtual SOL, starting from the create's post-buy state) and reports:

* how many trades land in the creation slot, and whose they are (the creator's own wallet
  or another one);
* the paper return of a buy entering at position j of the slot (j = 0 is right after the
  create, j = 1 after the first same-slot trade, ...), sold at the end of the slot `hold`
  seconds later, with the same costs as slot_profit.py;
* the realized result of each real same-slot buyer that is not the creator: SOL out of
  its sells over SOL into its buys on that token (both with the curve fee), unsold tokens
  marked at the token's last recorded price. Tips they paid are not visible here, so this
  is an upper bound on what they made.

A mint recorded by several recorders (overlapping hours) is counted once, from the first
directory given that has it.
"""
import argparse
import collections
import json
import os
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
parser.add_argument("--tip", type=float, default=0.001)
parser.add_argument("--holds", default="10,30,60,180")
parser.add_argument("--positions", type=int, default=6, help="report entry positions 0..N-1 in the creation slot")
parser.add_argument("--out", default=None, help="write one JSON line per launch (slot order, buyers)")
args = parser.parse_args()
holds = [float(h) for h in args.holds.split(",")]
SEC_PER_SLOT = 0.4  # replaced per directory by the measured value below


def pre_vsol(e):
    sol = e.get("sol") or 0.0
    return e["vsol"] - sol if e.get("side") == "b" else e["vsol"] + sol


def chain(start_vsol, es):
    """Order `es` (one slot's trades) by reserve chaining from `start_vsol`. Returns (ordered, complete)."""
    left = list(es)
    out = []
    cur = start_vsol
    while left:
        hit = [e for e in left if abs(pre_vsol(e) - cur) <= 1e-6 * max(cur, 1.0)]
        if not hit:
            break
        e = min(hit, key=lambda x: x["t"])
        out.append(e)
        left.remove(e)
        cur = e["vsol"]
    return out, not left


def end_states(trades, create_slot, after_create):
    """{slot: (vsol, vtok)} at the end of each slot that had trades (reserve chaining picks the last)."""
    group = collections.defaultdict(list)
    for e in trades:
        group[e["slot"]].append(e)
    out = {}
    for slot, es in group.items():
        pres = [pre_vsol(e) for e in es]
        ends = [e for e in es if not any(abs(e["vsol"] - p) <= 1e-7 * e["vsol"] for p in pres)]
        last = max(ends or es, key=lambda e: e["t"])
        out[slot] = (last["vsol"], last["vtok"])
    out.setdefault(create_slot, after_create)
    return out


seen = set()
launches = []  # per-launch dicts
paper = {(h, j): [] for h in holds for j in range(args.positions)}
paper_after_all = {h: [] for h in holds}  # enter after every same-slot trade (= slot_profit "last")
realized = []  # (launch index, trader, net fraction, buy SOL)
for d in args.raw:
    events = [e for e in read_events(raw_files(d)) if e.get("slot") is not None and e["e"] in ("create", "trade")]
    if not events:
        continue
    creates = {e["mint"]: e for e in events if e["e"] == "create" and not e.get("quote") and e["mint"] not in seen}
    trades = collections.defaultdict(list)
    for e in events:
        if e["e"] == "trade" and e["mint"] in creates and not e.get("quote") and e.get("vsol"):
            trades[e["mint"]].append(e)
    last_slot = max(e["slot"] for e in events)
    by_slot = collections.defaultdict(list)
    for e in events:
        by_slot[e["slot"]].append(e["t"])
    slots = sorted(by_slot)
    med = {s: float(np.median(by_slot[s])) for s in slots}
    pairs = [(b - a, med[b] - med[a]) for a, b in zip(slots, slots[1:]) if 0 < b - a <= 50]
    sps = float(np.median([dt / ds for ds, dt in pairs if dt > 0]))
    n_dir = 0
    for mint, c in creates.items():
        seen.add(mint)
        if not c.get("vsol") or not c.get("vtok"):
            continue  # no creator buy: no price at creation
        n_dir += 1
        s0 = c["slot"]
        ts = sorted(trades[mint], key=lambda e: (e["slot"], e["t"]))
        same = [e for e in ts if e["slot"] == s0]
        ordered, complete = chain(c["vsol"], same)
        after_create = (c["vsol"], c["vtok"])
        rec = {
            "mint": mint, "dir": os.path.basename(d.rstrip("/")), "slot": s0, "creator": c["creator"],
            "dev_sol": c.get("sol"), "complete": complete,
            "same_slot": [{"side": e["side"], "sol": e["sol"], "trader": e["trader"], "dev": e["trader"] == c["creator"]}
                          for e in (ordered if complete else same)],
        }
        launches.append(rec)
        states = end_states(ts, s0, after_create)
        order = np.array(sorted(states))
        if complete:
            path = [after_create] + [(e["vsol"], e["vtok"]) for e in ordered]
            rec["path"] = [[round(v, 9), round(t, 3)] for v, t in path]
            rec["exit"] = {}
            for h in holds:
                hs = int(round(h / sps))
                if s0 + hs > last_slot - 5:
                    continue
                i = np.searchsorted(order, s0 + hs, side="right") - 1
                xv, xt = states[order[i]]
                rec["exit"][f"{h:g}"] = [round(xv, 9), round(xt, 3)]
                for j in range(args.positions):
                    if j >= len(path):
                        break
                    v, t = path[j]
                    tok = buy_tokens(v, t, args.size, args.fee)
                    pnl = sell_sol(xv, xt, tok, args.fee) - args.size - 2 * args.network - args.tip
                    paper[(h, j)].append((len(launches) - 1, pnl / args.size))
                v, t = path[-1]
                tok = buy_tokens(v, t, args.size, args.fee)
                pnl = sell_sol(xv, xt, tok, args.fee) - args.size - 2 * args.network - args.tip
                paper_after_all[h].append((len(launches) - 1, pnl / args.size))
        # realized results of same-slot outside buyers over the whole recorded window
        if ts and ts[-1]["slot"] < last_slot - 5:
            lv, lt = ts[-1]["vsol"], ts[-1]["vtok"]
        elif ts:
            lv, lt = ts[-1]["vsol"], ts[-1]["vtok"]
        else:
            lv, lt = after_create
        for trader in {e["trader"] for e in same if e["side"] == "b" and e["trader"] != c["creator"]}:
            mine = [e for e in ts if e["trader"] == trader]
            spent = sum(e["sol"] * (1 + args.fee) for e in mine if e["side"] == "b")
            got = sum(e["sol"] * (1 - args.fee) for e in mine if e["side"] == "s")
            held = sum(e["tok"] for e in mine if e["side"] == "b") - sum(e["tok"] for e in mine if e["side"] == "s")
            if held > 0:
                got += sell_sol(lv, lt, held, args.fee)
            if spent > 0:
                realized.append((len(launches) - 1, trader, got / spent - 1, spent))
                rec.setdefault("realized", {})[trader] = round(got / spent - 1, 5)
    print(f"{d}: {n_dir} SOL launches with a creator buy, ~{sps:.3f} s/slot", file=sys.stderr)

rng = np.random.default_rng(0)


def ci(vals, groups):
    """Mean and 90% CI, bootstrapping launches (several values can share one launch)."""
    vals = np.asarray(vals)
    groups = np.asarray(groups)
    uniq, inv = np.unique(groups, return_inverse=True)
    sums = np.bincount(inv, weights=vals)
    cnts = np.bincount(inv)
    idx = rng.integers(0, len(uniq), (1000, len(uniq)))
    boots = sums[idx].sum(axis=1) / cnts[idx].sum(axis=1)
    lo, hi = np.quantile(boots, [0.05, 0.95])
    return vals.mean(), lo, hi


n = len(launches)
complete = [r for r in launches if r["complete"]]
print(f"{n} SOL launches with a creator buy; creation slot order rebuilt for {len(complete)} ({100 * len(complete) / n:.1f}%)\n")
cnt = collections.Counter()
for r in complete:
    others = [x for x in r["same_slot"] if not x["dev"]]
    k = len(others)
    cnt["0" if k == 0 else "1" if k == 1 else "2-4" if k <= 4 else "5+"] += 1
    cnt["dev_extra"] += any(x["dev"] for x in r["same_slot"])
print("Trades by other wallets in the creation slot (after the create):")
for key in ("0", "1", "2-4", "5+"):
    print(f"  {key:>4}: {cnt[key]:6d}  {100 * cnt[key] / len(complete):5.1f}%")
print(f"  launches where the creator's wallet trades again in its own slot: {100 * cnt['dev_extra'] / len(complete):.1f}%")
buys = [x for r in complete for x in r["same_slot"] if x["side"] == "b" and not x["dev"]]
print(f"  outside same-slot buys: {len(buys)}, median {np.median([b['sol'] for b in buys]):.3f} SOL\n")

print(f"Paper entry at position j of the creation slot (size {args.size} SOL, fee {100 * args.fee:.2f}%/side, tip {args.tip} SOL):")
for h in holds:
    line = f"  hold {h:>4g} s:"
    for j in range(args.positions):
        rs = paper[(h, j)]
        if len(rs) < 30:
            continue
        m, lo, hi = ci([x for _, x in rs], [g for g, _ in rs])
        line += f"  j={j} {100 * m:+5.1f}% [{100 * lo:+.1f},{100 * hi:+.1f}] n={len(rs)}"
    rs = paper_after_all[h]
    m, lo, hi = ci([x for _, x in rs], [g for g, _ in rs])
    print(line + f"  | after all {100 * m:+5.1f}% [{100 * lo:+.1f},{100 * hi:+.1f}]")

# entry right after the create, split by how many outsiders came after it (is j=0 only good when snipers pile in?)
print("\nj=0 (right after the create), hold 10 s, by outside same-slot trades:")
outsiders = {i: sum(not x["dev"] for x in launches[i]["same_slot"]) for i in range(n)}
for name, test in (("none", lambda k: k == 0), ("1", lambda k: k == 1), ("2-4", lambda k: 2 <= k <= 4), ("5+", lambda k: k >= 5)):
    rs = [(g, x) for g, x in paper[(holds[0], 0)] if test(outsiders[g])]
    if len(rs) >= 30:
        m, lo, hi = ci([x for _, x in rs], [g for g, _ in rs])
        print(f"  {name:>4}: {100 * m:+5.1f}% [{100 * lo:+.1f},{100 * hi:+.1f}] n={len(rs)}")

if realized:
    m, lo, hi = ci([x for _, _, x, _ in realized], [g for g, _, _, _ in realized])
    w = np.array([s for *_, s in realized])
    r = np.array([x for _, _, x, _ in realized])
    print(f"\nReal same-slot outside buyers, realized over the recorded window (curve fee both sides, no tips):")
    print(f"  {len(realized)} positions in {len({g for g, *_ in realized})} launches: mean {100 * m:+.1f}% [{100 * lo:+.1f},{100 * hi:+.1f}],"
          f" SOL-weighted {100 * (r * w).sum() / w.sum():+.1f}%, median {100 * np.median(r):+.1f}%, win {100 * (r > 0).mean():.0f}%")
    by_wallet = collections.defaultdict(list)
    for _, t, x, s in realized:
        by_wallet[t].append((x, s))
    top = sorted(by_wallet.items(), key=lambda kv: -len(kv[1]))[:10]
    print(f"  {len(by_wallet)} distinct wallets; the 10 most active:")
    for t, xs in top:
        spent = sum(s for _, s in xs)
        net = sum(x * s for x, s in xs)
        print(f"    {t[:8]}…  {len(xs):5d} launches  spent {spent:8.2f} SOL  net {net:+8.2f} SOL ({100 * net / spent:+.1f}%)")

if args.out:
    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w") as f:
        for r in launches:
            f.write(json.dumps(r) + "\n")
