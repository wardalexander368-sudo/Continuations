"""Who are the creation-slot buyers, and what do the ones an outsider competes with earn? (§3.18)

    python3 handoff/experiments/same_slot_who.py handoff/data/same-slot/launches.jsonl.gz [handoff/data/same-slot/blocks.jsonl]

Wallets are split by how they behave across launches:

* repeat snipers: buy in the creation slot of >= 5 launches from >= 5 different creators.
  A wallet funded by one deployer to fake early demand serves that deployer; a wallet
  that hits many unrelated creators' launches is a bot reacting to creates, i.e. the
  competition an outsider would face;
* one-off wallets: everything else (seen in 1-4 launches): mostly deployer-linked
  bundles, by Pine Analytics' tracing and by their sizes (round, identical amounts).

The realized result per (launch, wallet) comes from same_slot_entry.py (curve fee both
sides, unsold tokens marked at the last price, tips not included). With blocks.jsonl
(same_slot_blocks.py) it also reports where in the block the creation-slot buys sit and
what they paid to land there.
"""
import collections
import gzip
import json
import sys

import numpy as np

rows = [json.loads(line) for line in (gzip.open if sys.argv[1].endswith(".gz") else open)(sys.argv[1], "rt")]
creators_by_wallet = collections.defaultdict(set)
launches_by_wallet = collections.Counter()
for r in rows:
    for t in {x["trader"] for x in r["same_slot"] if x["side"] == "b" and not x["dev"]}:
        creators_by_wallet[t].add(r["creator"])
        launches_by_wallet[t] += 1
repeat = {t for t in launches_by_wallet if launches_by_wallet[t] >= 5 and len(creators_by_wallet[t]) >= 5}
print(f"{len(rows)} launches; {len(launches_by_wallet)} wallets bought in some creation slot; {len(repeat)} repeat snipers")
buys = [(r, x) for r in rows for x in r["same_slot"] if x["side"] == "b" and not x["dev"]]
nrep = sum(x["trader"] in repeat for _, x in buys)
print(f"outside creation-slot buys: {len(buys)}; by repeat snipers {nrep} ({100 * nrep / len(buys):.0f}%)")
with_rep = sum(any(x["trader"] in repeat for x in r["same_slot"]) for r in rows)
with_one = sum(any((not x["dev"]) and x["side"] == "b" and x["trader"] not in repeat for x in r["same_slot"]) for r in rows)
print(f"launches with a repeat sniper in the creation slot: {100 * with_rep / len(rows):.1f}%; with a one-off wallet: {100 * with_one / len(rows):.1f}%")

# position of the first repeat sniper among the slot's trades
pos = [next((j for j, x in enumerate(r["same_slot"]) if x["trader"] in repeat), None) for r in rows]
first = collections.Counter(p for p in pos if p is not None)
print("position of the first repeat-sniper buy in the slot (0 = right after the create):",
      {k: first[k] for k in sorted(first)[:8]})

rng = np.random.default_rng(0)


def summary(vals):
    v = np.array(vals)
    boots = v[rng.integers(0, len(v), (1000, len(v)))].mean(axis=1)
    lo, hi = np.quantile(boots, [0.05, 0.95])
    return f"n={len(v)} mean {100 * v.mean():+.1f}% [{100 * lo:+.1f},{100 * hi:+.1f}] median {100 * np.median(v):+.1f}% win {100 * (v > 0).mean():.0f}%"


rep_r, one_r = [], []
per_wallet = collections.defaultdict(list)
for r in rows:
    for t, x in (r.get("realized") or {}).items():
        (rep_r if t in repeat else one_r).append(x)
        if t in repeat:
            per_wallet[t].append(x)
print("\nRealized per position (before tips):")
print("  repeat snipers:", summary(rep_r))
print("  one-off wallets:", summary(one_r))
sizes = collections.defaultdict(list)
for r in rows:
    for x in r["same_slot"]:
        if x["side"] == "b" and not x["dev"] and x["trader"] in repeat:
            sizes[x["trader"]].append(x["sol"])
good = [t for t, xs in per_wallet.items() if np.mean(xs) > 0]
print(f"  repeat snipers with a positive mean before tips: {len(good)} of {len(per_wallet)}")
spent = {t: sum(sizes[t]) for t in per_wallet}
net = {t: sum(x * s for x, s in zip(per_wallet[t], sizes[t])) for t in per_wallet}
tot_s, tot_n = sum(spent.values()), sum(net.values())
print(f"  all repeat snipers together: {tot_s:.0f} SOL bought, {tot_n:+.1f} SOL net before tips ({100 * tot_n / tot_s:+.1f}%)")

if len(sys.argv) > 2:
    blocks = [json.loads(line) for line in open(sys.argv[2])]
    print(f"\nBlock positions ({len(blocks)} creation blocks fetched):")
    gaps, contig, tips, prios, rep_gaps, rep_tips, rep_prios, nonvote, idx_c = [], 0, [], [], [], [], [], [], []
    total = 0
    by_cls = collections.defaultdict(list)
    for b in blocks:
        ok = [h for h in b["touching"] if not h["err"]]
        if not ok:
            continue
        c = next((h for h in ok if h["payer"] == b["creator"]), ok[0])
        idx_c.append(c["i"] / max(b["block_txs"], 1))
        nonvote.append(b["nonvote_txs"])
        later = [h for h in ok if h["i"] > c["i"]]
        run = c["i"]
        for h in later:
            total += 1
            g = h["i"] - c["i"]
            in_run = h["i"] == run + 1
            if in_run:
                run = h["i"]
                contig += 1
            gaps.append(g)
            tips.append(h["tip"] / 1e9)
            prios.append(h["prio"] / 1e9)
            buyers = {x["trader"] for x in b["same_slot"] if x["side"] == "b" and not x["dev"]}
            cls = "repeat" if h["payer"] in repeat else "one-off" if h["payer"] in buyers else "other"
            by_cls[cls].append((in_run, g))
            if h["payer"] in repeat:
                rep_gaps.append(g)
                rep_tips.append(h["tip"] / 1e9)
                rep_prios.append(h["prio"] / 1e9)
    q = lambda v: np.quantile(v, [0.1, 0.5, 0.9]).round(6).tolist() if v else []  # noqa: E731
    print(f"  create sits at fraction {np.median(idx_c):.2f} of its block (median); blocks hold a median {np.median(nonvote):.0f} non-vote txs")
    print(f"  {total} later successful txs touching the mint; {contig} ({100 * contig / max(total, 1):.0f}%) in an unbroken run right after the create")
    print(f"  index gap after the create (p10/p50/p90): {q(gaps)}")
    print(f"  Jito tip SOL (p10/p50/p90): {q(tips)}; share with a tip {100 * np.mean(np.array(tips) > 0):.0f}%")
    print(f"  priority fee SOL (p10/p50/p90): {q(prios)}")
    for cls, v in sorted(by_cls.items()):
        print(f"  {cls:8s} {len(v):4d} txs: {100 * np.mean([a for a, _ in v]):.0f}% in the unbroken run after the create, median gap {np.median([g for _, g in v]):.0f}")
    if rep_gaps:
        print(f"  repeat snipers ({len(rep_gaps)} txs): gap {q(rep_gaps)}, tip {q(rep_tips)}, priority {q(rep_prios)}")

# Paper entries an outsider could aim for, from the rebuilt slot order (same_slot_entry.py --out).
sys.path.insert(0, ".")
from tartar.profit import buy_tokens, sell_sol  # noqa: E402

FEE, NET = 0.0125, 0.000105
print("\nPaper entries (curve fee 1.25%/side, network fees; priority fee as given; sold at the end of the slot `hold` later):")
scen = {
    "A first after the create (ahead of bundles and bots)": lambda r: 0,
    "B after the leading run of creator/one-off wallets (first among bots)": lambda r: next(
        (j for j, x in enumerate(r["same_slot"]) if x["trader"] in repeat), len(r["same_slot"])),
    "C a random place among the slot's repeat snipers": None,
    "D after every creation-slot trade": lambda r: len(r["same_slot"]),
}
prng = np.random.default_rng(1)
for size, prio in ((0.1, 0.0003), (0.1, 0.007), (1.0, 0.0003)):
    print(f"  size {size} SOL, priority {prio} SOL:")
    for name, f in scen.items():
        line = f"    {name}:"
        for h in ("10", "30", "60"):
            vals = []
            for r in rows:
                if "path" not in r or h not in r.get("exit", {}):
                    continue
                if f is None:
                    reps = [j for j, x in enumerate(r["same_slot"]) if x["trader"] in repeat]
                    j = int(prng.choice(reps + [reps[-1] + 1])) if reps else next(
                        (j for j, x in enumerate(r["same_slot"]) if x["trader"] in repeat), len(r["same_slot"]))
                else:
                    j = f(r)
                v, t = r["path"][j]
                xv, xt = r["exit"][h]
                tok = buy_tokens(v, t, size, FEE)
                vals.append((sell_sol(xv, xt, tok, FEE) - size - 2 * NET - prio) / size)
            v = np.array(vals)
            boots = v[prng.integers(0, len(v), (500, len(v)))].mean(axis=1)
            lo, hi = np.quantile(boots, [0.05, 0.95])
            line += f"  {h}s {100 * v.mean():+.1f}% [{100 * lo:+.1f},{100 * hi:+.1f}]"
        print(line + f"  (n={len(v)})")
